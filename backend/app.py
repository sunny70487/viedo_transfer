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
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, Any, Optional

import uvicorn
from fastapi import FastAPI, Request, Form, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
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
from backend.services.progress_policy import next_progress_state
from backend.services.subtitle_api import (
    router as subtitle_router,
    set_task_store,
    TaskStore,
)
from backend.services.system_api import router as system_router
from backend.services.task_api import router as task_router, set_task_registry
from backend.services.transcription_launcher import (
    create_task_entry,
    start_transcription_thread,
)
from backend.services.transcription_orchestrator import (
    finalize_task_success,
    resolve_output_directory,
)
from backend.services.transcription_progress import (
    estimate_total_steps,
    build_status_callback,
    finalize_task_failure,
)
from backend.services.upload_preprocessing import (
    validate_upload_filename,
    save_uploaded_file,
    build_transcription_request,
)
from backend.services.url_preprocessing import prepare_url_input

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("whisper_app.log")],
)
logger = logging.getLogger("whisper_app")

# 創建 FastAPI 應用
app = FastAPI(
    title="Whisper 轉錄應用", description="使用 Qwen3-ASR 進行音頻轉錄的 Web 應用"
)

# 前端檔案路徑設定
_BASE_DIR = Path(__file__).resolve().parent.parent
_FRONTEND_DIR = _BASE_DIR / "frontend"
_REACT_DIST = _BASE_DIR / "frontend-react" / "dist"
_USE_REACT = _REACT_DIST.is_dir() and (_REACT_DIST / "index.html").exists()

# 舊版前端（Jinja2 + Bootstrap）
app.mount(
    "/static", StaticFiles(directory=str(_FRONTEND_DIR / "static")), name="static"
)
templates = Jinja2Templates(directory=str(_FRONTEND_DIR / "templates"))

# React 前端靜態資源（如果建置輸出存在）
if _USE_REACT:
    app.mount(
        "/assets",
        StaticFiles(directory=str(_REACT_DIST / "assets")),
        name="react-assets",
    )

# 確保必要的目錄存在
UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
TEMP_DIR = Path("temp")

for directory in [UPLOAD_DIR, OUTPUT_DIR, TEMP_DIR]:
    directory.mkdir(exist_ok=True, parents=True)

# 任務狀態存儲
tasks = {}


# 任務模型
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


# 輔助函數：保存任務到磁盤
def save_task_to_disk(task: Task):
    """將任務對象保存到磁盤"""
    try:
        TaskPersistence.save_task(task.id, task.dict())
    except Exception as e:
        logger.error(f"保存任務 {task.id} 到磁盤時出錯: {str(e)}")


# 在應用啟動時從磁盤恢復任務數據
logger.info("正在初始化任務數據...")
persisted_tasks = TaskPersistence.initialize_tasks()
for task_id, task_data in persisted_tasks.items():
    try:
        # 嘗試從輸出文件路徑提取來源名稱（舊任務可能沒有 source_name）
        if (
            not task_data.get("source_name")
            and task_data.get("result")
            and task_data["result"].get("files")
        ):
            for file_type, file_path in task_data["result"]["files"].items():
                if file_type in ("txt", "srt", "json") and file_path:
                    basename = os.path.basename(file_path)
                    # 移除 task_id 前綴和副檔名，提取原始檔名
                    prefix = f"{task_id}_"
                    if basename.startswith(prefix):
                        name_part = basename[len(prefix) :]
                        # 移除副檔名和可能的 _segments 後綴
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


# 轉錄請求模型
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
    file_path: Optional[str] = None  # 添加本地文件路徑
    speaker_diarization: bool = False  # 啟用說話者辨識
    num_speakers: Optional[int] = None  # 說話者人數（None 為自動偵測）


# 轉錄任務處理函數
def process_transcription(
    task_id: str, file_path: str = None, request: TranscriptionRequest = None
):
    """在背景執行轉錄任務"""
    task = tasks[task_id]
    task.status = "processing"
    task.message = "正在處理轉錄任務..."
    task.progress = 5.0
    save_task_to_disk(task)  # 保存任務狀態

    try:
        # 設置輸出目錄
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
            # 如果是上傳的文件，直接設置進度
            task.progress = 30.0

        # 創建進度回調函數
        def progress_callback(current_step, total_steps, message=None):
            # 計算進度百分比 (30% - 95%)
            progress_range = 65.0  # 95 - 30
            progress_value = 30.0 + (current_step / total_steps) * progress_range

            # 更新任務狀態
            task.progress = min(95.0, progress_value)  # 不超過95%
            if message:
                task.message = message

            # 記錄進度
            logger.info(f"任務 {task_id} 進度: {task.progress:.1f}% - {task.message}")

        # 執行轉錄
        task.message = "正在執行轉錄..."

        import librosa

        estimated_steps = estimate_total_steps(
            split_segments=request.split_segments,
            segment_duration=request.segment_duration,
            file_path=file_path,
            get_duration=lambda path: librosa.get_duration(path=path),
            get_file_size_mb=lambda path: os.path.getsize(path) / (1024 * 1024),
        )

        # 模擬進度更新
        progress_thread = threading.Thread(
            target=simulate_progress,
            args=(task_id, estimated_steps, request.split_segments),
        )
        progress_thread.daemon = True
        progress_thread.start()

        status_callback = build_status_callback(task=task, save_task=save_task_to_disk)

        # 執行實際轉錄
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

        finalize_task_success(
            task=task,
            transcription_results=transcription_results,
            output_directory=output_directory,
            now=time.time(),
        )
        save_task_to_disk(task)  # 保存完成狀態

        logger.info(f"任務 {task_id} 完成: {transcription_results}")

    except Exception as e:
        logger.error(f"任務 {task_id} 失敗: {str(e)}", exc_info=True)
        finalize_task_failure(task=task, error=e, now=time.time())
        save_task_to_disk(task)  # 保存失敗狀態


# 模擬進度更新
def simulate_progress(task_id, total_steps, is_split_mode=False):
    """模擬進度更新，直到任務完成或失敗"""
    if task_id not in tasks:
        return

    task = tasks[task_id]
    current_progress = task.progress
    target_progress = 95.0

    for step in range(total_steps):
        # 如果任務已完成或失敗，停止更新
        if task.status in ["completed", "failed"] or task_id not in tasks:
            break

        current_progress, next_message = next_progress_state(
            current_progress=current_progress,
            target_progress=target_progress,
            total_steps=total_steps,
            step=step,
            is_split_mode=is_split_mode,
        )
        task.progress = current_progress
        if next_message:
            task.message = next_message

        # 等待一段時間
        time.sleep(2)  # 每2秒更新一次進度


# 添加 CORS 中間件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 路由定義
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """渲染主頁面（React 或舊版 Jinja2）"""
    if _USE_REACT:
        return FileResponse(str(_REACT_DIST / "index.html"))

    gpu_info = check_gpu()
    video_quality_options = [
        {"value": "best", "label": "最佳品質"},
        {"value": "1080p", "label": "1080p"},
        {"value": "720p", "label": "720p"},
        {"value": "480p", "label": "480p"},
        {"value": "360p", "label": "360p"},
    ]
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "gpu_info": gpu_info,
            "video_quality_options": video_quality_options,
        },
    )


@app.post("/transcribe/url")
async def transcribe_from_url(
    background_tasks: BackgroundTasks, request: TranscriptionRequest
):
    """從 URL 創建轉錄任務"""
    if not request.url:
        return JSONResponse(status_code=400, content={"error": "必須提供 URL"})

    task_id = str(uuid.uuid4())
    task = Task(
        id=task_id,
        status="queued",
        message="任務已加入隊列",
        start_time=time.time(),
        source_name=request.url,
    )
    tasks[task_id] = task
    save_task_to_disk(task)  # 保存新任務

    # 在背景執行轉錄任務
    thread = threading.Thread(
        target=process_transcription, args=(task_id, None, request)
    )
    thread.daemon = True
    thread.start()

    return {"task_id": task_id}


@app.post("/transcribe/local")
async def transcribe_from_local(request: TranscriptionRequest):
    """從本地文件路徑創建轉錄任務"""
    if not request.file_path:
        return JSONResponse(status_code=400, content={"error": "必須提供本地檔案路徑"})

    # 檢查文件是否存在
    if not os.path.exists(request.file_path):
        return JSONResponse(
            status_code=404, content={"error": f"找不到檔案: {request.file_path}"}
        )

    # 檢查文件是否為可支持的音頻/視頻格式
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
    start_transcription_thread(
        target=process_transcription,
        task_id=task.id,
        file_path=request.file_path,
        request=request,
    )

    return {"task_id": task.id}


@app.post("/transcribe/upload")
async def transcribe_from_upload(
    background_tasks: BackgroundTasks,
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
        )

        # 在背景執行轉錄任務
        start_transcription_thread(
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


# 字幕編輯器相關 API 端點
@app.get("/subtitle-editor/{task_id}")
async def subtitle_editor_page(request: Request, task_id: str):
    """渲染字幕編輯器頁面"""
    if task_id not in tasks:
        return JSONResponse(status_code=404, content={"error": "任務不存在"})

    task = tasks[task_id]
    if task.status != "completed":
        return JSONResponse(status_code=400, content={"error": "任務尚未完成"})

    return templates.TemplateResponse(
        "subtitle_editor.html", {"request": request, "task_id": task_id}
    )


@app.get("/editor/{task_id}")
async def react_editor_page(task_id: str):
    """React 版字幕編輯器（SPA client-side routing）"""
    if _USE_REACT:
        return FileResponse(str(_REACT_DIST / "index.html"))
    return JSONResponse(status_code=404, content={"error": "React 前端未建置"})


# 包含字幕 API 路由
app.include_router(subtitle_router)
app.include_router(download_router)
app.include_router(system_router)
app.include_router(task_router)

# 設置任務存儲供字幕 API 使用
set_task_store(TaskStore(tasks))
set_download_task_registry(tasks)
set_task_registry(tasks)

# 啟動應用
if __name__ == "__main__":
    uvicorn.run("backend.app:app", host="0.0.0.0", port=5000, reload=True)
