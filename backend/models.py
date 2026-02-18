#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
字幕編輯器資料模型
定義所有與字幕編輯相關的 Pydantic 資料模型
"""

from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, validator
from datetime import datetime
import logging
import time

logger = logging.getLogger(__name__)


class Word(BaseModel):
    """詞級時間戳模型"""

    word: str = Field(..., description="詞語內容")
    start: float = Field(..., ge=0, description="開始時間（秒）")
    end: float = Field(..., ge=0, description="結束時間（秒）")
    confidence: Optional[float] = Field(None, ge=0, le=1, description="信心度分數")

    @validator("end")
    def end_must_be_after_start(cls, v, values):
        if "start" in values and v < values["start"]:
            raise ValueError("結束時間必須大於或等於開始時間")
        return v


class Subtitle(BaseModel):
    """字幕條目模型"""

    index: int = Field(..., ge=0, description="字幕索引")
    start_time: float = Field(..., ge=0, description="開始時間（秒）")
    end_time: float = Field(..., ge=0, description="結束時間（秒）")
    text: str = Field(..., min_length=1, description="字幕文字內容")
    confidence: Optional[float] = Field(
        None, description="轉錄信心度（avg_logprob，可為負值）"
    )
    words: Optional[List[Word]] = Field(None, description="詞級時間戳列表")

    @validator("end_time")
    def end_time_must_be_after_start_time(cls, v, values):
        if "start_time" in values and v < values["start_time"]:
            raise ValueError("結束時間必須大於或等於開始時間")
        return v

    @validator("text")
    def text_must_not_be_empty(cls, v):
        if not v.strip():
            raise ValueError("字幕文字不能為空")
        return v.strip()

    @validator("words")
    def validate_words_timing(cls, v, values):
        """驗證並自動鉗位詞級時間戳到字幕範圍內"""
        if v is None:
            return v

        start_time = values.get("start_time", 0)
        end_time = values.get("end_time", 0)

        for word in v:
            if word.start < start_time or word.end > end_time:
                logger.warning(
                    f'詞語 "{word.word}" 的時間戳 ({word.start:.3f}-{word.end:.3f}) '
                    f"超出字幕範圍 ({start_time:.3f}-{end_time:.3f})，已自動鉗位"
                )
                word.start = max(word.start, start_time)
                word.end = min(word.end, end_time)
                # 鉗位後確保 start <= end
                if word.start > word.end:
                    word.start = word.end

        return v


class VideoInfo(BaseModel):
    """影片資訊模型"""

    duration: Optional[float] = Field(None, ge=0, description="影片總時長（秒）")
    format: Optional[str] = Field(None, description="影片格式")
    resolution: Optional[str] = Field(None, description="影片解析度")
    fps: Optional[float] = Field(None, ge=0, description="影片幀率")
    video_url: Optional[str] = Field(None, description="影片播放 URL")
    file_size: Optional[int] = Field(None, ge=0, description="檔案大小（位元組）")


class SubtitleMetadata(BaseModel):
    """字幕元資料模型"""

    language: Optional[str] = Field(default="unknown", description="語言代碼")

    @validator("language", pre=True, always=True)
    def language_must_not_be_none(cls, v):
        return v if v is not None else "unknown"

    model_used: Optional[str] = Field(None, description="使用的 Whisper 模型")
    created_at: float = Field(default_factory=time.time, description="創建時間戳")
    last_modified: float = Field(
        default_factory=time.time, description="最後修改時間戳"
    )
    total_duration: Optional[float] = Field(None, ge=0, description="總時長（秒）")
    total_segments: Optional[int] = Field(None, ge=0, description="總字幕段數")
    video_info: Optional[VideoInfo] = Field(None, description="影片資訊")
    transcription_settings: Optional[Dict[str, Any]] = Field(
        None, description="轉錄設定"
    )

    @validator("last_modified")
    def last_modified_must_be_after_created(cls, v, values):
        if "created_at" in values and v < values["created_at"]:
            logger.warning(
                f"最後修改時間 ({v}) 早於創建時間 ({values['created_at']})，"
                f"自動修正為當前時間"
            )
            return time.time()
        return v


class SubtitleCollection(BaseModel):
    """字幕集合模型"""

    task_id: str = Field(..., min_length=1, description="任務 ID")
    subtitles: List[Subtitle] = Field(default_factory=list, description="字幕列表")
    metadata: SubtitleMetadata = Field(
        default_factory=SubtitleMetadata, description="元資料"
    )

    @validator("subtitles")
    def validate_subtitle_order(cls, v):
        """驗證字幕時間順序（重疊僅記錄警告，不阻擋儲存）"""
        if len(v) <= 1:
            return v

        for i in range(1, len(v)):
            if v[i].start_time < v[i - 1].end_time:
                logger.warning(
                    f"字幕 {i} 的開始時間與前一個字幕重疊 "
                    f"(prev end={v[i - 1].end_time}, cur start={v[i].start_time})"
                )

        return v

    @validator("metadata")
    def update_metadata_from_subtitles(cls, v, values):
        """從字幕資料更新元資料"""
        subtitles = values.get("subtitles", [])
        if subtitles:
            v.total_segments = len(subtitles)
            v.total_duration = max([sub.end_time for sub in subtitles])
        return v

    def add_subtitle(self, subtitle: Subtitle) -> None:
        """添加字幕條目"""
        # 更新索引
        subtitle.index = len(self.subtitles)
        self.subtitles.append(subtitle)
        self._update_metadata()

    def remove_subtitle(self, index: int) -> bool:
        """移除字幕條目"""
        if 0 <= index < len(self.subtitles):
            self.subtitles.pop(index)
            # 重新編號
            for i, subtitle in enumerate(self.subtitles):
                subtitle.index = i
            self._update_metadata()
            return True
        return False

    def split_subtitle(self, index: int, split_time: float) -> bool:
        """分割字幕條目"""
        if not (0 <= index < len(self.subtitles)):
            return False

        original = self.subtitles[index]
        if not (original.start_time < split_time < original.end_time):
            return False

        # 創建兩個新的字幕條目
        first_part = Subtitle(
            index=index,
            start_time=original.start_time,
            end_time=split_time,
            text=original.text,  # 可以後續手動編輯
            confidence=original.confidence,
        )

        second_part = Subtitle(
            index=index + 1,
            start_time=split_time,
            end_time=original.end_time,
            text=original.text,  # 可以後續手動編輯
            confidence=original.confidence,
        )

        # 替換原字幕
        self.subtitles[index] = first_part
        self.subtitles.insert(index + 1, second_part)

        # 重新編號後續字幕
        for i in range(index + 2, len(self.subtitles)):
            self.subtitles[i].index = i

        self._update_metadata()
        return True

    def merge_subtitles(self, start_index: int, end_index: int) -> bool:
        """合併字幕條目"""
        if not (0 <= start_index < end_index < len(self.subtitles)):
            return False

        # 創建合併後的字幕
        first_subtitle = self.subtitles[start_index]
        last_subtitle = self.subtitles[end_index]

        merged_text = " ".join(
            [self.subtitles[i].text for i in range(start_index, end_index + 1)]
        )

        merged_subtitle = Subtitle(
            index=start_index,
            start_time=first_subtitle.start_time,
            end_time=last_subtitle.end_time,
            text=merged_text,
            confidence=first_subtitle.confidence,  # 使用第一個的信心度
        )

        # 移除舊字幕並插入新字幕
        del self.subtitles[start_index : end_index + 1]
        self.subtitles.insert(start_index, merged_subtitle)

        # 重新編號
        for i, subtitle in enumerate(self.subtitles):
            subtitle.index = i

        self._update_metadata()
        return True

    def _update_metadata(self) -> None:
        """更新元資料"""
        self.metadata.last_modified = time.time()
        self.metadata.total_segments = len(self.subtitles)
        if self.subtitles:
            self.metadata.total_duration = max([sub.end_time for sub in self.subtitles])


class RetranscribeRequest(BaseModel):
    """重新轉錄請求模型"""

    task_id: str = Field(..., min_length=1, description="原始任務 ID")
    start_time: float = Field(..., ge=0, description="重新轉錄開始時間（秒）")
    end_time: float = Field(..., ge=0, description="重新轉錄結束時間（秒）")
    subtitle_index: int = Field(..., ge=0, description="要替換的字幕索引")
    model_settings: Optional[Dict[str, Any]] = Field(
        None, description="Whisper 模型設定"
    )

    @validator("end_time")
    def end_time_must_be_after_start_time(cls, v, values):
        if "start_time" in values and v <= values["start_time"]:
            raise ValueError("結束時間必須大於開始時間")
        return v

    @validator("model_settings")
    def validate_model_settings(cls, v):
        if v is None:
            return v

        # 驗證模型設定的有效性
        valid_keys = {
            "model_size",
            "device",
            "compute_type",
            "language",
            "task",
            "beam_size",
            "vad_filter",
            "word_timestamps",
        }

        invalid_keys = set(v.keys()) - valid_keys
        if invalid_keys:
            raise ValueError(f"無效的模型設定鍵: {invalid_keys}")

        return v


class RetranscribeTask(BaseModel):
    """重新轉錄任務模型"""

    id: str = Field(..., min_length=1, description="重新轉錄任務 ID")
    original_task_id: str = Field(..., min_length=1, description="原始任務 ID")
    request: RetranscribeRequest = Field(..., description="重新轉錄請求")
    status: str = Field(default="queued", description="任務狀態")
    progress: float = Field(default=0.0, ge=0, le=100, description="進度百分比")
    message: str = Field(default="", description="狀態訊息")
    result: Optional[Subtitle] = Field(None, description="重新轉錄結果")
    error: Optional[str] = Field(None, description="錯誤訊息")
    created_at: float = Field(default_factory=time.time, description="創建時間戳")
    completed_at: Optional[float] = Field(None, description="完成時間戳")

    @validator("status")
    def validate_status(cls, v):
        valid_statuses = {"queued", "processing", "completed", "failed"}
        if v not in valid_statuses:
            raise ValueError(f"無效的狀態: {v}，有效狀態: {valid_statuses}")
        return v


class SubtitleExportRequest(BaseModel):
    """字幕匯出請求模型"""

    task_id: str = Field(..., min_length=1, description="任務 ID")
    format: str = Field(..., description="匯出格式")
    include_timestamps: bool = Field(default=True, description="是否包含時間戳")
    encoding: str = Field(default="utf-8", description="檔案編碼")

    @validator("format")
    def validate_format(cls, v):
        valid_formats = {"srt", "vtt", "txt", "json", "ass", "ssa"}
        if v.lower() not in valid_formats:
            raise ValueError(f"不支援的格式: {v}，支援的格式: {valid_formats}")
        return v.lower()

    @validator("encoding")
    def validate_encoding(cls, v):
        valid_encodings = {"utf-8", "utf-16", "gbk", "big5"}
        if v.lower() not in valid_encodings:
            raise ValueError(f"不支援的編碼: {v}，支援的編碼: {valid_encodings}")
        return v.lower()


class SubtitleSearchRequest(BaseModel):
    """字幕搜尋請求模型"""

    task_id: str = Field(..., min_length=1, description="任務 ID")
    query: str = Field(..., min_length=1, description="搜尋關鍵字")
    case_sensitive: bool = Field(default=False, description="是否區分大小寫")
    regex: bool = Field(default=False, description="是否使用正規表達式")
    time_range: Optional[Dict[str, float]] = Field(None, description="時間範圍篩選")

    @validator("time_range")
    def validate_time_range(cls, v):
        if v is None:
            return v

        if "start" in v and "end" in v:
            if v["end"] <= v["start"]:
                raise ValueError("結束時間必須大於開始時間")

        return v


class SubtitleSearchResult(BaseModel):
    """字幕搜尋結果模型"""

    matches: List[Dict[str, Any]] = Field(default_factory=list, description="匹配結果")
    total_matches: int = Field(default=0, description="總匹配數")
    search_time: float = Field(default=0.0, description="搜尋耗時（秒）")

    class Config:
        schema_extra = {
            "example": {
                "matches": [
                    {
                        "subtitle_index": 0,
                        "start_time": 1.5,
                        "end_time": 4.2,
                        "text": "這是匹配的字幕文字",
                        "match_positions": [2, 5],
                    }
                ],
                "total_matches": 1,
                "search_time": 0.05,
            }
        }
