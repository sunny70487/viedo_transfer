from types import SimpleNamespace

from backend.shared import llm_segmentation as ls
from backend.shared.subtitle_segmentation import is_word_char


def _words(text, start, step=0.2):
    """One word per CJK letter (punctuation dropped, like the aligner)."""
    letters = [ch for ch in text if is_word_char(ch)]
    return [
        {"word": ch, "start": start + i * step, "end": start + (i + 1) * step}
        for i, ch in enumerate(letters)
    ]


def _seg(text, start, step=0.2, **extra):
    words = _words(text, start, step)
    return {
        "start": words[0]["start"],
        "end": words[-1]["end"],
        "text": text,
        "words": words,
        **extra,
    }


def _client(responder):
    calls = []

    def create(**kwargs):
        user_text = kwargs["messages"][-1]["content"]
        calls.append(user_text)
        content = responder(user_text)
        message = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    completions = SimpleNamespace(create=create)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), calls


def _texts(segments):
    return [s["text"] for s in segments]


def _run(segments, responder, **kwargs):
    client, calls = _client(responder)
    out = ls.resegment_with_llm(segments, client=client, model="m", **kwargs)
    return out, calls


def test_resegment_moves_break_to_llm_line_boundary():
    segments = [
        _seg("今天我們來學習跟除錯相關的另一個非常", 0.0),
        _seg("重要的知識點——反除錯技術", 3.6),
    ]
    out, calls = _run(
        segments,
        lambda text: text.replace("相關的", "相關的\n"),
    )
    assert calls == ["今天我們來學習跟除錯相關的另一個非常重要的知識點——反除錯技術"]
    assert _texts(out) == [
        "今天我們來學習跟除錯相關的",
        "另一個非常重要的知識點——反除錯技術",
    ]
    for seg in out:
        assert seg["start"] == seg["words"][0]["start"]
        assert seg["end"] == seg["words"][-1]["end"]
    assert [s["id"] for s in out] == [0, 1]


def test_resegment_falls_back_when_llm_changes_text():
    segments = [_seg("我們先從最簡單的開始", 0.0), _seg("第一個方法", 2.2)]
    out, _ = _run(segments, lambda text: text.replace("簡單", "容易"))
    assert _texts(out) == ["我們先從最簡單的開始", "第一個方法"]


def test_resegment_falls_back_when_llm_raises():
    segments = [_seg("我們先從最簡單的開始", 0.0), _seg("第一個方法", 2.2)]

    def boom(_text):
        raise RuntimeError("api down")

    out, _ = _run(segments, boom)
    assert _texts(out) == ["我們先從最簡單的開始", "第一個方法"]


def test_resegment_snaps_break_inside_latin_word_to_word_end():
    text = "第一 isDebuggerPresent 這是一個函式"
    words = [
        {"word": "第", "start": 0.0, "end": 0.2},
        {"word": "一", "start": 0.2, "end": 0.4},
        {"word": "isDebuggerPresent", "start": 0.4, "end": 1.4},
    ] + _words("這是一個函式", 1.6)
    segments = [{"start": 0.0, "end": words[-1]["end"], "text": text,
                 "words": words}]
    out, _ = _run(
        segments, lambda t: t.replace("isDebugger", "isDebug\nger")
    )
    assert _texts(out) == ["第一 isDebuggerPresent", "這是一個函式"]


def test_resegment_resplits_line_that_exceeds_max_chars():
    text = "那為了安全起見大家可以在虛擬機裡面去抓包運行一下然後給大家演示如何通過抓包找到"
    segments = [_seg(text, 0.0, step=0.1)]
    out, _ = _run(segments, lambda t: t, max_chars=25)
    assert len(out) >= 2
    assert all(len(s["text"]) <= 25 for s in out)
    assert "".join(_texts(out)) == text


def test_resegment_breaks_at_long_pause_even_if_llm_joins_lines():
    segments = [_seg("我們先看一下", 0.0), _seg("這個函式", 4.0)]
    out, _ = _run(segments, lambda t: t)
    assert _texts(out) == ["我們先看一下", "這個函式"]


def test_resegment_skips_segments_without_word_timings():
    segments = [{"start": 0.0, "end": 1.0, "text": "沒有字級時間"}]
    out, calls = _run(segments, lambda t: t)
    assert calls == []
    assert [(s["start"], s["end"], s["text"]) for s in out] == [
        (0.0, 1.0, "沒有字級時間")
    ]


def test_resegment_sends_long_transcript_in_several_calls():
    segments = [
        _seg("第一段的內容在這裡", 0.0),
        _seg("第二段的內容在這裡", 2.0),
        _seg("第三段的內容在這裡", 4.0),
    ]
    out, calls = _run(segments, lambda t: t, chunk_chars=20)
    assert len(calls) >= 2
    assert "".join(_texts(out)) == "".join(_texts(segments))


def test_resegment_never_merges_across_speakers():
    segments = [
        _seg("你今天要講什麼", 0.0, speaker="A"),
        _seg("我要講反除錯", 1.5, speaker="B"),
    ]
    out, _ = _run(segments, lambda t: t)
    assert _texts(out) == ["你今天要講什麼", "我要講反除錯"]
    assert [s["speaker"] for s in out] == ["A", "B"]
