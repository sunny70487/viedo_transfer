# Whisper Transfer — Development Guide

**Stack**: Python 3.11+ / FastAPI (backend), React 19 / TypeScript / Vite / Tailwind v4 (frontend), PostgreSQL / SQLite (persistence)
**Architecture**: Monorepo — `backend/` (FastAPI + ASR engines) + `frontend-react/` (React SPA). Docker multi-stage build.
**Entry point**: `backend/app.py` → uvicorn; frontend served from `frontend-react/dist/` as static files.

## Module Map

| Directory / File | Responsibility |
|---|---|
| `backend/app.py` | FastAPI app, route definitions, thread-pool executor, task lifecycle |
| `backend/models.py` | Pydantic data models (Subtitle, Word, SubtitleCollection, etc.) |
| `backend/database.py` | SQLAlchemy engine/session, TaskRecord ORM model |
| `backend/task_persistence.py` | Task CRUD via SQLAlchemy, JSON migration, filesystem rebuild |
| `backend/qwen3_asr_transcribe.py` | Qwen3-ASR transcription engine (primary) |
| `backend/funasr_transcribe.py` | FunASR transcription engine (fallback), `download_from_url` |
| `backend/faster_whisper_transcribe.py` | Faster Whisper engine (legacy fallback) |
| `backend/shared/engine_routing.py` | Routes `transcribe_audio()` to correct ASR engine by model name |
| `backend/shared/text_processing.py` | OpenCC conversion, punctuation stripping, segment splitting |
| `backend/shared/transcription_pipeline.py` | Device resolution, SRT/VTT formatting, output file writing |
| `backend/shared/transcribe_helpers.py` | `check_gpu()`, `format_timestamp()` |
| `backend/shared/media_config.py` | Supported media extensions, MIME types |
| `backend/shared/llm_postprocess.py` | LLM-based subtitle enhancement (OpenAI-compatible API) |
| `backend/services/task_api.py` | `/tasks` CRUD + SSE streaming endpoints |
| `backend/services/subtitle_api.py` | `/api/subtitles` CRUD, search, export, burn-in, LLM enhance |
| `backend/services/download_api.py` | `/download/{task_id}/{file_type}` file serving |
| `backend/services/system_api.py` | `/gpu-info`, `/system/directories` endpoints |
| `backend/services/transcription_launcher.py` | `create_task_entry()`, `submit_transcription()` |
| `backend/services/transcription_orchestrator.py` | `resolve_output_directory()`, `finalize_task_success()` |
| `backend/services/transcription_progress.py` | Status callback builder, `finalize_task_failure()` |
| `backend/services/retranscribe_service.py` | Segment re-transcription service (ThreadPoolExecutor) |
| `backend/services/subtitle_converter.py` | Multi-format subtitle converter (SRT, VTT, ASS, SSA, TXT, JSON) |
| `backend/services/burn_in_service.py` | FFmpeg-based subtitle hardcoding into video |
| `backend/services/diarization_service.py` | pyannote.audio speaker diarization |
| `backend/services/upload_preprocessing.py` | File validation + save for uploads |
| `backend/services/url_preprocessing.py` | URL download preparation |
| `frontend-react/src/api/client.ts` | API client — all backend calls |
| `frontend-react/src/types/api.ts` | TypeScript interfaces mirroring backend models |
| `frontend-react/src/stores/editor-store.ts` | Zustand store — subtitle editor state, undo/redo |
| `frontend-react/src/pages/` | `HomePage` (task list + upload), `EditorPage` (subtitle editor) |
| `frontend-react/src/components/editor/` | VideoPlayer, SubtitleRow, SubtitleToolbar, ExportDialog, LlmEnhanceDialog |
| `frontend-react/src/components/transcription/` | UploadForm, URLForm, TaskCard, TaskList, TranscriptionOptions |
| `tests/` | pytest tests — `test_*.py` per module |

## Naming Conventions

| Kind | Convention | Example |
|---|---|---|
| Python file | `snake_case.py` | `subtitle_api.py` |
| Python function / variable | `snake_case` | `create_task_entry()`, `file_path` |
| Python class | `PascalCase` | `SubtitleCollection`, `TaskStore` |
| Python constant | `UPPER_SNAKE_CASE` | `SUPPORTED_MEDIA_EXTENSIONS`, `MAX_WORKERS` |
| Private Python | `_leading_underscore` | `_transcription_executor`, `_call_llm()` |
| TypeScript file | `kebab-case.ts(x)` | `editor-store.ts`, `SubtitleRow.tsx` |
| React component | `PascalCase.tsx` | `VideoPlayer.tsx` |
| TS interface | `PascalCase` | `SubtitleCollection`, `Task` |
| TS hook | `use-kebab-case.ts` | `use-tasks.ts` |
| API route | `/kebab-case/resource` | `/api/subtitles/{task_id}` |

## Error Handling

- Backend: raise `HTTPException` for request errors; `try/except` with `logger.error(msg, exc_info=True)` for internal errors.
- Background tasks: catch all in `process_transcription()`, call `finalize_task_failure()`. Non-fatal errors logged as warnings.
- Frontend: `api.request<T>()` throws `Error` with `body.detail || body.error`; callers handle with try/catch.

## Logging

- Framework: Python `logging` module. Logger per module: `logging.getLogger("module_name")` or `logging.getLogger(__name__)`.
- Format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`. Output: stdout + `whisper_app.log`.
- Levels: `INFO` for operations, `WARNING` for non-fatal issues, `ERROR` with `exc_info=True` for failures, `DEBUG` for persistence.

## Configuration

- Primary: environment variables (`DATABASE_URL`, `MAX_TRANSCRIPTION_WORKERS`, `HUGGINGFACE_TOKEN`).
- `.env` file loaded via `python-dotenv` at startup. See `.dev/config-reference.md` for full schema.
- Database: `DATABASE_URL` → PostgreSQL (production) or SQLite (development fallback).

## Common Tasks

### Add a new API endpoint
1. Create or edit a service file in `backend/services/`.
2. Define an `APIRouter` and add route handler functions.
3. In `backend/app.py`: import router, call `app.include_router(router)`.
4. Add corresponding TypeScript types in `frontend-react/src/types/api.ts`.
5. Add API method in `frontend-react/src/api/client.ts`.

### Add a new ASR engine
1. Create `backend/<engine>_transcribe.py` with a `transcribe_audio(**kwargs)` function.
2. Register model names in `backend/shared/engine_routing.py`.

### Add a new subtitle export format
1. Add format handler in `backend/services/subtitle_converter.py`.
2. Register in the converter's format registry.

## Data Flow

```
User → React SPA → api/client.ts → FastAPI endpoint
  → create_task_entry() → ThreadPoolExecutor.submit(process_transcription)
    → download (URL) or use uploaded file
    → engine_routing.transcribe_audio() → Qwen3-ASR / FunASR
    → (optional) LLM enhancement via llm_postprocess
    → finalize_task_success() → TaskPersistence.save_task() → DB
  → SSE /tasks/{id}/stream → React polling → UI update
```

## Code Quality

- **Compilability**: all generated code must be valid — use correct imports, declared types, and match existing patterns. When unsure, check existing files in the same module.
- **Tests**: pytest in `tests/`. Test file naming: `test_<module>.py`. After feature completion, write tests following existing style. Run: `python -m pytest tests/ -q`.
- **Lint**: `flake8` on `tests/ backend/shared/ backend/services/ backend/models.py backend/task_persistence.py`. Line length: default (79).
- **CI**: GitHub Actions runs flake8 + pytest on every push/PR (`.github/workflows/ci.yml`).

## Git Commit Style

```
<type>: <concise description in English>
```
Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `style`. Keep subject line under 72 chars.

## Deep References

| File | When to read |
|---|---|
| `.dev/architecture.md` | System design, concurrency model, data structures, pitfalls |
| `.dev/api-reference.md` | Full API listing, request/response formats, adding endpoints |
| `.dev/coding-style.md` | Pre-commit checklist, naming examples, error handling patterns |
| `.dev/function-index.md` | "I need to do X" → function lookup by developer intent |
| `.dev/config-reference.md` | All config keys, types, defaults, env var mapping |
| `.dev/UPDATE_GUIDE.md` | How to keep these docs in sync with code changes |
