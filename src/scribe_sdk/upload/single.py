"""Single-file upload: POST one complete recording; the backend VADs it.

`POST /v1/sessions/{id}/audio/{file_name}` with the whole file. Use this for
short, pre-recorded audio when you don't want client-side chunking. The server
performs VAD chunking internally.
"""

from __future__ import annotations

from pathlib import Path

from ..http import Transport
from ..models import UploadAudioResponse
from . import content_type_for


class SingleUploader:
    def __init__(self, transport: Transport) -> None:
        self._t = transport

    async def upload(
        self,
        session_id: str,
        audio: bytes | str | Path,
        *,
        filename: str | None = None,
        content_type: str | None = None,
        end_session: bool = True,
    ) -> UploadAudioResponse:
        """Upload a complete audio file (bytes or path)."""
        if isinstance(audio, (str, Path)):
            path = Path(audio)
            data = path.read_bytes()
            filename = filename or path.name
        else:
            data = audio
            filename = filename or "audio_0.wav"

        ct = content_type or content_type_for(filename)
        resp = await self._t.request(
            "POST",
            f"/v1/sessions/{session_id}/audio/{filename}",
            content=data,
            headers={"Content-Type": ct},
            expected=(200,),
        )
        result = UploadAudioResponse.model_validate(resp.json())

        if end_session:
            from ..sessions import SessionsAPI

            await SessionsAPI(self._t).end(session_id, audio_files_sent=1)
        return result
