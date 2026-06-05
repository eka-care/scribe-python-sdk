import httpx
import respx

from scribe_sdk import ScribeClient

BASE_URL = "http://testserver/voice"


@respx.mock
def test_sync_client_create_and_get():
    """The sync facade runs the async client on a background loop."""
    respx.post(f"{BASE_URL}/v1/sessions").mock(
        return_value=httpx.Response(
            201,
            json={"session_id": "ses_s", "status": "created", "created_at": 1, "expires_at": 2},
        )
    )
    respx.get(f"{BASE_URL}/v1/sessions/ses_s").mock(
        return_value=httpx.Response(
            200, json={"session_id": "ses_s", "status": "completed", "created_at": 1}
        )
    )

    with ScribeClient(
        base_url=BASE_URL,
        jwt_payload={"b-id": "biz", "iss": "t"},
        default_templates=["soap"],
    ) as client:
        session = client.create_session(upload_type="chunked", communication_protocol="http")
        assert session.session_id == "ses_s"
        result = client.wait_for_results("ses_s", interval=0.0)
        assert result.is_complete
