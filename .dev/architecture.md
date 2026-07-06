# Architecture

## System Diagram

```
                       ┌──────────────────────────────┐
                       │     React SPA (Vite build)   │
                       │  served as static files by   │
                       │  FastAPI (/, /editor/:id)    │
                       └───────────────┬──────────────┘
                                       │ fetch / SSE
                                       ▼
┌───────────────────────────────────────────────────────────────────┐
│                        FastAPI (uvicorn)                          │
│                                                                   │
│   ┌─────────── asyncio event loop ───────────────────┐            │
│   │ subtitle_api · task_api · download_api · folder  │            │
│   │ system_api · /transcribe/* routes in app.py      │            │
│   │ SSE generator: task_api.event_generator          │            │
│   └───────────────────────┬──────────────────────────┘            │
│                           │ submit()                              │
│                           ▼                                       │
│   ┌──────────── ThreadPoolExecutor("transcribe") ────────────┐    │
│   │ process_transcription → engine_routing → Qwen3 / FunASR  │    │
│   │ ffmpeg previews · yt-dlp downloads · LLM post-process    │    │
│   └──────────────────────────────────────────────────────────┘    │
│                           │                                       │
│                           ▼                                       │
│   ┌────── SQLAlchemy (SQLite dev / PostgreSQL Docker) ────────┐   │
│   │ TaskRecord · FolderRecord · incremental migrations        │   │
│   └───────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
           ▲                      ▲                          ▲
           │                      │                          │
  outputs/<task>/*.json  uploads/<task>_<name>        whisper_app.log
```

## Concurrency Model

Three execution domains share state through the `tasks` dict in `backend/app.py`:

| Domain | Runs in | Touches |
|---|---|---|
| asyncio loop | uvicorn main thread | `tasks` (read/write), SSE generators, DB sessions |
| Transcription workers | `_transcription_executor` threads | `tasks[task_id]` mutation, ffmpeg/torch/yt-dlp, DB sessions |
| Retranscribe workers | `RetranscribeService.executor` (2 threads) | `RetranscribeService.retranscribe_tasks` under `self._lock` |

Thread-pool sizing in `backend/app.py:_detect_max_workers`:

```python
# GPU mode → est. = max(2, int(total_vram_gb / 2)), capped at gpu_count*3
# CPU mode → est. = min(4, max(1, cpu_count // 2))
# Override: env MAX_TRANSCRIPTION_WORKERS
```

The SSE endpoint (`backend/services/task_api.py:46`) polls every 500 ms and breaks on terminal status:

```python
while True:
    tasks = get_task_registry()
    if task_id not in tasks:
        yield f"event: deleted\ndata: {json.dumps({'id': task_id})}\n\n"
        break
    task = tasks[task_id]
    ...
    if task.status in ("completed", "failed"):
        break
    await asyncio.sleep(0.5)
```

## Key Data Structures

| Name | Location | Shape | Lifecycle |
|---|---|---|---|
| `tasks` | `backend/app.py` (module global) | `Dict[str, Task]` | Filled from DB at import time; mutated by routes + workers; shut down with process |
| `Task` | `backend/app.py:Task` | Pydantic BaseModel | One instance per transcription job |
| `TaskRecord` | `backend/database.py` | SQLAlchemy ORM row | Persisted mirror of `Task` (lacks `source_file_path`, `partial_segments`) |
| `SubtitleCollection` | `backend/models.py` | Pydantic | Loaded on demand from `outputs/<id>/*.json`, saved as `<id>_updated.json` |
| `RetranscribeTask` | `backend/models.py` + service | Pydantic | In-memory only; lost on restart |
| `_transcription_executor` | `backend/app.py` | `ThreadPoolExecutor` | Singleton per process |

## Request Flow

```
1. Client POSTs /transcribe/url | /transcribe/upload | /transcribe/local
2. Route handler (app.py):
   · validate_upload_filename / check file_path existence
   · save_uploaded_file (uploads/{task_id}_{name}) if needed
   · create_task_entry → tasks[task_id] = Task(status="queued")
   · save_task_to_disk → TaskPersistence.save_task → DB
   · submit_transcription(executor, process_transcription, task_id, …)
   · return {"task_id": ...}
3. Worker thread picks up process_transcription:
   · resolve_output_directory → outputs/<task_id>/
   · prepare_source_video_for_preview (ffmpeg mp4, if video)
   · build_status_callback closure → updates task + persists
   · transcribe_audio(**kwargs) → engine_routing
   · _apply_llm_enhancement (optional)
   · finalize_task_success | finalize_task_failure
   · save_task_to_disk
4. Client consumes SSE /tasks/{id}/stream until status=completed|failed.
5. Editor UI calls GET /api/subtitles/{id} → loads *.json, returns SubtitleCollection.
6. User edits subtitles → PUT /api/subtitles/{id} → writes <id>_updated.json.
```

## Common Pitfalls

- **`tasks` dict is shared without a lock.** GIL serializes single ops, but check-then-act is not atomic. Keep multi-step mutations inside a single function.
- **Startup side effects at import time.** `backend.app` initializes the DB and loads tasks when imported. Tests that need to avoid this use `sys.modules.pop("backend.services.<mod>", None)` + `importlib.import_module(...)`.
- **Circular import via lazy binding.** `transcription_launcher.create_task_entry` has `from backend.app import Task as task_cls` inside the function. Never move the import to module scope.
- **Router globals need explicit wiring.** Each router has `_task_registry` / `_task_store` module globals. `app.py` must call `set_*` after `app.include_router(...)` or routes raise `RuntimeError("任務註冊表未初始化")`.
- **`RetranscribeService` is not persisted.** Restarts drop all retranscription state.
- **`Task.source_file_path` is NOT in the DB schema.** `TaskRecord` lacks this column; the value survives only in memory.
- **Duplicate video-extension lists.** `media_config.py` is canonical, but `subtitle_api.py` and `download_api.py` each inline their own. Keep them in sync when extending.
- **Vite dev proxy expects port 5000.** `backend/app.py:__main__` defaults to 5001 for local runs; Docker uses 5000. Adjust accordingly.
- **SSE generator re-fetches `tasks` each iteration.** Re-assignment inside the loop intentionally guards against registry swap, but the same check-then-use pattern is safe only because there is no `await` between `in` check and `tasks[task_id]` access.

## Key Globals

| Global | File | Injected via | Consumed by |
|---|---|---|---|
| `tasks: Dict[str, Task]` | `backend/app.py` | created at module scope | all routers, workers |
| `_transcription_executor` | `backend/app.py` | created at module scope | `submit_transcription()` |
| `_task_registry` | `backend/services/task_api.py` | `set_task_registry(tasks)` | task endpoints |
| `_task_registry` | `backend/services/folder_api.py` | `set_folder_task_registry(tasks)` | folder endpoints |
| `_task_registry` | `backend/services/download_api.py` | `set_download_task_registry(tasks)` | download endpoint |
| `_task_store` | `backend/services/subtitle_api.py` | `set_task_store(TaskStore(tasks))` | subtitle endpoints |
| `_retranscribe_service` | `backend/services/subtitle_api.py` | `get_retranscribe_service()` (lazy) | retranscribe endpoints |
| `MAX_WORKERS` | `backend/app.py` | `_detect_max_workers()` at import | executor size only |
| `SUPPORTED_MEDIA_EXTENSIONS` | `backend/shared/media_config.py` | module constant | upload validation, download MIME |
| `FUNASR_MODEL_NAMES` | `backend/shared/engine_routing.py` | module constant | engine dispatch |
