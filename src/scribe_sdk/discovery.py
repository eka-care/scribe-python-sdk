"""Discovery API client.

`GET /v1/.well-known/medscribealliance` is public (no auth) and advertises
supported audio formats, models, languages, and upload methods. The SDK can use
it to validate requests client-side before sending them.
"""

from __future__ import annotations

from typing import Any

from .http import Transport

DISCOVERY_PATH = "/v1/.well-known/medscribealliance"


class DiscoveryAPI:
    def __init__(self, transport: Transport) -> None:
        self._t = transport

    async def get(self) -> dict[str, Any]:
        """Fetch the raw discovery document."""
        # Public endpoint — no auth header needed, but sending one is harmless.
        resp = await self._t.request("GET", DISCOVERY_PATH, expected=(200,))
        return resp.json()
