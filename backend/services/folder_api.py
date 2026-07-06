"""
Folder management API router.
Provides CRUD for folders (with sub-folder support) and task-to-folder assignment.
"""

import io
import logging
import os
import re
import time
import uuid
import zipfile
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
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


def resolve_or_create_subfolder(
    session, *, root_id: str, sub_path: str, now: float, cache: Dict[str, str]
) -> str:
    """Resolve a slash-separated sub-path under root_id to a folder id,
    creating any missing intermediate folders. Returns the leaf folder id."""
    parent_id = root_id
    accumulated = ""
    for segment in [s for s in sub_path.split("/") if s.strip()]:
        accumulated = f"{accumulated}/{segment}" if accumulated else segment
        cached = cache.get(accumulated)
        if cached is not None:
            parent_id = cached
            continue
        existing = (
            session.query(FolderRecord.id)
            .filter(FolderRecord.parent_id == parent_id, FolderRecord.name == segment)
            .first()
        )
        if existing is not None:
            parent_id = existing[0]
        else:
            new_id = str(uuid.uuid4())
            max_order = session.query(FolderRecord.sort_order).order_by(
                FolderRecord.sort_order.desc()
            ).limit(1).scalar() or 0.0
            session.add(FolderRecord(
                id=new_id, name=segment, parent_id=parent_id,
                sort_order=max_order + 1.0, created_at=now, updated_at=now,
            ))
            session.flush()
            parent_id = new_id
        cache[accumulated] = parent_id
    return parent_id


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


_ILLEGAL_FILENAME_RE = re.compile(r'[\\/:*?"<>|]')


def _safe_filename(name: str) -> str:
    """Sanitize a string for safe use as a single filename component."""
    if not name:
        return ""
    return _ILLEGAL_FILENAME_RE.sub("_", name).strip()


def _unique_zip_path(used: set, sub_path: str, filename: str) -> str:
    """Build a ZIP-internal path under sub_path, de-duplicating collisions."""
    base, ext = os.path.splitext(filename)
    candidate = filename
    counter = 2
    while True:
        full = f"{sub_path}/{candidate}" if sub_path else candidate
        if full not in used:
            used.add(full)
            return full
        candidate = f"{base} ({counter}){ext}"
        counter += 1


def _build_relative_paths(rows, root_id: str) -> Dict[str, str]:
    """Given (id, name, parent_id) rows, return {folder_id: relative_path}
    for root_id and all its descendants. Root maps to "" (empty)."""
    by_id = {fid: (name, parent_id) for fid, name, parent_id in rows}
    paths: Dict[str, str] = {}

    def resolve(fid: str):
        if fid in paths:
            return paths[fid]
        if fid == root_id:
            paths[fid] = ""
            return ""
        if fid not in by_id:
            return None
        name, parent_id = by_id[fid]
        if parent_id is None:
            return None
        parent_path = resolve(parent_id)
        if parent_path is None:
            return None
        segment = _safe_filename(name) or fid
        paths[fid] = f"{parent_path}/{segment}" if parent_path else segment
        return paths[fid]

    for fid in by_id:
        resolve(fid)
    paths[root_id] = ""
    return paths


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


# ---------------------------------------------------------------------------
# Batch subtitle download
# ---------------------------------------------------------------------------
@router.get("/{folder_id}/download-subtitles")
async def download_folder_subtitles(
    folder_id: str,
    format: str = "srt",
    encoding: str = "utf-8",
):
    """Download all completed-task subtitles in a folder (recursively) as a ZIP."""
    from urllib.parse import quote

    from backend.services.subtitle_api import SubtitleService, get_tasks_storage
    from backend.services.subtitle_converter import SubtitleConverter

    converter = SubtitleConverter()
    fmt = format.lower()
    if not converter.is_format_supported(fmt):
        raise HTTPException(status_code=400, detail=f"不支援的格式: {format}")

    with SessionLocal() as session:
        folder = session.get(FolderRecord, folder_id)
        if folder is None:
            raise HTTPException(status_code=404, detail=_FOLDER_NOT_FOUND)

        folder_name = folder.name
        all_ids = [folder_id] + _get_descendant_ids(session, folder_id)

        rows = session.query(
            FolderRecord.id, FolderRecord.name, FolderRecord.parent_id
        ).filter(FolderRecord.id.in_(all_ids)).all()
        rel_paths = _build_relative_paths(
            [(r[0], r[1], r[2]) for r in rows], folder_id
        )

        task_rows = session.query(
            TaskRecord.id, TaskRecord.folder_id
        ).filter(
            TaskRecord.folder_id.in_(all_ids),
            TaskRecord.status == "completed",
        ).all()

    tasks = get_tasks_storage()
    buffer = io.BytesIO()
    used_paths: set = set()
    written = 0

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for task_id, task_folder_id in task_rows:
            task = tasks.get(task_id)
            if task is None or not getattr(task, "result", None):
                continue
            try:
                collection = SubtitleService.load_subtitle_data(task_id, tasks)
                output_dir = task.result["output_dir"]
                tmp_file = os.path.join(output_dir, f"{task_id}_folderdl.{fmt}")
                result_path = converter.convert(collection, fmt, tmp_file, encoding)
                with open(result_path, "rb") as fh:
                    data = fh.read()
                try:
                    os.remove(result_path)
                except OSError:
                    pass
            except Exception as exc:  # noqa: BLE001 - skip a single bad task
                logger.warning("略過任務 %s 的字幕轉換: %s", task_id, exc)
                continue

            source_name = getattr(task, "source_name", None) or task_id
            filename = f"{_safe_filename(source_name) or task_id}.{fmt}"
            sub_path = rel_paths.get(task_folder_id, "")
            zip_path = _unique_zip_path(used_paths, sub_path, filename)
            zf.writestr(zip_path, data)
            written += 1

    if written == 0:
        raise HTTPException(status_code=404, detail="此資料夾沒有可下載的字幕")

    buffer.seek(0)
    zip_filename = f"{_safe_filename(folder_name) or 'folder'}_subtitles.zip"

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{quote(zip_filename)}"
            )
        },
    )
