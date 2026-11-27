#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Speaker diarization service using pyannote.audio.

Provides speaker diarization (who spoke when) to be combined with
ASR transcription results. Uses pyannote/speaker-diarization-3.1 pipeline.

Usage:
    from backend.services.diarization_service import run_diarization

    # Returns list of (start, end, speaker_label) tuples
    segments = run_diarization("audio.wav", num_speakers=2)
"""

import os
import logging
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import List, Optional, Tuple

import torch

logger = logging.getLogger(__name__)

# ============================================================
# Pipeline caching (thread-safe singleton)
# ============================================================
_PIPELINE_LOCK = threading.Lock()
_PIPELINE_INSTANCE = None


def _get_pipeline(device: str = "auto"):
    """
    Load and cache the pyannote speaker-diarization pipeline.

    Requires a HuggingFace token with access to:
      - pyannote/speaker-diarization-3.1
      - pyannote/segmentation-3.0

    Set the token via environment variable HUGGINGFACE_TOKEN or HF_TOKEN.
    """
    global _PIPELINE_INSTANCE

    with _PIPELINE_LOCK:
        if _PIPELINE_INSTANCE is not None:
            return _PIPELINE_INSTANCE

        from pyannote.audio import Pipeline

        # Resolve HF token
        hf_token = os.environ.get("HUGGINGFACE_TOKEN") or os.environ.get("HF_TOKEN")
        if not hf_token:
            raise RuntimeError(
                "Speaker diarization requires a HuggingFace token. "
                "Set HUGGINGFACE_TOKEN or HF_TOKEN environment variable. "
                "You also need to accept the pyannote/speaker-diarization-3.1 "
                "and pyannote/segmentation-3.0 model licenses on HuggingFace."
            )

        logger.info("Loading pyannote speaker-diarization-3.1 pipeline...")
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token,
        )

        # Move to GPU if available
        if device == "auto":
            device = "cuda:0" if torch.cuda.is_available() else "cpu"
        elif device == "cuda":
            device = "cuda:0"

        pipeline.to(torch.device(device))
        logger.info(f"pyannote pipeline loaded on device: {device}")

        _PIPELINE_INSTANCE = pipeline
        return _PIPELINE_INSTANCE


# ============================================================
# Audio format helpers
# ============================================================

# soundfile (libsndfile) 支援的副檔名
_SUPPORTED_EXTENSIONS = {".wav", ".flac", ".ogg", ".aiff", ".aif"}


def _ensure_wav(audio_path: str) -> str:
    """
    確保音檔為 pyannote/soundfile 可讀取的格式。
    若副檔名不在支援列表中，透過 ffmpeg 轉為 16 kHz mono WAV 並回傳暫存路徑。
    若已是支援格式則直接回傳原路徑。
    """
    ext = Path(audio_path).suffix.lower()
    if ext in _SUPPORTED_EXTENSIONS:
        return audio_path

    logger.info(f"Converting {ext} to WAV for diarization: {audio_path}")
    tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_wav.close()

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                audio_path,
                "-ar",
                "16000",  # 16 kHz（pyannote 預設取樣率）
                "-ac",
                "1",  # mono
                "-c:a",
                "pcm_s16le",
                tmp_wav.name,
            ],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        os.unlink(tmp_wav.name)
        raise RuntimeError(
            "ffmpeg conversion failed for diarization: "
            f"{e.stderr.decode(errors='replace')}"
        ) from e

    return tmp_wav.name


# ============================================================
# Public API
# ============================================================


def run_diarization(
    audio_path: str,
    num_speakers: Optional[int] = None,
    min_speakers: Optional[int] = None,
    max_speakers: Optional[int] = None,
    device: str = "auto",
) -> List[Tuple[float, float, str]]:
    """
    Run speaker diarization on an audio file.

    Args:
        audio_path: Path to the audio file.
        num_speakers: Exact number of speakers (if known).
        min_speakers: Minimum number of speakers.
        max_speakers: Maximum number of speakers.
        device: Device to run on ('auto', 'cpu', 'cuda').

    Returns:
        List of (start_time, end_time, speaker_label) tuples,
        sorted by start_time. Speaker labels are "Speaker 1", "Speaker 2", etc.
    """
    pipeline = _get_pipeline(device=device)

    # Build pipeline parameters
    pipeline_params = {}
    if num_speakers is not None:
        pipeline_params["num_speakers"] = num_speakers
    if min_speakers is not None:
        pipeline_params["min_speakers"] = min_speakers
    if max_speakers is not None:
        pipeline_params["max_speakers"] = max_speakers

    logger.info(
        f"Running speaker diarization on: {audio_path} "
        f"(params: {pipeline_params or 'auto-detect'})"
    )

    # pyannote (soundfile/libsndfile) 不支援 webm/mp4 等格式，
    # 需要先用 ffmpeg 轉成 WAV 再送入 pipeline。
    wav_path = _ensure_wav(audio_path)

    # Run diarization
    try:
        diarization = pipeline(wav_path, **pipeline_params)
    finally:
        # 清理暫存 WAV（如果是轉檔產生的）
        if wav_path != audio_path and os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except OSError:
                pass

    # Parse results: map raw speaker IDs (SPEAKER_00, SPEAKER_01, ...)
    # to human-friendly labels (Speaker 1, Speaker 2, ...)
    speaker_map = {}
    speaker_counter = 0
    segments = []

    for turn, _, speaker_id in diarization.itertracks(yield_label=True):
        if speaker_id not in speaker_map:
            speaker_counter += 1
            speaker_map[speaker_id] = f"Speaker {speaker_counter}"

        segments.append((turn.start, turn.end, speaker_map[speaker_id]))

    # Sort by start time (should already be, but ensure)
    segments.sort(key=lambda x: x[0])

    logger.info(
        f"Diarization complete: {len(segments)} segments, "
        f"{len(speaker_map)} speakers detected"
    )

    return segments


def assign_speakers_to_segments(
    asr_segments: list,
    diarization_segments: List[Tuple[float, float, str]],
) -> list:
    """
    Assign speaker labels to ASR segments based on diarization results.

    For each ASR segment, find the diarization segment that overlaps most
    with it and assign that speaker label.

    Args:
        asr_segments: List of ASR segment dicts, each with 'start' and 'end' keys.
        diarization_segments: Output from run_diarization().

    Returns:
        The same asr_segments list, with a 'speaker' key added to each segment.
    """
    if not diarization_segments:
        return asr_segments

    for seg in asr_segments:
        seg_start = seg["start"]
        seg_end = seg["end"]
        seg_duration = seg_end - seg_start

        if seg_duration <= 0:
            seg["speaker"] = None
            continue

        # Find the diarization segment with maximum overlap
        best_speaker = None
        best_overlap = 0.0

        for d_start, d_end, d_speaker in diarization_segments:
            # Calculate overlap
            overlap_start = max(seg_start, d_start)
            overlap_end = min(seg_end, d_end)
            overlap = max(0.0, overlap_end - overlap_start)

            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = d_speaker

        seg["speaker"] = best_speaker

    return asr_segments
