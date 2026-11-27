from types import SimpleNamespace

import jieba
import pytest

import backend.shared.subtitle_postprocess as sp
from backend.shared.subtitle_segmentation import (
    attach_punctuation,
    segment_words,
)


def _words(tokens, start=0.0, step=0.2, gaps=None):
    """Build word dicts with uniform timing; *gaps* maps index → extra pause."""
    gaps = gaps or {}
    words = []
    t = start
    for i, tok in enumerate(tokens):
        t += gaps.get(i, 0.0)
        words.append({"word": tok, "start": round(t, 3), "end": round(t + step, 3)})
        t += step
    return words


def _chars(text):
    return list(text)


def _texts(segments):
    return [s["text"] for s in segments]


# ---------------------------------------------------------------------------
# attach_punctuation
# ---------------------------------------------------------------------------
def test_attach_punctuation_appends_marks_to_preceding_word():
    words = _words(_chars("大家好我是轩辕"))
    out = attach_punctuation(words, "大家好，我是轩辕。")
    assert [w["word"] for w in out] == ["大", "家", "好，", "我", "是", "轩", "辕。"]


def test_attach_punctuation_keeps_dotted_latin_together():
    words = _words(["访", "问", "CTF", "com", "网", "站"])
    out = attach_punctuation(words, "访问CTF.com网站")
    assert [w["word"] for w in out] == ["访", "问", "CTF.", "com", "网", "站"]
    assert _texts(segment_words(out)) == ["访问CTF.com网站"]


def test_attach_punctuation_tolerates_mismatched_text():
    words = _words(_chars("你好世界"))
    out = attach_punctuation(words, "完全不同的文字")
    assert [w["word"] for w in out] == ["你", "好", "世", "界"]


def test_attach_punctuation_does_not_mutate_input():
    words = _words(_chars("你好"))
    attach_punctuation(words, "你好。")
    assert words[1]["word"] == "好"


# ---------------------------------------------------------------------------
# segment_words
# ---------------------------------------------------------------------------
def test_segment_words_empty_input_returns_empty_list():
    assert segment_words([]) == []


def test_segment_words_breaks_at_sentence_end_without_pause():
    text = "这是第一个句子。接下来是第二个句子"
    words = attach_punctuation(_words(_chars("这是第一个句子接下来是第二个句子")), text)
    assert _texts(segment_words(words)) == ["这是第一个句子", "接下来是第二个句子"]


def test_segment_words_merges_short_clause_across_comma():
    text = "然后呢，我们来看一下这个地址"
    words = attach_punctuation(_words(_chars("然后呢我们来看一下这个地址")), text)
    assert _texts(segment_words(words)) == ["然后呢，我们来看一下这个地址"]


def test_segment_words_long_run_breaks_only_at_word_boundaries():
    text = (
        "那为了安全起见大家可以在虚拟机里面去抓包运行一下"
        "然后给大家演示一下如何通过抓包去找到这个木马程序的通信信息"
    )
    segments = segment_words(_words(_chars(text), step=0.12))

    assert "".join(_texts(segments)) == text
    assert len(segments) >= 2
    assert all(len(s["text"]) <= 25 for s in segments)

    word_ends = set()
    pos = 0
    for tok in jieba.cut(text):
        pos += len(tok)
        word_ends.add(pos)
    pos = 0
    for seg in segments[:-1]:
        pos += len(seg["text"])
        assert pos in word_ends, f"break inside a word after {seg['text']!r}"


def test_segment_words_avoids_ending_line_with_structural_particle():
    text = "我们今天要讲的是一个非常重要的网络通信协议的基本原理和实际的应用场景"
    segments = segment_words(_words(_chars(text), step=0.12))
    assert len(segments) >= 2
    assert not any(s["text"].endswith("的") for s in segments[:-1])


def test_segment_words_prefers_noticeable_pause_before_connector():
    first = "这两个就比较可疑了"
    second = "然后下面有这个木马详细的网络通信信息"
    words = _words(_chars(first + second), step=0.12, gaps={len(first): 0.45})
    assert _texts(segment_words(words)) == [first, second]


def test_segment_words_avoids_ending_line_with_measure_phrase():
    text = "给大家演示一下如何通过抓包去找到这个木马程序的通信信息以及后续的处理方式"
    segments = segment_words(_words(_chars(text), step=0.12))
    assert not any(
        s["text"].endswith(("这个", "一个", "如何")) for s in segments[:-1]
    )


def test_segment_words_strips_trailing_comma_but_keeps_question_mark():
    text = "问他连线的是哪一个IP地址？那看一下沙箱，这里有个网络行为，"
    tokens = _chars("问他连线的是哪一个") + ["IP"] + _chars("地址那看一下沙箱这里有个网络行为")
    words = attach_punctuation(_words(tokens, gaps={12: 1.5}), text)
    assert _texts(segment_words(words)) == [
        "问他连线的是哪一个IP地址？",
        "那看一下沙箱，这里有个网络行为",
    ]


def test_segment_words_does_not_merge_short_tail_across_sentence_end():
    text = "可能会损害自己的计算机。那为了"
    words = attach_punctuation(_words(_chars("可能会损害自己的计算机那为了")), text)
    assert _texts(segment_words(words)) == ["可能会损害自己的计算机", "那为了"]


def test_segment_words_joins_spelled_out_acronyms():
    text = "然后是一个CTF的com，然后HTTP有相关的通信"
    tokens = _chars("然后是一个") + ["C", "T", "F"] + ["的", "com"] + _chars("然后") \
        + ["H", "T", "T", "P"] + _chars("有相关的通信")
    words = attach_punctuation(_words(tokens), "然后是一个C T F的com，然后H T T P有相关的通信")
    assert "".join(_texts(segment_words(words, max_chars=40))).replace("，", "") == (
        text.replace("，", "")
    )


def test_segment_words_long_pause_forces_break():
    tokens = _chars("我们来看这个地址")
    words = _words(tokens, gaps={4: 2.0})
    assert _texts(segment_words(words)) == ["我们来看", "这个地址"]


def test_segment_words_respects_max_duration():
    words = _words(_chars("一二三四五六七八九十" * 2), step=0.5)
    segments = segment_words(words, max_duration=6.0)
    assert all(s["end"] - s["start"] <= 6.0 + 1e-6 for s in segments)


def test_segment_words_output_shape_and_timing():
    words = _words(_chars("你好世界"), start=3.0)
    (seg,) = segment_words(words)
    assert seg["start"] == 3.0
    assert seg["end"] == words[-1]["end"]
    assert seg["words"] == words
    assert seg["confidence"] is None
    assert seg["id"] == 0


def test_segment_words_inserts_spaces_between_latin_words():
    words = attach_punctuation(
        _words(["Hello", "world", "This", "is", "fine"]), "Hello, world. This is fine."
    )
    assert _texts(segment_words(words)) == ["Hello, world", "This is fine"]


def test_segment_words_accepts_attribute_free_dicts():
    # words coming from JSON may carry extra keys such as probability
    words = [
        dict(w, probability=None) for w in _words(_chars("测试一下"))
    ]
    assert _texts(segment_words(words)) == ["测试一下"]


def _breaks(segments):
    """Pairs of (line end, next line start) around every break."""
    return [(a["text"][-2:], b["text"][:2]) for a, b in zip(segments, segments[1:])]


def test_segment_words_breaks_at_dash_instead_of_after_adverb():
    text = "今天我们来学习跟调试相关的另一个非常重要的知识点——反调试技术"
    plain = text.replace("——", "")
    words = attach_punctuation(_words(_chars(plain), step=0.12), text)
    texts = _texts(segment_words(words))
    assert not any(t.endswith("非常") for t in texts[:-1])
    assert texts[-1] == "反调试技术"


def test_segment_words_keeps_a_not_a_question_with_its_complement():
    text = (
        "反调试技术核心关键问题就是一个检测自己有没有被调试"
        "或者再进一步扩展为现在有没有调试器存在"
    )
    segments = segment_words(_words(_chars(text), step=0.12))
    assert not any(t.endswith("有没有") for t in _texts(segments)[:-1])


def test_segment_words_does_not_end_line_on_adverb():
    text = "我们这个函数呢它的作用就是判断当前程序是否正在被调试器调试然后返回结果给调用者"
    segments = segment_words(_words(_chars(text), step=0.12))
    adverbs = ("是否", "正在", "非常", "就是", "已经", "比较")
    assert not any(t.endswith(adverbs) for t in _texts(segments)[:-1])


def test_segment_words_prefers_break_before_conjunction():
    text = "程序在运行过程中会不断检测调试器的存在或者检查进程列表中是否有调试工具在运行"
    segments = segment_words(_words(_chars(text), step=0.12))
    assert any(t.startswith("或者") for t in _texts(segments)[1:])


def test_segment_words_allows_break_after_sentence_final_le():
    first = "接下来我们发现它在内存里面了"
    second = "而是直接返回那个已经加载的模块地址给调用者使用"
    words = _words(_chars(first + second), step=0.12, gaps={len(first): 0.2})
    assert _texts(segment_words(words))[0] == first


def test_segment_words_break_hint_splits_without_showing_punctuation():
    text = "程序里面调用这个函数然后根据不同的返回值打印不同的内容"
    words = _words(_chars(text), step=0.12)
    hint_at = text.index("函数") + 1
    segments = segment_words(words, break_hints={hint_at: "clause"})
    assert _texts(segments) == ["程序里面调用这个函数", "然后根据不同的返回值打印不同的内容"]
    assert "，" not in "".join(_texts(segments))


def test_segment_words_never_splits_glossary_term_and_may_break_around_it():
    text = "这个数据结构就是当前线程的"
    words = _words(_chars(text), step=0.12)
    words.append({"word": "线程环境块", "start": words[-1]["end"],
                  "end": words[-1]["end"] + 0.6, "glossary": True})
    words += _words(_chars("TEB这个结构里面就包含了一些线程的信息"),
                    start=words[-1]["end"], step=0.12)
    segments = segment_words(words)
    assert any("线程环境块" in t for t in _texts(segments))


def test_segment_words_counts_latin_as_half_width():
    tokens = _chars("调用") + ["ntQueryInformationProcess"] + _chars("函数")
    words = _words(tokens, step=0.3)
    assert _texts(segment_words(words)) == ["调用ntQueryInformationProcess函数"]


def test_segment_words_sentence_hint_is_not_merged_across():
    text = "这是最基本的检测方法我们可以通过一个例子来试一下"
    words = _words(_chars(text), step=0.12)
    hint_at = text.index("方法") + 1
    segments = segment_words(words, break_hints={hint_at: "sentence"})
    assert _texts(segments)[0] == "这是最基本的检测方法"


def test_postprocess_segments_uses_punctuation_hints_and_keeps_words_in_sync(
    monkeypatch,
):
    pytest.importorskip("torch")
    import backend.qwen3_asr_transcribe as q3

    text = "程序里面调用这个函数然后根据不同的返回值打印不同的内容"
    words = _words(_chars(text), step=0.12)
    seg = {"id": 0, "start": 0.0, "end": words[-1]["end"], "text": text,
           "words": words}
    cut = text.index("函数") + 1
    monkeypatch.setattr(sp, "predict_break_hints", lambda ws: {cut: "clause"})

    segments, out_words = q3._postprocess_segments([seg], list(words))

    assert [s["text"] for s in segments] == [
        "程序裡面調用這個函數", "然後根據不同的返回值打印不同的內容"
    ]
    for s in segments:
        spelled = "".join(w["word"] for w in s["words"])
        assert spelled == s["text"]
    assert "".join(w["word"] for w in out_words) == "".join(
        s["text"] for s in segments
    )


def test_postprocess_segments_applies_glossary_before_segmenting(monkeypatch):
    pytest.importorskip("torch")
    import backend.qwen3_asr_transcribe as q3

    text = "这是当前线程的线程环境块TEB"
    tokens = _chars("这是当前线程的线程环境块") + ["TEB"]
    words = _words(tokens, step=0.12)
    seg = {"id": 0, "start": 0.0, "end": words[-1]["end"], "text": text,
           "words": words}
    monkeypatch.setattr(sp, "predict_break_hints", lambda ws: {})

    segments, out_words = q3._postprocess_segments(
        [seg], list(words), glossary="線程環境塊"
    )

    assert "線程環境塊" in [w["word"] for w in out_words]
    assert "".join(s["text"] for s in segments) == "這是當前線程的線程環境塊TEB"


def test_parse_qwen3_result_keeps_asr_punctuation_on_words():
    pytest.importorskip("torch")
    from backend.qwen3_asr_transcribe import _parse_qwen3_result

    items = [
        SimpleNamespace(text=ch, start_time=i * 0.2, end_time=i * 0.2 + 0.2)
        for i, ch in enumerate("你好世界")
    ]
    result = SimpleNamespace(text="你好，世界。", language="Chinese", time_stamps=items)
    _, words, _, _ = _parse_qwen3_result(result)
    assert [w["word"] for w in words] == ["你", "好，", "世", "界。"]
