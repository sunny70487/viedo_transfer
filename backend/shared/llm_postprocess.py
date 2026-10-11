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
from collections import deque
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


_ZH_TW_TERMS = (
    ("反匯編", "反組譯"), ("匯編語言", "組合語言"), ("匯編", "組譯"),
    ("動態鏈接庫", "動態連結庫"), ("動態鏈接", "動態連結"),
    ("軟件", "軟體"), ("硬件", "硬體"), ("固件", "韌體"),
    ("代碼", "程式碼"), ("源碼", "原始碼"),
    ("寄存器", "暫存器"), ("線程", "執行緒"), ("進程", "行程"),
    ("內存", "記憶體"), ("內核", "核心"),
    ("地址", "位址"), ("加載", "載入"), ("默認", "預設"),
    ("信息", "資訊"), ("數據", "資料"), ("鼠標", "滑鼠"),
    ("計算機", "電腦"), ("響應", "回應"), ("篡改", "竄改"),
    ("報文", "封包"), ("字體", "字型"), ("接口", "介面"),
    ("對象", "物件"), ("文件", "檔案"), ("調用", "呼叫"),
    ("幹掉", "擊敗"), ("屏幕", "螢幕"), ("緩存", "快取"),
    ("隊列", "佇列"), ("數組", "陣列"), ("指針", "指標"),
)


def _to_zh_tw_terms(text: str) -> str:
    for cn, tw in _ZH_TW_TERMS:
        if cn != tw:
            text = text.replace(cn, tw)
    return text


# Distilled from .opencode/skills/note-crafter/ — keep in sync when the skill changes.
_NOTES_SYSTEM_PROMPT = """\
你是一位擅長把口語課程轉錄整理成教學筆記的老師。請根據字幕逐字稿，產出一份\
結構清晰、圖文並茂的繁體中文 Markdown 教學筆記。

## 核心原則
口語轉錄是「原料」不是「成品」。字幕充滿口頭禪、跳躍、重複；你要**重寫成書面\
教材的脈絡**，按「理解順序」重新編排，而不是逐句照抄潤飾。

## 結構（用 Markdown 標題分層）
1. 一級標題 `#` 是主題名稱。
2. 開頭 1~2 句破題：從一個日常現象或謎題切入，說明為什麼要懂這個。
3. 每個核心概念用 `##`，必要時 `###` 分子概念。
4. 結尾要有「## 實際應用場景」（1~3 個真實情境）與「## 小結」（條列回顧 3~5 個觀念）。

### 標題命名（重要）
用「概念名：副標」的描述式命名，**不要**用「一、二、三」中文數字編號。
- 好：`## CPU 的語言：指令格式與基礎`、`## 程式的暫存區：堆疊 (Stack)`
- 壞：`## 一、什麼是 Hook`、`## 二、常見類型`

## 每個概念都走「三拍」
1. **比喻建立直覺**：先給一個具體、有畫面的生活化比喻（例如碼頭工人抓貨櫃、\
餐廳菜單、圖書館食譜）。一個概念一個比喻就好，湊不上就直接講白話，別硬湊。
2. **精確化**：比喻之後**立刻**接上精確版本 —— 用 Markdown 表格、程式碼區塊、\
或圖，避免只有比喻沒有乾貨。
3. **驗證/落地**：用範例或步驟把概念釘死。

## 產出的硬性配額（不得省略）
這幾項是筆記合格的最低標準，必須全部達成：
- **每個 `##` 章節至少一個比喻或一句有畫面的類比。** 越抽象的概念越要有。
- **全篇至少 2 個 Mermaid 流程圖或 ASCII 示意圖。** 只要涉及「呼叫鏈」「逐層\
搜尋」「前後位址變化」「記憶體佈局」，就必須畫出來，不能只用文字描述。
- **全篇至少 1 張對照表**，用來比較同類事物的差異與取捨（例如各種做法的\
層級、難度、適用場景）。讀者要能靠這張表決定「什麼情況該用哪一個」。
- **必須有「## 實際應用場景」章節**，並寫出可操作的步驟（用什麼工具、看什麼、\
什麼結果代表什麼）。
- **不要整篇都是 `- ` 條列。** 散文說明與條列交錯：先用一兩段白話把來龍去脈\
講通，再用條列收攏重點。條列只放結論，不要拿條列當解釋。

## 用文字圖表取代圖片（重要）
- **絕對不要**輸出 `![](image.png)` 這類圖片語法。
- 需要流程圖/關係圖時用 Mermaid（```mermaid 區塊）。
- 需要記憶體佈局/堆疊/位址示意時用 ASCII 圖（放在 ``` 區塊）。
- 對比、規則、指令一律用 Markdown 表格。
- 程式碼/組語/結構體用 fenced code block，並加行內註解說明「為什麼」。
- 技術名詞首次出現給中英對照，例如「記憶體對齊 (Memory Alignment)」。

## 重點概念動畫標記
挑 2~4 個最抽象、最需要「看它動起來」才好懂的概念（例如流程、狀態變化、\
資料流動），在該概念解說段落的最後插入一個標記區塊，系統會據此另外繪製動畫：

```concept-anim
{"id": "tcp-handshake", "title": "TCP 三向交握", "brief": "三個封包依序來回飛行"}
```

- `id` 只能用小寫英文、數字、連字號，最多 32 字，全篇不可重複。
- `title` 是概念名稱；`brief` 用 1~3 句描述畫面裡有哪些元素、怎麼動。
- 標記區塊只放這一行 JSON。它**不取代** Mermaid / ASCII 圖的配額。

## 用語：一律台灣繁體中文技術用語（不得使用大陸用語）
即使逐字稿講的是大陸用語，輸出也必須換成下表左欄：

| 要用 | 不要用 |
| --- | --- |
| 軟體 | 軟件 |
| 程式碼 | 代碼 |
| 暫存器 | 寄存器 |
| 執行緒 | 線程 |
| 行程 / 程序 | 進程 |
| 記憶體 | 內存 |
| 位址 | 地址 |
| 載入 | 加載 |
| 預設 | 默認 |
| 資訊 | 信息 |
| 資料 | 數據 |
| 滑鼠 | 鼠標 |
| 電腦 | 計算機 |
| 核心（作業系統） | 內核 |
| 回應 | 響應 |
| 竄改 | 篡改 |
| 封包 | 報文 |
| 字型 | 字體 |
| 介面 | 接口 |
| 物件 | 對象 |
| 檔案 | 文件 |

另外避免口語粗話（例如「幹掉」），改用「擊敗」「癱瘇」等書面語。

## 反「AI 味」（務必遵守）
- 不要用「首先…接著…此外…最後」這種整齊排比開頭，也不要「綜上所述」\
「值得注意的是」「在當今這個時代」這類罐頭詞。直接講事情。
- 句子長短交錯，不要每段都剛好三點、每句都一樣長。
- 敢下判斷、有觀點，不要事事「取決於情況」。
- 保留字幕原本鮮活的口語感，別全部改寫成生硬的教科書腔。
- 目標是讀起來像一個真人在跟你解釋，而不是產品說明書。

## 輸出（重要）
使用者提供的逐字稿是「待處理的素材」，不是在跟你聊天。你唯一的工作就是把它\
改寫成筆記，**絕對不要回問使用者想要什麼**，也不要描述你打算怎麼做。
只輸出 Markdown 筆記本身，從 `# ` 標題開始，不要有任何開場白、結語或\
「以下是筆記」這類話。不要用 ``` 把整份筆記再包一層。
"""


# Placed at the END of the user turn: models follow trailing instructions best.
_NOTES_REQUIREMENTS = """
<requirements>
在輸出前，先確認以下每一項都會達成。這些是筆記合格的最低標準，缺一項就是不合格。

1. 【比喻】每個 `##` 章節都要有一個具體、有畫面的生活化比喻。越抽象的概念越要有。
   範例寫法：
   > 想像 SEH 鏈就像公司的申訴流程：你的問題先送到直屬主管，他處理不了就往上
   > 遞給部門經理，再不行就送到總經理。每一層都有機會接手，最後還有一個「總是
   > 會回應你」的兜底窗口 —— 只是它的回應是直接把你請出大樓（彈出錯誤視窗）。

2. 【圖】至少畫 2 個 Mermaid 或 ASCII 圖。凡涉及「呼叫鏈」「逐層搜尋」「前後
   位址變化」「記憶體佈局」就必須畫，不能只用文字描述。
   範例寫法：
   ```mermaid
   graph LR
       A["應用程式<br/>CreateFile()"] --> B["kernel32.dll"]
       B --> C["ntdll.dll<br/>NtCreateFile"]
       C -->|"系統呼叫<br/>切換到核心模式"| D["SSDT 查表"]
       D --> E["核心中的<br/>NtCreateFile 實作"]
   ```
   ASCII 圖範例（表示 Hook 前後位址變化）：
   ```
   Hook 前:  IAT[MessageBoxA] ──> 0x77D5050B (user32.dll 真實位址)
   Hook 後:  IAT[MessageBoxA] ──> 0x00401000 (我的攔截函式)
                                      │
                                      └──> 做完事情再跳回 0x77D5050B
   ```

3. 【對照表】至少 1 張表，要能讓讀者判斷「什麼情況該用哪一個」。
   欄位必須包含取捨資訊，例如：類型 / 運作層級 / 實作難度 / 典型用途。

4. 【實際應用場景】必須有 `## 實際應用場景` 章節，寫出可操作步驟：
   用什麼工具、看哪裡、什麼結果代表什麼。

5. 【不要整篇條列】散文與條列交錯。先用一兩段白話把來龍去脈講通，再用條列
   收攏重點。條列只放結論，不要拿條列當解釋。

6. 【標題】用「概念名：副標」的描述式命名，不要用「一、二、三」數字編號。

7. 【概念動畫】挑 2~4 個最抽象的概念，在解說段落後各插入一個
   ```concept-anim 區塊（單行 JSON，含 id / title / brief）。id 用小寫英文與連字號。

現在直接輸出 Markdown 筆記本身，從 `# ` 標題開始。
不要回問我問題、不要說明你要做什麼、不要有任何開場白或結語、不要輸出這份清單。
</requirements>"""


def generate_notes(
    segments: List[Dict[str, Any]],
    *,
    api_key: str,
    base_url: str = "https://api.openai.com/v1",
    model: str = "gpt-4o-mini",
    content_hint: Optional[str] = None,
):
    """
    Turn a transcript into an illustrated Markdown study note (note-crafter
    style) and *stream* the result. Yields text chunks as they arrive.

    Raises RuntimeError on API/setup error.
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai 套件未安裝，無法產生筆記")

    if not api_key:
        raise RuntimeError("未提供 LLM API Key")
    if not segments:
        raise RuntimeError("目前沒有字幕資料")

    lines = []
    for seg in segments:
        t = seg.get("start", 0.0)
        m, s = divmod(int(t), 60)
        h, m = divmod(m, 60)
        ts = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        text = seg.get("text", "").strip()
        if text:
            lines.append(f"[{ts}] {text}")

    transcript = "\n".join(lines)
    hint_block = f"\n【內容描述】{content_hint}\n" if content_hint else ""
    user_content = (
        "請把下面 <transcript> 裡的課程逐字稿，改寫成一份繁體中文 Markdown 教學筆記。"
        f"{hint_block}\n"
        f"<transcript>\n{transcript}\n</transcript>\n"
        f"{_NOTES_REQUIREMENTS}"
    )

    client = OpenAI(
        api_key=api_key,
        base_url=_rewrite_localhost_url(base_url.rstrip("/")),
    )

    try:
        stream = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _NOTES_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.6,
            stream=True,
        )
        # Hold back the tail so term replacement still works when a word is
        # split across two chunks (e.g. "寄" then "存器").
        pending = ""
        max_term = max(len(cn) for cn, _ in _ZH_TW_TERMS)
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            piece = getattr(delta, "content", None)
            if not piece:
                continue
            pending += piece
            if len(pending) > max_term:
                emit, pending = pending[:-max_term], pending[-max_term:]
                yield _to_zh_tw_terms(emit)
        if pending:
            yield _to_zh_tw_terms(pending)
    except Exception as exc:
        logger.error("generate_notes failed: %s", exc, exc_info=True)
        raise RuntimeError(_friendly_error(exc)) from exc


_MINDMAP_MAX_DEPTH = 4
_MINDMAP_MAX_NODES = 60
_MINDMAP_FORMAT_ERROR = "心智圖格式錯誤，請重試"

_MINDMAP_SYSTEM_PROMPT = """\
你是一位課程內容架構師。請根據字幕逐字稿，整理出一份心智圖。

規則：
- 根節點是整份內容的主題；第二層是 3~7 個主要概念；往下最多再兩層。
- 總節點數不超過 50 個。每個節點標題 2~16 字，是名詞片語，不是句子。
- 每個節點附上該概念「第一次被講到」的時間，直接複製字幕開頭的時間戳\
（例如 "04:42"），不要換算或猜測。
- 一律使用台灣繁體中文技術用語。
- 只輸出合法 JSON，不要 Markdown、不要解釋。格式：
{"root": {"title": "...", "time": "MM:SS", "children": [\
{"title": "...", "time": "MM:SS", "children": []}]}}
"""


def _format_transcript(segments: List[Dict[str, Any]]) -> str:
    lines = []
    for seg in segments:
        m, s = divmod(int(seg.get("start", 0.0)), 60)
        h, m = divmod(m, 60)
        ts = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        text = seg.get("text", "").strip()
        if text:
            lines.append(f"[{ts}] {text}")
    return "\n".join(lines)


def _strip_code_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:])
        if raw.rstrip().endswith("```"):
            raw = raw.rstrip()[:-3]
    return raw.strip()


def _normalize_mindmap(raw_root: Dict[str, Any]) -> Dict[str, Any]:
    """Clean titles/times and enforce depth and node-count limits (BFS)."""
    def make(raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "title": _to_zh_tw_terms(str(raw.get("title", "")).strip()),
            "time": _parse_chapter_time(raw.get("time", 0)),
            "children": [],
        }

    root = make(raw_root)
    if not root["title"]:
        raise RuntimeError(_MINDMAP_FORMAT_ERROR)

    count = 1
    queue = deque([(raw_root, root, 1)])
    while queue:
        raw, node, depth = queue.popleft()
        raw_children = raw.get("children")
        if depth >= _MINDMAP_MAX_DEPTH or not isinstance(raw_children, list):
            continue
        for raw_child in raw_children:
            if count >= _MINDMAP_MAX_NODES:
                return root
            if not isinstance(raw_child, dict):
                continue
            child = make(raw_child)
            if not child["title"]:
                continue
            node["children"].append(child)
            count += 1
            queue.append((raw_child, child, depth + 1))
    return root


def generate_mindmap(
    segments: List[Dict[str, Any]],
    *,
    api_key: str,
    base_url: str = "https://api.openai.com/v1",
    model: str = "gpt-4o-mini",
    content_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build a timestamped mind map from a transcript via LLM.

    Returns {"root": {"title": str, "time": float, "children": [...]}}.
    Raises RuntimeError on empty input, API error, or malformed output.
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai 套件未安裝，無法產生心智圖")

    if not segments:
        raise RuntimeError("目前沒有字幕資料")

    user_content = _format_transcript(segments)
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
                {"role": "system", "content": _MINDMAP_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
        )
        raw = response.choices[0].message.content or ""
    except Exception as exc:
        logger.error("generate_mindmap failed: %s", exc, exc_info=True)
        raise RuntimeError(_friendly_error(exc)) from exc

    try:
        data = json.loads(_strip_code_fence(raw))
    except json.JSONDecodeError:
        raise RuntimeError(_MINDMAP_FORMAT_ERROR)
    if not isinstance(data, dict) or not isinstance(data.get("root"), dict):
        raise RuntimeError(_MINDMAP_FORMAT_ERROR)
    return {"root": _normalize_mindmap(data["root"])}


_CONCEPT_SVG_RULES = """\
你是 3Blue1Brown 風格的教學動畫設計師。請為指定的概念畫一張「會動的」SVG 說明圖。

硬性規格：
- 只輸出一個 <svg> 元素，從 <svg 開始、到 </svg> 結束，前後不要任何文字或 Markdown。
- 根元素必須是 <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 450">。
- 第一個子元素是深色背景 <rect width="800" height="450" fill="#0f172a"/>。
- 動畫只能用內嵌 <style> 裡的 CSS @keyframes 與 animation，全部 infinite。
- 文字用繁體中文（台灣用語），font-family 用 sans-serif，每行不超過 14 字，\
字級至少 18。
- 禁止：<script>、<foreignObject>、<image>、<iframe>、任何 on* 事件屬性、\
任何外部網址或 @import。內部引用只能用 #id。

視覺風格（必須遵守）：
- 調色盤：主要物件 #38bdf8（藍）、重點 #fbbf24（黃）、變化或指標 #f472b6（粉）、\
文字 #e2e8f0、註解 #94a3b8。不要用其他顏色，不要漸層。
- 形狀只畫外框：fill="none"，stroke-width 2~3，圓角 rx 4~8。
- 線條要「被畫出來」：設定 stroke-dasharray 與 stroke-dashoffset 等於路徑長度，\
再用動畫把 stroke-dashoffset 降到 0。
- 文字以「往上浮 8px＋淡入」出現。
- 移動、縮放一律用 cubic-bezier(.65,0,.35,1) 或 cubic-bezier(.22,1,.36,1)。

動畫節奏（必須遵守）：
- 一輪 8~12 秒，所有動畫用同一個週期長度，用 animation-delay 讓元素依序出現。
- 每輪分三段：依序畫出 → 全部停留讓人看清楚 → 一起淡出後重來。
- 禁止彈跳、搖晃、閃爍、旋轉、等速 linear 移動、steps()。
- 一張圖只講一個重點，最多 6 個主要元素，留白要足。

參考範例（概念：函式呼叫時 stack 壓入新的 frame）：
{example}
請照這個範例的手法與節奏，為下面的概念設計全新的畫面，不要照抄範例內容。
"""

_CONCEPT_SVG_EXAMPLE = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 450">
<style>
.draw{stroke-dasharray:540;stroke-dashoffset:540;
animation:draw 10s cubic-bezier(.65,0,.35,1) infinite}
.fade{opacity:0;animation:fade 10s cubic-bezier(.22,1,.36,1) infinite}
.d1{animation-delay:.8s}.d2{animation-delay:1.6s}.d3{animation-delay:2.6s}
.sp{animation:sp 10s cubic-bezier(.65,0,.35,1) infinite}
@keyframes draw{0%{stroke-dashoffset:540}20%,85%{stroke-dashoffset:0;opacity:1}
100%{stroke-dashoffset:0;opacity:0}}
@keyframes fade{0%{opacity:0;transform:translateY(8px)}
12%,85%{opacity:1;transform:none}100%{opacity:0}}
@keyframes sp{0%,35%{transform:none}50%,85%{transform:translateY(-80px);opacity:1}
100%{transform:translateY(-80px);opacity:0}}
</style>
<rect width="800" height="450" fill="#0f172a"/>
<text x="60" y="70" font-family="sans-serif" font-size="26" fill="#e2e8f0"
 class="fade">呼叫 foo() 時發生什麼事</text>
<rect x="300" y="300" width="200" height="70" rx="6" fill="none"
 stroke="#38bdf8" stroke-width="2.5" class="draw"/>
<text x="400" y="342" text-anchor="middle" font-family="sans-serif"
 font-size="22" fill="#e2e8f0" class="fade d1">main()</text>
<rect x="300" y="220" width="200" height="70" rx="6" fill="none"
 stroke="#fbbf24" stroke-width="2.5" class="draw d1"/>
<text x="400" y="262" text-anchor="middle" font-family="sans-serif"
 font-size="22" fill="#fbbf24" class="fade d2">foo() 的 frame</text>
<g class="sp"><line x1="230" y1="300" x2="290" y2="300" stroke="#f472b6"
 stroke-width="2.5"/><text x="150" y="307" font-family="sans-serif"
 font-size="20" fill="#f472b6">SP</text></g>
<text x="540" y="262" font-family="sans-serif" font-size="18" fill="#94a3b8"
 class="fade d3">放區域變數、返回位址</text>
</svg>"""

_CONCEPT_SVG_SYSTEM_PROMPT = _CONCEPT_SVG_RULES.format(
    example=_CONCEPT_SVG_EXAMPLE
)

_SVG_BLOCK_RE = re.compile(r"<svg\b[\s\S]*</svg>", re.IGNORECASE)


def generate_concept_svg(
    *,
    title: str,
    brief: str,
    content_hint: Optional[str] = None,
    api_key: str,
    base_url: str = "https://api.openai.com/v1",
    model: str = "gpt-4o-mini",
) -> str:
    """
    Ask the LLM for a CSS-animated SVG explaining one concept.

    Returns a sanitized SVG string. Raises RuntimeError on API error,
    missing SVG, or unsafe/malformed SVG.
    """
    from backend.shared.svg_sanitizer import sanitize_svg

    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai 套件未安裝，無法產生動畫")

    hint = f"\n課程背景：{content_hint}" if content_hint else ""
    user_content = f"概念：{title}\n畫面描述：{brief}{hint}"

    client = OpenAI(
        api_key=api_key,
        base_url=_rewrite_localhost_url(base_url.rstrip("/")),
    )
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _CONCEPT_SVG_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.7,
        )
        raw = response.choices[0].message.content or ""
    except Exception as exc:
        logger.error("generate_concept_svg failed: %s", exc, exc_info=True)
        raise RuntimeError(_friendly_error(exc)) from exc

    match = _SVG_BLOCK_RE.search(raw)
    if not match:
        raise RuntimeError("SVG 生成失敗，請重試")
    try:
        return sanitize_svg(match.group(0))
    except ValueError as exc:
        logger.warning("Rejected generated SVG: %s", exc)
        raise RuntimeError("SVG 內容不安全或格式錯誤，請重畫") from exc


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
