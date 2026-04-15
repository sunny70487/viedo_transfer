import json
from unittest.mock import MagicMock, patch

from backend.shared.llm_postprocess import summarize_subtitles


def _make_segments():
    return [
        {"start": 0.0, "end": 5.0, "text": "大家好，今天我們要討論 Kubernetes。"},
        {"start": 5.0, "end": 10.0, "text": "首先介紹 Pod 的概念。"},
        {"start": 10.0, "end": 15.0, "text": "接下來是 Deployment 的用法。"},
    ]


def test_summarize_subtitles_returns_summary_and_chapters():
    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps({
        "summary": "本影片介紹 Kubernetes 基礎概念。",
        "chapters": [
            {"time": 0.0, "title": "簡介"},
            {"time": 5.0, "title": "Pod 概念"},
            {"time": 10.0, "title": "Deployment"},
        ]
    })

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    with patch("openai.OpenAI", return_value=mock_client):
        result = summarize_subtitles(
            _make_segments(),
            api_key="test-key",
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
        )

    assert result["summary"] == "本影片介紹 Kubernetes 基礎概念。"
    assert len(result["chapters"]) == 3
    assert result["chapters"][0]["time"] == 0.0
    assert result["chapters"][1]["title"] == "Pod 概念"


def test_summarize_subtitles_handles_invalid_json_gracefully():
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "not json at all"

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    with patch("openai.OpenAI", return_value=mock_client):
        result = summarize_subtitles(
            _make_segments(),
            api_key="test-key",
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
        )

    assert "not json" in result["summary"]
    assert result["chapters"] == []
