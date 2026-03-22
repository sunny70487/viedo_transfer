#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
字幕編輯器 API 端點
提供字幕 CRUD 操作的 RESTful API
"""

import os
import json
import time
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query, Path as FastAPIPath
from fastapi.responses import JSONResponse, FileResponse, Response

from backend.models import (
    SubtitleCollection,
    Subtitle,
    Word,
    RetranscribeRequest,
    SubtitleExportRequest,
    SubtitleSearchRequest,
    SubtitleSearchResult,
    VideoInfo,
    SubtitleMetadata,
)

# 設置日誌
logger = logging.getLogger("subtitle_api")

# 創建 API 路由器
router = APIRouter(prefix="/api/subtitles", tags=["subtitles"])


class SubtitleService:
    """字幕服務類，處理字幕相關的業務邏輯"""

    @staticmethod
    def load_subtitle_data(task_id: str, tasks: Dict[str, Any]) -> SubtitleCollection:
        """從任務載入字幕資料"""
        if task_id not in tasks:
            raise HTTPException(status_code=404, detail="任務不存在")

        task = tasks[task_id]
        if task.status != "completed" or not task.result:
            raise HTTPException(status_code=400, detail="任務尚未完成或沒有結果")

        try:
            # 檢查是否有更新的字幕資料
            updated_json_path = task.result["files"].get("updated_json")
            if updated_json_path and os.path.exists(updated_json_path):
                json_file_path = updated_json_path
            else:
                json_file_path = task.result["files"].get("json")

            if not json_file_path or not os.path.exists(json_file_path):
                raise HTTPException(status_code=404, detail="找不到字幕資料文件")

            with open(json_file_path, "r", encoding="utf-8") as f:
                transcription_data = json.load(f)

            # 轉換為字幕格式
            subtitles = []
            if "segments" in transcription_data:
                for i, segment in enumerate(transcription_data["segments"]):
                    subtitle = Subtitle(
                        index=i,
                        start_time=segment.get("start", 0.0),
                        end_time=segment.get("end", 0.0),
                        text=segment.get("text", "").strip(),
                        confidence=segment.get("avg_logprob", None),
                    )

                    # 添加詞級時間戳（如果有）
                    if "words" in segment and segment["words"]:
                        subtitle.words = [
                            Word(
                                word=word.get("word", ""),
                                start=word.get("start", 0.0),
                                end=word.get("end", 0.0),
                                confidence=word.get("probability", None),
                            )
                            for word in segment["words"]
                        ]

                    subtitles.append(subtitle)

            # 獲取影片資訊
            video_info = VideoInfo()
            if task.result.get("files"):
                # 尋找影片文件 - 檢查多種可能的鍵名
                video_file_found = False

                # 首先檢查常見的影片格式鍵名
                for file_type in [
                    "video",
                    "mp4",
                    "avi",
                    "mov",
                    "mkv",
                    "webm",
                    "flv",
                    "wmv",
                    "m4v",
                ]:
                    if file_type in task.result["files"]:
                        file_path = task.result["files"][file_type]
                        if os.path.exists(file_path):
                            video_info.video_url = f"/download/{task_id}/video"  # 統一使用 'video' 作為鍵名
                            # 從文件路徑提取實際格式
                            actual_format = os.path.splitext(file_path)[1].lstrip(".")
                            video_info.format = actual_format or file_type
                            try:
                                video_info.file_size = os.path.getsize(file_path)
                            except:
                                pass
                            video_file_found = True
                            logger.info(
                                f"找到影片文件: {file_path}, 格式: {video_info.format}"
                            )
                            break

                # 如果還沒找到，遍歷所有文件尋找影片擴展名
                if not video_file_found:
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
                    for file_type, file_path in task.result["files"].items():
                        if isinstance(file_path, str) and os.path.exists(file_path):
                            ext = os.path.splitext(file_path)[1].lower()
                            if ext in video_extensions:
                                video_info.video_url = (
                                    f"/download/{task_id}/{file_type}"
                                )
                                video_info.format = ext.lstrip(".")
                                try:
                                    video_info.file_size = os.path.getsize(file_path)
                                except:
                                    pass
                                logger.info(
                                    f"通過擴展名找到影片: {file_path}, 格式: {video_info.format}"
                                )
                                break

            # 創建元資料
            metadata = SubtitleMetadata(
                language=transcription_data.get("language", "unknown"),
                model_used=transcription_data.get("model_name", "unknown"),
                created_at=task.start_time,
                last_modified=task.end_time or task.start_time,
                total_duration=transcription_data.get("duration", 0.0),
                video_info=video_info,
            )

            subtitle_collection = SubtitleCollection(
                task_id=task_id, subtitles=subtitles, metadata=metadata
            )

            return subtitle_collection

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"載入字幕資料時出錯: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"載入字幕資料時出錯: {str(e)}")

    @staticmethod
    def save_subtitle_data(
        task_id: str, subtitle_collection: SubtitleCollection, tasks: Dict[str, Any]
    ) -> Dict[str, Any]:
        """儲存字幕資料"""
        if task_id not in tasks:
            raise HTTPException(status_code=404, detail="任務不存在")

        try:
            # 驗證字幕資料
            if subtitle_collection.task_id != task_id:
                raise HTTPException(status_code=400, detail="任務 ID 不匹配")

            task = tasks[task_id]
            if not task.result or not task.result.get("output_dir"):
                raise HTTPException(status_code=400, detail="找不到任務輸出目錄")

            output_dir = task.result["output_dir"]

            # 儲存為 JSON 格式
            updated_json_path = os.path.join(output_dir, f"{task_id}_updated.json")

            # 轉換回 Whisper 格式
            whisper_data = {
                "text": " ".join([sub.text for sub in subtitle_collection.subtitles]),
                "segments": [
                    {
                        "id": sub.index,
                        "start": sub.start_time,
                        "end": sub.end_time,
                        "text": sub.text,
                        "avg_logprob": sub.confidence,
                        "words": [
                            {
                                "word": word.word,
                                "start": word.start,
                                "end": word.end,
                                "probability": word.confidence,
                            }
                            for word in (sub.words or [])
                        ]
                        if sub.words
                        else [],
                    }
                    for sub in subtitle_collection.subtitles
                ],
                "language": subtitle_collection.metadata.language,
                "duration": subtitle_collection.metadata.total_duration or 0.0,
                "model_name": subtitle_collection.metadata.model_used,
            }

            with open(updated_json_path, "w", encoding="utf-8") as f:
                json.dump(whisper_data, f, ensure_ascii=False, indent=2)

            # 更新任務結果
            task.result["files"]["updated_json"] = updated_json_path

            # 更新元資料
            subtitle_collection.metadata.last_modified = time.time()

            logger.info(f"字幕已更新: {task_id}")
            return {
                "message": "字幕已成功更新",
                "updated_at": subtitle_collection.metadata.last_modified,
                "total_segments": len(subtitle_collection.subtitles),
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"儲存字幕資料時出錯: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"儲存字幕資料時出錯: {str(e)}")

    @staticmethod
    def search_subtitles(
        task_id: str, search_request: SubtitleSearchRequest, tasks: Dict[str, Any]
    ) -> SubtitleSearchResult:
        """搜尋字幕內容"""
        import re

        start_time = time.time()

        # 載入字幕資料
        subtitle_collection = SubtitleService.load_subtitle_data(task_id, tasks)

        matches = []
        query = search_request.query

        # 準備搜尋模式
        if search_request.regex:
            try:
                pattern = re.compile(
                    query, 0 if search_request.case_sensitive else re.IGNORECASE
                )
            except re.error as e:
                raise HTTPException(
                    status_code=400, detail=f"無效的正規表達式: {str(e)}"
                )
        else:
            if not search_request.case_sensitive:
                query = query.lower()

        # 搜尋字幕
        for subtitle in subtitle_collection.subtitles:
            # 檢查時間範圍篩選
            if search_request.time_range:
                time_range = search_request.time_range
                if "start" in time_range and subtitle.end_time < time_range["start"]:
                    continue
                if "end" in time_range and subtitle.start_time > time_range["end"]:
                    continue

            # 搜尋文字
            text_to_search = subtitle.text
            if not search_request.case_sensitive and not search_request.regex:
                text_to_search = text_to_search.lower()

            match_positions = []

            if search_request.regex:
                # 正規表達式搜尋
                for match in pattern.finditer(subtitle.text):
                    match_positions.append(match.start())
            else:
                # 普通文字搜尋
                start_pos = 0
                while True:
                    pos = text_to_search.find(query, start_pos)
                    if pos == -1:
                        break
                    match_positions.append(pos)
                    start_pos = pos + 1

            if match_positions:
                matches.append(
                    {
                        "subtitle_index": subtitle.index,
                        "start_time": subtitle.start_time,
                        "end_time": subtitle.end_time,
                        "text": subtitle.text,
                        "match_positions": match_positions,
                        "match_count": len(match_positions),
                    }
                )

        search_time = time.time() - start_time

        return SubtitleSearchResult(
            matches=matches, total_matches=len(matches), search_time=search_time
        )


class TaskStore:
    def __init__(self, tasks: Optional[Dict[str, Any]] = None):
        self._tasks = tasks

    def set_tasks(self, tasks: Dict[str, Any]) -> None:
        self._tasks = tasks

    def get_tasks(self) -> Dict[str, Any]:
        if self._tasks is None:
            raise HTTPException(status_code=500, detail="任務存儲未初始化")
        return self._tasks


_task_store = TaskStore()


def set_task_store(task_store: TaskStore) -> None:
    global _task_store
    _task_store = task_store


def set_tasks_storage(tasks):
    _task_store.set_tasks(tasks)


def get_tasks_storage():
    return _task_store.get_tasks()


# API 端點定義
@router.get("/{task_id}")
async def get_subtitles(
    task_id: str = FastAPIPath(..., description="任務 ID"),
    include_words: bool = Query(True, description="是否包含詞級時間戳"),
):
    """獲取任務的字幕資料"""
    tasks = get_tasks_storage()
    subtitle_collection = SubtitleService.load_subtitle_data(task_id, tasks)

    # 如果不需要詞級時間戳，移除 words 資料以減少傳輸量
    if not include_words:
        for subtitle in subtitle_collection.subtitles:
            subtitle.words = None

    return subtitle_collection.dict()


@router.put("/{task_id}")
async def update_subtitles(
    subtitle_collection: SubtitleCollection,
    task_id: str = FastAPIPath(..., description="任務 ID"),
):
    """更新字幕內容"""
    tasks = get_tasks_storage()
    result = SubtitleService.save_subtitle_data(task_id, subtitle_collection, tasks)
    return result


@router.head("/{task_id}")
async def head_subtitles(task_id: str = FastAPIPath(..., description="任務 ID")):
    """檢查字幕資料是否可用 (HEAD)"""
    tasks = get_tasks_storage()

    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任務不存在")

    task = tasks[task_id]

    if task.status != "completed" or not task.result:
        raise HTTPException(status_code=400, detail="任務尚未完成或沒有結果")

    files = task.result.get("files") or {}
    candidate_paths = [
        files.get("updated_json"),
        files.get("json"),
        files.get("srt"),
        files.get("vtt"),
        files.get("txt"),
    ]

    for path in candidate_paths:
        if path and os.path.exists(path):
            return Response(status_code=200)

    raise HTTPException(status_code=404, detail="找不到字幕資料")


@router.get("/{task_id}/download/{format}")
async def download_subtitles(
    task_id: str = FastAPIPath(..., description="任務 ID"),
    format: str = FastAPIPath(..., description="下載格式"),
    encoding: str = Query("utf-8", description="檔案編碼"),
    include_timestamps: bool = Query(True, description="是否包含時間戳（僅 TXT 格式）"),
    include_metadata: bool = Query(
        True, description="是否包含元資料（VTT 和 JSON 格式）"
    ),
):
    """下載編輯後的字幕"""
    from backend.services.subtitle_converter import SubtitleConverter

    tasks = get_tasks_storage()

    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任務不存在")

    task = tasks[task_id]
    if not task.result:
        raise HTTPException(status_code=400, detail="任務沒有結果")

    try:
        # 載入字幕資料
        subtitle_collection = SubtitleService.load_subtitle_data(task_id, tasks)

        # 使用新的轉換器
        converter = SubtitleConverter()

        # 驗證格式
        if not converter.is_format_supported(format):
            supported_formats = converter.get_supported_formats()
            raise HTTPException(
                status_code=400,
                detail=f"不支援的格式: {format}，支援的格式: {supported_formats}",
            )

        # 驗證字幕資料
        validation_errors = converter.validate_subtitle_collection(subtitle_collection)
        if validation_errors:
            logger.warning(f"字幕資料驗證警告: {validation_errors}")

        # 準備轉換選項
        convert_options = {"include_metadata": include_metadata}

        if format == "txt":
            convert_options["include_timestamps"] = include_timestamps

        # 生成輸出檔案路徑
        output_dir = task.result["output_dir"]
        output_filename = f"{task_id}_edited.{format}"
        output_file = os.path.join(output_dir, output_filename)

        # 轉換並儲存檔案
        result_path = converter.convert(
            subtitle_collection, format, output_file, encoding, **convert_options
        )

        # 確認檔案存在
        if not os.path.exists(result_path):
            raise HTTPException(status_code=500, detail="檔案生成失敗")

        # 設置適當的 MIME 類型
        format_info = converter.get_format_info(format)
        media_type = (
            format_info["mimeType"] if format_info else "application/octet-stream"
        )

        return FileResponse(
            path=result_path,
            filename=output_filename,
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={output_filename}"},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下載字幕時出錯: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"下載字幕時出錯: {str(e)}")


@router.post("/{task_id}/search")
async def search_subtitles(
    search_request: SubtitleSearchRequest,
    task_id: str = FastAPIPath(..., description="任務 ID"),
):
    """搜尋字幕內容"""
    tasks = get_tasks_storage()

    # 驗證任務 ID 匹配
    if search_request.task_id != task_id:
        raise HTTPException(status_code=400, detail="請求中的任務 ID 與路徑不匹配")

    result = SubtitleService.search_subtitles(task_id, search_request, tasks)
    return result.dict()


@router.get("/{task_id}/metadata")
async def get_subtitle_metadata(task_id: str = FastAPIPath(..., description="任務 ID")):
    """獲取字幕元資料"""
    tasks = get_tasks_storage()
    subtitle_collection = SubtitleService.load_subtitle_data(task_id, tasks)
    return subtitle_collection.metadata.dict()


@router.get("/{task_id}/statistics")
async def get_subtitle_statistics(
    task_id: str = FastAPIPath(..., description="任務 ID"),
):
    """獲取字幕統計資訊"""
    tasks = get_tasks_storage()
    subtitle_collection = SubtitleService.load_subtitle_data(task_id, tasks)

    # 計算統計資訊
    total_segments = len(subtitle_collection.subtitles)
    total_duration = subtitle_collection.metadata.total_duration or 0.0

    if subtitle_collection.subtitles:
        total_words = sum(
            len(sub.text.split()) for sub in subtitle_collection.subtitles
        )
        total_characters = sum(len(sub.text) for sub in subtitle_collection.subtitles)
        avg_segment_duration = (
            total_duration / total_segments if total_segments > 0 else 0.0
        )
        avg_confidence = (
            sum(
                sub.confidence
                for sub in subtitle_collection.subtitles
                if sub.confidence
            )
            / total_segments
            if total_segments > 0
            else None
        )
    else:
        total_words = 0
        total_characters = 0
        avg_segment_duration = 0.0
        avg_confidence = None

    return {
        "task_id": task_id,
        "total_segments": total_segments,
        "total_duration": total_duration,
        "total_words": total_words,
        "total_characters": total_characters,
        "average_segment_duration": avg_segment_duration,
        "average_confidence": avg_confidence,
        "language": subtitle_collection.metadata.language,
        "created_at": subtitle_collection.metadata.created_at,
        "last_modified": subtitle_collection.metadata.last_modified,
    }


@router.get("/formats")
async def get_supported_formats():
    """獲取支援的字幕格式"""
    from backend.services.subtitle_converter import SubtitleConverter

    converter = SubtitleConverter()
    formats = []

    for format_name in converter.get_supported_formats():
        format_info = converter.get_format_info(format_name)
        if format_info:
            formats.append(
                {
                    "format": format_name,
                    "name": format_info["name"],
                    "description": format_info["description"],
                    "extension": format_info["extension"],
                    "mime_type": format_info["mimeType"],
                    "icon": format_info["icon"],
                }
            )

    return {"supported_formats": formats, "total_count": len(formats)}


# 導入重新轉錄服務
from backend.services.retranscribe_service import get_retranscribe_service


# 重新轉錄相關 API 端點
@router.post("/{task_id}/retranscribe")
async def create_retranscribe_task(
    request: RetranscribeRequest,
    task_id: str = FastAPIPath(..., description="原始任務 ID"),
):
    """創建重新轉錄任務"""
    tasks = get_tasks_storage()

    # 驗證任務 ID 匹配
    if request.task_id != task_id:
        raise HTTPException(status_code=400, detail="請求中的任務 ID 與路徑不匹配")

    try:
        retranscribe_service = get_retranscribe_service()
        retranscribe_task_id = retranscribe_service.create_retranscribe_task(
            request, tasks
        )

        return {
            "retranscribe_task_id": retranscribe_task_id,
            "message": "重新轉錄任務已創建",
            "status": "queued",
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"創建重新轉錄任務時出錯: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"創建重新轉錄任務時出錯: {str(e)}")


@router.get("/retranscribe/{retranscribe_task_id}")
async def get_retranscribe_task_status(
    retranscribe_task_id: str = FastAPIPath(..., description="重新轉錄任務 ID"),
):
    """獲取重新轉錄任務狀態"""
    try:
        retranscribe_service = get_retranscribe_service()
        task = retranscribe_service.get_retranscribe_task(retranscribe_task_id)

        if not task:
            raise HTTPException(status_code=404, detail="重新轉錄任務不存在")

        return task.dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"獲取重新轉錄任務狀態時出錯: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"獲取重新轉錄任務狀態時出錯: {str(e)}"
        )


@router.get("/retranscribe")
async def get_all_retranscribe_tasks():
    """獲取所有重新轉錄任務"""
    try:
        retranscribe_service = get_retranscribe_service()
        tasks = retranscribe_service.get_all_retranscribe_tasks()

        return {
            "tasks": {task_id: task.dict() for task_id, task in tasks.items()},
            "total_count": len(tasks),
        }

    except Exception as e:
        logger.error(f"獲取重新轉錄任務列表時出錯: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"獲取重新轉錄任務列表時出錯: {str(e)}"
        )


@router.post("/{task_id}/retranscribe/{retranscribe_task_id}/apply")
async def apply_retranscribe_result(
    retranscribe_task_id: str = FastAPIPath(..., description="重新轉錄任務 ID"),
    task_id: str = FastAPIPath(..., description="原始任務 ID"),
):
    """應用重新轉錄結果到原始字幕"""
    tasks = get_tasks_storage()

    try:
        # 獲取重新轉錄任務
        retranscribe_service = get_retranscribe_service()
        retranscribe_task = retranscribe_service.get_retranscribe_task(
            retranscribe_task_id
        )

        if not retranscribe_task:
            raise HTTPException(status_code=404, detail="重新轉錄任務不存在")

        if retranscribe_task.original_task_id != task_id:
            raise HTTPException(status_code=400, detail="任務 ID 不匹配")

        if retranscribe_task.status != "completed":
            raise HTTPException(status_code=400, detail="重新轉錄任務尚未完成")

        if not retranscribe_task.result:
            raise HTTPException(status_code=400, detail="重新轉錄任務沒有結果")

        # 載入原始字幕資料
        subtitle_collection = SubtitleService.load_subtitle_data(task_id, tasks)

        # 替換指定的字幕條目
        subtitle_index = retranscribe_task.request.subtitle_index
        if subtitle_index < 0 or subtitle_index >= len(subtitle_collection.subtitles):
            raise HTTPException(status_code=400, detail="字幕索引超出範圍")

        # 更新字幕條目
        subtitle_collection.subtitles[subtitle_index] = retranscribe_task.result

        # 儲存更新後的字幕資料
        save_result = SubtitleService.save_subtitle_data(
            task_id, subtitle_collection, tasks
        )

        return {
            "message": "重新轉錄結果已應用",
            "subtitle_index": subtitle_index,
            "updated_text": retranscribe_task.result.text,
            "save_result": save_result,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"應用重新轉錄結果時出錯: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"應用重新轉錄結果時出錯: {str(e)}")


@router.delete("/retranscribe/{retranscribe_task_id}")
async def delete_retranscribe_task(
    retranscribe_task_id: str = FastAPIPath(..., description="重新轉錄任務 ID"),
):
    """刪除重新轉錄任務"""
    try:
        retranscribe_service = get_retranscribe_service()

        with retranscribe_service._lock:
            if retranscribe_task_id not in retranscribe_service.retranscribe_tasks:
                raise HTTPException(status_code=404, detail="重新轉錄任務不存在")

            task = retranscribe_service.retranscribe_tasks[retranscribe_task_id]

            # 只允許刪除已完成或失敗的任務
            if task.status not in ["completed", "failed"]:
                raise HTTPException(
                    status_code=400, detail="只能刪除已完成或失敗的任務"
                )

            del retranscribe_service.retranscribe_tasks[retranscribe_task_id]

        return {"message": "重新轉錄任務已刪除"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"刪除重新轉錄任務時出錯: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"刪除重新轉錄任務時出錯: {str(e)}")


# 注意：字幕格式生成函數已移至 subtitle_converter.py 模組
