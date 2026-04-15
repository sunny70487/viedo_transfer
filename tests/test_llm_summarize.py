import json
from unittest.mock import MagicMock, patch

from backend.shared.llm_postprocess import summarize_subtitles, _parse_chapter_time


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
            {"time": "00:00", "title": "簡介"},
            {"time": "00:05", "title": "Pod 概念"},
            {"time": "00:10", "title": "Deployment"},
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
    assert result["chapters"][1]["time"] == 5.0
    assert result["chapters"][1]["title"] == "Pod 概念"


def test_summarize_subtitles_parses_mmss_timestamps_correctly():
    """LLM returns MM:SS strings; verify conversion to seconds."""
    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps({
        "summary": "測試摘要",
        "chapters": [
            {"time": "04:42", "title": "章節一"},
            {"time": "12:30", "title": "章節二"},
            {"time": "27:59", "title": "章節三"},
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

    assert result["chapters"][0]["time"] == 4 * 60 + 42   # 282
    assert result["chapters"][1]["time"] == 12 * 60 + 30  # 750
    assert result["chapters"][2]["time"] == 27 * 60 + 59  # 1679


# ── _parse_chapter_time unit tests ────────────────────────────────────────

def test_parse_chapter_time_mmss():
    assert _parse_chapter_time("04:42") == 282.0


def test_parse_chapter_time_hhmmss():
    assert _parse_chapter_time("01:04:42") == 3600 + 282.0


def test_parse_chapter_time_numeric():
    assert _parse_chapter_time(154.5) == 154.5


def test_parse_chapter_time_invalid_returns_zero():
    assert _parse_chapter_time("bad") == 0.0


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
