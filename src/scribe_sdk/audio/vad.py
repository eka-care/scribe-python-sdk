"""Silero-VAD client-side chunking (optional ``[audio]`` extra).

Splits audio into speech-bounded chunks — the same VAD model the backend
streaming pipeline uses — so chunked upload sends `chunk_0`, `chunk_1`, … that
align with natural speech boundaries instead of arbitrary time slices.

Each yielded chunk is a WAV byte string (mono, 16 kHz, 16-bit) ready to POST.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from .encode import (
    TARGET_SAMPLE_RATE,
    decode_to_pcm16,
    pcm16_to_float32,
    pcm16_to_wav,
)

# Mirror the backend's chunking envelope (see vad_chunking_service.py).
MAX_CHUNK_SECONDS = 24.0
PREFERRED_CHUNK_SECONDS =10.0

_model = None


def _load_model():
    """Lazily load the silero VAD ONNX model (cached process-wide)."""
    global _model
    if _model is None:
        try:
            from silero_vad import load_silero_vad
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                'silero-vad is required for client-side VAD. Install: '
                'uv add "scribe-python-sdk[audio]"'
            ) from exc
        _model = load_silero_vad(onnx=True)
    return _model


def vad_segments_pcm(
    pcm: bytes,
    *,
    sample_rate: int = TARGET_SAMPLE_RATE,
    max_chunk_seconds: float = MAX_CHUNK_SECONDS,
) -> Iterator[bytes]:
    """Yield raw-PCM segments bounded by detected speech.

    Long speech runs are hard-split at `max_chunk_seconds` so no single chunk
    exceeds the backend's per-chunk ceiling.
    """
    from silero_vad import get_speech_timestamps

    model = _load_model()
    audio = pcm16_to_float32(pcm)
    timestamps = get_speech_timestamps(
        audio, model, sampling_rate=sample_rate, return_seconds=False
    )
    max_samples = int(max_chunk_seconds * sample_rate)
    bytes_per_sample = 2

    for ts in timestamps:
        start, end = ts["start"], ts["end"]
        for seg_start in range(start, end, max_samples):
            seg_end = min(seg_start + max_samples, end)
            yield pcm[seg_start * bytes_per_sample : seg_end * bytes_per_sample]


def vad_chunks_from_pcm(
    pcm: bytes, *, sample_rate: int = TARGET_SAMPLE_RATE
) -> Iterator[bytes]:
    """Yield WAV-encoded speech chunks from raw PCM."""
    for segment in vad_segments_pcm(pcm, sample_rate=sample_rate):
        if segment:
            yield pcm16_to_wav(segment, sample_rate=sample_rate)


def vad_chunks_from_file(
    source: str | Path | bytes,
    *,
    target_sample_rate: int = TARGET_SAMPLE_RATE,
) -> Iterator[bytes]:
    """Decode an audio file/bytes, VAD it, and yield WAV chunks."""
    pcm, sr = decode_to_pcm16(source, target_sample_rate)
    yield from vad_chunks_from_pcm(pcm, sample_rate=sr)


class StreamingVADChunker:
    """Incremental VAD for live capture.

    Feed PCM as it arrives via `feed()`; it buffers and, whenever enough audio
    has accumulated, emits completed WAV chunks. Call `flush()` at the end.
    Note: silero runs on whole buffers, so this batches by `window_seconds`.
    """

    def __init__(
        self,
        *,
        sample_rate: int = TARGET_SAMPLE_RATE,
        window_seconds: float = PREFERRED_CHUNK_SECONDS,
    ) -> None:
        self._sr = sample_rate
        self._window_bytes = int(window_seconds * sample_rate) * 2
        self._buffer = bytearray()

    def feed(self, pcm: bytes) -> Iterator[bytes]:
        self._buffer.extend(pcm)
        while len(self._buffer) >= self._window_bytes:
            window = bytes(self._buffer[: self._window_bytes])
            del self._buffer[: self._window_bytes]
            yield from vad_chunks_from_pcm(window, sample_rate=self._sr)

    def flush(self) -> Iterator[bytes]:
        if self._buffer:
            window = bytes(self._buffer)
            self._buffer.clear()
            yield from vad_chunks_from_pcm(window, sample_rate=self._sr)
