"""`scribe` command-line interface.

    scribe --mode chunked --file visit.wav
    scribe --mode chunked --record 30
    scribe --mode stream  --record 30

Reads config from --config / SCRIBE_CONFIG / scribe.config.json (+ env). The
mic options require the [audio] extra.
"""

from __future__ import annotations

import argparse
import sys

from . import ScribeClient, __version__
from .errors import ScribeError


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="scribe", description="Scribe SDK CLI")
    p.add_argument("--version", action="version", version=f"scribe-python-sdk {__version__}")
    p.add_argument(
        "--mode",
        choices=["chunked", "stream", "single"],
        default="chunked",
        help="Upload mode (default: chunked)",
    )
    p.add_argument("--config", help="Path to scribe.config.json/.yaml")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--file", help="Audio file to upload (chunked/single modes)")
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
                session_id = _run_upload(client, args)

            print(f"\n⏳ Waiting for results (session {session_id}) …")
            result = client.wait_for_results(
                session_id,
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


def _run_upload(client: ScribeClient, args) -> str:
    upload_type = "single" if args.mode == "single" else "chunked"
    session = client.create_session(
        upload_type=upload_type,
        communication_protocol="http",
        templates=_templates(args.templates),
    )
    print(f"✓ Session created: {session.session_id}")

    pcm_source = _get_audio(args)

    if args.mode == "single":
        client.upload_file(session.session_id, pcm_source["wav"])
        print("✓ Uploaded single file; session ended.")
    else:
        from .audio import vad_chunks_from_pcm

        index = 0
        for chunk in vad_chunks_from_pcm(pcm_source["pcm"], sample_rate=pcm_source["sr"]):
            client.upload_chunk(session.session_id, index, chunk, ext="wav")
            print(f"   ↑ chunk_{index}.wav ({len(chunk)} bytes)")
            index += 1
        client.end_session(session.session_id, audio_files_sent=index)
        print(f"✓ Uploaded {index} chunk(s); session ended.")
    return session.session_id


def _run_stream(client: ScribeClient, args) -> str:
    from .audio import microphone_frames

    if not args.record:
        raise SystemExit("--mode stream requires --record SECONDS")

    stream = client.open_stream()
    print(f"✓ Stream open (session {stream.session_id}); recording {args.record}s …")
    try:
        for frame in microphone_frames(max_seconds=args.record):
            stream.send_audio(frame)
    finally:
        stream.stop()
    print("✓ Stream stopped.")
    return stream.session_id


def _get_audio(args) -> dict:
    from .audio import decode_to_pcm16, pcm16_to_wav, record_pcm

    if args.file:
        pcm, sr = decode_to_pcm16(args.file)
    elif args.record:
        print(f"🎙  Recording {args.record}s …")
        pcm = record_pcm(args.record)
        sr = 16000
    else:
        raise SystemExit("Provide --file PATH or --record SECONDS")
    return {"pcm": pcm, "sr": sr, "wav": pcm16_to_wav(pcm, sr)}


def _print_result(result) -> None:
    print(f"\n✓ Final status: {result.status}")
    if result.transcript:
        print(f"\n--- transcript ---\n{result.transcript}")
    for tid, tr in (result.templates or {}).items():
        print(f"\n--- template: {tid} ({tr.status}) ---")
        print(tr.data if tr.data is not None else tr.error)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
