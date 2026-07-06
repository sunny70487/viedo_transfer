#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
音頻片段提取服務
提供基於時間戳的音頻切割功能，支援音頻格式轉換和品質最佳化
"""

import os
import tempfile
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, validator
import shutil

# 設置日誌
logger = logging.getLogger("audio_segment_service")


class AudioSegmentRequest(BaseModel):
    """音頻片段提取請求模型"""
    audio_file_path: str = Field(..., description="原始音頻文件路徑")
    start_time: float = Field(..., ge=0, description="開始時間（秒）")
    end_time: float = Field(..., ge=0, description="結束時間（秒）")
    output_format: str = Field(default="flac", description="輸出音頻格式")
    quality: str = Field(default="high", description="音頻品質")
    sample_rate: Optional[int] = Field(None, description="採樣率")
    channels: Optional[int] = Field(None, description="聲道數")

    @validator('end_time')
    def end_time_must_be_after_start_time(cls, v, values):
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('結束時間必須大於開始時間')
        return v

    @validator('output_format')
    def validate_output_format(cls, v):
        supported_formats = ['flac', 'wav', 'mp3', 'aac', 'ogg']
        if v.lower() not in supported_formats:
            raise ValueError(f'不支援的音頻格式: {v}，支援的格式: {supported_formats}')
        return v.lower()

    @validator('quality')
    def validate_quality(cls, v):
        valid_qualities = ['low', 'medium', 'high', 'lossless']
        if v.lower() not in valid_qualities:
            raise ValueError(f'無效的品質設定: {v}，有效設定: {valid_qualities}')
        return v.lower()


class AudioSegmentResult(BaseModel):
    """音頻片段提取結果模型"""
    success: bool = Field(..., description="是否成功")
    output_file_path: Optional[str] = Field(None, description="輸出文件路徑")
    duration: Optional[float] = Field(None, description="片段時長（秒）")
    file_size: Optional[int] = Field(None, description="文件大小（位元組）")
    format: Optional[str] = Field(None, description="輸出格式")
    sample_rate: Optional[int] = Field(None, description="採樣率")
    channels: Optional[int] = Field(None, description="聲道數")
    error_message: Optional[str] = Field(None, description="錯誤訊息")


class AudioSegmentService:
    """音頻片段提取服務類"""
    
    def __init__(self):
        self.temp_dir = None
        self._check_ffmpeg()
    
    def _check_ffmpeg(self):
        """檢查 FFmpeg 是否可用"""
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                raise RuntimeError("FFmpeg 不可用")
            logger.info("FFmpeg 檢查通過")
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
            logger.error(f"FFmpeg 檢查失敗: {str(e)}")
            raise RuntimeError(f"FFmpeg 不可用: {str(e)}")
    
    def _get_audio_info(self, audio_file_path: str) -> Dict[str, Any]:
        """獲取音頻文件資訊"""
        try:
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json', 
                '-show_format', '-show_streams', audio_file_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                raise RuntimeError(f"無法獲取音頻資訊: {result.stderr}")
            
            import json
            probe_data = json.loads(result.stdout)
            
            # 尋找音頻流
            audio_stream = None
            for stream in probe_data.get('streams', []):
                if stream.get('codec_type') == 'audio':
                    audio_stream = stream
                    break
            
            if not audio_stream:
                raise RuntimeError("找不到音頻流")
            
            format_info = probe_data.get('format', {})
            
            return {
                'duration': float(format_info.get('duration', 0)),
                'sample_rate': int(audio_stream.get('sample_rate', 0)),
                'channels': int(audio_stream.get('channels', 0)),
                'codec': audio_stream.get('codec_name', 'unknown'),
                'bit_rate': int(format_info.get('bit_rate', 0)),
                'format_name': format_info.get('format_name', 'unknown')
            }
            
        except Exception as e:
            logger.error(f"獲取音頻資訊時出錯: {str(e)}")
            raise RuntimeError(f"獲取音頻資訊失敗: {str(e)}")
    
    def _get_quality_settings(self, format: str, quality: str) -> Dict[str, str]:
        """根據格式和品質獲取編碼設定"""
        quality_settings = {
            'flac': {
                'low': {'compression_level': '8'},
                'medium': {'compression_level': '5'},
                'high': {'compression_level': '1'},
                'lossless': {'compression_level': '0'}
            },
            'wav': {
                'low': {'sample_fmt': 's16'},
                'medium': {'sample_fmt': 's24'},
                'high': {'sample_fmt': 's32'},
                'lossless': {'sample_fmt': 'f32'}
            },
            'mp3': {
                'low': {'b:a': '128k'},
                'medium': {'b:a': '192k'},
                'high': {'b:a': '320k'},
                'lossless': {'b:a': '320k'}
            },
            'aac': {
                'low': {'b:a': '128k'},
                'medium': {'b:a': '192k'},
                'high': {'b:a': '256k'},
                'lossless': {'b:a': '320k'}
            },
            'ogg': {
                'low': {'q:a': '3'},
                'medium': {'q:a': '6'},
                'high': {'q:a': '9'},
                'lossless': {'q:a': '10'}
            }
        }
        
        return quality_settings.get(format, {}).get(quality, {})
    
    def extract_segment(self, request: AudioSegmentRequest, 
                       output_dir: Optional[str] = None) -> AudioSegmentResult:
        """提取音頻片段"""
        try:
            # 驗證輸入文件
            if not os.path.exists(request.audio_file_path):
                return AudioSegmentResult(
                    success=False,
                    error_message=f"音頻文件不存在: {request.audio_file_path}"
                )
            
            # 獲取音頻資訊
            audio_info = self._get_audio_info(request.audio_file_path)
            
            # 驗證時間範圍
            if request.end_time > audio_info['duration']:
                logger.warning(f"結束時間 {request.end_time} 超過音頻總時長 {audio_info['duration']}")
                # 調整結束時間到音頻總時長
                request.end_time = audio_info['duration']
            
            # 設置輸出目錄
            if output_dir is None:
                if self.temp_dir is None:
                    self.temp_dir = tempfile.mkdtemp(prefix="audio_segments_")
                output_dir = self.temp_dir
            else:
                Path(output_dir).mkdir(parents=True, exist_ok=True)
            
            # 生成輸出文件名
            duration = request.end_time - request.start_time
            output_filename = f"segment_{request.start_time:.2f}_{request.end_time:.2f}.{request.output_format}"
            output_path = os.path.join(output_dir, output_filename)
            
            # 構建 FFmpeg 命令
            cmd = [
                'ffmpeg', '-y',  # 覆蓋輸出文件
                '-ss', str(request.start_time),  # 開始時間
                '-i', request.audio_file_path,   # 輸入文件
                '-t', str(duration),             # 持續時間
                '-vn',                           # 不包含視頻
            ]
            
            # 添加音頻編碼器
            if request.output_format == 'flac':
                cmd.extend(['-c:a', 'flac'])
            elif request.output_format == 'wav':
                cmd.extend(['-c:a', 'pcm_s16le'])
            elif request.output_format == 'mp3':
                cmd.extend(['-c:a', 'libmp3lame'])
            elif request.output_format == 'aac':
                cmd.extend(['-c:a', 'aac'])
            elif request.output_format == 'ogg':
                cmd.extend(['-c:a', 'libvorbis'])
            
            # 添加品質設定
            quality_settings = self._get_quality_settings(request.output_format, request.quality)
            for key, value in quality_settings.items():
                cmd.extend([f'-{key}', value])
            
            # 添加採樣率設定
            if request.sample_rate:
                cmd.extend(['-ar', str(request.sample_rate)])
            
            # 添加聲道設定
            if request.channels:
                cmd.extend(['-ac', str(request.channels)])
            
            # 添加輸出文件
            cmd.append(output_path)
            
            logger.info(f"執行音頻片段提取: {' '.join(cmd)}")
            
            # 執行 FFmpeg 命令
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                error_msg = f"FFmpeg 執行失敗: {result.stderr}"
                logger.error(error_msg)
                return AudioSegmentResult(
                    success=False,
                    error_message=error_msg
                )
            
            # 驗證輸出文件
            if not os.path.exists(output_path):
                return AudioSegmentResult(
                    success=False,
                    error_message="輸出文件未生成"
                )
            
            # 獲取輸出文件資訊
            output_info = self._get_audio_info(output_path)
            file_size = os.path.getsize(output_path)
            
            logger.info(f"音頻片段提取成功: {output_path}")
            
            return AudioSegmentResult(
                success=True,
                output_file_path=output_path,
                duration=output_info['duration'],
                file_size=file_size,
                format=request.output_format,
                sample_rate=output_info['sample_rate'],
                channels=output_info['channels']
            )
            
        except Exception as e:
            error_msg = f"音頻片段提取時出錯: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return AudioSegmentResult(
                success=False,
                error_message=error_msg
            )
    
    def cleanup_temp_files(self):
        """清理臨時文件"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
                logger.info(f"已清理臨時目錄: {self.temp_dir}")
                self.temp_dir = None
            except Exception as e:
                logger.warning(f"清理臨時目錄時出錯: {str(e)}")
    
    def __del__(self):
        """析構函數，自動清理臨時文件"""
        self.cleanup_temp_files()