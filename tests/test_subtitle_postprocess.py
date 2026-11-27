import backend.shared.subtitle_postprocess as sp


def _words(tokens, start=0.0, step=0.12):
    return [
        {"word": tok, "start": round(start + i * step, 3),
         "end": round(start + i * step + step, 3), "probability": None}
        for i, tok in enumerate(tokens)
    ]


def _saved_segment(text, tokens, start=0.0):
    words = _words(tokens, start=start)
    return {"id": 0, "start": words[0]["start"], "end": words[-1]["end"],
            "text": text, "words": words}


def test_rebuild_saved_segments_applies_glossary_across_old_lines(monkeypatch):
    monkeypatch.setattr(sp, "predict_break_hints", lambda ws: {})
    first = _saved_segment("這個數據結構就是當前線程的線程環境",
                           list("這個數據結構就是當前線程的線程環境"))
    second = _saved_segment("塊 TEB，這個結構裡面", list("塊") + ["TEB"]
                            + list("這個結構裡面"), start=first["end"])

    segments = sp.rebuild_saved_segments([first, second], glossary="線程環境塊")

    texts = [s["text"] for s in segments]
    assert any("線程環境塊" in t for t in texts)
    assert not any(t.startswith("塊") for t in texts)


def test_rebuild_saved_segments_keeps_words_and_text_in_sync(monkeypatch):
    monkeypatch.setattr(sp, "predict_break_hints", lambda ws: {})
    seg = _saved_segment("調用這個函數，然後根據返回值打印",
                         list("調用這個函數然後根據返回值打印"))

    segments = sp.rebuild_saved_segments([seg])

    assert segments
    for s in segments:
        spelled = "".join(w["word"] for w in s["words"])
        assert spelled == "".join(ch for ch in s["text"] if ch.isalnum())
    assert segments[0]["start"] == seg["start"]
    assert segments[-1]["end"] == seg["end"]


def test_rebuild_saved_segments_keeps_traditional_output(monkeypatch):
    monkeypatch.setattr(sp, "predict_break_hints", lambda ws: {})
    seg = _saved_segment("裡面的線程", list("裡面的線程"))

    (out,) = sp.rebuild_saved_segments([seg])

    assert out["text"] == "裡面的線程"


def test_rebuild_saved_segments_restores_space_at_old_line_edges(monkeypatch):
    monkeypatch.setattr(sp, "predict_break_hints", lambda ws: {})
    first = _saved_segment("方法，調用", list("方法調用"))
    second = _saved_segment("ntQueryInformationProcess",
                            ["ntQueryInformationProcess"], start=first["end"])
    third = _saved_segment("函數", list("函數"), start=second["end"])

    segments = sp.rebuild_saved_segments([first, second, third])

    assert "".join(s["text"] for s in segments) == (
        "方法，調用 ntQueryInformationProcess 函數"
    )


def test_rebuild_saved_segments_keeps_tight_spacing_when_asr_writes_it(
    monkeypatch,
):
    monkeypatch.setattr(sp, "predict_break_hints", lambda ws: {})
    first = _saved_segment("包括VC加的調試", list("包括") + ["VC"] + list("加的調試"))
    second = _saved_segment("O牛debug的", ["O"] + list("牛") + ["debug"] + list("的"),
                            start=first["end"])
    third = _saved_segment("用", list("用"), start=second["end"])

    segments = sp.rebuild_saved_segments([first, second, third])

    assert "".join(s["text"] for s in segments) == "包括VC加的調試O牛debug的用"


def test_rebuild_saved_segments_skips_segments_without_words(monkeypatch):
    monkeypatch.setattr(sp, "predict_break_hints", lambda ws: {})
    seg = {"id": 0, "start": 0.0, "end": 1.0, "text": "沒有字級時間", "words": []}

    assert sp.rebuild_saved_segments([seg]) == []
