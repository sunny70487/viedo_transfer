from types import SimpleNamespace

from backend.services.url_preprocessing import prepare_url_input


def test_prepare_url_input_updates_task_and_returns_downloaded_file():
    task = SimpleNamespace(message="", progress=0.0)

    downloaded = prepare_url_input(
        task=task,
        request=SimpleNamespace(
            url="https://example.com/video",
            download_format="audio",
            video_quality="best",
        ),
        output_directory="outputs/task-1",
        download=lambda **kwargs: ("outputs/task-1/source.flac", "outputs/task-1"),
    )

    assert downloaded == "outputs/task-1/source.flac"
    assert task.progress == 30.0
    assert task.message == "下載完成，開始轉錄: outputs/task-1/source.flac"


def test_prepare_url_input_raises_when_download_fails():
    task = SimpleNamespace(message="", progress=0.0)

    try:
        prepare_url_input(
            task=task,
            request=SimpleNamespace(
                url="https://example.com/video",
                download_format="audio",
                video_quality="best",
            ),
            output_directory="outputs/task-1",
            download=lambda **kwargs: (None, "outputs/task-1"),
        )
        assert False, "Expected download failure to raise"
    except RuntimeError as exc:
        assert "下載失敗" in str(exc)


def test_prepare_url_input_sets_in_progress_message_before_download():
    task = SimpleNamespace(message="", progress=0.0)
    observed = {}

    def _download(**kwargs):
        observed["message_before"] = task.message
        observed["progress_before"] = task.progress
        return ("outputs/task-1/source.flac", "outputs/task-1")

    prepare_url_input(
        task=task,
        request=SimpleNamespace(
            url="https://example.com/video",
            download_format="audio",
            video_quality="best",
        ),
        output_directory="outputs/task-1",
        download=_download,
    )

    assert observed == {
        "message_before": "正在從 URL 下載: https://example.com/video",
        "progress_before": 10.0,
    }
