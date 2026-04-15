import logging
from pathlib import Path
import subprocess

from backend.shared.media_config import VIDEO_EXTENSIONS

logger = logging.getLogger(__name__)

# Formats the browser can play natively without conversion
_BROWSER_NATIVE_CONTAINERS = {".mp4", ".webm"}
_FFMPEG_TIMEOUT_REMUX = 300   # seconds
_FFMPEG_TIMEOUT_TRANSCODE = 900


def is_video_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


def build_mp4_conversion_command(source: str | Path, target: str | Path) -> list[str]:
    return [
        "ffmpeg",
        "-i",
        str(source),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        "-y",
        str(target),
    ]


def maybe_prepare_video_output(
    audio_path: str | Path,
    base_output_path: Path,
    base_filename: str,
    output_files: dict,
    *,
    verbose: bool,
    status_callback=None,
    expose_mp4_key: bool = False,
) -> None:
    audio_path = Path(audio_path)
    file_ext = audio_path.suffix.lower()

    if not is_video_file(audio_path):
        return

    if verbose:
        print(f"\n檢測到影片文件格式: {file_ext}")

    if file_ext == ".mp4":
        output_files["video"] = str(audio_path)
        if expose_mp4_key:
            output_files["mp4"] = str(audio_path)
        if verbose:
            print("✓ 影片已經是 MP4 格式，無需轉換")
        return

    mp4_filename = f"{base_filename}_converted.mp4"
    mp4_path = base_output_path / mp4_filename

    if status_callback:
        status_callback(f"正在將 {file_ext} 轉換為 MP4 以確保瀏覽器兼容性...")
    if verbose:
        print(f"正在將 {file_ext} 轉換為 MP4 以確保瀏覽器兼容性...")

    try:
        result = subprocess.run(
            build_mp4_conversion_command(audio_path, mp4_path),
            capture_output=True,
        )

        if result.returncode == 0 and mp4_path.exists():
            output_files["video"] = str(mp4_path)
            if expose_mp4_key:
                output_files["mp4"] = str(mp4_path)
            if verbose:
                file_size_mb = mp4_path.stat().st_size / (1024 * 1024)
                print(f"✓ 影片已轉換為 MP4: {mp4_path.name} ({file_size_mb:.1f} MB)")
            return

        if verbose:
            stderr_msg = result.stderr.decode("utf-8", errors="replace")[:200]
            print("⚠ 影片轉換失敗，使用原始文件")
            print(f"FFmpeg 錯誤: {stderr_msg}")
    except Exception as exc:
        if verbose:
            print(f"⚠ 無法轉換影片: {str(exc)}")
            print("使用原始影片文件")

    output_files["video"] = str(audio_path)
    if expose_mp4_key:
        output_files[file_ext.lstrip(".")] = str(audio_path)


def prepare_source_video_for_preview(
    source_path: "str | Path",
    output_dir: "str | Path",
    task_id: str,
    *,
    status_callback=None,
    verbose: bool = False,
) -> "str | None":
    """
    Ensure a browser-playable mp4 exists before transcription starts.

    Strategy (in order):
      1. Not a video file → return None (audio-only, no preview needed)
      2. Already .mp4 or .webm → return source path as-is (browser-native)
      3. Remux with ``-c copy`` (near-instant, codec-preserving)
      4. Full transcode to H.264/AAC as last resort
      5. Both fail → return None (VideoPlayer shows fallback)

    The returned path (when not None) is safe to serve directly to a
    browser and is stored as ``task.source_file_path``.
    """
    source_path = Path(source_path)

    if not is_video_file(source_path):
        return None

    ext = source_path.suffix.lower()

    if ext in _BROWSER_NATIVE_CONTAINERS:
        return str(source_path)

    preview_path = Path(output_dir) / f"{task_id}_preview.mp4"

    if status_callback:
        status_callback("正在準備影片預覽...", progress=8.0)
    if verbose:
        print(f"Preparing mp4 preview from {source_path.name}")

    # ── Attempt 1: remux (copy all streams, change container only) ──
    remux_cmd = [
        "ffmpeg", "-i", str(source_path),
        "-c", "copy",
        "-movflags", "+faststart",
        "-y", str(preview_path),
    ]
    try:
        result = subprocess.run(
            remux_cmd,
            capture_output=True,
            timeout=_FFMPEG_TIMEOUT_REMUX,
        )
        if (
            result.returncode == 0
            and preview_path.exists()
            and preview_path.stat().st_size > 0
        ):
            if verbose:
                size_mb = preview_path.stat().st_size / (1024 * 1024)
                print(f"  ✓ Remux succeeded: {size_mb:.1f} MB")
            return str(preview_path)
        if verbose:
            stderr = result.stderr.decode("utf-8", errors="replace")[:300]
            print(f"  Remux failed (rc={result.returncode}): {stderr}")
    except subprocess.TimeoutExpired:
        logger.warning("Video remux timed out for %s", source_path.name)
    except Exception as exc:
        logger.warning("Video remux error: %s", exc)

    # ── Attempt 2: full transcode (H.264 + AAC) ──
    if status_callback:
        status_callback("正在轉碼影片為 MP4...", progress=10.0)

    try:
        result = subprocess.run(
            build_mp4_conversion_command(source_path, preview_path),
            capture_output=True,
            timeout=_FFMPEG_TIMEOUT_TRANSCODE,
        )
        if (
            result.returncode == 0
            and preview_path.exists()
            and preview_path.stat().st_size > 0
        ):
            if verbose:
                size_mb = preview_path.stat().st_size / (1024 * 1024)
                print(f"  ✓ Transcode succeeded: {size_mb:.1f} MB")
            return str(preview_path)
        if verbose:
            stderr = result.stderr.decode("utf-8", errors="replace")[:300]
            print(f"  Transcode failed (rc={result.returncode}): {stderr}")
    except subprocess.TimeoutExpired:
        logger.warning("Video transcode timed out for %s", source_path.name)
    except Exception as exc:
        logger.warning("Video transcode error: %s", exc)

    logger.warning(
        "Could not prepare mp4 preview for %s — VideoPlayer will show fallback",
        source_path.name,
    )
    return None
