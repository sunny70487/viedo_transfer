import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend import task_persistence as task_persistence_module


def _make_test_session(tmp_path):
    """Create an in-memory SQLite test database and return a session factory."""
    db_path = tmp_path / "test_tasks.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def test_save_task_round_trip(tmp_path, monkeypatch):
    test_session = _make_test_session(tmp_path)
    monkeypatch.setattr(task_persistence_module, "SessionLocal", test_session)

    task_data = {
        "id": "task-1",
        "status": "completed",
        "progress": 100.0,
        "result": {"files": {"json": "task-1.json"}},
        "start_time": 123.0,
    }

    assert (
        task_persistence_module.TaskPersistence.save_task("task-1", task_data) is True
    )

    loaded = task_persistence_module.TaskPersistence.load_all_tasks()

    assert "task-1" in loaded
    assert loaded["task-1"]["status"] == "completed"
    assert loaded["task-1"]["result"] == {"files": {"json": "task-1.json"}}


def test_scan_and_rebuild_tasks_restores_completed_task_from_outputs(
    tmp_path, monkeypatch
):
    test_session = _make_test_session(tmp_path)
    monkeypatch.setattr(task_persistence_module, "SessionLocal", test_session)

    outputs_dir = tmp_path / "outputs"
    task_dir = outputs_dir / "task-1"
    task_dir.mkdir(parents=True)

    transcription_data = {
        "text": "測試字幕",
        "segments": [{"id": 0, "start": 0.0, "end": 1.0, "text": "測試字幕"}],
        "language": "zh",
    }
    (task_dir / "task-1.json").write_text(
        json.dumps(transcription_data, ensure_ascii=False),
        encoding="utf-8",
    )
    (task_dir / "task-1.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\n測試字幕\n", encoding="utf-8"
    )

    monkeypatch.setattr(task_persistence_module, "OUTPUTS_DIR", outputs_dir)

    rebuilt = task_persistence_module.TaskPersistence.scan_and_rebuild_tasks()

    assert "task-1" in rebuilt
    assert rebuilt["task-1"]["status"] == "completed"
    assert rebuilt["task-1"]["result"]["files"]["json"].endswith("task-1.json")
