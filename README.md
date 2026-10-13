# Python Microservices Telemetry Lab

A teaching lab for distributed traces, latency, request metrics, errors, and incident troubleshooting.

## Architecture
- `order-service` calls `inventory-service`, `payment-service`, and `shipping-service` sequentially.
- OpenTelemetry instruments FastAPI server requests and HTTPX client calls. Trace context propagates across HTTP requests.
- OpenTelemetry Collector receives spans over OTLP and exports them to Jaeger.
- Prometheus scrapes each service's `/metrics` endpoint.
- Grafana is connected to Prometheus as a datasource.

## Requirements
- Docker Desktop or Docker Engine with the Docker Compose plugin.
- Ports 3000, 8001-8004, 9090, 16686, 4317 and 4318 available.

## 1. Start the lab
From this folder:

```bash
docker compose up --build -d
docker compose ps
```

Give the containers 30-60 seconds to initialize. If anything fails:
```bash
docker compose logs -f order-service
docker compose logs -f otel-collector
docker compose logs -f jaeger
```

## 2. Create normal traffic
```bash
curl -s -X POST 'http://localhost:8001/orders?scenario=normal'
```
Run it several times to create enough traces and metrics.

## 3. Create a slow payment
```bash
curl -s -X POST 'http://localhost:8001/orders?scenario=slow_payment'
```
This makes inventory wait normally but adds about two seconds inside payment. Open Jaeger at http://localhost:16686, choose `order-service`, click Find Traces, and open a trace. Find the long `POST` client span and the `payment.charge` span. Exact durations vary by machine.

## 4. Create a slow inventory request
```bash
curl -s -X POST 'http://localhost:8001/orders?scenario=slow_inventory'
```
Compare the trace with `slow_payment`. Identify which span became longer.

## 5. Simulate errors
Inventory error:
```bash
curl -i -X POST 'http://localhost:8001/orders?scenario=fail_inventory'
```
Payment error:
```bash
curl -i -X POST 'http://localhost:8001/orders?scenario=fail_payment'
```
Inspect the trace status, failed span, HTTP status code, and the `app.failed_dependency` attribute on the order span.

## 6. Explore metrics
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (login: admin / admin; change password if prompted)

Try these PromQL expressions in Prometheus or Grafana:

Request rate:
```promql
sum by (service) (rate(http_requests_total[1m]))
```

Error responses:
```promql
sum by (service) (rate(http_requests_total{status=~"4..|5.."}[5m]))
```

Approximate p95 request duration by service:
```promql
histogram_quantile(0.95, sum by (le, service) (rate(http_request_duration_seconds_bucket[5m])))
```

Average request duration by service:
```promql
sum by (service) (rate(http_request_duration_seconds_sum[5m]))
/
sum by (service) (rate(http_request_duration_seconds_count[5m]))
```

If the graph is empty, send traffic first and wait for at least one scrape interval.

## 7. Important concepts to teach
- Trace: one end-to-end request, identified by a trace ID.
- Span: one timed operation within a trace. Spans have parent-child relationships.
- Context propagation: the trace context is sent in HTTP headers so downstream spans belong to the same trace.
- Latency: elapsed time for an operation. Sequential downstream calls add to the end-to-end latency.
- Metrics: aggregated measurements over time, such as request counts, error counts, and latency histograms.
- p95 latency: 95% of observed requests completed at or below this duration.
- Logs: event records that help explain why an operation failed. This starter lab does not add structured application logs or log/trace correlation; those are optional extensions.

## 8. Hands-on challenges
1. Run 10 normal requests and compare trace durations.
2. Run 5 slow-payment requests. Find the longest span and estimate the payment contribution.
3. Compare p95 before and after slow requests.
4. Trigger each failure. Identify the first failing service and the HTTP status.
5. Stop the payment container (`docker compose stop payment-service`) and observe the order-service error/trace. Restart it (`docker compose start payment-service`).
6. Stop shipping and observe the effect.
7. Change `slow_payment` from 2.0 seconds to 4.0 seconds in `services/payment/app.py`, rebuild, and measure again.
8. Add a `quantity` attribute to the order span and inspect it in Jaeger. Do not add customer names, emails, tokens, or payment card data to span attributes.

## 9. Troubleshooting
- `docker compose ps`: see whether all services are running.
- `docker compose logs -f <service-name>`: inspect container logs.
- No traces: verify the collector is running and check its logs. Wait a few seconds for batch export.
- No metrics: open `http://localhost:8001/metrics`; ensure Prometheus targets are UP at `http://localhost:9090/targets`.
- Jaeger is at `http://localhost:16686`.
- This is a local teaching demo, not a production-ready deployment. It uses demo responses, simple in-memory metrics, no authentication, and no real payment provider.
## 10. Stop the lab
```bash
docker compose down
```
To remove persisted container state too (not needed for this lab):
```bash
docker compose down -v
```
