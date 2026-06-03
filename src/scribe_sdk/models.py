"""Pydantic models mirroring the MedScribeAlliance Protocol v0.1 wire shapes.

These match `voice2rx/protocol/models/sessions.py` on the backend. Request
models are lenient where the server is; response models tolerate extra fields
(`extra="allow"`) so a backend that grows new fields does not break old SDKs.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class SessionMode(str, Enum):
    CONSULTATION = "consultation"
    DICTATION = "dictation"


class Model(str, Enum):
    LITE = "lite"
    PRO = "pro"


class UploadType(str, Enum):
    CHUNKED = "chunked"
    SINGLE = "single"
    STREAM = "stream"


class CommunicationProtocol(str, Enum):
    WEBSOCKET = "websocket"
    HTTP = "http"
    RPC = "rpc"


class SessionStatus(str, Enum):
    CREATED = "created"
    INITIALIZED = "initialized"
    RECORDING = "recording"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    EXPIRED = "expired"


# Statuses that mean "stop polling".
TERMINAL_STATUSES = {
    SessionStatus.COMPLETED,
    SessionStatus.PARTIAL,
    SessionStatus.FAILED,
    SessionStatus.EXPIRED,
}


class _Wire(BaseModel):
    model_config = ConfigDict(extra="allow", use_enum_values=True)


# --------------------------------------------------------------------------- #
# Requests
# --------------------------------------------------------------------------- #
class CreateSessionRequest(_Wire):
    session_id: str | None = Field(default=None, min_length=16, max_length=64)
    session_mode: SessionMode = SessionMode.DICTATION
    templates: list[str]
    model: Model = Model.LITE
    language_hint: list[str] | None = None
    transcript_language: str | None = None
    upload_type: UploadType
    communication_protocol: CommunicationProtocol
    additional_data: dict[str, Any] | None = None
    patient_details: dict[str, Any] | None = None


class EndSessionRequest(_Wire):
    audio_files_sent: int = Field(ge=0)


class PatchSessionRequest(_Wire):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    patient_details: dict[str, Any] | None = None
    user_status: str | None = None
    processing_status: str | None = None
    additional_data: dict[str, Any] | None = None
    language_hint: list[str] | None = None
    templates: list[str] | None = None


# --------------------------------------------------------------------------- #
# Responses
# --------------------------------------------------------------------------- #
class CreateSessionResponse(_Wire):
    session_id: str
    status: str
    created_at: int
    expires_at: int
    upload_url: str | None = None
    patient_details: dict[str, Any] | None = None


class TemplateResult(_Wire):
    status: str
    data: Any | None = None
    error: dict[str, Any] | None = None


class SessionStatusResponse(_Wire):
    """Unified view over the 200 / 202 / 206 / 410 session-status responses.

    The SDK normalizes all of them into this single shape; `http_status`
    records which one the backend actually returned.
    """

    session_id: str
    status: str
    created_at: int | None = None
    completed_at: int | None = None
    expires_at: int | None = None
    model_used: str | None = None
    language_detected: str | None = None
    audio_files_received: int | None = None
    audio_files_processed: int | None = None
    audio_files: list[str] | None = None
    additional_data: dict[str, Any] | None = None
    templates: dict[str, TemplateResult] | None = None
    transcript: str | None = None
    processing_errors: list[dict[str, Any]] | None = None
    patient_details: dict[str, Any] | None = None

    # Injected by the SDK, not part of the wire body.
    http_status: int | None = None

    @property
    def is_terminal(self) -> bool:
        try:
            return SessionStatus(self.status) in TERMINAL_STATUSES
        except ValueError:
            return False

    @property
    def is_complete(self) -> bool:
        return self.status in (SessionStatus.COMPLETED.value, SessionStatus.PARTIAL.value)


class EndSessionResponse(_Wire):
    session_id: str
    status: str
    message: str | None = None
    audio_files_received: int | None = None
    audio_files: list[str] | None = None


class UploadAudioResponse(_Wire):
    session_id: str
    success: bool
    original_filename: str | None = None


class TemplateInfo(_Wire):
    id: str
    name: str | None = None
    description: str | None = None


class TemplatesListResponse(_Wire):
    templates: list[TemplateInfo]


# --------------------------------------------------------------------------- #
# Streaming
# --------------------------------------------------------------------------- #
class CreateStreamSessionRequest(_Wire):
    session_id: str | None = None
    b_id: str
    uuid: str | None = None
    caller_number: str | None = None
    provider: str | None = None
    additional_data: dict[str, Any] | None = None


class CreateStreamSessionResponse(_Wire):
    stream_id: str
    wss_url: str
    session_id: str
    b_id: str | None = None
