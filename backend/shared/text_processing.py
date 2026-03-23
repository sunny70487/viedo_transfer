"""
Shared text processing utilities for transcription post-processing.
Used by both Qwen3-ASR and FunASR engines.
"""

import re

try:
    from opencc import OpenCC

    _S2TW_CONVERTER = OpenCC("s2twp")
    OPENCC_AVAILABLE = True
except ImportError:
    _S2TW_CONVERTER = None
    OPENCC_AVAILABLE = False

_SUBTITLE_PUNCTUATION = re.compile(
    r"[，。？、！；：\u201c\u201d\u2018\u2019（）【】《》…—,\.!\?;:\"\'()\[\]{}<>\-]"
)


def convert_to_traditional(text: str) -> str:
    """將簡體中文轉換為臺灣繁體中文（含詞彙轉換）。若 opencc 不可用則原樣返回。"""
    if OPENCC_AVAILABLE and _S2TW_CONVERTER is not None:
        return _S2TW_CONVERTER.convert(text)
    return text


def strip_punctuation(text: str) -> str:
    """移除字幕文字中的標點符號。"""
    return _SUBTITLE_PUNCTUATION.sub("", text).strip()


def split_long_segments(segments_json, words_data, max_duration: float = 15.0):
    """
    Post-process: split any segment longer than *max_duration* seconds
    at the nearest word boundary close to the midpoint.
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

    still_long = any(
        (s["end"] - s["start"]) > max_duration and len(s.get("words", [])) >= 2
        for s in new_segments
    )
    if still_long:
        return split_long_segments(new_segments, new_words, max_duration)

    return new_segments, new_words
