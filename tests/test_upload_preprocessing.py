from types import SimpleNamespace

from backend.services.upload_preprocessing import (
    build_transcription_request,
    save_uploaded_file,
    validate_upload_filename,
)


def test_validate_upload_filename_accepts_supported_media_extension():
    valid, error = validate_upload_filename("demo.webm")

    assert valid is True
    assert error is None


def test_validate_upload_filename_rejects_unsupported_extension():
    valid, error = validate_upload_filename("notes.txt")

    assert valid is False
    assert "不支援的檔案格式" in error


def test_save_uploaded_file_writes_content_to_task_dir_with_original_name(tmp_path):
    file_obj = SimpleNamespace(filename="demo.wav", file=SimpleNamespace(read=None))

    class _Buffer:
        def __init__(self, payload):
            self.payload = payload
            self.used = False

        def read(self, *_args, **_kwargs):
            if self.used:
                return b""
            self.used = True
            return self.payload

    file_obj.file = _Buffer(b"audio-bytes")

    saved_path = save_uploaded_file(
        upload_dir=tmp_path,
        task_id="task-1",
        upload_file=file_obj,
    )

    assert saved_path == tmp_path / "task-1" / "demo.wav"
    assert saved_path.read_bytes() == b"audio-bytes"


def test_build_transcription_request_copies_form_values():
    class _RequestStub:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    request = build_transcription_request(
        request_cls=_RequestStub,
        model_size="qwen3-asr-1.7b",
        device="cpu",
        compute_type="default",
        language="zh",
        task="transcribe",
        beam_size=3,
        vad_filter=True,
        word_timestamps=False,
        output_format="srt",
        split_segments=True,
        segment_duration=45,
        output_dir="outputs/demo",
        speaker_diarization=True,
        num_speakers=2,
    )

    assert request.model_size == "qwen3-asr-1.7b"
    assert request.split_segments is True
    assert request.segment_duration == 45
    assert request.speaker_diarization is True
    assert request.num_speakers == 2
