from pathlib import Path
import subprocess


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
