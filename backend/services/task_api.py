import asyncio
import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

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


@router.get("/tasks/{task_id}/stream")
async def stream_task_status(task_id: str):
    """Server-Sent Events endpoint for real-time task progress."""
    tasks = get_task_registry()
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任務不存在")

    async def event_generator():
        last_snapshot = None
        while True:
            tasks = get_task_registry()
            if task_id not in tasks:
                yield f"event: deleted\ndata: {json.dumps({'id': task_id})}\n\n"
                break

            task = tasks[task_id]
            snapshot = (task.status, task.progress, task.message)

            if snapshot != last_snapshot:
                yield f"data: {json.dumps(task.dict(), default=str)}\n\n"
                last_snapshot = snapshot

            if task.status in ("completed", "failed"):
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    tasks = get_task_registry()
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任務不存在")

    task = tasks[task_id]
    was_active = task.status not in ("completed", "failed")
    if was_active:
        task.status = "failed"
        task.message = "任務已被使用者取消"

    del tasks[task_id]
    TaskPersistence.delete_task(task_id)
    return {"message": "任務已取消並刪除" if was_active else "任務已刪除"}


@router.get("/tasks/batch/{batch_id}")
async def get_batch_status(batch_id: str):
    """查詢批次中所有任務的狀態"""
    tasks = get_task_registry()
    batch_tasks = {
        tid: t.dict()
        for tid, t in tasks.items()
        if getattr(t, "batch_id", None) == batch_id
    }
    if not batch_tasks:
        raise HTTPException(status_code=404, detail="批次不存在")

    statuses = [t["status"] for t in batch_tasks.values()]
    progresses = [t.get("progress", 0) for t in batch_tasks.values()]
    return {
        "batch_id": batch_id,
        "total": len(batch_tasks),
        "completed": statuses.count("completed"),
        "failed": statuses.count("failed"),
        "in_progress": len([s for s in statuses if s not in ("completed", "failed", "queued")]),
        "queued": statuses.count("queued"),
        "overall_progress": sum(progresses) / len(progresses) if progresses else 0,
        "tasks": batch_tasks,
    }


@router.get("/tasks")
async def get_all_tasks():
    tasks = get_task_registry()
    return {task_id: task.dict() for task_id, task in tasks.items()}
