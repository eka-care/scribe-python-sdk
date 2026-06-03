"""Audio decode/encode helpers (part of the optional ``[audio]`` extra).

- `decode_to_pcm16`: decode any supported container (wav/mp3/m4a/webm/ogg) to
  raw 16-bit little-endian mono PCM at a target sample rate, using PyAV.
- `pcm16_to_wav`: wrap raw PCM in a WAV container (stdlib, no native deps).
- `pcm16_to_float32`: normalize PCM bytes to a numpy float32 array for VAD.

WAV is the chunk format the bundled VAD chunker emits — the backend accepts
`audio/wav`, and producing it needs no encoder.
"""

from __future__ import annotations

import io
import wave
from pathlib import Path

TARGET_SAMPLE_RATE = 16000


def _require(mod: str, extra: str = "audio"):
    try:
        return __import__(mod)
    except ImportError as exc:  # pragma: no cover - exercised only without extra
        raise ImportError(
            f"'{mod}' is required for audio processing. Install the extra: "
            f'uv add "scribe-python-sdk[{extra}]"'
        ) from exc


def pcm16_to_wav(pcm: bytes, sample_rate: int = TARGET_SAMPLE_RATE, channels: int = 1) -> bytes:
    """Wrap raw 16-bit PCM in a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def pcm16_to_float32(pcm: bytes):
    """Convert 16-bit PCM bytes to a normalized numpy float32 array in [-1, 1]."""
    np = _require("numpy")
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    return audio


def decode_to_pcm16(
    source: bytes | str | Path,
    target_sample_rate: int = TARGET_SAMPLE_RATE,
) -> tuple[bytes, int]:
    """Decode an audio source to mono 16-bit PCM at `target_sample_rate`.

    Returns (pcm_bytes, sample_rate). WAV inputs already matching the target are
    decoded with the stdlib; everything else goes through PyAV.
    """
    if isinstance(source, (str, Path)):
        path = Path(source)
        if path.suffix.lower() == ".wav":
            pcm, sr = _decode_wav(path.read_bytes())
            if sr == target_sample_rate:
                return pcm, sr
        data = path.read_bytes()
    else:
        data = source

    return _decode_with_av(data, target_sample_rate)


def _decode_wav(data: bytes) -> tuple[bytes, int]:
    with wave.open(io.BytesIO(data), "rb") as wf:
        sr = wf.getframerate()
        channels = wf.getnchannels()
        frames = wf.readframes(wf.getnframes())
    if channels == 1:
        return frames, sr
    # Downmix to mono.
    np = _require("numpy")
    arr = np.frombuffer(frames, dtype=np.int16).reshape(-1, channels)
    mono = arr.mean(axis=1).astype(np.int16)
    return mono.tobytes(), sr


def _decode_with_av(data: bytes, target_sample_rate: int) -> tuple[bytes, int]:
    av = _require("av")
    container = av.open(io.BytesIO(data))
    resampler = av.AudioResampler(format="s16", layout="mono", rate=target_sample_rate)
    chunks: list[bytes] = []
    for frame in container.decode(audio=0):
        for resampled in resampler.resample(frame):
            chunks.append(bytes(resampled.planes[0]))
    # Flush the resampler.
    for resampled in resampler.resample(None):
        chunks.append(bytes(resampled.planes[0]))
    return b"".join(chunks), target_sample_rate
