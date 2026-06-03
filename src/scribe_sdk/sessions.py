"""Session lifecycle client for protocol v0.1.

Wraps the `/v1/sessions` family:
    POST   /v1/sessions                                  create
    GET    /v1/sessions/{id}                             status / results
    POST   /v1/sessions/{id}/end                         end (commit + process)
    PATCH  /v1/sessions/{id}                             update (while init)
    POST   /v1/sessions/{id}/process/template/{tid}      trigger extraction
"""

from __future__ import annotations

from typing import Any

from .config import ScribeConfig
from .http import Transport
from .models import (
    CommunicationProtocol,
    CreateSessionRequest,
    CreateSessionResponse,
    EndSessionRequest,
    EndSessionResponse,
    Model,
    PatchSessionRequest,
    SessionMode,
    SessionStatusResponse,
    UploadType,
)


class SessionsAPI:
    def __init__(self, transport: Transport) -> None:
        self._t = transport

    @property
    def _config(self) -> ScribeConfig:
        return self._t.config

    async def create(
        self,
        *,
        upload_type: UploadType | str,
        communication_protocol: CommunicationProtocol | str,
        templates: list[str] | None = None,
        session_id: str | None = None,
        session_mode: SessionMode | str = SessionMode.DICTATION,
        model: Model | str | None = None,
        language_hint: list[str] | None = None,
        transcript_language: str | None = None,
        additional_data: dict[str, Any] | None = None,
        patient_details: dict[str, Any] | None = None,
    ) -> CreateSessionResponse:
        """Create a session, falling back to configured defaults."""
        resolved_templates = templates or self._config.default_templates
        if not resolved_templates:
            raise ValueError(
                "No templates specified and no default_templates configured. "
                "Pass templates=[...] or set default_templates in your config."
            )

        resolved_model = model if model is not None else self._config.default_model

        req = CreateSessionRequest(
            session_id=session_id,
            session_mode=SessionMode(session_mode),
            templates=resolved_templates,
            model=Model(resolved_model),
            language_hint=language_hint or self._config.default_language_hint,
            transcript_language=transcript_language or self._config.transcript_language,
            upload_type=UploadType(upload_type),
            communication_protocol=CommunicationProtocol(communication_protocol),
            additional_data=additional_data,
            patient_details=patient_details,
        )
        resp = await self._t.request(
            "POST",
            "/v1/sessions",
            json=req.model_dump(exclude_none=True),
            headers={"Content-Type": "application/json"},
            expected=(200, 201),
        )
        return CreateSessionResponse.model_validate(resp.json())

    async def get(
        self, session_id: str, *, template_id: str | None = None
    ) -> SessionStatusResponse:
        """Get session status/results. Normalizes 200/202/206/410 into one model."""
        params = {"template_id": template_id} if template_id else None
        resp = await self._t.request(
            "GET",
            f"/v1/sessions/{session_id}",
            params=params,
            expected=(200, 202, 206, 410),
        )
        body = resp.json()
        result = SessionStatusResponse.model_validate(body)
        result.http_status = resp.status_code
        return result

    async def end(self, session_id: str, *, audio_files_sent: int) -> EndSessionResponse:
        """Signal end-of-upload; backend commits and starts processing."""
        req = EndSessionRequest(audio_files_sent=audio_files_sent)
        resp = await self._t.request(
            "POST",
            f"/v1/sessions/{session_id}/end",
            json=req.model_dump(),
            headers={"Content-Type": "application/json"},
            expected=(200, 202),
        )
        return EndSessionResponse.model_validate(resp.json())

    async def patch(self, session_id: str, **changes: Any) -> dict[str, Any]:
        """Update a session while it is still in the init state."""
        req = PatchSessionRequest(**changes)
        resp = await self._t.request(
            "PATCH",
            f"/v1/sessions/{session_id}",
            json=req.model_dump(exclude_none=True),
            headers={"Content-Type": "application/json"},
            expected=(200,),
        )
        return resp.json()

    async def process_template(
        self, session_id: str, template_id: str | None = None
    ) -> dict[str, Any]:
        """Trigger (re)generation of a template's extraction."""
        path = f"/v1/sessions/{session_id}/process/template"
        if template_id:
            path += f"/{template_id}"
        resp = await self._t.request("POST", path, expected=(200, 202))
        return resp.json()
