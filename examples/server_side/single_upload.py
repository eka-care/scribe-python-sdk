"""Minimal server-side usage: single-file upload (sync API).

Run:
    uv run python examples/server_side/single_upload.py path/to/visit.wav
"""

import sys

from scribe_sdk import ScribeClient


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: single_upload.py <audio-file>")
    audio_path = sys.argv[1]

    # Config is read from scribe.config.json / SCRIBE_* env / .env.
    with ScribeClient() as client:
        session = client.create_session(
            upload_type="single",
            communication_protocol="http",
            # templates omitted -> uses default_templates from config
        )
        print("session:", session.session_id)

        client.upload_file(session.session_id, audio_path)  # ends the session
        result = client.wait_for_results(session.session_id)

        print("status:", result.status)
        for tid, tr in (result.templates or {}).items():
            print(f"\n[{tid}] {tr.status}")
            print(tr.data if tr.data is not None else tr.error)


if __name__ == "__main__":
    main()
