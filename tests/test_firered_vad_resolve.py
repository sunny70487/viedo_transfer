import pytest

import backend.shared.firered_vad as fv


@pytest.fixture(autouse=True)
def reset_download_cache(monkeypatch):
    """The download result is cached process-wide; isolate it per test."""
    monkeypatch.setattr(fv, "_DOWNLOAD_ATTEMPTED", False)
    monkeypatch.setattr(fv, "_DOWNLOADED_DIR", None)


def test_prefers_explicit_env_override(monkeypatch, tmp_path):
    weights = tmp_path / "VAD"
    weights.mkdir()
    (weights / "model.pth.tar").write_bytes(b"x")
    monkeypatch.setenv("FIRERED_VAD_MODEL_DIR", str(weights))

    assert fv.resolve_model_dir() == str(weights)


def test_prefers_local_dir_when_it_exists(monkeypatch, tmp_path):
    monkeypatch.delenv("FIRERED_VAD_MODEL_DIR", raising=False)
    local = tmp_path / "pretrained_models" / "FireRedVAD" / "VAD"
    local.mkdir(parents=True)
    (local / "model.pth.tar").write_bytes(b"x")
    monkeypatch.setattr(fv, "_DEFAULT_MODEL_DIR", str(local))
    monkeypatch.setattr(
        fv, "_download_model_dir", lambda: (_ for _ in ()).throw(AssertionError)
    )

    assert fv.resolve_model_dir() == str(local)


def test_downloads_when_no_local_weights(monkeypatch, tmp_path):
    monkeypatch.delenv("FIRERED_VAD_MODEL_DIR", raising=False)
    monkeypatch.setattr(fv, "_DEFAULT_MODEL_DIR", str(tmp_path / "absent"))
    fetched = tmp_path / "hf_cache" / "VAD"
    fetched.mkdir(parents=True)
    monkeypatch.setattr(fv, "_download_model_dir", lambda: str(fetched))

    assert fv.resolve_model_dir() == str(fetched)


def test_returns_none_when_download_fails(monkeypatch, tmp_path):
    monkeypatch.delenv("FIRERED_VAD_MODEL_DIR", raising=False)
    monkeypatch.setattr(fv, "_DEFAULT_MODEL_DIR", str(tmp_path / "absent"))
    monkeypatch.setattr(fv, "_download_model_dir", lambda: None)

    assert fv.resolve_model_dir() is None


def test_is_available_false_when_no_model_dir(monkeypatch):
    monkeypatch.setattr(fv, "resolve_model_dir", lambda: None)

    assert fv.is_available() is False


def test_detect_returns_none_when_unavailable(monkeypatch):
    monkeypatch.setattr(fv, "is_available", lambda: False)

    assert fv.detect_speech_segments("any.wav") is None


def test_download_is_attempted_only_once(monkeypatch, tmp_path):
    monkeypatch.delenv("FIRERED_VAD_MODEL_DIR", raising=False)
    monkeypatch.setattr(fv, "_DEFAULT_MODEL_DIR", str(tmp_path / "absent"))
    calls = {"n": 0}

    def counting():
        calls["n"] += 1
        return None

    monkeypatch.setattr(fv, "_download_model_dir", counting)
    fv.resolve_model_dir()
    fv.resolve_model_dir()

    assert calls["n"] == 1
