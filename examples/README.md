# Examples

All examples read config from `scribe.config.json` / `SCRIBE_*` env / `.env`
(copy `scribe.config.example.json` and fill in your credentials first).

| Example | What it shows | Extras needed |
|---|---|---|
| [`cli/`](cli/) | The bundled `scribe` CLI (`--mode chunked\|stream\|single`) | `audio` (for mic/VAD) |
| [`server_side/single_upload.py`](server_side/single_upload.py) | Sync API, single-file upload | — |
| [`server_side/chunked_upload.py`](server_side/chunked_upload.py) | Async API, client-side silero VAD chunking | `audio` |
| [`browser_relay/`](browser_relay/) | JS frontend + FastAPI relay using the SDK | `server`, `audio` |

```bash
uv sync --extra dev --extra audio --extra server
```
