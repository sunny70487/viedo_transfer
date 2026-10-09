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
