from backend.shared import llm_postprocess as lp


class _FakeDelta:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.delta = _FakeDelta(content)


class _FakeChunk:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


def _fake_openai(monkeypatch, pieces):
    class FakeCompletions:
        def create(self, **_kwargs):
            return iter([_FakeChunk(p) for p in pieces])

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

        def __init__(self, **_kwargs):
            pass

    import openai

    monkeypatch.setattr(openai, "OpenAI", FakeClient)


def test_replaces_mainland_terms_with_taiwan_terms():
    src = "寄存器、線程、默認、加載、代碼、鼠標、信息、反匯編"
    out = lp._to_zh_tw_terms(src)
    assert "暫存器" in out
    assert "執行緒" in out
    assert "預設" in out
    assert "載入" in out
    assert "程式碼" in out
    assert "滑鼠" in out
    assert "資訊" in out
    assert "反組譯" in out


def test_no_selfmapping_terms_inflate_buffer():
    for cn, tw in lp._ZH_TW_TERMS:
        assert cn != tw, f"no-op term pair inflates the stream buffer: {cn}"


def test_stream_replaces_term_split_across_chunks(monkeypatch):
    # "寄存器" is split as "寄" + "存器" across two chunks.
    _fake_openai(monkeypatch, ["# 標題\n這是寄", "存器與線", "程的默", "認行為。"])

    out = "".join(
        lp.generate_notes([{"start": 0.0, "text": "x"}], api_key="k")
    )

    assert "暫存器" in out
    assert "執行緒" in out
    assert "預設" in out
    assert "寄存器" not in out
    assert "線程" not in out


def test_requirements_block_is_appended_to_user_turn(monkeypatch):
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return iter(())

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

        def __init__(self, **_kwargs):
            pass

    import openai

    monkeypatch.setattr(openai, "OpenAI", FakeClient)

    list(lp.generate_notes([{"start": 0.0, "text": "測試"}], api_key="k"))

    user_msg = captured["messages"][1]["content"]
    assert "<transcript>" in user_msg
    assert "<requirements>" in user_msg
    assert user_msg.rstrip().endswith("</requirements>")
