# Browser relay example

A browser **can't** run a Python SDK, and you don't want `client_id`/`secret` in
client-side JS. So this example puts a thin **FastAPI relay** in the middle:

```
browser (mic capture, JS)  ──audio──▶  FastAPI relay (Scribe SDK)  ──▶  eka backend
        ▲                                                                   │
        └───────────────── results (polled via relay) ◀─────────────────────┘
```

Two modes in the UI:

1. **Record & upload** — `MediaRecorder` captures a WebM/Opus blob; the browser
   POSTs it to `/api/upload`; the relay does a single upload (backend VADs it).
2. **Live stream** — WebAudio captures PCM16 @ 16 kHz; the browser streams frames
   over a WebSocket to `/api/stream`; the relay forwards them into an SDK
   streaming session.

## Run

```bash
uv sync --extra server --extra audio
# put your credentials in scribe.config.json (kept server-side)
uv run uvicorn examples.browser_relay.server:app --reload
# open http://127.0.0.1:8000
```

> Mic capture requires a secure context. `http://127.0.0.1` is treated as secure
> by browsers; for remote hosts use HTTPS.

## Notes

- The relay holds one shared `AsyncScribeClient` for the process (see `lifespan`).
- Streaming result retrieval depends on the backend resolving streamed
  `session_id`s under your auth — see the "Known seam" note in the top-level README.
