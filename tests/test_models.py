import pytest
from pydantic import ValidationError

from backend.models import Subtitle, SubtitleMetadata, Word


def test_subtitle_strips_surrounding_whitespace():
    subtitle = Subtitle(
        index=0,
        start_time=0.0,
        end_time=1.5,
        text="  測試字幕  ",
        confidence=None,
        words=None,
    )

    assert subtitle.text == "測試字幕"


def test_subtitle_rejects_whitespace_only_text():
    with pytest.raises(ValidationError, match="字幕文字不能為空"):
        Subtitle(
            index=0,
            start_time=0.0,
            end_time=1.5,
            text="   ",
            confidence=None,
            words=None,
        )


def test_subtitle_clamps_word_timings_to_subtitle_bounds():
    subtitle = Subtitle(
        index=0,
        start_time=1.0,
        end_time=3.0,
        text="詞級時間戳",
        confidence=None,
        words=[Word(word="測試", start=0.5, end=3.5, confidence=None)],
    )

    assert subtitle.words is not None
    assert subtitle.words[0].start == 1.0
    assert subtitle.words[0].end == 3.0


def test_subtitle_metadata_defaults_none_language_to_unknown():
    metadata = SubtitleMetadata(
        language=None,
        model_used=None,
        total_duration=None,
        total_segments=None,
        video_info=None,
        transcription_settings=None,
    )

    assert metadata.language == "unknown"
