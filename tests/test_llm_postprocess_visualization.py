import json

import pytest

from backend.shared import llm_postprocess as lp


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


def _fake_openai(monkeypatch, content=None, error=None):
    calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            if error is not None:
                raise error
            return _FakeResponse(content)

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

        def __init__(self, **_kwargs):
            pass

    import openai

    monkeypatch.setattr(openai, "OpenAI", FakeClient)
    return calls


SEGMENTS = [
    {"start": 0.0, "end": 5.0, "text": "今天講 TCP"},
    {"start": 65.0, "end": 70.0, "text": "三向交握"},
]


def _node(title, time="00:00", children=None):
    return {"title": title, "time": time, "children": children or []}


def test_generate_mindmap_parses_tree_and_times(monkeypatch):
    payload = {"root": _node("TCP", "00:00", [_node("三向交握", "01:05")])}
    calls = _fake_openai(monkeypatch, json.dumps(payload, ensure_ascii=False))

    result = lp.generate_mindmap(SEGMENTS, api_key="k", model="m")

    assert result["root"]["title"] == "TCP"
    assert result["root"]["time"] == 0.0
    child = result["root"]["children"][0]
    assert child == {"title": "三向交握", "time": 65.0, "children": []}
    assert calls[0]["model"] == "m"
    assert "[01:05] 三向交握" in calls[0]["messages"][1]["content"]


def test_generate_mindmap_accepts_code_fence(monkeypatch):
    raw = "```json\n" + json.dumps({"root": _node("A")}) + "\n```"
    _fake_openai(monkeypatch, raw)
    assert lp.generate_mindmap(SEGMENTS, api_key="k")["root"]["title"] == "A"


def test_generate_mindmap_drops_blank_titles_and_converts_terms(monkeypatch):
    payload = {"root": _node("根", children=[_node("  "), _node("線程模型")])}
    _fake_openai(monkeypatch, json.dumps(payload, ensure_ascii=False))
    children = lp.generate_mindmap(SEGMENTS, api_key="k")["root"]["children"]
    assert [c["title"] for c in children] == ["執行緒模型"]


def test_generate_mindmap_truncates_depth_to_four_levels(monkeypatch):
    deep = _node("L1", children=[_node("L2", children=[_node(
        "L3", children=[_node("L4", children=[_node("L5")])]
    )])])
    _fake_openai(monkeypatch, json.dumps({"root": deep}))
    root = lp.generate_mindmap(SEGMENTS, api_key="k")["root"]
    level4 = root["children"][0]["children"][0]["children"][0]
    assert level4["title"] == "L4"
    assert level4["children"] == []


def test_generate_mindmap_caps_total_nodes_at_sixty(monkeypatch):
    groups = [
        _node(f"G{i}", children=[_node(f"G{i}-{j}") for j in range(10)])
        for i in range(10)
    ]
    _fake_openai(monkeypatch, json.dumps({"root": _node("R", children=groups)}))
    root = lp.generate_mindmap(SEGMENTS, api_key="k")["root"]

    def count(n):
        return 1 + sum(count(c) for c in n["children"])

    assert count(root) == 60
    # BFS order keeps every first-level group before any grandchild
    assert len(root["children"]) == 10


def test_generate_mindmap_rejects_invalid_json(monkeypatch):
    _fake_openai(monkeypatch, "不是 JSON")
    with pytest.raises(RuntimeError, match="心智圖格式錯誤"):
        lp.generate_mindmap(SEGMENTS, api_key="k")


def test_generate_mindmap_rejects_missing_root(monkeypatch):
    _fake_openai(monkeypatch, json.dumps({"tree": {}}))
    with pytest.raises(RuntimeError, match="心智圖格式錯誤"):
        lp.generate_mindmap(SEGMENTS, api_key="k")


def test_generate_mindmap_requires_segments(monkeypatch):
    _fake_openai(monkeypatch, "{}")
    with pytest.raises(RuntimeError, match="目前沒有字幕資料"):
        lp.generate_mindmap([], api_key="k")


def test_generate_mindmap_wraps_api_errors(monkeypatch):
    _fake_openai(monkeypatch, error=Exception("rate limited"))
    with pytest.raises(RuntimeError, match="rate limited"):
        lp.generate_mindmap(SEGMENTS, api_key="k")
