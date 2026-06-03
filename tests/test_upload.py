import httpx
import respx

from scribe_sdk.upload import content_type_for


def test_content_type_for():
    assert content_type_for("chunk_0.wav") == "audio/wav"
    assert content_type_for("chunk_0.m4a") == "audio/mp4"
    assert content_type_for("a.webm") == "audio/webm;codecs=opus"
    assert content_type_for("a.unknown") == "application/octet-stream"


@respx.mock
async def test_upload_chunk_names_and_content_type(client, base_url):
    route = respx.post(f"{base_url}/v1/sessions/ses_x/audio/chunk_0.wav").mock(
        return_value=httpx.Response(
            200, json={"session_id": "ses_x", "success": True, "original_filename": "chunk_0.wav"}
        )
    )
    res = await client.upload_chunk("ses_x", 0, b"RIFFdata", ext="wav")
    assert res.success
    assert route.calls.last.request.headers["content-type"] == "audio/wav"
    assert route.calls.last.request.content == b"RIFFdata"


@respx.mock
async def test_upload_chunks_iterable_then_end(client, base_url):
    for i in range(3):
        respx.post(f"{base_url}/v1/sessions/ses_x/audio/chunk_{i}.wav").mock(
            return_value=httpx.Response(
                200, json={"session_id": "ses_x", "success": True}
            )
        )
    end = respx.post(f"{base_url}/v1/sessions/ses_x/end").mock(
        return_value=httpx.Response(202, json={"session_id": "ses_x", "status": "processing"})
    )

    async def chunks():
        for b in (b"a", b"b", b"c"):
            yield b

    n = await client.upload_chunks("ses_x", chunks())
    assert n == 3
    assert end.called
    assert b'"audio_files_sent":3' in end.calls.last.request.content.replace(b" ", b"")


@respx.mock
async def test_single_upload_then_end(client, base_url):
    respx.post(f"{base_url}/v1/sessions/ses_x/audio/visit.wav").mock(
        return_value=httpx.Response(200, json={"session_id": "ses_x", "success": True})
    )
    end = respx.post(f"{base_url}/v1/sessions/ses_x/end").mock(
        return_value=httpx.Response(202, json={"session_id": "ses_x", "status": "processing"})
    )
    await client.upload_file("ses_x", b"RIFF....", filename="visit.wav")
    assert end.called
