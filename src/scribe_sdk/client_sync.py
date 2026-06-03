"""ScribeClient — synchronous facade over AsyncScribeClient.

Runs the async client on a dedicated background event loop (via an anyio
blocking portal) so blocking code, scripts, and the CLI can use the SDK without
writing `async`/`await`. WebSocket streaming is supported through a
`SyncStreamSession` that proxies each call onto the same loop.

    client = ScribeClient(config_path="scribe.config.json")
    session = client.create_session(upload_type="single", communication_protocol="http")
    client.upload_file(session.session_id, "visit.wav")
    result = client.wait_for_results(session.session_id)
    client.close()
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from anyio.from_thread import BlockingPortal, start_blocking_portal

from .client_async import AsyncScribeClient
from .config import ScribeConfig
from .models import (
    CreateSessionResponse,
    SessionStatusResponse,
    UploadAudioResponse,
)
from .stream import StreamSession


class ScribeClient:
    def __init__(
        self,
        config: ScribeConfig | None = None,
        *,
        config_path: str | Path | None = None,
        **overrides: Any,
    ) -> None:
        self._portal_cm = start_blocking_portal()
        self._portal: BlockingPortal = self._portal_cm.__enter__()
        self._async: AsyncScribeClient = self._portal.call(
            lambda: _make_async(config, config_path, overrides)
        )

    @property
    def config(self) -> ScribeConfig:
        return self._async.config

    # ------------------------------------------------------------------ #
    def discovery(self) -> dict[str, Any]:
        return self._portal.call(self._async.discovery.get)

    def create_session(self, **kwargs: Any) -> CreateSessionResponse:
        return self._portal.call(lambda: self._async.create_session(**kwargs))

    def upload_file(
        self,
        session_id: str,
        audio: bytes | str | Path,
        *,
        filename: str | None = None,
        content_type: str | None = None,
        end_session: bool = True,
    ) -> UploadAudioResponse:
        return self._portal.call(
            lambda: self._async.upload_file(
                session_id,
                audio,
                filename=filename,
                content_type=content_type,
                end_session=end_session,
            )
        )

    def upload_chunk(
        self, session_id: str, index: int, data: bytes, *, prefix: str = "chunk", ext: str = "wav"
    ) -> UploadAudioResponse:
        return self._portal.call(
            lambda: self._async.upload_chunk(session_id, index, data, prefix=prefix, ext=ext)
        )

    def end_session(self, session_id: str, *, audio_files_sent: int) -> None:
        self._portal.call(
            lambda: self._async.end_session(session_id, audio_files_sent=audio_files_sent)
        )

    def open_stream(self, **kwargs: Any) -> SyncStreamSession:
        session = self._portal.call(lambda: self._async.open_stream(**kwargs))
        return SyncStreamSession(session, self._portal)

    def wait_for_results(
        self,
        session_id: str,
        *,
        interval: float | None = None,
        timeout: float | None = None,
        template_id: str | None = None,
        on_update: Callable[[SessionStatusResponse], None] | None = None,
    ) -> SessionStatusResponse:
        return self._portal.call(
            lambda: self._async.wait_for_results(
                session_id,
                interval=interval,
                timeout=timeout,
                template_id=template_id,
                on_update=on_update,
            )
        )

    # ------------------------------------------------------------------ #
    def close(self) -> None:
        try:
            self._portal.call(self._async.aclose)
        finally:
            self._portal_cm.__exit__(None, None, None)

    def __enter__(self) -> ScribeClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class SyncStreamSession:
    """Synchronous proxy over a `StreamSession` bound to the client's loop."""

    def __init__(self, session: StreamSession, portal: BlockingPortal) -> None:
        self._session = session
        self._portal = portal

    @property
    def session_id(self) -> str:
        return self._session.session_id

    @property
    def stream_id(self) -> str:
        return self._session.stream_id

    def send_audio(self, pcm: bytes) -> None:
        self._portal.call(lambda: self._session.send_audio(pcm))

    def stop(self, reason: str | None = None) -> None:
        self._portal.call(lambda: self._session.stop(reason))

    def __enter__(self) -> SyncStreamSession:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.stop()


async def _make_async(
    config: ScribeConfig | None,
    config_path: str | Path | None,
    overrides: dict[str, Any],
) -> AsyncScribeClient:
    return AsyncScribeClient(config=config, config_path=config_path, **overrides)
