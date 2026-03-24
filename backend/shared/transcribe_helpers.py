def format_timestamp(seconds, format="srt"):
    hours = int(seconds / 3600)
    minutes = int((seconds % 3600) / 60)
    secs = seconds % 60

    if format == "srt":
        return (
            f"{hours:02d}:{minutes:02d}:{int(secs):02d},{int(secs * 1000) % 1000:03d}"
        )
    if format == "vtt":
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def check_gpu(torch_module=None):
    if torch_module is None:
        import torch as torch_module

    cuda_available = torch_module.cuda.is_available()
    device_count = torch_module.cuda.device_count()

    # device_count > 0 means CUDA driver sees GPUs even if runtime
    # reports unavailable (e.g. lazy init or driver/runtime mismatch).
    has_gpu = cuda_available or device_count > 0

    gpu_info = {
        "available": has_gpu,
        "device_count": device_count,
        "devices": [],
    }

    if device_count > 0:
        for index in range(device_count):
            try:
                device_properties = torch_module.cuda.get_device_properties(index)
                gpu_info["devices"].append(
                    {
                        "name": torch_module.cuda.get_device_name(index),
                        "memory_allocated": (
                            f"{torch_module.cuda.memory_allocated(index) / 1024**2:.2f} MB"
                        ),
                        "memory_reserved": (
                            f"{torch_module.cuda.memory_reserved(index) / 1024**2:.2f} MB"
                        ),
                        "max_memory": (
                            f"{device_properties.total_memory / 1024**3:.2f} GB"
                        ),
                    }
                )
            except Exception:
                gpu_info["devices"].append(
                    {
                        "name": f"GPU {index} (資訊無法讀取)",
                        "memory_allocated": "N/A",
                        "memory_reserved": "N/A",
                        "max_memory": "N/A",
                    }
                )

    return gpu_info
