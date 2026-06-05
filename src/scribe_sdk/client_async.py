"""AsyncScribeClient — the primary, fully-async SDK entry point.

Exposes both low-level sub-APIs (`.sessions`, `.discovery`, `.stream`) and
high-level convenience methods that cover the common flows end to end. Every
flow keeps the steps separated — start a session, send audio, end the session,
then poll for results:

    file/bytes: create_session -> upload_audio_file -> end -> wait_for_results
    raw PCM:    create_session -> upload_pcm        -> end -> wait_for_results
    streaming:  open_stream -> send_audio -> stop    -> wait_for_results

Voice activity detection always runs client-side: `upload_audio_file` /
`upload_pcm` VAD the audio locally (via `scribe_sdk.audio`, the `[audio]` extra)
and POST only speech-bounded `chunk_0`, `chunk_1`, … — the backend never does
VAD. There is deliberately no whole-file ("single") upload.
"""

from __future__ import annotations

from collections.abc import AsyncIterable, Awaitable
from pathlib import Path
from typing import Any, Callable

import anyio
import httpx

from .config import ScribeConfig
from .discovery import DiscoveryAPI
from .http import Transport
from .models import (
    CreateSessionResponse,
    SessionStatusResponse,
    UploadAudioResponse,
)
from .results import ResultPoller
from .sessions import SessionsAPI
from .stream import StreamSession, StreamUploader
from .upload import ChunkedUploader


class AsyncScribeClient:
    def __init__(
        self,
        config: ScribeConfig | None = None,
        *,
        config_path: str | Path | None = None,
        http_client: httpx.AsyncClient | None = None,
        **overrides: Any,
    ) -> None:
        self.config = config or ScribeConfig.load(path=config_path, **overrides)
        self._transport = Transport(self.config, client=http_client)

        self.discovery = DiscoveryAPI(self._transport)
        self.sessions = SessionsAPI(self._transport)
        self.stream = StreamUploader(self._transport)
        self._chunked = ChunkedUploader(self._transport)
        self._poller = ResultPoller(self.sessions)

    async def create_session(self, **kwargs: Any) -> CreateSessionResponse:
        """Create a session (see SessionsAPI.create). Defaults pulled from config."""
        kwargs.setdefault("upload_type", "chunked")
        kwargs.setdefault("communication_protocol", "http")
        return await self.sessions.create(**kwargs)

    async def upload_audio_file(
        self,
        session_id: str,
        audio: bytes | str | Path,
        *,
        prefix: str = "chunk",
        start_index: int = 0,
        end_session: bool = True,
    ) -> int:
        """Decode + VAD an audio file/bytes locally, upload the speech chunks.

        Replaces whole-file ("single") upload: voice activity detection runs on
        this machine and only speech-bounded WAV chunks (`chunk_0`, `chunk_1`, …)
        are POSTed — the backend never sees un-VADded audio. Accepts a path or
        raw container bytes (wav/mp3/m4a/webm/ogg, decoded via the `[audio]`
        extra). Returns the number of chunks uploaded.

        Pass `end_session=False` (and a running `start_index`) to upload several
        files into one session before ending it yourself.
        """
        from .audio import vad_chunks_from_file

        # Decode + VAD are CPU-bound and synchronous; run them off the event loop.
        chunks = await anyio.to_thread.run_sync(
            lambda: list(vad_chunks_from_file(audio))
        )
        return await self._chunked.upload_all(
            session_id,
            chunks,
            prefix=prefix,
            ext="wav",
            start_index=start_index,
            end_session=end_session,
        )

    async def upload_pcm(
        self,
        session_id: str,
        pcm: bytes,
        *,
        sample_rate: int = 16000,
        prefix: str = "chunk",
        start_index: int = 0,
        end_session: bool = True,
    ) -> int:
        """VAD raw 16-bit mono PCM locally, upload the speech chunks.

        Same as `upload_audio_file` but for already-decoded PCM (e.g. captured
        from a mic). Returns the number of chunks uploaded.
        """
        from .audio import vad_chunks_from_pcm

        chunks = await anyio.to_thread.run_sync(
            lambda: list(vad_chunks_from_pcm(pcm, sample_rate=sample_rate))
        )
        return await self._chunked.upload_all(
            session_id,
            chunks,
            prefix=prefix,
            ext="wav",
            start_index=start_index,
            end_session=end_session,
        )

    async def upload_chunks(
        self,
        session_id: str,
        chunks: AsyncIterable[bytes],
        *,
        prefix: str = "chunk",
        ext: str = "wav",
        start_index: int = 0,
        end_session: bool = True,
    ) -> int:
        """Upload an (async) stream of pre-chunked audio as chunk_0, chunk_1, ..."""
        return await self._chunked.upload_all(
            session_id,
            chunks,
            prefix=prefix,
            ext=ext,
            start_index=start_index,
            end_session=end_session,
        )

    async def upload_chunk(
        self, session_id: str, index: int, data: bytes, *, prefix: str = "chunk", ext: str = "m4a"
    ) -> UploadAudioResponse:
        """Upload one chunk (caller manages indexing and end())."""
        return await self._chunked.upload_chunk(
            session_id, index, data, prefix=prefix, ext=ext
        )

    async def end_session(self, session_id: str, *, audio_files_sent: int) -> None:
        await self.sessions.end(session_id, audio_files_sent=audio_files_sent)

    async def open_stream(self, **kwargs: Any) -> StreamSession:
        """Open a connected WebSocket streaming session."""
        return await self.stream.open(**kwargs)

    async def wait_for_results(
        self,
        session_id: str,
        *,
        interval: float | None = None,
        timeout: float | None = None,
        template_id: str | None = None,
        on_update: Callable[[SessionStatusResponse], Awaitable[None] | None] | None = None,
    ) -> SessionStatusResponse:
        """Poll until the session reaches a terminal state."""
        return await self._poller.wait(
            session_id,
            interval=interval or self.config.poll_interval,
            timeout=timeout or self.config.poll_timeout,
            template_id=template_id,
            on_update=on_update,
        )

    async def aclose(self) -> None:
        await self._transport.aclose()

    async def __aenter__(self) -> AsyncScribeClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()
