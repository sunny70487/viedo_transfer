from types import SimpleNamespace

from backend.services.transcription_orchestrator import (
    finalize_task_success,
    resolve_output_directory,
)


def test_resolve_output_directory_prefers_request_output_dir(tmp_path):
    output_dir = tmp_path / "custom-output"
    request = SimpleNamespace(output_dir=str(output_dir))

    resolved = resolve_output_directory(
        request=request, task_id="task-1", output_root=tmp_path
    )

    assert resolved == str(output_dir)


def test_resolve_output_directory_falls_back_to_task_specific_folder(tmp_path):
    request = SimpleNamespace(output_dir=None)

    resolved = resolve_output_directory(
        request=request, task_id="task-1", output_root=tmp_path
    )

    assert resolved == str(tmp_path / "task-1")


def test_finalize_task_success_updates_state_and_result(tmp_path):
    task = SimpleNamespace(
        status="processing",
        progress=30.0,
        message="正在執行轉錄...",
        result=None,
        end_time=None,
    )

    finalize_task_success(
        task=task,
        transcription_results={"srt": "demo.srt"},
        output_directory=str(tmp_path),
        now=123.0,
    )

    assert task.status == "completed"
    assert task.progress == 100.0
    assert task.message == "轉錄完成"
    assert task.result == {"files": {"srt": "demo.srt"}, "output_dir": str(tmp_path)}
    assert task.end_time == 123.0
