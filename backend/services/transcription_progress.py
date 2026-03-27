def estimate_total_steps(
    *,
    split_segments,
    segment_duration,
    file_path,
    get_duration,
    get_file_size_mb,
):
    if split_segments:
        try:
            audio_duration = get_duration(file_path)
            return max(1, int(audio_duration / segment_duration))
        except Exception:
            file_size_mb = get_file_size_mb(file_path)
            return max(10, int(file_size_mb / 5))

    file_size_mb = get_file_size_mb(file_path)
    return max(10, int(file_size_mb / 5))


def build_status_callback(*, task, save_task):
    def status_callback(message, progress=None):
        task.message = message
        if progress is not None:
            task.progress = progress
        save_task(task)

    return status_callback


def finalize_task_failure(*, task, error, now):
    task.status = "failed"
    task.message = f"轉錄失敗: {str(error)}"
    task.error = str(error)
    task.end_time = now
