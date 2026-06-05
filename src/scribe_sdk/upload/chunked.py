"""Chunked upload: POST each VAD-bounded chunk as chunk_0, chunk_1, ...

Backend contract (`POST /v1/sessions/{id}/audio/{file_name}`):
- file_name must be `<base>_<number>.<ext>` so the server can recover order.
- body is raw audio bytes; Content-Type from the extension.
- finish with `POST /v1/sessions/{id}/end {audio_files_sent: N}`.

This uploader is transport-only: it takes already-encoded chunk bytes. Producing
those chunks (mic capture + silero VAD) lives in `scribe_sdk.audio` so the core
SDK stays free of native deps.
"""

from __future__ import annotations

from collections.abc import AsyncIterable, AsyncIterator, Iterable
from typing import Union

from ..http import Transport
from ..models import UploadAudioResponse
from . import content_type_for

# Accepts either an async stream of chunks (live capture) or a plain sync
# iterable/list (a fully VAD'd file) — `_as_async_iter` normalizes both.
ChunkSource = Union[AsyncIterable[bytes], "AsyncIterator[bytes]", Iterable[bytes]]


class ChunkedUploader:
    def __init__(self, transport: Transport) -> None:
        self._t = transport

    async def upload_chunk(
        self,
        session_id: str,
        index: int,
        data: bytes,
        *,
        prefix: str = "chunk",
        ext: str = "wav",
    ) -> UploadAudioResponse:
        """Upload a single chunk as `{prefix}_{index}.{ext}`."""
        filename = f"{prefix}_{index}.{ext.lstrip('.')}"
        resp = await self._t.request(
            "POST",
            f"/v1/sessions/{session_id}/audio/{filename}",
            content=data,
            headers={"Content-Type": content_type_for(filename)},
            expected=(200,),
        )
        return UploadAudioResponse.model_validate(resp.json())

    async def upload_all(
        self,
        session_id: str,
        chunks: ChunkSource,
        *,
        prefix: str = "chunk",
        ext: str = "wav",
        start_index: int = 0,
        end_session: bool = True,
    ) -> int:
        """Stream chunks from an (async) iterable, then optionally end the session.

        Returns the number of chunks uploaded.
        """
        index = start_index
        async for data in _as_async_iter(chunks):
            if not data:
                continue
            await self.upload_chunk(session_id, index, data, prefix=prefix, ext=ext)
            index += 1

        sent = index - start_index
        if end_session:
            await self._end(session_id, sent)
        return sent

    async def _end(self, session_id: str, audio_files_sent: int) -> None:
        from ..sessions import SessionsAPI

        await SessionsAPI(self._t).end(session_id, audio_files_sent=audio_files_sent)


async def _as_async_iter(source: ChunkSource) -> AsyncIterator[bytes]:
    if hasattr(source, "__aiter__"):
        async for item in source:  # type: ignore[union-attr]
            yield item
    else:  # plain iterable of bytes
        for item in source:  # type: ignore[union-attr]
            yield item
