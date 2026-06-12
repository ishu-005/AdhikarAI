"""Structured logging + a per-request request-id middleware."""
from __future__ import annotations

import logging
import os
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_request_id: ContextVar[str] = ContextVar("request_id", default="-")
_configured = False


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.request_id = _request_id.get()
        return True


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | req=%(request_id)s | %(message)s"
        )
    )
    handler.addFilter(_RequestIdFilter())
    root = logging.getLogger("adhikarai")
    root.handlers = [handler]
    root.setLevel(level)
    root.propagate = False
    _configured = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(f"adhikarai.{name}")


def current_request_id() -> str:
    return _request_id.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a short request id to every request for traceable logs."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        token = _request_id.set(rid)
        try:
            response = await call_next(request)
        finally:
            _request_id.reset(token)
        response.headers["X-Request-ID"] = rid
        return response
