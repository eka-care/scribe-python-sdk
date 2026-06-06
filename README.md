# scribe-python-sdk

Turn medical audio into structured notes (SOAP, medication lists, EMR templates) in a few lines of Python.

It talks to the **MedScribeAlliance Protocol v0.1** scribe backend (Voice2Rx / eka.care) for you: create a session, send audio, get results. Async-first, with a plain synchronous client for scripts.

```python
from scribe_sdk import ScribeClient

with ScribeClient() as client:
    s = client.create_session()
    client.upload_audio_file(s.session_id, "visit.wav")
    result = client.wait_for_results(s.session_id)
    print(result.templates)
```

That's a full transcription-to-notes round trip. Everything below is detail.

---

## Integrate in 60 seconds

**1. Install**

```bash
uv add "scribe-python-sdk[audio]"     # [audio] adds mic capture + file decoding
# or: pip install "scribe-python-sdk[audio]"
```

**2. Set credentials** — create a `.env` file next to your script:

```bash
SCRIBE_ENV=prod                                  # "dev" -> api.dev.eka.care
SCRIBE_CLIENT_ID=your-client-id
SCRIBE_CLIENT_SECRET=your-client-secret
SCRIBE_DEFAULT_TEMPLATES=eka_emr_template,clinical_notes_template
```

> Get your `client_id` / `client_secret` from eka.care. They live **only** in the
> environment — the SDK refuses to read them from a config file.

**3. Run** the snippet at the top of this README. Done — no other setup.

The SDK auto-loads `.env`, logs in, picks the right host from `SCRIBE_ENV`, and uses
`SCRIBE_DEFAULT_TEMPLATES` so you don't repeat them on every call.

---

## The three ways to send audio

Pick one — they all finish the same way: `wait_for_results(session_id)`.

### 1. A file (simplest)

```python
with ScribeClient() as client:
    s = client.create_session()
    client.upload_audio_file(s.session_id, "visit.wav")   # decode + VAD locally, upload
    result = client.wait_for_results(s.session_id)
    print(result.status, result.templates)
```

Accepts `.wav/.mp3/.m4a/.webm/.ogg` (a path or raw `bytes`).

### 2. Raw PCM you already captured

```python
with ScribeClient() as client:
    s = client.create_session()
    client.upload_pcm(s.session_id, pcm_bytes, sample_rate=16000)
    result = client.wait_for_results(s.session_id)
```

### 3. Live streaming over WebSocket (real-time)

```python
from scribe_sdk import AsyncScribeClient

async with AsyncScribeClient() as client:
    async with await client.open_stream() as stream:
        async for frame in mic_frames():       # raw 16-bit LE PCM, mono, 16 kHz
            await stream.send_audio(frame)
        await stream.stop()                    # flush + end the session
    result = await client.wait_for_results(stream.session_id)
```

> Streaming is async-only. Everything else has both a sync (`ScribeClient`) and
> async (`AsyncScribeClient`) flavor with identical method names — add `await`.

That's the whole surface. `create_session` → send audio → `wait_for_results`.

---

## Reading the result

`wait_for_results()` returns a `SessionStatusResponse`:

```python
result = client.wait_for_results(s.session_id)

result.status        # "completed" | "partial" | "failed" | ...
result.transcript    # full transcript text
result.templates     # list of {template_id: {...}} — one entry per generated document
```

`templates` is a **list** of single-key dicts (one template can yield several documents):

```python
for doc in result.templates:
    for template_id, payload in doc.items():
        print(template_id, payload["status"], payload.get("data"))
```

---

## Configuration

Everything has a sensible default. The only thing you *must* provide is credentials.

Resolution order (highest wins): **explicit kwargs › environment / `.env` › config file › defaults**.

### Environment variables

| Variable | Purpose |
|---|---|
| `SCRIBE_CLIENT_ID` / `SCRIBE_CLIENT_SECRET` | credentials (**env-only**) |
| `SCRIBE_ENV` | `prod` (default, `api.eka.care`) or `dev` (`api.dev.eka.care`) |
| `SCRIBE_DEFAULT_TEMPLATES` | comma-separated templates used when you don't pass `templates=` |
| `SCRIBE_DEFAULT_MODEL` | `lite` (default) or `pro` |
| `SCRIBE_BASE_URL` / `SCRIBE_AUTH_BASE_URL` | override hosts directly (wins over `SCRIBE_ENV`) |

### Optional config file

Put non-secret defaults in `scribe.config.json` (or `.yaml`) in your working dir — it's
picked up automatically:

```json
{
  "default_templates": ["eka_emr_template", "clinical_notes_template"],
  "default_model": "pro",
  "transcript_language": "en"
}
```

### Or pass it inline

```python
client = ScribeClient(
    env="dev",
    default_templates=["soap"],
    client_id="...",          # or leave to env
    client_secret="...",
)
```

### Per-call overrides

`create_session()` takes the same options when you want to override config for one session:

```python
s = client.create_session(
    templates=["soap"],
    model="pro",
    session_mode="consultation",        # or "dictation" (default)
    language_hint=["en", "hi"],
    patient_details={"name": "..."},
)
```

---

## Authentication, briefly

- **Production:** the SDK exchanges `client_id` + `client_secret` for a Bearer token at
  `{auth_base_url}/connect-auth/v1/account/login` automatically. You never touch tokens.
- **Local backend (no gateway):** pass `jwt_payload={...}` to send the `jwt-payload`
  header directly and skip login.

Your business id (`b_id`) is derived from your token — you never configure it.

---

## Examples

Runnable, in `examples/`:

- `examples/server_side/file_upload.py` — call the SDK from your backend (start → upload → poll).
- `examples/fastapi_app/` — a FastAPI server + browser UI (record / upload / live-stream / poll).
  Credentials stay server-side; the browser talks only to your server.
- `examples/cli/` — the bundled `scribe` CLI (`--mode chunked|stream`).

---

## How it works

Voice-activity detection always runs **client-side**: `upload_audio_file` / `upload_pcm` /
streaming decode and VAD on your machine and send only speech-bounded chunks (or raw PCM
frames) — the backend never receives an un-VADded whole file. Chunked and streaming both go
through the same protocol session API (`POST /v1/sessions`) and read results back through the
same `GET /v1/sessions/{id}`, so they behave identically. For streaming, `stop()` flushes the
last chunk and calls `end` — the single trigger that commits the session and starts processing.

---

## Development

```bash
uv sync --extra dev
uv run pytest          # mocked HTTP, no backend needed
uv run ruff check .
uv run mypy src
```

## License

MIT
