"""Shared test fixtures.

Tests run fully offline: HTTP is mocked with respx and auth uses the dev
`jwt_payload` path so no login round-trip is needed.
"""

from __future__ import annotations

import pytest

from scribe_sdk import AsyncScribeClient

BASE_URL = "http://testserver/voice"


@pytest.fixture
def base_url() -> str:
    return BASE_URL


@pytest.fixture
async def client():
    """An AsyncScribeClient in dev (jwt-payload) mode with sane test defaults."""
    c = AsyncScribeClient(
        base_url=BASE_URL,
        jwt_payload={"b-id": "biz_test", "iss": "test"},
        default_templates=["soap"],
        poll_interval=0.0,
        poll_timeout=5.0,
    )
    try:
        yield c
    finally:
        await c.aclose()
