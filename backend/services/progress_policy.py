def default_progress_messages():
    return [
        "正在處理音頻...",
        "正在分析語音...",
        "正在生成轉錄...",
        "正在處理時間戳...",
        "正在優化結果...",
    ]


def build_split_progress_message(completed_segments, total_steps):
    return (
        f"正在處理分段 {completed_segments}/{total_steps} "
        f"({(completed_segments / total_steps * 100):.1f}%)"
    )


def next_progress_state(
    *,
    start_progress,
    target_progress,
    total_steps,
    step,
    is_split_mode,
):
    fraction = (step + 1) / total_steps
    next_progress = min(target_progress, start_progress + fraction * (target_progress - start_progress))

    if is_split_mode:
        completed_segments = step + 1
        return next_progress, build_split_progress_message(
            completed_segments, total_steps
        )

    if step % 3 == 0:
        messages = default_progress_messages()
        return next_progress, messages[step % len(messages)]

    return next_progress, None
