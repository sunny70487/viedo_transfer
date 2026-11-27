"""
Rule-based subtitle segmentation from word-level timestamps.

Lines are chosen by dynamic programming over candidate break points, so the
whole run is optimised at once instead of greedily cutting at the first pause.
Break quality is scored from (in priority order) ASR punctuation, speech
pauses and Chinese word boundaries (jieba). Lines never cut through a word
and avoid dangling function words such as 「的」「把」.
"""

import logging
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

logger = logging.getLogger("subtitle_segmentation")

try:
    import jieba
    import jieba.posseg as jieba_posseg

    jieba.setLogLevel(logging.WARNING)
    JIEBA_AVAILABLE = True
except ImportError:
    jieba = None
    jieba_posseg = None
    JIEBA_AVAILABLE = False

try:
    from opencc import OpenCC

    _T2S_CONVERTER = OpenCC("t2s")
except ImportError:
    _T2S_CONVERTER = None

_SENTENCE_END = set("。？！?!…")
_CLAUSE_END = set("，,、；;：:—–）)」』】》")
_TRAILING_STRIP = set("，,。.、；;：:—–")

# jieba POS prefixes that need a continuation: adverb, preposition,
# conjunction, auxiliary/particle (的 地 得 着 了 过 is "u").
_DANGLING_POS = ("d", "p", "c", "u")
_CONNECTORS = (
    "然后", "然後", "或者", "但是", "可是", "不过", "不過", "所以", "因为", "因為",
    "如果", "而且", "并且", "並且", "而是", "那么", "那麼", "接下来", "接下來",
    "比如", "例如", "也就是", "从而", "從而", "否则", "否則", "同时", "同時",
)
_FINAL_PARTICLES = {"了", "过", "過", "等等", "的话", "的話", "似的"}
_A_NOT_A = ("有没有", "有沒有", "是不是", "能不能", "会不会", "會不會",
            "要不要", "对不对", "對不對", "可不可以")

_BAD_LINE_END = set("的地得和跟與与及或把被將将在對对從从向給给為为是而之")
_BAD_LINE_START = set("的地得了著着過过們们嗎吗呢吧啊")
_BAD_LINE_END_WORDS = (
    "這個", "这个", "那個", "那个", "一個", "一个", "一些", "這些", "这些",
    "如何", "這樣", "这样", "一種", "一种", "因為", "因为", "所以", "如果",
    "然後", "然后", "就是", "還是", "还是", "需要", "可以", "通過", "通过",
)

_LONG_GAP = 0.3
_INF = float("inf")


def is_word_char(ch: str) -> bool:
    """True for letters, digits and apostrophes (everything else is punctuation)."""
    if ch == "'":
        return True
    cat = unicodedata.category(ch)
    return cat.startswith("L") or cat.startswith("N")


def _is_latin_or_digit(ch: str) -> bool:
    return ch.isascii() and ch.isalnum()


def _display_width(text: str) -> float:
    """Line length in full-width units: ASCII counts as half a CJK character."""
    return sum(0.5 if ch.isascii() else 1.0 for ch in text)


def attach_punctuation(
    words: List[Dict[str, Any]], text: str
) -> List[Dict[str, Any]]:
    """Re-attach punctuation from the ASR *text* onto the aligned *words*.

    Forced aligners drop punctuation from their tokens; this walks the
    original text and appends each run of punctuation to the preceding word
    (plus a trailing space when the source had one). Words that cannot be
    located are left unchanged. Returns new dicts; the input is not mutated.
    """
    result: List[Dict[str, Any]] = []
    pos = 0
    for w in words:
        new_w = dict(w)
        core = w.get("word", "")
        idx = text.find(core, pos, pos + len(core) + 20) if core else -1
        if idx >= 0:
            end = idx + len(core)
            j = end
            while j < len(text) and not is_word_char(text[j]):
                j += 1
            trailing = text[end:j]
            punct = "".join(ch for ch in trailing if not ch.isspace())
            has_space = any(ch.isspace() for ch in trailing)
            spelled = len(core) == 1 and core.isupper() and not punct
            space = " " if has_space and not spelled else ""
            new_w["word"] = core + punct + space
            pos = j
        result.append(new_w)
    return result


def _needs_space(prev: str, curr: str) -> bool:
    """Space between Latin/digit tokens, except spelled-out letters (C T F → CTF)."""
    if not (prev and curr):
        return False
    if not (_is_latin_or_digit(prev[-1]) and _is_latin_or_digit(curr[0])):
        return False
    spelled = len(prev) == 1 and len(curr) == 1 and prev.isupper() and curr.isupper()
    return not spelled


def join_tokens(tokens: Iterable[str]) -> str:
    """Concatenate tokens, inserting a space between adjacent Latin/digit words."""
    parts: List[str] = []
    for tok in tokens:
        if not tok:
            continue
        if parts and _needs_space(parts[-1], tok):
            parts.append(" ")
        parts.append(tok)
    return "".join(parts)


def _clean_line(text: str) -> str:
    text = text.strip()
    while text and text[-1] in _TRAILING_STRIP:
        text = text[:-1].rstrip()
    return text


def _core(token: str) -> str:
    """Token without trailing punctuation / whitespace."""
    stripped = token.rstrip()
    while stripped and not is_word_char(stripped[-1]):
        stripped = stripped[:-1]
    return stripped


def _punct_tail(token: str) -> str:
    return token.rstrip()[len(_core(token)):]


def _jieba_probe(text: str) -> str:
    if _T2S_CONVERTER is not None:
        simplified = _T2S_CONVERTER.convert(text)
        if len(simplified) == len(text):
            return simplified
    return text


def word_end_offsets(text: str) -> Optional[Set[int]]:
    """Character offsets in *text* where a jieba word ends (None without jieba)."""
    if not JIEBA_AVAILABLE:
        return None
    ends: Set[int] = set()
    pos = 0
    for tok in jieba.cut(_jieba_probe(text), HMM=True):
        pos += len(tok)
        ends.add(pos)
    return ends


_Tags = Dict[int, Tuple[str, str]]


def word_tags(text: str) -> Tuple[_Tags, _Tags]:
    """(by_end, by_start): jieba (word, POS flag) keyed by end / start offset."""
    by_end: _Tags = {}
    by_start: _Tags = {}
    if not JIEBA_AVAILABLE:
        return by_end, by_start
    pos = 0
    for pair in jieba_posseg.cut(_jieba_probe(text)):
        tok, flag = pair.word, pair.flag
        by_start[pos] = (tok, flag)
        pos += len(tok)
        by_end[pos] = (tok, flag)
    return by_end, by_start


def _is_sentence_end(token: str) -> bool:
    punct = _punct_tail(token)
    if any(ch in _SENTENCE_END for ch in punct):
        return True
    # A Latin full stop only ends a sentence when followed by a space.
    return punct.endswith(".") and token.endswith(" ")


def segment_words(
    words: List[Dict[str, Any]],
    *,
    max_chars: int = 25,
    target_chars: int = 16,
    min_chars: int = 6,
    max_duration: float = 6.0,
    force_break_pause: float = 1.0,
    break_hints: Optional[Dict[int, str]] = None,
) -> List[Dict[str, Any]]:
    """Group *words* into subtitle segments.

    Args:
        words: dicts with ``word``/``start``/``end``; ``word`` may carry
            trailing punctuation (see :func:`attach_punctuation`).
        max_chars / max_duration: hard limits per line (a single word may
            exceed them).
        target_chars / min_chars: preferred line length; shorter lines are
            penalised so orphans merge into neighbours.
        force_break_pause: a silence at least this long always ends a line.
        break_hints: word index → ``"sentence"`` / ``"clause"`` for boundaries
            predicted by a punctuation model. They score like real
            punctuation but are never shown in the text.

    Returns:
        Segment dicts ``{id, start, end, text, confidence, words}``; output
        words have the attached punctuation removed again.
    """
    if not words:
        return []

    tokens = [w.get("word", "") for w in words]
    n = len(tokens)
    hints = break_hints or {}

    # Offset of each token end inside the joined text → word-boundary test.
    token_ends: List[int] = []
    needs_space: List[bool] = []
    length = 0
    for i, tok in enumerate(tokens):
        space = i > 0 and _needs_space(tokens[i - 1], tok)
        needs_space.append(space)
        length += len(tok) + (1 if space else 0)
        token_ends.append(length)
    joined = join_tokens(tokens)
    word_ends = word_end_offsets(joined)
    tags_by_end, tags_by_start = word_tags(joined)

    gaps = [0.0] * n  # gaps[i] = silence after word i
    for i in range(n - 1):
        gaps[i] = max(0.0, words[i + 1]["start"] - words[i]["end"])

    prefix = [0.0]
    for tok in tokens:
        prefix.append(prefix[-1] + _display_width(tok.strip()))
    tail_len = [
        _display_width(_punct_tail(tok))
        if _punct_tail(tok)[-1:] in _TRAILING_STRIP else 0.0
        for tok in tokens
    ]

    def shown_chars(a: int, b: int) -> float:
        """Display width of words a..b (trailing , 。 — are stripped)."""
        return prefix[b + 1] - prefix[a] - tail_len[b]

    def break_allowed(i: int, use_words: bool) -> bool:
        if i == n - 1 or _punct_tail(tokens[i]) or gaps[i] >= force_break_pause:
            return True
        if i in hints:
            return True
        # A glossary term is a word of its own, whatever jieba thinks.
        if words[i].get("glossary") or words[i + 1].get("glossary"):
            return True
        if not use_words or word_ends is None:
            return True
        if tokens[i].endswith(" ") or needs_space[i + 1]:
            return True
        return token_ends[i] in word_ends

    def break_cost(i: int) -> float:
        """Cost of ending a line after word i (i < n - 1)."""
        if _is_sentence_end(tokens[i]):
            cost = 0.0
        elif any(ch in _CLAUSE_END for ch in _punct_tail(tokens[i])):
            cost = 1.0
        elif i in hints:
            # Model-predicted marks are less reliable than ASR punctuation.
            cost = 1.0 if hints[i] == "sentence" else 2.0
        else:
            cost = max(0.5, 8.0 - 10.0 * gaps[i])
            tail = _core(join_tokens(tokens[max(0, i - 1):i + 1]))
            last = tags_by_end.get(token_ends[i])
            if last:
                word, flag = last
                dangling = (
                    flag.startswith(_DANGLING_POS) and word not in _FINAL_PARTICLES
                )
                if (
                    word in _BAD_LINE_END
                    or word.endswith(_BAD_LINE_END_WORDS)
                    or dangling
                ):
                    cost += 10.0
            elif tail[-1:] in _BAD_LINE_END or tail.endswith(_BAD_LINE_END_WORDS):
                cost += 10.0
            if tail.endswith(_A_NOT_A):
                cost += 10.0
            next_start = token_ends[i] + (1 if needs_space[i + 1] else 0)
            nxt_tag = tags_by_start.get(next_start)
            if nxt_tag and nxt_tag[0].startswith(_CONNECTORS):
                cost -= 3.0
        nxt = tokens[i + 1].lstrip()
        if nxt[:1] in _BAD_LINE_START:
            cost += 10.0
        return max(cost, 0.0)

    def line_cost(a: int, b: int) -> float:
        """Cost of a line spanning words a..b inclusive (inf if infeasible)."""
        chars = shown_chars(a, b)
        if a != b and words[b]["end"] - words[a]["start"] > max_duration:
            return _INF
        cost = 2.0 + 0.02 * (target_chars - chars) ** 2
        if chars < min_chars:
            cost += 3.0 * (min_chars - chars)
        for k in range(a, b):
            if gaps[k] >= force_break_pause:
                return _INF
            if gaps[k] >= _LONG_GAP:
                cost += 10.0 * gaps[k]
            if _is_sentence_end(tokens[k]):
                cost += 30.0
            elif hints.get(k) == "sentence":
                cost += 6.0
        return cost

    def solve(use_words: bool) -> Optional[List[int]]:
        allowed = [break_allowed(i, use_words) for i in range(n)]
        best = [_INF] * (n + 1)
        back = [-1] * (n + 1)
        best[0] = 0.0
        for end in range(n):
            if not allowed[end]:
                continue
            extra = break_cost(end) if end < n - 1 else 0.0
            for start in range(end, -1, -1):
                if start != end and shown_chars(start, end) > max_chars:
                    break
                if (start > 0 and not allowed[start - 1]) or best[start] == _INF:
                    continue
                total = best[start] + line_cost(start, end) + extra
                if total < best[end + 1]:
                    best[end + 1] = total
                    back[end + 1] = start
        if best[n] == _INF:
            return None
        starts: List[int] = []
        j = n
        while j > 0:
            starts.append(back[j])
            j = back[j]
        return sorted(starts)

    starts = solve(use_words=True)
    if starts is None:
        logger.debug("No word-boundary segmentation fits the limits; relaxing")
        starts = solve(use_words=False) or [0]

    segments: List[Dict[str, Any]] = []
    bounds = starts + [n]
    for a, b in zip(bounds, bounds[1:]):
        chunk = words[a:b]
        segments.append(
            {
                "id": len(segments),
                "start": chunk[0]["start"],
                "end": chunk[-1]["end"],
                "text": _clean_line(join_tokens(tokens[a:b])),
                "confidence": None,
                "words": [dict(w, word=_core(w.get("word", ""))) for w in chunk],
            }
        )
    return segments


def _text_to_pseudo_words(
    text: str, start_time: float, end_time: float
) -> List[Dict[str, Any]]:
    """Tokenise *text* (CJK chars, Latin/digit runs) with proportional timing."""
    pieces: List[List[int]] = []  # [token_start, token_end] offsets in text
    i = 0
    while i < len(text):
        ch = text[i]
        if _is_latin_or_digit(ch):
            j = i
            while j < len(text) and _is_latin_or_digit(text[j]):
                j += 1
            pieces.append([i, j])
            i = j
        elif is_word_char(ch):
            pieces.append([i, i + 1])
            i += 1
        else:
            if pieces:
                pieces[-1][1] = i + 1
            i += 1

    total = len(text) or 1
    duration = end_time - start_time
    words: List[Dict[str, Any]] = []
    for a, b in pieces:
        words.append(
            {
                "word": text[a:b],
                "start": start_time + duration * a / total,
                "end": start_time + duration * b / total,
            }
        )
    return words


def segment_text(
    text: str,
    start_time: float,
    end_time: float,
    *,
    max_chars: int = 25,
    target_chars: int = 16,
) -> List[Dict[str, Any]]:
    """Split plain *text* (no word timings) into lines; times are proportional.

    Returns ``[{start, end, text}]`` dicts.
    """
    words = _text_to_pseudo_words(text, start_time, end_time)
    if not words:
        return [{"start": start_time, "end": end_time, "text": text.strip()}]
    segments = segment_words(
        words,
        max_chars=max_chars,
        target_chars=target_chars,
        max_duration=_INF,
        force_break_pause=_INF,
    )
    return [
        {
            "start": round(seg["start"], 3),
            "end": round(seg["end"], 3),
            "text": seg["text"],
        }
        for seg in segments
        if seg["text"]
    ]
