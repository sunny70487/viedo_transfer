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


def check_gpu(torch_module):
    gpu_info = {
        "available": torch_module.cuda.is_available(),
        "device_count": torch_module.cuda.device_count(),
        "devices": [],
    }

    if gpu_info["available"]:
        for index in range(gpu_info["device_count"]):
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

    return gpu_info
