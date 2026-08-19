import multiprocessing as mp
import os
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pydub import AudioSegment

from backend.shared.firered_vad import detect_speech_segments, plan_vad_chunks


def parse_audio_duration(stderr_text):
    duration_match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d+)", stderr_text)
    if duration_match is None:
        return None

    hours, minutes, seconds = duration_match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def split_audio(
    audio_path,
    segment_duration=30,
    output_dir=None,
    verbose=True,
    max_workers=None,
    tqdm_factory=None,
):
    if output_dir is None:
        temp_dir = tempfile.mkdtemp()
        output_dir = temp_dir
    else:
        temp_dir = None
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    duration_cmd = ["ffmpeg", "-i", audio_path, "-hide_banner"]
    try:
        result = subprocess.run(duration_cmd, capture_output=True)
        output = result.stderr.decode("utf-8", errors="replace")
        total_duration = parse_audio_duration(output)

        if total_duration is None:
            try:
                audio = AudioSegment.from_file(audio_path)
                total_duration = len(audio) / 1000.0
            except Exception as exc:
                print(f"無法獲取音檔時長 (pydub): {exc}")
                file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
                total_duration = file_size_mb * 60
    except Exception as exc:
        print(f"無法獲取音檔時長 (ffmpeg): {exc}")
        try:
            audio = AudioSegment.from_file(audio_path)
            total_duration = len(audio) / 1000.0
        except Exception as fallback_exc:
            print(f"使用 pydub 獲取時長也失敗: {fallback_exc}")
            file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
            total_duration = file_size_mb * 60

    num_segments = int(total_duration / segment_duration) + 1

    if verbose:
        print(
            "音檔總長度: "
            f"{int(total_duration / 3600):02d}:"
            f"{int((total_duration % 3600) / 60):02d}:"
            f"{int(total_duration % 60):02d}"
        )
        print(f"預計將分割為 {num_segments} 個片段")
        print("使用多線程加速分割處理...")

    def split_segment(index):
        start_time = index * segment_duration
        if start_time >= total_duration:
            return None

        segment_filename = os.path.join(output_dir, f"segment_{index:03d}.flac")
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(start_time),
            "-i",
            audio_path,
            "-t",
            str(segment_duration),
            "-vn",
            "-c:a",
            "flac",
            "-threads",
            "2",
            segment_filename,
        ]

        try:
            result = subprocess.run(ffmpeg_cmd, capture_output=True)
            if result.returncode != 0:
                error_message = result.stderr.decode("utf-8", errors="replace")
                print(f"分割音檔段 {index} 時出錯: 返回碼 {result.returncode}")
                print(f"錯誤輸出: {error_message}")
                return None
            return segment_filename
        except Exception as exc:
            print(f"分割音檔段 {index} 時出錯: {exc}")
            return None

    if max_workers is None:
        max_workers = min(mp.cpu_count(), 4)

    successful_segments = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(split_segment, i): i for i in range(num_segments)}

        progress_bar = None
        if verbose and tqdm_factory is not None:
            progress_bar = tqdm_factory(total=num_segments, desc="分割進度")
        elif verbose:
            print(f"開始分割處理 {num_segments} 個片段...")

        completed_count = 0
        for future in as_completed(futures):
            segment_file = future.result()
            if segment_file:
                successful_segments.append(segment_file)
            if verbose:
                completed_count += 1
                if progress_bar is not None:
                    progress_bar.update(1)
                elif completed_count % 10 == 0 or completed_count == num_segments:
                    percent_complete = min(
                        100, round((completed_count / num_segments) * 100)
                    )
                    print(
                        f"分割進度: {percent_complete}% ({completed_count}/{num_segments})"
                    )

        if progress_bar is not None:
            progress_bar.close()

    segment_files = sorted(successful_segments)

    if verbose:
        print(f"分割完成! 共生成 {len(segment_files)} 個片段。")

    return segment_files, temp_dir


def _extract_span(audio_path, start_s, end_s, out_path):
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start_s:.3f}",
        "-i", audio_path,
        "-t", f"{end_s - start_s:.3f}",
        "-vn", "-c:a", "flac", "-threads", "2",
        out_path,
    ]
    try:
        result = subprocess.run(ffmpeg_cmd, capture_output=True)
        if result.returncode != 0:
            print(
                f"擷取語音片段 {start_s:.2f}-{end_s:.2f}s 失敗: "
                f"返回碼 {result.returncode}"
            )
            return None
        return out_path
    except Exception as exc:
        print(f"擷取語音片段 {start_s:.2f}-{end_s:.2f}s 失敗: {exc}")
        return None


def split_audio_by_vad(
    audio_path,
    max_duration=30,
    output_dir=None,
    verbose=True,
    max_workers=None,
):
    """
    Split audio at VAD-detected silence boundaries.

    Returns ``(segments, temp_dir, used_vad)`` where ``segments`` is a list of
    ``(file_path, start_offset_s)`` pairs. Returning the true start offset with
    each file is what keeps timestamps correct: callers must not assume the
    Nth chunk begins at ``N * max_duration``.

    Falls back to fixed-interval :func:`split_audio` when VAD is unavailable or
    finds no speech, in which case ``used_vad`` is ``False``.
    """
    speech_segments = detect_speech_segments(audio_path)

    if not speech_segments:
        if verbose:
            print("VAD 不可用或未偵測到語音，改用固定間隔分割")
        segment_files, temp_dir = split_audio(
            audio_path,
            segment_duration=max_duration,
            output_dir=output_dir,
            verbose=verbose,
            max_workers=max_workers,
        )
        segments = [
            (path, float(index * max_duration))
            for index, path in enumerate(segment_files)
        ]
        return segments, temp_dir, False

    chunks = plan_vad_chunks(speech_segments, max_duration=float(max_duration))

    if output_dir is None:
        temp_dir = tempfile.mkdtemp()
        output_dir = temp_dir
    else:
        temp_dir = None
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    speech_total = sum(end - start for start, end in speech_segments)
    if verbose:
        print(
            f"VAD 偵測到 {len(speech_segments)} 段語音（共 {speech_total:.1f} 秒），"
            f"合併為 {len(chunks)} 個片段"
        )

    if max_workers is None:
        max_workers = min(mp.cpu_count(), 4)

    def extract(index):
        start_s, end_s = chunks[index]
        out_path = os.path.join(output_dir, f"vad_segment_{index:04d}.flac")
        produced = _extract_span(audio_path, start_s, end_s, out_path)
        if produced is None:
            return None
        return produced, start_s

    results = [None] * len(chunks)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(extract, i): i for i in range(len(chunks))}
        for future in as_completed(futures):
            index = futures[future]
            results[index] = future.result()

    segments = [item for item in results if item is not None]

    if verbose:
        print(f"VAD 分割完成! 共生成 {len(segments)} 個片段。")

    return segments, temp_dir, True
