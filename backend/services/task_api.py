import asyncio
import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.database import SessionLocal, TaskRecord
from backend.task_persistence import TaskPersistence

logger = logging.getLogger("task_api")

router = APIRouter(tags=["tasks"])


class SetWatchedRequest(BaseModel):
    watched: bool


class RenameTaskRequest(BaseModel):
    name: str


_MAX_TASK_NAME_LENGTH = 200


_task_registry: Optional[Dict[str, Any]] = None


def set_task_registry(tasks: Dict[str, Any]) -> None:
    global _task_registry
    _task_registry = tasks


def get_task_registry() -> Dict[str, Any]:
    if _task_registry is None:
        raise RuntimeError("任務註冊表未初始化")
    return _task_registry


@router.delete("/tasks/failed")
async def delete_all_failed_tasks():
    """Delete all tasks with status 'failed'."""
    tasks = get_task_registry()
    failed_ids = [tid for tid, t in tasks.items() if t.status == "failed"]
    for tid in failed_ids:
        del tasks[tid]
        TaskPersistence.delete_task(tid)
    return {"message": f"已刪除 {len(failed_ids)} 個失敗任務", "deleted_count": len(failed_ids)}


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


@router.put("/tasks/{task_id}/watched")
async def set_task_watched(task_id: str, req: SetWatchedRequest):
    """Mark a task as watched or unwatched."""
    tasks = get_task_registry()
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任務不存在")

    try:
        with SessionLocal() as session:
            record = session.get(TaskRecord, task_id)
            if record is not None:
                record.watched = req.watched
                session.commit()
    except Exception as e:
        logger.error(
            "Failed to set watched on task %s: %s", task_id, e, exc_info=True
        )
        raise HTTPException(status_code=500, detail="無法更新已看過狀態")

    tasks[task_id].watched = req.watched
    return {"id": task_id, "watched": req.watched}


@router.put("/tasks/{task_id}/name")
async def rename_task(task_id: str, req: RenameTaskRequest):
    """Rename a task (overwrites the display name shown in the task list)."""
    tasks = get_task_registry()
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任務不存在")

    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="任務名稱不可為空")
    if len(name) > _MAX_TASK_NAME_LENGTH:
        raise HTTPException(status_code=400, detail="任務名稱過長")

    try:
        with SessionLocal() as session:
            record = session.get(TaskRecord, task_id)
            if record is not None:
                record.source_name = name
                session.commit()
    except Exception as e:
        logger.error(
            "Failed to rename task %s: %s", task_id, e, exc_info=True
        )
        raise HTTPException(status_code=500, detail="無法更新任務名稱")

    tasks[task_id].source_name = name
    return {"id": task_id, "source_name": name}


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
