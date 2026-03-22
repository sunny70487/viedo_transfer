#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Qwen3-ASR transcription engine.

Drop-in replacement for funasr_transcribe with the same public API:
    transcribe_audio(...)  → dict of output file paths
    check_gpu()            → GPU info dict
    download_from_url(...) → (file_path, folder_path)

Utility functions (download_from_url, check_gpu, split_audio, format_timestamp,
_convert_to_traditional, _strip_punctuation, _split_long_segments) are
re-used from funasr_transcribe to avoid duplication.
"""

import os
import time
import threading
import json
import subprocess
import re
from pathlib import Path

import torch

# ---- Re-use utilities from the original FunASR module ----
from backend.funasr_transcribe import (
    download_from_url,  # noqa: F401 — re-exported
    split_audio,
    _convert_to_traditional,
    _strip_punctuation,
    _split_long_segments,
)
from backend.shared.transcribe_helpers import check_gpu, format_timestamp
from backend.shared.video_utils import maybe_prepare_video_output

# ============================================================
# Qwen3-ASR model name mapping
# ============================================================
_QWEN3_MODEL_MAP = {
    "qwen3-asr-1.7b": "Qwen/Qwen3-ASR-1.7B",
    "qwen3-asr-0.6b": "Qwen/Qwen3-ASR-0.6B",
    # Legacy FunASR names → map to Qwen3-ASR-1.7B
    "paraformer-zh": "Qwen/Qwen3-ASR-1.7B",
    "paraformer": "Qwen/Qwen3-ASR-1.7B",
    "sensevoice": "Qwen/Qwen3-ASR-1.7B",
    "large-v3": "Qwen/Qwen3-ASR-1.7B",
    "large-v3-turbo": "Qwen/Qwen3-ASR-1.7B",
    "fun-asr-nano": "Qwen/Qwen3-ASR-0.6B",
    "nano": "Qwen/Qwen3-ASR-0.6B",
    "tiny": "Qwen/Qwen3-ASR-1.7B",
    "base": "Qwen/Qwen3-ASR-1.7B",
    "small": "Qwen/Qwen3-ASR-1.7B",
    "medium": "Qwen/Qwen3-ASR-1.7B",
    "large-v1": "Qwen/Qwen3-ASR-1.7B",
    "large-v2": "Qwen/Qwen3-ASR-1.7B",
}

_FORCED_ALIGNER_MAP = {
    "Qwen/Qwen3-ASR-1.7B": "Qwen/Qwen3-ForcedAligner-0.6B",
    "Qwen/Qwen3-ASR-0.6B": "Qwen/Qwen3-ForcedAligner-0.6B",
}

# Language code → Qwen3-ASR full language name
_LANG_CODE_TO_NAME = {
    "zh": "Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "pt": "Portuguese",
    "ar": "Arabic",
    "ru": "Russian",
    "it": "Italian",
    "th": "Thai",
    "vi": "Vietnamese",
    "id": "Indonesian",
    None: None,
}

# ============================================================
# Model caching (same pattern as FunASR module)
# ============================================================
_MODEL_CACHE_LOCK = threading.Lock()
_LOADED_MODELS = {}


def _resolve_model_name(model_size: str) -> str:
    """Map a user-facing model_size string to a Qwen3-ASR model identifier."""
    return _QWEN3_MODEL_MAP.get(model_size, "Qwen/Qwen3-ASR-1.7B")


def _resolve_language(language) -> str | None:
    """Convert a short language code (e.g. 'zh') to the full name Qwen3-ASR expects."""
    if language is None:
        return None
    return _LANG_CODE_TO_NAME.get(language, language)


def _build_qwen3_model(model_name: str, device: str, word_timestamps: bool = True):
    """Instantiate a Qwen3ASRModel with optional ForcedAligner."""
    from qwen_asr import Qwen3ASRModel

    dtype = torch.bfloat16 if "cuda" in device else torch.float32

    kwargs = {
        "dtype": dtype,
        "device_map": device,
        "max_inference_batch_size": 32,
        "max_new_tokens": 256,
    }

    # Attach forced aligner for word-level timestamps
    if word_timestamps and model_name in _FORCED_ALIGNER_MAP:
        aligner_name = _FORCED_ALIGNER_MAP[model_name]
        kwargs["forced_aligner"] = aligner_name
        kwargs["forced_aligner_kwargs"] = {
            "dtype": dtype,
            "device_map": device,
        }

    return Qwen3ASRModel.from_pretrained(model_name, **kwargs)


# ============================================================
# Result parsing
# ============================================================


def _parse_qwen3_result(result, time_offset: float = 0.0):
    """
    Parse Qwen3-ASR result into the standard segments / words structure.

    Returns:
        (segments_json, words_data, full_text, detected_language)
    """
    segments_json = []
    words_data = []

    full_text = (result.text or "").strip()
    detected_language = getattr(result, "language", None)

    time_stamps = getattr(result, "time_stamps", None)
    if time_stamps and len(time_stamps) > 0:
        # time_stamps may be a list of lists; flatten if needed
        ts_list = time_stamps[0] if (isinstance(time_stamps[0], list)) else time_stamps

        # Build words
        all_words = []
        for ts in ts_list:
            w = {
                "word": ts.text,
                "start": ts.start_time + time_offset,
                "end": ts.end_time + time_offset,
                "probability": None,
            }
            all_words.append(w)

        # Group into segments by punctuation boundaries (fine-grained, ~1-3s per segment)
        current_words = []
        current_text = ""
        seg_start = None
        # Break on ALL punctuation — commas, periods, question marks, etc.
        SEGMENT_BREAKS = set("。？！.?!，、,；;：:…～~）)」』】》")
        MAX_SEG_DURATION = 5.0

        for w in all_words:
            if seg_start is None:
                seg_start = w["start"]
            current_words.append(w)
            current_text += w["word"]

            seg_duration = w["end"] - seg_start
            word_stripped = w["word"].rstrip()
            is_break_point = word_stripped and word_stripped[-1] in SEGMENT_BREAKS

            if is_break_point or seg_duration >= MAX_SEG_DURATION:
                seg = {
                    "id": len(segments_json),
                    "start": seg_start,
                    "end": w["end"],
                    "text": current_text,
                    "confidence": None,
                    "words": list(current_words),
                }
                segments_json.append(seg)
                words_data.extend(current_words)
                current_words = []
                current_text = ""
                seg_start = None

        # Flush remaining
        if current_words:
            seg = {
                "id": len(segments_json),
                "start": seg_start,
                "end": current_words[-1]["end"],
                "text": current_text,
                "confidence": None,
                "words": list(current_words),
            }
            segments_json.append(seg)
            words_data.extend(current_words)
    else:
        # No timestamps — single segment
        if full_text:
            segments_json.append(
                {
                    "id": 0,
                    "start": 0.0 + time_offset,
                    "end": 0.0 + time_offset,
                    "text": full_text,
                    "confidence": None,
                    "words": [],
                }
            )

    return segments_json, words_data, full_text, detected_language


# ============================================================
# Post-processing: pause-based re-segmentation
# ============================================================


def _merge_segments_by_pause(
    segments_json,
    words_data,
    pause_threshold: float = 0.25,
    max_duration: float = 5.0,
    max_chars: int = 25,
    soft_pause: float = 0.15,
    soft_min_chars: int = 10,
):
    """
    Re-segment words into natural phrase-level subtitle blocks using
    speech pause detection from word-level timestamps.

    Uses a two-tier break strategy to produce FunASR-like short phrases:

      - **Soft break**: a small pause (≥ soft_pause) when enough text has
        accumulated (≥ soft_min_chars).  This catches natural phrase
        boundaries where the speaker takes a brief breath.
      - **Hard break**: a clear pause (≥ pause_threshold), OR the segment
        would exceed max_duration / max_chars.

    Typical output: ~3-15 characters per segment, ~1-3 seconds each.

    Args:
        segments_json: List of segment dicts (each with a ``words`` list).
        words_data:    Flat list of word dicts (will be rebuilt from result).
        pause_threshold: Gap (seconds) that always triggers a break.
        max_duration:  Hard maximum segment duration (seconds).
        max_chars:     Hard maximum characters per segment.
        soft_pause:    Smaller gap threshold used together with soft_min_chars.
        soft_min_chars: Minimum accumulated chars before a soft_pause triggers a break.

    Returns:
        (new_segments, new_words) — re-segmented lists.
    """
    # Collect all words in chronological order
    all_words = []
    for seg in segments_json:
        for w in seg.get("words", []):
            all_words.append(w)

    if len(all_words) < 2:
        return segments_json, words_data

    new_segments = []
    current_words = [all_words[0]]

    for i in range(1, len(all_words)):
        prev_word = all_words[i - 1]
        curr_word = all_words[i]

        # Gap between end of previous word and start of current word
        gap = curr_word["start"] - prev_word["end"]

        # What the segment would look like if we appended curr_word
        current_start = current_words[0]["start"]
        potential_duration = curr_word["end"] - current_start
        current_chars = sum(len(w["word"]) for w in current_words)
        potential_chars = current_chars + len(curr_word["word"])

        # Soft break: small pause + enough accumulated text → natural phrase boundary
        soft_break = gap >= soft_pause and current_chars >= soft_min_chars

        # Hard break: clear pause, or would exceed hard limits
        hard_break = (
            gap >= pause_threshold
            or potential_duration > max_duration
            or potential_chars > max_chars
        )

        if soft_break or hard_break:
            # Finalize current segment
            text = _strip_punctuation("".join(w["word"] for w in current_words))
            new_segments.append(
                {
                    "id": len(new_segments),
                    "start": current_words[0]["start"],
                    "end": current_words[-1]["end"],
                    "text": text,
                    "confidence": None,
                    "words": list(current_words),
                }
            )
            current_words = [curr_word]
        else:
            current_words.append(curr_word)

    # Flush remaining words
    if current_words:
        text = _strip_punctuation("".join(w["word"] for w in current_words))
        new_segments.append(
            {
                "id": len(new_segments),
                "start": current_words[0]["start"],
                "end": current_words[-1]["end"],
                "text": text,
                "confidence": None,
                "words": list(current_words),
            }
        )

    # Rebuild flat words list from new segments
    new_words = []
    for seg in new_segments:
        new_words.extend(seg.get("words", []))

    return new_segments, new_words


# ============================================================
# Main public API
# ============================================================


def transcribe_audio(
    audio_path,
    model_size="qwen3-asr-1.7b",
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
    speaker_diarization=False,
    num_speakers=None,
) -> dict:
    """
    使用 Qwen3-ASR 將音檔轉錄為文本

    參數:
        audio_path (str): 音檔文件的路徑
        model_size (str): 模型名稱 (qwen3-asr-1.7b, qwen3-asr-0.6b, 或舊版名稱)
        device (str): 運行設備 (auto, cpu, cuda)
        compute_type (str): 計算類型 — 保留用於 API 兼容性
        language (str): 語言代碼 (如 'zh', 'en')，None 表示自動檢測
        task (str): 任務類型 (transcribe, translate)
        beam_size (int): 束搜索大小 — 保留用於 API 兼容性
        vad_filter (bool): 是否使用語音活動檢測過濾 — 保留用於 API 兼容性
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
        speaker_diarization (bool): 是否啟用說話者辨識
        num_speakers (int): 說話者人數（None 表示自動偵測）

    返回:
        dict: 輸出文件路徑字典
    """
    # Resolve model name
    model_name = _resolve_model_name(model_size)

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
        print(f"計算類型: {compute_type} (Qwen3-ASR 不使用此參數)")
        print("正在初始化 Qwen3-ASR 模型...")

    # 初始化模型 (with caching)
    cache_key = (model_name, device, word_timestamps)
    with _MODEL_CACHE_LOCK:
        model = _LOADED_MODELS.get(cache_key)
        if model is None:
            model = _build_qwen3_model(model_name, device, word_timestamps)
            _LOADED_MODELS[cache_key] = model

    model_load_time = time.time() - start_time
    if verbose:
        print(f"模型載入完成，耗時: {model_load_time:.2f} 秒")
        print(f"開始轉錄音檔文件: {audio_path}")

    # Resolve language for Qwen3-ASR
    lang_name = _resolve_language(language)

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

                # Run Qwen3-ASR on this segment
                results = model.transcribe(
                    audio=segment_file,
                    language=lang_name,
                    return_time_stamps=word_timestamps,
                )

                # Qwen3-ASR returns a list of results; process each
                result_list = results if isinstance(results, list) else [results]

                # Parse results with time offset
                time_offset = float(i * segment_duration)

                for r in result_list:
                    seg_segments, seg_words, seg_text, seg_lang = _parse_qwen3_result(
                        r,
                        time_offset=time_offset,
                    )

                    if seg_lang:
                        detected_language = detected_language or seg_lang

                    # Post-processing: split overly long segments
                    seg_segments, seg_words = _split_long_segments(
                        seg_segments, seg_words, max_duration=5.0
                    )

                    # Post-processing: Simplified → Traditional Chinese (Taiwan)
                    for seg in seg_segments:
                        seg["text"] = _convert_to_traditional(seg["text"])
                        for w in seg.get("words", []):
                            w["word"] = _convert_to_traditional(w["word"])
                    for w in seg_words:
                        w["word"] = _convert_to_traditional(w["word"])

                    # Post-processing: 移除標點符號
                    for seg in seg_segments:
                        seg["text"] = _strip_punctuation(seg["text"])

                    # Post-processing: merge short segments into natural sentences
                    seg_segments, seg_words = _merge_segments_by_pause(
                        seg_segments, seg_words
                    )

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
                        start_label = format_timestamp(
                            segment_start or 0.0, format="srt"
                        )
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
            status_callback("正在使用 Qwen3-ASR 進行轉錄...")

        # Run Qwen3-ASR
        results = model.transcribe(
            audio=audio_path,
            language=lang_name,
            return_time_stamps=word_timestamps,
        )

        if verbose:
            print(f"轉錄處理完成！共耗時: {time.time() - transcription_start:.2f} 秒")

        # Qwen3-ASR may return a list or a single result
        result_list = results if isinstance(results, list) else [results]

        for r in result_list:
            seg_segments, seg_words, full_text_parsed, det_lang = _parse_qwen3_result(
                r,
                time_offset=0.0,
            )

            if det_lang:
                detected_language = detected_language or det_lang

            # Post-processing: split overly long segments
            seg_segments, seg_words = _split_long_segments(
                seg_segments, seg_words, max_duration=5.0
            )

            # Post-processing: Simplified → Traditional Chinese (Taiwan)
            for seg in seg_segments:
                seg["text"] = _convert_to_traditional(seg["text"])
                for w in seg.get("words", []):
                    w["word"] = _convert_to_traditional(w["word"])
            for w in seg_words:
                w["word"] = _convert_to_traditional(w["word"])

            # Post-processing: 移除標點符號
            for seg in seg_segments:
                seg["text"] = _strip_punctuation(seg["text"])

            # Post-processing: merge short segments into natural sentences
            # by detecting speech pauses in word-level timestamps
            seg_segments, seg_words = _merge_segments_by_pause(seg_segments, seg_words)

            segments_json.extend(seg_segments)
            words_data.extend(seg_words)

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

    # ================================================================
    # Speaker diarization (optional post-processing step)
    # ================================================================
    if speaker_diarization and segments_json:
        try:
            if status_callback:
                status_callback("正在執行說話者辨識 (Speaker Diarization)...")
            if verbose:
                print("正在執行說話者辨識 (pyannote.audio)...")

            from backend.services.diarization_service import (
                run_diarization,
                assign_speakers_to_segments,
            )

            diarization_segments = run_diarization(
                audio_path=audio_path,
                num_speakers=num_speakers,
                device=device,
            )

            # Assign speaker labels to ASR segments
            assign_speakers_to_segments(segments_json, diarization_segments)

            if verbose:
                speakers = {
                    seg.get("speaker") for seg in segments_json if seg.get("speaker")
                }
                print(f"說話者辨識完成，共偵測到 {len(speakers)} 位說話者")

            if status_callback:
                status_callback("說話者辨識完成，正在生成輸出...")
        except Exception as e:
            # Diarization failure should not block transcription output
            if verbose:
                print(f"⚠ 說話者辨識失敗: {e}")
            logger = __import__("logging").getLogger(__name__)
            logger.warning(f"Speaker diarization failed: {e}", exc_info=True)

    # ================================================================
    # Rebuild SRT / VTT / transcript with speaker labels (if present)
    # ================================================================
    srt_content = ""
    vtt_content = "WEBVTT\n\n"
    transcript_parts = []

    for seg in segments_json:
        segment_text = seg["text"]
        if not segment_text:
            continue

        speaker = seg.get("speaker")
        display_text = f"[{speaker}]: {segment_text}" if speaker else segment_text

        transcript_parts.append(display_text)

        seg_start = seg["start"]
        seg_end = seg["end"]
        segment_number = seg["id"] + 1

        start_time_srt = format_timestamp(seg_start, format="srt")
        end_time_srt = format_timestamp(seg_end, format="srt")
        srt_content += (
            f"{segment_number}\n{start_time_srt} --> {end_time_srt}\n{display_text}\n\n"
        )

        start_time_vtt = format_timestamp(seg_start, format="vtt")
        end_time_vtt = format_timestamp(seg_end, format="vtt")
        vtt_content += f"{start_time_vtt} --> {end_time_vtt}\n{display_text}\n\n"

        if show_in_terminal and display_text:
            print(f"[{seg_start:.2f}s -> {seg_end:.2f}s] {display_text}")

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

    full_transcript = "\n".join(transcript_parts)

    # Collect unique speakers for JSON metadata
    speakers_detected = sorted(
        {seg.get("speaker") for seg in segments_json if seg.get("speaker")}
    )

    json_data = {
        "text": full_transcript,
        "segments": segments_json,
        "language": detected_language,
        "language_probability": language_probability,
        "words": words_data if words_data else None,
        "speakers": speakers_detected if speakers_detected else None,
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
    )

    if verbose:
        print(f"\n轉錄結果已保存至: {output_files}")

    return output_files
