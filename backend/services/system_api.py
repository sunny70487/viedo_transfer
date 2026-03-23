import os
import platform

from fastapi import APIRouter, HTTPException, Query

from backend.shared.transcribe_helpers import check_gpu

router = APIRouter(tags=["system"])


@router.get("/gpu-info")
async def get_gpu_info():
    """獲取 GPU 信息"""
    return check_gpu()


@router.get("/system/directories")
async def get_system_directories():
    """獲取系統目錄列表"""
    system = platform.system()
    directories = []

    try:
        if system == "Windows":
            import win32api

            drives = win32api.GetLogicalDriveStrings()
            drives = drives.split("\000")[:-1]
            directories = drives
        else:
            directories = ["/", "/home", "/tmp", os.getcwd()]

        return {"directories": directories, "current": os.getcwd(), "system": system}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"獲取系統目錄時出錯: {str(e)}")


@router.get("/system/subdirectories")
async def get_subdirectories(path: str = Query(..., description="目錄路徑")):
    """獲取指定目錄的子目錄列表"""
    try:
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail=f"路徑不存在: {path}")

        if not os.path.isdir(path):
            raise HTTPException(status_code=400, detail=f"路徑不是目錄: {path}")

        subdirectories = []
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            if os.path.isdir(item_path):
                try:
                    stat = os.stat(item_path)
                    subdirectories.append(
                        {
                            "name": item,
                            "path": item_path,
                            "modified": stat.st_mtime,
                        }
                    )
                except OSError:
                    continue

        subdirectories.sort(key=lambda x: x["name"].lower())
        return {"path": path, "subdirectories": subdirectories}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"獲取子目錄時出錯: {str(e)}")
