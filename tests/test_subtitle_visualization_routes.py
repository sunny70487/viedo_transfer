import importlib
import inspect
import json
import sys
import types
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _load_subtitle_api_module():
    sys.modules.pop("backend.services.subtitle_api", None)
    stub = types.ModuleType("backend.services.retranscribe_service")

    class _DummyRetranscribeService:
        def get_retranscribe_task(self, task_id):
            return None

        def get_all_retranscribe_tasks(self):
            return {}

    setattr(stub, "get_retranscribe_service", lambda: _DummyRetranscribeService())
    sys.modules["backend.services.retranscribe_service"] = stub
    return importlib.import_module("backend.services.subtitle_api")


def _make_task(tmp_path, task_id="task-1"):
    json_path = tmp_path / f"{task_id}.json"
    json_path.write_text(
        json.dumps(
            {
                "segments": [{"start": 0.0, "end": 1.0, "text": "測試字幕"}],
                "language": "zh",
                "model_name": "qwen3-asr-1.7b",
                "duration": 1.0,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return SimpleNamespace(
        status="completed",
        result={"files": {"json": str(json_path)}, "output_dir": str(tmp_path)},
        start_time=1.0,
        end_time=2.0,
    )


def _client(subtitle_api, tasks):
    subtitle_api.set_tasks_storage(tasks)
    app = FastAPI()
    app.include_router(subtitle_api.router)
    return TestClient(app)


def test_resolve_task_output_dir_uses_first_result_file(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    task = _make_task(tmp_path)
    assert subtitle_api._resolve_task_output_dir(task) == str(tmp_path)


def test_resolve_task_output_dir_falls_back_to_output_dir(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    task = SimpleNamespace(result={"files": {}, "output_dir": str(tmp_path)})
    assert subtitle_api._resolve_task_output_dir(task) == str(tmp_path)


def test_resolve_task_output_dir_returns_none_without_result():
    subtitle_api = _load_subtitle_api_module()
    assert subtitle_api._resolve_task_output_dir(SimpleNamespace(result=None)) is None


def test_summarize_endpoint_is_sync():
    subtitle_api = _load_subtitle_api_module()
    assert not inspect.iscoroutinefunction(
        subtitle_api.summarize_subtitles_endpoint
    )


def test_get_notes_still_returns_saved_summary(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    (tmp_path / "task-1_notes.json").write_text(
        json.dumps({"summary": "S", "chapters": []}), encoding="utf-8"
    )
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})
    res = client.get("/api/subtitles/task-1/notes")
    assert res.status_code == 200
    assert res.json()["summary"] == "S"


def _fake_notes_gen(pieces, error=None):
    def _gen(segments, **_kwargs):
        for p in pieces:
            yield p
        if error is not None:
            raise error
    return _gen


def test_generate_notes_endpoint_is_sync():
    subtitle_api = _load_subtitle_api_module()
    assert not inspect.iscoroutinefunction(subtitle_api.generate_notes_endpoint)


def test_generate_notes_saves_markdown_and_clears_old_animations(
    tmp_path, monkeypatch
):
    from backend.shared import llm_postprocess as lp

    subtitle_api = _load_subtitle_api_module()
    monkeypatch.setattr(
        lp, "generate_notes", _fake_notes_gen(["# 標題\n", "內容"])
    )
    old_anim = tmp_path / "task-1_anim_old.svg"
    old_anim.write_text("<svg/>", encoding="utf-8")
    other_task_anim = tmp_path / "task-2_anim_x.svg"
    other_task_anim.write_text("<svg/>", encoding="utf-8")

    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})
    res = client.post(
        "/api/subtitles/task-1/generate-notes", json={"api_key": "k"}
    )

    assert res.status_code == 200
    assert '"type": "done"' in res.text
    saved = tmp_path / "task-1_study_notes.md"
    assert saved.read_text(encoding="utf-8") == "# 標題\n內容"
    assert not old_anim.exists()
    assert other_task_anim.exists()


def test_generate_notes_error_keeps_previous_files(tmp_path, monkeypatch):
    from backend.shared import llm_postprocess as lp

    subtitle_api = _load_subtitle_api_module()
    monkeypatch.setattr(
        lp,
        "generate_notes",
        _fake_notes_gen(["# 半"], error=RuntimeError("boom")),
    )
    notes = tmp_path / "task-1_study_notes.md"
    notes.write_text("舊筆記", encoding="utf-8")
    old_anim = tmp_path / "task-1_anim_old.svg"
    old_anim.write_text("<svg/>", encoding="utf-8")

    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})
    res = client.post(
        "/api/subtitles/task-1/generate-notes", json={"api_key": "k"}
    )

    assert '"type": "error"' in res.text
    assert '"type": "done"' not in res.text
    assert notes.read_text(encoding="utf-8") == "舊筆記"
    assert old_anim.exists()


def test_get_study_notes_returns_saved_markdown(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    (tmp_path / "task-1_study_notes.md").write_text("# 筆記", encoding="utf-8")
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})
    res = client.get("/api/subtitles/task-1/study-notes")
    assert res.status_code == 200
    assert res.json() == {"markdown": "# 筆記"}


def test_get_study_notes_404_when_missing(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})
    assert client.get("/api/subtitles/task-1/study-notes").status_code == 404
    assert client.get("/api/subtitles/nope/study-notes").status_code == 404


def test_mindmap_endpoints_are_sync():
    subtitle_api = _load_subtitle_api_module()
    assert not inspect.iscoroutinefunction(subtitle_api.generate_mindmap_endpoint)
    assert not inspect.iscoroutinefunction(subtitle_api.get_mindmap)


def test_post_mindmap_saves_and_returns(tmp_path, monkeypatch):
    from backend.shared import llm_postprocess as lp

    subtitle_api = _load_subtitle_api_module()
    mindmap = {"root": {"title": "T", "time": 0.0, "children": []}}
    seen = {}

    def fake(segments, **kwargs):
        seen.update(kwargs)
        seen["segments"] = segments
        return mindmap

    monkeypatch.setattr(lp, "generate_mindmap", fake)
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    res = client.post(
        "/api/subtitles/task-1/mindmap", json={"api_key": "k", "model": "m"}
    )

    assert res.status_code == 200
    assert res.json() == mindmap
    assert seen["model"] == "m"
    assert seen["segments"][0]["text"] == "測試字幕"
    saved = json.loads(
        (tmp_path / "task-1_mindmap.json").read_text(encoding="utf-8")
    )
    assert saved == mindmap
    assert client.get("/api/subtitles/task-1/mindmap").json() == mindmap


def test_post_mindmap_runtime_error_is_502(tmp_path, monkeypatch):
    from backend.shared import llm_postprocess as lp

    subtitle_api = _load_subtitle_api_module()

    def boom(segments, **kwargs):
        raise RuntimeError("心智圖格式錯誤，請重試")

    monkeypatch.setattr(lp, "generate_mindmap", boom)
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})
    res = client.post("/api/subtitles/task-1/mindmap", json={"api_key": "k"})
    assert res.status_code == 502
    assert res.json()["detail"] == "心智圖格式錯誤，請重試"
    assert not (tmp_path / "task-1_mindmap.json").exists()


def test_get_mindmap_404_when_missing(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})
    assert client.get("/api/subtitles/task-1/mindmap").status_code == 404
