from prometheus_client import Counter, Histogram

REQUESTS = Counter("evidentia_requests_total", "Total API requests", ["route", "method", "status"])
LATENCY  = Histogram("evidentia_latency_seconds", "Request latency", ["route", "method"])

import time
from starlette.middleware.base import BaseHTTPMiddleware

class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        LATENCY.labels(request.url.path, request.method).observe(time.perf_counter() - start)
        REQUESTS.labels(request.url.path, request.method, str(response.status_code)).inc()
        return response
