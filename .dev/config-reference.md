# Configuration Reference

## Runtime Environment Variables

| Variable | Type | Default | Read by | Purpose |
|---|---|---|---|---|
| `DATABASE_URL` | str (SQLAlchemy URL) | `sqlite:///<repo>/tasks.db` | `backend/database.py` | Database connection. Use `postgresql://...` in Docker. |
| `MAX_TRANSCRIPTION_WORKERS` | int | auto-detected | `backend/app.py:_detect_max_workers` | Overrides the transcription thread-pool size. |
| `HF_TOKEN` | str | (none) | Hugging Face libraries | API access for gated models. Load from `.env` locally. |
| `NVIDIA_VISIBLE_DEVICES` | str | `all` (Docker) | CUDA runtime | GPU visibility. Set by `docker-compose.yml`. |
| `NVIDIA_DRIVER_CAPABILITIES` | str | `compute,utility` (Docker) | CUDA runtime | Driver capabilities. Set by `docker-compose.yml`. |
| `MODELSCOPE_CACHE` | path | `/app/models` (Docker) | ModelScope | Where to cache downloaded ASR models. |
| `HF_HOME` | path | `/app/models` (Docker) | huggingface_hub | HF cache root. |
| `HUGGINGFACE_HUB_CACHE` | path | `/app/models` (Docker) | huggingface_hub | Specific cache dir for hub downloads. |
| `PYTHONUNBUFFERED` | `1` (Docker) | unset | Python runtime | Flush stdout/stderr immediately. |
| `PYTHONDONTWRITEBYTECODE` | `1` (Docker) | unset | Python runtime | Skip `.pyc` generation. |

`.env` is loaded once in `backend/app.py` via `load_dotenv()` at import time — anything read later with `os.environ.get(...)` will see its values.

## Auto-Detection Heuristics

`backend/app.py:_detect_max_workers`:

```text
if MAX_TRANSCRIPTION_WORKERS is set:
    workers = max(1, int(env))
elif torch.cuda.is_available():
    total_vram_gb = sum(props.total_memory for each GPU) / 1024**3
    estimated = max(2, int(total_vram_gb / 2))          # ~2 GB per worker
    workers = min(estimated, gpu_count * 3)             # capped at 3x GPU count
else:
    workers = min(4, max(1, (os.cpu_count() or 4) // 2))
```

## Application-Level Constants

| Constant | File | Meaning |
|---|---|---|
| `SUPPORTED_MEDIA_EXTENSIONS` | `backend/shared/media_config.py` | Union of `AUDIO_EXTENSIONS` and `VIDEO_EXTENSIONS`. Source of truth for upload validation. |
| `AUDIO_EXTENSIONS` | `backend/shared/media_config.py` | `{".mp3", ".wav", ".ogg", ".flac", ".aac"}` |
| `VIDEO_EXTENSIONS` | `backend/shared/media_config.py` | `{".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv", ".m4v", ".mpeg", ".mpg"}` |
| `MEDIA_TYPES` | `backend/shared/media_config.py` | Extension → MIME mapping for download responses. |
| `FUNASR_MODEL_NAMES` | `backend/shared/engine_routing.py` | Model aliases routed to `funasr_transcribe`. Everything else goes to `qwen3_asr_transcribe`. |
| `_BROWSER_NATIVE_CONTAINERS` | `backend/shared/video_utils.py` | `{".mp4", ".webm"}` — no transcode needed. |
| `_FFMPEG_TIMEOUT_REMUX` / `_FFMPEG_TIMEOUT_TRANSCODE` | `backend/shared/video_utils.py` | ffmpeg subprocess timeouts in seconds. |
| `MAX_HISTORY` | `frontend-react/src/stores/editor-store.ts` | Undo stack size (50). |
| `_MAX_LINES_PER_BATCH` / `_MAX_CHARS_PER_BATCH` | `backend/shared/llm_postprocess.py` | LLM enhance batching limits. |

## Directories

| Path | Created by | Purpose |
|---|---|---|
| `uploads/` | `backend/app.py` (startup `mkdir`) | Incoming files, named `<task_id>_<original>` |
| `outputs/` | `backend/app.py` (startup `mkdir`) | Per-task result directories `outputs/<task_id>/` |
| `temp/` | `backend/app.py` (startup `mkdir`) | Scratch area for ffmpeg / splits |
| `faster-whisper-large-v3-zh-TW/` | checked-in model dir | Optional local FasterWhisper model (read-only mount in Docker) |
| `frontend-react/dist/` | `npm run build` | SPA static bundle served by FastAPI |

## Database Schema

Managed by `backend/database.py` (`Base.metadata.create_all` + `_run_migrations`).

### `tasks` table (`TaskRecord`)

| Column | Type | Notes |
|---|---|---|
| `id` | VARCHAR(36) PK | UUID |
| `status` | VARCHAR(20) | `queued`, `uploading`, `processing`, `completed`, `failed` |
| `progress` | FLOAT | 0–100 |
| `message` | TEXT | Current human-readable status |
| `result` | JSON | `{files: {srt, vtt, txt, json, video?, updated_json?}, output_dir}` |
| `error` | TEXT | Error message when failed |
| `start_time` | FLOAT | epoch seconds |
| `end_time` | FLOAT nullable | epoch seconds |
| `source_name` | TEXT | Displayed title |
| `batch_id` | VARCHAR(36) indexed | Optional batch grouping |
| `folder_id` | VARCHAR(36) indexed | Optional folder assignment |
| `sort_order` | FLOAT | Ordering within folder |

Not persisted (in-memory only): `source_file_path`, `partial_segments`. Remember to extend the schema + add a migration if you need these across restarts.

### `folders` table (`FolderRecord`)

| Column | Type | Notes |
|---|---|---|
| `id` | VARCHAR(36) PK | UUID |
| `name` | VARCHAR(255) | Display name |
| `parent_id` | VARCHAR(36) indexed nullable | Sub-folder support |
| `sort_order` | FLOAT | Ordering |
| `created_at` / `updated_at` | FLOAT | epoch seconds |

## Frontend Config

| Key | File | Purpose |
|---|---|---|
| Path alias `@/*` | `frontend-react/tsconfig.app.json`, `vite.config.ts` | Resolves to `frontend-react/src/*` |
| Dev proxy | `frontend-react/vite.config.ts` | Proxies `/transcribe`, `/tasks`, `/download`, `/gpu-info`, `/system`, `/api` to `http://localhost:5000` |
| React Query defaults | `frontend-react/src/App.tsx` | `{ retry: 1, refetchOnWindowFocus: false }` |
| TypeScript strict mode | `frontend-react/tsconfig.app.json` | `strict: true`, `noUnusedLocals`, `noUnusedParameters` |

Note: `backend/app.py:__main__` uses port 5001 for direct invocation, but Docker and Vite assume 5000. Run via `uvicorn backend.app:app --port 5000 --reload` for local dev that matches the Vite proxy.

## CI Configuration

`.github/workflows/ci.yml`:

| Setting | Value |
|---|---|
| Runner | `windows-latest` |
| Python | 3.12 |
| Triggers | `push`, `pull_request` |
| Pinned deps in CI | `pydantic==2.11.9`, `fastapi==0.117.1`, `httpx==0.28.1` |
| Lint scope | `tests backend/shared backend/services backend/models.py backend/task_persistence.py` |
| Test command | `python -m pytest tests/ -q` |
| Frontend tests | none (run locally) |

`.flake8`: `max-line-length=88`, excludes `.git`, `.venv`, `.worktrees`.
