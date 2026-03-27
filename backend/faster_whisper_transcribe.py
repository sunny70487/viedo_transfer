#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import os
import time
import torch
import numpy as np
import tempfile
import re
import subprocess  # 確保導入 subprocess 用於調用外部命令
from pathlib import Path
from faster_whisper import WhisperModel
from pydub import AudioSegment
import yt_dlp
import multiprocessing as mp
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from backend.shared.download_helpers import (
    build_safe_title,
    build_yt_dlp_options,
    download_from_url as shared_download_from_url,
)
from backend.shared.transcribe_helpers import (
    check_gpu as shared_check_gpu,
    format_timestamp as shared_format_timestamp,
)
from backend.shared.split_audio_helpers import split_audio as shared_split_audio
from backend.shared.video_utils import maybe_prepare_video_output

# 嘗試導入 tqdm 用於顯示進度條，但如果不可用也能繼續執行
try:
    from tqdm import tqdm

    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False


def check_gpu():
    return shared_check_gpu(torch)


def split_audio(
    audio_path, segment_duration=30, output_dir=None, verbose=True, max_workers=None
):
    tqdm_factory = tqdm if verbose and TQDM_AVAILABLE else None
    return shared_split_audio(
        audio_path,
        segment_duration=segment_duration,
        output_dir=output_dir,
        verbose=verbose,
        max_workers=max_workers,
        tqdm_factory=tqdm_factory,
    )


_MODEL_CACHE_LOCK = threading.Lock()
_LOADED_MODELS = {}


def transcribe_audio(
    audio_path,
    model_size="large-v3",
    device="auto",
    compute_type="default",
    language=None,
    task="transcribe",
    beam_size=5,
    vad_filter=True,
    vad_parameters=None,
    word_timestamps=True,
    output_dir=None,
    output_format="txt",
    verbose=True,
    show_in_terminal=False,
    split_segments=False,
    segment_duration=30,
    max_workers=None,
    status_callback=None,
):
    """
    使用 Faster Whisper 將音檔轉錄為文本

    參數:
        audio_path (str): 音檔文件的路徑
        model_size (str): 模型大小 (tiny, base, small, medium, large-v1, large-v2, large-v3)
        device (str): 運行設備 (auto, cpu, cuda)
        compute_type (str): 計算類型 (default, float16, int8, int8_float16)
        language (str): 語言代碼 (如 'zh', 'en')，None 表示自動檢測
        task (str): 任務類型 (transcribe, translate)
        beam_size (int): 束搜索大小
        vad_filter (bool): 是否使用語音活動檢測過濾
        vad_parameters (dict): VAD 參數設置
        word_timestamps (bool): 是否生成詞級時間戳
        output_dir (str): 輸出目錄，None 表示與音檔文件相同目錄
        output_format (str): 輸出格式 (txt, srt, vtt, json)
        verbose (bool): 是否顯示詳細進度信息
        show_in_terminal (bool): 是否在終端顯示轉錄結果
        split_segments (bool): 是否將音檔分割為小片段轉錄
        segment_duration (int): 分割片段的時長（秒）
        max_workers (int): 分割音檔時使用的最大工作線程數

    返回:
        str: 轉錄的文本路徑
    """
    if verbose:
        print(f"正在載入模型: {model_size}")
    start_time = time.time()

    # 決定設備
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"

    if verbose:
        print(f"使用設備: {device}")

    # 顯示 GPU 資訊（如果使用）
    if device == "cuda" and verbose:
        gpu_info = check_gpu()
        print(f"檢測到 {gpu_info['device_count']} 個 GPU 設備:")
        for i, gpu in enumerate(gpu_info["devices"]):
            print(f" - GPU {i}: {gpu['name']} ({gpu['max_memory']} 總記憶體)")
            print(
                f"   已分配: {gpu['memory_allocated']}, 已保留: {gpu['memory_reserved']}"
            )

    # 決定計算類型
    if compute_type == "default":
        compute_type = "float16" if device == "cuda" else "int8"

    if verbose:
        print(f"計算類型: {compute_type}")
        print("正在初始化 Whisper 模型...")

    # 初始化模型
    cache_key = (model_size, device, compute_type)
    with _MODEL_CACHE_LOCK:
        model = _LOADED_MODELS.get(cache_key)
        if model is None:
            model = WhisperModel(model_size, device=device, compute_type=compute_type)
            _LOADED_MODELS[cache_key] = model

    model_load_time = time.time() - start_time
    if verbose:
        print(f"模型載入完成，耗時: {model_load_time:.2f} 秒")
        print(f"開始轉錄音檔文件: {audio_path}")

    # 設置 VAD 參數
    if vad_filter and vad_parameters is None:
        vad_parameters = {
            "threshold": 0.5,
            "min_speech_duration_ms": 250,
            "min_silence_duration_ms": 2000,
            "speech_pad_ms": 400,
        }

    # 決定輸出路徑
    audio_path_obj = Path(audio_path)
    base_output_path = Path(output_dir) if output_dir else audio_path_obj.parent
    base_filename = audio_path_obj.stem

    # 創建輸出目錄（如果不存在）
    base_output_path.mkdir(parents=True, exist_ok=True)

    # 初始化輸出內容
    transcript_parts = []
    srt_content = ""
    vtt_content = "WEBVTT\n\n"
    segments_json = []
    words_data = []

    # 用於儲存最終輸出文件路徑
    output_files = {}

    detected_language = None
    language_probability = None

    if split_segments:
        if verbose:
            print(f"分割音檔為每 {segment_duration} 秒的片段...")

        segment_files, temp_dir = split_audio(
            audio_path,
            segment_duration=segment_duration,
            output_dir=None,
            verbose=verbose,
            max_workers=max_workers,
        )

        if verbose:
            print(f"共分割為 {len(segment_files)} 個片段")

        segments_txt_path = base_output_path / f"{base_filename}_segments.txt"
        with open(segments_txt_path, "w", encoding="utf-8") as segments_file:
            total_segs = len(segment_files)
            for i, segment_file in enumerate(segment_files):
                if verbose:
                    print(f"正在轉錄片段 {i + 1}/{total_segs}: {segment_file}")

                if status_callback:
                    seg_progress = 30.0 + (i / total_segs) * 65.0
                    status_callback(
                        f"正在轉錄片段 {i + 1}/{total_segs}",
                        progress=seg_progress,
                    )

                transcription_start = time.time()
                segments, info = model.transcribe(
                    segment_file,
                    language=language,
                    task=task,
                    beam_size=beam_size,
                    vad_filter=vad_filter,
                    vad_parameters=vad_parameters,
                    word_timestamps=word_timestamps,
                )

                if info:
                    detected_language = detected_language or getattr(
                        info, "language", None
                    )
                    language_probability = language_probability or getattr(
                        info, "language_probability", None
                    )

                segment_segments = list(segments)
                segment_texts = []
                segment_start = None
                segment_end = None

                for seg in segment_segments:
                    segment_text = (seg.text or "").strip()
                    if segment_text:
                        transcript_parts.append(segment_text)
                        segment_texts.append(segment_text)

                    absolute_start = float(
                        i * segment_duration + (getattr(seg, "start", 0.0) or 0.0)
                    )
                    absolute_end = float(
                        i * segment_duration + (getattr(seg, "end", 0.0) or 0.0)
                    )

                    segment_start = (
                        absolute_start
                        if segment_start is None
                        else min(segment_start, absolute_start)
                    )
                    segment_end = (
                        absolute_end
                        if segment_end is None
                        else max(segment_end, absolute_end)
                    )

                    segment_index = len(segments_json)
                    segment_number = segment_index + 1

                    start_time_srt = format_timestamp(absolute_start, format="srt")
                    end_time_srt = format_timestamp(absolute_end, format="srt")
                    srt_content += f"{segment_number}\n{start_time_srt} --> {end_time_srt}\n{segment_text}\n\n"

                    start_time_vtt = format_timestamp(absolute_start, format="vtt")
                    end_time_vtt = format_timestamp(absolute_end, format="vtt")
                    vtt_content += (
                        f"{start_time_vtt} --> {end_time_vtt}\n{segment_text}\n\n"
                    )

                    if show_in_terminal and segment_text:
                        print(
                            f"[{absolute_start:.2f}s -> {absolute_end:.2f}s] {segment_text}"
                        )

                    words_payload = []
                    if hasattr(seg, "words") and seg.words:
                        for word in seg.words:
                            absolute_word_start = float(
                                i * segment_duration
                                + (getattr(word, "start", 0.0) or 0.0)
                            )
                            absolute_word_end = float(
                                i * segment_duration
                                + (getattr(word, "end", 0.0) or 0.0)
                            )
                            word_payload = {
                                "word": word.word,
                                "start": absolute_word_start,
                                "end": absolute_word_end,
                                "probability": getattr(word, "probability", None),
                            }
                            words_payload.append(word_payload)
                            words_data.append(word_payload)

                    segments_json.append(
                        {
                            "id": segment_index,
                            "start": absolute_start,
                            "end": absolute_end,
                            "text": segment_text,
                            "confidence": getattr(seg, "avg_logprob", None),
                            "words": words_payload,
                        }
                    )

                if segment_texts:
                    start_label = format_timestamp(segment_start or 0.0, format="srt")
                    end_label = format_timestamp(segment_end or 0.0, format="srt")
                    segments_file.write(
                        f"片段 {i + 1} [{start_label} - {end_label}]:\n"
                    )
                    segments_file.write(" ".join(segment_texts) + "\n\n")

                if verbose:
                    print(
                        f"片段 {i + 1} 轉錄完成，耗時: {time.time() - transcription_start:.2f} 秒"
                    )

                if status_callback:
                    seg_progress = 30.0 + ((i + 1) / total_segs) * 65.0
                    status_callback(
                        f"片段 {i + 1}/{total_segs} 轉錄完成",
                        progress=seg_progress,
                    )

        if temp_dir:
            import shutil

            shutil.rmtree(temp_dir)

        output_files["segments_txt"] = str(segments_txt_path)
    else:
        transcription_start = time.time()

        segments, info = model.transcribe(
            audio_path,
            language=language,
            task=task,
            beam_size=beam_size,
            vad_filter=vad_filter,
            vad_parameters=vad_parameters,
            word_timestamps=word_timestamps,
        )

        if verbose:
            print(f"轉錄處理完成！共耗時: {time.time() - transcription_start:.2f} 秒")
            if info:
                print(
                    f"檢測到的語言: {info.language} (機率: {info.language_probability:.2f})"
                )

        if info:
            detected_language = getattr(info, "language", None)
            language_probability = getattr(info, "language_probability", None)

        if show_in_terminal and verbose:
            print("\n" + "=" * 50)
            print("轉錄結果:")
            print("=" * 50 + "\n")

        for seg in list(segments):
            segment_text = (seg.text or "").strip()
            if segment_text:
                transcript_parts.append(segment_text)

            start_time = float(getattr(seg, "start", 0.0) or 0.0)
            end_time = float(getattr(seg, "end", 0.0) or 0.0)
            segment_index = len(segments_json)
            segment_number = segment_index + 1

            start_time_srt = format_timestamp(start_time, format="srt")
            end_time_srt = format_timestamp(end_time, format="srt")
            srt_content += f"{segment_number}\n{start_time_srt} --> {end_time_srt}\n{segment_text}\n\n"

            start_time_vtt = format_timestamp(start_time, format="vtt")
            end_time_vtt = format_timestamp(end_time, format="vtt")
            vtt_content += f"{start_time_vtt} --> {end_time_vtt}\n{segment_text}\n\n"

            if show_in_terminal and segment_text:
                print(f"[{start_time:.2f}s -> {end_time:.2f}s] {segment_text}")

            words_payload = []
            if hasattr(seg, "words") and seg.words:
                for word in seg.words:
                    word_start = float(getattr(word, "start", 0.0) or 0.0)
                    word_end = float(getattr(word, "end", 0.0) or 0.0)
                    word_payload = {
                        "word": word.word,
                        "start": word_start,
                        "end": word_end,
                        "probability": getattr(word, "probability", None),
                    }
                    words_payload.append(word_payload)
                    words_data.append(word_payload)

            segments_json.append(
                {
                    "id": segment_index,
                    "start": start_time,
                    "end": end_time,
                    "text": segment_text,
                    "confidence": getattr(seg, "avg_logprob", None),
                    "words": words_payload,
                }
            )

    # 寫入標準輸出文件

    # 純文本輸出
    txt_path = base_output_path / f"{base_filename}.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(transcript_parts))
    output_files["txt"] = str(txt_path)

    # 根據請求的格式輸出其他格式
    if output_format == "srt" or output_format == "all":
        srt_path = base_output_path / f"{base_filename}.srt"
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)
        output_files["srt"] = str(srt_path)

    if output_format == "vtt" or output_format == "all":
        vtt_path = base_output_path / f"{base_filename}.vtt"
        with open(vtt_path, "w", encoding="utf-8") as f:
            f.write(vtt_content)
        output_files["vtt"] = str(vtt_path)

    import json

    full_transcript = "\n".join(transcript_parts)
    json_data = {
        "text": full_transcript,
        "segments": segments_json,
        "language": detected_language,
        "language_probability": language_probability,
        "words": words_data if words_data else None,
    }

    json_path = base_output_path / f"{base_filename}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    output_files["json"] = str(json_path)

    # 如果需要在終端顯示完整結果但不是實時顯示片段
    if show_in_terminal and verbose and len(segments_json) == 0 and full_transcript:
        print("\n" + "=" * 50)
        print("轉錄結果:")
        print("=" * 50)
        print(full_transcript)
        print("=" * 50 + "\n")

    maybe_prepare_video_output(
        audio_path,
        base_output_path,
        base_filename,
        output_files,
        verbose=verbose,
        status_callback=status_callback,
        expose_mp4_key=True,
    )

    if verbose:
        print(f"\n轉錄結果已保存至: {output_files}")

    return output_files


def format_timestamp(seconds, format="srt"):
    return shared_format_timestamp(seconds, format=format)


def download_from_url(
    url,
    output_dir=None,
    download_format="audio",
    verbose=True,
    cookies=None,
    video_quality="best",
):
    return shared_download_from_url(
        url,
        output_dir=output_dir,
        download_format=download_format,
        verbose=verbose,
        cookies=cookies,
        video_quality=video_quality,
    )


def main():
    parser = argparse.ArgumentParser(
        description="使用 Faster Whisper 轉錄音檔文件或從 URL 下載後轉錄"
    )

    # 定義互斥組，用戶要麼提供音檔文件，要麼提供 URL
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--audio", type=str, help="要轉錄的音檔文件路徑")
    input_group.add_argument("--url", type=str, help="要下載並轉錄的網路視頻/音檔 URL")

    # URL 下載相關參數
    parser.add_argument(
        "--download_format",
        type=str,
        default="both",
        choices=["audio", "video", "both"],
        help="下載格式 (默認: both，即下載影片並提取音檔進行轉錄)",
    )
    parser.add_argument(
        "--cookies", type=str, default=None, help="Cookie 文件路徑，用於需要登錄的網站"
    )
    parser.add_argument(
        "--keep_video",
        action="store_true",
        help="保留下載的視頻文件（僅在下載格式為video時有效）",
    )
    parser.add_argument(
        "--keep_audio",
        action="store_true",
        help="轉錄完成後保留提取的音檔文件（默認會在轉錄後刪除）",
    )
    parser.add_argument(
        "--download_only", action="store_true", help="只下載影片或音檔，不進行轉錄"
    )
    parser.add_argument(
        "--video_quality",
        type=str,
        default="best",
        choices=["best", "1080p", "720p", "480p", "360p"],
        help="影片下載品質 (默認: best 最高品質)",
    )

    # 現有的轉錄參數
    parser.add_argument(
        "--model",
        type=str,
        default="asadfgglie/faster-whisper-large-v3-zh-TW",
        choices=[
            "tiny",
            "base",
            "small",
            "medium",
            "large-v1",
            "large-v2",
            "large-v3",
            "asadfgglie/faster-whisper-large-v3-zh-TW",
        ],
        help="Whisper 模型大小",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        choices=["auto", "cpu", "cuda"],
        help="運行設備 (默認: auto)",
    )
    parser.add_argument(
        "--compute_type",
        type=str,
        default="default",
        choices=["default", "float16", "int8", "int8_float16"],
        help="計算類型 (默認: 在 GPU 上為 float16，在 CPU 上為 int8)",
    )
    parser.add_argument(
        "--language",
        type=str,
        default=None,
        help="語言代碼 (如 'zh', 'en')，不指定則自動檢測",
    )
    parser.add_argument(
        "--task",
        type=str,
        default="transcribe",
        choices=["transcribe", "translate"],
        help="任務類型 (默認: transcribe)",
    )
    parser.add_argument("--beam_size", type=int, default=5, help="束搜索大小 (默認: 5)")
    parser.add_argument("--no_vad", action="store_true", help="禁用語音活動檢測過濾")
    parser.add_argument(
        "--no_word_timestamps", action="store_true", help="禁用詞級時間戳生成"
    )
    parser.add_argument(
        "--output_dir", type=str, default=None, help="輸出目錄 (默認與音檔文件相同目錄)"
    )
    parser.add_argument(
        "--output_format",
        type=str,
        default="srt",
        choices=["txt", "srt", "vtt", "json", "all"],
        help="輸出格式 (默認: srt)",
    )
    parser.add_argument("--quiet", action="store_true", help="不顯示詳細進度信息")
    parser.add_argument(
        "--show_in_terminal", action="store_true", help="在終端顯示轉錄結果"
    )
    parser.add_argument(
        "--split", action="store_true", help="將音檔分割為小片段進行轉錄"
    )
    parser.add_argument(
        "--segment_duration",
        type=int,
        default=30,
        help="分割片段的時長（秒）(默認: 30)",
    )
    parser.add_argument(
        "--max_workers",
        type=int,
        default=None,
        help="音檔分割時使用的最大工作線程數 (默認: 自動決定)",
    )

    args = parser.parse_args()

    # 處理命令行參數
    audio_path = args.audio
    final_output_dir = args.output_dir

    # 如果提供了 URL，先下載
    if args.url:
        if not args.quiet:
            print(f"從 URL 下載: {args.url}")

        # 處理 "both" 下載格式，強制使用 video 下載
        actual_download_format = (
            "video" if args.download_format == "both" else args.download_format
        )

        # 下載文件
        downloaded_file, folder_path = download_from_url(
            url=args.url,
            output_dir=args.output_dir,
            download_format=actual_download_format,
            verbose=not args.quiet,
            cookies=args.cookies,
            video_quality=args.video_quality,
        )

        if not downloaded_file:
            # 嘗試在可能的位置尋找檔案，而不是直接失敗
            possible_title = (
                args.url.split("=")[-1] if "=" in args.url else args.url.split("/")[-1]
            )
            safe_title = "".join(
                [
                    c if c.isalnum() or c in [" ", "-", "_"] else "_"
                    for c in possible_title
                ]
            )

            # 確定搜索目錄
            search_path = Path(args.output_dir) if args.output_dir else Path.cwd()

            # 搜索可能的檔案
            if not args.quiet:
                print(f"下載失敗，尋找可能的已存在檔案...")

            # 搜索所有子資料夾
            potential_files = []
            for ext in [".mp4", ".mkv", ".webm", ".flac", ".mp3"]:
                potential_files.extend(list(search_path.glob(f"**/*{ext}")))

            # 如果找到檔案，使用最新的一個
            if potential_files:
                downloaded_file = str(sorted(potential_files, key=os.path.getmtime)[-1])
                folder_path = Path(downloaded_file).parent
                if not args.quiet:
                    print(f"使用已存在的檔案: {downloaded_file}")
            else:
                print("無法找到任何可用檔案")
                return

        # 使用下載檔案的專屬資料夾作為輸出目錄
        final_output_dir = str(folder_path)

        # 如果用戶只想下載而不轉錄，在這裡直接返回
        if args.download_only:
            if not args.quiet:
                print(f"\n只下載完成！文件保存在: {downloaded_file}")
            return downloaded_file

        # 如果下載的是視頻，需要提取音檔用於轉錄
        if actual_download_format == "video":
            if not args.quiet:
                print("從視頻中提取音檔...")

            # 保存原始視頻路徑
            video_path = downloaded_file

            # 提取音檔到同一資料夾
            audio_path = str(
                Path(folder_path) / f"{Path(downloaded_file).stem}.extracted_audio.flac"
            )

            # 使用 ffmpeg 提取音檔（比 pydub 更有效率且支援更多格式）
            try:
                ffmpeg_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    video_path,
                    "-vn",
                    "-c:a",
                    "flac",
                    audio_path,
                ]
                # 使用相同的錯誤處理方式
                result = subprocess.run(ffmpeg_cmd, capture_output=True)
                # 檢查返回碼
                if result.returncode != 0:
                    error_output = result.stderr.decode("utf-8", errors="replace")
                    print(f"提取音檔時出錯: 返回碼 {result.returncode}")
                    print(f"錯誤輸出: {error_output}")
                    return
                if not args.quiet:
                    print(f"音檔已提取至: {audio_path}")
            except Exception as e:
                print(f"提取音檔時出錯: {e}")
                return
        else:
            # 如果是直接下載音檔，則音檔路徑就是下載的文件
            audio_path = downloaded_file

    # 執行轉錄
    transcription_results = transcribe_audio(
        audio_path=audio_path,
        model_size=args.model,
        device=args.device,
        compute_type=args.compute_type,
        language=args.language,
        task=args.task,
        beam_size=args.beam_size,
        vad_filter=not args.no_vad,
        word_timestamps=not args.no_word_timestamps,
        output_dir=final_output_dir,
        output_format=args.output_format,
        verbose=not args.quiet,
        show_in_terminal=args.show_in_terminal,
        split_segments=args.split,
        segment_duration=args.segment_duration,
        max_workers=args.max_workers,
    )

    # 轉錄完成後，處理檔案保留/刪除邏輯
    if args.url:
        # 只有在不是原始音檔檔案的情況下才需要處理刪除
        if args.download_format in ["video", "both"] and not args.download_only:
            # 默認刪除提取的音檔檔案，除非指定保留
            if not args.keep_audio and not args.download_only:
                try:
                    os.remove(audio_path)
                    if not args.quiet:
                        print(f"已刪除音檔文件: {audio_path}")
                except Exception as e:
                    print(f"刪除音檔文件時出錯: {e}")

            # 默認刪除視頻檔案，除非指定保留
            if not args.keep_video and args.download_format == "both":
                try:
                    video_path = downloaded_file
                    os.remove(video_path)
                    if not args.quiet:
                        print(f"已刪除視頻文件: {video_path}")
                except Exception as e:
                    print(f"刪除視頻文件時出錯: {e}")

    # 顯示完成信息
    if not args.quiet:
        print("\n轉錄處理完成！")
        if transcription_results:
            print(f"輸出文件: {transcription_results}")

    return transcription_results


if __name__ == "__main__":
    main()
