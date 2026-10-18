"""FastAPI Request Middleware and Global Exception Handlers."""

import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.logging import get_logger
from src.core.monitoring import telemetry
from src.db.repository import DuplicateRunError

logger = get_logger("api_middleware")


class RequestTrackingMiddleware(BaseHTTPMiddleware):
    """Middleware attaching unique X-Request-ID and logging structured request telemetry."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        # Extract or generate unique request correlation ID
        req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
        request.state.request_id = req_id

        start_time = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Attach correlation ID to response headers
        response.headers["X-Request-ID"] = req_id
        response.headers["X-Response-Time-MS"] = str(duration_ms)

        # Record telemetry metrics
        telemetry.record_request(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        logger.info(
            f"[{req_id}] {request.method} {request.url.path} -> "
            f"status={response.status_code} duration={duration_ms}ms"
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter protecting heavy compute routes from exhaustion (FL-13)."""

    def __init__(self, app: Any, requests_per_minute: int = 120, heavy_route_rpm: int = 15) -> None:
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.heavy_route_rpm = heavy_route_rpm
        self._history: dict[str, list[float]] = {}
        self.heavy_prefixes = ("/api/v1/models/train", "/api/v1/forecasts", "/api/v1/data/import")

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        # Exempt health checks and options requests
        if request.method == "OPTIONS" or request.url.path in ("/health", "/ready", "/metrics"):
            return await call_next(request)  # type: ignore[no-any-return]

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - 60.0

        # Check if route is a heavy resource consumer
        is_heavy = any(request.url.path.startswith(prefix) for prefix in self.heavy_prefixes)
        limit = self.heavy_route_rpm if is_heavy else self.requests_per_minute
        key = f"{client_ip}:{'heavy' if is_heavy else 'std'}"

        timestamps = self._history.setdefault(key, [])
        # Prune entries older than 60 seconds
        self._history[key] = [t for t in timestamps if t > window_start]

        if len(self._history[key]) >= limit:
            req_id = getattr(request.state, "request_id", None) or f"req_{uuid.uuid4().hex[:12]}"
            logger.warning(f"Rate limit exceeded for client {client_ip} on {request.url.path} (Limit: {limit}/min)")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={"X-Request-ID": req_id, "Retry-After": "60"},
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"Rate limit exceeded. Maximum {limit} requests per minute allowed on this endpoint.",
                        "request_id": req_id,
                    }
                },
            )

        self._history[key].append(now)
        return await call_next(request)  # type: ignore[no-any-return]


def register_exception_handlers(app: FastAPI) -> None:
    """Register custom exception handlers returning standardized ErrorEnvelope format."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        req_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=exc.status_code,
            headers={"X-Request-ID": req_id} if req_id else None,
            content={
                "error": {
                    "code": f"HTTP_{exc.status_code}",
                    "message": exc.detail,
                    "request_id": req_id,
                    "details": getattr(exc, "extra", None),
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        req_id = getattr(request.state, "request_id", None)
        errors = []
        for err in exc.errors():
            loc = " -> ".join(str(part) for part in err.get("loc", []))
            errors.append({"field": loc, "issue": err.get("msg")})

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            headers={"X-Request-ID": req_id} if req_id else None,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request payload failed schema validation.",
                    "request_id": req_id,
                    "details": {"validation_errors": errors},
                }
            },
        )

    @app.exception_handler(DuplicateRunError)
    async def duplicate_run_exception_handler(request: Request, exc: DuplicateRunError) -> JSONResponse:
        req_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            headers={"X-Request-ID": req_id} if req_id else None,
            content={
                "error": {
                    "code": "DUPLICATE_RUN_CONFLICT",
                    "message": str(exc),
                    "request_id": req_id,
                    "details": None,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        req_id = getattr(request.state, "request_id", None)
        logger.exception(f"Unhandled exception on [{req_id}] {request.method} {request.url.path}: {exc}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            headers={"X-Request-ID": req_id} if req_id else None,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected server error occurred. Please contact system support.",
                    "request_id": req_id,
                    "details": {"error_type": type(exc).__name__},
                }
            },
        )
