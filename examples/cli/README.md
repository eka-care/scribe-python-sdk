# CLI example

The SDK installs a `scribe` command (entry point `scribe_sdk.cli:main`).

```bash
# chunked upload of an existing file (client-side silero VAD -> chunk_0, chunk_1, …)
uv run scribe --mode chunked --file visit.wav

# record 30s from the mic, then chunked upload
uv run scribe --mode chunked --record 30

# single-file mode (server-side VAD)
uv run scribe --mode single --file visit.wav

# live streaming for 30s over WebSocket
uv run scribe --mode stream --record 30

# override templates for one run
uv run scribe --mode chunked --file visit.wav --templates soap,medications
```

Config comes from `--config PATH`, `SCRIBE_CONFIG`, or `scribe.config.json` in
the working directory (plus `SCRIBE_*` env / `.env`). Mic and VAD options need
the `[audio]` extra: `uv sync --extra audio`.
