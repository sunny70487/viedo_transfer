import importlib
import sys
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.models import RetranscribeRequest


def _load_modules():
    sys.modules.pop("backend.services.retranscribe_service", None)
    sys.modules.pop("backend.services.subtitle_api", None)

    retranscribe_service = importlib.import_module(
        "backend.services.retranscribe_service"
    )
    subtitle_api = importlib.import_module("backend.services.subtitle_api")
    return retranscribe_service, subtitle_api


def test_delete_task_method_removes_completed_retranscribe_task():
    retranscribe_service, _ = _load_modules()
    service = retranscribe_service.RetranscribeService()

    task = SimpleNamespace(status="completed")
    service.retranscribe_tasks["task-1"] = task

    removed = service.delete_task("task-1")

    assert removed is task
    assert "task-1" not in service.retranscribe_tasks


def test_delete_task_returns_none_when_task_missing():
    retranscribe_service, _ = _load_modules()
    service = retranscribe_service.RetranscribeService()

    removed = service.delete_task("missing")

    assert removed is None


def test_delete_retranscribe_endpoint_uses_service_delete_method(monkeypatch):
    _, subtitle_api = _load_modules()

    class _ServiceStub:
        def __init__(self):
            self.called_with = None

        def get_retranscribe_task(self, task_id):
            return SimpleNamespace(status="completed")

        def delete_task(self, task_id):
            self.called_with = task_id
            return SimpleNamespace(status="completed")

    service_stub = _ServiceStub()
    monkeypatch.setattr(
        subtitle_api,
        "get_retranscribe_service",
        lambda: service_stub,
    )

    app = FastAPI()
    app.include_router(subtitle_api.router)
    client = TestClient(app)

    response = client.delete("/api/subtitles/retranscribe/task-1")

    assert response.status_code == 200
    assert service_stub.called_with == "task-1"


def test_create_retranscribe_task_reads_original_task_from_injected_store(monkeypatch):
    retranscribe_service, _ = _load_modules()

    class _StoreStub:
        def __init__(self, tasks):
            self._tasks = tasks

        def get_tasks(self):
            return self._tasks

    original_task = SimpleNamespace(status="completed", result={"files": {"json": "x"}})
    store = _StoreStub({"task-1": original_task})
    service = retranscribe_service.RetranscribeService(task_store=store)

    submitted = {}

    def _fake_submit(fn, task_id):
        submitted["fn"] = fn
        submitted["task_id"] = task_id
        return None

    service.executor.submit = _fake_submit

    request = RetranscribeRequest(
        task_id="task-1",
        subtitle_index=0,
        start_time=0.0,
        end_time=1.0,
    )

    task_id = service.create_retranscribe_task(request)

    assert task_id in service.retranscribe_tasks
    assert submitted["task_id"] == task_id


def test_create_retranscribe_task_fails_when_store_has_no_original_task():
    retranscribe_service, _ = _load_modules()

    class _StoreStub:
        def get_tasks(self):
            return {}

    service = retranscribe_service.RetranscribeService(task_store=_StoreStub())
    request = RetranscribeRequest(
        task_id="missing",
        subtitle_index=0,
        start_time=0.0,
        end_time=1.0,
    )

    try:
        service.create_retranscribe_task(request)
        assert False, "Expected missing original task to raise"
    except ValueError as exc:
        assert "原始任務不存在" in str(exc)
