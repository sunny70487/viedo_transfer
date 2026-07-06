# Function Index (by Intent)

Search by "I need to …" before writing new code. Locations use `module:function` notation; files are relative to repo root.

## I need to create or submit a transcription task

| Intent | Use | Why |
|---|---|---|
| Create a new task row in the in-memory registry + DB | `backend/services/transcription_launcher.py:create_task_entry(*, tasks, save_task, source_name, batch_id=None, folder_id=None, task_cls=None)` | Handles UUID, persistence, timestamps |
| Submit a prepared job to the thread pool | `backend/services/transcription_launcher.py:submit_transcription(*, executor, target, task_id, file_path, request)` | Single entry-point for scheduling work |
| Run the actual transcription call | `backend/shared/engine_routing.py:transcribe_audio(**kwargs)` | Picks Qwen3 / FunASR based on `model_size` |

Pick `create_task_entry` over hand-rolling a `Task(...)` — it ensures the DB row exists before any worker runs.

## I need to report progress / finalize / fail a task

| Intent | Use |
|---|---|
| Build a status callback (used by engines) | `backend/services/transcription_progress.py:build_status_callback(*, task, save_task)` |
| Estimate total steps for split transcription | `backend/services/transcription_progress.py:estimate_total_steps(...)` |
| Mark a task as successful | `backend/services/transcription_orchestrator.py:finalize_task_success(*, task, transcription_results, output_directory, now)` |
| Mark a task as failed | `backend/services/transcription_progress.py:finalize_task_failure(*, task, error, now)` |
| Compute next progress percent + message | `backend/services/progress_policy.py:next_progress_state(...)` |
| Resolve where to place output files | `backend/services/transcription_orchestrator.py:resolve_output_directory(*, request, task_id, output_root)` |

Always call `save_task_to_disk(task)` after mutating a `Task` outside the status callback — the callback only persists on message/progress change.

## I need to persist / load / delete tasks

| Intent | Use |
|---|---|
| Save task snapshot | `backend/task_persistence.py:TaskPersistence.save_task(task_id, task_data)` |
| Load all tasks at startup | `backend/task_persistence.py:TaskPersistence.load_all_tasks()` |
| Full startup init (DB create → load → migrate → rebuild) | `backend/task_persistence.py:TaskPersistence.initialize_tasks()` |
| Delete task row | `backend/task_persistence.py:TaskPersistence.delete_task(task_id)` |
| Rebuild tasks from `outputs/` if DB empty | `backend/task_persistence.py:TaskPersistence.scan_and_rebuild_tasks()` |
| Migrate legacy `tasks_data.json` | `backend/task_persistence.py:TaskPersistence._migrate_from_json()` (internal) |

## I need to read / write subtitle data

| Intent | Use |
|---|---|
| Load subtitles for a completed task | `backend/services/subtitle_api.py:SubtitleService.load_subtitle_data(task_id, tasks)` |
| Save subtitle collection to `<id>_updated.json` | `backend/services/subtitle_api.py:SubtitleService.save_subtitle_data(...)` |
| Write SRT/VTT/TXT/JSON outputs | `backend/shared/transcription_pipeline.py:write_output_files(...)` |
| Build a single SRT/VTT entry | `backend/shared/transcription_pipeline.py:build_srt_entry(...)` / `build_vtt_entry(...)` |
| Format a timestamp | `backend/shared/transcribe_helpers.py:format_timestamp(seconds, format="srt"|"vtt")` |

Load path prefers `<id>_updated.json` over the original engine output. Don't bypass this — it preserves edits.

## I need to validate / save an uploaded file

| Intent | Use |
|---|---|
| Validate filename extension | `backend/services/upload_preprocessing.py:validate_upload_filename(filename)` |
| Persist uploaded file to `uploads/` | `backend/services/upload_preprocessing.py:save_uploaded_file(*, upload_dir, task_id, upload_file)` |
| Build a `TranscriptionRequest` from Form fields | `backend/services/upload_preprocessing.py:build_transcription_request(*, request_cls, **kwargs)` |
| Decide if a path is a supported media file | `backend/shared/media_config.py:is_supported_media_file(path)` |
| Get MIME type for a file path | `backend/shared/media_config.py:get_media_type(path)` |

## I need to download media from a URL

| Intent | Use |
|---|---|
| Complete URL input step (progress + download) | `backend/services/url_preprocessing.py:prepare_url_input(*, task, request, output_directory, download)` |
| Build yt-dlp options | `backend/shared/download_helpers.py:build_yt_dlp_options(...)` |
| Produce a safe filename title | `backend/shared/download_helpers.py:build_safe_title(title, fallback_name=None)` |

## I need to work with video files

| Intent | Use |
|---|---|
| Check if path is a video | `backend/shared/video_utils.py:is_video_file(path)` |
| Convert any video to browser-friendly mp4 | `backend/shared/video_utils.py:prepare_source_video_for_preview(*, source_path, output_dir, task_id, status_callback=None)` |
| Build the raw ffmpeg command list | `backend/shared/video_utils.py:build_mp4_conversion_command(source, target)` |
| Add a transcoded mp4 alongside outputs | `backend/shared/video_utils.py:maybe_prepare_video_output(...)` |

## I need to expose / consume GPU info

| Intent | Use |
|---|---|
| Get structured GPU info | `backend/shared/transcribe_helpers.py:check_gpu(torch_module=None)` |
| Decide how many workers to run | `backend/app.py:_detect_max_workers()` (called once at import) |

## I need to post-process subtitles via an LLM

| Intent | Use |
|---|---|
| Enhance subtitles (fix ASR mistakes) | `backend/shared/llm_postprocess.py:enhance_subtitles(segments, *, api_key, base_url, model, content_hint=None, status_callback=None, mode="enhance")` |
| Translate subtitles | `enhance_subtitles(..., mode="translate", target_language="...")` |
| Merge short segments before LLM | `backend/shared/llm_postprocess.py:merge_short_segments(segments)` |
| Re-split long sentences after LLM | `backend/shared/llm_postprocess.py:resplit_long_segments(segments)` |
| Summarize + chapterize | `backend/shared/llm_postprocess.py:summarize_subtitles(segments, *, api_key, base_url, model, content_hint=None)` |
| Rewrite localhost URL (Docker) | `backend/shared/llm_postprocess.py:_rewrite_localhost_url(url)` (private; mirror in `app.py`) |

## I need to manage folders

| Intent | Use |
|---|---|
| Any folder CRUD | `backend/services/folder_api.py` router |
| Set the tasks registry that folder endpoints use | `backend/services/folder_api.py:set_folder_task_registry(registry)` |
| Reorder folders or tasks | `PUT /api/folders/reorder` / `PUT /api/folders/{id}/tasks/reorder` |

## I need to call the backend from the frontend

| Intent | Use |
|---|---|
| Any REST call | `frontend-react/src/api/client.ts:api.<method>(...)` |
| Task SSE stream | `frontend-react/src/hooks/use-task-stream.ts:useTaskStream(taskId, enabled?)` |
| Query all tasks | `frontend-react/src/hooks/use-tasks.ts` |
| Query a single task | `frontend-react/src/hooks/use-task.ts` |
| Load subtitles | `frontend-react/src/hooks/use-subtitles.ts` |
| List folders | `frontend-react/src/hooks/use-folders.ts` |
| GPU info | `frontend-react/src/hooks/use-gpu-info.ts` |
| LLM settings persistence | `frontend-react/src/hooks/use-llm-settings.ts` |
| Toast notifications | `frontend-react/src/hooks/use-task-notifications.ts` + `stores/toast-store.ts` |

## Decision Guides

### "Do I submit via `executor.submit` or just `await` the work?"
- Blocking (CPU/GPU/ffmpeg/torch): submit to `_transcription_executor` via `submit_transcription`.
- I/O bound async-capable (httpx): use `await` inside the async route directly.

### "Do I load subtitles from `json` or `updated_json`?"
- Use `SubtitleService.load_subtitle_data`; it already prefers `updated_json`. Do not reimplement.

### "Should this constant go in `media_config.py` or somewhere local?"
- If it is a supported extension or MIME type: `backend/shared/media_config.py`. Everywhere else should import from there.

### "Do I call the engine directly?"
- No. Always go through `backend.shared.engine_routing.transcribe_audio(**kwargs)`. If adding a new engine, register its model names in `FUNASR_MODEL_NAMES` or extend the dispatch there.

### "Do I need `build_status_callback`?"
- Yes, any engine or long task that reports progress must accept a `status_callback(message=?, progress=?, segment=?)` and call it. The stock builder already persists state.

### "Where do I put a helper that has no FastAPI dependency?"
- `backend/shared/`. If it uses `HTTPException` or router-specific types, it belongs in `backend/services/`.
