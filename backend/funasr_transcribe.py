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
from funasr import AutoModel
from pydub import AudioSegment
import yt_dlp
import multiprocessing as mp
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# 嘗試導入 opencc 用於簡體→繁體轉換
try:
    from opencc import OpenCC

    _S2TW_CONVERTER = OpenCC("s2twp")
    OPENCC_AVAILABLE = True
except ImportError:
    _S2TW_CONVERTER = None
    OPENCC_AVAILABLE = False

# 嘗試導入 tqdm 用於顯示進度條，但如果不可用也能繼續執行
try:
    from tqdm import tqdm

    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

# ============================================================
# FunASR model name mapping
# ============================================================
_FUNASR_MODEL_MAP = {
    # Paraformer (Chinese, best accuracy)
    "paraformer-zh": "paraformer-zh",
    "paraformer": "paraformer-zh",
    # SenseVoice (multilingual + emotion)
    "sensevoice": "iic/SenseVoiceSmall",
    "SenseVoiceSmall": "iic/SenseVoiceSmall",
    "iic/SenseVoiceSmall": "iic/SenseVoiceSmall",
    # Whisper wrappers inside FunASR
    "large-v3": "Whisper-large-v3",
    "whisper-large-v3": "Whisper-large-v3",
    "Whisper-large-v3": "Whisper-large-v3",
    "large-v3-turbo": "Whisper-large-v3-turbo",
    "whisper-large-v3-turbo": "Whisper-large-v3-turbo",
    "Whisper-large-v3-turbo": "Whisper-large-v3-turbo",
    # Fun-ASR-Nano
    "fun-asr-nano": "FunAudioLLM/Fun-ASR-Nano-2512",
    "nano": "FunAudioLLM/Fun-ASR-Nano-2512",
    "FunAudioLLM/Fun-ASR-Nano-2512": "FunAudioLLM/Fun-ASR-Nano-2512",
    # Legacy faster-whisper model names → map to FunASR Whisper wrapper
    "tiny": "Whisper-large-v3",
    "base": "Whisper-large-v3",
    "small": "Whisper-large-v3",
    "medium": "Whisper-large-v3",
    "large-v1": "Whisper-large-v3",
    "large-v2": "Whisper-large-v3",
    "asadfgglie/faster-whisper-large-v3-zh-TW": "paraformer-zh",
}

_WHISPER_MODELS = {
    "Whisper-large-v3",
    "Whisper-large-v3-turbo",
}

_SENSEVOICE_MODELS = {
    "iic/SenseVoiceSmall",
}


def _resolve_model_name(model_size: str) -> str:
    """Map a user-facing model_size string to a FunASR model identifier."""
    return _FUNASR_MODEL_MAP.get(model_size, model_size)


def _is_whisper_model(model_name: str) -> bool:
    return model_name in _WHISPER_MODELS


def _is_sensevoice_model(model_name: str) -> bool:
    return model_name in _SENSEVOICE_MODELS


def check_gpu():
    """
    檢查 GPU 狀態並返回詳細資訊
    """
    gpu_info = {
        "available": torch.cuda.is_available(),
        "device_count": torch.cuda.device_count(),
        "devices": [],
    }

    if gpu_info["available"]:
        for i in range(gpu_info["device_count"]):
            gpu_info["devices"].append(
                {
                    "name": torch.cuda.get_device_name(i),
                    "memory_allocated": f"{torch.cuda.memory_allocated(i) / 1024**2:.2f} MB",
                    "memory_reserved": f"{torch.cuda.memory_reserved(i) / 1024**2:.2f} MB",
                    "max_memory": f"{torch.cuda.get_device_properties(i).total_memory / 1024**3:.2f} GB",
                }
            )

    return gpu_info


def split_audio(
    audio_path, segment_duration=30, output_dir=None, verbose=True, max_workers=None
):
    """
    將音檔分割為指定時長的片段，使用多線程加速處理

    參數:
        audio_path (str): 音檔文件路徑
        segment_duration (int): 每個片段的時長（秒）
        output_dir (str): 輸出目錄，None 表示使用臨時目錄
        verbose (bool): 是否顯示詳細進度信息
        max_workers (int): 最大工作線程數，None表示自動設定

    返回:
        list: 分割後的音檔片段文件路徑列表
    """
    # 創建臨時目錄或使用指定目錄
    if output_dir is None:
        temp_dir = tempfile.mkdtemp()
        output_dir = temp_dir
    else:
        temp_dir = None
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    segment_files = []

    # 使用 ffmpeg 獲取音檔總長度（秒）
    duration_cmd = ["ffmpeg", "-i", audio_path, "-hide_banner"]
    try:
        # 不使用 text=True，而是手動處理 bytes 輸出
        result = subprocess.run(duration_cmd, capture_output=True)
        # 使用 utf-8 編碼嘗試解碼輸出，忽略無法解碼的部分
        output = result.stderr.decode("utf-8", errors="replace")

        # 解析總時長
        duration_match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d+)", output)
        if duration_match:
            h, m, s = duration_match.groups()
            total_duration = int(h) * 3600 + int(m) * 60 + float(s)
        else:
            # 如果無法解析時長，嘗試用 pydub 獲取
            try:
                audio = AudioSegment.from_file(audio_path)
                total_duration = len(audio) / 1000.0  # 毫秒轉秒
            except Exception as e:
                print(f"無法獲取音檔時長 (pydub): {e}")
                # 估算一個值，假設檔案每 MB 對應約 1 分鐘的音檔
                file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
                total_duration = file_size_mb * 60
    except Exception as e:
        print(f"無法獲取音檔時長 (ffmpeg): {e}")
        # 嘗試用 pydub 獲取
        try:
            audio = AudioSegment.from_file(audio_path)
            total_duration = len(audio) / 1000.0  # 毫秒轉秒
        except Exception as e2:
            print(f"使用 pydub 獲取時長也失敗: {e2}")
            # 估算一個值
            file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
            total_duration = file_size_mb * 60

    # 計算需要分割的段數
    num_segments = int(total_duration / segment_duration) + 1

    if verbose:
        print(
            f"音檔總長度: {int(total_duration / 3600):02d}:{int((total_duration % 3600) / 60):02d}:{int(total_duration % 60):02d}"
        )
        print(f"預計將分割為 {num_segments} 個片段")
        print(f"使用多線程加速分割處理...")

    # 定義單個分割任務
    def split_segment(i):
        start_time = i * segment_duration
        if start_time >= total_duration:
            return None

        segment_filename = os.path.join(output_dir, f"segment_{i:03d}.flac")

        # 優化ffmpeg命令提高效率
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(start_time),  # 放在輸入前提高定位速度
            "-i",
            audio_path,
            "-t",
            str(segment_duration),
            "-vn",
            "-c:a",
            "flac",
            "-threads",
            "2",  # 限制每個任務的線程數
            segment_filename,
        ]

        try:
            result = subprocess.run(ffmpeg_cmd, capture_output=True)
            if result.returncode != 0:
                error_message = result.stderr.decode("utf-8", errors="replace")
                print(f"分割音檔段 {i} 時出錯: 返回碼 {result.returncode}")
                print(f"錯誤輸出: {error_message}")
                return None
            return segment_filename
        except Exception as e:
            print(f"分割音檔段 {i} 時出錯: {e}")
            return None

    # 決定使用的最大線程數
    if max_workers is None:
        max_workers = min(mp.cpu_count(), 4)  # 預設最多使用4個核心避免過載

    # 使用線程池並行處理分割任務
    successful_segments = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任務
        futures = {executor.submit(split_segment, i): i for i in range(num_segments)}

        # 使用tqdm顯示進度條
        if verbose and TQDM_AVAILABLE:
            pbar = tqdm(total=num_segments, desc="分割進度")
        elif verbose:
            print(f"開始分割處理 {num_segments} 個片段...")

        # 處理完成的任務
        completed_count = 0
        for future in as_completed(futures):
            segment_file = future.result()
            if segment_file:
                successful_segments.append(segment_file)
            if verbose:
                completed_count += 1
                if TQDM_AVAILABLE:
                    pbar.update(1)
                elif completed_count % 10 == 0 or completed_count == num_segments:
                    percent_complete = min(
                        100, round((completed_count / num_segments) * 100)
                    )
                    print(
                        f"分割進度: {percent_complete}% ({completed_count}/{num_segments})"
                    )

        if verbose and TQDM_AVAILABLE:
            pbar.close()

    # 排序片段文件以確保順序正確
    segment_files = sorted(successful_segments)

    if verbose:
        print(f"分割完成! 共生成 {len(segment_files)} 個片段。")

    return segment_files, temp_dir


_MODEL_CACHE_LOCK = threading.Lock()
_LOADED_MODELS = {}


def _build_funasr_model(model_name: str, device: str):
    """Instantiate the correct FunASR AutoModel with appropriate sub-models."""

    if _is_whisper_model(model_name):
        # FunASR Whisper wrapper — no punc_model
        return AutoModel(
            model=model_name,
            vad_model="fsmn-vad",
            vad_kwargs={"max_single_segment_time": 30000},
            device=device,
        )
    elif _is_sensevoice_model(model_name):
        # SenseVoice — no punc_model
        return AutoModel(
            model=model_name,
            vad_model="fsmn-vad",
            vad_kwargs={"max_single_segment_time": 30000},
            device=device,
        )
    else:
        # Paraformer and other models — with punc_model for sentence splitting
        # max_single_segment_time=15000 (15s) keeps VAD chunks short;
        # ct-punc + sentence_timestamp=True further splits at punctuation → ~1-5s segments
        return AutoModel(
            model=model_name,
            vad_model="fsmn-vad",
            punc_model="ct-punc",
            vad_kwargs={"max_single_segment_time": 15000},
            device=device,
        )


def _run_funasr_generate(
    model,
    model_name: str,
    audio_input: str,
    language=None,
    task="transcribe",
    beam_size=5,
    word_timestamps=True,
):
    """Call model.generate() with the correct kwargs for each model type."""

    if _is_whisper_model(model_name):
        decoding_options = {
            "task": task,
            "language": language,
            "beam_size": beam_size,
            "fp16": True,
            "without_timestamps": not word_timestamps,
        }
        return model.generate(
            input=audio_input,
            cache={},
            batch_size_s=0,
            DecodingOptions=decoding_options,
        )
    elif _is_sensevoice_model(model_name):
        return model.generate(
            input=audio_input,
            cache={},
            language="auto" if language is None else language,
            use_itn=True,
            batch_size_s=60,
            merge_vad=True,
            merge_length_s=15,
            output_timestamp=word_timestamps,
        )
    else:
        # Paraformer and similar
        return model.generate(
            input=audio_input,
            cache={},
            batch_size_s=300,
            pred_timestamp=word_timestamps,
            sentence_timestamp=True,
            return_raw_text=True,
        )


def _clean_sensevoice_text(text: str) -> str:
    """Remove SenseVoice special tags like <|zh|><|NEUTRAL|><|Speech|><|woitn|> from text."""
    from funasr.utils.postprocess_utils import rich_transcription_postprocess

    return rich_transcription_postprocess(text)


def _convert_to_traditional(text: str) -> str:
    """將簡體中文轉換為臺灣繁體中文（含詞彙轉換）。若 opencc 不可用則原樣返回。"""
    if OPENCC_AVAILABLE and _S2TW_CONVERTER is not None:
        return _S2TW_CONVERTER.convert(text)
    return text


# 字幕中需要移除的標點符號（中英文）
_SUBTITLE_PUNCTUATION = re.compile(
    r"[，。？、！；：\u201c\u201d\u2018\u2019（）【】《》…—,\.!\?;:\"\'()\[\]{}<>\-]"
)


def _strip_punctuation(text: str) -> str:
    """移除字幕文字中的標點符號。"""
    return _SUBTITLE_PUNCTUATION.sub("", text).strip()


def _split_long_segments(segments_json, words_data, max_duration: float = 15.0):
    """
    Post-process: split any segment longer than *max_duration* seconds
    at the nearest word boundary close to the midpoint.
    This guarantees no subtitle block exceeds the threshold.
    """
    new_segments = []
    new_words = []

    for seg in segments_json:
        seg_dur = seg["end"] - seg["start"]
        seg_words = seg.get("words", [])

        if seg_dur <= max_duration or len(seg_words) < 2:
            seg["id"] = len(new_segments)
            new_segments.append(seg)
            new_words.extend(seg_words)
            continue

        # Split at the word boundary closest to the midpoint
        mid_time = seg["start"] + seg_dur / 2.0
        best_idx = 0
        best_dist = float("inf")
        for i in range(1, len(seg_words)):
            dist = abs(seg_words[i]["start"] - mid_time)
            if dist < best_dist:
                best_dist = dist
                best_idx = i

        left_words = seg_words[:best_idx]
        right_words = seg_words[best_idx:]

        left_text = "".join(w["word"] for w in left_words)
        right_text = "".join(w["word"] for w in right_words)

        left_start = seg["start"]
        left_end = left_words[-1]["end"] if left_words else mid_time
        right_start = right_words[0]["start"] if right_words else mid_time
        right_end = seg["end"]

        left_seg = {
            "id": len(new_segments),
            "start": left_start,
            "end": left_end,
            "text": left_text,
            "confidence": seg.get("confidence"),
            "words": left_words,
        }
        new_segments.append(left_seg)
        new_words.extend(left_words)

        right_seg = {
            "id": len(new_segments),
            "start": right_start,
            "end": right_end,
            "text": right_text,
            "confidence": seg.get("confidence"),
            "words": right_words,
        }
        new_segments.append(right_seg)
        new_words.extend(right_words)

    # Recursively split if any segment is still too long
    still_long = any(
        (s["end"] - s["start"]) > max_duration and len(s.get("words", [])) >= 2
        for s in new_segments
    )
    if still_long:
        return _split_long_segments(new_segments, new_words, max_duration)

    return new_segments, new_words


def _parse_funasr_result(res, model_name: str, time_offset: float = 0.0):
    """
    Parse FunASR output into the standard segments/words structure.

    Returns:
        (segments_json, words_data, full_text, detected_language)
    """
    segments_json = []
    words_data = []
    transcript_parts = []
    detected_language = None

    if not res or len(res) == 0:
        return segments_json, words_data, "", detected_language

    for result_item in res:
        raw_text = result_item.get("text", "")

        # SenseVoice: clean special tags
        if _is_sensevoice_model(model_name):
            # Try to detect language from tags
            lang_match = re.search(r"<\|(\w+)\|>", raw_text)
            if lang_match:
                detected_language = detected_language or lang_match.group(1)
            raw_text = _clean_sensevoice_text(raw_text)

        # Check for sentence_info (Paraformer with punc_model)
        sentence_info = result_item.get("sentence_info", None)

        if sentence_info:
            # Each sentence_info entry becomes a segment
            for sent in sentence_info:
                sent_text = (sent.get("text", "") or "").strip()
                if not sent_text:
                    continue

                # Timestamps in milliseconds → convert to seconds
                seg_start = float(sent.get("start", 0)) / 1000.0 + time_offset
                seg_end = float(sent.get("end", 0)) / 1000.0 + time_offset

                segment_index = len(segments_json)
                transcript_parts.append(sent_text)

                # Character-level timestamps from sentence_info
                words_payload = []
                char_timestamps = sent.get("timestamp", [])
                if char_timestamps:
                    chars = list(sent_text.replace(" ", ""))
                    for idx, ts_pair in enumerate(char_timestamps):
                        if idx < len(chars):
                            w_start = float(ts_pair[0]) / 1000.0 + time_offset
                            w_end = float(ts_pair[1]) / 1000.0 + time_offset
                            word_payload = {
                                "word": chars[idx],
                                "start": w_start,
                                "end": w_end,
                                "probability": None,
                            }
                            words_payload.append(word_payload)
                            words_data.append(word_payload)

                segments_json.append(
                    {
                        "id": segment_index,
                        "start": seg_start,
                        "end": seg_end,
                        "text": sent_text,
                        "confidence": None,
                        "words": words_payload,
                    }
                )
        else:
            # Flat result — single segment with character-level timestamps
            text = (raw_text or "").strip()
            if not text:
                continue

            transcript_parts.append(text)

            # Get character-level timestamps
            char_timestamps = result_item.get("timestamp", [])
            seg_start = 0.0 + time_offset
            seg_end = 0.0 + time_offset
            if char_timestamps and len(char_timestamps) > 0:
                seg_start = float(char_timestamps[0][0]) / 1000.0 + time_offset
                seg_end = float(char_timestamps[-1][1]) / 1000.0 + time_offset

            segment_index = len(segments_json)

            words_payload = []
            if char_timestamps:
                chars = list(text.replace(" ", ""))
                for idx, ts_pair in enumerate(char_timestamps):
                    if idx < len(chars):
                        w_start = float(ts_pair[0]) / 1000.0 + time_offset
                        w_end = float(ts_pair[1]) / 1000.0 + time_offset
                        word_payload = {
                            "word": chars[idx],
                            "start": w_start,
                            "end": w_end,
                            "probability": None,
                        }
                        words_payload.append(word_payload)
                        words_data.append(word_payload)

            segments_json.append(
                {
                    "id": segment_index,
                    "start": seg_start,
                    "end": seg_end,
                    "text": text,
                    "confidence": None,
                    "words": words_payload,
                }
            )

    # ---- Post-processing: split overly long segments ----
    segments_json, words_data = _split_long_segments(
        segments_json, words_data, max_duration=15.0
    )

    # ---- Post-processing: Simplified → Traditional Chinese (Taiwan) ----
    for seg in segments_json:
        seg["text"] = _convert_to_traditional(seg["text"])
        for w in seg.get("words", []):
            w["word"] = _convert_to_traditional(w["word"])
    for w in words_data:
        w["word"] = _convert_to_traditional(w["word"])

    # ---- Post-processing: 移除標點符號 ----
    for seg in segments_json:
        seg["text"] = _strip_punctuation(seg["text"])
    transcript_parts = [seg["text"] for seg in segments_json if seg["text"]]

    full_text = (
        "\n".join(transcript_parts)
        if transcript_parts
        else _strip_punctuation(_convert_to_traditional(raw_text.strip()))
    )
    return segments_json, words_data, full_text, detected_language


def transcribe_audio(
    audio_path,
    model_size="paraformer-zh",
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
    使用 FunASR 將音檔轉錄為文本

    參數:
        audio_path (str): 音檔文件的路徑
        model_size (str): 模型名稱 (paraformer-zh, sensevoice, large-v3, large-v3-turbo, nano, etc.)
        device (str): 運行設備 (auto, cpu, cuda)
        compute_type (str): 計算類型 — 保留用於 API 兼容性，FunASR 不使用此參數
        language (str): 語言代碼 (如 'zh', 'en')，None 表示自動檢測
        task (str): 任務類型 (transcribe, translate)
        beam_size (int): 束搜索大小 — 僅用於 Whisper 模型
        vad_filter (bool): 是否使用語音活動檢測過濾 — FunASR 內建 VAD
        vad_parameters (dict): VAD 參數設置 — 保留用於 API 兼容性
        word_timestamps (bool): 是否生成詞級時間戳
        output_dir (str): 輸出目錄，None 表示與音檔文件相同目錄
        output_format (str): 輸出格式 (txt, srt, vtt, json)
        verbose (bool): 是否顯示詳細進度信息
        show_in_terminal (bool): 是否在終端顯示轉錄結果
        split_segments (bool): 是否將音檔分割為小片段轉錄
        segment_duration (int): 分割片段的時長（秒）
        max_workers (int): 分割音檔時使用的最大工作線程數
        status_callback (callable): 狀態回調函數

    返回:
        dict: 輸出文件路徑字典
    """
    # Resolve model name
    model_name = _resolve_model_name(model_size)

    # If translate is requested and model is not Whisper, force Whisper-large-v3
    if task == "translate" and not _is_whisper_model(model_name):
        if verbose:
            print(f"翻譯任務需要 Whisper 模型，從 {model_name} 切換至 Whisper-large-v3")
        model_name = "Whisper-large-v3"

    if verbose:
        print(f"正在載入模型: {model_name} (原始參數: {model_size})")
    start_time = time.time()

    # 決定設備
    if device == "auto":
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
    elif device == "cuda":
        device = "cuda:0"

    if verbose:
        print(f"使用設備: {device}")

    # 顯示 GPU 資訊（如果使用）
    if "cuda" in device and verbose:
        gpu_info = check_gpu()
        print(f"檢測到 {gpu_info['device_count']} 個 GPU 設備:")
        for i, gpu in enumerate(gpu_info["devices"]):
            print(f" - GPU {i}: {gpu['name']} ({gpu['max_memory']} 總記憶體)")
            print(
                f"   已分配: {gpu['memory_allocated']}, 已保留: {gpu['memory_reserved']}"
            )

    if verbose:
        print(f"計算類型: {compute_type} (FunASR 不使用此參數)")
        print("正在初始化 FunASR 模型...")

    # 初始化模型 (with caching)
    cache_key = (model_name, device)
    with _MODEL_CACHE_LOCK:
        model = _LOADED_MODELS.get(cache_key)
        if model is None:
            model = _build_funasr_model(model_name, device)
            _LOADED_MODELS[cache_key] = model

    model_load_time = time.time() - start_time
    if verbose:
        print(f"模型載入完成，耗時: {model_load_time:.2f} 秒")
        print(f"開始轉錄音檔文件: {audio_path}")

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
            for i, segment_file in enumerate(segment_files):
                if verbose:
                    print(f"正在轉錄片段 {i + 1}/{len(segment_files)}: {segment_file}")

                transcription_start = time.time()

                # Run FunASR on this segment
                res = _run_funasr_generate(
                    model,
                    model_name,
                    segment_file,
                    language=language,
                    task=task,
                    beam_size=beam_size,
                    word_timestamps=word_timestamps,
                )

                # Parse results with time offset
                time_offset = float(i * segment_duration)
                seg_segments, seg_words, seg_text, seg_lang = _parse_funasr_result(
                    res,
                    model_name,
                    time_offset=time_offset,
                )

                if seg_lang:
                    detected_language = detected_language or seg_lang

                # Accumulate segments with corrected IDs
                segment_texts = []
                segment_start = None
                segment_end = None

                for seg in seg_segments:
                    seg_text_str = seg["text"]
                    if seg_text_str:
                        transcript_parts.append(seg_text_str)
                        segment_texts.append(seg_text_str)

                    absolute_start = seg["start"]
                    absolute_end = seg["end"]

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

                    # Re-index with global offset
                    segment_index = len(segments_json)
                    segment_number = segment_index + 1
                    seg["id"] = segment_index

                    start_time_srt = format_timestamp(absolute_start, format="srt")
                    end_time_srt = format_timestamp(absolute_end, format="srt")
                    srt_content += f"{segment_number}\n{start_time_srt} --> {end_time_srt}\n{seg_text_str}\n\n"

                    start_time_vtt = format_timestamp(absolute_start, format="vtt")
                    end_time_vtt = format_timestamp(absolute_end, format="vtt")
                    vtt_content += (
                        f"{start_time_vtt} --> {end_time_vtt}\n{seg_text_str}\n\n"
                    )

                    if show_in_terminal and seg_text_str:
                        print(
                            f"[{absolute_start:.2f}s -> {absolute_end:.2f}s] {seg_text_str}"
                        )

                    segments_json.append(seg)
                    words_data.extend(seg.get("words", []))

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

        if temp_dir:
            import shutil

            shutil.rmtree(temp_dir)

        output_files["segments_txt"] = str(segments_txt_path)
    else:
        transcription_start = time.time()

        if status_callback:
            status_callback("正在使用 FunASR 進行轉錄...")

        # Run FunASR
        res = _run_funasr_generate(
            model,
            model_name,
            audio_path,
            language=language,
            task=task,
            beam_size=beam_size,
            word_timestamps=word_timestamps,
        )

        if verbose:
            print(f"轉錄處理完成！共耗時: {time.time() - transcription_start:.2f} 秒")

        # Parse results
        segments_json, words_data, full_text_parsed, det_lang = _parse_funasr_result(
            res,
            model_name,
            time_offset=0.0,
        )

        if det_lang:
            detected_language = det_lang

        # Try to detect language from the model/result if not set
        if detected_language is None and language:
            detected_language = language

        if verbose and detected_language:
            prob_str = (
                f" (機率: {language_probability:.2f})" if language_probability else ""
            )
            print(f"檢測到的語言: {detected_language}{prob_str}")

        if show_in_terminal and verbose:
            print("\n" + "=" * 50)
            print("轉錄結果:")
            print("=" * 50 + "\n")

        # Build transcript_parts and SRT/VTT from parsed segments
        for seg in segments_json:
            segment_text = seg["text"]
            if segment_text:
                transcript_parts.append(segment_text)

            seg_start = seg["start"]
            seg_end = seg["end"]
            segment_number = seg["id"] + 1

            start_time_srt = format_timestamp(seg_start, format="srt")
            end_time_srt = format_timestamp(seg_end, format="srt")
            srt_content += f"{segment_number}\n{start_time_srt} --> {end_time_srt}\n{segment_text}\n\n"

            start_time_vtt = format_timestamp(seg_start, format="vtt")
            end_time_vtt = format_timestamp(seg_end, format="vtt")
            vtt_content += f"{start_time_vtt} --> {end_time_vtt}\n{segment_text}\n\n"

            if show_in_terminal and segment_text:
                print(f"[{seg_start:.2f}s -> {seg_end:.2f}s] {segment_text}")

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

    # 處理原始影片文件（如果存在）
    # 檢查輸入文件是否為影片格式
    video_extensions = {
        ".mp4",
        ".avi",
        ".mov",
        ".mkv",
        ".webm",
        ".flv",
        ".wmv",
        ".m4v",
        ".mpeg",
        ".mpg",
    }
    audio_path_obj = Path(audio_path)
    file_ext = audio_path_obj.suffix.lower()

    if file_ext in video_extensions:
        if verbose:
            print(f"\n檢測到影片文件格式: {file_ext}")

        # 如果不是 MP4，轉換為 MP4（使用 FFmpeg）
        if file_ext != ".mp4":
            try:
                import subprocess

                mp4_filename = f"{base_filename}_converted.mp4"
                mp4_path = base_output_path / mp4_filename

                if status_callback:
                    status_callback(
                        f"正在將 {file_ext} 轉換為 MP4 以確保瀏覽器兼容性..."
                    )
                if verbose:
                    print(f"正在將 {file_ext} 轉換為 MP4 以確保瀏覽器兼容性...")

                # FFmpeg 轉換命令
                # 使用快速預設和恆定質量模式，保留音訊
                cmd = [
                    "ffmpeg",
                    "-i",
                    str(audio_path),
                    "-c:v",
                    "libx264",  # H.264 視訊編碼
                    "-preset",
                    "fast",  # 快速編碼
                    "-crf",
                    "23",  # 恆定質量（18-28，23是平衡點）
                    "-c:a",
                    "aac",  # AAC 音訊編碼
                    "-b:a",
                    "128k",  # 音訊碼率
                    "-movflags",
                    "+faststart",  # 優化網路播放
                    "-y",  # 覆蓋現有文件
                    str(mp4_path),
                ]

                # 執行轉換（隱藏 FFmpeg 輸出）
                result = subprocess.run(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )

                if result.returncode == 0 and mp4_path.exists():
                    output_files["video"] = str(mp4_path)
                    if verbose:
                        file_size_mb = mp4_path.stat().st_size / (1024 * 1024)
                        print(
                            f"✓ 影片已轉換為 MP4: {mp4_path.name} ({file_size_mb:.1f} MB)"
                        )
                else:
                    # 轉換失敗，使用原始文件
                    if verbose:
                        print(f"⚠ 影片轉換失敗，使用原始文件")
                        print(f"FFmpeg 錯誤: {result.stderr[:200]}")
                    output_files["video"] = str(audio_path)

            except Exception as e:
                # 如果轉換失敗（如 FFmpeg 未安裝），使用原始文件
                if verbose:
                    print(f"⚠ 無法轉換影片: {str(e)}")
                    print(f"使用原始影片文件")
                output_files["video"] = str(audio_path)
        else:
            # 已經是 MP4，直接使用
            output_files["video"] = str(audio_path)
            if verbose:
                print(f"✓ 影片已經是 MP4 格式，無需轉換")

    if verbose:
        print(f"\n轉錄結果已保存至: {output_files}")

    return output_files


def format_timestamp(seconds, format="srt"):
    """
    將秒數格式化為 SRT 或 VTT 格式的時間戳
    """
    hours = int(seconds / 3600)
    minutes = int((seconds % 3600) / 60)
    secs = seconds % 60

    if format == "srt":
        return (
            f"{hours:02d}:{minutes:02d}:{int(secs):02d},{int(secs * 1000) % 1000:03d}"
        )
    elif format == "vtt":
        return f"{hours:02d}:{minutes:02d}:{secs:.3f}"
    else:
        return f"{hours:02d}:{minutes:02d}:{secs:.3f}"


def download_from_url(
    url,
    output_dir=None,
    download_format="audio",
    verbose=True,
    cookies=None,
    video_quality="best",
):
    """
    使用 yt-dlp 從 URL 下載視頻或音檔

    參數:
        url (str): 要下載的 URL
        output_dir (str): 輸出目錄，默認為當前目錄
        download_format (str): 下載格式，可以是 "audio" 或 "video"
        verbose (bool): 是否顯示詳細進度信息
        cookies (str): Cookie 文件路徑，用於需要登錄的網站
        video_quality (str): 影片畫質，可選值: "best", "1080p", "720p", "480p", "360p"

    返回:
        tuple: (下載的文件路徑, 檔案資料夾路徑)
    """
    if verbose:
        print(f"正在從 URL 下載: {url}")
        print(f"設定的影片品質: {video_quality}")

    # 設置基本輸出目錄
    if output_dir:
        base_output_path = Path(output_dir)
        base_output_path.mkdir(parents=True, exist_ok=True)
    else:
        base_output_path = Path.cwd()

    # 首先獲取影片資訊以建立資料夾名稱
    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        info = ydl.extract_info(url, download=False)
        video_title = info.get("title", None)
        if video_title:
            # 處理標題中的特殊字符，確保安全的資料夾名稱
            safe_title = "".join(
                [c if c.isalnum() or c in [" ", "-", "_"] else "_" for c in video_title]
            )
            safe_title = safe_title[:50]  # 限制長度
        else:
            # 如果無法獲取標題，使用時間戳
            safe_title = f"download_{int(time.time())}"

    # 創建專屬資料夾
    folder_path = base_output_path / safe_title
    folder_path.mkdir(exist_ok=True)

    if verbose:
        print(f"為該下載項目創建資料夾: {folder_path}")

    # 設定 yt-dlp 選項
    ydl_opts = {
        "quiet": not verbose,
        "no_warnings": not verbose,
        "paths": {"home": str(folder_path)},
        "outtmpl": {"default": "%(title)s.%(ext)s"},
        "windowsfilenames": True,  # 讓文件名在 Windows 上有效
        "restrictfilenames": True,  # 避免使用特殊字符
        "keepvideo": True,  # 保留原始視頻文件，防止被自動刪除
    }

    # 根據下載格式設定不同的選項
    if download_format == "audio":
        ydl_opts.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "flac",  # 統一使用 FLAC 格式
                        "preferredquality": "192",
                    }
                ],
                "keepfiles": True,  # 保留中間檔案，確保音訊檔案生成成功
            }
        )
    else:  # video
        # 根據所選畫質設定格式
        if video_quality == "best":
            format_str = "bestvideo+bestaudio/best"
        elif video_quality == "1080p":
            format_str = "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
        elif video_quality == "720p":
            format_str = "bestvideo[height<=720]+bestaudio/best[height<=720]"
        elif video_quality == "480p":
            format_str = "bestvideo[height<=480]+bestaudio/best[height<=480]"
        elif video_quality == "360p":
            format_str = "bestvideo[height<=360]+bestaudio/best[height<=360]"
        else:
            format_str = "best"  # 預設使用最佳品質

        ydl_opts.update(
            {
                "format": format_str,
                "merge_output_format": "mp4",  # 設置合併後的輸出格式為 mp4
            }
        )

    # 添加 cookies 文件（如果有提供）
    if cookies:
        ydl_opts["cookiefile"] = cookies

    downloaded_file = None

    # 定義一個鉤子來獲取下載的文件路徑
    def get_filepath_hook(d):
        nonlocal downloaded_file
        if d["status"] == "finished":
            downloaded_file = d["filename"]
            if verbose:
                print(f"下載完成：{downloaded_file}")

    ydl_opts["progress_hooks"] = [get_filepath_hook]

    # 執行下載
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            # 如果文件已經下載，可能沒有觸發 hook，所以需要手動設置檔案路徑
            if not downloaded_file and "requested_downloads" in info_dict:
                # 嘗試從 info_dict 獲取檔案路徑
                for download in info_dict["requested_downloads"]:
                    downloaded_file = download.get("filepath")
                    if downloaded_file:
                        if verbose:
                            print(f"使用已存在的檔案：{downloaded_file}")
                        break

            # 如果仍然沒有檔案路徑，嘗試使用標題和擴展名構建
            if not downloaded_file and "title" in info_dict and "ext" in info_dict:
                safe_title = "".join(
                    [
                        c if c.isalnum() or c in [" ", "-", "_"] else "_"
                        for c in info_dict["title"]
                    ]
                )
                safe_title = safe_title[:50]
                possible_path = str(folder_path / f"{safe_title}.{info_dict['ext']}")
                if os.path.exists(possible_path):
                    downloaded_file = possible_path
                    if verbose:
                        print(f"檢測到已存在的檔案：{downloaded_file}")
    except Exception as e:
        # 檢查錯誤信息，如果包含「檔案已經下載」相關信息
        error_msg = str(e).lower()
        if "has already been downloaded" in error_msg or "already exists" in error_msg:
            # 嘗試從錯誤消息中提取檔案路徑
            path_match = re.search(r"'(.*?)'", str(e))
            if path_match:
                downloaded_file = path_match.group(1)
                if verbose:
                    print(f"使用已下載的檔案：{downloaded_file}")
            else:
                # 嘗試在資料夾中找到可能的檔案
                potential_files = list(folder_path.glob("*.*"))
                if potential_files:
                    # 獲取最新的檔案
                    downloaded_file = str(
                        sorted(potential_files, key=os.path.getmtime)[-1]
                    )
                    if verbose:
                        print(f"使用資料夾中最新的檔案：{downloaded_file}")
        else:
            print(f"下載時出錯: {e}")

    # 如果是音檔下載，文件擴展名會更改為 .flac
    if download_format == "audio" and downloaded_file:
        downloaded_file = re.sub(r"\.[^.]+$", ".flac", downloaded_file)

    if downloaded_file and verbose:
        print(f"文件已下載至: {downloaded_file}")

    return downloaded_file, folder_path


def main():
    parser = argparse.ArgumentParser(
        description="使用 FunASR 轉錄音檔文件或從 URL 下載後轉錄"
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

    # FunASR 轉錄參數
    parser.add_argument(
        "--model",
        type=str,
        default="paraformer-zh",
        choices=[
            "paraformer-zh",
            "paraformer",
            "sensevoice",
            "SenseVoiceSmall",
            "large-v3",
            "whisper-large-v3",
            "large-v3-turbo",
            "whisper-large-v3-turbo",
            "fun-asr-nano",
            "nano",
        ],
        help="FunASR 模型名稱 (默認: paraformer-zh)",
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
        help="計算類型 (FunASR 不使用此參數，保留用於 API 兼容性)",
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
        help="任務類型 (默認: transcribe，translate 需要 Whisper 模型)",
    )
    parser.add_argument(
        "--beam_size",
        type=int,
        default=5,
        help="束搜索大小 (默認: 5，僅用於 Whisper 模型)",
    )
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
