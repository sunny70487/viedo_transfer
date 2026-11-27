"""
Apply the user's glossary (the 「專有名詞 / 術語」 field) to aligned words.

Rule-based, no LLM. Two kinds of entries:

* ``錯字=>正確`` — an explicit correction, applied wherever the wrong
  spelling appears.
* ``術語`` — a plain term. Exact occurrences (ignoring Simplified/Traditional
  and letter case) take the glossary spelling; Chinese occurrences that sound
  exactly the same (same pinyin *and* tones, at least two characters) are
  corrected to it.

Every match is merged into a single word spanning the original words'
timing and marked ``glossary=True``, so the line breaker never splits a term
across two subtitle lines. Matches only start and end on word boundaries
and never cross punctuation the ASR produced.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from backend.shared.subtitle_segmentation import _core, _punct_tail

logger = logging.getLogger("glossary")

CORRECTION_SEPARATOR = "=>"
_SPLIT_RE = re.compile(r"[\n,，、]")
_HAN_RE = re.compile(r"[\u3400-\u9fff]")
_MIN_HOMOPHONE_CHARS = 2

try:
    from opencc import OpenCC

    _T2S = OpenCC("t2s")
except ImportError:
    _T2S = None

try:
    from pypinyin import Style, lazy_pinyin

    PYPINYIN_AVAILABLE = True
except ImportError:
    PYPINYIN_AVAILABLE = False

Glossary = Tuple[List[str], Dict[str, str]]


def parse_glossary(raw) -> Glossary:
    """Split the glossary field into ``(terms, corrections)``.

    *raw* is a string (newline / comma separated) or a list. ``terms`` holds
    every correct spelling (plain terms and the right side of corrections),
    de-duplicated case-insensitively in input order.
    """
    if raw is None:
        return [], {}
    items = _SPLIT_RE.split(raw) if isinstance(raw, str) else raw

    terms: List[str] = []
    corrections: Dict[str, str] = {}
    seen = set()
    for item in items:
        if not isinstance(item, str):
            continue
        entry = item.strip()
        right = entry
        if CORRECTION_SEPARATOR in entry:
            wrong, right = (s.strip() for s in entry.split(CORRECTION_SEPARATOR, 1))
            if not wrong or not right:
                continue
            corrections[wrong] = right
        if right and right.casefold() not in seen:
            seen.add(right.casefold())
            terms.append(right)
    return terms, corrections


def _norm(text: str) -> str:
    """Comparison key: Simplified, lower-case, no whitespace."""
    text = "".join(text.split())
    if _T2S is not None:
        simplified = _T2S.convert(text)
        if len(simplified) == len(text):
            text = simplified
    return text.casefold()


def _tone_key(text: str) -> Optional[str]:
    if not PYPINYIN_AVAILABLE:
        return None
    syllables = lazy_pinyin(
        _norm(text), style=Style.TONE3, neutral_tone_with_five=True
    )
    return " ".join(syllables)


def _is_all_han(text: str) -> bool:
    return bool(text) and all(_HAN_RE.match(ch) for ch in text)


def _build_tables(glossary: Glossary):
    terms, corrections = glossary
    exact: Dict[str, str] = {}
    for term in terms:
        exact.setdefault(_norm(term), term)
    for wrong, right in corrections.items():
        exact[_norm(wrong)] = right

    homophones: Dict[str, str] = {}
    for term in terms:
        if len(term) >= _MIN_HOMOPHONE_CHARS and _is_all_han(term):
            key = _tone_key(term)
            if key:
                homophones.setdefault(key, term)
    homophone_lengths = {len(t) for t in homophones.values()}
    return exact, homophones, homophone_lengths


def apply_glossary(
    words: List[Dict[str, Any]], glossary: Glossary
) -> List[Dict[str, Any]]:
    """Return *words* with glossary matches merged into single words."""
    terms, corrections = glossary
    if not words or (not terms and not corrections):
        return words

    exact, homophones, homophone_lengths = _build_tables(glossary)
    prefixes = {key[:k] for key in exact for k in range(1, len(key) + 1)}
    cores = [_core(w.get("word", "")) for w in words]
    keys = [_norm(c) for c in cores]
    tails = [_punct_tail(w.get("word", "")) for w in words]

    out: List[Dict[str, Any]] = []
    i = 0
    n = len(words)
    while i < n:
        match = _find_match(i, cores, keys, tails, exact, prefixes,
                            homophones, homophone_lengths)
        if match is None:
            out.append(words[i])
            i += 1
            continue
        j, replacement = match
        last = words[j]["word"]
        tail = last[len(last.rstrip()) - len(tails[j]):] if tails[j] else ""
        trailing_space = " " if last.endswith(" ") and not tail.endswith(" ") else ""
        merged = dict(words[i])
        merged.update(
            word=replacement + tail + trailing_space,
            end=words[j]["end"],
            glossary=True,
        )
        if j > i:
            merged["probability"] = None
        if cores[i] != replacement or j > i:
            logger.debug("glossary: %r -> %r", "".join(cores[i:j + 1]), replacement)
        out.append(merged)
        i = j + 1
    return out


def _find_match(i, cores, keys, tails, exact, prefixes, homophones,
                homophone_lengths) -> Optional[Tuple[int, str]]:
    """Longest match starting at word *i*: ``(last_word_index, replacement)``."""
    best: Optional[Tuple[int, str]] = None
    acc = ""
    for j in range(i, len(cores)):
        if not keys[j]:
            break
        acc += keys[j]
        if acc not in prefixes:
            break
        if acc in exact:
            best = (j, exact[acc])
        if tails[j]:
            break
    if best is not None or not homophones:
        return best

    text = ""
    longest = max(homophone_lengths)
    for j in range(i, len(cores)):
        if not _is_all_han(cores[j]):
            break
        text += cores[j]
        if len(text) > longest:
            break
        if len(text) in homophone_lengths:
            term = homophones.get(_tone_key(text))
            if term:
                best = (j, term)
        if tails[j]:
            break
    return best
