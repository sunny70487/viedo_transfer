#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from dotenv import load_dotenv

load_dotenv()

import json
import logging
import platform
import shutil
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Any, List, Optional

import uvicorn
from fastapi import FastAPI, Form, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.funasr_transcribe import download_from_url, check_gpu
from backend.models import (
    Word,
    Subtitle,
    SubtitleCollection,
    RetranscribeRequest,
    VideoInfo,
    SubtitleMetadata,
    RetranscribeTask,
    SubtitleExportRequest,
)
from backend.shared.engine_routing import transcribe_audio
from backend.task_persistence import TaskPersistence
from backend.shared.media_config import SUPPORTED_MEDIA_EXTENSIONS
from backend.services.download_api import (
    router as download_router,
    set_download_task_registry,
)
from backend.services.subtitle_api import (
    router as subtitle_router,
    set_task_store,
    TaskStore,
)
from backend.services.system_api import router as system_router
from backend.services.task_api import router as task_router, set_task_registry
from backend.services.folder_api import (
    router as folder_router,
    set_folder_task_registry,
)
from backend.services.transcription_launcher import (
    create_task_entry,
    submit_transcription,
)
from backend.services.transcription_orchestrator import (
    finalize_task_success,
    resolve_output_directory,
)
from backend.services.transcription_progress import (
    build_status_callback,
    finalize_task_failure,
)
from backend.services.upload_preprocessing import (
    validate_upload_filename,
    save_uploaded_file,
    build_transcription_request,
)
from backend.services.url_preprocessing import prepare_url_input

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("whisper_app.log")],
)
logger = logging.getLogger("whisper_app")

# ---------------------------------------------------------------------------
# Transcription thread-pool (controls concurrent GPU workloads)
# ---------------------------------------------------------------------------

def _detect_max_workers() -> int:
    """
    Auto-detect the optimal number of concurrent transcription workers.

    GPU mode  — estimate from total VRAM (≈3.5 GB per ASR model instance),
                at least 2 workers per GPU, capped at 3× GPU count.
    CPU mode  — half the logical cores, capped at 4.

    Override with MAX_TRANSCRIPTION_WORKERS env var.
    """
    override = os.environ.get("MAX_TRANSCRIPTION_WORKERS")
    if override:
        return max(1, int(override))

    try:
        import torch

        if torch.cuda.is_available() and torch.cuda.device_count() > 0:
            gpu_count = torch.cuda.device_count()
            total_vram_gb = 0.0
            for i in range(gpu_count):
                props = torch.cuda.get_device_properties(i)
                total_vram_gb += props.total_memory / (1024 ** 3)

            vram_per_worker_gb = 2
            estimated = max(2, int(total_vram_gb / vram_per_worker_gb))
            workers = min(estimated, gpu_count * 3)
            logger.info(
                "GPU detected: %d device(s), %.1f GB total VRAM → %d worker(s)",
                gpu_count,
                total_vram_gb,
                workers,
            )
            return workers
    except Exception:
        pass

    cpu_count = os.cpu_count() or 4
    workers = min(4, max(1, cpu_count // 2))
    logger.info("CPU mode: %d cores → %d worker(s)", cpu_count, workers)
    return workers


MAX_WORKERS = _detect_max_workers()
_transcription_executor = ThreadPoolExecutor(
    max_workers=MAX_WORKERS, thread_name_prefix="transcribe"
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_BASE_DIR = Path(__file__).resolve().parent.parent
_REACT_DIST = _BASE_DIR / "frontend-react" / "dist"

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
TEMP_DIR = Path("temp")

for directory in [UPLOAD_DIR, OUTPUT_DIR, TEMP_DIR]:
    directory.mkdir(exist_ok=True, parents=True)

# ---------------------------------------------------------------------------
# In-memory task registry (source of truth at runtime)
# ---------------------------------------------------------------------------
tasks: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class Task(BaseModel):
    id: str
    status: str
    progress: float = 0.0
    message: str = ""
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    start_time: float
    end_time: Optional[float] = None
    source_name: Optional[str] = None
    batch_id: Optional[str] = None
    folder_id: Optional[str] = None
    sort_order: float = 0.0
    partial_segments: Optional[List[Dict[str, Any]]] = None
    source_file_path: Optional[str] = None


class TranscriptionRequest(BaseModel):
    url: Optional[str] = None
    model_size: str = "qwen3-asr-1.7b"
    device: str = "auto"
    compute_type: str = "default"
    language: Optional[str] = None
    task: str = "transcribe"
    beam_size: int = 5
    vad_filter: bool = True
    word_timestamps: bool = True
    output_format: str = "srt"
    split_segments: bool = False
    segment_duration: int = 30
    download_format: str = "audio"
    video_quality: str = "best"
    output_dir: Optional[str] = None
    file_path: Optional[str] = None
    speaker_diarization: bool = False
    num_speakers: Optional[int] = None
    llm_enhance: bool = False
    llm_api_key: Optional[str] = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_content_hint: Optional[str] = None
    folder_id: Optional[str] = None


class BatchUrlRequest(BaseModel):
    urls: List[str]
    download_format: str = "audio"
    video_quality: str = "best"
    model_size: str = "qwen3-asr-1.7b"
    device: str = "auto"
    compute_type: str = "default"
    language: Optional[str] = None
    task: str = "transcribe"
    beam_size: int = 5
    vad_filter: bool = True
    word_timestamps: bool = True
    output_format: str = "srt"
    split_segments: bool = False
    segment_duration: int = 30
    speaker_diarization: bool = False
    num_speakers: Optional[int] = None
    llm_enhance: bool = False
    llm_api_key: Optional[str] = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_content_hint: Optional[str] = None
    folder_id: Optional[str] = None


class LlmModelsRequest(BaseModel):
    api_key: str
    base_url: str = "https://api.openai.com/v1"


# ---------------------------------------------------------------------------
# Persistence helper
# ---------------------------------------------------------------------------
def save_task_to_disk(task: Task):
    """Persist the task object to the database."""
    try:
        TaskPersistence.save_task(task.id, task.dict())
    except Exception as e:
        logger.error(f"保存任務 {task.id} 到資料庫時出錯: {str(e)}")


# ---------------------------------------------------------------------------
# Restore persisted tasks on startup
# ---------------------------------------------------------------------------
logger.info("正在初始化任務數據...")
persisted_tasks = TaskPersistence.initialize_tasks()
for task_id, task_data in persisted_tasks.items():
    try:
        if (
            not task_data.get("source_name")
            and task_data.get("result")
            and task_data["result"].get("files")
        ):
            for file_type, file_path in task_data["result"]["files"].items():
                if file_type in ("txt", "srt", "json") and file_path:
                    basename = os.path.basename(file_path)
                    prefix = f"{task_id}_"
                    if basename.startswith(prefix):
                        name_part = basename[len(prefix):]
                        name_part = os.path.splitext(name_part)[0]
                        if name_part.endswith("_segments"):
                            name_part = name_part[: -len("_segments")]
                        if name_part.endswith("_converted"):
                            name_part = name_part[: -len("_converted")]
                        if name_part:
                            task_data["source_name"] = name_part
                            break
        task = Task(**task_data)
        tasks[task_id] = task
        logger.info(f"已恢復任務: {task_id} (狀態: {task.status})")
    except Exception as e:
        logger.error(f"恢復任務 {task_id} 時出錯: {str(e)}", exc_info=True)
logger.info(f"任務數據初始化完成，共載入 {len(tasks)} 個任務")


# ---------------------------------------------------------------------------
# Background transcription worker
# ---------------------------------------------------------------------------
def _apply_llm_enhancement(
    transcription_results: Dict[str, Any],
    request: TranscriptionRequest,
    status_callback,
):
    """Read the JSON output, merge short segments, enhance with LLM, and rewrite all output files."""
    from backend.shared.llm_postprocess import enhance_subtitles, merge_short_segments, resplit_long_segments
    from backend.shared.transcription_pipeline import (
        build_srt_entry,
        build_vtt_entry,
    )

    json_path = transcription_results.get("json")
    if not json_path or not os.path.isfile(json_path):
        logger.warning("No JSON output found — skipping LLM enhancement")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    segments = data.get("segments", [])
    if not segments:
        return

    orig_count = len(segments)
    segments = merge_short_segments(segments)
    if len(segments) < orig_count:
        logger.info(
            "Merged %d short segments (%d → %d)",
            orig_count - len(segments), orig_count, len(segments),
        )

    enhanced = enhance_subtitles(
        segments,
        api_key=request.llm_api_key,
        base_url=request.llm_base_url,
        model=request.llm_model,
        content_hint=request.llm_content_hint,
        status_callback=status_callback,
    )

    enhanced = resplit_long_segments(enhanced)
    data["segments"] = enhanced
    data["text"] = "\n".join(seg["text"] for seg in enhanced if seg.get("text"))

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    txt_path = transcription_results.get("txt")
    if txt_path and os.path.isfile(txt_path):
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(data["text"])

    srt_path = transcription_results.get("srt")
    if srt_path and os.path.isfile(srt_path):
        srt_content = ""
        for idx, seg in enumerate(enhanced, 1):
            srt_content += build_srt_entry(idx, seg["start"], seg["end"], seg["text"])
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

    vtt_path = transcription_results.get("vtt")
    if vtt_path and os.path.isfile(vtt_path):
        vtt_content = "WEBVTT\n\n"
        for seg in enhanced:
            vtt_content += build_vtt_entry(seg["start"], seg["end"], seg["text"])
        with open(vtt_path, "w", encoding="utf-8") as f:
            f.write(vtt_content)


def process_transcription(
    task_id: str, file_path: str = None, request: TranscriptionRequest = None
):
    """Runs inside the thread-pool executor."""
    task = tasks[task_id]
    task.status = "processing"
    task.message = "正在處理轉錄任務..."
    task.progress = 5.0
    save_task_to_disk(task)

    try:
        output_directory = resolve_output_directory(
            request=request,
            task_id=task_id,
            output_root=OUTPUT_DIR,
        )
        os.makedirs(output_directory, exist_ok=True)

        if request.url:
            file_path = prepare_url_input(
                task=task,
                request=request,
                output_directory=output_directory,
                download=download_from_url,
            )
        else:
            task.progress = 30.0

        # Store source path so the video can be served during transcription
        if file_path and os.path.isfile(file_path):
            task.source_file_path = file_path

        task.message = "正在執行轉錄..."

        status_callback = build_status_callback(task=task, save_task=save_task_to_disk)

        transcription_results = transcribe_audio(
            audio_path=file_path,
            model_size=request.model_size,
            device=request.device,
            compute_type=request.compute_type,
            language=request.language,
            task=request.task,
            beam_size=request.beam_size,
            vad_filter=request.vad_filter,
            word_timestamps=request.word_timestamps,
            output_dir=output_directory,
            output_format=request.output_format,
            verbose=True,
            show_in_terminal=False,
            split_segments=request.split_segments,
            segment_duration=request.segment_duration,
            status_callback=status_callback,
            speaker_diarization=request.speaker_diarization,
            num_speakers=request.num_speakers,
        )

        if request.llm_enhance and request.llm_api_key:
            try:
                _apply_llm_enhancement(transcription_results, request, status_callback)
            except Exception as llm_err:
                logger.warning("LLM enhancement failed (non-fatal): %s", llm_err)

        finalize_task_success(
            task=task,
            transcription_results=transcription_results,
            output_directory=output_directory,
            now=time.time(),
        )
        save_task_to_disk(task)

        logger.info(f"任務 {task_id} 完成: {transcription_results}")

    except Exception as e:
        logger.error(f"任務 {task_id} 失敗: {str(e)}", exc_info=True)
        finalize_task_failure(task=task, error=e, now=time.time())
        save_task_to_disk(task)


# ---------------------------------------------------------------------------
# FastAPI lifespan (startup / shutdown)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI):
    src = "env override" if os.environ.get("MAX_TRANSCRIPTION_WORKERS") else "auto-detected"
    logger.info(
        "轉錄工作池已啟動 (max_workers=%d, %s)",
        _transcription_executor._max_workers,
        src,
    )
    yield
    _transcription_executor.shutdown(wait=False)
    logger.info("轉錄工作池已關閉")


# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Whisper 轉錄應用",
    description="使用 Qwen3-ASR 進行音頻轉錄的 Web 應用",
    lifespan=lifespan,
)

if _REACT_DIST.is_dir() and (_REACT_DIST / "assets").is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=str(_REACT_DIST / "assets")),
        name="react-assets",
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/")
async def index():
    """渲染主頁面"""
    index_html = _REACT_DIST / "index.html"
    if not index_html.exists():
        return JSONResponse(
            status_code=503,
            content={"error": "前端尚未建置，請先執行 npm run build"},
        )
    return FileResponse(str(index_html))


@app.post("/transcribe/url")
async def transcribe_from_url(request: TranscriptionRequest):
    """從 URL 創建轉錄任務"""
    if not request.url:
        return JSONResponse(status_code=400, content={"error": "必須提供 URL"})

    task = create_task_entry(
        tasks=tasks,
        save_task=save_task_to_disk,
        source_name=request.url,
        folder_id=request.folder_id,
    )

    submit_transcription(
        executor=_transcription_executor,
        target=process_transcription,
        task_id=task.id,
        file_path=None,
        request=request,
    )

    return {"task_id": task.id}


@app.post("/transcribe/local")
async def transcribe_from_local(request: TranscriptionRequest):
    """從本地文件路徑創建轉錄任務"""
    if not request.file_path:
        return JSONResponse(status_code=400, content={"error": "必須提供本地檔案路徑"})

    if not os.path.exists(request.file_path):
        return JSONResponse(
            status_code=404, content={"error": f"找不到檔案: {request.file_path}"}
        )

    valid_extensions = sorted(SUPPORTED_MEDIA_EXTENSIONS)
    file_ext = os.path.splitext(request.file_path)[1].lower()

    if file_ext not in valid_extensions:
        return JSONResponse(
            status_code=400,
            content={
                "error": f"不支援的檔案格式: {file_ext}。支援的格式: {', '.join(valid_extensions)}"
            },
        )

    task = create_task_entry(
        tasks=tasks,
        save_task=save_task_to_disk,
        source_name=os.path.basename(request.file_path),
    )
    submit_transcription(
        executor=_transcription_executor,
        target=process_transcription,
        task_id=task.id,
        file_path=request.file_path,
        request=request,
    )

    return {"task_id": task.id}


@app.post("/transcribe/upload")
async def transcribe_from_upload(
    file: UploadFile = File(...),
    model_size: str = Form("large-v3"),
    device: str = Form("auto"),
    compute_type: str = Form("default"),
    language: Optional[str] = Form(None),
    task: str = Form("transcribe"),
    beam_size: int = Form(5),
    vad_filter: bool = Form(True),
    word_timestamps: bool = Form(True),
    output_format: str = Form("srt"),
    split_segments: bool = Form(False),
    segment_duration: int = Form(30),
    output_dir: Optional[str] = Form(None),
    speaker_diarization: bool = Form(False),
    num_speakers: Optional[int] = Form(None),
    llm_enhance: bool = Form(False),
    llm_api_key: Optional[str] = Form(None),
    llm_base_url: str = Form("https://api.openai.com/v1"),
    llm_model: str = Form("gpt-4o-mini"),
    llm_content_hint: Optional[str] = Form(None),
    folder_id: Optional[str] = Form(None),
):
    """從上傳的文件創建轉錄任務"""
    try:
        valid, error = validate_upload_filename(file.filename)
        if not valid:
            return JSONResponse(status_code=400, content={"error": error})

        task_obj = create_task_entry(
            tasks=tasks,
            save_task=save_task_to_disk,
            source_name=file.filename,
            folder_id=folder_id,
        )
        task_obj.status = "uploading"
        task_obj.message = "正在上傳文件"
        save_task_to_disk(task_obj)

        try:
            file_path = save_uploaded_file(
                upload_dir=UPLOAD_DIR,
                task_id=task_obj.id,
                upload_file=file,
            )
        except Exception as e:
            logger.error(f"保存上傳文件失敗: {str(e)}", exc_info=True)
            return JSONResponse(
                status_code=500, content={"error": f"保存文件時出錯: {str(e)}"}
            )

        request = build_transcription_request(
            request_cls=TranscriptionRequest,
            model_size=model_size,
            device=device,
            compute_type=compute_type,
            language=language,
            task=task,
            beam_size=beam_size,
            vad_filter=vad_filter,
            word_timestamps=word_timestamps,
            output_format=output_format,
            split_segments=split_segments,
            segment_duration=segment_duration,
            output_dir=output_dir,
            speaker_diarization=speaker_diarization,
            num_speakers=num_speakers,
            llm_enhance=llm_enhance,
            llm_api_key=llm_api_key,
            llm_base_url=llm_base_url,
            llm_model=llm_model,
            llm_content_hint=llm_content_hint,
        )

        submit_transcription(
            executor=_transcription_executor,
            target=process_transcription,
            task_id=task_obj.id,
            file_path=str(file_path),
            request=request,
        )

        return {"task_id": task_obj.id}

    except Exception as e:
        logger.error(f"處理上傳請求時出錯: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500, content={"error": f"處理上傳請求時出錯: {str(e)}"}
        )


# ---------------------------------------------------------------------------
# Batch transcription routes
# ---------------------------------------------------------------------------
@app.post("/transcribe/batch/urls")
async def transcribe_batch_urls(request: BatchUrlRequest):
    """一次提交多個 URL 進行批次轉錄"""
    urls = [u.strip() for u in request.urls if u.strip()]
    if not urls:
        return JSONResponse(status_code=400, content={"error": "至少需要提供一個 URL"})
    if len(urls) > 20:
        return JSONResponse(status_code=400, content={"error": "單次批次最多 20 個 URL"})

    batch_id = str(uuid.uuid4())
    task_ids: list[str] = []

    shared_opts = request.model_dump(exclude={"urls"})

    for url in urls:
        task = create_task_entry(
            tasks=tasks,
            save_task=save_task_to_disk,
            source_name=url,
            batch_id=batch_id,
            folder_id=request.folder_id,
        )
        req = TranscriptionRequest(url=url, **shared_opts)
        submit_transcription(
            executor=_transcription_executor,
            target=process_transcription,
            task_id=task.id,
            file_path=None,
            request=req,
        )
        task_ids.append(task.id)

    logger.info("Batch %s created with %d URL task(s)", batch_id, len(task_ids))
    return {"batch_id": batch_id, "task_ids": task_ids}


@app.post("/transcribe/batch/upload")
async def transcribe_batch_upload(
    files: List[UploadFile] = File(...),
    model_size: str = Form("qwen3-asr-1.7b"),
    device: str = Form("auto"),
    compute_type: str = Form("default"),
    language: Optional[str] = Form(None),
    task: str = Form("transcribe"),
    beam_size: int = Form(5),
    vad_filter: bool = Form(True),
    word_timestamps: bool = Form(True),
    output_format: str = Form("srt"),
    split_segments: bool = Form(False),
    segment_duration: int = Form(30),
    output_dir: Optional[str] = Form(None),
    speaker_diarization: bool = Form(False),
    num_speakers: Optional[int] = Form(None),
    llm_enhance: bool = Form(False),
    llm_api_key: Optional[str] = Form(None),
    llm_base_url: str = Form("https://api.openai.com/v1"),
    llm_model: str = Form("gpt-4o-mini"),
    llm_content_hint: Optional[str] = Form(None),
    folder_id: Optional[str] = Form(None),
):
    """一次上傳多個檔案進行批次轉錄"""
    if not files:
        return JSONResponse(status_code=400, content={"error": "至少需要上傳一個檔案"})
    if len(files) > 20:
        return JSONResponse(status_code=400, content={"error": "單次批次最多 20 個檔案"})

    batch_id = str(uuid.uuid4())
    task_ids: list[str] = []
    errors: list[str] = []

    for file in files:
        valid, error = validate_upload_filename(file.filename)
        if not valid:
            errors.append(f"{file.filename}: {error}")
            continue

        display_name = Path(file.filename).name if file.filename else file.filename
        task_obj = create_task_entry(
            tasks=tasks,
            save_task=save_task_to_disk,
            source_name=display_name,
            batch_id=batch_id,
            folder_id=folder_id,
        )
        task_obj.status = "uploading"
        task_obj.message = "正在上傳文件"
        save_task_to_disk(task_obj)

        try:
            file_path = save_uploaded_file(
                upload_dir=UPLOAD_DIR,
                task_id=task_obj.id,
                upload_file=file,
            )
        except Exception as e:
            logger.error("Batch upload – save failed for %s: %s", file.filename, e)
            task_obj.status = "failed"
            task_obj.error = str(e)
            save_task_to_disk(task_obj)
            errors.append(f"{file.filename}: {str(e)}")
            continue

        req = build_transcription_request(
            request_cls=TranscriptionRequest,
            model_size=model_size,
            device=device,
            compute_type=compute_type,
            language=language,
            task=task,
            beam_size=beam_size,
            vad_filter=vad_filter,
            word_timestamps=word_timestamps,
            output_format=output_format,
            split_segments=split_segments,
            segment_duration=segment_duration,
            output_dir=output_dir,
            speaker_diarization=speaker_diarization,
            num_speakers=num_speakers,
            llm_enhance=llm_enhance,
            llm_api_key=llm_api_key,
            llm_base_url=llm_base_url,
            llm_model=llm_model,
            llm_content_hint=llm_content_hint,
        )

        submit_transcription(
            executor=_transcription_executor,
            target=process_transcription,
            task_id=task_obj.id,
            file_path=str(file_path),
            request=req,
        )
        task_ids.append(task_obj.id)

    logger.info("Batch %s created with %d file task(s)", batch_id, len(task_ids))
    result: Dict[str, Any] = {"batch_id": batch_id, "task_ids": task_ids}
    if errors:
        result["errors"] = errors
    return result


@app.post("/transcribe/batch/folder-upload")
async def transcribe_folder_upload(
    files: List[UploadFile] = File(...),
    relative_paths: str = Form("[]"),
    folder_name: str = Form(""),
    model_size: str = Form("qwen3-asr-1.7b"),
    device: str = Form("auto"),
    compute_type: str = Form("default"),
    language: Optional[str] = Form(None),
    task: str = Form("transcribe"),
    beam_size: int = Form(5),
    vad_filter: bool = Form(True),
    word_timestamps: bool = Form(True),
    output_format: str = Form("srt"),
    split_segments: bool = Form(False),
    segment_duration: int = Form(30),
    output_dir: Optional[str] = Form(None),
    speaker_diarization: bool = Form(False),
    num_speakers: Optional[int] = Form(None),
    llm_enhance: bool = Form(False),
    llm_api_key: Optional[str] = Form(None),
    llm_base_url: str = Form("https://api.openai.com/v1"),
    llm_model: str = Form("gpt-4o-mini"),
    llm_content_hint: Optional[str] = Form(None),
):
    """Upload files from a folder scan, create a folder, and transcribe each file."""
    import time as _time
    from backend.database import SessionLocal as _Session, FolderRecord

    if not files:
        return JSONResponse(status_code=400, content={"error": "至少需要上傳一個檔案"})

    name = folder_name.strip() or "未命名資料夾"
    now = _time.time()
    folder_id = str(uuid.uuid4())
    try:
        with _Session() as session:
            session.add(FolderRecord(id=folder_id, name=name, created_at=now, updated_at=now))
            session.commit()
    except Exception as e:
        logger.error("Failed to create folder for upload: %s", e)
        return JSONResponse(status_code=500, content={"error": f"建立資料夾失敗: {e}"})

    batch_id = str(uuid.uuid4())
    task_ids: list[str] = []
    errors: list[str] = []

    import re as _re

    def _natural_sort_key(name: str):
        return [
            int(part) if part.isdigit() else part.lower()
            for part in _re.split(r'(\d+)', name)
        ]

    indexed_files = sorted(
        enumerate(files),
        key=lambda pair: _natural_sort_key(
            Path(pair[1].filename).name if pair[1].filename else ""
        ),
    )

    for sort_idx, (_, file) in enumerate(indexed_files):
        valid, error = validate_upload_filename(file.filename)
        if not valid:
            errors.append(f"{file.filename}: {error}")
            continue

        display_name = Path(file.filename).name if file.filename else file.filename
        task_obj = create_task_entry(
            tasks=tasks,
            save_task=save_task_to_disk,
            source_name=display_name,
            batch_id=batch_id,
            folder_id=folder_id,
        )
        task_obj.sort_order = float(sort_idx)
        task_obj.status = "uploading"
        task_obj.message = "正在上傳文件"
        save_task_to_disk(task_obj)

        try:
            fpath = save_uploaded_file(
                upload_dir=UPLOAD_DIR,
                task_id=task_obj.id,
                upload_file=file,
            )
        except Exception as e:
            logger.error("Folder upload – save failed for %s: %s", file.filename, e)
            task_obj.status = "failed"
            task_obj.error = str(e)
            save_task_to_disk(task_obj)
            errors.append(f"{file.filename}: {str(e)}")
            continue

        req = build_transcription_request(
            request_cls=TranscriptionRequest,
            model_size=model_size,
            device=device,
            compute_type=compute_type,
            language=language,
            task=task,
            beam_size=beam_size,
            vad_filter=vad_filter,
            word_timestamps=word_timestamps,
            output_format=output_format,
            split_segments=split_segments,
            segment_duration=segment_duration,
            output_dir=output_dir,
            speaker_diarization=speaker_diarization,
            num_speakers=num_speakers,
            llm_enhance=llm_enhance,
            llm_api_key=llm_api_key,
            llm_base_url=llm_base_url,
            llm_model=llm_model,
            llm_content_hint=llm_content_hint,
        )

        submit_transcription(
            executor=_transcription_executor,
            target=process_transcription,
            task_id=task_obj.id,
            file_path=str(fpath),
            request=req,
        )
        task_ids.append(task_obj.id)

    logger.info(
        "Folder '%s' (%s) batch %s created with %d task(s)",
        name, folder_id, batch_id, len(task_ids),
    )
    result: Dict[str, Any] = {
        "folder_id": folder_id,
        "batch_id": batch_id,
        "task_ids": task_ids,
    }
    if errors:
        result["errors"] = errors
    return result


@app.get("/subtitle-editor/{task_id}")
@app.get("/editor/{task_id}")
async def editor_page(task_id: str):
    """字幕編輯器頁面（SPA client-side routing）"""
    index_html = _REACT_DIST / "index.html"
    if not index_html.exists():
        return JSONResponse(
            status_code=503,
            content={"error": "前端尚未建置，請先執行 npm run build"},
        )
    return FileResponse(str(index_html))


# ---------------------------------------------------------------------------
# LLM model proxy (avoids browser CORS to issues)
# ---------------------------------------------------------------------------
def _rewrite_localhost_url(url: str) -> str:
    """In Docker, rewrite localhost/127.0.0.1 to host.docker.internal."""
    if not os.path.exists("/.dockerenv"):
        return url
    import re
    return re.sub(
        r"(https?://)(?:localhost|127\.0\.0\.1)(:\d+)",
        r"\1host.docker.internal\2",
        url,
    )


@app.post("/api/llm/models")
async def proxy_llm_models(req: LlmModelsRequest):
    """Proxy a GET /models request to the user-specified OpenAI-compatible endpoint."""
    import httpx

    base = _rewrite_localhost_url(req.base_url.rstrip("/"))
    url = f"{base}/models"
    headers = {"Authorization": f"Bearer {req.api_key}"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            return JSONResponse(
                status_code=resp.status_code,
                content={"error": f"LLM API returned {resp.status_code}: {resp.text[:500]}"},
            )
        data = resp.json()
        models = []
        for m in data.get("data", []):
            models.append({"id": m.get("id", ""), "name": m.get("id", "")})
        models.sort(key=lambda x: x["id"])
        return {"models": models}
    except httpx.TimeoutException:
        return JSONResponse(status_code=504, content={"error": "連線逾時，請檢查 Base URL 是否正確"})
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": f"無法連線至 LLM API: {str(e)}"})


# ---------------------------------------------------------------------------
# Include routers & wire up shared state
# ---------------------------------------------------------------------------
app.include_router(subtitle_router)
app.include_router(download_router)
app.include_router(system_router)
app.include_router(task_router)
app.include_router(folder_router)

set_task_store(TaskStore(tasks))
set_download_task_registry(tasks)
set_task_registry(tasks)
set_folder_task_registry(tasks)

# ---------------------------------------------------------------------------
# Dev entry-point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run("backend.app:app", host="0.0.0.0", port=5001, reload=True)
