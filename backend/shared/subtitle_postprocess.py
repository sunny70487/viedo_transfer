"""
Turn aligned ASR words into final subtitle lines.

Shared by the Qwen3-ASR engine (right after recognition) and the subtitle
editor's 「重新斷句」 action, which rebuilds lines from the word timestamps
already stored in a task's JSON, without running ASR again.
"""

import logging
import re

from backend.shared.glossary import apply_glossary, parse_glossary
from backend.shared.punctuation_hints import predict_break_hints
from backend.shared.subtitle_segmentation import (
    _core,
    attach_punctuation,
    segment_words,
)
from backend.shared.text_processing import (
    convert_segment_to_traditional,
    convert_to_traditional,
    smart_strip_punctuation,
)

logger = logging.getLogger("subtitle_postprocess")


def resegment_words(segments_json, words_data, *, glossary=None):
    """Re-group all words into subtitle lines via ``segment_words``.

    Glossary terms are corrected and merged into single words first, so a
    term is never split across two lines. Returns (new_segments, new_words);
    inputs without word timestamps are returned unchanged.
    """
    all_words = [w for seg in segments_json for w in seg.get("words", [])]
    if not all_words:
        return segments_json, words_data

    all_words = apply_glossary(all_words, parse_glossary(glossary))
    new_segments = segment_words(all_words, break_hints=predict_break_hints(all_words))
    new_words = [w for seg in new_segments for w in seg["words"]]
    return new_segments, new_words


def postprocess_segments(segments_json, words_data, *, glossary=None):
    """Segment into subtitle lines, then convert to Traditional Chinese (Taiwan).

    Segmentation runs before conversion because jieba's dictionary is
    Simplified Chinese.
    """
    segments_json, words_data = resegment_words(
        segments_json, words_data, glossary=glossary
    )

    converted = []
    for seg in segments_json:
        seg = convert_segment_to_traditional(seg)
        seg["text"] = smart_strip_punctuation(seg["text"])
        converted.append(seg)
    new_words = [w for seg in converted for w in seg.get("words", [])]
    if not new_words:
        new_words = [
            dict(w, word=convert_to_traditional(w["word"])) for w in words_data
        ]
    return converted, new_words


_HAN = r"[\u3400-\u9fff]"
_LATIN = r"[A-Za-z0-9]"
_SPACED_MIX = re.compile(f"{_HAN} {_LATIN}|{_LATIN} {_HAN}")
_TIGHT_MIX = re.compile(f"{_HAN}{_LATIN}|{_LATIN}{_HAN}")


def _is_han(ch: str) -> bool:
    return bool(re.match(_HAN, ch))


def _is_latin(ch: str) -> bool:
    return ch.isascii() and ch.isalnum()


def _restore_edge_spaces(segments) -> None:
    """Re-add the Chinese↔Latin space lost where an old line ended.

    Line text is stripped, so 「調用」|「ntQuery…」 no longer records whether
    the ASR put a space between them. Follow the convention the same file
    uses inside its lines (Qwen3-ASR normally spaces mixed scripts).
    """
    texts = [seg.get("text", "") for seg in segments]
    spaced = sum(len(_SPACED_MIX.findall(t)) for t in texts)
    tight = sum(len(_TIGHT_MIX.findall(t)) for t in texts)
    if tight > spaced:
        return
    for prev, nxt in zip(segments, segments[1:]):
        last = prev["words"][-1]
        word = last["word"]
        if word != word.rstrip() or word.rstrip() != _core(word):
            continue
        a, b = word[-1:], nxt["words"][0]["word"][:1]
        if (_is_han(a) and _is_latin(b)) or (_is_latin(a) and _is_han(b)):
            last["word"] = word + " "


def rebuild_saved_segments(segments, *, glossary=None):
    """Re-segment the segments stored in a task's JSON.

    Saved words have their punctuation stripped, so it is re-attached from
    each segment's text before segmenting. Segments without word timestamps
    cannot be re-timed and are dropped; callers should check for an empty
    result.
    """
    timed = []
    for seg in segments:
        words = [w for w in seg.get("words") or [] if w.get("word")]
        if not words:
            continue
        timed.append(dict(seg, words=attach_punctuation(words, seg.get("text", ""))))
    if not timed:
        return []
    _restore_edge_spaces(timed)
    all_words = [w for seg in timed for w in seg["words"]]
    rebuilt, _ = postprocess_segments(timed, all_words, glossary=glossary)
    for i, seg in enumerate(rebuilt):
        seg["id"] = i
    return rebuilt
