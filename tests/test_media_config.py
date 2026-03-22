from backend.shared.media_config import (
    SUPPORTED_MEDIA_EXTENSIONS,
    VIDEO_EXTENSIONS,
    get_media_type,
    is_supported_media_file,
)


def test_supported_media_extensions_include_audio_and_video_types():
    assert ".mp3" in SUPPORTED_MEDIA_EXTENSIONS
    assert ".webm" in SUPPORTED_MEDIA_EXTENSIONS


def test_video_extensions_only_include_video_formats():
    assert ".mp4" in VIDEO_EXTENSIONS
    assert ".wav" not in VIDEO_EXTENSIONS


def test_is_supported_media_file_checks_extension_case_insensitively():
    assert is_supported_media_file("Demo.WEBM") is True
    assert is_supported_media_file("notes.txt") is False


def test_get_media_type_falls_back_to_octet_stream():
    assert get_media_type("archive.bin") == "application/octet-stream"


def test_get_media_type_returns_known_video_type():
    assert get_media_type("clip.webm") == "video/webm"
