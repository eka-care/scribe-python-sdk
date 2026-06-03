import httpx
import pytest
import respx

from scribe_sdk.errors import SessionExpiredError


@respx.mock
async def test_poll_until_complete(client, base_url):
    responses = [
        httpx.Response(202, json={"session_id": "s", "status": "processing", "created_at": 1}),
        httpx.Response(202, json={"session_id": "s", "status": "processing", "created_at": 1}),
        httpx.Response(200, json={"session_id": "s", "status": "completed", "created_at": 1}),
    ]
    respx.get(f"{base_url}/v1/sessions/s").mock(side_effect=responses)

    seen = []
    result = await client.wait_for_results(
        "s", interval=0.0, on_update=lambda st: seen.append(st.status)
    )
    assert result.status == "completed"
    assert seen == ["processing", "processing", "completed"]


@respx.mock
async def test_poll_expired_raises(client, base_url):
    respx.get(f"{base_url}/v1/sessions/s").mock(
        return_value=httpx.Response(410, json={"session_id": "s", "status": "expired"})
    )
    with pytest.raises(SessionExpiredError):
        await client.wait_for_results("s", interval=0.0)
