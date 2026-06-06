"""WebSocket streaming over the protocol session API.

Streaming uses ONLY the protocol endpoints — the same `POST /v1/sessions` used
for chunked upload, with `upload_type="stream"`:

    1. POST /v1/sessions {upload_type:"stream", communication_protocol:"websocket", ...}
         -> {session_id, upload_url}      # upload_url is the wss:// URL
    2. connect upload_url, send audio frames:
         - raw 16-bit LE PCM, mono, 16 kHz  (default, sent as binary frames), or
         - JSON envelope: {"event":"media","media":{"payload": base64(pcm)}}
    3. stop(): send a {"event":"stop"} frame, wait for the server to flush the
       final chunk and close the socket, then POST /v1/sessions/{id}/end to commit
       and start processing.

Results are retrieved by polling the protocol session (`session_id`) via the
authenticated `GET /v1/sessions/{session_id}`. The business id is taken from your
token on both the create and get sides (the SDK never sends a configured `b_id`),
so the streamed session is written under, and read back by, the same business.
"""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import anyio
import websockets

from ..errors import ScribeError
from ..http import Transport
from ..models import CommunicationProtocol, Model, SessionMode, UploadType

if TYPE_CHECKING:
    from ..sessions import SessionsAPI

DEFAULT_SAMPLE_RATE = 16000
DEFAULT_FINALIZE_TIMEOUT = 10.0


def _stream_id_from_wss(wss_url: str, fallback: str) -> str:
    """Extract the stream_id from a wss URL of the form
    `wss://host/voice/v1/stream/sessions/{stream_id}/audio`.

    Falls back to `fallback` (the session_id) when it can't be parsed. The
    stream_id is only used cosmetically in the JSON-envelope `start` frame; the
    server identifies the stream from the URL path.
    """
    try:
        parts = [p for p in urlparse(wss_url).path.split("/") if p]
        if "sessions" in parts:
            i = parts.index("sessions")
            if i + 1 < len(parts):
                return parts[i + 1]
    except Exception:
        pass
    return fallback


class StreamUploader:
    def __init__(self, transport: Transport, sessions: SessionsAPI) -> None:
        self._t = transport
        self._sessions = sessions

    async def open(
        self,
        *,
        templates: list[str] | None = None,
        session_id: str | None = None,
        session_mode: SessionMode | str = SessionMode.DICTATION,
        model: Model | str | None = None,
        language_hint: list[str] | None = None,
        transcript_language: str | None = None,
        additional_data: dict[str, Any] | None = None,
        patient_details: dict[str, Any] | None = None,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        json_envelope: bool = False,
        finalize_timeout: float = DEFAULT_FINALIZE_TIMEOUT,
    ) -> StreamSession:
        """Create a streaming session via the protocol API and connect the WebSocket.

        Calls `POST /v1/sessions` with `upload_type="stream"` (the same protocol
        create-session used by chunked upload) and returns a connected
        `StreamSession`. The wss URL is taken from the create response's
        `upload_url`. `b_id`/`uuid` are resolved from your token by the backend —
        the SDK never sends them.
        """
        resp = await self._sessions.create(
            upload_type=UploadType.STREAM,
            communication_protocol=CommunicationProtocol.WEBSOCKET,
            templates=templates,
            session_id=session_id,
            session_mode=session_mode,
            model=model,
            language_hint=language_hint,
            transcript_language=transcript_language,
            additional_data=additional_data,
            patient_details=patient_details,
        )
        wss_url = resp.upload_url
        if not wss_url:
            raise ScribeError(
                "Create-session returned no upload_url for upload_type=stream; "
                "the backend did not provision a WebSocket stream."
            )
        session = StreamSession(
            session_id=resp.session_id,
            wss_url=wss_url,
            sessions=self._sessions,
            sample_rate=sample_rate,
            json_envelope=json_envelope,
            finalize_timeout=finalize_timeout,
        )
        await session._connect()
        return session


class StreamSession:
    """A connected streaming session. Use as an async context manager.

        async with await client.open_stream() as s:
            await s.send_audio(pcm_bytes)
            await s.stop()              # flush + end the session
        result = await client.wait_for_results(s.session_id)
    """

    def __init__(
        self,
        *,
        session_id: str,
        wss_url: str,
        sessions: SessionsAPI,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        json_envelope: bool = False,
        finalize_timeout: float = DEFAULT_FINALIZE_TIMEOUT,
    ) -> None:
        self.session_id = session_id
        self.wss_url = wss_url
        self.stream_id = _stream_id_from_wss(wss_url, session_id)
        self._sessions = sessions
        self._sample_rate = sample_rate
        self._json = json_envelope
        self._finalize_timeout = finalize_timeout
        # websockets' connection type has moved across versions; the connection
        # returned by websockets.connect() is duck-typed here (send/close/wait_closed).
        self._ws: Any | None = None
        self._started = False
        self._stopped = False

    async def _connect(self) -> None:
        self._ws = await websockets.connect(self.wss_url, max_size=None)
        if self._json:
            await self._send_start()

    async def _send_start(self) -> None:
        await self._require_ws().send(
            json.dumps(
                {
                    "event": "start",
                    "start": {
                        "streamId": self.stream_id,
                        "mediaFormat": {
                            "encoding": "audio/x-l16",
                            "sampleRate": self._sample_rate,
                        },
                    },
                }
            )
        )
        self._started = True

    async def send_audio(self, pcm: bytes) -> None:
        """Send a frame of raw 16-bit LE PCM (mono, `sample_rate` Hz)."""
        if not pcm:
            return
        ws = self._require_ws()
        if self._json:
            await ws.send(
                json.dumps(
                    {
                        "event": "media",
                        "media": {"payload": base64.b64encode(pcm).decode("ascii")},
                    }
                )
            )
        else:
            await ws.send(pcm)

    async def stop(self, reason: str | None = None, *, finalize: bool = True) -> None:
        """Stop streaming and finalize the session (idempotent).

        Sends a `stop` event, waits for the server to flush the final chunk and
        close the socket, then calls `POST /v1/sessions/{id}/end` to commit and
        start processing — the single, canonical finalize trigger for protocol
        streaming sessions. Pass `finalize=False` to skip the end call (e.g. to
        end the session yourself later).
        """
        if self._stopped:
            return
        self._stopped = True
        ws = self._ws
        if ws is not None:
            try:
                # Best-effort stop signal; the server flushes on the receive-loop
                # break (works in both binary and JSON-envelope modes).
                try:
                    await ws.send(
                        json.dumps(
                            {"event": "stop", **({"reason": reason} if reason else {})}
                        )
                    )
                except Exception:
                    pass
                # Wait for the server to flush remaining audio to storage and
                # close, so the subsequent end-session sees every chunk.
                with anyio.move_on_after(self._finalize_timeout):
                    await ws.wait_closed()
            finally:
                try:
                    await ws.close()
                except Exception:
                    pass
                self._ws = None
        if finalize:
            await self._sessions.end(self.session_id, audio_files_sent=0)

    def _require_ws(self) -> Any:
        if self._ws is None:
            raise RuntimeError("Stream is not connected (or already stopped).")
        return self._ws

    async def __aenter__(self) -> StreamSession:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.stop()
