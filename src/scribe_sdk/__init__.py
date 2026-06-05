"""Scribe Python SDK — MedScribeAlliance Protocol v0.1 client.

Audio is always VAD'd on the client (see `scribe_sdk.audio`); the SDK POSTs only
speech-bounded chunks and never asks the backend to VAD a whole file.

Quick start (sync)::

    from scribe_sdk import ScribeClient

    client = ScribeClient(config_path="scribe.config.json")
    s = client.create_session(upload_type="chunked", communication_protocol="http")
    client.upload_audio_file(s.session_id, "visit.wav")   # VAD locally, upload chunks
    result = client.wait_for_results(s.session_id)
    print(result.templates)
    client.close()

Quick start (async)::

    from scribe_sdk import AsyncScribeClient

    async with AsyncScribeClient(config_path="scribe.config.json") as client:
        s = await client.create_session(upload_type="chunked", communication_protocol="http")
        await client.upload_audio_file(s.session_id, "visit.wav")
        result = await client.wait_for_results(s.session_id)
"""

from __future__ import annotations

from .client_async import AsyncScribeClient
from .client_sync import ScribeClient, SyncStreamSession
from .config import ScribeConfig
from .errors import (
    APIError,
    AuthError,
    ConfigError,
    InvalidAudioError,
    ScribeError,
    SessionExpiredError,
    SessionNotFoundError,
    SessionStateError,
    ValidationError,
)
from .models import (
    CommunicationProtocol,
    CreateSessionResponse,
    Model,
    SessionMode,
    SessionStatus,
    SessionStatusResponse,
    UploadType,
)
from .stream import StreamSession

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # clients
    "ScribeClient",
    "AsyncScribeClient",
    "SyncStreamSession",
    "StreamSession",
    "ScribeConfig",
    # enums / models
    "CommunicationProtocol",
    "CreateSessionResponse",
    "Model",
    "SessionMode",
    "SessionStatus",
    "SessionStatusResponse",
    "UploadType",
    # errors
    "ScribeError",
    "ConfigError",
    "AuthError",
    "APIError",
    "InvalidAudioError",
    "ValidationError",
    "SessionNotFoundError",
    "SessionExpiredError",
    "SessionStateError",
]
