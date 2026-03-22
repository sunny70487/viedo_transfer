from pathlib import Path

from backend.shared.video_utils import build_mp4_conversion_command, is_video_file


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
