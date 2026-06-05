# CLI example

The SDK installs a `scribe` command (entry point `scribe_sdk.cli:main`). It
captures audio from a file or the microphone, VADs it **locally**, and either
uploads the speech chunks over HTTP or streams raw PCM live over a WebSocket.
There is no whole-file/server-side-VAD upload.

```bash
# chunked upload of an existing file (client-side silero VAD -> chunk_0, chunk_1, …)
uv run scribe --mode chunked --file visit.wav

# record 30s from the mic, VAD locally, then chunked upload
uv run scribe --mode chunked --record 30

# live streaming for 30s over WebSocket
uv run scribe --mode stream --record 30

# override templates for one run
uv run scribe --mode chunked --file visit.wav --templates soap,medications
```

Each run keeps the steps separated — start session → send audio → end session →
poll results (1s interval).

Config comes from `--config PATH`, `SCRIBE_CONFIG`, or `scribe.config.json` in
the working directory (plus `SCRIBE_*` env / `.env`). Mic and VAD options need
the `[audio]` extra: `uv sync --extra audio`.
