from backend.shared.firered_vad import plan_vad_chunks


def test_plan_vad_chunks_groups_adjacent_segments_under_max_duration():
    segments = [(0.0, 5.0), (6.0, 10.0), (11.0, 15.0)]

    chunks = plan_vad_chunks(segments, max_duration=20.0)

    assert chunks == [(0.0, 15.0)]


def test_plan_vad_chunks_starts_new_chunk_when_max_duration_exceeded():
    segments = [(0.0, 20.0), (21.0, 40.0)]

    chunks = plan_vad_chunks(segments, max_duration=25.0)

    assert chunks == [(0.0, 20.0), (21.0, 40.0)]


def test_plan_vad_chunks_cuts_at_silence_not_at_fixed_interval():
    # Speech runs 0-28s then a gap, then 30-35s. A fixed 30s split would cut
    # mid-word at exactly 30.0; VAD planning must cut inside the 28-30s silence.
    segments = [(0.0, 28.0), (30.0, 35.0)]

    chunks = plan_vad_chunks(segments, max_duration=30.0)

    assert chunks == [(0.0, 28.0), (30.0, 35.0)]


def test_plan_vad_chunks_splits_single_segment_longer_than_max_duration():
    segments = [(0.0, 75.0)]

    chunks = plan_vad_chunks(segments, max_duration=30.0)

    assert len(chunks) == 3
    assert chunks[0][0] == 0.0
    assert chunks[-1][1] == 75.0
    for start, end in chunks:
        assert end - start <= 30.0
    # Contiguous: no audio dropped between parts.
    for (_, prev_end), (next_start, _) in zip(chunks, chunks[1:]):
        assert prev_end == next_start


def test_plan_vad_chunks_returns_empty_list_for_no_speech():
    assert plan_vad_chunks([], max_duration=30.0) == []


def test_plan_vad_chunks_keeps_chunks_within_max_duration():
    segments = [(0.0, 12.0), (13.0, 25.0), (26.0, 38.0), (39.0, 50.0)]

    chunks = plan_vad_chunks(segments, max_duration=30.0)

    for start, end in chunks:
        assert end - start <= 30.0
    assert chunks[0][0] == 0.0
    assert chunks[-1][1] == 50.0
