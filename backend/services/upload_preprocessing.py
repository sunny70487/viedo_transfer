import shutil
from pathlib import Path

from backend.shared.media_config import SUPPORTED_MEDIA_EXTENSIONS


def validate_upload_filename(filename: str):
    if not filename:
        return False, "未提供文件名"

    file_ext = Path(filename).suffix.lower()
    valid_extensions = sorted(SUPPORTED_MEDIA_EXTENSIONS)
    if file_ext not in valid_extensions:
        return (
            False,
            f"不支援的檔案格式: {file_ext}。支援的格式: {', '.join(valid_extensions)}",
        )

    return True, None


def save_uploaded_file(*, upload_dir: Path, task_id: str, upload_file):
    safe_name = Path(upload_file.filename).name if upload_file.filename else "upload"
    # Per-task sub-dir keeps the original filename intact; output stems derive
    # from it, so results are named after the original upload (not task_id_*).
    task_dir = upload_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    file_path = task_dir / safe_name
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)
    return file_path


def build_transcription_request(*, request_cls, **kwargs):
    return request_cls(**kwargs)
