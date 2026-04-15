"""
Folder management API router.
Provides CRUD for folders (with sub-folder support) and task-to-folder assignment.
"""

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.database import SessionLocal, FolderRecord, TaskRecord

logger = logging.getLogger("folder_api")

router = APIRouter(prefix="/api/folders", tags=["folders"])

_task_registry: Dict[str, Any] = {}
_FOLDER_NOT_FOUND = "找不到資料夾"
_NEED_TASK_IDS = "至少需要一個任務 ID"


def set_folder_task_registry(registry: Dict[str, Any]):
    global _task_registry
    _task_registry = registry


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------
class CreateFolderRequest(BaseModel):
    name: str
    parent_id: Optional[str] = None


class RenameFolderRequest(BaseModel):
    name: str


class MoveTasksRequest(BaseModel):
    task_ids: List[str]


class ReorderFoldersRequest(BaseModel):
    folder_ids: List[str]


class ReorderTasksRequest(BaseModel):
    task_ids: List[str]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
@router.get("")
async def list_folders():
    """List all folders with task counts."""
    try:
        with SessionLocal() as session:
            folders = session.query(FolderRecord).order_by(FolderRecord.sort_order.asc()).all()
            result = []
            for f in folders:
                task_count = (
                    session.query(TaskRecord)
                    .filter(TaskRecord.folder_id == f.id)
                    .count()
                )
                result.append({
                    "id": f.id,
                    "name": f.name,
                    "parent_id": f.parent_id,
                    "sort_order": f.sort_order,
                    "task_count": task_count,
                    "created_at": f.created_at,
                    "updated_at": f.updated_at,
                })
        return result
    except Exception as e:
        logger.error("Failed to list folders: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def create_folder(req: CreateFolderRequest):
    """Create a new folder (optionally as a sub-folder)."""
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="資料夾名稱不可為空")
    now = time.time()
    folder_id = str(uuid.uuid4())
    try:
        with SessionLocal() as session:
            if req.parent_id:
                parent = session.get(FolderRecord, req.parent_id)
                if parent is None:
                    raise HTTPException(status_code=404, detail="父資料夾不存在")

            max_order = session.query(FolderRecord.sort_order).order_by(
                FolderRecord.sort_order.desc()
            ).limit(1).scalar() or 0.0
            sort_order = max_order + 1.0
            record = FolderRecord(
                id=folder_id, name=name, parent_id=req.parent_id,
                sort_order=sort_order, created_at=now, updated_at=now,
            )
            session.add(record)
            session.commit()
        return {
            "id": folder_id, "name": name, "parent_id": req.parent_id,
            "sort_order": sort_order, "task_count": 0,
            "created_at": now, "updated_at": now,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create folder: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Reorder (must be registered before /{folder_id} routes)
# ---------------------------------------------------------------------------
@router.put("/reorder")
async def reorder_folders(req: ReorderFoldersRequest):
    """Update folder sort order."""
    if not req.folder_ids:
        raise HTTPException(status_code=400, detail="至少需要一個資料夾 ID")
    try:
        with SessionLocal() as session:
            for idx, fid in enumerate(req.folder_ids):
                record = session.get(FolderRecord, fid)
                if record is not None:
                    record.sort_order = float(idx)
            session.commit()
        return {"message": "排序已更新"}
    except Exception as e:
        logger.error("Failed to reorder folders: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{folder_id}")
async def rename_folder(folder_id: str, req: RenameFolderRequest):
    """Rename a folder."""
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="資料夾名稱不可為空")
    try:
        with SessionLocal() as session:
            record = session.get(FolderRecord, folder_id)
            if record is None:
                raise HTTPException(status_code=404, detail=_FOLDER_NOT_FOUND)
            record.name = name
            record.updated_at = time.time()
            session.commit()
        return {"id": folder_id, "name": name}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to rename folder %s: %s", folder_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _get_descendant_ids(session, folder_id: str) -> List[str]:
    """Recursively collect all descendant folder IDs."""
    ids = []
    children = session.query(FolderRecord.id).filter(
        FolderRecord.parent_id == folder_id
    ).all()
    for (child_id,) in children:
        ids.append(child_id)
        ids.extend(_get_descendant_ids(session, child_id))
    return ids


@router.delete("/{folder_id}")
async def delete_folder(folder_id: str):
    """Delete a folder, all sub-folders, and all tasks within them."""
    try:
        with SessionLocal() as session:
            record = session.get(FolderRecord, folder_id)
            if record is None:
                raise HTTPException(status_code=404, detail=_FOLDER_NOT_FOUND)

            all_folder_ids = [folder_id] + _get_descendant_ids(session, folder_id)

            deleted_task_ids = [
                tid for (tid,) in session.query(TaskRecord.id).filter(
                    TaskRecord.folder_id.in_(all_folder_ids)
                ).all()
            ]

            if deleted_task_ids:
                session.query(TaskRecord).filter(
                    TaskRecord.id.in_(deleted_task_ids)
                ).delete(synchronize_session="fetch")

            session.query(FolderRecord).filter(
                FolderRecord.id.in_(all_folder_ids)
            ).delete(synchronize_session="fetch")
            session.commit()

        for tid in deleted_task_ids:
            _task_registry.pop(tid, None)

        return {
            "message": f"已刪除資料夾及 {len(deleted_task_ids)} 個任務",
            "deleted_task_ids": deleted_task_ids,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete folder %s: %s", folder_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Task assignment
# ---------------------------------------------------------------------------
@router.post("/{folder_id}/tasks")
async def move_tasks_to_folder(folder_id: str, req: MoveTasksRequest):
    """Move tasks into a folder."""
    if not req.task_ids:
        raise HTTPException(status_code=400, detail=_NEED_TASK_IDS)
    try:
        with SessionLocal() as session:
            folder = session.get(FolderRecord, folder_id)
            if folder is None:
                raise HTTPException(status_code=404, detail=_FOLDER_NOT_FOUND)
            session.query(TaskRecord).filter(
                TaskRecord.id.in_(req.task_ids)
            ).update({"folder_id": folder_id}, synchronize_session="fetch")
            folder.updated_at = time.time()
            session.commit()

        for tid in req.task_ids:
            task = _task_registry.get(tid)
            if task is not None:
                task.folder_id = folder_id

        return {"message": f"已移動 {len(req.task_ids)} 個任務到資料夾"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to move tasks to folder %s: %s", folder_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{folder_id}/tasks")
async def remove_tasks_from_folder(folder_id: str, req: MoveTasksRequest):
    """Remove tasks from a folder (set folder_id to null)."""
    if not req.task_ids:
        raise HTTPException(status_code=400, detail=_NEED_TASK_IDS)
    try:
        with SessionLocal() as session:
            session.query(TaskRecord).filter(
                TaskRecord.id.in_(req.task_ids),
                TaskRecord.folder_id == folder_id,
            ).update({"folder_id": None}, synchronize_session="fetch")
            session.commit()

        for tid in req.task_ids:
            task = _task_registry.get(tid)
            if task is not None and getattr(task, "folder_id", None) == folder_id:
                task.folder_id = None

        return {"message": f"已從資料夾移除 {len(req.task_ids)} 個任務"}
    except Exception as e:
        logger.error("Failed to remove tasks from folder %s: %s", folder_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Task reorder
# ---------------------------------------------------------------------------
@router.put("/{folder_id}/tasks/reorder")
async def reorder_tasks_in_folder(folder_id: str, req: ReorderTasksRequest):
    """Reorder tasks within a folder. task_ids should be in desired order."""
    if not req.task_ids:
        raise HTTPException(status_code=400, detail=_NEED_TASK_IDS)
    try:
        with SessionLocal() as session:
            for idx, tid in enumerate(req.task_ids):
                record = session.get(TaskRecord, tid)
                if record is not None:
                    record.sort_order = float(idx)
            session.commit()

        for idx, tid in enumerate(req.task_ids):
            task = _task_registry.get(tid)
            if task is not None:
                task.sort_order = float(idx)

        return {"message": "任務排序已更新"}
    except Exception as e:
        logger.error("Failed to reorder tasks in folder %s: %s", folder_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
