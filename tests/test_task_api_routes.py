import importlib
import sys
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _load_task_api_module():
    sys.modules.pop("backend.services.task_api", None)
    return importlib.import_module("backend.services.task_api")


def test_get_task_status_returns_serialized_task():
    task_api = _load_task_api_module()
    task_api.set_task_registry(
        {
            "task-1": SimpleNamespace(
                id="task-1",
                status="completed",
                dict=lambda: {"id": "task-1", "status": "completed"},
            )
        }
    )

    app = FastAPI()
    app.include_router(task_api.router)
    client = TestClient(app)

    response = client.get("/tasks/task-1")

    assert response.status_code == 200
    assert response.json() == {"id": "task-1", "status": "completed"}


def test_get_all_tasks_returns_task_mapping():
    task_api = _load_task_api_module()
    task_api.set_task_registry(
        {
            "task-1": SimpleNamespace(dict=lambda: {"id": "task-1"}),
            "task-2": SimpleNamespace(dict=lambda: {"id": "task-2"}),
        }
    )

    app = FastAPI()
    app.include_router(task_api.router)
    client = TestClient(app)

    response = client.get("/tasks")

    assert response.status_code == 200
    assert response.json() == {
        "task-1": {"id": "task-1"},
        "task-2": {"id": "task-2"},
    }


def test_delete_task_removes_completed_task_and_calls_persistence(monkeypatch):
    task_api = _load_task_api_module()
    tasks = {
        "task-1": SimpleNamespace(status="completed"),
    }
    task_api.set_task_registry(tasks)

    deleted = {}
    monkeypatch.setattr(
        task_api.TaskPersistence,
        "delete_task",
        lambda task_id: deleted.setdefault("task_id", task_id),
    )

    app = FastAPI()
    app.include_router(task_api.router)
    client = TestClient(app)

    response = client.delete("/tasks/task-1")

    assert response.status_code == 200
    assert response.json() == {"message": "任務已刪除"}
    assert deleted["task_id"] == "task-1"
    assert "task-1" not in tasks
