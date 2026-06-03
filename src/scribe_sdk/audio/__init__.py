"""Optional audio toolkit: mic capture, silero VAD chunking, encode helpers.

Requires the ``[audio]`` extra (native libs: portaudio, onnxruntime, PyAV)::

    uv add "scribe-python-sdk[audio]"

Imports here are lazy where they pull native deps, so importing this module is
cheap; the ImportError (with install hint) surfaces only when you call a
function that needs a missing library.
"""

from .capture import microphone_frames, record_pcm
from .encode import decode_to_pcm16, pcm16_to_float32, pcm16_to_wav
from .vad import (
    StreamingVADChunker,
    vad_chunks_from_file,
    vad_chunks_from_pcm,
    vad_segments_pcm,
)

__all__ = [
    "microphone_frames",
    "record_pcm",
    "decode_to_pcm16",
    "pcm16_to_wav",
    "pcm16_to_float32",
    "vad_chunks_from_file",
    "vad_chunks_from_pcm",
    "vad_segments_pcm",
    "StreamingVADChunker",
]
