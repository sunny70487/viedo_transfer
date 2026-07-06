"""
字幕燒錄服務 — 使用 FFmpeg 將字幕硬嵌入影片
"""

import os
import logging
import subprocess
import threading
import uuid
from typing import Dict, List, Optional

logger = logging.getLogger("burn_in_service")

_burn_tasks: Dict[str, dict] = {}


def _format_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    ms = int((s % 1) * 1000)
    return f"{h:02d}:{m:02d}:{int(s):02d},{ms:03d}"


def _generate_srt(subtitles: List[dict]) -> str:
    lines: list[str] = []
    for i, sub in enumerate(subtitles):
        start = _format_srt_time(sub["start_time"])
        end = _format_srt_time(sub["end_time"])
        text = sub["text"]
        if sub.get("speaker"):
            text = f"[{sub['speaker']}] {text}"
        lines.append(str(i + 1))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def _rgb_to_ass_color(hex_rgb: str) -> str:
    """Convert hex RGB (e.g. 'FFFFFF') to ASS colour &H00BBGGRR."""
    hex_rgb = hex_rgb.lstrip("#")
    if len(hex_rgb) != 6:
        hex_rgb = "FFFFFF"
    r, g, b = hex_rgb[0:2], hex_rgb[2:4], hex_rgb[4:6]
    return f"&H00{b.upper()}{g.upper()}{r.upper()}"


def start_burn_in(
    task_id: str,
    subtitles: List[dict],
    video_path: str,
    output_dir: str,
    font_size: int = 22,
    font_color: str = "FFFFFF",
    outline_color: str = "000000",
    outline_width: int = 2,
    margin_v: int = 30,
) -> str:
    burn_id = uuid.uuid4().hex[:8]
    output_path = os.path.join(output_dir, f"{task_id}_burned.mp4")

    task_info = {
        "id": burn_id,
        "task_id": task_id,
        "status": "processing",
        "progress": 0,
        "output_path": output_path,
        "error": None,
    }
    _burn_tasks[burn_id] = task_info

    thread = threading.Thread(
        target=_run_burn_in,
        args=(task_info, subtitles, video_path, output_dir,
              font_size, font_color, outline_color, outline_width, margin_v),
        daemon=True,
    )
    thread.start()
    return burn_id


def _run_burn_in(
    task_info: dict,
    subtitles: List[dict],
    video_path: str,
    output_dir: str,
    font_size: int,
    font_color: str,
    outline_color: str,
    outline_width: int,
    margin_v: int,
):
    srt_filename = f"_burn_temp_{task_info['id']}.srt"
    srt_path = os.path.join(output_dir, srt_filename)
    process: Optional[subprocess.Popen] = None
    try:
        srt_content = _generate_srt(subtitles)
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        primary = _rgb_to_ass_color(font_color)
        outline = _rgb_to_ass_color(outline_color)

        force_style = (
            f"FontSize={font_size},"
            f"PrimaryColour={primary},"
            f"OutlineColour={outline},"
            f"BorderStyle=1,"
            f"Outline={outline_width},"
            f"Shadow=1,"
            f"MarginV={margin_v}"
        )

        # Use just the filename (no drive letter / colons) and set cwd
        # to output_dir. This avoids Windows path escaping issues with
        # FFmpeg's subtitles filter where C: is misinterpreted.
        vf = f"subtitles={srt_filename}:force_style='{force_style}'"
        cmd = [
            "ffmpeg", "-y",
            "-i", os.path.abspath(video_path),
            "-vf", vf,
            "-c:a", "copy",
            "-preset", "fast",
            os.path.abspath(task_info["output_path"]),
        ]

        logger.info("Burn-in started: %s", task_info["id"])
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=output_dir,
        )
        _, stderr_bytes = process.communicate(timeout=7200)

        if process.returncode != 0:
            err = stderr_bytes.decode("utf-8", errors="replace")[-500:]
            task_info["status"] = "failed"
            task_info["error"] = err
            logger.error("Burn-in failed: %s", err)
        else:
            task_info["status"] = "completed"
            task_info["progress"] = 100
            logger.info("Burn-in completed: %s", task_info["output_path"])

    except subprocess.TimeoutExpired:
        if process:
            process.kill()
        task_info["status"] = "failed"
        task_info["error"] = "FFmpeg 超時（超過 2 小時）"
    except Exception as exc:
        task_info["status"] = "failed"
        task_info["error"] = str(exc)
        logger.error("Burn-in error: %s", exc, exc_info=True)
    finally:
        if os.path.exists(srt_path):
            try:
                os.unlink(srt_path)
            except OSError:
                pass


def get_burn_in_task(burn_id: str) -> Optional[dict]:
    return _burn_tasks.get(burn_id)
