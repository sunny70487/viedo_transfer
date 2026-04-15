# Configuration Reference

## Environment Variables

All configuration is via environment variables. Loaded from `.env` file by `python-dotenv` at startup (`backend/app.py`).

### Database

| Key | Type | Default | Maps to | Description |
|---|---|---|---|---|
| `DATABASE_URL` | `str` | `sqlite:///tasks.db` | `database.DATABASE_URL` → SQLAlchemy `engine` | Database connection string. PostgreSQL in production, SQLite for dev. |

**Note**: The default SQLite path is relative to project root (`{project_root}/tasks.db`). In Docker, `DATABASE_URL` is set to PostgreSQL in `docker-compose.yml`.

### Transcription Workers

| Key | Type | Default | Maps to | Description |
|---|---|---|---|---|
| `MAX_TRANSCRIPTION_WORKERS` | `int` | auto-detect | `app.MAX_WORKERS` → `_transcription_executor` | Max concurrent transcription threads. Auto: GPU=VRAM÷2GB (min 2, max 3×GPU), CPU=cores÷2 (max 4). |

### Model Cache (Docker)

| Key | Type | Default | Maps to | Description |
|---|---|---|---|---|
| `MODELSCOPE_CACHE` | `str` | `/app/models` | ModelScope cache dir | Where ASR models are cached |
| `HF_HOME` | `str` | `/app/models` | HuggingFace cache dir | Where HF models are cached |
| `HUGGINGFACE_HUB_CACHE` | `str` | `/app/models` | HF Hub cache dir | Alias for HF cache |

### Speaker Diarization

| Key | Type | Default | Maps to | Description |
|---|---|---|---|---|
| `HUGGINGFACE_TOKEN` | `str` | (none) | `diarization_service._get_pipeline()` | HuggingFace token for pyannote model access |
| `HF_TOKEN` | `str` | (none) | fallback for above | Alternative env var name |

### GPU (Docker)

| Key | Type | Default | Maps to | Description |
|---|---|---|---|---|
| `NVIDIA_VISIBLE_DEVICES` | `str` | `all` | NVIDIA runtime | Which GPUs to expose |
| `NVIDIA_DRIVER_CAPABILITIES` | `str` | `compute,utility` | NVIDIA runtime | Required capabilities |

### Python Runtime (Docker)

| Key | Type | Default | Maps to | Description |
|---|---|---|---|---|
| `PYTHONUNBUFFERED` | `str` | `1` | Python runtime | Disable output buffering |
| `PYTHONDONTWRITEBYTECODE` | `str` | `1` | Python runtime | Don't write .pyc files |

## Docker Compose Configuration

### Services

#### `postgres`
- Image: `postgres:16-alpine`
- DB: `whisper_transfer`, User: `whisper`, Password: `whisper_secret`
- Health check: `pg_isready` every 10s
- Volume: `postgres-data` (named volume)

#### `whisper`
- Build: multi-stage Dockerfile (Node.js → CUDA + Python)
- Port: `5050:5000` (host:container)
- `shm_size: 2gb` (for PyTorch DataLoader / CUDA)
- `extra_hosts: host.docker.internal:host-gateway` (for local LLM access)
- Volumes: `./outputs`, `./uploads`, `whisper-models` (named), local fine-tuned models (read-only)

### Named Volumes
| Volume | Name | Purpose |
|---|---|---|
| `whisper-models` | `whisper-model-cache` | ASR model cache |
| `postgres-data` | `whisper-postgres-data` | PostgreSQL data |

## SQLite vs PostgreSQL

| Aspect | SQLite (dev) | PostgreSQL (prod/Docker) |
|---|---|---|
| Connection | `sqlite:///tasks.db` | `postgresql://whisper:whisper_secret@postgres:5432/whisper_transfer` |
| Thread safety | `check_same_thread=False` + WAL mode | Native multi-connection |
| Pragmas | `journal_mode=WAL`, `synchronous=NORMAL` | N/A |
| Setup | Automatic (file-based) | Requires `docker-compose` or manual setup |

## Hardcoded Defaults (in source code)

### app.py
| Constant | Value | Description |
|---|---|---|
| `UPLOAD_DIR` | `Path("uploads")` | Upload storage |
| `OUTPUT_DIR` | `Path("outputs")` | Transcription output |
| `TEMP_DIR` | `Path("temp")` | Temporary files |
| Default port (dev) | `5001` | `__main__` entry point |
| Default port (Docker) | `5000` | Dockerfile CMD |

### TranscriptionRequest defaults
| Field | Default | Description |
|---|---|---|
| `model_size` | `"qwen3-asr-1.7b"` | ASR model |
| `device` | `"auto"` | GPU/CPU selection |
| `compute_type` | `"default"` | Precision mode |
| `beam_size` | `5` | Beam search width |
| `vad_filter` | `True` | Voice activity detection |
| `word_timestamps` | `True` | Per-word timing |
| `output_format` | `"srt"` | Default subtitle format |
| `download_format` | `"audio"` | Audio-only download |
| `video_quality` | `"best"` | yt-dlp quality |

### LLM Post-processing (llm_postprocess.py)
| Constant | Value | Description |
|---|---|---|
| `_MAX_RETRIES` | `3` | LLM call retry count |
| `_RETRY_BACKOFF` | `(2, 5, 10)` | Seconds between retries |
| `_MAX_LINES_PER_BATCH` | `80` | Lines per LLM enhancement batch |
| `_MAX_LINES_PER_BATCH_TRANSLATE` | `30` | Lines per translation batch |
| `_MAX_CHARS_PER_BATCH` | `6000` | Chars per enhancement batch |
| `_MAX_CHARS_PER_BATCH_TRANSLATE` | `3000` | Chars per translation batch |
| `_BATCH_COOLDOWN` | `1.0` | Seconds between batches |
| `_CONTEXT_OVERLAP` | `3` | Context lines between batches |
| `_TARGET_CHARS` | `20` | Target chars per subtitle line |
| `_MAX_CHARS` | `30` | Max chars before resplit |

### Retranscribe Service
| Constant | Value | Location |
|---|---|---|
| `max_workers` | `2` | `RetranscribeService.__init__` |
| Audio format | `"flac"` | `_extract_audio_segment` |
| Cleanup age | `24` hours | `cleanup_completed_tasks` |

### Burn-in Defaults
| Field | Default | Description |
|---|---|---|
| `font_size` | `22` | Subtitle font size |
| `font_color` | `"FFFFFF"` | White text |
| `outline_color` | `"000000"` | Black outline |
| `outline_width` | `2` | Outline thickness |
| `margin_v` | `30` | Vertical margin |
| Timeout | `7200s` (2h) | FFmpeg process timeout |
