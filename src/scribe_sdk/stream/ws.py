"""WebSocket streaming over the `/v1/stream/*` endpoints.

Flow (reuses the same mechanism telephony providers use):

    1. POST /v1/stream/sessions {session_id?, ...}
         -> {stream_id, wss_url, session_id}
    2. connect wss_url, send audio frames:
         - raw 16-bit LE PCM, mono, 16 kHz  (default, sent as binary frames), or
         - JSON envelope: {"event":"media","media":{"payload": base64(pcm)}}
    3. send a "stop" event (or just disconnect) to finalize; the server flushes,
       commits the transaction, and queues transcription.

Results are retrieved by polling the protocol session (`session_id`) via the
authenticated `GET /v1/sessions/{session_id}`. The business id is taken from your
token on both the stream-create and protocol-get sides (the SDK never sends a
configured `b_id`), so the streamed session is written under, and read back by,
the same business — see the README's "Streaming result retrieval" section.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import websockets

from ..http import Transport
from ..models import CreateStreamSessionRequest, CreateStreamSessionResponse

DEFAULT_SAMPLE_RATE = 16000


class StreamUploader:
    def __init__(self, transport: Transport) -> None:
        self._t = transport

    async def create_session(
        self,
        *,
        session_id: str | None = None,
        b_id: str | None = None,
        uuid: str | None = None,
        provider: str | None = None,
        additional_data: dict[str, Any] | None = None,
    ) -> CreateStreamSessionResponse:
        """Create a stream session and obtain the WSS URL.

        `b_id` is not required: the backend resolves it (and `uuid`) from the
        jwt-payload derived from your Bearer token (or your dev jwt_payload). The
        optional `b_id` kwarg only exists for advanced/raw-backend callers that
        need to set it explicitly (telephony-style).
        """
        req = CreateStreamSessionRequest(
            session_id=session_id,
            b_id=b_id,
            uuid=uuid,
            provider=provider,
            additional_data=additional_data,
        )
        resp = await self._t.request(
            "POST",
            "/v1/stream/sessions",
            json=req.model_dump(exclude_none=True),
            headers={"Content-Type": "application/json"},
            expected=(200, 201),
        )
        return CreateStreamSessionResponse.model_validate(resp.json())

    async def open(
        self,
        *,
        session_id: str | None = None,
        b_id: str | None = None,
        uuid: str | None = None,
        provider: str | None = None,
        additional_data: dict[str, Any] | None = None,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        json_envelope: bool = False,
    ) -> StreamSession:
        """Create a stream session and return a connected `StreamSession`."""
        meta = await self.create_session(
            session_id=session_id,
            b_id=b_id,
            uuid=uuid,
            provider=provider,
            additional_data=additional_data,
        )
        session = StreamSession(
            meta, sample_rate=sample_rate, json_envelope=json_envelope
        )
        await session._connect()
        return session


class StreamSession:
    """A connected streaming session. Use as an async context manager.

        async with await client.stream.open() as s:
            await s.send_audio(pcm_bytes)
            await s.stop()
        result = await client.wait_for_results(s.session_id)
    """

    def __init__(
        self,
        meta: CreateStreamSessionResponse,
        *,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        json_envelope: bool = False,
    ) -> None:
        self.meta = meta
        self.stream_id = meta.stream_id
        self.session_id = meta.session_id
        self.wss_url = meta.wss_url
        self._sample_rate = sample_rate
        self._json = json_envelope
        self._ws: websockets.WebSocketClientProtocol | None = None
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

    async def stop(self, reason: str | None = None) -> None:
        """Send the stop event and close the socket (idempotent)."""
        if self._stopped:
            return
        self._stopped = True
        ws = self._ws
        if ws is None:
            return
        try:
            if self._json:
                await ws.send(
                    json.dumps({"event": "stop", **({"reason": reason} if reason else {})})
                )
            await ws.close()
        finally:
            self._ws = None

    def _require_ws(self) -> websockets.WebSocketClientProtocol:
        if self._ws is None:
            raise RuntimeError("Stream is not connected (or already stopped).")
        return self._ws

    async def __aenter__(self) -> StreamSession:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.stop()
