from types import SimpleNamespace

from backend.services.transcription_progress import (
    build_status_callback,
    estimate_total_steps,
    finalize_task_failure,
)


def test_estimate_total_steps_uses_segment_count_when_split_enabled():
    task = SimpleNamespace()

    steps = estimate_total_steps(
        split_segments=True,
        segment_duration=30,
        file_path="demo.wav",
        get_duration=lambda path: 95.0,
        get_file_size_mb=lambda path: 1.0,
    )

    assert steps == 3


def test_estimate_total_steps_falls_back_to_file_size_when_duration_fails():
    steps = estimate_total_steps(
        split_segments=True,
        segment_duration=30,
        file_path="demo.wav",
        get_duration=lambda path: (_ for _ in ()).throw(RuntimeError("boom")),
        get_file_size_mb=lambda path: 55.0,
    )

    assert steps == 11


def test_build_status_callback_updates_message_and_persists():
    task = SimpleNamespace(message="old")
    saved = []

    callback = build_status_callback(
        task=task, save_task=lambda current: saved.append(current.message)
    )
    callback("new message")

    assert task.message == "new message"
    assert saved == ["new message"]


def test_finalize_task_failure_updates_task_state_and_error():
    task = SimpleNamespace(status="processing", message="", error=None, end_time=None)

    finalize_task_failure(task=task, error=RuntimeError("failed"), now=456.0)

    assert task.status == "failed"
    assert task.message == "轉錄失敗: failed"
    assert task.error == "failed"
    assert task.end_time == 456.0
