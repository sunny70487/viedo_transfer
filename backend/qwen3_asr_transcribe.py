#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Qwen3-ASR transcription engine.

Drop-in replacement for funasr_transcribe with the same public API:
    transcribe_audio(...)  → dict of output file paths
    check_gpu()            → GPU info dict
    download_from_url(...) → (file_path, folder_path)

Utility functions (download_from_url, check_gpu, split_audio, format_timestamp)
and subtitle post-processing (backend.shared.subtitle_postprocess) are shared
with the other engines and the subtitle editor.
"""

import logging
import time
import threading

import torch

# ---- Re-use shared utilities ----
from backend.shared.download_helpers import download_from_url  # noqa: F401 — re-exported
from backend.shared.asr_context import build_asr_context
from backend.shared.subtitle_postprocess import postprocess_segments
from backend.shared.subtitle_segmentation import attach_punctuation
from backend.shared.split_audio_helpers import split_audio, split_audio_by_vad
from backend.shared.transcribe_helpers import format_timestamp
from backend.shared.transcription_pipeline import (
    resolve_device,
    print_gpu_info,
    init_output_paths,
    init_buffers,
    write_output_files,
)
from backend.shared.video_utils import maybe_prepare_video_output

logger = logging.getLogger("qwen3_asr_transcribe")

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


# qwen_asr cuts its input into chunks of at most this many seconds and runs
# one generate() per chunk (mirrors MAX_FORCE_ALIGN_INPUT_SECONDS /
# MAX_ASR_INPUT_SECONDS in qwen_asr.inference.utils).
_FALLBACK_ALIGN_CHUNK_SECONDS = 180
_FALLBACK_ASR_CHUNK_SECONDS = 1200

# Dense speech measured ~5-6 tokens/s; 10 leaves headroom for fast talkers
# and mixed CJK/English text. A too-small budget silently drops the tail of
# every chunk, which showed up as 10-20 s subtitle gaps on long lectures.
_TOKENS_PER_SECOND_BUDGET = 10

# Output this close to the cap was almost certainly cut off by it.
_TRUNCATION_MARGIN_TOKENS = 16


def _max_chunk_seconds(word_timestamps: bool) -> int:
    """Longest audio span qwen_asr feeds to a single generate() call."""
    try:
        from qwen_asr.inference import utils as qwen_utils

        if word_timestamps:
            return int(qwen_utils.MAX_FORCE_ALIGN_INPUT_SECONDS)
        return int(qwen_utils.MAX_ASR_INPUT_SECONDS)
    except Exception:
        if word_timestamps:
            return _FALLBACK_ALIGN_CHUNK_SECONDS
        return _FALLBACK_ASR_CHUNK_SECONDS


def _max_new_tokens_for(word_timestamps: bool) -> int:
    """Token budget large enough that no chunk can be cut short."""
    return _max_chunk_seconds(word_timestamps) * _TOKENS_PER_SECOND_BUDGET


def _output_hit_token_limit(model, text: str) -> bool:
    """True when ``text`` is long enough that generation hit max_new_tokens."""
    limit = getattr(model, "max_new_tokens", None)
    tokenizer = getattr(getattr(model, "processor", None), "tokenizer", None)
    if not limit or tokenizer is None or not text:
        return False
    try:
        token_count = len(tokenizer(text, add_special_tokens=False)["input_ids"])
    except Exception:
        return False
    return token_count >= limit - _TRUNCATION_MARGIN_TOKENS


def _warn_if_truncated(model, text: str, start_s: float, label: str) -> None:
    if _output_hit_token_limit(model, text):
        logger.warning(
            "%s (starting %.1fs) reached max_new_tokens=%s; "
            "the end of this span may be missing from the transcript",
            label,
            start_s,
            model.max_new_tokens,
        )


def _build_qwen3_model(model_name: str, device: str, word_timestamps: bool = True):
    """Instantiate a Qwen3ASRModel with optional ForcedAligner."""
    from qwen_asr import Qwen3ASRModel

    dtype = torch.bfloat16 if "cuda" in device else torch.float32

    kwargs = {
        "dtype": dtype,
        "device_map": device,
        "max_inference_batch_size": 32,
        "max_new_tokens": _max_new_tokens_for(word_timestamps),
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

        # The aligner strips punctuation; restore it from the ASR text so
        # downstream segmentation can break at sentence / clause marks.
        all_words = attach_punctuation(all_words, full_text)

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
# Post-processing: punctuation / pause / word-boundary re-segmentation
# ============================================================


def _postprocess_segments(segments_json, words_data, glossary=None):
    return postprocess_segments(segments_json, words_data, glossary=glossary)


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
    context=None,
    hotwords=None,
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
        vad_filter (bool): 啟用 FireRedVAD，在靜音處切段（需搭配 split_segments）
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
        context (str): 音檔情境描述，用於偏置辨識結果
        hotwords (list|str): 專有名詞/術語清單，提高這些詞的辨識正確率

    返回:
        dict: 輸出文件路徑字典
    """
    # Resolve model name
    model_name = _resolve_model_name(model_size)

    if verbose:
        print(f"正在載入模型: {model_name} (原始參數: {model_size})")
    start_time = time.time()

    device = resolve_device(device, verbose=verbose)
    print_gpu_info(device, verbose=verbose)

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

    asr_context = build_asr_context(context=context, hotwords=hotwords)
    if asr_context and verbose:
        print(f"啟用辨識偏置 context（{len(asr_context)} 字元）")

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

        if vad_filter:
            segment_files, temp_dir, used_vad = split_audio_by_vad(
                audio_path,
                max_duration=segment_duration,
                output_dir=None,
                verbose=verbose,
                max_workers=max_workers,
            )
        else:
            raw_files, temp_dir = split_audio(
                audio_path,
                segment_duration=segment_duration,
                output_dir=None,
                verbose=verbose,
                max_workers=max_workers,
            )
            segment_files = [
                (path, float(index * segment_duration))
                for index, path in enumerate(raw_files)
            ]
            used_vad = False

        if verbose:
            mode = "VAD 語音邊界" if used_vad else "固定間隔"
            print(f"共分割為 {len(segment_files)} 個片段（{mode}）")

        single_generate_per_segment = segment_duration <= _max_chunk_seconds(
            word_timestamps
        )

        segments_txt_path = base_output_path / f"{base_filename}_segments.txt"
        with open(segments_txt_path, "w", encoding="utf-8") as segments_file:
            total_segs = len(segment_files)
            for i, (segment_file, segment_offset) in enumerate(segment_files):
                if verbose:
                    print(f"正在轉錄片段 {i + 1}/{total_segs}: {segment_file}")

                if status_callback:
                    seg_progress = 30.0 + (i / total_segs) * 65.0
                    status_callback(
                        f"正在轉錄片段 {i + 1}/{total_segs}",
                        progress=seg_progress,
                    )

                transcription_start = time.time()

                # Run Qwen3-ASR on this segment
                results = model.transcribe(
                    audio=segment_file,
                    context=asr_context,
                    language=lang_name,
                    return_time_stamps=word_timestamps,
                )

                # Qwen3-ASR returns a list of results; process each
                result_list = results if isinstance(results, list) else [results]

                # Offset comes from the splitter, not from the loop index, so a
                # dropped or variable-length chunk cannot shift later timestamps.
                time_offset = segment_offset

                for r in result_list:
                    if single_generate_per_segment:
                        _warn_if_truncated(
                            model, r.text, time_offset, f"片段 {i + 1}/{total_segs}"
                        )
                    seg_segments, seg_words, seg_text, seg_lang = _parse_qwen3_result(
                        r,
                        time_offset=time_offset,
                    )

                    if seg_lang:
                        detected_language = detected_language or seg_lang

                    seg_segments, seg_words = _postprocess_segments(
                        seg_segments, seg_words, glossary=hotwords
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
                        if status_callback:
                            status_callback(segment={
                                "start": seg.get("start", 0.0),
                                "end": seg.get("end", 0.0),
                                "text": seg.get("text", ""),
                                "speaker": seg.get("speaker"),
                            })

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
            status_callback("正在使用 Qwen3-ASR 進行轉錄...", progress=30.0)

        # Run Qwen3-ASR
        results = model.transcribe(
            audio=audio_path,
            context=asr_context,
            language=lang_name,
            return_time_stamps=word_timestamps,
        )

        if status_callback:
            status_callback("轉錄完成，正在生成輸出...", progress=90.0)

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

            seg_segments, seg_words = _postprocess_segments(
                seg_segments, seg_words, glossary=hotwords
            )

            segments_json.extend(seg_segments)
            words_data.extend(seg_words)
            if status_callback:
                for seg in seg_segments:
                    status_callback(segment={
                        "start": seg.get("start", 0.0),
                        "end": seg.get("end", 0.0),
                        "text": seg.get("text", ""),
                        "speaker": seg.get("speaker"),
                    })

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

    speakers_detected = sorted(
        {seg.get("speaker") for seg in segments_json if seg.get("speaker")}
    )
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
        speakers=speakers_detected if speakers_detected else None,
        model_name=model_name,
        verbose=verbose,
        show_in_terminal=show_in_terminal,
    )

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
