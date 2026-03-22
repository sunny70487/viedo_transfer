from backend.shared.transcribe_helpers import check_gpu, format_timestamp


def test_format_timestamp_outputs_srt_style_timecode():
    assert format_timestamp(3661.275, format="srt") == "01:01:01,275"


def test_format_timestamp_outputs_vtt_style_timecode():
    assert format_timestamp(61.5, format="vtt") == "00:01:01.500"


def test_check_gpu_returns_empty_devices_when_cuda_unavailable(monkeypatch):
    class _CudaStub:
        @staticmethod
        def is_available():
            return False

        @staticmethod
        def device_count():
            return 0

    class _TorchStub:
        cuda = _CudaStub()

    gpu_info = check_gpu(torch_module=_TorchStub())

    assert gpu_info == {"available": False, "device_count": 0, "devices": []}


def test_check_gpu_collects_device_details_when_cuda_available(monkeypatch):
    class _Props:
        total_memory = 8 * 1024**3

    class _CudaStub:
        @staticmethod
        def is_available():
            return True

        @staticmethod
        def device_count():
            return 2

        @staticmethod
        def get_device_name(index):
            return f"GPU-{index}"

        @staticmethod
        def memory_allocated(index):
            return (index + 1) * 1024**2

        @staticmethod
        def memory_reserved(index):
            return (index + 2) * 1024**2

        @staticmethod
        def get_device_properties(index):
            return _Props()

    class _TorchStub:
        cuda = _CudaStub()

    gpu_info = check_gpu(torch_module=_TorchStub())

    assert gpu_info["available"] is True
    assert gpu_info["device_count"] == 2
    assert gpu_info["devices"][0]["name"] == "GPU-0"
    assert gpu_info["devices"][1]["memory_reserved"] == "3.00 MB"
