# Examples

All examples read config from `scribe.config.json` / `SCRIBE_*` env / `.env`
(copy `scribe.config.example.json` and fill in your credentials first).

Voice activity detection always runs **client-side** — these examples decode and
VAD audio locally and upload only speech chunks (or stream raw PCM). There is no
whole-file ("single") upload.

| Example | What it shows | Extras needed |
|---|---|---|
| [`cli/`](cli/) | The bundled `scribe` CLI (`--mode chunked\|stream`) — mic/file VAD + WebSocket | `audio` |
| [`server_side/file_upload.py`](server_side/file_upload.py) | Async API: start → VAD file locally → upload chunks → end → poll | `audio` |
| [`fastapi_app/`](fastapi_app/) | FastAPI server + minimal UI: start session, upload file, mic record, live stream, end, poll | `server`, `audio` |

```bash
uv sync --extra dev --extra audio --extra server
```
