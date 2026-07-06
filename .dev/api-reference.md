# API Reference

All endpoints are served by `backend/app.py` directly or via routers included at the bottom of `backend/app.py`. Request/response bodies are JSON unless noted.

## Transcription (in `backend/app.py`)

| Method | Path | Purpose | Body / Params |
|---|---|---|---|
| POST | `/transcribe/url` | Start transcription from a remote URL (yt-dlp) | `TranscriptionRequest` |
| POST | `/transcribe/local` | Start transcription from a server-local file path | `TranscriptionRequest` with `file_path` |
| POST | `/transcribe/upload` | Start transcription from an uploaded file | multipart form (see `app.py:564-622`) |
| POST | `/transcribe/batch/urls` | Queue up to 20 URLs | `BatchUrlRequest` |
| POST | `/transcribe/batch/upload` | Queue up to 20 uploaded files | multipart `files[]` + form fields |
| POST | `/transcribe/batch/folder-upload` | Create a folder and queue all uploaded files | multipart `files[]` + `folder_name` |
| POST | `/api/llm/models` | Proxy to OpenAI-compatible `/v1/models` | `LlmModelsRequest` |
| GET  | `/` | Serve `frontend-react/dist/index.html` | — |
| GET  | `/editor/{task_id}` | SPA entry for editor (client-side routing) | — |
| GET  | `/subtitle-editor/{task_id}` | Alias of `/editor/{task_id}` | — |

All successful transcription POSTs return `{"task_id": "<uuid>"}` (or `{"batch_id", "task_ids": [...]}` for batch routes).

## Tasks (`backend/services/task_api.py`, prefix `/tasks`)

| Method | Path | Purpose |
|---|---|---|
| GET    | `/tasks` | All tasks as `{id: Task}` |
| GET    | `/tasks/{task_id}` | Single task snapshot |
| GET    | `/tasks/{task_id}/stream` | SSE stream; emits JSON snapshot on change, closes on terminal status |
| DELETE | `/tasks/{task_id}` | Cancel or delete a task |
| DELETE | `/tasks/failed` | Bulk-delete all failed tasks |
| GET    | `/tasks/batch/{batch_id}` | Aggregate status for a batch |

## Subtitles (`backend/services/subtitle_api.py`, prefix `/api/subtitles`)

| Method | Path | Purpose |
|---|---|---|
| GET    | `/api/subtitles/formats` | Supported export formats |
| HEAD   | `/api/subtitles/{task_id}` | Existence probe |
| GET    | `/api/subtitles/{task_id}` | Load `SubtitleCollection` (prefers `<id>_updated.json`) |
| PUT    | `/api/subtitles/{task_id}` | Save `SubtitleCollection` |
| GET    | `/api/subtitles/{task_id}/download/{format}` | Export SRT/VTT/TXT/JSON/ASS/SSA |
| POST   | `/api/subtitles/{task_id}/search` | Search within task subtitles |
| GET    | `/api/subtitles/{task_id}/metadata` | Metadata only |
| GET    | `/api/subtitles/{task_id}/statistics` | Subtitle count, duration, WPM |
| POST   | `/api/subtitles/{task_id}/retranscribe` | Queue a slice re-transcription |
| GET    | `/api/subtitles/retranscribe/{id}` | Retranscribe job status |
| GET    | `/api/subtitles/retranscribe` | All retranscribe jobs |
| POST   | `/api/subtitles/{task_id}/retranscribe/{id}/apply` | Apply result to subtitle collection |
| DELETE | `/api/subtitles/retranscribe/{id}` | Cancel / delete retranscribe job |
| POST   | `/api/subtitles/{task_id}/burn-in` | Start burn-in job |
| GET    | `/api/subtitles/burn-in/{burn_id}` | Burn-in status |
| GET    | `/api/subtitles/burn-in/{burn_id}/download` | Download burned MP4 |
| POST   | `/api/subtitles/enhance` | SSE: LLM-enhance or translate subtitles |
| POST   | `/api/subtitles/{task_id}/summarize` | Generate summary + chapter notes |
| GET    | `/api/subtitles/{task_id}/notes` | Retrieve previously saved notes |

## Folders (`backend/services/folder_api.py`, prefix `/api/folders`)

| Method | Path | Purpose |
|---|---|---|
| GET    | `/api/folders` | List all folders with task counts |
| POST   | `/api/folders` | Create folder (optional `parent_id`) |
| PUT    | `/api/folders/{folder_id}` | Rename |
| DELETE | `/api/folders/{folder_id}` | Delete; contained tasks become unassigned |
| POST   | `/api/folders/{folder_id}/tasks` | Move tasks into folder |
| DELETE | `/api/folders/{folder_id}/tasks` | Remove tasks from folder |
| PUT    | `/api/folders/reorder` | Reorder folders |
| PUT    | `/api/folders/{folder_id}/tasks/reorder` | Reorder tasks within folder |

## System (`backend/services/system_api.py`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/gpu-info` | `check_gpu()` payload |
| GET | `/system/directories` | Drive/root listing (Windows uses `win32api`) |
| GET | `/system/subdirectories?path=...` | Subdirs under a path |

## Download (`backend/services/download_api.py`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/download/{task_id}/{file_type}` | Stream result file with `Accept-Ranges: bytes`. `file_type=video` also falls through to `source_file_path` while job is still running. |

## Request / Response Shapes

Primary Pydantic models live in `backend/models.py` and the top of `backend/app.py`:

- `TranscriptionRequest`, `BatchUrlRequest`, `LlmModelsRequest` — `backend/app.py`
- `Subtitle`, `Word`, `SubtitleCollection`, `SubtitleMetadata`, `VideoInfo`, `RetranscribeRequest`, `RetranscribeTask`, `SubtitleExportRequest`, `SubtitleSearchRequest`, `SubtitleSearchResult` — `backend/models.py`

Canonical TypeScript mirrors live in `frontend-react/src/types/api.ts`. Keep both sides in sync when changing shapes.

## How to Add a New Endpoint

1. Choose (or create) a file under `backend/services/`. Convention: one router per domain, `router = APIRouter(prefix="/api/<domain>", tags=["<domain>"])`.
2. At the top of the file, define inline Pydantic models for request / response bodies. Follow the style of `folder_api.py:CreateFolderRequest`.
3. Declare shared-state globals (`_task_registry`, `_task_store`, etc.) at module level and expose a `set_*` injector function. Add a `get_*` that raises `RuntimeError` if still `None`.
4. Write the handler:

```python
@router.post("/{folder_id}/tasks")
async def move_tasks_to_folder(folder_id: str, req: MoveTasksRequest):
    if not req.task_ids:
        raise HTTPException(status_code=400, detail=_NEED_TASK_IDS)
    tasks = _task_registry
    ...
    return {"message": f"已將 {len(req.task_ids)} 個任務移至資料夾 {folder_id}"}
```

5. Register the router and wire state in `backend/app.py` near the bottom:

```python
app.include_router(my_new_router)
set_my_new_registry(tasks)
```

6. Add the frontend bindings:
   - Add the TypeScript interface to `frontend-react/src/types/api.ts`.
   - Add the method to `frontend-react/src/api/client.ts`.
   - If polled over time, create a hook in `frontend-react/src/hooks/use-<name>.ts`.

7. Add a test:

```python
# tests/test_<module>_api_routes.py
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.services.my_new_api import router, set_my_new_registry

def test_my_new_endpoint():
    tasks = {...}
    set_my_new_registry(tasks)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    r = client.post("/api/my/path", json={...})
    assert r.status_code == 200
```

8. Run `python -m flake8 tests backend/shared backend/services backend/models.py backend/task_persistence.py && python -m pytest tests/ -q`.

## Streaming Endpoints

Two endpoints stream beyond single-shot JSON:

- `GET /tasks/{task_id}/stream` — Server-Sent Events; consumed by `frontend-react/src/hooks/use-task-stream.ts` via `EventSource`. Events are unnamed data frames plus a named `deleted` event when the task is removed.
- `POST /api/subtitles/enhance` — SSE with `data: <json>` frames; consumed by the async generator `api.enhanceSubtitlesStream` in `frontend-react/src/api/client.ts`.

Use the same patterns (StreamingResponse + `text/event-stream`) when adding new streams.
