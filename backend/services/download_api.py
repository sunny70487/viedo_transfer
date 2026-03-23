import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from backend.shared.media_config import VIDEO_EXTENSIONS, get_media_type

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
        raise HTTPException(status_code=404, detail="任務不存在")

    task = tasks[task_id]
    if task.status != "completed" or not task.result:
        raise HTTPException(status_code=400, detail="任務尚未完成或沒有結果")

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
                    if ext in VIDEO_EXTENSIONS:
                        video_file_path = path
                        break

        if video_file_path:
            file_path = video_file_path
        else:
            raise HTTPException(status_code=404, detail="找不到影片文件")
    else:
        raise HTTPException(
            status_code=404, detail=f"找不到 {file_type} 格式的結果文件"
        )

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件不存在")

    media_type = get_media_type(file_path)
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
