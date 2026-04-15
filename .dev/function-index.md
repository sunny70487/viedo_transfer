# Function Index — by Developer Intent

## I need to create/manage transcription tasks

| Function | Signature | Purpose | File |
|---|---|---|---|
| `create_task_entry` | `(*, tasks, save_task, source_name, batch_id=None)` | Create a new task in the registry | `services/transcription_launcher.py` |
| `submit_transcription` | `(*, executor, target, task_id, file_path, request) → Future` | Submit task to thread pool | `services/transcription_launcher.py` |
| `process_transcription` | `(task_id, file_path, request)` | Main worker — downloads, transcribes, saves | `app.py` |
| `save_task_to_disk` | `(task: Task)` | Persist task to database | `app.py` |

## I need to run ASR transcription

| Function | Signature | Purpose | File |
|---|---|---|---|
| `transcribe_audio` | `(**kwargs) → Dict[str, str]` | Unified entry — routes to correct engine | `shared/engine_routing.py` |
| `_qwen3_transcribe` | `(**kwargs)` | Qwen3-ASR engine | `qwen3_asr_transcribe.py` |
| `_funasr_transcribe` | `(**kwargs)` | FunASR engine | `funasr_transcribe.py` |

**Decision guide**: Always call `engine_routing.transcribe_audio()` — it auto-routes based on `model_size`. Direct engine calls only for debugging.

## I need to handle task state transitions

| Function | Signature | Purpose | File |
|---|---|---|---|
| `finalize_task_success` | `(*, task, transcription_results, output_directory, now)` | Mark task completed with results | `services/transcription_orchestrator.py` |
| `finalize_task_failure` | `(*, task, error, now)` | Mark task as failed | `services/transcription_progress.py` |
| `build_status_callback` | `(*, task, save_task) → Callable` | Create progress callback for engines | `services/transcription_progress.py` |
| `resolve_output_directory` | `(*, request, task_id, output_root) → str` | Determine output path | `services/transcription_orchestrator.py` |

## I need to work with task persistence (database)

| Function | Signature | Purpose | File |
|---|---|---|---|
| `TaskPersistence.save_task` | `(task_id: str, task_data: dict) → bool` | Upsert task to DB | `task_persistence.py` |
| `TaskPersistence.load_all_tasks` | `() → Dict[str, Any]` | Load all tasks from DB | `task_persistence.py` |
| `TaskPersistence.delete_task` | `(task_id: str) → bool` | Delete task from DB | `task_persistence.py` |
| `TaskPersistence.initialize_tasks` | `() → Dict[str, Any]` | Init DB + load/migrate/rebuild | `task_persistence.py` |
| `TaskPersistence.scan_and_rebuild_tasks` | `() → Dict[str, Any]` | Rebuild from filesystem | `task_persistence.py` |
| `init_db` | `()` | Create tables if needed | `database.py` |

## I need to handle file uploads

| Function | Signature | Purpose | File |
|---|---|---|---|
| `validate_upload_filename` | `(filename: str) → (bool, Optional[str])` | Check extension validity | `services/upload_preprocessing.py` |
| `save_uploaded_file` | `(*, upload_dir, task_id, upload_file) → Path` | Save upload to disk | `services/upload_preprocessing.py` |
| `build_transcription_request` | `(*, request_cls, **kwargs) → TranscriptionRequest` | Construct request from form data | `services/upload_preprocessing.py` |

## I need to handle URL downloads

| Function | Signature | Purpose | File |
|---|---|---|---|
| `prepare_url_input` | `(*, task, request, output_directory, download) → str` | Download from URL, update task progress | `services/url_preprocessing.py` |
| `download_from_url` | `(url, output_dir, download_format, verbose, video_quality) → (str, str)` | yt-dlp download wrapper | `funasr_transcribe.py` |

## I need to work with subtitles (load/save/edit)

| Function | Signature | Purpose | File |
|---|---|---|---|
| `SubtitleService.load_subtitle_data` | `(task_id, tasks) → SubtitleCollection` | Load from JSON → Pydantic models | `services/subtitle_api.py` |
| `SubtitleService.save_subtitle_data` | `(task_id, collection, tasks) → dict` | Save as `_updated.json` | `services/subtitle_api.py` |
| `SubtitleService.search_subtitles` | `(task_id, request, tasks) → SubtitleSearchResult` | Text/regex search | `services/subtitle_api.py` |
| `SubtitleCollection.split_subtitle` | `(index, split_time) → bool` | Split at timestamp | `models.py` |
| `SubtitleCollection.merge_subtitles` | `(start_index, end_index) → bool` | Merge range | `models.py` |
| `SubtitleCollection.add_subtitle` | `(subtitle) → None` | Append subtitle | `models.py` |
| `SubtitleCollection.remove_subtitle` | `(index) → bool` | Remove by index | `models.py` |

## I need to convert subtitle formats

| Function | Signature | Purpose | File |
|---|---|---|---|
| `SubtitleConverter.convert` | `(collection, format, output_file, encoding, **opts) → str` | Convert + write to file | `services/subtitle_converter.py` |
| `SubtitleConverter.is_format_supported` | `(format) → bool` | Check format support | `services/subtitle_converter.py` |
| `SubtitleConverter.get_supported_formats` | `() → list` | List all formats | `services/subtitle_converter.py` |
| `build_srt_entry` | `(index, start, end, text) → str` | Single SRT block | `shared/transcription_pipeline.py` |
| `build_vtt_entry` | `(start, end, text) → str` | Single VTT block | `shared/transcription_pipeline.py` |

## I need to process/transform text

| Function | Signature | Purpose | File |
|---|---|---|---|
| `convert_to_traditional` | `(text: str) → str` | Simplified → Traditional Chinese | `shared/text_processing.py` |
| `strip_punctuation` | `(text: str) → str` | Remove all punctuation | `shared/text_processing.py` |
| `smart_strip_punctuation` | `(text: str) → str` | Remove only trailing periods | `shared/text_processing.py` |
| `swap_first_two_lines` | `(text: str) → str` | Swap line 1 ↔ line 2 (bilingual) | `shared/text_processing.py` |
| `split_long_segments` | `(segments_json, words_data, max_duration=15.0)` | Split at word boundaries | `shared/text_processing.py` |
| `format_timestamp` | `(seconds, format="srt") → str` | Seconds → SRT/VTT timestamp | `shared/transcribe_helpers.py` |

## I need LLM subtitle enhancement

| Function | Signature | Purpose | File |
|---|---|---|---|
| `enhance_subtitles` | `(segments, *, api_key, base_url, model, content_hint, status_callback)` | Full batch enhancement | `shared/llm_postprocess.py` |
| `merge_short_segments` | `(segments, target_chars=20, max_chars=30) → list` | Merge short + resplit long | `shared/llm_postprocess.py` |
| `resplit_long_segments` | `(segments, target_chars=20, max_chars=30) → list` | Split at punctuation marks | `shared/llm_postprocess.py` |
| `build_translate_prompt` | `(target_language: str) → str` | Build translation system prompt | `shared/llm_postprocess.py` |
| `_call_llm` | `(client, model, lines, content_hint, ...) → List[str]` | Call LLM with retry logic | `shared/llm_postprocess.py` |
| `_chunk_lines` | `(lines, max_lines=80, max_chars=6000) → List[List[int]]` | Split into API-sized batches | `shared/llm_postprocess.py` |

**Decision guide**: Use `enhance_subtitles()` for batch processing in background tasks. Use the SSE endpoint `POST /api/subtitles/enhance` for interactive frontend use.

## I need to handle speaker diarization

| Function | Signature | Purpose | File |
|---|---|---|---|
| `run_diarization` | `(audio_path, num_speakers=None, ...) → List[Tuple]` | Run pyannote diarization | `services/diarization_service.py` |
| `assign_speakers_to_segments` | `(asr_segments, diarization_segments) → list` | Match speakers to ASR segments | `services/diarization_service.py` |

## I need to handle re-transcription

| Function | Signature | Purpose | File |
|---|---|---|---|
| `get_retranscribe_service` | `() → RetranscribeService` | Get/create singleton service | `services/retranscribe_service.py` |
| `RetranscribeService.create_retranscribe_task` | `(request) → str` | Create + submit re-transcribe job | `services/retranscribe_service.py` |
| `AudioSegmentService.extract_segment` | `(request) → result` | Extract audio segment via FFmpeg | `services/audio_segment_service.py` |

## I need to burn subtitles into video

| Function | Signature | Purpose | File |
|---|---|---|---|
| `start_burn_in` | `(task_id, subtitles, video_path, output_dir, **style) → str` | Start burn-in thread | `services/burn_in_service.py` |
| `get_burn_in_task` | `(burn_id) → Optional[dict]` | Check burn-in progress | `services/burn_in_service.py` |

## I need to check system/GPU status

| Function | Signature | Purpose | File |
|---|---|---|---|
| `check_gpu` | `(torch_module=None) → dict` | GPU availability + memory info | `shared/transcribe_helpers.py` |
| `resolve_device` | `(device: str, verbose=False) → str` | Normalize 'auto'/'cuda' → 'cuda:0'/'cpu' | `shared/transcription_pipeline.py` |
| `is_supported_media_file` | `(path: str) → bool` | Check file extension | `shared/media_config.py` |
| `get_media_type` | `(path: str) → str` | Get MIME type for extension | `shared/media_config.py` |

## I need to write transcription output files

| Function | Signature | Purpose | File |
|---|---|---|---|
| `write_output_files` | `(base_path, filename, format, ...) → dict` | Write txt/srt/vtt/json | `shared/transcription_pipeline.py` |
| `init_output_paths` | `(audio_path, output_dir) → (Path, str)` | Setup output directory | `shared/transcription_pipeline.py` |
| `init_buffers` | `() → dict` | Fresh accumulator buffers | `shared/transcription_pipeline.py` |
