import importlib
import sys
from types import SimpleNamespace


def _load_launcher_module():
    sys.modules.pop("backend.services.transcription_launcher", None)
    return importlib.import_module("backend.services.transcription_launcher")


def test_create_task_entry_registers_task_and_persists(monkeypatch):
    launcher = _load_launcher_module()

    tasks = {}
    persisted = {}

    class _TaskStub:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    monkeypatch.setattr(launcher.uuid, "uuid4", lambda: "task-1")
    monkeypatch.setattr(launcher.time, "time", lambda: 123.0)

    def _save(task):
        persisted["task_id"] = task.id

    task = launcher.create_task_entry(
        tasks=tasks,
        save_task=_save,
        source_name="demo.wav",
        task_cls=_TaskStub,
    )

    assert task.id == "task-1"
    assert task.status == "queued"
    assert tasks["task-1"] is task
    assert persisted["task_id"] == "task-1"


def test_submit_transcription_delegates_to_executor():
    launcher = _load_launcher_module()

    captured = {}

    class _FakeExecutor:
        _threads = []

        def submit(self, fn, *args):
            captured["fn"] = fn
            captured["args"] = args
            return SimpleNamespace()

    def _target(*args):
        return args

    launcher.submit_transcription(
        executor=_FakeExecutor(),
        target=_target,
        task_id="task-1",
        file_path="input.wav",
        request=SimpleNamespace(model_size="qwen3-asr-1.7b"),
    )

    assert captured["fn"] is _target
    assert captured["args"][0] == "task-1"
    assert captured["args"][1] == "input.wav"
