"""
Predict phrase boundaries with FunASR's CT-Transformer punctuation model.

Qwen3-ASR punctuates sparsely (often a whole sentence without a comma), so
the segmenter is left guessing where a phrase ends. This module runs the
punctuation model over the aligner's words and returns *hints* — word
indices where a clause or sentence ends. Hints only steer where lines
break; the predicted marks are never written into the subtitle text.

Set ``SUBTITLE_PUNC_MODEL`` to an empty string to disable, or to another
ModelScope model id. Any failure returns no hints (segmentation still works).
"""

import logging
import os
import threading
from typing import Any, Dict, List

from backend.shared.subtitle_segmentation import is_word_char

logger = logging.getLogger("punctuation_hints")

_DEFAULT_MODEL = "ct-punc"
_SENTENCE_MARKS = set("。？！?!")
_CLAUSE_MARKS = set("，、；：,;:")

_model_lock = threading.Lock()
_model_cache: Dict[str, Any] = {}

try:
    from opencc import OpenCC

    _T2S = OpenCC("t2s")
except ImportError:
    _T2S = None


def _model_name() -> str:
    return os.environ.get("SUBTITLE_PUNC_MODEL", _DEFAULT_MODEL).strip()


def _punctuate(text: str) -> str:
    name = _model_name()
    with _model_lock:
        model = _model_cache.get(name)
        if model is None:
            from funasr import AutoModel

            model = AutoModel(model=name, disable_update=True, disable_pbar=True)
            _model_cache[name] = model
        results = model.generate(input=text)
    return "".join(r.get("text", "") for r in results)


def _letters(text: str) -> str:
    return "".join(ch for ch in text if is_word_char(ch)).lower()


def predict_break_hints(words: List[Dict[str, Any]]) -> Dict[int, str]:
    """Map word index → ``"sentence"`` / ``"clause"`` where a mark is predicted."""
    if not words or not _model_name():
        return {}

    word_letters = [_letters(w.get("word", "")) for w in words]
    plain = "".join(word_letters)
    if not plain:
        return {}
    probe = plain
    if _T2S is not None:
        simplified = _T2S.convert(plain)
        if len(simplified) == len(plain):
            probe = simplified

    try:
        punctuated = _punctuate(probe)
    except Exception as exc:
        logger.warning("Punctuation model unavailable, skipping hints: %s", exc)
        return {}

    if _letters(punctuated) != probe.lower():
        logger.warning("Punctuation model changed the text; ignoring its hints")
        return {}

    ends: List[int] = []
    total = 0
    for letters in word_letters:
        total += len(letters)
        ends.append(total)
    end_to_word = {end: i for i, end in enumerate(ends) if word_letters[i]}

    hints: Dict[int, str] = {}
    seen = 0
    for ch in punctuated:
        if is_word_char(ch):
            seen += 1
            continue
        kind = (
            "sentence" if ch in _SENTENCE_MARKS
            else "clause" if ch in _CLAUSE_MARKS
            else None
        )
        idx = end_to_word.get(seen)
        if kind and idx is not None and idx < len(words) - 1:
            if hints.get(idx) != "sentence":
                hints[idx] = kind
    return hints
