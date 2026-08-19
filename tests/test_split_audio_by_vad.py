import backend.shared.split_audio_helpers as sah


def test_split_audio_by_vad_returns_start_offset_for_each_segment(monkeypatch):
    monkeypatch.setattr(
        sah, "detect_speech_segments", lambda path: [(2.0, 10.0), (20.0, 28.0)]
    )
    monkeypatch.setattr(
        sah, "_extract_span", lambda src, start, end, out: out
    )

    segments, temp_dir, used_vad = sah.split_audio_by_vad(
        "audio.wav", max_duration=30.0, verbose=False
    )

    assert used_vad is True
    assert [round(start, 2) for _, start in segments] == [2.0]
    assert temp_dir is not None


def test_split_audio_by_vad_offsets_match_chunk_starts(monkeypatch):
    monkeypatch.setattr(
        sah,
        "detect_speech_segments",
        lambda path: [(0.0, 25.0), (30.0, 50.0), (60.0, 75.0)],
    )
    monkeypatch.setattr(sah, "_extract_span", lambda src, start, end, out: out)

    segments, _temp_dir, used_vad = sah.split_audio_by_vad(
        "audio.wav", max_duration=30.0, verbose=False
    )

    assert used_vad is True
    expected = [start for start, _ in sah.plan_vad_chunks(
        [(0.0, 25.0), (30.0, 50.0), (60.0, 75.0)], max_duration=30.0
    )]
    assert [start for _, start in segments] == expected


def test_split_audio_by_vad_falls_back_to_fixed_split_when_vad_unavailable(
    monkeypatch,
):
    monkeypatch.setattr(sah, "detect_speech_segments", lambda path: None)
    monkeypatch.setattr(
        sah,
        "split_audio",
        lambda *a, **kw: (["seg_000.flac", "seg_001.flac"], "/tmp/x"),
    )

    segments, temp_dir, used_vad = sah.split_audio_by_vad(
        "audio.wav", max_duration=30.0, verbose=False
    )

    assert used_vad is False
    assert segments == [("seg_000.flac", 0.0), ("seg_001.flac", 30.0)]
    assert temp_dir == "/tmp/x"


def test_split_audio_by_vad_falls_back_when_no_speech_detected(monkeypatch):
    monkeypatch.setattr(sah, "detect_speech_segments", lambda path: [])
    monkeypatch.setattr(
        sah, "split_audio", lambda *a, **kw: (["seg_000.flac"], "/tmp/y")
    )

    segments, _temp_dir, used_vad = sah.split_audio_by_vad(
        "audio.wav", max_duration=30.0, verbose=False
    )

    assert used_vad is False
    assert segments == [("seg_000.flac", 0.0)]


def test_split_audio_by_vad_skips_spans_that_fail_extraction(monkeypatch):
    monkeypatch.setattr(
        sah, "detect_speech_segments", lambda path: [(0.0, 10.0), (40.0, 50.0)]
    )
    calls = {"n": 0}

    def flaky_extract(src, start, end, out):
        calls["n"] += 1
        return None if calls["n"] == 1 else out

    monkeypatch.setattr(sah, "_extract_span", flaky_extract)

    segments, _temp_dir, used_vad = sah.split_audio_by_vad(
        "audio.wav", max_duration=30.0, verbose=False
    )

    assert used_vad is True
    assert [start for _, start in segments] == [40.0]
