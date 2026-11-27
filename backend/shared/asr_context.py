"""
Build the context string Qwen3-ASR uses to bias recognition.

Qwen3-ASR accepts a `context=` argument that becomes the system message. Naming
domain terms there fixes identifiers the decoder would otherwise mis-hear: on a
Windows reverse-engineering lecture, term accuracy went from 46.7% to 100%
(shellcode was rendered "circle"/"希爾克" without it).

FireRedASR2-AED has no equivalent, so this is Qwen3-ASR specific.
"""

from backend.shared.glossary import CORRECTION_SEPARATOR

DEFAULT_MAX_CHARS = 8000

_SEPARATOR = ", "


def _normalize_hotwords(hotwords):
    if hotwords is None:
        return []
    if isinstance(hotwords, str):
        raw = hotwords.replace(",", "\n").replace("、", "\n").splitlines()
    else:
        raw = hotwords

    seen = set()
    ordered = []
    for item in raw:
        if not isinstance(item, str):
            continue
        # "wrong=>right" glossary corrections: only the right spelling biases ASR.
        term = item.split(CORRECTION_SEPARATOR)[-1].strip()
        if not term:
            continue
        key = term.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(term)
    return ordered


def _join_within_budget(terms, budget):
    if budget <= 0:
        return ""
    parts = []
    used = 0
    for term in terms:
        addition = len(term) if not parts else len(_SEPARATOR) + len(term)
        if used + addition > budget:
            break
        parts.append(term)
        used += addition
    return _SEPARATOR.join(parts)


def build_asr_context(context=None, hotwords=None, max_chars=DEFAULT_MAX_CHARS):
    """
    Combine a free-form context description with a hotword list.

    Args:
        context: free-form description of the audio, e.g. its domain.
        hotwords: terms to bias toward. Accepts a list, or a string separated
            by newlines, commas or full-width commas.
        max_chars: hard cap on the returned string.

    Returns:
        The context string, or "" when there is nothing to say.
    """
    prefix = (context or "").strip()
    terms = _normalize_hotwords(hotwords)

    if not terms:
        return prefix[:max_chars]

    if not prefix:
        return _join_within_budget(terms, max_chars)

    joined = _join_within_budget(terms, max_chars - len(prefix) - 1)
    if not joined:
        return prefix[:max_chars]
    return f"{prefix}\n{joined}"
