import importlib
import json
import sys
import types
from types import SimpleNamespace

from fastapi import FastAPI
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


def test_load_subtitle_data_reads_transcription_json(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    json_path = tmp_path / "task-1.json"
    json_path.write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "start": 0.0,
                        "end": 1.5,
                        "text": " 測試字幕 ",
                        "avg_logprob": -0.1,
                    }
                ],
                "language": "zh",
                "model_name": "qwen3-asr-1.7b",
                "duration": 1.5,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    tasks = {"task-1": _build_completed_task(json_path, tmp_path)}

    collection = subtitle_api.SubtitleService.load_subtitle_data("task-1", tasks)

    assert collection.task_id == "task-1"
    assert len(collection.subtitles) == 1
    assert collection.subtitles[0].text == "測試字幕"
    assert collection.metadata.language == "zh"


def _resegment_client(tmp_path, monkeypatch, segments):
    subtitle_api = _load_subtitle_api_module()
    import backend.shared.subtitle_postprocess as sp

    monkeypatch.setattr(sp, "predict_break_hints", lambda ws: {})
    json_path = tmp_path / "task-1.json"
    json_path.write_text(
        json.dumps({"segments": segments}, ensure_ascii=False), encoding="utf-8"
    )
    updated_path = tmp_path / "task-1_updated.json"
    updated_path.write_text(json.dumps({"segments": []}), encoding="utf-8")
    task = _build_completed_task(json_path, tmp_path)
    task.result["files"]["updated_json"] = str(updated_path)
    subtitle_api.set_tasks_storage({"task-1": task})

    app = FastAPI()
    app.include_router(subtitle_api.router)
    return TestClient(app), updated_path


def _word(ch, i):
    return {"word": ch, "start": i * 0.2, "end": i * 0.2 + 0.2}


def test_resegment_rebuilds_lines_from_original_words(tmp_path, monkeypatch):
    first = "當前線程的線程環境"
    second = "塊裡面的信息"
    segments = [
        {"start": 0.0, "end": 1.8, "text": first,
         "words": [_word(ch, i) for i, ch in enumerate(first)]},
        {"start": 1.8, "end": 3.0, "text": second,
         "words": [_word(ch, i + len(first)) for i, ch in enumerate(second)]},
    ]
    client, updated_path = _resegment_client(tmp_path, monkeypatch, segments)

    response = client.post(
        "/api/subtitles/task-1/resegment", json={"glossary": "線程環境塊"}
    )

    assert response.status_code == 200
    subs = response.json()["subtitles"]
    assert "".join(s["text"] for s in subs) == "當前線程的線程環境塊裡面的信息"
    assert any("線程環境塊" in s["text"] for s in subs)
    assert [s["index"] for s in subs] == list(range(len(subs)))
    assert all(s["words"] for s in subs)
    assert json.loads(updated_path.read_text())["segments"] == []


def test_resegment_rejects_task_without_word_timestamps(tmp_path, monkeypatch):
    segments = [{"start": 0.0, "end": 1.0, "text": "沒有字級時間"}]
    client, _ = _resegment_client(tmp_path, monkeypatch, segments)

    response = client.post("/api/subtitles/task-1/resegment", json={})

    assert response.status_code == 400


def test_head_subtitles_returns_404_for_missing_task(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    subtitle_api.set_tasks_storage({})

    app = FastAPI()
    app.include_router(subtitle_api.router)
    client = TestClient(app)

    response = client.head("/api/subtitles/missing-task")

    assert response.status_code == 404
