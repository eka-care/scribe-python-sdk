"""AsyncScribeClient — the primary, fully-async SDK entry point.

Exposes both low-level sub-APIs (`.sessions`, `.discovery`, `.stream`) and
high-level convenience methods that cover the common flows end to end:

    chunked:   create_session -> upload chunks -> end -> wait_for_results
    single:    create_session -> upload file (+ end) -> wait_for_results
    streaming: stream.open -> send_audio -> stop -> wait_for_results
"""

from __future__ import annotations

from collections.abc import AsyncIterable, Awaitable
from pathlib import Path
from typing import Any, Callable

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
from .upload import ChunkedUploader, SingleUploader


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
        self._single = SingleUploader(self._transport)
        self._poller = ResultPoller(self.sessions)

    # ------------------------------------------------------------------ #
    # High-level convenience flows
    # ------------------------------------------------------------------ #
    async def create_session(self, **kwargs: Any) -> CreateSessionResponse:
        """Create a session (see SessionsAPI.create). Defaults pulled from config."""
        kwargs.setdefault("upload_type", "chunked")
        kwargs.setdefault("communication_protocol", "http")
        return await self.sessions.create(**kwargs)

    async def upload_file(
        self,
        session_id: str,
        audio: bytes | str | Path,
        *,
        filename: str | None = None,
        content_type: str | None = None,
        end_session: bool = True,
    ) -> UploadAudioResponse:
        """Single-file upload (server-side VAD). Optionally ends the session."""
        return await self._single.upload(
            session_id,
            audio,
            filename=filename,
            content_type=content_type,
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

    # ------------------------------------------------------------------ #
    async def aclose(self) -> None:
        await self._transport.aclose()

    async def __aenter__(self) -> AsyncScribeClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()
