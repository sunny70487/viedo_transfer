import json

from backend import task_persistence as task_persistence_module


def test_save_task_round_trip(tmp_path, monkeypatch):
    data_file = tmp_path / "tasks_data.json"
    monkeypatch.setattr(task_persistence_module, "TASKS_DATA_FILE", data_file)

    task_data = {
        "id": "task-1",
        "status": "completed",
        "progress": 100.0,
        "result": {"files": {"json": "task-1.json"}},
    }

    assert (
        task_persistence_module.TaskPersistence.save_task("task-1", task_data) is True
    )

    loaded = task_persistence_module.TaskPersistence.load_all_tasks()

    assert loaded == {"task-1": task_data}


def test_scan_and_rebuild_tasks_restores_completed_task_from_outputs(
    tmp_path, monkeypatch
):
    outputs_dir = tmp_path / "outputs"
    data_file = tmp_path / "tasks_data.json"
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
    monkeypatch.setattr(task_persistence_module, "TASKS_DATA_FILE", data_file)

    rebuilt = task_persistence_module.TaskPersistence.scan_and_rebuild_tasks()

    assert "task-1" in rebuilt
    assert rebuilt["task-1"]["status"] == "completed"
    assert rebuilt["task-1"]["result"]["files"]["json"].endswith("task-1.json")
    assert data_file.exists()
