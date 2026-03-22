import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter(tags=["download"])

_task_registry: Optional[Dict[str, Any]] = None


def set_download_task_registry(tasks: Dict[str, Any]) -> None:
    global _task_registry
    _task_registry = tasks


def get_download_task_registry() -> Dict[str, Any]:
    if _task_registry is None:
        raise RuntimeError("下載任務註冊表未初始化")
    return _task_registry


@router.get("/download/{task_id}/{file_type}")
async def download_result(task_id: str, file_type: str, request: Request):
    tasks = get_download_task_registry()

    if task_id not in tasks:
        return JSONResponse(status_code=404, content={"error": "任務不存在"})

    task = tasks[task_id]
    if task.status != "completed" or not task.result:
        return JSONResponse(
            status_code=400, content={"error": "任務尚未完成或沒有結果"}
        )

    video_extensions = {
        ".mp4",
        ".avi",
        ".mov",
        ".mkv",
        ".webm",
        ".flv",
        ".wmv",
        ".m4v",
    }

    if file_type in task.result["files"]:
        file_path = task.result["files"][file_type]
    elif file_type == "video":
        video_file_path = None

        for video_key in ["video", "mp4", "avi", "mov", "mkv", "webm"]:
            if video_key in task.result["files"]:
                video_file_path = task.result["files"][video_key]
                break

        if not video_file_path:
            for _, path in task.result["files"].items():
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

    if not os.path.exists(file_path):
        return JSONResponse(status_code=404, content={"error": "文件不存在"})

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
    download_filename = os.path.basename(file_path)

    return FileResponse(
        path=file_path,
        filename=download_filename,
        media_type=media_type,
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600",
        },
    )
