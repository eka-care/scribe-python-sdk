"""Audio upload strategies for the protocol HTTP path."""

# Maps file extension -> Content-Type accepted by the backend audio endpoint.
_CONTENT_TYPES = {
    ".webm": "audio/webm;codecs=opus",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg;codecs=opus",
    ".mp4": "audio/mp4",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mp3",
}


def content_type_for(filename: str) -> str:
    """Best-effort Content-Type from a filename extension."""
    for ext, ct in _CONTENT_TYPES.items():
        if filename.lower().endswith(ext):
            return ct
    return "application/octet-stream"


# Submodule imports come after `content_type_for` is defined to avoid a circular
# import (the submodules import this helper from the package).
from .chunked import ChunkedUploader  # noqa: E402
from .single import SingleUploader  # noqa: E402

__all__ = ["ChunkedUploader", "SingleUploader", "content_type_for"]
