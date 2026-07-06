#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
字幕格式轉換器
支援多種字幕格式的匯出功能，包括 SRT、VTT、TXT 等格式
"""

import os
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from backend.models import SubtitleCollection


class SubtitleConverter:
    """字幕格式轉換器類"""

    SUPPORTED_FORMATS = {"srt", "vtt", "txt", "json", "ass", "ssa"}

    def __init__(self):
        """初始化轉換器"""
        self.format_handlers = {
            "srt": self._convert_to_srt,
            "vtt": self._convert_to_vtt,
            "txt": self._convert_to_txt,
            "json": self._convert_to_json,
            "ass": self._convert_to_ass,
            "ssa": self._convert_to_ssa,
        }

    def convert(
        self,
        subtitle_collection: SubtitleCollection,
        format: str,
        output_path: Optional[str] = None,
        encoding: str = "utf-8",
        **options,
    ) -> str:
        """
        轉換字幕到指定格式

        Args:
            subtitle_collection: 字幕集合
            format: 目標格式
            output_path: 輸出檔案路徑（可選）
            encoding: 檔案編碼
            **options: 格式特定選項

        Returns:
            str: 轉換後的內容或檔案路徑

        Raises:
            ValueError: 不支援的格式
            IOError: 檔案寫入錯誤
        """
        format = format.lower()
        if format not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"不支援的格式: {format}，支援的格式: {self.SUPPORTED_FORMATS}"
            )

        # 獲取轉換處理器
        handler = self.format_handlers[format]

        # 執行轉換
        content = handler(subtitle_collection, **options)

        # 如果指定了輸出路徑，寫入檔案
        if output_path:
            try:
                # 確保目錄存在
                os.makedirs(os.path.dirname(output_path), exist_ok=True)

                # 寫入檔案
                if format == "json":
                    with open(output_path, "w", encoding=encoding) as f:
                        json.dump(content, f, ensure_ascii=False, indent=2)
                else:
                    with open(output_path, "w", encoding=encoding) as f:
                        f.write(content)

                return output_path
            except Exception as e:
                raise IOError(f"寫入檔案失敗: {str(e)}")

        # 返回內容
        if format == "json":
            return json.dumps(content, ensure_ascii=False, indent=2)
        return content

    def _convert_to_srt(
        self, subtitle_collection: SubtitleCollection, **options
    ) -> str:
        """轉換為 SRT 格式"""
        lines = []

        for i, subtitle in enumerate(subtitle_collection.subtitles, 1):
            # 序號
            lines.append(str(i))

            # 時間戳
            start_time = self._format_srt_time(subtitle.start_time)
            end_time = self._format_srt_time(subtitle.end_time)
            lines.append(f"{start_time} --> {end_time}")

            # 字幕文字
            text = subtitle.text.strip()
            if text:
                lines.append(text)

            # 空行分隔
            lines.append("")

        return "\n".join(lines)

    def _convert_to_vtt(
        self, subtitle_collection: SubtitleCollection, **options
    ) -> str:
        """轉換為 VTT 格式"""
        lines = ["WEBVTT", ""]

        # 添加元資料註釋（可選）
        if options.get("include_metadata", True):
            metadata = subtitle_collection.metadata
            lines.extend(
                [
                    f"NOTE Created: {datetime.fromtimestamp(metadata.created_at).isoformat()}",
                    f"NOTE Language: {metadata.language}",
                    f"NOTE Total Duration: {metadata.total_duration:.2f}s",
                    "",
                ]
            )

        for subtitle in subtitle_collection.subtitles:
            # 時間戳
            start_time = self._format_vtt_time(subtitle.start_time)
            end_time = self._format_vtt_time(subtitle.end_time)
            lines.append(f"{start_time} --> {end_time}")

            # 字幕文字
            text = subtitle.text.strip()
            if text:
                lines.append(text)

            # 空行分隔
            lines.append("")

        return "\n".join(lines)

    def _convert_to_txt(
        self, subtitle_collection: SubtitleCollection, **options
    ) -> str:
        """轉換為純文字格式"""
        include_timestamps = options.get("include_timestamps", False)
        include_index = options.get("include_index", False)
        separator = options.get("separator", "\n")

        lines = []

        for subtitle in subtitle_collection.subtitles:
            text_parts = []

            # 添加索引（可選）
            if include_index:
                text_parts.append(f"[{subtitle.index + 1}]")

            # 添加時間戳（可選）
            if include_timestamps:
                start_time = self._format_readable_time(subtitle.start_time)
                end_time = self._format_readable_time(subtitle.end_time)
                text_parts.append(f"({start_time} - {end_time})")

            # 添加文字內容
            text = subtitle.text.strip()
            if text:
                text_parts.append(text)

            if text_parts:
                lines.append(" ".join(text_parts))

        return separator.join(lines)

    def _convert_to_json(
        self, subtitle_collection: SubtitleCollection, **options
    ) -> Dict[str, Any]:
        """轉換為 JSON 格式"""
        include_words = options.get("include_words", True)
        include_metadata = options.get("include_metadata", True)

        result = {"task_id": subtitle_collection.task_id, "subtitles": []}

        # 添加字幕資料
        for subtitle in subtitle_collection.subtitles:
            subtitle_data = {
                "index": subtitle.index,
                "start_time": subtitle.start_time,
                "end_time": subtitle.end_time,
                "text": subtitle.text,
            }

            if subtitle.confidence is not None:
                subtitle_data["confidence"] = subtitle.confidence

            if include_words and subtitle.words:
                subtitle_data["words"] = [
                    {
                        "word": word.word,
                        "start": word.start,
                        "end": word.end,
                        "confidence": word.confidence,
                    }
                    for word in subtitle.words
                ]

            result["subtitles"].append(subtitle_data)

        # 添加元資料
        if include_metadata:
            result["metadata"] = {
                "language": subtitle_collection.metadata.language,
                "model_used": subtitle_collection.metadata.model_used,
                "created_at": subtitle_collection.metadata.created_at,
                "last_modified": subtitle_collection.metadata.last_modified,
                "total_duration": subtitle_collection.metadata.total_duration,
                "total_segments": subtitle_collection.metadata.total_segments,
            }

            if subtitle_collection.metadata.video_info:
                result["metadata"]["video_info"] = (
                    subtitle_collection.metadata.video_info.dict()
                )

        return result

    def _convert_to_ass(
        self, subtitle_collection: SubtitleCollection, **options
    ) -> str:
        """轉換為 ASS (Advanced SubStation Alpha) 格式"""
        lines = [
            "[Script Info]",
            "Title: Subtitle Export",
            f"ScriptType: v4.00+",
            f"Collisions: Normal",
            f"PlayDepth: 0",
            f"Timer: 100.0000",
            f"Video Aspect Ratio: 0",
            f"WrapStyle: 0",
            f"ScaledBorderAndShadow: no",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]

        for subtitle in subtitle_collection.subtitles:
            start_time = self._format_ass_time(subtitle.start_time)
            end_time = self._format_ass_time(subtitle.end_time)
            text = subtitle.text.replace("\n", "\\N")  # ASS 換行符

            lines.append(f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}")

        return "\n".join(lines)

    def _convert_to_ssa(
        self, subtitle_collection: SubtitleCollection, **options
    ) -> str:
        """轉換為 SSA (SubStation Alpha) 格式"""
        lines = [
            "[Script Info]",
            "Title: Subtitle Export",
            "ScriptType: v4.00",
            "Collisions: Normal",
            "PlayDepth: 0",
            "",
            "[V4 Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, TertiaryColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, AlphaLevel, Encoding",
            "Style: Default,Arial,20,16777215,255,0,0,0,0,1,2,0,2,10,10,10,0,1",
            "",
            "[Events]",
            "Format: Marked, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]

        for subtitle in subtitle_collection.subtitles:
            start_time = self._format_ssa_time(subtitle.start_time)
            end_time = self._format_ssa_time(subtitle.end_time)
            text = subtitle.text.replace("\n", "\\n")  # SSA 換行符

            lines.append(
                f"Dialogue: Marked=0,{start_time},{end_time},Default,,0,0,0,,{text}"
            )

        return "\n".join(lines)

    def _format_srt_time(self, seconds: float) -> str:
        """格式化 SRT 時間格式 (HH:MM:SS,mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"

    def _format_vtt_time(self, seconds: float) -> str:
        """格式化 VTT 時間格式 (HH:MM:SS.mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"

    def _format_ass_time(self, seconds: float) -> str:
        """格式化 ASS 時間格式 (H:MM:SS.cc)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        cs = int((seconds % 1) * 100)  # 百分之一秒
        return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"

    def _format_ssa_time(self, seconds: float) -> str:
        """格式化 SSA 時間格式 (H:MM:SS.cc)"""
        return self._format_ass_time(seconds)  # SSA 和 ASS 時間格式相同

    def _format_readable_time(self, seconds: float) -> str:
        """格式化可讀時間格式 (MM:SS 或 HH:MM:SS)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"

    @classmethod
    def get_supported_formats(cls) -> List[str]:
        """獲取支援的格式列表"""
        return list(cls.SUPPORTED_FORMATS)

    @classmethod
    def is_format_supported(cls, format: str) -> bool:
        """檢查格式是否支援"""
        return format.lower() in cls.SUPPORTED_FORMATS

    def get_format_info(self, format: str) -> Optional[Dict[str, str]]:
        """獲取格式資訊"""
        format_info = {
            "srt": {
                "name": "SRT",
                "description": "SubRip 字幕格式",
                "extension": "srt",
                "mimeType": "text/plain",
                "icon": "bi-file-text",
            },
            "vtt": {
                "name": "VTT",
                "description": "WebVTT 字幕格式",
                "extension": "vtt",
                "mimeType": "text/vtt",
                "icon": "bi-file-code",
            },
            "txt": {
                "name": "TXT",
                "description": "純文字格式",
                "extension": "txt",
                "mimeType": "text/plain",
                "icon": "bi-file-earmark-text",
            },
            "json": {
                "name": "JSON",
                "description": "JSON 資料格式",
                "extension": "json",
                "mimeType": "application/json",
                "icon": "bi-file-earmark-code",
            },
            "ass": {
                "name": "ASS",
                "description": "Advanced SubStation Alpha 格式",
                "extension": "ass",
                "mimeType": "text/plain",
                "icon": "bi-file-text",
            },
            "ssa": {
                "name": "SSA",
                "description": "SubStation Alpha 格式",
                "extension": "ssa",
                "mimeType": "text/plain",
                "icon": "bi-file-text",
            },
        }

        return format_info.get(format.lower())

    def validate_subtitle_collection(
        self, subtitle_collection: SubtitleCollection
    ) -> List[str]:
        """
        驗證字幕集合的有效性

        Returns:
            List[str]: 驗證錯誤列表，空列表表示無錯誤
        """
        errors = []

        if not subtitle_collection.subtitles:
            errors.append("字幕集合為空")
            return errors

        # 檢查時間戳順序
        for i, subtitle in enumerate(subtitle_collection.subtitles):
            # 檢查基本時間戳有效性
            if subtitle.start_time < 0:
                errors.append(f"字幕 {i} 開始時間為負數: {subtitle.start_time}")

            if subtitle.end_time <= subtitle.start_time:
                errors.append(
                    f"字幕 {i} 結束時間不大於開始時間: {subtitle.start_time} >= {subtitle.end_time}"
                )

            # 檢查文字內容
            if not subtitle.text.strip():
                errors.append(f"字幕 {i} 文字內容為空")

            # 檢查與下一個字幕的重疊
            if i < len(subtitle_collection.subtitles) - 1:
                next_subtitle = subtitle_collection.subtitles[i + 1]
                if subtitle.end_time > next_subtitle.start_time:
                    errors.append(f"字幕 {i} 與字幕 {i + 1} 時間重疊")

        return errors
