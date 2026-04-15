from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.shared.video_utils import (
    build_mp4_conversion_command,
    is_video_file,
    prepare_source_video_for_preview,
)


def test_is_video_file_returns_true_for_supported_video_extension():
    assert is_video_file("demo.webm") is True


def test_is_video_file_returns_false_for_audio_extension():
    assert is_video_file("demo.wav") is False


def test_build_mp4_conversion_command_matches_expected_ffmpeg_args(tmp_path):
    source = tmp_path / "clip.webm"
    target = tmp_path / "clip_converted.mp4"

    command = build_mp4_conversion_command(source, target)

    assert command == [
        "ffmpeg",
        "-i",
        str(source),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        "-y",
        str(target),
    ]


def test_build_mp4_conversion_command_accepts_path_objects(tmp_path):
    source = Path(tmp_path / "clip.mov")
    target = Path(tmp_path / "clip_converted.mp4")

    command = build_mp4_conversion_command(source, target)

    assert command[2] == str(source)
    assert command[-1] == str(target)


# ── prepare_source_video_for_preview ──────────────────────────────────────

def test_prepare_source_video_returns_none_for_audio_file(tmp_path):
    audio = tmp_path / "track.mp3"
    audio.touch()
    result = prepare_source_video_for_preview(audio, tmp_path, "task1")
    assert result is None


def test_prepare_source_video_returns_source_for_mp4(tmp_path):
    video = tmp_path / "clip.mp4"
    video.touch()
    result = prepare_source_video_for_preview(video, tmp_path, "task1")
    assert result == str(video)


def test_prepare_source_video_returns_source_for_webm(tmp_path):
    video = tmp_path / "clip.webm"
    video.touch()
    result = prepare_source_video_for_preview(video, tmp_path, "task1")
    assert result == str(video)


def test_prepare_source_video_remux_success(tmp_path):
    source = tmp_path / "clip.mkv"
    source.touch()
    preview_path = tmp_path / "task42_preview.mp4"

    def fake_run(cmd, **kwargs):
        preview_path.write_bytes(b"fake mp4 data")
        m = MagicMock()
        m.returncode = 0
        return m

    with patch("backend.shared.video_utils.subprocess.run", side_effect=fake_run):
        result = prepare_source_video_for_preview(
            source, tmp_path, "task42"
        )

    assert result == str(preview_path)


def test_prepare_source_video_falls_back_to_transcode_when_remux_fails(tmp_path):
    source = tmp_path / "clip.avi"
    source.touch()
    preview_path = tmp_path / "task99_preview.mp4"
    call_count = {"n": 0}

    def fake_run(cmd, **kwargs):
        m = MagicMock()
        call_count["n"] += 1
        if call_count["n"] == 1:
            # remux attempt: fail
            m.returncode = 1
            m.stderr = b""
        else:
            # transcode attempt: succeed
            preview_path.write_bytes(b"fake mp4 data")
            m.returncode = 0
        return m

    with patch("backend.shared.video_utils.subprocess.run", side_effect=fake_run):
        result = prepare_source_video_for_preview(
            source, tmp_path, "task99"
        )

    assert result == str(preview_path)
    assert call_count["n"] == 2


def test_prepare_source_video_returns_none_when_both_fail(tmp_path):
    source = tmp_path / "clip.mov"
    source.touch()

    def fake_run(cmd, **kwargs):
        m = MagicMock()
        m.returncode = 1
        m.stderr = b""
        return m

    with patch("backend.shared.video_utils.subprocess.run", side_effect=fake_run):
        result = prepare_source_video_for_preview(
            source, tmp_path, "task77"
        )

    assert result is None
