# scribe-python-sdk

Python SDK for the **MedScribeAlliance Protocol v0.1** — the scribe protocol exposed by
Voice2Rx / eka.care. It turns medical audio (consultations, dictation) into structured
template results (SOAP notes, medication lists, etc.).

Use it from your server, a CLI, or behind a FastAPI relay to:

- **create sessions** with your configured default templates (or per-call overrides),
- **send audio two ways** — *chunked* (client-side VAD → `chunk_0`, `chunk_1`, …) or
  *streaming* (real-time WebSocket),
- **poll for results**.

**Voice activity detection always runs client-side.** The SDK decodes and VADs audio
on your machine and POSTs only speech-bounded chunks (or streams raw PCM) — the scribe
backend never receives an un-VADded whole file. There is deliberately no single/whole-file
upload.

Async-first (`httpx` + `websockets`) with a synchronous facade for scripts and the CLI.

---

## Install (uv)

This project uses [uv](https://docs.astral.sh/uv/).

```bash
# core SDK (pure-Python: sessions, upload, streaming, results)
uv add scribe-python-sdk

# with mic capture + silero VAD chunking (native libs: portaudio, onnxruntime)
uv add "scribe-python-sdk[audio]"
```

Working inside this repo:

```bash
uv sync --extra dev            # core + dev tooling
uv sync --extra dev --extra audio --extra server   # everything
```

---

## Configure

Configuration resolves with precedence **kwargs > env vars > config file > defaults**.

> **Credentials are env-only.** `client_id` and `client_secret` are **never** read
> from a config file — loading a file that contains either key raises a `ConfigError`.
> Supply them through the environment (or as explicit kwargs). Everything else may live
> in the config file, the environment, or both.

A `scribe.config.json` (or `.yaml`) — note: no credentials here:

```json
{
  "base_url": "https://api.eka.care/voice",
  "auth_base_url": "https://api.eka.care",
  "default_templates": ["soap", "medications"],
  "default_model": "lite",
  "default_language_hint": ["en"],
  "transcript_language": "en"
}
```

Credentials come from the environment (`.env` is auto-loaded):

```bash
SCRIBE_ENV=dev               # "prod" (default) -> api.eka.care, "dev" -> api.dev.eka.care
SCRIBE_CLIENT_ID=...
SCRIBE_CLIENT_SECRET=...
SCRIBE_DEFAULT_TEMPLATES=soap,medications
```

### Dev vs prod

Use `SCRIBE_ENV` (or `env="dev"` kwarg) to switch hosts without typing full URLs:

| `SCRIBE_ENV` | `base_url` | `auth_base_url` |
|---|---|---|
| `prod` (default) | `https://api.eka.care/voice` | `https://api.eka.care` |
| `dev` | `https://api.dev.eka.care/voice` | `https://api.dev.eka.care` |

An explicit `base_url` / `auth_base_url` (env var, kwarg, or config file) always
overrides the preset. For example:

```python
client = AsyncScribeClient(env="dev")                 # or ScribeClient(env="dev")
# or: SCRIBE_ENV=dev in the environment / .env
```

`default_templates` is what `create_session()` uses when you don't pass `templates=` —
so configured clients get the right result templates automatically.

### Authentication

Production: the SDK exchanges `client_id` + `client_secret` at
`{auth_base_url}/connect-auth/v1/account/login` for a Bearer token and sends it to the
public gateway, which validates it and injects the `jwt-payload` header for the backend.

Local/dev against a raw backend (no gateway): set a `jwt_payload` dict in config to send
that header directly and skip login.

---

## Usage

Every flow keeps the steps separated — **start session → send audio → end session →
poll results** (the poller waits 1s between checks).

### File upload with client-side VAD (sync)

```python
from scribe_sdk import ScribeClient   # decode + VAD need the [audio] extra

with ScribeClient(config_path="scribe.config.json") as client:
    s = client.create_session(upload_type="chunked", communication_protocol="http")
    n = client.upload_audio_file(s.session_id, "visit.wav", end_session=False)  # VAD locally
    client.end_session(s.session_id, audio_files_sent=n)
    result = client.wait_for_results(s.session_id)
    print(result.status, result.templates)
```

### File / PCM upload (async)

```python
from scribe_sdk import AsyncScribeClient   # requires [audio]

async with AsyncScribeClient(config_path="scribe.config.json") as client:
    s = await client.create_session(upload_type="chunked", communication_protocol="http")
    # from a file/bytes …
    n = await client.upload_audio_file(s.session_id, "visit.wav", end_session=False)
    # … or from raw 16-bit mono PCM you already captured:
    # n = await client.upload_pcm(s.session_id, pcm_bytes, sample_rate=16000, end_session=False)
    await client.end_session(s.session_id, audio_files_sent=n)
    result = await client.wait_for_results(s.session_id)
```

> Lower-level: pass your own VAD chunk iterator to `upload_chunks(...)` — see
> `scribe_sdk.audio.vad_chunks_from_file` / `vad_chunks_from_pcm`.

### Streaming (async, real-time WebSocket)

```python
async with AsyncScribeClient(config_path="scribe.config.json") as client:
    async with await client.open_stream() as stream:
        async for pcm_frame in mic_frames():        # raw 16-bit LE PCM, mono, 16 kHz
            await stream.send_audio(pcm_frame)
        await stream.stop()
    result = await client.wait_for_results(stream.session_id)
```

---

## Examples

- `examples/cli/` — the bundled `scribe` CLI: `--mode chunked|stream` (mic/file VAD + WS).
- `examples/fastapi_app/` — FastAPI server + minimal UI (start session, upload file, mic
  record, live stream, end, poll). VAD runs in the SDK on the server; keeps
  `client_id`/`secret` server-side.
- `examples/server_side/` — minimal "call the SDK from your backend" script.

---

## Upload modes at a glance

| Mode | When | How |
|---|---|---|
| **chunked** | files & most recordings | client VADs → `chunk_0..N` POSTs → `end` |
| **streaming** | live/real-time | `POST /v1/sessions` (`stream`) → WebSocket raw-PCM frames → `stop` (flush + `end`) |

Both finish with `wait_for_results(session_id)`. VAD is always client-side — there is no
whole-file/server-VAD mode.

---

## Streaming result retrieval — how it ties together

Streaming uses **only** the protocol session API — the same `POST /v1/sessions` create as chunked
upload, with `upload_type="stream"`. The create response returns a `wss://` URL in `upload_url`;
`open_stream()` connects to it. Results are read back through the **same** authenticated
`GET /v1/sessions/{session_id}` path used by chunked upload, because both sides hit the same
`voice2rx_transactions` table keyed by the composite primary key `(session_id, b_id)`.

You **never configure a business id in the SDK** — `b_id` (and `uuid`) come from your token. The
protocol create-session reads them from the jwt-payload the gateway injects from your Bearer token,
so the streamed session is written under the business the gateway authenticated, which is exactly
what `GET /v1/sessions/{session_id}` then looks up. The protocol `GET` applies no extra
`uuid`/owner filter.

Finalize is explicit: `stop()` sends a `stop` frame, waits for the server to flush the last chunk
and close the socket, then calls `POST /v1/sessions/{session_id}/end` to commit and start
processing. (Closing the socket alone does **not** commit a protocol streaming session — the
end call is the single canonical trigger.) So with token auth, streaming and
`wait_for_results(stream.session_id)` work out of the box. While the stream is live the session
reads back as `initialized`/`processing` (non-terminal, so the SDK keeps polling); after `stop()`
the backend commits (`user_status=commit`) and the results become available. Both modes use the
identical key, so they behave the same way.

---

## Development

```bash
uv sync --extra dev
uv run pytest                 # unit tests (mocked HTTP, no backend needed)
uv run ruff check .
uv run mypy src
```

## License

MIT
