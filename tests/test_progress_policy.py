from backend.services.progress_policy import (
    build_split_progress_message,
    default_progress_messages,
    next_progress_state,
)


def test_next_progress_state_advances_toward_target_progress():
    progress, message = next_progress_state(
        start_progress=30.0,
        target_progress=95.0,
        total_steps=13,
        step=0,
        is_split_mode=False,
    )

    assert progress > 30.0
    assert progress <= 95.0
    assert message in default_progress_messages()


def test_next_progress_state_reaches_target_on_final_step():
    progress, _ = next_progress_state(
        start_progress=30.0,
        target_progress=95.0,
        total_steps=10,
        step=9,
        is_split_mode=False,
    )

    assert progress == 95.0


def test_next_progress_state_never_exceeds_target_past_final_step():
    progress, _ = next_progress_state(
        start_progress=30.0,
        target_progress=95.0,
        total_steps=10,
        step=15,
        is_split_mode=False,
    )

    assert progress == 95.0


def test_split_progress_message_reports_segment_counts():
    assert build_split_progress_message(3, 10) == "正在處理分段 3/10 (30.0%)"


def test_next_progress_state_uses_split_mode_message():
    progress, message = next_progress_state(
        start_progress=30.0,
        target_progress=95.0,
        total_steps=10,
        step=1,
        is_split_mode=True,
    )

    # step 1 of 10 => 2/10 of the 30->95 span => 30 + 0.2 * 65
    assert progress == 43.0
    assert message == "正在處理分段 2/10 (20.0%)"


def test_next_progress_state_only_rotates_message_every_third_step():
    _, message = next_progress_state(
        start_progress=30.0,
        target_progress=95.0,
        total_steps=10,
        step=1,
        is_split_mode=False,
    )

    assert message is None
