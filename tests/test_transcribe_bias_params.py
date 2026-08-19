from backend.app import TranscriptionRequest, BatchUrlRequest


def test_transcription_request_accepts_bias_fields():
    req = TranscriptionRequest(
        url="https://example.com/a.mp4",
        hotwords="shellcode\nVirtualAlloc",
        context="逆向工程課程",
    )

    assert req.hotwords == "shellcode\nVirtualAlloc"
    assert req.context == "逆向工程課程"


def test_transcription_request_bias_fields_default_to_none():
    req = TranscriptionRequest(url="https://example.com/a.mp4")

    assert req.hotwords is None
    assert req.context is None


def test_batch_url_request_accepts_bias_fields():
    req = BatchUrlRequest(
        urls=["https://example.com/a.mp4"],
        hotwords="Kubernetes",
        context="K8s 課程",
    )

    assert req.hotwords == "Kubernetes"
    assert req.context == "K8s 課程"


def test_none_bias_fields_produce_empty_context():
    from backend.shared.asr_context import build_asr_context

    req = TranscriptionRequest(url="https://example.com/a.mp4")

    assert build_asr_context(context=req.context, hotwords=req.hotwords) == ""
