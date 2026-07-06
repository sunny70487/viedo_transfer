# AGENTS.md

## Environment Setup
First-time setup on a fresh clone (idempotent — safe to re-run):

| OS | Command |
|---|---|
| Windows (primary) | `.\scripts\dev-setup.ps1 setup` |
| macOS / Linux / WSL | `make setup` |

Daily commands:

| Goal | Windows | macOS / Linux |
|---|---|---|
| Start dev servers (backend :5000 + frontend :5173) | `.\scripts\dev-setup.ps1 dev` | `make dev` |
| Run tests | `.\scripts\dev-setup.ps1 test` | `make test` |
| Run linters | `.\scripts\dev-setup.ps1 lint` | `make lint` |
| Local CI simulation (lint + test) | `.\scripts\dev-setup.ps1 check` | `make check` |
| Remove caches / build artifacts | `.\scripts\dev-setup.ps1 clean` | `make clean` |

- Runtime versions: Python 3.12 (`.python-version`), Node 22 (`.nvmrc`).
- `setup` creates `.env` from `.env.example` if missing; secrets are optional — defaults work for local dev.
- On Windows `dev` launches uvicorn in a new window and runs Vite in the current window (Ctrl+C stops the frontend; close the other window to stop the backend). On Unix both run in parallel under a single `trap 'kill 0' INT` so one Ctrl+C stops both.

## Verify Changes

| Step | Command | Failure looks like |
|---|---|---|
| Backend lint | `python -m flake8 tests backend/shared backend/services backend/models.py backend/task_persistence.py` | Any output lines of the form `path:line:col: E###/W###/F###` — each is a violation. Zero output = pass. |
| Backend test | `python -m pytest tests/ -q` | `FAILED` markers, a final line like `N failed, M passed`, or a non-zero exit. Warnings alone are OK. |
| Frontend lint | `npm --prefix frontend-react run lint` | ESLint prints `✖ N problems (N errors, …)` and exits non-zero. A `0 problems` summary = pass. |
| Frontend build | `npm --prefix frontend-react run build` | `error TS####` from `tsc -b`, or a Vite `Build failed` banner. Success ends with `✓ built in ...`. |
| Full check | `bash .dev/scripts/verify.sh` | The script prints `--- verify.sh OK ---` on success and exits 0; any earlier step failure aborts with a non-zero code. Use `--backend-only` / `--frontend-only` flags to narrow scope. |

## Hard Constraints
- NEVER import from `backend.app` at module scope in `backend/services/*` or `backend/shared/*` (circular import). Use lazy imports inside functions only, as `transcription_launcher.py:create_task_entry` does.
- NEVER mutate the shared `tasks` dict directly from a route handler; ALWAYS go through `create_task_entry()` / `save_task_to_disk()` so the SQL persistence layer stays consistent.
- ALWAYS dispatch transcription through `backend.shared.engine_routing.transcribe_audio(**kwargs)`. NEVER call `qwen3_asr_transcribe` or `funasr_transcribe` directly from services or routes.
- NEVER block the asyncio event loop with heavy work inside a route handler; ALWAYS submit CPU/GPU work to `_transcription_executor` via `submit_transcription()`.
- NEVER add a new global registry without also adding a `set_*()` injector function and wiring it in `backend/app.py` after `app.include_router()`.
- NEVER commit secrets (`HF_TOKEN`, LLM API keys, passwords). `.env` is for local development only.
- ALWAYS add new supported media extensions to `backend/shared/media_config.py` first; do not duplicate extension lists elsewhere.
- ALWAYS match the surrounding file's conventions (naming, logging style, error handling) before introducing a new pattern.

## Project Overview
Backend: Python 3.12 + FastAPI + SQLAlchemy + Pydantic v2; transcription via Qwen3-ASR / FunASR on GPU thread pool.
Frontend: React 19 + TypeScript + Vite + TailwindCSS + Zustand + TanStack React Query, served as static assets by the backend.
Persistence: SQLite in dev (`tasks.db`), PostgreSQL in Docker (via `DATABASE_URL`).

## Module Map
| Path | Responsibility |
|---|---|
| `backend/app.py` | FastAPI app factory, route wiring, `tasks` registry, `_transcription_executor`, transcription worker |
| `backend/database.py` | SQLAlchemy engine, `TaskRecord`/`FolderRecord` ORM, incremental migrations |
| `backend/models.py` | Pydantic domain models (Subtitle, SubtitleCollection, RetranscribeRequest, …) |
| `backend/task_persistence.py` | `TaskPersistence` class: save/load/delete/rebuild tasks via SQL |
| `backend/qwen3_asr_transcribe.py` | Qwen3-ASR engine implementation |
| `backend/funasr_transcribe.py` | FunASR / SenseVoice / Whisper engine implementation |
| `backend/faster_whisper_transcribe.py` | Legacy FasterWhisper wrapper |
| `backend/services/subtitle_api.py` | Subtitle CRUD, enhance (SSE), summarize, retranscribe, burn-in |
| `backend/services/task_api.py` | Task status, SSE stream, batch status, delete |
| `backend/services/download_api.py` | Serves result files (video/srt/txt/json) |
| `backend/services/folder_api.py` | Folder CRUD, task-to-folder assignment, reorder |
| `backend/services/system_api.py` | GPU info, directory listing |
| `backend/services/retranscribe_service.py` | In-memory re-transcription queue |
| `backend/services/audio_segment_service.py` | Cut audio/video slices with ffmpeg |
| `backend/services/burn_in_service.py` | Burn subtitles into video via ffmpeg |
| `backend/services/diarization_service.py` | Speaker diarization (pyannote.audio) |
| `backend/services/transcription_launcher.py` | `create_task_entry()` + `submit_transcription()` |
| `backend/services/transcription_orchestrator.py` | `resolve_output_directory`, `finalize_task_success` |
| `backend/services/transcription_progress.py` | `build_status_callback`, `finalize_task_failure`, step estimation |
| `backend/services/upload_preprocessing.py` | Filename validation, file save helper |
| `backend/services/url_preprocessing.py` | URL download pre-step |
| `backend/services/progress_policy.py` | Progress message / next-state pure helpers |
| `backend/shared/engine_routing.py` | Dispatches `transcribe_audio` to the right engine |
| `backend/shared/transcription_pipeline.py` | Common output-file writers (SRT/VTT/TXT/JSON) |
| `backend/shared/transcribe_helpers.py` | `format_timestamp`, `check_gpu` |
| `backend/shared/video_utils.py` | ffmpeg mp4 conversion for browser preview |
| `backend/shared/media_config.py` | Canonical supported-extensions sets + MIME map |
| `backend/shared/download_helpers.py` | yt-dlp option builder |
| `backend/shared/split_audio_helpers.py` | Split long audio into segments |
| `backend/shared/text_processing.py` | Post-processing text utilities |
| `backend/shared/llm_postprocess.py` | OpenAI-compatible subtitle enhance + summarize |
| `frontend-react/src/App.tsx` | Router + React Query root |
| `frontend-react/src/api/client.ts` | All REST + SSE + streaming calls |
| `frontend-react/src/stores/` | Zustand stores: `editor-store`, `theme-store`, `toast-store` |
| `frontend-react/src/hooks/` | React Query hooks prefixed `use-*.ts` |
| `frontend-react/src/pages/` | `HomePage.tsx`, `EditorPage.tsx` |
| `frontend-react/src/components/` | Feature-grouped UI (editor/, layout/, transcription/, ui/) |
| `frontend-react/src/types/api.ts` | All shared TypeScript interfaces |
| `tests/` | Pytest tests (`test_<module>.py`) |

## Naming Conventions
| Kind | Convention | Example |
|---|---|---|
| Python file | `snake_case.py` | `transcription_launcher.py` |
| Python function | `snake_case`, verb-first | `build_status_callback`, `finalize_task_success` |
| Python private helper | `_leading_underscore` | `_detect_max_workers`, `_apply_llm_enhancement` |
| Python class | `PascalCase` | `TaskPersistence`, `SubtitleService` |
| Pydantic request/response | `<Entity><Role>` | `TranscriptionRequest`, `SubtitleExportRequest` |
| Python constant / module singleton | `UPPER_SNAKE_CASE` or `_leading_underscore` | `FUNASR_MODEL_NAMES`, `_transcription_executor` |
| TS React component file | `PascalCase.tsx` | `SubtitleRow.tsx`, `VideoPlayer.tsx` |
| TS non-component file | `kebab-case.ts` | `editor-store.ts`, `use-task-stream.ts` |
| TS hook | `useCamelCase` | `useEditorStore`, `useTaskStream` |
| TS interface | `PascalCase`, no `I` prefix | `Subtitle`, `TaskResult` |
| Test file | `test_<module>.py`, `test_<behavior>()` | `test_transcription_orchestrator.py` |
| Python logger name | string literal matching module purpose | `logger = logging.getLogger("subtitle_api")` |
| API route prefix | kebab inside, underscore-free | `/api/subtitles`, `/api/folders`, `/transcribe/batch/urls` |

## Compact Quick-Reference

**Error handling.** Raise `fastapi.HTTPException(status_code=..., detail="...")` at API boundaries (see `task_api.py:27`). For validation helpers return `(bool, error_msg)` tuples (see `upload_preprocessing.py:8`). Inside workers catch broad `Exception`, log with `logger.error(..., exc_info=True)`, then call `finalize_task_failure()` (see `app.py:373`). Use `logger.warning(...)` for non-fatal failures that should not abort the main flow.

**Logging.** Root config is in `backend/app.py` (`basicConfig` with StreamHandler + FileHandler → `whisper_app.log`). Every module declares its own logger: `logger = logging.getLogger("<name>")`. Both `%s` and f-string formatting are accepted; prefer `%s` for hot paths. Always pass `exc_info=True` when logging a caught exception.

**Configuration.** Environment variables are loaded once in `backend/app.py` via `load_dotenv()` at the top of the file. Read new values through `os.environ.get("NAME", default)`. `DATABASE_URL` is read in `backend/database.py`; `MAX_TRANSCRIPTION_WORKERS` in `backend/app.py:_detect_max_workers`. See `.dev/config-reference.md` for the full list.

## Common Tasks

### Add a new REST endpoint
1. Pick the correct router file under `backend/services/` (create a new one only if the domain is genuinely new).
2. Define Pydantic request/response models inline at the top of the file, matching the style in `folder_api.py`.
3. Use `@router.<method>("/path")` with a route-matching `async def` handler.
4. Access shared state only via the injector: e.g. `tasks = get_task_registry()`.
5. Raise `HTTPException` for 4xx; let the framework handle 500s (they are still logged because of worker-level `logger.error(..., exc_info=True)`).
6. If you added a new router, also: `app.include_router(new_router)` in `backend/app.py`, and add a `set_*_registry()` wiring call below the `app.include_router(...)` block.
7. Add/extend a test in `tests/test_<module>_api_routes.py` using `fastapi.testclient.TestClient`.

### Add a new Python module
1. Place pure helpers in `backend/shared/`; domain services in `backend/services/`.
2. Add `logger = logging.getLogger("<module_name>")` at the top.
3. Use keyword-only args (`def foo(*, ...)`) for multi-parameter public helpers, mirroring `transcription_progress.build_status_callback`.
4. Add a companion `tests/test_<module>.py` file.
5. If the new module is imported by something in `backend/services/` or `backend/shared/`, make sure flake8 will pick it up (the CI scope already covers both directories).

### Add a new frontend API method
1. Add the TypeScript types to `frontend-react/src/types/api.ts`.
2. Add a method to the `api` object in `frontend-react/src/api/client.ts` using the existing `request<T>()` helper for JSON endpoints.
3. If it is a long-running query, write a hook in `frontend-react/src/hooks/use-<name>.ts` using `@tanstack/react-query`.
4. For streaming endpoints, follow the generator pattern in `api.enhanceSubtitlesStream`.

### Add a new transcription engine
1. Create `backend/<engine>_transcribe.py` with a `transcribe_audio(**kwargs)` function that returns the same dict shape (`{"txt": ..., "srt": ..., "json": ...}`) as the existing engines.
2. Register model name aliases in `backend/shared/engine_routing.py` (add to `FUNASR_MODEL_NAMES` or extend the dispatch).
3. Reuse `backend/shared/transcription_pipeline.py` helpers for output file writing.

## Data Flow

```
Browser ── POST /transcribe/upload ─► app.py route handler
                                          │
                                          ├─ validate_upload_filename
                                          ├─ save_uploaded_file    (uploads/{task_id}_{name})
                                          ├─ create_task_entry     (in-memory tasks dict)
                                          ├─ save_task_to_disk     (TaskPersistence → DB)
                                          ├─ submit_transcription  (ThreadPoolExecutor)
                                          └─ 200 {task_id}

    ┌─── worker thread ─── process_transcription(task_id) ───────────────┐
    │  resolve_output_directory  → outputs/{task_id}/                    │
    │  prepare_source_video_for_preview (ffmpeg mp4)                     │
    │  build_status_callback  (updates task + DB on each tick)           │
    │  engine_routing.transcribe_audio → Qwen3-ASR or FunASR             │
    │  _apply_llm_enhancement (optional)                                 │
    │  finalize_task_success / finalize_task_failure                     │
    │  save_task_to_disk                                                 │
    └────────────────────────────────────────────────────────────────────┘

Browser ── GET /tasks/{id}/stream (SSE) ─► task_api.event_generator
                                              │ polls tasks dict every 500ms
                                              └─ yields JSON snapshot until terminal
Browser ── GET /api/subtitles/{id}       ─► subtitle_api loads outputs/{task_id}/*.json
Browser ── GET /download/{id}/{type}     ─► download_api streams result file
```

## Code Quality
- Code must compile / type-check without errors: valid Python imports; TypeScript must pass `tsc -b` (part of `npm run build`).
- Match existing patterns in the same directory before inventing new ones.
- Tests: every new public function in `backend/services/` or `backend/shared/` needs a focused unit test using `SimpleNamespace` / `monkeypatch`. Isolate module state via `sys.modules.pop()` if the module has import-time side effects.
- Lint: flake8 runs against `tests/`, `backend/shared/`, `backend/services/`, `backend/models.py`, `backend/task_persistence.py` with `max-line-length=88`. `backend/app.py` and engine files are outside that scope; new code placed there is lint-free by policy but should still stay within 88 cols.
- CI (`.github/workflows/ci.yml`, windows-latest): installs dev deps + pinned `pydantic==2.11.9 fastapi==0.117.1 httpx==0.28.1`, runs flake8, runs `pytest tests/ -q`. Frontend is not built in CI; run the frontend check locally when touching `frontend-react/`.

## Git Commit Style
Format observed in history: `<type>[optional scope]: <imperative summary>`.
- `feat:` new user-visible capability
- `fix:` bug fix
- `refactor:` behavior-preserving code change
- `test:` test-only change
- `chore:` tooling, deps, build
- `docs:` documentation only
Keep subject ≤72 chars, imperative voice. Add body paragraphs for non-trivial changes.

## Working with This Repo
- After modifying code, run the relevant verification command BEFORE reporting completion.
- If backend files changed: run backend test + lint.
- If frontend files changed: run frontend check.
- If API interfaces changed: verify BOTH backend and frontend.
- If unsure about a pattern, check existing files in the same directory before inventing a new approach.
- When a task spans multiple steps, update PROGRESS.md after each step.

## Deep References
| File | Read when |
|---|---|
| `.dev/architecture.md` | Adding cross-cutting concerns, debugging concurrency issues, understanding task lifecycle |
| `.dev/api-reference.md` | Adding/modifying an endpoint, integrating a new client |
| `.dev/coding-style.md` | Before opening a PR; when writing new modules/tests |
| `.dev/function-index.md` | Looking for an existing helper before writing a new one |
| `.dev/config-reference.md` | Changing environment variables, Docker config, DB connection |
| `.dev/UPDATE_GUIDE.md` | Keeping this instruction layer in sync after refactors |
| `.dev/scripts/diff-summary.sh` | Producing a compact summary of outstanding changes |
| `.dev/scripts/verify.sh` | Running the full check from Section 1 |
| `.dev/exec-plans/templates/exec-plan-template.md` | Starting a new multi-step plan |
| `.dev/tool-access.md` | Before running shell commands, dependency installs, or touching infrastructure files |

## State Management
- Before starting a multi-step task: check `.dev/exec-plans/active/` for existing plans. Create one if the task has 3+ steps.
- At end of each session: update `PROGRESS.md` with current state.
- At start of each session: read `PROGRESS.md` and active exec-plans.
- When a plan is complete: move it to `.dev/exec-plans/completed/`.
- Decision rationale must be recorded — future sessions need to know WHY a choice was made, not just WHAT was chosen.

## Safety / Tool Access
- Full policy lives in `.dev/tool-access.md`. Read it before running shell commands or touching infrastructure files.
- Never modify `.env`, secrets, CI files (`.github/**`), `Dockerfile`, `docker-compose.yml`, `.flake8`, or `pyproject.toml` without explicit user approval.
- Never run destructive DB ops, `git push --force`, or install a dep without updating its manifest.
- Always run `git diff --cached` before committing; abort if secrets appear.
- When in doubt, stop and ask the human.
