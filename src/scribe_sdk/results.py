"""Result polling.

After a session is ended (or a stream stops), processing is asynchronous. Poll
`GET /v1/sessions/{id}` until it reaches a terminal status (completed / partial /
failed / expired) or a timeout elapses.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Callable

import anyio

from .errors import ScribeError, SessionExpiredError
from .models import SessionStatusResponse
from .sessions import SessionsAPI


class ResultPoller:
    def __init__(self, sessions: SessionsAPI) -> None:
        self._sessions = sessions

    async def wait(
        self,
        session_id: str,
        *,
        interval: float,
        timeout: float,
        template_id: str | None = None,
        on_update: Callable[[SessionStatusResponse], Awaitable[None] | None] | None = None,
    ) -> SessionStatusResponse:
        """Poll until terminal or timeout. Raises on expiry/timeout."""
        start = anyio.current_time()

        while True:
            status = await self._sessions.get(session_id, template_id=template_id)
            if on_update is not None:
                result = on_update(status)
                if result is not None:
                    await result  # support async callbacks

            if status.http_status == 410 or status.status == "expired":
                raise SessionExpiredError(
                    f"Session {session_id} expired before completing.",
                    status_code=410,
                )
            if status.is_terminal:
                return status

            if anyio.current_time() - start >= timeout:
                raise ScribeError(
                    f"Timed out after {timeout}s waiting for session {session_id} "
                    f"(last status: {status.status})."
                )
            await anyio.sleep(interval)
