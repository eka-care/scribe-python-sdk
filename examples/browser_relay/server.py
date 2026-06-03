"""Browser relay server.

A small FastAPI app that uses the Scribe SDK on the server side so the browser
never sees your client_id/secret. The static frontend (static/) captures the
mic and talks to this relay; the relay talks to the eka backend.

Two paths are demonstrated:
- POST /api/upload      : browser posts a recorded blob -> SDK single upload
- WS   /api/stream      : browser streams PCM16 frames -> SDK live streaming
- GET  /api/results/... : poll session results

Run:
    uv sync --extra server --extra audio
    uv run uvicorn examples.browser_relay.server:app --reload
    # open http://127.0.0.1:8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from scribe_sdk import AsyncScribeClient

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One shared SDK client for the process. Reads config from
    # scribe.config.json / SCRIBE_* env (kept server-side).
    app.state.scribe = AsyncScribeClient()
    yield
    await app.state.scribe.aclose()


app = FastAPI(title="Scribe browser relay", lifespan=lifespan)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/upload")
async def upload(file: UploadFile) -> JSONResponse:
    """Single-file upload: browser records a blob, we relay it to the backend."""
    client: AsyncScribeClient = app.state.scribe
    data = await file.read()
    session = await client.create_session(
        upload_type="single", communication_protocol="http"
    )
    await client.upload_file(
        session.session_id,
        data,
        filename=file.filename or "recording.webm",
        content_type=file.content_type,
    )
    return JSONResponse({"session_id": session.session_id})


@app.get("/api/results/{session_id}")
async def results(session_id: str) -> JSONResponse:
    """Poll once; returns current status + any template results."""
    client: AsyncScribeClient = app.state.scribe
    status = await client.sessions.get(session_id)
    return JSONResponse(status.model_dump(exclude_none=True))


@app.websocket("/api/stream")
async def stream(ws: WebSocket) -> None:
    """Relay live PCM16 frames from the browser into an SDK stream session."""
    await ws.accept()
    client: AsyncScribeClient = app.state.scribe
    stream_session = await client.open_stream()
    await ws.send_json({"event": "ready", "session_id": stream_session.session_id})
    try:
        while True:
            message = await ws.receive()
            if message.get("bytes") is not None:
                await stream_session.send_audio(message["bytes"])
            elif message.get("text") == "stop":
                break
    except WebSocketDisconnect:
        pass
    finally:
        await stream_session.stop()
    try:
        await ws.send_json({"event": "stopped", "session_id": stream_session.session_id})
        await ws.close()
    except RuntimeError:
        pass


# Serve the rest of the static assets (app.js, etc.).
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
