"""FastAPI app demonstrating the Scribe SDK with **client-side VAD**.

A browser can't run a Python SDK, and you don't want `client_id`/`secret` in
client-side JS — so this server sits in the middle and uses the SDK. The key
point: voice activity detection runs **here** (in the SDK, on your server), not
on the scribe backend. Uploaded files are VAD'd locally and only speech-bounded
chunks are POSTed. There is no single/whole-file upload.

Every flow keeps the protocol steps separated:
    start session  ->  send audio  ->  end session  ->  poll results (1s)

Endpoints:
    POST /api/sessions                  start a chunked session
    POST /api/sessions/{sid}/audio      upload one file -> SDK VADs it -> chunks
    POST /api/sessions/{sid}/end        end the session
    GET  /api/sessions/{sid}/results    poll status + template results
    WS   /api/stream                    live mic PCM16 -> SDK streaming session

Run:
    uv sync --extra server --extra audio
    # put your credentials in scribe.config.json (kept server-side)
    uv run uvicorn examples.fastapi_app.server:app --reload
    # open http://127.0.0.1:8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from scribe_sdk import AsyncScribeClient

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.scribe = AsyncScribeClient()
    # session_id -> chunks uploaded so far (lets /audio be called repeatedly and
    # /end report the right audio_files_sent total).
    app.state.chunk_counts = {}
    yield
    await app.state.scribe.aclose()


app = FastAPI(title="Scribe SDK — client-side VAD demo", lifespan=lifespan)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/sessions")
async def start_session() -> JSONResponse:
    """Step 1 — start a chunked session."""
    client: AsyncScribeClient = app.state.scribe
    session = await client.create_session(
        upload_type="chunked", communication_protocol="http"
    )
    app.state.chunk_counts[session.session_id] = 0
    return JSONResponse({"session_id": session.session_id})


@app.post("/api/sessions/{session_id}/audio")
async def upload_audio(session_id: str, file: UploadFile) -> JSONResponse:
    """Step 2 — VAD one uploaded file in the SDK and upload its speech chunks.

    Can be called repeatedly to add more audio to the same session before ending.
    """
    client: AsyncScribeClient = app.state.scribe
    if session_id not in app.state.chunk_counts:
        raise HTTPException(status_code=404, detail="Unknown session (start one first).")

    data = await file.read()
    start_index = app.state.chunk_counts[session_id]
    # upload_audio_file decodes (PyAV) + VADs (silero) locally, then POSTs the
    # speech chunks as chunk_<start_index>, chunk_<start_index+1>, …
    uploaded = await client.upload_audio_file(
        session_id, data, start_index=start_index, end_session=False
    )
    app.state.chunk_counts[session_id] += uploaded
    return JSONResponse(
        {"chunks_uploaded": uploaded, "total_chunks": app.state.chunk_counts[session_id]}
    )


@app.post("/api/sessions/{session_id}/end")
async def end_session(session_id: str) -> JSONResponse:
    """Step 3 — end the session; the backend commits and starts processing."""
    client: AsyncScribeClient = app.state.scribe
    total = app.state.chunk_counts.pop(session_id, 0)
    await client.end_session(session_id, audio_files_sent=total)
    return JSONResponse({"session_id": session_id, "audio_files_sent": total})


@app.get("/api/sessions/{session_id}/results")
async def results(session_id: str) -> JSONResponse:
    """Step 4 — poll once; the browser repeats this every 1s until terminal."""
    client: AsyncScribeClient = app.state.scribe
    status = await client.sessions.get(session_id)
    return JSONResponse(status.model_dump(exclude_none=True))

# live streaming endpoint — the browser sends raw PCM16 frames over a WebSocket, and the server 
# proxies them into an SDK stream session. Results are sent back over
# the same WS as JSON messages. This keeps the streaming protocol separate from the chunked upload 
# flow and lets us use
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

# server the rest of the static assets (app.js, etc.).
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
