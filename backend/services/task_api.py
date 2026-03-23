from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException

from backend.task_persistence import TaskPersistence

router = APIRouter(tags=["tasks"])

_task_registry: Optional[Dict[str, Any]] = None


def set_task_registry(tasks: Dict[str, Any]) -> None:
    global _task_registry
    _task_registry = tasks


def get_task_registry() -> Dict[str, Any]:
    if _task_registry is None:
        raise RuntimeError("任務註冊表未初始化")
    return _task_registry


@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    tasks = get_task_registry()
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任務不存在")

    return tasks[task_id].dict()


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    tasks = get_task_registry()
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任務不存在")

    task = tasks[task_id]
    if task.status not in ("completed", "failed"):
        raise HTTPException(status_code=400, detail="只能刪除已完成或失敗的任務")

    del tasks[task_id]
    TaskPersistence.delete_task(task_id)
    return {"message": "任務已刪除"}


@router.get("/tasks")
async def get_all_tasks():
    tasks = get_task_registry()
    return {task_id: task.dict() for task_id, task in tasks.items()}
