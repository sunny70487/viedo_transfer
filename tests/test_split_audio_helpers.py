from backend.shared.split_audio_helpers import parse_audio_duration


def test_parse_audio_duration_uses_ffmpeg_duration_when_available():
    stderr_text = "Duration: 00:01:30.50, start: 0.000000, bitrate: 128 kb/s"

    duration = parse_audio_duration(stderr_text)

    assert duration == 90.5


def test_parse_audio_duration_returns_none_when_ffmpeg_output_has_no_duration():
    stderr_text = "Input #0, wav, from 'sample.wav':\nMetadata:\n  encoder: Lavf"

    duration = parse_audio_duration(stderr_text)

    assert duration is None
