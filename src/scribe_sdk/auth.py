"""Authentication for the Scribe SDK.

Production path: exchange ``client_id`` + ``client_secret`` at
``{auth_base_url}/connect-auth/v1/account/login`` for an access/refresh token,
then send ``Authorization: Bearer <access_token>`` to the public gateway, which
validates it and injects the ``jwt-payload`` header for downstream services.

Dev path: if ``config.jwt_payload`` is set, skip login entirely and send that
JSON object as the ``jwt-payload`` header directly to a raw backend.

The provider is async and concurrency-safe: a single in-flight login/refresh is
shared by all callers via an asyncio lock.
"""

from __future__ import annotations

import json
import time

import anyio
import httpx

from .config import ScribeConfig
from .errors import AuthError

_REFRESH_SKEW_SECONDS = 300  # refresh 5 min before expiry


class AuthProvider:
    """Resolves auth headers for outgoing requests, refreshing as needed."""

    def __init__(self, config: ScribeConfig, http: httpx.AsyncClient) -> None:
        self._config = config
        self._http = http
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at: float = 0.0
        self._lock = anyio.Lock()

    @property
    def _direct_mode(self) -> bool:
        return self._config.jwt_payload is not None

    async def auth_headers(self, *, force_refresh: bool = False) -> dict[str, str]:
        """Return headers to attach to a protocol request."""
        if self._direct_mode:
            return {"jwt-payload": json.dumps(self._config.jwt_payload)}

        token = await self._valid_token(force_refresh=force_refresh)
        return {"Authorization": f"Bearer {token}"}

    async def _valid_token(self, *, force_refresh: bool) -> str:
        async with self._lock:
            now = time.time()
            needs = (
                force_refresh
                or self._access_token is None
                or now >= self._expires_at - _REFRESH_SKEW_SECONDS
            )
            if not needs:
                return self._access_token  # type: ignore[return-value]

            if self._refresh_token and not force_refresh:
                try:
                    await self._refresh()
                    return self._access_token  # type: ignore[return-value]
                except AuthError:
                    pass  # fall through to a fresh login
            await self._login()
            return self._access_token  # type: ignore[return-value]

    def _auth_url(self, path: str) -> str:
        return f"{self._config.auth_base_url.rstrip('/')}{path}"

    async def _login(self) -> None:
        self._config.require_credentials()
        payload = {
            "client_id": self._config.client_id,
            "client_secret": self._config.client_secret,
        }
        if self._config.api_key:
            payload["api_key"] = self._config.api_key
        await self._token_request(
            self._auth_url("/connect-auth/v1/account/login"), payload, action="login"
        )

    async def _refresh(self) -> None:
        await self._token_request(
            self._auth_url("/connect-auth/v1/account/refresh-token"),{
                "refresh_token" : self._refresh_token,
                "access_token": self._access_token,
            }
        )

    async def _token_request(self, url: str, body: dict, *, action: str) -> None:
        try:
            resp = await self._http.post(url, json=body, timeout=30.0)
        except httpx.HTTPError as exc:  # network/timeout
            raise AuthError(f"{action} request failed: {exc}") from exc
        if resp.status_code >= 400:
            raise AuthError(
                f"{action} failed: {resp.status_code} {resp.text[:200]}",
                status_code=resp.status_code,
            )
        data = resp.json()
        self._access_token = data.get("access_token")
        if not self._access_token:
            raise AuthError(f"{action} response missing access_token")
        self._refresh_token = data.get("refresh_token", self._refresh_token)
        expires_in = data.get("expires_in")
        self._expires_at = time.time() + float(expires_in) if expires_in else time.time() + 3600
