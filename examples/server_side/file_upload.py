"""Server-side usage: upload a file with client-side VAD (async API).

Decodes the input, runs silero VAD **locally**, and uploads only the
speech-bounded chunk_0, chunk_1, … — the backend never VADs a whole file. The
steps are kept separate: start session -> upload audio -> end session -> poll
results (1s interval). Requires the [audio] extra.

Run:
    uv run python examples/server_side/file_upload.py path/to/visit.wav
"""

import asyncio
import sys

from scribe_sdk import AsyncScribeClient


async def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: file_upload.py <audio-file>")
    audio_path = sys.argv[1]

    async with AsyncScribeClient() as client:
        # 1) start the session
        session = await client.create_session(
            upload_type="chunked", communication_protocol="http"
        )
        print("session:", session.session_id)

        # 2) decode + VAD locally, upload the speech chunks (end separately below)
        n = await client.upload_audio_file(
            session.session_id, audio_path, end_session=False
        )
        print(f"VAD'd locally; uploaded {n} chunk(s)")

        # 3) end the session
        await client.end_session(session.session_id, audio_files_sent=n)

        # 4) poll for results (waits 1s between checks by default)
        result = await client.wait_for_results(
            session.session_id, on_update=lambda s: print("  status:", s.status)
        )
        print("\nfinal:", result.status)
        for tid, tr in (result.templates or {}).items():
            print(f"\n[{tid}] {tr.status}\n{tr.data if tr.data is not None else tr.error}")


if __name__ == "__main__":
    asyncio.run(main())
