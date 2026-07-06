#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
任務持久化模組
使用 SQLAlchemy 將任務數據保存到資料庫
支援 PostgreSQL (生產環境) 和 SQLite (開發環境)
Configure via DATABASE_URL environment variable.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any

from backend.database import SessionLocal, TaskRecord, init_db

logger = logging.getLogger("task_persistence")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = _PROJECT_ROOT / "outputs"
_LEGACY_JSON = _PROJECT_ROOT / "tasks_data.json"


class TaskPersistence:
    """任務持久化管理器（SQLAlchemy 後端）"""

    @staticmethod
    def save_task(task_id: str, task_data: Dict[str, Any]) -> bool:
        """保存單個任務數據到資料庫（thread-safe — 每次取得獨立 session）"""
        try:
            with SessionLocal() as session:
                record = session.get(TaskRecord, task_id)
                if record is None:
                    record = TaskRecord(id=task_id)
                    session.add(record)
                record.status = task_data.get("status", "queued")
                record.progress = task_data.get("progress", 0.0)
                record.message = task_data.get("message", "")
                record.result = task_data.get("result")
                record.error = task_data.get("error")
                record.start_time = task_data.get("start_time", 0.0)
                record.end_time = task_data.get("end_time")
                record.source_name = task_data.get("source_name")
                record.batch_id = task_data.get("batch_id")
                record.folder_id = task_data.get("folder_id")
                record.sort_order = task_data.get("sort_order", 0.0)
                session.commit()
            logger.debug(f"任務 {task_id} 已保存到資料庫")
            return True
        except Exception as e:
            logger.error(f"保存任務 {task_id} 時出錯: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def load_all_tasks() -> Dict[str, Any]:
        """從資料庫載入所有任務數據"""
        try:
            with SessionLocal() as session:
                records = session.query(TaskRecord).all()
                tasks = {r.id: r.to_dict() for r in records}
            if tasks:
                logger.info(f"從資料庫載入了 {len(tasks)} 個任務")
            return tasks
        except Exception as e:
            logger.error(f"載入任務數據時出錯: {str(e)}", exc_info=True)
            return {}

    @staticmethod
    def delete_task(task_id: str) -> bool:
        """從資料庫刪除任務數據"""
        try:
            with SessionLocal() as session:
                record = session.get(TaskRecord, task_id)
                if record is None:
                    logger.warning(f"任務 {task_id} 不存在於資料庫")
                    return False
                session.delete(record)
                session.commit()
            logger.info(f"任務 {task_id} 已從資料庫刪除")
            return True
        except Exception as e:
            logger.error(f"刪除任務 {task_id} 時出錯: {str(e)}", exc_info=True)
            return False

    # ------------------------------------------------------------------
    # Migration & recovery
    # ------------------------------------------------------------------

    @staticmethod
    def _migrate_from_json() -> Dict[str, Any]:
        """Migrate tasks from legacy tasks_data.json if present."""
        if not _LEGACY_JSON.exists():
            return {}
        try:
            with open(_LEGACY_JSON, "r", encoding="utf-8") as f:
                old_tasks = json.load(f)
            if not old_tasks:
                return {}
            logger.info(f"從 JSON 遷移 {len(old_tasks)} 個任務到資料庫...")
            for task_id, task_data in old_tasks.items():
                TaskPersistence.save_task(task_id, task_data)
            _LEGACY_JSON.rename(_LEGACY_JSON.with_suffix(".json.bak"))
            logger.info("JSON 遷移完成，原始檔案已重命名為 .json.bak")
            return old_tasks
        except Exception as e:
            logger.error(f"從 JSON 遷移時出錯: {str(e)}", exc_info=True)
            return {}

    @staticmethod
    def scan_and_rebuild_tasks() -> Dict[str, Any]:
        """掃描 outputs 目錄，重建任務列表"""
        rebuilt_tasks: Dict[str, Any] = {}
        try:
            if not OUTPUTS_DIR.exists():
                logger.warning(f"輸出目錄 {OUTPUTS_DIR} 不存在")
                return rebuilt_tasks

            for task_dir in OUTPUTS_DIR.iterdir():
                if not task_dir.is_dir():
                    continue

                task_id = task_dir.name
                json_files = list(task_dir.glob("*.json"))
                if not json_files:
                    continue

                json_file = json_files[0]
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        json.load(f)
                except Exception:
                    continue

                output_files: Dict[str, str] = {}
                for ext in ["json", "srt", "vtt", "txt"]:
                    matching = list(task_dir.glob(f"*.{ext}"))
                    if matching:
                        updated = [fp for fp in matching if "updated" in fp.name]
                        if updated:
                            output_files[ext] = str(updated[0])
                            if ext == "json":
                                output_files["updated_json"] = str(updated[0])
                        else:
                            output_files[ext] = str(matching[0])

                creation_time = task_dir.stat().st_ctime
                modification_time = json_file.stat().st_mtime

                task_data = {
                    "id": task_id,
                    "status": "completed",
                    "progress": 100.0,
                    "message": "轉錄完成（從文件系統恢復）",
                    "result": {"files": output_files, "output_dir": str(task_dir)},
                    "error": None,
                    "start_time": creation_time,
                    "end_time": modification_time,
                }

                rebuilt_tasks[task_id] = task_data
                TaskPersistence.save_task(task_id, task_data)
                logger.info(f"從文件系統恢復任務: {task_id}")

            logger.info(f"從文件系統重建了 {len(rebuilt_tasks)} 個任務")
            return rebuilt_tasks

        except Exception as e:
            logger.error(f"掃描和重建任務時出錯: {str(e)}", exc_info=True)
            return rebuilt_tasks

    @staticmethod
    def initialize_tasks() -> Dict[str, Any]:
        """
        初始化任務數據：
        1. 建立資料庫表
        2. 嘗試從資料庫載入
        3. 若為空，嘗試遷移 legacy JSON
        4. 若仍為空，從文件系統重建
        """
        init_db()

        tasks = TaskPersistence.load_all_tasks()
        if tasks:
            return tasks

        tasks = TaskPersistence._migrate_from_json()
        if tasks:
            return tasks

        logger.info("資料庫中沒有任務數據，嘗試從文件系統重建...")
        return TaskPersistence.scan_and_rebuild_tasks()
