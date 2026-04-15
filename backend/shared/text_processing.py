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


_TRAILING_PERIOD = re.compile(r"[。.]+$")


def smart_strip_punctuation(text: str) -> str:
    """保留逗號、問號等有助閱讀的標點，僅移除行尾句號。"""
    return _TRAILING_PERIOD.sub("", text).strip()


def swap_first_two_lines(text: str) -> str:
    """若文字含至少兩行（以換行分隔），交換第一行與第二行；其餘行序不變。"""
    lines = text.split("\n")
    if len(lines) < 2:
        return text
    lines[0], lines[1] = lines[1], lines[0]
    return "\n".join(lines)


_LATIN_LOWER_UPPER = re.compile(r"([a-z])([A-Z])")
_LATIN_LETTER_DIGIT = re.compile(r"([a-zA-Z])(\d)")
_DIGIT_LATIN_LETTER = re.compile(r"(\d)([a-zA-Z])")
_CJK = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


def space_english_tokens(text: str) -> str:
    """Insert spaces at camelCase boundaries in non-CJK text.

    Handles patterns like 'DockerandContainerd' → 'Docker and Containerd'.
    For all-lowercase concatenations, use rebuild_segment_text_from_timestamps
    which leverages timestamp gaps for more accurate word boundaries.
    """
    if not text or _CJK.search(text):
        return text

    result = _LATIN_LOWER_UPPER.sub(r"\1 \2", text)
    result = _LATIN_LETTER_DIGIT.sub(r"\1 \2", result)
    result = _DIGIT_LATIN_LETTER.sub(r"\1 \2", result)
    result = re.sub(r" {2,}", " ", result)
    return result.strip()


def rebuild_segment_text_from_timestamps(
    chars: list[str],
    timestamps: list[list[float]],
    gap_threshold_ms: float = 120.0,
) -> str:
    """Reconstruct text from character-level timestamps, inserting spaces at gaps.

    FunASR character-level timestamps have small gaps within a word and larger
    gaps between words. By detecting these gaps we can reliably insert spaces
    even for all-lowercase English like 'manytimes' → 'many times'.

    Args:
        chars: list of individual characters (spaces already stripped)
        timestamps: list of [start_ms, end_ms] pairs, same length as chars
        gap_threshold_ms: minimum gap (in ms) between consecutive characters
            to be considered a word boundary
    """
    if not chars:
        return ""
    if len(chars) == 1:
        return chars[0]

    if not timestamps or len(timestamps) < 2:
        return "".join(chars)

    parts = [chars[0]]
    for i in range(1, min(len(chars), len(timestamps))):
        prev_end = timestamps[i - 1][1]
        curr_start = timestamps[i][0]
        gap = curr_start - prev_end

        prev_char = chars[i - 1]
        curr_char = chars[i]
        prev_is_latin = prev_char.isascii() and prev_char.isalpha()
        curr_is_latin = curr_char.isascii() and curr_char.isalpha()

        if gap >= gap_threshold_ms and prev_is_latin and curr_is_latin:
            parts.append(" ")
        parts.append(chars[i])

    text = "".join(parts)
    text = _LATIN_LOWER_UPPER.sub(r"\1 \2", text)
    return re.sub(r" {2,}", " ", text).strip()


def _join_words_text(words: list) -> str:
    """Join word-level tokens into text with appropriate spacing.

    Handles both multi-character tokens (Qwen3-ASR) and single-character
    tokens (FunASR) by checking token lengths and using timestamp gaps
    for single-char Latin sequences.
    """
    if not words:
        return ""

    has_timestamps = all("start" in w and "end" in w for w in words if w.get("word"))
    avg_len = sum(len(w.get("word", "")) for w in words) / max(len(words), 1)

    if avg_len <= 1.5 and has_timestamps:
        chars = [w.get("word", "") for w in words if w.get("word")]
        timestamps = [[w["start"] * 1000, w["end"] * 1000] for w in words if w.get("word")]
        return rebuild_segment_text_from_timestamps(chars, timestamps)

    parts = []
    for w in words:
        ch = w.get("word", "")
        if not ch:
            continue
        if parts and _needs_space(parts[-1], ch):
            parts.append(" ")
        parts.append(ch)
    return "".join(parts)


def _needs_space(prev: str, curr: str) -> bool:
    """Determine if a space is needed between two adjacent tokens."""
    if not prev or not curr:
        return False
    last_char = prev[-1]
    first_char = curr[0]
    last_is_latin = last_char.isascii() and last_char.isalpha()
    first_is_latin = first_char.isascii() and first_char.isalpha()
    last_is_digit = last_char.isdigit()
    first_is_digit = first_char.isdigit()
    if last_is_latin and first_is_latin:
        return True
    if (last_is_latin and first_is_digit) or (last_is_digit and first_is_latin):
        return True
    return False


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

        left_text = _join_words_text(left_words)
        right_text = _join_words_text(right_words)

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
