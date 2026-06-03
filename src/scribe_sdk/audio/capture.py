"""Microphone capture (optional ``[audio]`` extra), via sounddevice/portaudio.

Yields raw 16-bit little-endian mono PCM frames at 16 kHz — the format both the
streaming WS path and the VAD chunker expect.
"""

from __future__ import annotations

import queue
from collections.abc import Iterator

from .encode import TARGET_SAMPLE_RATE


def _require_sounddevice():
    try:
        import sounddevice as sd
    except (ImportError, OSError) as exc:  # OSError: portaudio missing
        raise ImportError(
            'Microphone capture needs sounddevice + portaudio. Install: '
            'uv add "scribe-python-sdk[audio]"  (and the portaudio system lib)'
        ) from exc
    return sd


def microphone_frames(
    *,
    sample_rate: int = TARGET_SAMPLE_RATE,
    frame_ms: int = 30,
    device: int | None = None,
    max_seconds: float | None = None,
) -> Iterator[bytes]:
    """Yield PCM frames from the default mic until interrupted or `max_seconds`.

    Each frame is `frame_ms` of audio. Stop with Ctrl-C / by breaking the loop;
    the input stream is closed on exit.
    """
    sd = _require_sounddevice()
    blocksize = int(sample_rate * frame_ms / 1000)
    q: queue.Queue[bytes] = queue.Queue()

    def _callback(indata, frames, time_info, status):  # noqa: ANN001
        q.put(bytes(indata))

    emitted_frames = 0
    frame_limit = (
        int(max_seconds * 1000 / frame_ms) if max_seconds is not None else None
    )

    with sd.RawInputStream(
        samplerate=sample_rate,
        blocksize=blocksize,
        device=device,
        dtype="int16",
        channels=1,
        callback=_callback,
    ):
        while frame_limit is None or emitted_frames < frame_limit:
            yield q.get()
            emitted_frames += 1


def record_pcm(
    seconds: float,
    *,
    sample_rate: int = TARGET_SAMPLE_RATE,
    device: int | None = None,
) -> bytes:
    """Record a fixed duration and return raw PCM bytes (blocking)."""
    sd = _require_sounddevice()
    frames = sd.rec(
        int(seconds * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        device=device,
    )
    sd.wait()
    return frames.tobytes()
