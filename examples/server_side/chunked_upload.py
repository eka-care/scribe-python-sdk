"""Server-side usage: chunked upload with client-side silero VAD (async API).

Splits the input into speech-bounded chunk_0, chunk_1, … and uploads each, then
ends the session and polls for results. Requires the [audio] extra.

Run:
    uv run python examples/server_side/chunked_upload.py path/to/visit.wav
"""

import asyncio
import sys

from scribe_sdk import AsyncScribeClient
from scribe_sdk.audio import vad_chunks_from_file


async def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: chunked_upload.py <audio-file>")
    audio_path = sys.argv[1]

    async with AsyncScribeClient() as client:
        session = await client.create_session(
            upload_type="chunked",
            communication_protocol="http",
        )
        print("session:", session.session_id)

        # vad_chunks_from_file yields WAV chunks; upload_chunks names them
        # chunk_0.wav, chunk_1.wav, … and calls /end automatically.
        n = await client.upload_chunks(
            session.session_id, vad_chunks_from_file(audio_path)
        )
        print(f"uploaded {n} chunk(s)")

        result = await client.wait_for_results(
            session.session_id, on_update=lambda s: print("  status:", s.status)
        )
        print("\nfinal:", result.status)
        for tid, tr in (result.templates or {}).items():
            print(f"\n[{tid}] {tr.status}\n{tr.data if tr.data is not None else tr.error}")


if __name__ == "__main__":
    asyncio.run(main())
