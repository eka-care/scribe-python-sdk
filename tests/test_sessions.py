import httpx
import respx

from scribe_sdk.models import SessionStatus


@respx.mock
async def test_create_session_uses_default_templates(client, base_url):
    route = respx.post(f"{base_url}/v1/sessions").mock(
        return_value=httpx.Response(
            201,
            json={
                "session_id": "ses_abc",
                "status": "created",
                "created_at": 1,
                "expires_at": 2,
            },
        )
    )
    s = await client.create_session(upload_type="chunked", communication_protocol="http")
    assert s.session_id == "ses_abc"
    body = respx.calls.last.request.content
    assert b'"soap"' in body  # default template applied
    # dev jwt-payload header is attached
    assert route.calls.last.request.headers.get("jwt-payload")


@respx.mock
async def test_get_session_records_http_status(client, base_url):
    respx.get(f"{base_url}/v1/sessions/ses_x").mock(
        return_value=httpx.Response(
            202,
            json={"session_id": "ses_x", "status": "processing", "created_at": 1},
        )
    )
    status = await client.sessions.get("ses_x")
    assert status.http_status == 202
    assert status.status == SessionStatus.PROCESSING.value
    assert not status.is_terminal


@respx.mock
async def test_get_session_completed_is_terminal(client, base_url):
    respx.get(f"{base_url}/v1/sessions/ses_done").mock(
        return_value=httpx.Response(
            200,
            json={
                "session_id": "ses_done",
                "status": "completed",
                "created_at": 1,
                "templates": [{"soap": {"status": "success", "data": {"s": "x"}}}],
            },
        )
    )
    status = await client.sessions.get("ses_done")
    assert status.is_terminal and status.is_complete
    assert status.templates[0]["soap"]["data"] == {"s": "x"}


@respx.mock
async def test_end_session(client, base_url):
    respx.post(f"{base_url}/v1/sessions/ses_x/end").mock(
        return_value=httpx.Response(
            202, json={"session_id": "ses_x", "status": "processing", "audio_files_received": 3}
        )
    )
    res = await client.sessions.end("ses_x", audio_files_sent=3)
    assert res.audio_files_received == 3
