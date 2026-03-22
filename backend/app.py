#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from dotenv import load_dotenv

load_dotenv()  # 載入 .env 中的環境變數（如 HF_TOKEN）

import time
import uuid
import threading
import uvicorn
import logging
from typing import List, Optional, Dict, Any
from pathlib import Path
from fastapi import FastAPI, Request, Form, UploadFile, File, BackgroundTasks
from fastapi.responses import (
    JSONResponse,
    HTMLResponse,
    FileResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import shutil
import json

# 導入轉錄模組（雙引擎：Qwen3-ASR + FunASR）
from backend.qwen3_asr_transcribe import transcribe_audio as _qwen3_transcribe
from backend.funasr_transcribe import transcribe_audio as _funasr_transcribe
from backend.funasr_transcribe import download_from_url, check_gpu

# FunASR 專屬模型名稱（選到這些時走 FunASR 引擎）
_FUNASR_MODEL_NAMES = {
    "paraformer-zh",
    "paraformer",
    "sensevoice",
    "SenseVoiceSmall",
    "iic/SenseVoiceSmall",
    "large-v3",
    "whisper-large-v3",
    "Whisper-large-v3",
    "large-v3-turbo",
    "whisper-large-v3-turbo",
    "Whisper-large-v3-turbo",
    "fun-asr-nano",
    "nano",
    "FunAudioLLM/Fun-ASR-Nano-2512",
}


def transcribe_audio(**kwargs):
    """根據 model_size 自動路由到 Qwen3-ASR 或 FunASR 引擎"""
    model_size = kwargs.get("model_size", "qwen3-asr-1.7b")
    if model_size in _FUNASR_MODEL_NAMES:
        return _funasr_transcribe(**kwargs)
    return _qwen3_transcribe(**kwargs)


# 導入任務持久化模組
from backend.task_persistence import TaskPersistence

# 系統相關導入
import platform
import subprocess
from fastapi.middleware.cors import CORSMiddleware

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

# 設置靜態文件和模板（前端檔案位於 frontend/ 目錄下）
_BASE_DIR = Path(__file__).resolve().parent.parent
_FRONTEND_DIR = _BASE_DIR / "frontend"

app.mount(
    "/static", StaticFiles(directory=str(_FRONTEND_DIR / "static")), name="static"
)
templates = Jinja2Templates(directory=str(_FRONTEND_DIR / "templates"))

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


# 導入字幕相關資料模型
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
    """渲染主頁面"""
    gpu_info = check_gpu()

    # 在此處添加影片畫質選項，前端應該更新UI來呈現這些選項
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


@app.get("/download/{task_id}/{file_type}")
async def download_result(task_id: str, file_type: str, request: Request):
    """下載或串流轉錄結果文件（支持影片範圍請求）"""
    if task_id not in tasks:
        return JSONResponse(status_code=404, content={"error": "任務不存在"})

    task = tasks[task_id]
    if task.status != "completed" or not task.result:
        return JSONResponse(
            status_code=400, content={"error": "任務尚未完成或沒有結果"}
        )

    # 定義影片文件擴展名（在函數開頭定義，避免作用域問題）
    video_extensions = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv", ".m4v"}

    # 嘗試直接匹配文件類型
    if file_type in task.result["files"]:
        file_path = task.result["files"][file_type]
    # 如果請求的是 'video'，嘗試找到任何影片文件
    elif file_type == "video":
        video_file_path = None

        # 先檢查常見的影片鍵名
        for video_key in ["video", "mp4", "avi", "mov", "mkv", "webm"]:
            if video_key in task.result["files"]:
                video_file_path = task.result["files"][video_key]
                break

        # 如果還沒找到，遍歷所有文件
        if not video_file_path:
            for key, path in task.result["files"].items():
                if isinstance(path, str):
                    ext = os.path.splitext(path)[1].lower()
                    if ext in video_extensions:
                        video_file_path = path
                        break

        if video_file_path:
            file_path = video_file_path
        else:
            return JSONResponse(status_code=404, content={"error": "找不到影片文件"})
    else:
        return JSONResponse(
            status_code=404, content={"error": f"找不到 {file_type} 格式的結果文件"}
        )

    # 確保文件存在
    if not os.path.exists(file_path):
        return JSONResponse(status_code=404, content={"error": "文件不存在"})

    # 根據文件類型設置正確的 media_type
    ext = os.path.splitext(file_path)[1].lower()
    media_types = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
        ".avi": "video/x-msvideo",
        ".mov": "video/quicktime",
        ".flv": "video/x-flv",
        ".wmv": "video/x-ms-wmv",
        ".m4v": "video/x-m4v",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    # 統一使用 FileResponse（Starlette 的 FileResponse 已內建 HTTP Range 支持，
    # 能正確處理影片的 seek/暫停/拖動，避免自訂 StreamingResponse 導致的黑屏問題）
    download_filename = os.path.basename(file_path)
    logger.info(
        f"提供檔案: {file_path}, filename: {download_filename}, media_type: {media_type}"
    )
    return FileResponse(
        path=file_path,
        filename=download_filename,
        media_type=media_type,
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600",
        },
    )


async def stream_video_with_range(file_path: str, media_type: str, request: Request):
    """支持 HTTP Range 請求的影片串流"""
    file_size = os.path.getsize(file_path)

    # 獲取 Range 請求頭
    range_header = request.headers.get("range")

    if not range_header:
        # 沒有 Range 請求，返回完整文件
        def iterfile():
            with open(file_path, "rb") as f:
                chunk_size = 1024 * 1024  # 1MB chunks
                while chunk := f.read(chunk_size):
                    yield chunk

        return StreamingResponse(
            iterfile(),
            media_type=media_type,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(file_size),
                "Content-Type": media_type,
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache",
            },
        )

    # 解析 Range 請求（格式: bytes=start-end）
    try:
        range_str = range_header.replace("bytes=", "")
        range_parts = range_str.split("-")
        start = int(range_parts[0]) if range_parts[0] else 0
        end = (
            int(range_parts[1])
            if len(range_parts) > 1 and range_parts[1]
            else file_size - 1
        )

        # 確保範圍有效
        start = max(0, start)
        end = min(file_size - 1, end)
        content_length = end - start + 1

        logger.info(
            f"範圍請求: bytes {start}-{end}/{file_size} ({content_length} bytes)"
        )

        # 生成指定範圍的內容
        def iterfile_range():
            with open(file_path, "rb") as f:
                f.seek(start)
                remaining = content_length
                chunk_size = 1024 * 1024  # 1MB chunks

                while remaining > 0:
                    chunk_to_read = min(chunk_size, remaining)
                    chunk = f.read(chunk_to_read)
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        # 返回 206 Partial Content 響應
        return StreamingResponse(
            iterfile_range(),
            status_code=206,
            media_type=media_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
                "Content-Type": media_type,
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache",
            },
        )

    except Exception as e:
        logger.error(f"處理 Range 請求時出錯: {str(e)}")
        # 如果解析失敗，返回完整文件
        return FileResponse(path=file_path, media_type=media_type)


# 導入字幕 API 模組
from backend.services.subtitle_api import (
    router as subtitle_router,
    set_task_store,
    TaskStore,
)
from backend.services.download_api import (
    router as download_router,
    set_download_task_registry,
)
from backend.services.system_api import router as system_router
from backend.services.task_api import router as task_router, set_task_registry
from backend.services.transcription_orchestrator import (
    finalize_task_success,
    resolve_output_directory,
)
from backend.services.url_preprocessing import prepare_url_input


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
