import pytest
from pydantic import ValidationError

from backend.models import RetranscribeRequest


def _req(**settings):
    return RetranscribeRequest(
        task_id="t1", start_time=0.0, end_time=5.0, subtitle_index=0,
        model_settings=settings,
    )


def test_model_settings_accepts_hotwords():
    req = _req(hotwords="shellcode\nVirtualAlloc")

    assert req.model_settings["hotwords"] == "shellcode\nVirtualAlloc"


def test_model_settings_accepts_context():
    req = _req(context="逆向工程課程")

    assert req.model_settings["context"] == "逆向工程課程"


def test_model_settings_still_rejects_unknown_keys():
    with pytest.raises(ValidationError):
        _req(not_a_real_setting=1)
