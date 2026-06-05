"""`scribe` command-line interface.

A self-contained client that captures audio from a file or the microphone,
runs voice activity detection **locally** (via the `[audio]` extra), and either:

    --mode chunked : VAD on this machine -> upload speech chunks over HTTP
    --mode stream  : stream raw PCM frames live over a WebSocket

Either way the backend never VADs a whole file — there is no single-file upload.
Every run keeps the steps separated: start session -> send audio -> end session
-> poll results (1s interval).

    scribe --mode chunked --file visit.wav
    scribe --mode chunked --record 30
    scribe --mode stream  --record 30

Reads config from --config / SCRIBE_CONFIG / scribe.config.json (+ env). The mic
and VAD options require the [audio] extra.
"""

from __future__ import annotations

import argparse
import sys

from . import ScribeClient, __version__
from .errors import ScribeError

POLL_INTERVAL_SECONDS = 1.0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="scribe", description="Scribe SDK CLI")
    p.add_argument("--version", action="version", version=f"scribe-python-sdk {__version__}")
    p.add_argument(
        "--mode",
        choices=["chunked", "stream"],
        default="chunked",
        help="chunked = local VAD + HTTP chunk upload; stream = live WebSocket (default: chunked)",
    )
    p.add_argument("--config", help="Path to scribe.config.json/.yaml")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--file", help="Audio file to upload (chunked mode only)")
    src.add_argument(
        "--record",
        type=float,
        metavar="SECONDS",
        help="Record from the microphone for N seconds (needs [audio])",
    )
    p.add_argument(
        "--templates",
        help="Comma-separated template ids (overrides config defaults)",
    )
    p.add_argument("--poll-timeout", type=float, default=None, help="Max seconds to wait")
    return p


def _templates(arg: str | None) -> list[str] | None:
    if not arg:
        return None
    return [t.strip() for t in arg.split(",") if t.strip()]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        with ScribeClient(config_path=args.config) as client:
            if args.mode == "stream":
                session_id = _run_stream(client, args)
            else:
                session_id = _run_chunked(client, args)

            # Step 4: poll for results, waiting 1s between checks (client-side).
            print(f"\n⏳ Waiting for results (session {session_id}) …")
            result = client.wait_for_results(
                session_id,
                interval=POLL_INTERVAL_SECONDS,
                timeout=args.poll_timeout,
                on_update=lambda s: print(f"   status: {s.status}"),
            )
            _print_result(result)
        return 0
    except ScribeError as exc:
        print(f"\n✗ {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        print("\nInterrupted.", file=sys.stderr)
        return 130


def _run_chunked(client: ScribeClient, args) -> str:
    """Local VAD -> chunked HTTP upload. Steps kept separate: start, upload, end."""
    # Step 1: start the session.
    session = client.create_session(
        upload_type="chunked",
        communication_protocol="http",
        templates=_templates(args.templates),
    )
    print(f"✓ Session created: {session.session_id}")

    # Step 2: produce audio (file or mic), VAD it in the SDK, upload chunks.
    #         end_session=False keeps end() as its own explicit step below.
    if args.file:
        n = client.upload_audio_file(
            session.session_id, args.file, end_session=False
        )
    elif args.record:
        from .audio import record_pcm

        print(f"🎙  Recording {args.record}s …")
        pcm = record_pcm(args.record)
        n = client.upload_pcm(session.session_id, pcm, end_session=False)
    else:
        raise SystemExit("chunked mode needs --file PATH or --record SECONDS")
    print(f"✓ VAD'd locally and uploaded {n} chunk(s).")

    # Step 3: end the session.
    client.end_session(session.session_id, audio_files_sent=n)
    print("✓ Session ended.")
    return session.session_id


def _run_stream(client: ScribeClient, args) -> str:
    """Live mic -> WebSocket streaming. Steps: open, send frames, stop."""
    from .audio import microphone_frames

    if not args.record:
        raise SystemExit("--mode stream requires --record SECONDS")

    # Step 1: open the stream session (WebSocket).
    stream = client.open_stream()
    print(f"✓ Stream open (session {stream.session_id}); recording {args.record}s …")
    try:
        # Step 2: send raw PCM frames from the mic as they arrive.
        for frame in microphone_frames(max_seconds=args.record):
            stream.send_audio(frame)
    finally:
        # Step 3: stop the stream (finalizes the session server-side).
        stream.stop()
    print("✓ Stream stopped.")
    return stream.session_id


def _print_result(result) -> None:
    print(f"\n✓ Final status: {result.status}")
    if result.transcript:
        print(f"\n--- transcript ---\n{result.transcript}")
    for tid, tr in (result.templates or {}).items():
        print(f"\n--- template: {tid} ({tr.status}) ---")
        print(tr.data if tr.data is not None else tr.error)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
