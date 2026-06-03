"""Thin transport wrapper around httpx.

`Transport` owns the shared `httpx.AsyncClient`, injects auth headers on every
request, retries once on 401 (token may have just expired), and converts error
responses into typed `ScribeError`s. Successful responses are returned raw so
callers can decode JSON or read bytes as appropriate.
"""

from __future__ import annotations

from typing import Any

import httpx

from .auth import AuthProvider
from .config import ScribeConfig
from .errors import APIError, error_from_response


class Transport:
    def __init__(self, config: ScribeConfig, client: httpx.AsyncClient | None = None) -> None:
        self._config = config
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=config.request_timeout)
        self._auth = AuthProvider(config, self._client)

    @property
    def config(self) -> ScribeConfig:
        return self._config

    def url(self, path: str) -> str:
        """Resolve a protocol path (e.g. '/v1/sessions') against base_url."""
        base = self._config.base_url.rstrip("/")
        return f"{base}{path}"

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
        expected: tuple[int, ...] = (200, 201, 202, 206),
    ) -> httpx.Response:
        url = self.url(path)
        base_headers = dict(headers or {})

        for attempt in range(2):  # initial try + one retry after forced refresh
            auth = await self._auth.auth_headers(force_refresh=attempt == 1)
            merged = {**auth, **base_headers}
            try:
                resp = await self._client.request(
                    method,
                    url,
                    json=json,
                    content=content,
                    headers=merged,
                    params=params,
                    timeout=timeout or self._config.request_timeout,
                )
            except httpx.HTTPError as exc:
                raise APIError(f"{method} {url} failed: {exc}") from exc

            if resp.status_code == 401 and attempt == 0 and self._config.jwt_payload is None:
                continue  # token likely expired — refresh and retry once

            if resp.status_code in expected:
                return resp
            raise error_from_response(resp.status_code, _safe_json(resp))

        # Unreachable, but keeps type-checkers happy.
        raise APIError("request retry loop exhausted")  # pragma: no cover

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return {"detail": resp.text[:500]}
