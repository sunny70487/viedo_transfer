import importlib
import json
import sys
import types
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.testclient import TestClient


def _load_subtitle_api_module():
    sys.modules.pop("backend.services.subtitle_api", None)

    retranscribe_stub = types.ModuleType("backend.services.retranscribe_service")

    class _DummyRetranscribeService:
        def get_retranscribe_task(self, task_id):
            return None

        def get_all_retranscribe_tasks(self):
            return {}

    setattr(
        retranscribe_stub,
        "get_retranscribe_service",
        lambda: _DummyRetranscribeService(),
    )
    sys.modules["backend.services.retranscribe_service"] = retranscribe_stub

    return importlib.import_module("backend.services.subtitle_api")


def _build_completed_task(json_path, output_dir):
    return SimpleNamespace(
        status="completed",
        result={
            "files": {"json": str(json_path)},
            "output_dir": str(output_dir),
        },
        start_time=1.0,
        end_time=2.0,
    )


def test_task_store_requires_initialization_before_access():
    subtitle_api = _load_subtitle_api_module()
    store = subtitle_api.TaskStore()

    try:
        store.get_tasks()
        assert False, "Expected store access to fail before initialization"
    except HTTPException as exc:
        assert exc.status_code == 500
        assert "任務存儲未初始化" in str(exc.detail)


def test_task_store_returns_same_backing_tasks_dict(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    json_path = tmp_path / "task-1.json"
    json_path.write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "start": 0.0,
                        "end": 1.0,
                        "text": "測試字幕",
                    }
                ],
                "language": "zh",
                "duration": 1.0,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    tasks = {"task-1": _build_completed_task(json_path, tmp_path)}
    store = subtitle_api.TaskStore(tasks)

    assert store.get_tasks() is tasks


def test_head_subtitles_succeeds_with_initialized_task_store(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    json_path = tmp_path / "task-1.json"
    json_path.write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "start": 0.0,
                        "end": 1.0,
                        "text": "測試字幕",
                    }
                ],
                "language": "zh",
                "duration": 1.0,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    tasks = {"task-1": _build_completed_task(json_path, tmp_path)}
    subtitle_api.set_task_store(subtitle_api.TaskStore(tasks))

    app = FastAPI()
    app.include_router(subtitle_api.router)
    client = TestClient(app)

    response = client.head("/api/subtitles/task-1")

    assert response.status_code == 200
