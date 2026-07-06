import importlib
import io
import json
import sys
import zipfile
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base, FolderRecord, TaskRecord


def _load_folder_api():
    sys.modules.pop("backend.services.folder_api", None)
    return importlib.import_module("backend.services.folder_api")


def _make_test_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def _write_json(path, text="subtitle text"):
    path.write_text(
        json.dumps(
            {
                "segments": [{"start": 0.0, "end": 1.5, "text": text}],
                "language": "zh",
                "model_name": "qwen3-asr-1.7b",
                "duration": 1.5,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _task_record(task_id, folder_id, sort_order):
    return TaskRecord(
        id=task_id,
        status="completed",
        folder_id=folder_id,
        sort_order=sort_order,
        start_time=1.0,
    )


def _completed_task(json_path, output_dir, source_name):
    return SimpleNamespace(
        status="completed",
        source_name=source_name,
        result={"files": {"json": str(json_path)}, "output_dir": str(output_dir)},
        start_time=1.0,
        end_time=2.0,
    )


def _make_client(folder_api):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(folder_api.router)
    return TestClient(app)


def _add_folder(session, fid, name, parent_id=None, sort_order=0.0):
    session.add(FolderRecord(
        id=fid, name=name, parent_id=parent_id, sort_order=sort_order,
        created_at=1.0, updated_at=1.0,
    ))


def _get(folder_api, folder_id, fmt):
    return _make_client(folder_api).get(
        f"/api/folders/{folder_id}/download-subtitles?format={fmt}"
    )


def test_safe_filename_strips_path_and_illegal_chars():
    folder_api = _load_folder_api()
    assert folder_api._safe_filename("a/b\\c:d*e?.mp4") == "a_b_c_d_e_.mp4"
    assert folder_api._safe_filename("") == ""


def test_unique_in_zip_adds_suffix_on_collision():
    folder_api = _load_folder_api()
    used = set()
    a = folder_api._unique_zip_path(used, "", "name.srt")
    b = folder_api._unique_zip_path(used, "", "name.srt")
    c = folder_api._unique_zip_path(used, "sub", "name.srt")
    assert a == "name.srt"
    assert b == "name (2).srt"
    assert c == "sub/name.srt"


def test_build_relative_paths_maps_root_and_descendants():
    folder_api = _load_folder_api()
    rows = [
        ("root", "Root", None),
        ("childA", "A", "root"),
        ("grandB", "B", "childA"),
        ("other", "Other", None),
    ]
    paths = folder_api._build_relative_paths(rows, "root")
    assert paths["root"] == ""
    assert paths["childA"] == "A"
    assert paths["grandB"] == "A/B"
    assert "other" not in paths


def test_download_folder_subtitles_includes_subfolders_with_structure(
    tmp_path, monkeypatch
):
    folder_api = _load_folder_api()
    subtitle_api = importlib.import_module("backend.services.subtitle_api")

    session_factory = _make_test_session(tmp_path)
    monkeypatch.setattr(folder_api, "SessionLocal", session_factory)

    out = tmp_path / "outputs"
    out.mkdir()
    j1 = tmp_path / "t1.json"
    _write_json(j1, "root task")
    j2 = tmp_path / "t2.json"
    _write_json(j2, "child task")

    with session_factory() as s:
        _add_folder(s, "root", "Root")
        _add_folder(s, "childA", "A", parent_id="root", sort_order=1.0)
        s.add(_task_record("t1", "root", 0.0))
        s.add(_task_record("t2", "childA", 0.0))
        s.commit()

    tasks = {
        "t1": _completed_task(j1, out, "video-one"),
        "t2": _completed_task(j2, out, "video-two"),
    }
    folder_api.set_folder_task_registry(tasks)
    subtitle_api.set_tasks_storage(tasks)

    resp = _get(folder_api, "root", "srt")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = set(zf.namelist())
    assert "video-one.srt" in names
    assert "A/video-two.srt" in names


def test_download_converts_format_not_in_files(tmp_path, monkeypatch):
    folder_api = _load_folder_api()
    subtitle_api = importlib.import_module("backend.services.subtitle_api")
    session_factory = _make_test_session(tmp_path)
    monkeypatch.setattr(folder_api, "SessionLocal", session_factory)

    out = tmp_path / "outputs"
    out.mkdir()
    j1 = tmp_path / "t1.json"
    _write_json(j1)
    with session_factory() as s:
        _add_folder(s, "root", "Root")
        s.add(_task_record("t1", "root", 0.0))
        s.commit()

    tasks = {"t1": _completed_task(j1, out, "clip")}
    folder_api.set_folder_task_registry(tasks)
    subtitle_api.set_tasks_storage(tasks)

    resp = _get(folder_api, "root", "vtt")
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    assert "clip.vtt" in zf.namelist()
    assert zf.read("clip.vtt").decode("utf-8").startswith("WEBVTT")


def test_download_dedupes_same_source_name(tmp_path, monkeypatch):
    folder_api = _load_folder_api()
    subtitle_api = importlib.import_module("backend.services.subtitle_api")
    session_factory = _make_test_session(tmp_path)
    monkeypatch.setattr(folder_api, "SessionLocal", session_factory)

    out = tmp_path / "outputs"
    out.mkdir()
    j1 = tmp_path / "t1.json"
    _write_json(j1)
    j2 = tmp_path / "t2.json"
    _write_json(j2)
    with session_factory() as s:
        _add_folder(s, "root", "Root")
        s.add(_task_record("t1", "root", 0.0))
        s.add(_task_record("t2", "root", 1.0))
        s.commit()

    tasks = {
        "t1": _completed_task(j1, out, "same"),
        "t2": _completed_task(j2, out, "same"),
    }
    folder_api.set_folder_task_registry(tasks)
    subtitle_api.set_tasks_storage(tasks)

    resp = _get(folder_api, "root", "srt")
    assert resp.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(resp.content)).namelist()
    assert "same.srt" in names
    assert "same (2).srt" in names


def test_download_empty_folder_returns_404(tmp_path, monkeypatch):
    folder_api = _load_folder_api()
    subtitle_api = importlib.import_module("backend.services.subtitle_api")
    session_factory = _make_test_session(tmp_path)
    monkeypatch.setattr(folder_api, "SessionLocal", session_factory)
    with session_factory() as s:
        _add_folder(s, "root", "Root")
        s.commit()
    folder_api.set_folder_task_registry({})
    subtitle_api.set_tasks_storage({})
    resp = _get(folder_api, "root", "srt")
    assert resp.status_code == 404


def test_download_unsupported_format_returns_400(tmp_path, monkeypatch):
    folder_api = _load_folder_api()
    session_factory = _make_test_session(tmp_path)
    monkeypatch.setattr(folder_api, "SessionLocal", session_factory)
    with session_factory() as s:
        _add_folder(s, "root", "Root")
        s.commit()
    resp = _get(folder_api, "root", "doc")
    assert resp.status_code == 400


def test_download_missing_folder_returns_404(tmp_path, monkeypatch):
    folder_api = _load_folder_api()
    session_factory = _make_test_session(tmp_path)
    monkeypatch.setattr(folder_api, "SessionLocal", session_factory)
    resp = _get(folder_api, "nope", "srt")
    assert resp.status_code == 404
