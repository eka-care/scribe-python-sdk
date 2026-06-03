"""Scribe Python SDK — MedScribeAlliance Protocol v0.1 client.

Quick start (sync)::

    from scribe_sdk import ScribeClient

    client = ScribeClient(config_path="scribe.config.json")
    s = client.create_session(upload_type="single", communication_protocol="http")
    client.upload_file(s.session_id, "visit.wav")
    result = client.wait_for_results(s.session_id)
    print(result.templates)
    client.close()

Quick start (async)::

    from scribe_sdk import AsyncScribeClient

    async with AsyncScribeClient(config_path="scribe.config.json") as client:
        s = await client.create_session(upload_type="single", communication_protocol="http")
        await client.upload_file(s.session_id, "visit.wav")
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
