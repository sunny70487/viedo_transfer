#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
片段重新轉錄服務
提供音頻片段重新轉錄功能，包括任務排隊和處理邏輯
"""

import os
import uuid
import time
import threading
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json

from backend.models import RetranscribeRequest, RetranscribeTask, Subtitle, Word
from backend.services.audio_segment_service import (
    AudioSegmentService,
    AudioSegmentRequest,
)
from backend.faster_whisper_transcribe import transcribe_audio

# 設置日誌
logger = logging.getLogger("retranscribe_service")


class RetranscribeService:
    """重新轉錄服務類"""

    def __init__(self, max_workers: int = 2):
        self.retranscribe_tasks: Dict[str, RetranscribeTask] = {}
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.audio_service = AudioSegmentService()
        self._lock = threading.Lock()

    def create_retranscribe_task(
        self, request: RetranscribeRequest, tasks_storage: Dict[str, Any]
    ) -> str:
        """創建重新轉錄任務"""
        try:
            # 驗證原始任務
            if request.task_id not in tasks_storage:
                raise ValueError(f"原始任務不存在: {request.task_id}")

            original_task = tasks_storage[request.task_id]
            if original_task.status != "completed" or not original_task.result:
                raise ValueError("原始任務尚未完成或沒有結果")

            # 生成重新轉錄任務 ID
            retranscribe_task_id = str(uuid.uuid4())

            # 創建重新轉錄任務
            retranscribe_task = RetranscribeTask(
                id=retranscribe_task_id,
                original_task_id=request.task_id,
                request=request,
                status="queued",
                message="任務已加入隊列",
            )

            with self._lock:
                self.retranscribe_tasks[retranscribe_task_id] = retranscribe_task

            # 提交任務到執行器
            future = self.executor.submit(
                self._process_retranscribe_task, retranscribe_task_id, tasks_storage
            )

            logger.info(f"重新轉錄任務已創建: {retranscribe_task_id}")
            return retranscribe_task_id

        except Exception as e:
            logger.error(f"創建重新轉錄任務時出錯: {str(e)}", exc_info=True)
            raise

    def get_retranscribe_task(self, task_id: str) -> Optional[RetranscribeTask]:
        """獲取重新轉錄任務"""
        with self._lock:
            return self.retranscribe_tasks.get(task_id)

    def get_all_retranscribe_tasks(self) -> Dict[str, RetranscribeTask]:
        """獲取所有重新轉錄任務"""
        with self._lock:
            return self.retranscribe_tasks.copy()

    def _process_retranscribe_task(self, task_id: str, tasks_storage: Dict[str, Any]):
        """處理重新轉錄任務"""
        try:
            with self._lock:
                task = self.retranscribe_tasks.get(task_id)

            if not task:
                logger.error(f"重新轉錄任務不存在: {task_id}")
                return

            # 更新任務狀態
            task.status = "processing"
            task.message = "正在處理重新轉錄任務..."
            task.progress = 10.0

            logger.info(f"開始處理重新轉錄任務: {task_id}")

            # 獲取原始任務資料
            original_task = tasks_storage[task.original_task_id]

            # 尋找原始音頻文件
            audio_file_path = self._find_audio_file(original_task)
            if not audio_file_path:
                raise RuntimeError("找不到原始音頻文件")

            task.progress = 20.0
            task.message = "正在提取音頻片段..."

            # 提取音頻片段
            segment_result = self._extract_audio_segment(task, audio_file_path)
            if not segment_result.success:
                raise RuntimeError(f"音頻片段提取失敗: {segment_result.error_message}")

            task.progress = 40.0
            task.message = "正在執行重新轉錄..."

            # 執行重新轉錄
            transcription_result = self._transcribe_segment(
                task, segment_result.output_file_path
            )

            task.progress = 80.0
            task.message = "正在處理轉錄結果..."

            # 處理轉錄結果
            subtitle = self._process_transcription_result(task, transcription_result)

            # 完成任務
            task.status = "completed"
            task.progress = 100.0
            task.message = "重新轉錄完成"
            task.result = subtitle
            task.completed_at = time.time()

            logger.info(f"重新轉錄任務完成: {task_id}")

        except Exception as e:
            error_msg = f"重新轉錄任務失敗: {str(e)}"
            logger.error(error_msg, exc_info=True)

            with self._lock:
                task = self.retranscribe_tasks.get(task_id)
                if task:
                    task.status = "failed"
                    task.error = error_msg
                    task.message = error_msg
                    task.completed_at = time.time()

        finally:
            # 清理臨時文件
            try:
                self.audio_service.cleanup_temp_files()
            except Exception as e:
                logger.warning(f"清理臨時文件時出錯: {str(e)}")

    def _find_audio_file(self, original_task) -> Optional[str]:
        """尋找原始音頻文件"""
        try:
            if not original_task.result or not original_task.result.get("files"):
                return None

            # 優先尋找音頻文件
            audio_extensions = [".flac", ".wav", ".mp3", ".aac", ".ogg"]
            for file_type, file_path in original_task.result["files"].items():
                if any(file_path.lower().endswith(ext) for ext in audio_extensions):
                    if os.path.exists(file_path):
                        return file_path

            # 如果沒有音頻文件，尋找視頻文件
            video_extensions = [".mp4", ".avi", ".mov", ".mkv", ".webm"]
            for file_type, file_path in original_task.result["files"].items():
                if any(file_path.lower().endswith(ext) for ext in video_extensions):
                    if os.path.exists(file_path):
                        return file_path

            return None

        except Exception as e:
            logger.error(f"尋找音頻文件時出錯: {str(e)}")
            return None

    def _extract_audio_segment(self, task: RetranscribeTask, audio_file_path: str):
        """提取音頻片段"""
        try:
            segment_request = AudioSegmentRequest(
                audio_file_path=audio_file_path,
                start_time=task.request.start_time,
                end_time=task.request.end_time,
                output_format="flac",  # 使用 FLAC 格式以保證品質
                quality="high",
            )

            return self.audio_service.extract_segment(segment_request)

        except Exception as e:
            logger.error(f"提取音頻片段時出錯: {str(e)}")
            raise

    def _transcribe_segment(
        self, task: RetranscribeTask, segment_file_path: str
    ) -> Dict[str, Any]:
        """轉錄音頻片段"""
        try:
            # 獲取模型設定
            model_settings = task.request.model_settings or {}

            # 設置預設值
            model_size = model_settings.get("model_size", "large-v3")
            device = model_settings.get("device", "auto")
            compute_type = model_settings.get("compute_type", "default")
            language = model_settings.get("language", None)
            task_type = model_settings.get("task", "transcribe")
            beam_size = model_settings.get("beam_size", 5)
            vad_filter = model_settings.get("vad_filter", True)
            word_timestamps = model_settings.get("word_timestamps", True)

            # 創建臨時輸出目錄
            temp_output_dir = os.path.join(
                os.path.dirname(segment_file_path), f"retranscribe_{task.id}"
            )
            os.makedirs(temp_output_dir, exist_ok=True)

            # 執行轉錄
            transcription_files = transcribe_audio(
                audio_path=segment_file_path,
                model_size=model_size,
                device=device,
                compute_type=compute_type,
                language=language,
                task=task_type,
                beam_size=beam_size,
                vad_filter=vad_filter,
                word_timestamps=word_timestamps,
                output_dir=temp_output_dir,
                output_format="json",
                verbose=False,
                show_in_terminal=False,
            )

            # 讀取 JSON 結果
            json_file = transcription_files.get("json")
            if not json_file or not os.path.exists(json_file):
                raise RuntimeError("轉錄結果文件不存在")

            with open(json_file, "r", encoding="utf-8") as f:
                transcription_data = json.load(f)

            return transcription_data

        except Exception as e:
            logger.error(f"轉錄音頻片段時出錯: {str(e)}")
            raise

    def _process_transcription_result(
        self, task: RetranscribeTask, transcription_data: Dict[str, Any]
    ) -> Subtitle:
        """處理轉錄結果"""
        try:
            # 獲取轉錄的文字和時間戳
            segments = transcription_data.get("segments", [])

            if not segments:
                # 如果沒有分段，創建一個空的字幕
                return Subtitle(
                    index=task.request.subtitle_index,
                    start_time=task.request.start_time,
                    end_time=task.request.end_time,
                    text="",
                    confidence=0.0,
                )

            # 合併所有分段的文字
            combined_text = " ".join([seg.get("text", "").strip() for seg in segments])

            # 計算平均信心度
            confidences = [
                seg.get("avg_logprob", 0.0)
                for seg in segments
                if seg.get("avg_logprob")
            ]
            avg_confidence = (
                sum(confidences) / len(confidences) if confidences else None
            )

            # 收集詞級時間戳
            words = []
            for seg in segments:
                if "words" in seg and seg["words"]:
                    for word_data in seg["words"]:
                        # 調整時間戳到原始音頻的時間
                        adjusted_start = task.request.start_time + word_data.get(
                            "start", 0.0
                        )
                        adjusted_end = task.request.start_time + word_data.get(
                            "end", 0.0
                        )

                        word = Word(
                            word=word_data.get("word", ""),
                            start=adjusted_start,
                            end=adjusted_end,
                            confidence=word_data.get("probability", None),
                        )
                        words.append(word)

            # 創建新的字幕條目
            subtitle = Subtitle(
                index=task.request.subtitle_index,
                start_time=task.request.start_time,
                end_time=task.request.end_time,
                text=combined_text.strip(),
                confidence=avg_confidence,
                words=words if words else None,
            )

            return subtitle

        except Exception as e:
            logger.error(f"處理轉錄結果時出錯: {str(e)}")
            raise

    def cleanup_completed_tasks(self, max_age_hours: int = 24):
        """清理已完成的任務"""
        try:
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600

            tasks_to_remove = []

            with self._lock:
                for task_id, task in self.retranscribe_tasks.items():
                    if (
                        task.status in ["completed", "failed"]
                        and task.completed_at
                        and current_time - task.completed_at > max_age_seconds
                    ):
                        tasks_to_remove.append(task_id)

                for task_id in tasks_to_remove:
                    del self.retranscribe_tasks[task_id]

            if tasks_to_remove:
                logger.info(f"已清理 {len(tasks_to_remove)} 個過期的重新轉錄任務")

        except Exception as e:
            logger.error(f"清理已完成任務時出錯: {str(e)}")

    def shutdown(self):
        """關閉服務"""
        try:
            logger.info("正在關閉重新轉錄服務...")
            self.executor.shutdown(wait=True)
            self.audio_service.cleanup_temp_files()
            logger.info("重新轉錄服務已關閉")
        except Exception as e:
            logger.error(f"關閉重新轉錄服務時出錯: {str(e)}")


# 全域服務實例
_retranscribe_service = None


def get_retranscribe_service() -> RetranscribeService:
    """獲取重新轉錄服務實例"""
    global _retranscribe_service
    if _retranscribe_service is None:
        _retranscribe_service = RetranscribeService()
    return _retranscribe_service


def shutdown_retranscribe_service():
    """關閉重新轉錄服務"""
    global _retranscribe_service
    if _retranscribe_service:
        _retranscribe_service.shutdown()
        _retranscribe_service = None
