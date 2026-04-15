# API Reference

## Route Overview

All routes are defined in `backend/app.py` (direct) or via `APIRouter` in `backend/services/`.

### Transcription Endpoints (app.py)

| Method | Path | Description |
|---|---|---|
| `POST` | `/transcribe/url` | Create transcription from URL |
| `POST` | `/transcribe/local` | Create transcription from local file path |
| `POST` | `/transcribe/upload` | Create transcription from uploaded file (multipart) |
| `POST` | `/transcribe/batch/urls` | Batch URL transcription |
| `POST` | `/transcribe/batch/upload` | Batch file upload transcription |
| `POST` | `/api/llm/models` | Proxy LLM model listing |

### Task Endpoints (services/task_api.py)

| Method | Path | Description |
|---|---|---|
| `GET` | `/tasks` | List all tasks |
| `GET` | `/tasks/{task_id}` | Get single task status |
| `GET` | `/tasks/{task_id}/stream` | SSE real-time task progress |
| `DELETE` | `/tasks/{task_id}` | Cancel/delete task |
| `GET` | `/tasks/batch/{batch_id}` | Batch status summary |

### Subtitle Endpoints (services/subtitle_api.py, prefix: `/api/subtitles`)

| Method | Path | Description |
|---|---|---|
| `GET` | `/{task_id}` | Get subtitle collection |
| `HEAD` | `/{task_id}` | Check subtitle availability |
| `PUT` | `/{task_id}` | Update subtitle collection |
| `GET` | `/{task_id}/download/{format}` | Download subtitles (srt/vtt/txt/json/ass/ssa) |
| `POST` | `/{task_id}/search` | Search subtitle text |
| `GET` | `/{task_id}/metadata` | Get subtitle metadata |
| `GET` | `/{task_id}/statistics` | Get subtitle statistics |
| `POST` | `/{task_id}/retranscribe` | Create re-transcription task |
| `POST` | `/{task_id}/retranscribe/{rtid}/apply` | Apply re-transcription result |
| `GET` | `/retranscribe/{rtid}` | Get re-transcription status |
| `GET` | `/retranscribe` | List all re-transcription tasks |
| `DELETE` | `/retranscribe/{rtid}` | Delete re-transcription task |
| `POST` | `/{task_id}/burn-in` | Start subtitle burn-in to video |
| `GET` | `/burn-in/{burn_id}` | Get burn-in progress |
| `GET` | `/burn-in/{burn_id}/download` | Download burn-in result |
| `POST` | `/enhance` | LLM subtitle enhancement (SSE streaming) |
| `GET` | `/formats` | List supported export formats |

### Download Endpoints (services/download_api.py)

| Method | Path | Description |
|---|---|---|
| `GET` | `/download/{task_id}/{file_type}` | Download result file |

### System Endpoints (services/system_api.py)

| Method | Path | Description |
|---|---|---|
| `GET` | `/gpu-info` | GPU information |
| `GET` | `/system/directories` | Root directories |
| `GET` | `/system/subdirectories?path=` | List subdirectories |

### SPA Catch-all (app.py)

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Serve React SPA index.html |
| `GET` | `/editor/{task_id}` | SPA client-side routing |
| `GET` | `/subtitle-editor/{task_id}` | SPA client-side routing (legacy) |

## Key Request/Response Formats

### TranscriptionRequest (POST body)
```json
{
  "url": "https://youtube.com/watch?v=...",
  "model_size": "qwen3-asr-1.7b",
  "device": "auto",
  "compute_type": "default",
  "language": null,
  "task": "transcribe",
  "beam_size": 5,
  "vad_filter": true,
  "word_timestamps": true,
  "output_format": "srt",
  "split_segments": false,
  "segment_duration": 30,
  "download_format": "audio",
  "video_quality": "best",
  "speaker_diarization": false,
  "num_speakers": null,
  "llm_enhance": false,
  "llm_api_key": null,
  "llm_base_url": "https://api.openai.com/v1",
  "llm_model": "gpt-4o-mini",
  "llm_content_hint": null
}
```

### Task Response
```json
{
  "id": "uuid",
  "status": "completed",
  "progress": 100.0,
  "message": "轉錄完成",
  "result": {
    "files": { "json": "path", "srt": "path", "txt": "path", "video": "path" },
    "output_dir": "outputs/uuid"
  },
  "error": null,
  "start_time": 1700000000.0,
  "end_time": 1700000060.0,
  "source_name": "video.mp4",
  "batch_id": null
}
```

### SubtitleCollection (GET/PUT body)
```json
{
  "task_id": "uuid",
  "subtitles": [
    { "index": 0, "start_time": 0.0, "end_time": 2.5, "text": "...", "words": [...], "confidence": -0.3 }
  ],
  "metadata": {
    "language": "zh", "model_used": "qwen3-asr-1.7b",
    "total_duration": 120.0, "total_segments": 50,
    "video_info": { "video_url": "/download/uuid/video", "format": "mp4" }
  }
}
```

## Authentication / Authorization

None. The application is designed for local/private network use. CORS allows all origins.

## Step-by-step: Add a New Endpoint

1. **Choose location**: If it relates to an existing domain, add to the relevant `services/*.py`. Otherwise create a new service file.

2. **Define the router** (if new file):
```python
from fastapi import APIRouter
router = APIRouter(prefix="/api/myfeature", tags=["myfeature"])
```

3. **Add route handler**:
```python
@router.get("/{item_id}")
async def get_item(item_id: str):
    # Access task registry if needed:
    tasks = get_tasks_storage()  # or whatever accessor is wired up
    return {"id": item_id}
```

4. **Wire up in app.py**:
```python
from backend.services.my_service import router as my_router
app.include_router(my_router)
# If it needs task access:
from backend.services.my_service import set_my_task_registry
set_my_task_registry(tasks)
```

5. **Add frontend types** in `frontend-react/src/types/api.ts`:
```typescript
export interface MyItem { id: string; name: string }
```

6. **Add API method** in `frontend-react/src/api/client.ts`:
```typescript
getMyItem(id: string) {
  return request<MyItem>(`/api/myfeature/${id}`)
},
```

7. **Write tests** in `tests/test_my_service.py` following existing patterns.

## SSE Streaming Pattern

Used by `/tasks/{id}/stream` and `/api/subtitles/enhance`:
```python
from starlette.responses import StreamingResponse

async def event_generator():
    yield f"data: {json.dumps(payload)}\n\n"

return StreamingResponse(event_generator(), media_type="text/event-stream")
```

Frontend consumption:
```typescript
const reader = res.body.getReader()
const decoder = new TextDecoder()
// Read chunks, split on '\n', parse 'data: ' prefixed lines
```
