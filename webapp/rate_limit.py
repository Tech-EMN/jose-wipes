"""Rate limiting middleware for the José Wipes Web Video Studio.

Protects the API from accidental abuse and credit overconsumption.
Uses a sliding-window in-memory store — sufficient for single-user/small-team use.

Environment variables:
    JW_RATE_LIMIT_JOBS: max POST /api/jobs per window (default: 5)
    JW_RATE_LIMIT_WINDOW_SECONDS: window size in seconds (default: 60)
    JW_RATE_LIMIT_ENABLED: set to "false" to disable (default: "true")
"""

from __future__ import annotations

import logging
import os
import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

_log = logging.getLogger(__name__)

# Configuration
_RATE_LIMIT_ENABLED = os.getenv("JW_RATE_LIMIT_ENABLED", "true").strip().lower() not in {
    "false", "0", "no", "off",
}
_JOBS_LIMIT = int(os.getenv("JW_RATE_LIMIT_JOBS", "5"))
_WINDOW_SECONDS = int(os.getenv("JW_RATE_LIMIT_WINDOW_SECONDS", "60"))

# Routes subject to rate limiting with their specific limits
_RATE_LIMITED_ROUTES: dict[str, tuple[int, int]] = {
    "POST /api/jobs": (_JOBS_LIMIT, _WINDOW_SECONDS),
}

# Routes exempt from rate limiting
_RATE_LIMIT_EXEMPT_PREFIXES = (
    "/static/",
    "/assets/",
    "/api/health",
    "/api/jobs/",  # GET status/download — only POST is limited
)


@dataclass
class _ClientWindow:
    """Sliding-window counter for a single client."""

    timestamps: list[float] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def allow(self, limit: int, window_seconds: int) -> bool:
        """Check if request is allowed under sliding-window limit."""
        now = time.monotonic()
        with self.lock:
            # Remove expired timestamps
            cutoff = now - window_seconds
            self.timestamps = [t for t in self.timestamps if t > cutoff]

            if len(self.timestamps) >= limit:
                return False

            self.timestamps.append(now)
            return True

    def remaining(self, limit: int, window_seconds: int) -> int:
        """Return remaining requests available in this window."""
        now = time.monotonic()
        with self.lock:
            cutoff = now - window_seconds
            self.timestamps = [t for t in self.timestamps if t > cutoff]
            return max(0, limit - len(self.timestamps))

    def reset_after(self, window_seconds: int) -> int:
        """Return seconds until the earliest timestamp expires."""
        now = time.monotonic()
        with self.lock:
            if not self.timestamps:
                return 0
            remaining = window_seconds - (now - self.timestamps[0])
            return max(0, int(remaining))


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limit middleware for FastAPI."""

    def __init__(self, app):
        super().__init__(app)
        self._windows: dict[str, _ClientWindow] = defaultdict(_ClientWindow)
        self._cleanup_lock = threading.Lock()
        self._last_cleanup = time.monotonic()

    def _client_key(self, request: Request) -> str:
        """Derive a rate-limit key from the client.

        Priority: X-Forwarded-For > client host > "unknown".
        """
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        if request.client and request.client.host:
            return request.client.host

        return "unknown"

    def _maybe_cleanup(self) -> None:
        """Periodically evict stale client windows (every 300s)."""
        now = time.monotonic()
        if now - self._last_cleanup < 300:
            return
        with self._cleanup_lock:
            if now - self._last_cleanup < 300:
                return
            max_age = now - max(w for _, w in _RATE_LIMITED_ROUTES.values())
            stale = [
                k for k, w in self._windows.items()
                if not w.timestamps or all(t <= max_age for t in w.timestamps)
            ]
            for k in stale:
                del self._windows[k]
            self._last_cleanup = now
            if stale:
                _log.debug("Rate limit cleanup: evicted %d stale windows", len(stale))

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> JSONResponse | None:
        if not _RATE_LIMIT_ENABLED:
            return await call_next(request)

        method = request.method
        path = request.url.path

        # Skip rate limiting for exempt paths
        if path.startswith(_RATE_LIMIT_EXEMPT_PREFIXES) and not path == "/api/jobs":
            return await call_next(request)

        # Find matching rate limit rule
        route_key = f"{method} {path}"
        rule = _RATE_LIMITED_ROUTES.get(route_key)

        if rule is None:
            # Check prefix match for POST on anything under /api/jobs
            return await call_next(request)

        limit, window_seconds = rule
        client_key = self._client_key(request)
        full_key = f"{client_key}:{route_key}"
        window = self._windows[full_key]

        if not window.allow(limit, window_seconds):
            retry_after = window.reset_after(window_seconds)
            _log.warning(
                "Rate limit exceeded: %s %s from %s (limit=%d/%ds)",
                method, path, client_key, limit, window_seconds,
            )
            return JSONResponse(
                status_code=HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": (
                        f"Limite de requisições excedido. "
                        f"Tente novamente em {retry_after} segundos."
                    ),
                    "retry_after_seconds": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(retry_after),
                },
            )

        self._maybe_cleanup()

        response = await call_next(request)

        # Add rate limit headers to successful responses
        remaining = window.remaining(limit, window_seconds)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(window.reset_after(window_seconds))

        return response
