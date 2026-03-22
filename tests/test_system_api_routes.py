import importlib
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _load_system_api_module():
    sys.modules.pop("backend.services.system_api", None)
    return importlib.import_module("backend.services.system_api")


def test_gpu_info_route_delegates_to_check_gpu(monkeypatch):
    system_api = _load_system_api_module()

    monkeypatch.setattr(system_api, "check_gpu", lambda: {"available": False})

    app = FastAPI()
    app.include_router(system_api.router)
    client = TestClient(app)

    response = client.get("/gpu-info")

    assert response.status_code == 200
    assert response.json() == {"available": False}


def test_system_directories_returns_current_directory_on_non_windows(monkeypatch):
    system_api = _load_system_api_module()

    monkeypatch.setattr(system_api.platform, "system", lambda: "Linux")
    monkeypatch.setattr(system_api.os, "getcwd", lambda: str(Path("/workspace")))

    app = FastAPI()
    app.include_router(system_api.router)
    client = TestClient(app)

    response = client.get("/system/directories")

    assert response.status_code == 200
    body = response.json()
    expected = os.getcwd()
    assert body["current"] == expected
    assert expected in body["directories"]


def test_system_subdirectories_lists_only_directories(tmp_path, monkeypatch):
    system_api = _load_system_api_module()

    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")

    app = FastAPI()
    app.include_router(system_api.router)
    client = TestClient(app)

    response = client.get("/system/subdirectories", params={"path": str(tmp_path)})

    assert response.status_code == 200
    names = {item["name"] for item in response.json()["subdirectories"]}
    assert names == {"alpha", "beta"}
