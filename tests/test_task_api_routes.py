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


def _watched_client(tmp_path, monkeypatch, tasks):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.database import Base, TaskRecord

    task_api = _load_task_api_module()
    engine = create_engine(f"sqlite:///{tmp_path / 'watched.db'}")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        for tid in tasks:
            session.add(TaskRecord(id=tid, status="completed", start_time=1.0))
        session.commit()
    monkeypatch.setattr(task_api, "SessionLocal", session_factory)
    task_api.set_task_registry(tasks)

    app = FastAPI()
    app.include_router(task_api.router)
    return TestClient(app), session_factory, TaskRecord


def test_set_task_watched_updates_registry_and_database(tmp_path, monkeypatch):
    tasks = {"task-1": SimpleNamespace(status="completed", watched=False)}
    client, session_factory, task_record = _watched_client(
        tmp_path, monkeypatch, tasks
    )

    response = client.put("/tasks/task-1/watched", json={"watched": True})

    assert response.status_code == 200
    assert response.json() == {"id": "task-1", "watched": True}
    assert tasks["task-1"].watched is True
    with session_factory() as session:
        assert session.get(task_record, "task-1").watched is True

    response = client.put("/tasks/task-1/watched", json={"watched": False})
    assert response.status_code == 200
    assert tasks["task-1"].watched is False


def test_set_task_watched_returns_404_for_unknown_task(tmp_path, monkeypatch):
    client, _, _ = _watched_client(tmp_path, monkeypatch, {})

    response = client.put("/tasks/missing/watched", json={"watched": True})

    assert response.status_code == 404


def test_set_task_watched_rejects_missing_body_field(tmp_path, monkeypatch):
    tasks = {"task-1": SimpleNamespace(status="completed", watched=False)}
    client, _, _ = _watched_client(tmp_path, monkeypatch, tasks)

    response = client.put("/tasks/task-1/watched", json={})

    assert response.status_code == 422
    assert tasks["task-1"].watched is False


def test_rename_task_updates_registry_and_database(tmp_path, monkeypatch):
    tasks = {"task-1": SimpleNamespace(status="completed", source_name="old.mp4")}
    client, session_factory, task_record = _watched_client(
        tmp_path, monkeypatch, tasks
    )

    response = client.put("/tasks/task-1/name", json={"name": "  第 3 課：堆疊  "})

    assert response.status_code == 200
    assert response.json() == {"id": "task-1", "source_name": "第 3 課：堆疊"}
    assert tasks["task-1"].source_name == "第 3 課：堆疊"
    with session_factory() as session:
        assert session.get(task_record, "task-1").source_name == "第 3 課：堆疊"


def test_rename_task_rejects_blank_name(tmp_path, monkeypatch):
    tasks = {"task-1": SimpleNamespace(status="completed", source_name="old.mp4")}
    client, session_factory, task_record = _watched_client(
        tmp_path, monkeypatch, tasks
    )

    response = client.put("/tasks/task-1/name", json={"name": "   "})

    assert response.status_code == 400
    assert response.json()["detail"] == "任務名稱不可為空"
    assert tasks["task-1"].source_name == "old.mp4"
    with session_factory() as session:
        assert session.get(task_record, "task-1").source_name is None


def test_rename_task_rejects_overlong_name(tmp_path, monkeypatch):
    tasks = {"task-1": SimpleNamespace(status="completed", source_name="old.mp4")}
    client, _, _ = _watched_client(tmp_path, monkeypatch, tasks)

    assert client.put(
        "/tasks/task-1/name", json={"name": "名" * 200}
    ).status_code == 200
    response = client.put("/tasks/task-1/name", json={"name": "名" * 201})

    assert response.status_code == 400
    assert response.json()["detail"] == "任務名稱過長"
    assert tasks["task-1"].source_name == "名" * 200


def test_rename_task_returns_404_for_unknown_task(tmp_path, monkeypatch):
    client, _, _ = _watched_client(tmp_path, monkeypatch, {})

    response = client.put("/tasks/missing/name", json={"name": "x"})

    assert response.status_code == 404


def test_rename_task_keeps_memory_unchanged_when_database_fails(
    tmp_path, monkeypatch
):
    tasks = {"task-1": SimpleNamespace(status="completed", source_name="old.mp4")}
    client, _, _ = _watched_client(tmp_path, monkeypatch, tasks)
    task_api = sys.modules["backend.services.task_api"]

    def broken_session():
        raise RuntimeError("db down")

    monkeypatch.setattr(task_api, "SessionLocal", broken_session)

    response = client.put("/tasks/task-1/name", json={"name": "new"})

    assert response.status_code == 500
    assert tasks["task-1"].source_name == "old.mp4"
