import os, time
import httpx
from fastapi import FastAPI, HTTPException, Request
from prometheus_client import Counter, Histogram, make_asgi_app
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

SERVICE = os.getenv("SERVICE_NAME", "order-service")
provider = TracerProvider(resource=Resource.create({"service.name": SERVICE}))
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

app = FastAPI(title=SERVICE)
app.mount("/metrics", make_asgi_app())
REQUESTS = Counter("http_requests_total", "HTTP requests", ["service", "route", "status"])
LATENCY = Histogram("http_request_duration_seconds", "Request duration", ["service", "route"])

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)
    start = time.perf_counter()
    status = "500"
    try:
        response = await call_next(request)
        status = str(response.status_code)
        return response
    finally:
        REQUESTS.labels(SERVICE, request.url.path, status).inc()
        LATENCY.labels(SERVICE, request.url.path).observe(time.perf_counter() - start)

@app.get("/health")
def health():
    return {"service": SERVICE, "status": "ok"}

@app.post("/orders")
async def create_order(scenario: str = "normal"):
    with tracer.start_as_current_span("order.create") as span:
        span.set_attribute("app.scenario", scenario)
        inventory = os.getenv("INVENTORY_URL")
        payment = os.getenv("PAYMENT_URL")
        shipping = os.getenv("SHIPPING_URL")
        timeout = httpx.Timeout(5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Calls are sequential on purpose so students can see each latency contribution.
            stock = await client.get(f"{inventory}/stock/SKU-101", params={"scenario": scenario})
            if stock.status_code >= 400:
                span.set_attribute("app.failed_dependency", "inventory-service")
                raise HTTPException(status_code=stock.status_code, detail={"dependency": "inventory-service", "response": stock.text})
            charge = await client.post(f"{payment}/charge", params={"scenario": scenario})
            if charge.status_code >= 400:
                span.set_attribute("app.failed_dependency", "payment-service")
                raise HTTPException(status_code=charge.status_code, detail={"dependency": "payment-service", "response": charge.text})
            ship = await client.post(f"{shipping}/create")
            if ship.status_code >= 400:
                span.set_attribute("app.failed_dependency", "shipping-service")
                raise HTTPException(status_code=ship.status_code, detail={"dependency": "shipping-service", "response": ship.text})
        return {
            "order_id": "order-demo-123",
            "status": "created",
            "inventory": stock.json(),
            "payment": charge.json(),
            "shipping": ship.json(),
            "scenario": scenario
        }

FastAPIInstrumentor.instrument_app(app)
HTTPXClientInstrumentor().instrument()
