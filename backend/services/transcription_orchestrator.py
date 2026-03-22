from pathlib import Path


def resolve_output_directory(*, request, task_id, output_root):
    if request.output_dir:
        return request.output_dir
    return str(Path(output_root) / task_id)


def finalize_task_success(*, task, transcription_results, output_directory, now):
    task.status = "completed"
    task.progress = 100.0
    task.message = "轉錄完成"
    task.result = {
        "files": transcription_results,
        "output_dir": output_directory,
    }
    task.end_time = now
