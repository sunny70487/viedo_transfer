"""
LLM-based subtitle post-processing using OpenAI-compatible APIs.
Fixes mixed Chinese-English transcription errors, preserves original English
terms, and improves punctuation / sentence flow.
"""

import json
import logging
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def _rewrite_localhost_url(url: str) -> str:
    """In Docker, rewrite localhost/127.0.0.1 to host.docker.internal."""
    if not os.path.exists("/.dockerenv"):
        return url
    return re.sub(
        r"(https?://)(?:localhost|127\.0\.0\.1)(:\d+)",
        r"\1host.docker.internal\2",
        url,
    )

_MAX_RETRIES = 3
_RETRY_BACKOFF = (2, 5, 10)

_SYSTEM_PROMPT = """\
你是一位專業的語音轉錄校對員。你的任務是修正語音辨識（ASR）系統產生的字幕文字。

## 規則
1. **保持行數完全一致**：輸入幾行就輸出幾行，不可合併或拆分。
2. **保留原始時間軸語序**：不可調換任何行的順序。
3. **修正音譯錯誤**：當語音中夾雜英文術語（如程式語言名稱、技術名詞、品牌名等），\
ASR 系統可能會將其音譯為中文字。請根據上下文還原為正確的英文拼寫。\
例如：「賽控」→「Second」、「瑞乃寶」→「Renoir」、「皮森」→「Python」。
4. **修正錯別字與同音字**：修正因語音辨識產生的同音或近音錯字。
5. **中文數字轉阿拉伯數字**：口語中的中文數字詞一律轉為阿拉伯數字。\
包括但不限於：「一百一十」→「110」、「三千五百」→「3500」、「兩萬」→「20000」、\
「三十二」→「32」、「一千零二十四」→「1024」、「五百六十七點八」→「567.8」、\
「兩個半小時」→「2 個半小時」、「第三百二十一」→「第 321」。\
帶單位時數字與單位之間加空格：「一百一十 GB」→「110 GB」。\
序數、年份、日期、百分比等同理：「二零二四年」→「2024 年」、「百分之八十五」→「85%」。\
注意：成語或固定用語中的數字不轉換（如「一模一樣」、「三心二意」、「一般來說」保持原樣）。
6. **改善標點符號**：適當添加逗號、問號等標點以提升可讀性，但不要添加行尾句號。
7. **改善語句通順度**：如果某行讀起來不通順或斷句錯誤，在不改變生成內容的前提下微調斷句使其更自然流暢。
8. **不要添加或刪除實質內容**：只做修正，不可自行添加說明或刪減原意。
9. **僅輸出修正後的字幕文字**：不要輸出行號、解釋、或任何額外說明。

## 輸出格式
每行對應一行字幕文字，行與行之間以換行分隔。不要輸出其他任何內容。
"""

_MAX_LINES_PER_BATCH = 80
_MAX_LINES_PER_BATCH_TRANSLATE = 30
_MAX_CHARS_PER_BATCH = 6_000
_MAX_CHARS_PER_BATCH_TRANSLATE = 3_000
_BATCH_COOLDOWN = 1.0

_CONTEXT_OVERLAP = 3


def _build_user_message(
    lines: List[str],
    content_hint: Optional[str] = None,
    numbered: bool = False,
    prev_context: Optional[List[str]] = None,
    next_context: Optional[List[str]] = None,
) -> str:
    parts = []
    if content_hint:
        parts.append(f"【內容描述】{content_hint}\n")

    if prev_context:
        parts.append("【前文參考（僅供理解上下文，不要修改也不要輸出）】")
        parts.extend(f"... {line}" for line in prev_context)
        parts.append("")

    parts.append(f"【待校對字幕】（共 {len(lines)} 行，輸出必須恰好 {len(lines)} 行）")
    if numbered:
        parts.extend(f"[{i+1}] {line}" for i, line in enumerate(lines))
    else:
        parts.extend(lines)

    if next_context:
        parts.append("")
        parts.append("【後文參考（僅供理解上下文，不要修改也不要輸出）】")
        parts.extend(f"... {line}" for line in next_context)

    return "\n".join(parts)


def _friendly_error(exc: Exception) -> str:
    """Extract a short, readable error message from an OpenAI SDK exception."""
    msg = str(exc)
    if "<html" in msg.lower() or "<!doctype" in msg.lower():
        status = getattr(exc, "status_code", None) or ""
        return f"LLM API 回傳了 HTML 錯誤頁面 (HTTP {status})，伺服器可能暫時無法使用"
    if len(msg) > 300:
        msg = msg[:300] + "..."
    return msg


def _is_retryable(exc: Exception) -> bool:
    """Check if the error is transient and worth retrying."""
    status = getattr(exc, "status_code", None)
    if status and status in (429, 500, 502, 503, 504):
        return True
    cls_name = type(exc).__name__
    return cls_name in ("APITimeoutError", "APIConnectionError", "InternalServerError")


def build_translate_prompt(target_language: str) -> str:
    """Build a system prompt for subtitle translation."""
    return f"""\
你是一位專業的字幕翻譯員。你的任務是將字幕逐行翻譯為{target_language}。

## 規則
1. **嚴格逐行對應**：輸入的每一行前面有 [行號]。你必須按照相同順序，為每一行輸出一行翻譯。\
輸入 N 行就輸出 N 行，不可合併、拆分、跳過或增加行。
2. **翻譯要自然流暢**：符合{target_language}的表達習慣，不要逐字翻譯。
3. **保留專有名詞**：技術術語、品牌名、人名等保留原文或使用通用譯名。
4. **保持語氣和風格**：翻譯應保持原文的語氣。
5. **不要添加或刪除實質內容**：只做翻譯，不可自行添加說明或刪減原意。

## 輸出格式
每行只輸出翻譯後的文字。不要輸出行號、方括號、解釋或任何額外內容。
行數必須與輸入完全一致。
"""


def _reconcile_lines(raw_lines: List[str], expected: int) -> Optional[List[str]]:
    """Try to reconcile LLM output to the expected line count.

    Returns *None* when reconciliation is impossible.
    """
    # 1) Drop completely empty lines
    cleaned = [l for l in raw_lines if l.strip()]
    if len(cleaned) == expected:
        return [l.strip() for l in cleaned]

    # 2) Remove lines that look like headers / notes from the LLM
    filtered = [
        l for l in cleaned
        if not l.strip().startswith("【")
        and not l.strip().startswith("---")
        and not l.strip().startswith("以上")
        and not l.strip().startswith("注：")
        and not l.strip().startswith("備註")
    ]
    if len(filtered) == expected:
        return [l.strip() for l in filtered]

    # 3) Strip leading line numbers / bracketed numbers the LLM may have added
    #    e.g. "1. ", "1: ", "1、", "[1] ", "(1) "
    import re
    stripped_nums = []
    for l in cleaned:
        m = re.match(r"^(?:\[?\d+\]?[\.\:、\)\s])\s*", l)
        stripped_nums.append(l[m.end():] if m else l)
    # Re-filter empty after stripping
    stripped_nums = [l for l in stripped_nums if l.strip()]
    if len(stripped_nums) == expected:
        return [l.strip() for l in stripped_nums]

    # 4) If only 1–2 extra lines, take the first N lines
    if len(cleaned) > expected and (len(cleaned) - expected) <= 3:
        return [l.strip() for l in cleaned[:expected]]

    return None


def _call_llm(
    client: Any,
    model: str,
    lines: List[str],
    content_hint: Optional[str] = None,
    system_prompt: Optional[str] = None,
    numbered: bool = False,
    prev_context: Optional[List[str]] = None,
    next_context: Optional[List[str]] = None,
) -> List[str]:
    """Call the LLM with retry logic. Raises on persistent failure."""
    user_msg = _build_user_message(
        lines, content_hint, numbered=numbered,
        prev_context=prev_context, next_context=next_context,
    )
    messages = [
        {"role": "system", "content": system_prompt or _SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]
    expected = len(lines)

    last_exc: Optional[Exception] = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.3,
            )
            raw = response.choices[0].message.content or ""
            result_lines = raw.strip().split("\n")

            # Fast path: exact match
            if len(result_lines) == expected:
                return [l.strip() for l in result_lines]

            # Slow path: try to reconcile
            reconciled = _reconcile_lines(result_lines, expected)
            if reconciled is not None:
                logger.info(
                    "LLM returned %d raw lines, reconciled to %d",
                    len(result_lines), expected,
                )
                return reconciled

            # If this is the last attempt, accept partial result rather than
            # discarding all enhancements.
            if attempt == _MAX_RETRIES - 1:
                logger.warning(
                    "LLM returned %d lines but expected %d — "
                    "using partial results where possible",
                    len(result_lines), expected,
                )
                cleaned = [l for l in result_lines if l.strip()]
                result = list(lines)
                for i in range(min(len(cleaned), expected)):
                    result[i] = cleaned[i].strip()
                return result

            # Retry with an explicit correction hint
            logger.info(
                "LLM returned %d lines (expected %d) — retrying (attempt %d)",
                len(result_lines), expected, attempt + 1,
            )
            messages = [
                {"role": "system", "content": system_prompt or _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": raw},
                {"role": "user", "content": (
                    f"行數不正確。你輸出了 {len(result_lines)} 行，"
                    f"但應為恰好 {expected} 行。"
                    f"請重新輸出，確保行數完全一致。"
                )},
            ]
            time.sleep(_RETRY_BACKOFF[0])
            continue

        except Exception as exc:
            last_exc = exc
            friendly = _friendly_error(exc)
            if _is_retryable(exc) and attempt < _MAX_RETRIES - 1:
                wait = _RETRY_BACKOFF[attempt] if attempt < len(_RETRY_BACKOFF) else 10
                logger.warning(
                    "LLM request failed (attempt %d/%d): %s — retrying in %ds",
                    attempt + 1, _MAX_RETRIES, friendly, wait,
                )
                time.sleep(wait)
            else:
                raise RuntimeError(friendly) from last_exc

    raise RuntimeError(_friendly_error(last_exc)) from last_exc


_BREAK_PUNCT = set("，。？！：；、?!,;:")
_SENTENCE_PARTICLES = set("呢嗎啊吧呀哦哇啦囉喔嘛咧耶噢")
_ALL_BREAKS = _BREAK_PUNCT | _SENTENCE_PARTICLES

_TARGET_CHARS = 20
_MAX_CHARS = 30
_ORPHAN_THRESHOLD = 12
_TRAILING_STRIP_PUNCT = set("、；;")


def _strip_trailing_punct(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove trailing enumeration / semicolon marks from subtitle text.

    Commas (，,) are preserved — they are natural in subtitle line endings.
    """
    for seg in segments:
        text = seg.get("text", "")
        while text and text[-1] in _TRAILING_STRIP_PUNCT:
            text = text[:-1]
        seg["text"] = text.strip()
    return [s for s in segments if s.get("text")]


def _split_at_punctuation(
    text: str,
    start_time: float,
    end_time: float,
    target_chars: int = _TARGET_CHARS,
    max_chars: int = _MAX_CHARS,
) -> List[Dict[str, Any]]:
    """Split *text* at punctuation boundaries with proportional timestamps."""
    total = len(text)
    if total <= max_chars:
        return [{"start": start_time, "end": end_time, "text": text}]

    duration = end_time - start_time

    pieces: List[str] = []
    pos = 0
    last_punct = -1

    for i, ch in enumerate(text):
        if ch in _ALL_BREAKS:
            last_punct = i + 1
            if last_punct - pos >= target_chars:
                pieces.append(text[pos:last_punct])
                pos = last_punct
                last_punct = -1

        if i + 1 - pos >= max_chars and last_punct > pos:
            pieces.append(text[pos:last_punct])
            pos = last_punct
            last_punct = -1

    if pos < total:
        tail = text[pos:]
        if pieces and len(tail) <= target_chars // 3:
            pieces[-1] += tail
        else:
            pieces.append(tail)

    for j in range(1, len(pieces)):
        while pieces[j] and pieces[j][0] in _ALL_BREAKS:
            pieces[j - 1] += pieces[j][0]
            pieces[j] = pieces[j][1:]

    result: List[Dict[str, Any]] = []
    char_pos = 0
    for piece in pieces:
        stripped = piece.strip()
        if not stripped:
            char_pos += len(piece)
            continue
        t0 = start_time + (char_pos / total) * duration if total else start_time
        char_pos += len(piece)
        t1 = start_time + (char_pos / total) * duration if total else end_time
        result.append({"start": round(t0, 3), "end": round(t1, 3), "text": stripped})

    return result if result else [{"start": start_time, "end": end_time, "text": text}]


def merge_short_segments(
    segments: List[Dict[str, Any]],
    target_chars: int = _TARGET_CHARS,
    max_chars: int = _MAX_CHARS,
    **_kwargs,
) -> List[Dict[str, Any]]:
    """
    Fix unnatural ASR breaks in two steps:

    Step 1 — Orphan merge: merge short continuation segments
             (≤ 3 chars unconditionally, ≤ 12 chars when previous
             doesn't end with punctuation) into the previous segment.

    Step 2 — Resplit: any segment exceeding *max_chars* is split
             at the nearest punctuation mark, targeting *target_chars*
             per line. Timestamps are distributed proportionally.
    """
    if not segments or len(segments) <= 1:
        return list(segments)

    # --- Step 1: orphan merge ---
    merged: List[Dict[str, Any]] = [dict(segments[0])]

    for seg in segments[1:]:
        prev = merged[-1]
        prev_text = prev.get("text", "").rstrip()
        curr_text = seg.get("text", "").strip()

        if not curr_text:
            continue

        last_char = prev_text[-1] if prev_text else ""
        is_break = last_char in _ALL_BREAKS

        force = len(curr_text) <= 3 and prev_text
        orphan = (
            len(curr_text) <= _ORPHAN_THRESHOLD
            and prev_text
            and not is_break
        )
        mid_sentence = (
            not is_break
            and prev_text
            and len(prev_text) + len(curr_text) <= max_chars * 2
        )

        if force or orphan or mid_sentence:
            merged[-1] = {
                **prev,
                "text": prev_text + curr_text,
                "end": seg.get("end", prev.get("end")),
            }
            if "words" in prev and "words" in seg:
                merged[-1]["words"] = (prev.get("words") or []) + (
                    seg.get("words") or []
                )
        else:
            merged.append(dict(seg))

    # --- Step 2: resplit long segments ---
    return resplit_long_segments(merged, target_chars, max_chars)


def resplit_long_segments(
    segments: List[Dict[str, Any]],
    target_chars: int = _TARGET_CHARS,
    max_chars: int = _MAX_CHARS,
) -> List[Dict[str, Any]]:
    """Split any segment exceeding *max_chars* at punctuation marks."""
    result: List[Dict[str, Any]] = []
    for seg in segments:
        text = seg.get("text", "").strip()
        if not text:
            continue
        if len(text) <= max_chars:
            result.append(dict(seg))
        else:
            start = seg.get("start", 0.0)
            end = seg.get("end", start)
            result.extend(
                _split_at_punctuation(text, start, end, target_chars, max_chars)
            )

    result = _strip_trailing_punct(result)
    for i, s in enumerate(result):
        s["id"] = i
    return result


def _chunk_lines(
    lines: List[str],
    max_lines: int = _MAX_LINES_PER_BATCH,
    max_chars: int = _MAX_CHARS_PER_BATCH,
) -> List[List[int]]:
    """Split line indices into chunks respecting both line count and char count."""
    chunks: List[List[int]] = []
    current_chunk: List[int] = []
    current_size = 0

    for i, line in enumerate(lines):
        line_size = len(line) + 1
        if current_chunk and (
            len(current_chunk) >= max_lines or current_size + line_size > max_chars
        ):
            chunks.append(current_chunk)
            current_chunk = []
            current_size = 0
        current_chunk.append(i)
        current_size += line_size

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def enhance_subtitles(
    segments: List[Dict[str, Any]],
    *,
    api_key: str,
    base_url: str = "https://api.openai.com/v1",
    model: str = "gpt-4o-mini",
    content_hint: Optional[str] = None,
    status_callback: Optional[Callable] = None,
) -> List[Dict[str, Any]]:
    """
    Use an OpenAI-compatible LLM to polish subtitle text.
    Returns segments with corrected text. On any error, returns originals.
    """
    try:
        from openai import OpenAI
    except ImportError:
        logger.error("openai package not installed — skipping LLM enhancement")
        return segments

    if not api_key:
        logger.warning("No LLM API key provided — skipping enhancement")
        return segments

    lines = [seg.get("text", "") for seg in segments]
    if not lines:
        return segments

    if status_callback:
        status_callback("正在使用 AI 增強字幕品質...", progress=92.0)

    base_url = base_url.rstrip("/")
    client = OpenAI(api_key=api_key, base_url=_rewrite_localhost_url(base_url))

    chunks = _chunk_lines(lines)
    corrected = [""] * len(lines)

    total_chunks = len(chunks)
    try:
        for chunk_idx, indices in enumerate(chunks):
            chunk_lines = [lines[i] for i in indices]

            if status_callback:
                pct = 92.0 + (chunk_idx / total_chunks) * 6.0
                status_callback(
                    f"AI 校對中 ({chunk_idx + 1}/{total_chunks})...",
                    progress=pct,
                )

            if chunk_idx > 0:
                time.sleep(_BATCH_COOLDOWN)

            prev_ctx = None
            next_ctx = None
            if total_chunks > 1:
                if chunk_idx > 0:
                    prev_indices = chunks[chunk_idx - 1]
                    prev_ctx = [lines[i] for i in prev_indices[-_CONTEXT_OVERLAP:]]
                if chunk_idx < total_chunks - 1:
                    next_indices = chunks[chunk_idx + 1]
                    next_ctx = [lines[i] for i in next_indices[:_CONTEXT_OVERLAP]]

            result = _call_llm(
                client, model, chunk_lines, content_hint,
                prev_context=prev_ctx, next_context=next_ctx,
            )
            for j, idx in enumerate(indices):
                corrected[idx] = result[j]

    except Exception as exc:
        logger.exception("LLM enhancement failed — returning original text")
        if status_callback:
            status_callback(f"AI 增強失敗: {exc}", progress=98.0)
        raise

    enhanced = []
    for i, seg in enumerate(segments):
        new_seg = dict(seg)
        new_seg["text"] = corrected[i] if corrected[i] else seg.get("text", "")
        enhanced.append(new_seg)

    if status_callback:
        status_callback("AI 字幕增強完成", progress=98.0)

    return enhanced


def _parse_chapter_time(value: object) -> float:
    """Convert "MM:SS", "HH:MM:SS", or numeric seconds to float seconds."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        parts = value.strip().split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + float(parts[1])
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        except (ValueError, IndexError):
            pass
    return 0.0


_SUMMARIZE_SYSTEM_PROMPT = """\
你是一位影片內容分析師。請根據以下字幕逐字稿，完成兩件事：

1. 撰寫一段 2-4 句的內容摘要，描述影片主題與重點。
2. 找出 3-8 個主要話題的切換點，輸出帶時間戳的章節列表。

重要規則：
- 使用與字幕相同的語言回答。
- 只輸出合法的 JSON，不要加入任何 Markdown 或解釋文字。
- 格式必須完全符合：\
{"summary": "...", "chapters": [{"time": "MM:SS", "title": "..."}, ...]}
- time 必須直接複製字幕中的時間戳（例如 "04:42"、"12:30"），\
不要換算、不要猜測，只能使用字幕開頭出現過的時間戳。
"""


def summarize_subtitles(
    segments: List[Dict[str, Any]],
    *,
    api_key: str,
    base_url: str = "https://api.openai.com/v1",
    model: str = "gpt-4o-mini",
    content_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Summarize a transcript and produce timestamped chapters via LLM.

    Returns:
        {"summary": str, "chapters": [{"time": float, "title": str}]}
    On non-JSON response, returns {"summary": <raw text>, "chapters": []}.
    Raises RuntimeError on API error.
    """
    try:
        from openai import OpenAI
    except ImportError:
        logger.error("openai package not installed — cannot summarize")
        return {"summary": "", "chapters": []}

    if not segments:
        return {"summary": "", "chapters": []}

    lines = []
    for seg in segments:
        t = seg.get("start", 0.0)
        m, s = divmod(int(t), 60)
        h, m = divmod(m, 60)
        ts = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        lines.append(f"[{ts}] {seg.get('text', '').strip()}")

    user_content = "\n".join(lines)
    if content_hint:
        user_content = f"【內容描述】{content_hint}\n\n{user_content}"

    client = OpenAI(
        api_key=api_key,
        base_url=_rewrite_localhost_url(base_url.rstrip("/")),
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SUMMARIZE_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
        )
        raw = (response.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
            if raw.endswith("```"):
                raw = raw[:-3].rstrip()
        data = json.loads(raw)
        return {
            "summary": str(data.get("summary", "")),
            "chapters": [
                {
                    "time": _parse_chapter_time(c.get("time", 0)),
                    "title": str(c.get("title", "")),
                }
                for c in data.get("chapters", [])
                if isinstance(c, dict)
            ],
        }
    except json.JSONDecodeError:
        logger.warning(
            "summarize_subtitles: LLM returned non-JSON, using raw text"
        )
        return {"summary": raw, "chapters": []}
    except Exception as exc:
        logger.error(
            "summarize_subtitles failed: %s", exc, exc_info=True
        )
        raise RuntimeError(_friendly_error(exc)) from exc
