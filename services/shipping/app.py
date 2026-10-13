import os, time, random
from fastapi import FastAPI, Request
from prometheus_client import Counter, Histogram, make_asgi_app
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

SERVICE = os.getenv("SERVICE_NAME", "shipping-service")
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

@app.post("/create")
async def create_shipment():
    with tracer.start_as_current_span("shipping.create_shipment"):
        time.sleep(random.uniform(0.04, 0.15))
        return {"shipment_id": "ship-demo-123", "status": "created"}

FastAPIInstrumentor.instrument_app(app)
