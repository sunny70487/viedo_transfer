import os


AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".aac"}
VIDEO_EXTENSIONS = {
    ".mp4",
    ".avi",
    ".mov",
    ".mkv",
    ".webm",
    ".flv",
    ".wmv",
    ".m4v",
    ".mpeg",
    ".mpg",
}
SUPPORTED_MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS

MEDIA_TYPES = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".mov": "video/quicktime",
    ".flv": "video/x-flv",
    ".wmv": "video/x-ms-wmv",
    ".m4v": "video/x-m4v",
    ".mpeg": "video/mpeg",
    ".mpg": "video/mpeg",
}


def is_supported_media_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SUPPORTED_MEDIA_EXTENSIONS


def get_media_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return MEDIA_TYPES.get(ext, "application/octet-stream")
