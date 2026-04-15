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
from backend.shared.download_helpers import (
    build_safe_title,
    build_yt_dlp_options,
    download_from_url as shared_download_from_url,
)
from backend.shared.split_audio_helpers import split_audio as shared_split_audio
from backend.shared.transcribe_helpers import (
    check_gpu as _shared_check_gpu,
    format_timestamp,
)
from backend.shared.transcription_pipeline import (
    resolve_device,
    print_gpu_info,
    init_output_paths,
    init_buffers,
    write_output_files,
)

from backend.shared.text_processing import (
    convert_to_traditional as _convert_to_traditional,
    strip_punctuation as _strip_punctuation,
    smart_strip_punctuation as _smart_strip_punctuation,
    split_long_segments as _split_long_segments,
    space_english_tokens as _space_english_tokens,
    rebuild_segment_text_from_timestamps as _rebuild_from_ts,
    _join_words_text,
    OPENCC_AVAILABLE,
)

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
    """檢查 GPU 狀態並返回詳細資訊（delegates to shared helper）"""
    return _shared_check_gpu(torch)


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

                seg_start = float(sent.get("start", 0)) / 1000.0 + time_offset
                seg_end = float(sent.get("end", 0)) / 1000.0 + time_offset

                segment_index = len(segments_json)

                # Character-level timestamps from sentence_info
                words_payload = []
                char_timestamps = sent.get("timestamp", [])
                if char_timestamps:
                    chars = list(sent_text.replace(" ", ""))
                    display_text = _rebuild_from_ts(chars, char_timestamps)
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
                else:
                    display_text = sent_text

                transcript_parts.append(display_text)
                segments_json.append(
                    {
                        "id": segment_index,
                        "start": seg_start,
                        "end": seg_end,
                        "text": display_text,
                        "confidence": None,
                        "words": words_payload,
                    }
                )
        else:
            # Flat result — single segment with character-level timestamps
            text = (raw_text or "").strip()
            if not text:
                continue

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
                display_text = _rebuild_from_ts(chars, char_timestamps)
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
            else:
                display_text = text

            transcript_parts.append(display_text)
            segments_json.append(
                {
                    "id": segment_index,
                    "start": seg_start,
                    "end": seg_end,
                    "text": display_text,
                    "confidence": None,
                    "words": words_payload,
                }
            )

    # ---- Post-processing: add spaces between English tokens ----
    for seg in segments_json:
        seg["text"] = _space_english_tokens(seg["text"])

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

    for seg in segments_json:
        seg["text"] = _smart_strip_punctuation(seg["text"])
    transcript_parts = [seg["text"] for seg in segments_json if seg["text"]]

    full_text = (
        "\n".join(transcript_parts)
        if transcript_parts
        else _smart_strip_punctuation(_convert_to_traditional(raw_text.strip()))
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

    device = resolve_device(device, verbose=verbose)
    print_gpu_info(device, verbose=verbose)

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

    base_output_path, base_filename = init_output_paths(audio_path, output_dir)
    bufs = init_buffers()
    transcript_parts = bufs["transcript_parts"]
    srt_content = bufs["srt_content"]
    vtt_content = bufs["vtt_content"]
    segments_json = bufs["segments_json"]
    words_data = bufs["words_data"]
    output_files = bufs["output_files"]
    detected_language = bufs["detected_language"]
    language_probability = bufs["language_probability"]

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

        if status_callback:
            status_callback("正在使用 FunASR 進行轉錄...", progress=30.0)

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

        if status_callback:
            status_callback("轉錄完成，正在生成輸出...", progress=90.0)

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

    write_output_files(
        base_output_path,
        base_filename,
        output_format,
        transcript_parts,
        srt_content,
        vtt_content,
        segments_json,
        words_data,
        detected_language,
        language_probability,
        output_files,
        verbose=verbose,
        show_in_terminal=show_in_terminal,
    )

    from backend.shared.video_utils import maybe_prepare_video_output

    maybe_prepare_video_output(
        audio_path,
        base_output_path,
        base_filename,
        output_files,
        verbose=verbose,
        status_callback=status_callback,
    )

    if verbose:
        print(f"\n轉錄結果已保存至: {output_files}")

    return output_files


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
