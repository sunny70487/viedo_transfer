# Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────┐
│                    React SPA (Vite)                      │
│  Pages: HomePage, EditorPage                            │
│  State: Zustand stores (editor-store, theme-store)      │
│  API:   api/client.ts → fetch()                         │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP / SSE
┌──────────────────────▼──────────────────────────────────┐
│                  FastAPI (backend/app.py)                │
│  Middleware: CORS (allow all origins)                    │
│  Static:    frontend-react/dist/ served at /assets      │
│  Routers:   task_api, subtitle_api, download_api,       │
│             system_api                                   │
├─────────────────────────────────────────────────────────┤
│             ThreadPoolExecutor (transcription)           │
│  max_workers = auto-detect (GPU VRAM / CPU cores)       │
│  or override via MAX_TRANSCRIPTION_WORKERS env var      │
├─────────────────────────────────────────────────────────┤
│                     Services Layer                       │
│  transcription_launcher → transcription_orchestrator    │
│  retranscribe_service (separate ThreadPoolExecutor)     │
│  burn_in_service (daemon threads + FFmpeg subprocess)   │
│  diarization_service (pyannote, cached singleton)       │
│  subtitle_converter, audio_segment_service              │
├─────────────────────────────────────────────────────────┤
│                    Shared Utilities                      │
│  engine_routing → qwen3_asr / funasr / faster_whisper   │
│  text_processing, transcription_pipeline                │
│  llm_postprocess (OpenAI-compatible API)                │
│  media_config, transcribe_helpers                       │
├─────────────────────────────────────────────────────────┤
│                    Persistence Layer                     │
│  SQLAlchemy (PostgreSQL / SQLite)                       │
│  TaskRecord ORM + TaskPersistence static methods        │
│  Legacy JSON migration on first startup                 │
└─────────────────────────────────────────────────────────┘
```

## Concurrency Model

- **Main thread**: asyncio event loop (uvicorn) — handles HTTP requests.
- **Transcription pool**: `ThreadPoolExecutor` in `app.py`, shared by URL/upload/local/batch endpoints. GIL released during C-extension calls (torch, ffmpeg).
- **Retranscribe pool**: separate `ThreadPoolExecutor(max_workers=2)` in `RetranscribeService`, manages segment re-transcription.
- **Burn-in**: daemon threads in `burn_in_service.py`, each runs an FFmpeg subprocess.
- **Diarization pipeline**: cached singleton behind `threading.Lock`, loaded once on first use.
- **Task state**: in-memory `dict` (`tasks` in `app.py`) is the runtime source of truth. Written to DB asynchronously via `TaskPersistence.save_task()`. Each worker thread gets its own DB session (thread-safe via `SessionLocal()`).

## Key Data Structures

### Task lifecycle states
```
queued → uploading → processing → completed
                  ↘               ↗
                    failed ←──────
```

### In-memory task registry
`tasks: Dict[str, Task]` in `app.py` — keyed by UUID. Shared across routes and workers via module-level reference injection (`set_task_registry()`, `set_task_store()`, `set_download_task_registry()`).

### Transcription output (JSON schema)
```json
{
  "text": "full transcript",
  "segments": [
    { "id": 0, "start": 0.0, "end": 2.5, "text": "...", "words": [...], "speaker": "Speaker 1" }
  ],
  "language": "zh",
  "language_probability": 0.98,
  "words": [...],
  "speakers": [...]
}
```

### Subtitle editing flow
1. `SubtitleService.load_subtitle_data()` reads JSON → converts to `SubtitleCollection` (Pydantic).
2. Frontend edits via Zustand `editor-store` (undo/redo history, dirty tracking).
3. `SubtitleService.save_subtitle_data()` writes `{task_id}_updated.json`.
4. Export reads updated JSON, converts via `SubtitleConverter`.

## Request Processing Flow

### Transcription (URL)
1. `POST /transcribe/url` → validate → `create_task_entry()` → `submit_transcription()`.
2. Worker: `process_transcription()` → `prepare_url_input()` (yt-dlp download) → `transcribe_audio()` → optional `_apply_llm_enhancement()` → `finalize_task_success()`.
3. Client polls via `GET /tasks/{id}` or `GET /tasks/{id}/stream` (SSE).

### Subtitle Enhancement (SSE)
1. `POST /api/subtitles/enhance` → merge short segments → chunk lines.
2. Stream SSE events: `progress` per batch → final `result` with all subtitles.
3. Frontend `enhanceSubtitlesStream()` reads SSE via `ReadableStream`.

## Common Pitfalls

### Shared state injection
Routers access the task registry through module-level setters (`set_task_registry()`, etc.), called in `app.py` after `app.include_router()`. If you add a new router that needs task access, you must wire it up the same way.

### Thread-safe DB sessions
`TaskPersistence.save_task()` creates a new `SessionLocal()` context per call. Never share a session across threads. SQLite uses WAL mode to reduce write contention.

### Docker localhost rewriting
When running in Docker, `_rewrite_localhost_url()` converts `localhost`/`127.0.0.1` to `host.docker.internal` for LLM API calls. This happens in both `app.py` and `llm_postprocess.py`. Check `os.path.exists("/.dockerenv")`.

### LLM line count reconciliation
`_call_llm()` in `llm_postprocess.py` retries up to 3 times if the LLM returns a different number of lines than expected. Uses `_reconcile_lines()` to strip headers, line numbers, and empty lines. On final failure, returns partial results merged with originals.

### Video file lookup
Both `subtitle_api.py` and `download_api.py` search for video files by iterating through known keys (`video`, `mp4`, `avi`, ...) then by extension. This duplicated logic in `_find_video_path()` must stay in sync.

### Pydantic validator side effects
`Subtitle.validate_words_timing` mutates word objects in-place (clamping). `SubtitleMetadata` auto-corrects `last_modified` if before `created_at`. These validators fire on construction.

## Key Global Variables

### app.py
| Variable | Type | Purpose |
|---|---|---|
| `tasks` | `Dict[str, Task]` | In-memory task registry (runtime source of truth) |
| `MAX_WORKERS` | `int` | Transcription thread-pool size |
| `_transcription_executor` | `ThreadPoolExecutor` | Shared transcription worker pool |
| `UPLOAD_DIR` / `OUTPUT_DIR` / `TEMP_DIR` | `Path` | Working directories |

### database.py
| Variable | Type | Purpose |
|---|---|---|
| `DATABASE_URL` | `str` | DB connection string (from env or SQLite fallback) |
| `engine` | `sqlalchemy.Engine` | Global DB engine |
| `SessionLocal` | `sessionmaker` | Session factory (thread-safe) |

### Services (module-level singletons)
| Variable | Location | Purpose |
|---|---|---|
| `_task_store` | `subtitle_api.py` | `TaskStore` wrapper for task dict |
| `_task_registry` | `task_api.py`, `download_api.py` | Direct task dict references |
| `_retranscribe_service` | `retranscribe_service.py` | Lazy singleton `RetranscribeService` |
| `_burn_tasks` | `burn_in_service.py` | In-memory burn-in task registry |
| `_PIPELINE_INSTANCE` | `diarization_service.py` | Cached pyannote pipeline |

### Shared
| Variable | Location | Purpose |
|---|---|---|
| `_S2TW_CONVERTER` | `text_processing.py` | OpenCC converter instance (s2twp) |
| `FUNASR_MODEL_NAMES` | `engine_routing.py` | frozenset of model names routed to FunASR |
