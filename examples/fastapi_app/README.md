# FastAPI app — client-side VAD

A browser **can't** run a Python SDK, and you don't want `client_id`/`secret` in
client-side JS. So this example puts a **FastAPI server** in the middle that uses
the Scribe SDK. The important bit: **voice activity detection runs in the SDK on
this server**, never on the scribe backend. Uploaded files are decoded + VAD'd
locally and only speech-bounded chunks are sent.

```
browser (file / mic, JS)  ──audio──▶  FastAPI + Scribe SDK  ──VAD here──▶  scribe backend
        ▲                              (client-side VAD)         (chunks only)   │
        └──────────────── results (polled every 1s via the relay) ◀─────────────┘
```

Every flow keeps the protocol steps **separated**:

```
start session  →  send audio  →  end session  →  poll results (1s)
```

## UI options

1. **Start session** — `POST /api/sessions` creates a `chunked` session.
2. **Upload an audio file** — `POST /api/sessions/{id}/audio`; the SDK decodes
   (PyAV) and VADs (silero) the file, then uploads the chunks. Repeatable —
   upload several files into the same session.
3. **Record from the mic** — captures a WebM blob in the browser and posts it to
   the same `/audio` endpoint (also VAD'd server-side).
4. **End session** — `POST /api/sessions/{id}/end`, then the browser polls
   `GET /api/sessions/{id}/results` every second until it's done.
5. **Live stream** — streams raw PCM16 @ 16 kHz frames over a WebSocket into the
   SDK's streaming session, then polls for results.

## Run

```bash
uv sync --extra server --extra audio
# put your credentials in scribe.config.json (kept server-side)
uv run uvicorn examples.fastapi_app.server:app --reload
# open http://127.0.0.1:8000
```

> Mic capture requires a secure context. `http://127.0.0.1` is treated as secure
> by browsers; for remote hosts use HTTPS.

## Notes

- The server holds one shared `AsyncScribeClient` for the process (see `lifespan`)
  and tracks each session's chunk count so `/audio` can be called repeatedly and
  `/end` reports the right `audio_files_sent` total.
- `upload_audio_file` does the decode + VAD off the event loop (`anyio.to_thread`),
  so concurrent requests aren't blocked.
- Streaming result retrieval depends on the backend resolving streamed
  `session_id`s under your auth — see the "Streaming result retrieval" note in the
  top-level README.
