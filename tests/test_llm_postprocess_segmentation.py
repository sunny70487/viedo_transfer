from backend.shared import llm_postprocess as lp


def _seg(start, end, text, words=None):
    seg = {"start": start, "end": end, "text": text}
    if words is not None:
        seg["words"] = words
    return seg


def _texts(segments):
    return [s["text"] for s in segments]


def _char_words(text, start, step=0.1):
    return [
        {"word": ch, "start": start + i * step, "end": start + (i + 1) * step}
        for i, ch in enumerate(text)
    ]


def test_merge_short_segments_keeps_word_timed_segments_unchanged():
    segments = [
        _seg(0.0, 0.6, "我們來看一下", _char_words("我們來看一下", 0.0)),
        _seg(0.7, 1.1, "這個地址", _char_words("這個地址", 0.7)),
    ]
    assert _texts(lp.merge_short_segments(segments)) == ["我們來看一下", "這個地址"]


def test_resplit_long_segments_uses_word_timestamps():
    text = "那為了安全起見大家可以在虛擬機裡面去抓包運行一下然後給大家演示如何通過抓包找到"
    words = _char_words(text, 10.0)
    out = lp.resplit_long_segments([_seg(10.0, words[-1]["end"], text, words)])
    assert len(out) >= 2
    for seg in out:
        assert seg["start"] == seg["words"][0]["start"]
        assert seg["end"] == seg["words"][-1]["end"]
    assert "".join(s["text"] for s in out) == text


def test_merge_short_segments_does_not_merge_across_long_pause():
    segments = [_seg(0.0, 1.0, "然後我們"), _seg(3.0, 4.0, "來看這個")]
    assert _texts(lp.merge_short_segments(segments)) == ["然後我們", "來看這個"]


def test_merge_short_segments_still_merges_orphan_fragment():
    segments = [_seg(0.0, 1.5, "我們直接看源代碼"), _seg(1.6, 2.0, "看一下")]
    assert _texts(lp.merge_short_segments(segments)) == ["我們直接看源代碼看一下"]


def test_merge_short_segments_mid_sentence_merge_respects_max_chars():
    first = "這裡呢我推薦一個抓包軟件叫做科萊網絡"
    second = "分析系統類似於Wireshark這樣的一個抓包工具"
    out = lp.merge_short_segments([_seg(0.0, 3.0, first), _seg(3.1, 6.0, second)])
    assert all(len(s["text"]) <= lp._MAX_CHARS for s in out)


def test_split_at_punctuation_without_punct_breaks_at_word_boundary():
    text = "那為了安全起見大家可以在虛擬機裡面去抓包運行一下然後給大家演示如何通過抓包找到"
    pieces = lp._split_at_punctuation(text, 0.0, 10.0)
    assert "".join(p["text"] for p in pieces) == text
    assert all(len(p["text"]) <= lp._MAX_CHARS for p in pieces)
    assert not any(p["text"].endswith(("虛", "抓", "運", "演")) for p in pieces[:-1])


def test_split_at_punctuation_does_not_split_on_particle_inside_word():
    text = "今天我們要去吧台點一杯咖啡然後聊聊這次比賽的題目解析以及後續的學習方向"
    pieces = lp._split_at_punctuation(text, 0.0, 10.0)
    assert not any(p["text"].endswith("吧") for p in pieces[:-1])
