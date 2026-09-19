"""ASGI middleware for request correlation and performance metrics with streaming response support."""

import time
import uuid

import structlog

from packages.observability.metrics import (
    API_REQUEST_DURATION_SECONDS,
    API_REQUESTS_TOTAL,
)


class CorrelationAndMetricsMiddleware:
    """Pure ASGI middleware ensuring every request has correlation IDs and logs duration without buffering streams."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        request_id = headers.get(b"x-request-id", b"").decode("utf-8") or str(uuid.uuid4())
        correlation_id = headers.get(b"x-correlation-id", b"").decode("utf-8") or request_id

        # Bind structlog contextvars
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            correlation_id=correlation_id,
            method=scope.get("method"),
            path=scope.get("path"),
        )

        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["request_id"] = request_id
        scope["state"]["correlation_id"] = correlation_id

        start_time = time.perf_counter()
        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 200)
                msg_headers = list(message.get("headers", []))
                msg_headers.append((b"x-request-id", request_id.encode("utf-8")))
                msg_headers.append((b"x-correlation-id", correlation_id.encode("utf-8")))
                message["headers"] = msg_headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - start_time
            endpoint = scope.get("path", "")
            method = scope.get("method", "")
            API_REQUESTS_TOTAL.labels(
                method=method,
                endpoint=endpoint,
                status_code=str(status_code),
            ).inc()
            API_REQUEST_DURATION_SECONDS.labels(
                method=method,
                endpoint=endpoint,
            ).observe(duration)
