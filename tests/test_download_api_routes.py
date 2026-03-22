import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _load_download_api_module():
    sys.modules.pop("backend.services.download_api", None)
    return importlib.import_module("backend.services.download_api")


def _build_completed_task(file_map):
    return SimpleNamespace(status="completed", result={"files": file_map})


def test_download_route_serves_direct_file_type_match(tmp_path):
    download_api = _load_download_api_module()
    srt_path = tmp_path / "task-1.srt"
    srt_path.write_text("subtitle", encoding="utf-8")

    download_api.set_download_task_registry(
        {"task-1": _build_completed_task({"srt": str(srt_path)})}
    )

    app = FastAPI()
    app.include_router(download_api.router)
    client = TestClient(app)

    response = client.get("/download/task-1/srt")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/octet-stream"
    ) or response.headers["content-type"].startswith("text/plain")


def test_download_route_resolves_video_alias_to_existing_video_file(tmp_path):
    download_api = _load_download_api_module()
    video_path = tmp_path / "clip.webm"
    video_path.write_bytes(b"video-bytes")

    download_api.set_download_task_registry(
        {"task-1": _build_completed_task({"converted": str(video_path)})}
    )

    app = FastAPI()
    app.include_router(download_api.router)
    client = TestClient(app)

    response = client.get("/download/task-1/video")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("video/webm")


def test_download_route_returns_404_for_missing_result_file():
    download_api = _load_download_api_module()
    download_api.set_download_task_registry({})

    app = FastAPI()
    app.include_router(download_api.router)
    client = TestClient(app)

    response = client.get("/download/missing/srt")

    assert response.status_code == 404
    assert response.json() == {"error": "任務不存在"}
