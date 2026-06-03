# scribe-python-sdk

Python SDK for the **MedScribeAlliance Protocol v0.1** — the scribe protocol exposed by
Voice2Rx / eka.care. It turns medical audio (consultations, dictation) into structured
template results (SOAP notes, medication lists, etc.).

Use it from your server, a CLI, or behind a browser relay to:

- **create sessions** with your configured default templates (or per-call overrides),
- **upload audio two ways** — *chunked* (client-side VAD → `chunk_0`, `chunk_1`, …) or
  *streaming* (real-time WebSocket), plus a simple *single-file* mode,
- **poll for results**.

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

A `scribe.config.json` (or `.yaml`):

```json
{
  "base_url": "https://api.eka.care/voice",
  "auth_base_url": "https://api.eka.care",
  "client_id": "YOUR_CLIENT_ID",
  "client_secret": "YOUR_CLIENT_SECRET",
  "b_id": "YOUR_BUSINESS_ID",
  "default_templates": ["soap", "medications"],
  "default_model": "lite",
  "default_language_hint": ["en"],
  "transcript_language": "en"
}
```

Or via environment (`.env` is auto-loaded):

```bash
SCRIBE_CLIENT_ID=...
SCRIBE_CLIENT_SECRET=...
SCRIBE_B_ID=...
SCRIBE_DEFAULT_TEMPLATES=soap,medications
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

### Single-file upload (sync)

```python
from scribe_sdk import ScribeClient

with ScribeClient(config_path="scribe.config.json") as client:
    s = client.create_session(upload_type="single", communication_protocol="http")
    client.upload_file(s.session_id, "visit.wav")        # backend VADs it, ends session
    result = client.wait_for_results(s.session_id)
    print(result.status, result.templates)
```

### Chunked upload (async, client-side VAD)

```python
from scribe_sdk import AsyncScribeClient
from scribe_sdk.audio import vad_chunks_from_file   # requires [audio]

async with AsyncScribeClient(config_path="scribe.config.json") as client:
    s = await client.create_session(upload_type="chunked", communication_protocol="http")
    n = await client.upload_chunks(s.session_id, vad_chunks_from_file("visit.wav"))
    result = await client.wait_for_results(s.session_id)
```

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

- `examples/cli/` — interactive CLI: `scribe --mode chunked|stream`.
- `examples/browser_relay/` — JS frontend (captures mic) + FastAPI relay server that uses
  the SDK. Keeps `client_id`/`secret` server-side.
- `examples/server_side/` — minimal "call the SDK from your backend" script.

---

## Upload modes at a glance

| Mode | When | How |
|---|---|---|
| **single** | short, pre-recorded clips | one POST; backend does VAD chunking |
| **chunked** | long recordings, reliable delivery | client VADs → `chunk_0..N` POSTs → `end` |
| **streaming** | live/real-time | WebSocket frames → `stop` |

All three finish with `wait_for_results(session_id)`.

---

## Known seam: streaming result retrieval

Streaming reuses the telephony `/v1/stream/*` endpoints, which create the backend session
*without* protocol auth (business id in the body). Reading those results back through the
authenticated `/v1/sessions/{id}` path may require backend wiring to associate the streamed
`session_id` with the caller. The SDK exposes `stream.session_id` so you can poll; if your
backend doesn't yet resolve streamed sessions under protocol auth, treat this as a backend
follow-up. The chunked and single paths have no such seam.

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
