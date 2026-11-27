"""
LLM semantic subtitle segmentation.

The LLM only decides *where* lines break: it receives the plain transcript
and returns it with newlines inserted. The characters are checked against
the input, and each break is mapped back onto the word-level timestamps, so
timing always comes from the forced aligner. Any chunk the LLM gets wrong
keeps its rule-based lines from ``segment_words``.
"""

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from backend.shared.llm_postprocess import (
    _RETRY_BACKOFF,
    _friendly_error,
    _is_retryable,
    _rewrite_localhost_url,
)
from backend.shared.subtitle_segmentation import (
    attach_punctuation,
    is_word_char,
    join_tokens,
    segment_words,
)

logger = logging.getLogger("llm_segmentation")

MAX_CHARS = 25
MAX_DURATION = 6.0
FORCE_BREAK_PAUSE = 1.0
CHUNK_CHARS = 1500
_MAX_ATTEMPTS = 2

_OPENING_PUNCT = set("「『（(《【“‘[{<")
_TRAILING_STRIP = set("，,。.、；;：:")
_BASE_KEYS = {"id", "start", "end", "text", "words", "confidence"}

_SYSTEM_PROMPT = """\
你是專業的字幕斷句員。使用者會給你一段語音轉錄文字，請把它切成適合螢幕閱讀的字幕行。

## 規則
1. **只能插入換行**：不可新增、刪除、修改或調換任何字、標點或空格。逐字照抄原文，只在要斷行的地方換行。
2. **每行不超過 {max_chars} 個字**，理想長度約 10～20 字；不要切出只有 1～3 個字的零碎行。
3. **以語意完整為最優先**：每行應是一個完整的意群（主謂、動賓、介賓、修飾語與被修飾語保持在同一行）。
   - 錯誤：「另一個非常｜重要的知識點」（副詞「非常」與「重要」被拆開）
   - 錯誤：「檢測自己有沒有｜被除錯」（動詞片語被拆開）
4. 優先在句號、問號、逗號等標點後斷行；沒有標點時，在完整子句或片語之間斷行。
5. 行尾不要停在「的、地、得、把、被、在、和、跟、對、從、給、為、是、這個、一個、因為、如果、就是」等需要接續的字詞；行首不要以「的、了、著、過、們、嗎、呢、吧」開始。
6. 英文單字、數字、程式名稱、專有名詞不可從中間切開。

## 輸出
只輸出斷行後的原文，每行一條字幕，不要加行號、引號、說明或任何其他內容。
"""


def _letters(text: str) -> str:
    return "".join(ch for ch in text if is_word_char(ch))


def _clean_line(text: str) -> str:
    text = text.strip()
    while text and text[-1] in _TRAILING_STRIP:
        text = text[:-1].rstrip()
    return text


def _is_word_timed(seg: Dict[str, Any]) -> bool:
    words = seg.get("words") or []
    spelled = "".join(w.get("word", "") for w in words)
    return bool(words) and _letters(spelled) == _letters(seg.get("text", ""))


def _extra_keys(seg: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in seg.items() if k not in _BASE_KEYS}


def _text_cut(text: str, n_letters: int) -> int:
    """Index in *text* just after its *n_letters*-th letter plus trailing punct."""
    seen = 0
    i = 0
    while i < len(text) and seen < n_letters:
        if is_word_char(text[i]):
            seen += 1
        i += 1
    while (
        i < len(text)
        and not is_word_char(text[i])
        and text[i] not in _OPENING_PUNCT
    ):
        i += 1
    return i


def _word_breaks(words: List[Dict[str, Any]], lines: List[str]) -> List[int]:
    """Word indices where a new line starts, snapped to whole words."""
    word_ends = []
    total = 0
    for w in words:
        total += len(_letters(w.get("word", "")))
        word_ends.append(total)

    breaks: List[int] = []
    offset = 0
    for line in lines[:-1]:
        offset += len(_letters(line))
        idx = next(i for i, end in enumerate(word_ends) if end >= offset)
        if idx + 1 < len(words) and (not breaks or idx + 1 > breaks[-1]):
            breaks.append(idx + 1)
    return breaks


def _violates_limits(words: List[Dict[str, Any]], text: str, max_chars: int) -> bool:
    if len(text) > max_chars:
        return True
    if words[-1]["end"] - words[0]["start"] > MAX_DURATION:
        return True
    return any(
        b["start"] - a["end"] >= FORCE_BREAK_PAUSE for a, b in zip(words, words[1:])
    )


def _build_lines(
    text: str,
    words: List[Dict[str, Any]],
    breaks: List[int],
    extra: Dict[str, Any],
    max_chars: int,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    bounds = [0] + breaks + [len(words)]
    letter_counts = [len(_letters(w.get("word", ""))) for w in words]
    for a, b in zip(bounds, bounds[1:]):
        chunk = [dict(w) for w in words[a:b]]
        lo = _text_cut(text, sum(letter_counts[:a])) if a else 0
        hi = _text_cut(text, sum(letter_counts[:b]))
        line_text = _clean_line(text[lo:hi])
        if not line_text:
            continue
        if _violates_limits(chunk, line_text, max_chars):
            pieces = segment_words(
                attach_punctuation(chunk, line_text),
                max_chars=max_chars,
                max_duration=MAX_DURATION,
                force_break_pause=FORCE_BREAK_PAUSE,
            )
        else:
            pieces = [
                {
                    "start": chunk[0]["start"],
                    "end": chunk[-1]["end"],
                    "text": line_text,
                    "confidence": None,
                    "words": chunk,
                }
            ]
        out.extend({**extra, **p} for p in pieces if p.get("text"))
    return out


def _ask_llm(
    client: Any,
    model: str,
    text: str,
    system_prompt: str,
    content_hint: Optional[str],
) -> Optional[List[str]]:
    """Return the LLM's lines, or None when it altered the text."""
    user_msg = text
    if content_hint:
        user_msg = f"【內容描述（僅供參考，不要輸出）】{content_hint}\n\n{text}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]
    for attempt in range(_MAX_ATTEMPTS + 1):
        try:
            response = client.chat.completions.create(
                model=model, messages=messages, temperature=0.1
            )
        except Exception as exc:
            if _is_retryable(exc) and attempt < _MAX_ATTEMPTS:
                time.sleep(_RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)])
                continue
            raise
        raw = response.choices[0].message.content or ""
        lines = [
            ln.strip() for ln in raw.strip().split("\n")
            if ln.strip() and not ln.strip().startswith("```")
        ]
        if lines and _letters("".join(lines)) == _letters(text):
            return lines
        if attempt >= _MAX_ATTEMPTS - 1:
            return None
        logger.info("LLM altered the transcript while segmenting — retrying")
        messages = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": "你改動了原文文字。請逐字照抄原文，只插入換行後重新輸出。"},
        ]
    return None


def _chunk_segments(
    segments: List[Dict[str, Any]], chunk_chars: int
) -> List[List[Dict[str, Any]]]:
    """Group consecutive segments into LLM batches (same speaker, word-timed)."""
    chunks: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    size = 0
    for seg in segments:
        new_group = (
            not current
            or seg.get("speaker") != current[-1].get("speaker")
            or _is_word_timed(seg) != _is_word_timed(current[-1])
            or size + len(seg.get("text", "")) > chunk_chars
        )
        if new_group and current:
            chunks.append(current)
            current, size = [], 0
        current.append(seg)
        size += len(seg.get("text", ""))
    if current:
        chunks.append(current)
    return chunks


def _resegment_chunk(
    chunk: List[Dict[str, Any]],
    client: Any,
    model: str,
    system_prompt: str,
    content_hint: Optional[str],
    max_chars: int,
) -> List[Dict[str, Any]]:
    if not all(_is_word_timed(seg) for seg in chunk):
        return [dict(seg) for seg in chunk]
    text = join_tokens(seg.get("text", "").strip() for seg in chunk)
    words = [w for seg in chunk for w in seg["words"]]
    try:
        lines = _ask_llm(client, model, text, system_prompt, content_hint)
    except Exception as exc:
        logger.warning("LLM segmentation failed: %s", _friendly_error(exc))
        lines = None
    if lines is None:
        return [dict(seg) for seg in chunk]
    breaks = _word_breaks(words, lines)
    return _build_lines(text, words, breaks, _extra_keys(chunk[0]), max_chars)


def resegment_with_llm(
    segments: List[Dict[str, Any]],
    *,
    client: Any,
    model: str,
    content_hint: Optional[str] = None,
    max_chars: int = MAX_CHARS,
    chunk_chars: int = CHUNK_CHARS,
    status_callback: Optional[Callable] = None,
) -> List[Dict[str, Any]]:
    """Re-break word-timed *segments* at semantic boundaries chosen by an LLM.

    Segments without matching word timings, and any chunk where the LLM
    fails or rewrites the text, are returned unchanged.
    """
    if not segments:
        return list(segments)
    system_prompt = _SYSTEM_PROMPT.format(max_chars=max_chars)
    chunks = _chunk_segments(segments, chunk_chars)
    result: List[Dict[str, Any]] = []
    for idx, chunk in enumerate(chunks):
        if status_callback:
            status_callback(
                f"AI 語意斷句中 ({idx + 1}/{len(chunks)})...",
                progress=90.0 + 2.0 * idx / len(chunks),
            )
        result.extend(
            _resegment_chunk(
                chunk, client, model, system_prompt, content_hint, max_chars
            )
        )
    for i, seg in enumerate(result):
        seg["id"] = i
    return result


def resegment_subtitles(
    segments: List[Dict[str, Any]],
    *,
    api_key: str,
    base_url: str = "https://api.openai.com/v1",
    model: str = "gpt-4o-mini",
    content_hint: Optional[str] = None,
    status_callback: Optional[Callable] = None,
) -> List[Dict[str, Any]]:
    """Build an OpenAI-compatible client and run :func:`resegment_with_llm`."""
    try:
        from openai import OpenAI
    except ImportError:
        logger.error("openai package not installed — skipping LLM segmentation")
        return segments
    client = OpenAI(
        api_key=api_key, base_url=_rewrite_localhost_url(base_url.rstrip("/"))
    )
    return resegment_with_llm(
        segments,
        client=client,
        model=model,
        content_hint=content_hint,
        status_callback=status_callback,
    )
