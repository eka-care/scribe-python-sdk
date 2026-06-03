"""Typed exceptions for the Scribe SDK.

Backend protocol errors use a standard envelope::

    {"error": {"code": "...", "message": "...", "details": {...}}}

`error_from_response` maps that envelope (and transport failures) to the
exception hierarchy below so callers can `except ScribeError` broadly or catch
specific subclasses.
"""

from __future__ import annotations

from typing import Any


class ScribeError(Exception):
    """Base class for every error raised by the SDK."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        parts = [self.message]
        if self.code:
            parts.append(f"code={self.code}")
        if self.status_code:
            parts.append(f"status={self.status_code}")
        return " | ".join(parts)


class ConfigError(ScribeError):
    """Raised when configuration is missing or invalid (e.g. no client_id)."""


class AuthError(ScribeError):
    """Login/refresh failed, or the gateway rejected credentials (401/403)."""


class SessionNotFoundError(ScribeError):
    """The session id does not exist (404)."""


class SessionExpiredError(ScribeError):
    """The session has expired (410)."""


class SessionStateError(ScribeError):
    """Session already ended/committed or otherwise in a conflicting state."""


class InvalidAudioError(ScribeError):
    """Unsupported audio format or oversized chunk (400/413)."""


class ValidationError(ScribeError):
    """Request validation failed server-side (422)."""


class APIError(ScribeError):
    """Catch-all for unexpected backend responses (5xx and unmapped 4xx)."""


# Map backend `error.code` strings to specific exception classes.
_CODE_MAP: dict[str, type[ScribeError]] = {
    "authentication_failed": AuthError,
    "invalid_request": ValidationError,
    "invalid_audio_format": InvalidAudioError,
    "session_not_found": SessionNotFoundError,
    "session_ended": SessionStateError,
    "session_completed": SessionStateError,
    "processing_failed": APIError,
    "internal_error": APIError,
}

# Fallback mapping by HTTP status when no recognizable code is present.
_STATUS_MAP: dict[int, type[ScribeError]] = {
    400: ValidationError,
    401: AuthError,
    403: AuthError,
    404: SessionNotFoundError,
    409: SessionStateError,
    410: SessionExpiredError,
    413: InvalidAudioError,
    422: ValidationError,
}


def error_from_response(status_code: int, body: Any) -> ScribeError:
    """Build the most specific exception for an HTTP error response."""
    code: str | None = None
    message = f"Request failed with status {status_code}"
    details: dict[str, Any] = {}

    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            code = err.get("code")
            message = err.get("message", message)
            details = err.get("details", {}) or {}
        elif isinstance(body.get("detail"), str):
            message = body["detail"]

    exc_cls = _CODE_MAP.get(code or "") or _STATUS_MAP.get(status_code, APIError)
    return exc_cls(message, code=code, status_code=status_code, details=details)
