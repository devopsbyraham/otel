import os, time, random
from fastapi import FastAPI, HTTPException, Request
from prometheus_client import Counter, Histogram, make_asgi_app
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

SERVICE = os.getenv("SERVICE_NAME", "inventory-service")
resource = Resource.create({"service.name": SERVICE})
provider = TracerProvider(resource=resource)
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
        elapsed = time.perf_counter() - start
        route = request.url.path
        REQUESTS.labels(SERVICE, route, status).inc()
        LATENCY.labels(SERVICE, route).observe(elapsed)

@app.get("/health")
def health():
    return {"service": SERVICE, "status": "ok"}

@app.get("/stock/{sku}")
async def stock(sku: str, scenario: str = "normal"):
    with tracer.start_as_current_span("inventory.check_stock") as span:
        span.set_attribute("app.sku", sku)
        if scenario == "slow_inventory":
            time.sleep(1.2)
        else:
            time.sleep(random.uniform(0.03, 0.12))
        if scenario == "fail_inventory":
            span.set_attribute("app.failure_reason", "simulated_out_of_stock")
            raise HTTPException(status_code=409, detail="Item is out of stock (simulated)")
        return {"sku": sku, "available": True}

FastAPIInstrumentor.instrument_app(app)
