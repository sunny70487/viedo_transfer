from backend.shared import punctuation_hints as ph


def _words(tokens):
    return [
        {"word": tok, "start": i * 0.2, "end": (i + 1) * 0.2}
        for i, tok in enumerate(tokens)
    ]


def _fake_model(punctuated):
    calls = []

    def predict(text):
        calls.append(text)
        return punctuated

    return predict, calls


def test_predict_break_hints_maps_marks_to_word_indices(monkeypatch):
    predict, calls = _fake_model("我们先看一下，然后再试。好的")
    monkeypatch.setattr(ph, "_punctuate", predict)
    words = _words(list("我們先看一下然後再試好的"))
    hints = ph.predict_break_hints(words)
    assert calls == ["我们先看一下然后再试好的"]
    assert hints == {5: "clause", 9: "sentence"}


def test_predict_break_hints_handles_latin_words(monkeypatch):
    predict, _ = _fake_model("调用 isdebuggerpresent，然后返回")
    monkeypatch.setattr(ph, "_punctuate", predict)
    words = _words(["調", "用", "isDebuggerPresent", "然", "後", "返", "回"])
    assert ph.predict_break_hints(words) == {2: "clause"}


def test_predict_break_hints_returns_empty_when_model_fails(monkeypatch):
    def boom(_text):
        raise RuntimeError("model missing")

    monkeypatch.setattr(ph, "_punctuate", boom)
    assert ph.predict_break_hints(_words(list("你好世界"))) == {}


def test_predict_break_hints_ignores_trailing_mark(monkeypatch):
    predict, _ = _fake_model("你好世界。")
    monkeypatch.setattr(ph, "_punctuate", predict)
    assert ph.predict_break_hints(_words(list("你好世界"))) == {}


def test_predict_break_hints_disabled_by_env(monkeypatch):
    predict, calls = _fake_model("你好，世界")
    monkeypatch.setattr(ph, "_punctuate", predict)
    monkeypatch.setenv("SUBTITLE_PUNC_MODEL", "")
    assert ph.predict_break_hints(_words(list("你好世界"))) == {}
    assert calls == []
