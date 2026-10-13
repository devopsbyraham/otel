import os, time, random
from fastapi import FastAPI, HTTPException, Request
from prometheus_client import Counter, Histogram, make_asgi_app
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

SERVICE = os.getenv("SERVICE_NAME", "payment-service")
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

@app.post("/charge")
async def charge(scenario: str = "normal"):
    with tracer.start_as_current_span("payment.charge") as span:
        if scenario == "slow_payment":
            time.sleep(2.0)
        else:
            time.sleep(random.uniform(0.08, 0.22))
        if scenario == "fail_payment":
            span.set_attribute("app.failure_reason", "simulated_payment_declined")
            raise HTTPException(status_code=402, detail="Payment declined (simulated)")
        return {"payment_id": "pay-demo-123", "status": "approved"}

FastAPIInstrumentor.instrument_app(app)
