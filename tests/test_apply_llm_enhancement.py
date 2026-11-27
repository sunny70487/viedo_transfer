import json

import backend.app as app_module
from backend.app import TranscriptionRequest
from backend.shared import llm_postprocess, llm_segmentation


def _write_outputs(tmp_path):
    words = [
        {"word": ch, "start": i * 0.2, "end": (i + 1) * 0.2}
        for i, ch in enumerate("另一個非常重要")
    ]
    data = {
        "text": "另一個非常重要",
        "segments": [
            {"id": 0, "start": 0.0, "end": 1.0, "text": "另一個非常",
             "words": words[:5]},
            {"id": 1, "start": 1.0, "end": 1.4, "text": "重要",
             "words": words[5:]},
        ],
    }
    json_path = tmp_path / "out.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    srt_path = tmp_path / "out.srt"
    srt_path.write_text("", encoding="utf-8")
    return {"json": str(json_path), "srt": str(srt_path)}


def test_apply_llm_enhancement_resegments_before_enhancing(tmp_path, monkeypatch):
    results = _write_outputs(tmp_path)
    seen = {}

    def fake_resegment(segments, **kwargs):
        seen["resegment_in"] = [s["text"] for s in segments]
        seen["resegment_model"] = kwargs["model"]
        return [{"id": 0, "start": 0.0, "end": 1.4, "text": "另一個非常重要"}]

    def fake_enhance(segments, **kwargs):
        seen["enhance_in"] = [s["text"] for s in segments]
        return segments

    monkeypatch.setattr(llm_segmentation, "resegment_subtitles", fake_resegment)
    monkeypatch.setattr(llm_postprocess, "enhance_subtitles", fake_enhance)

    request = TranscriptionRequest(
        llm_enhance=True, llm_api_key="k", llm_model="my-model"
    )
    app_module._apply_llm_enhancement(results, request, None)

    assert seen["resegment_in"] == ["另一個非常", "重要"]
    assert seen["resegment_model"] == "my-model"
    assert seen["enhance_in"] == ["另一個非常重要"]
    srt = (tmp_path / "out.srt").read_text(encoding="utf-8")
    assert "另一個非常重要" in srt
