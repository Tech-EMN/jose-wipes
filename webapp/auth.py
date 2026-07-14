"""Authentication middleware for the José Wipes Web Video Studio.

Provides defense-in-depth via API key header validation.
Designed to complement Traefik HTTP Basic Auth at the edge —
if the reverse proxy is bypassed (direct port, Vercel, Heroku),
the application layer still enforces authentication.

Environment variables:
    JW_API_KEY: static API key for header-based auth (X-API-Key).
        When unset, the middleware logs a warning and allows all requests
        in development mode. In production, it MUST be set.

    JW_AUTH_STRICT: when "true", reject requests that fail auth
        instead of just logging a warning. Defaults to "true".

Usage:
    from webapp.auth import AuthMiddleware, require_api_key

    app.add_middleware(AuthMiddleware)
    # or per-route:
    @app.get("/api/jobs/{job_id}", dependencies=[Depends(require_api_key)])
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

_log = logging.getLogger(__name__)

AUTH_HEADER = "X-API-Key"
API_KEY = os.getenv("JW_API_KEY", "").strip()
STRICT_MODE = os.getenv("JW_AUTH_STRICT", "true").strip().lower() in {"true", "1", "yes", "sim"}

# Paths that do NOT require authentication
_PUBLIC_PATHS = frozenset({
    "/api/health/external",
    "/health",
    "/",
})

_PUBLIC_PREFIXES = (
    "/static/",
    "/assets/",
)


def _is_public_path(path: str) -> bool:
    """Check if a path is publicly accessible without auth."""
    return path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIXES)


def _validate_api_key(api_key: str | None) -> bool:
    """Validate the provided API key against the configured key."""
    if not API_KEY:
        return True  # Not configured — allow all (dev mode)
    if not api_key:
        return False
    # Constant-time comparison to prevent timing attacks
    return _constant_time_compare(api_key, API_KEY)


def _constant_time_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks."""
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    return result == 0


@dataclass
class AuthError:
    """Structured authentication error response."""

    status_code: int
    detail: str


class AuthMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that enforces API key authentication.

    All routes except / and /api/health/external require a valid
    X-API-Key header when JW_API_KEY is configured.

    When JW_AUTH_STRICT=false and no key is configured, a warning
    is logged but the request proceeds (development mode).
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # Allow public paths without authentication
        if _is_public_path(path):
            return await call_next(request)

        # Check if auth is configured
        if not API_KEY:
            if STRICT_MODE:
                _log.error(
                    "JW_API_KEY not configured but strict mode is on. "
                    "Set JW_API_KEY in .env or set JW_AUTH_STRICT=false for development."
                )
                return JSONResponse(
                    status_code=HTTP_403_FORBIDDEN,
                    content={
                        "detail": "Servidor não configurado para autenticação. "
                        "Contate o administrador do sistema."
                    },
                )
            _log.warning(
                "JW_API_KEY not configured — allowing all requests. "
                "This is insecure for production. Set JW_API_KEY in .env."
            )
            return await call_next(request)

        # Validate API key header
        api_key = request.headers.get(AUTH_HEADER)
        api_key_alt = request.headers.get(AUTH_HEADER.lower())

        effective_key = api_key or api_key_alt

        if not _validate_api_key(effective_key):
            _log.warning(
                "Authentication failed for %s %s from %s",
                request.method,
                path,
                request.client.host if request.client else "unknown",
            )
            return JSONResponse(
                status_code=HTTP_401_UNAUTHORIZED,
                content={"detail": "Chave de API inválida ou ausente. Inclua o header X-API-Key."},
                headers={"WWW-Authenticate": "ApiKey"},
            )

        return await call_next(request)
