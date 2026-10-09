"""
FireRedVAD-based voice activity detection.

Provides real VAD so that long audio can be cut at silence boundaries instead
of at fixed wall-clock intervals, which avoids splitting words mid-utterance.

The model is tiny (~2.4 MB / 0.6M params) and runs on CPU with RTF ~0.003, so
it is loaded once per process and kept in memory.
"""

import logging
import math
import os
import subprocess
import tempfile
import threading

logger = logging.getLogger("firered_vad")

_MODEL_DIR_ENV = "FIRERED_VAD_MODEL_DIR"
_DEFAULT_MODEL_DIR = os.path.join("pretrained_models", "FireRedVAD", "VAD")
_HF_REPO_ID = "FireRedTeam/FireRedVAD"

_VAD_LOCK = threading.Lock()
_VAD_INSTANCE = None

_DOWNLOAD_LOCK = threading.Lock()
_DOWNLOAD_ATTEMPTED = False
_DOWNLOADED_DIR = None


def plan_vad_chunks(segments, max_duration=30.0):
    """
    Group VAD speech segments into chunks no longer than ``max_duration``.

    Cut points land inside silence gaps between segments, so no word is split.
    A single segment longer than ``max_duration`` is divided evenly, since
    there is no silence inside it to cut on.

    Args:
        segments: list of ``(start_s, end_s)`` speech spans, ascending.
        max_duration: maximum chunk length in seconds.

    Returns:
        list of ``(start_s, end_s)`` chunk spans.
    """
    if not segments:
        return []

    chunks = []
    current_start = None
    current_end = None

    for seg_start, seg_end in segments:
        seg_duration = seg_end - seg_start

        if seg_duration > max_duration:
            if current_start is not None:
                chunks.append((current_start, current_end))
                current_start = None
                current_end = None
            parts = math.ceil(seg_duration / max_duration)
            step = seg_duration / parts
            for part in range(parts):
                part_start = seg_start + part * step
                part_end = seg_end if part == parts - 1 else part_start + step
                chunks.append((part_start, part_end))
            continue

        if current_start is None:
            current_start = seg_start
            current_end = seg_end
        elif seg_end - current_start <= max_duration:
            current_end = seg_end
        else:
            chunks.append((current_start, current_end))
            current_start = seg_start
            current_end = seg_end

    if current_start is not None:
        chunks.append((current_start, current_end))

    return chunks


def _download_model_dir():
    """Fetch the weights into the Hugging Face cache, as the ASR models do.

    Returns the VAD subdirectory, or None when the download is unavailable.
    """
    try:
        from huggingface_hub import snapshot_download

        logger.info("Downloading FireRedVAD weights from %s", _HF_REPO_ID)
        root = snapshot_download(repo_id=_HF_REPO_ID, allow_patterns=["VAD/*"])
        candidate = os.path.join(root, "VAD")
        return candidate if os.path.isdir(candidate) else None
    except Exception as exc:
        logger.warning("Could not download FireRedVAD weights: %s", exc)
        return None


def resolve_model_dir():
    """Locate the FireRedVAD weights, downloading them once if necessary.

    Order: explicit env override, bundled local directory, then the Hugging
    Face cache (which is a persistent volume in Docker). Returns None when no
    weights can be obtained, so callers fall back to fixed-interval splitting.
    """
    global _DOWNLOAD_ATTEMPTED, _DOWNLOADED_DIR

    override = os.environ.get(_MODEL_DIR_ENV)
    if override:
        return override

    if os.path.isdir(_DEFAULT_MODEL_DIR):
        return _DEFAULT_MODEL_DIR

    with _DOWNLOAD_LOCK:
        if not _DOWNLOAD_ATTEMPTED:
            _DOWNLOAD_ATTEMPTED = True
            _DOWNLOADED_DIR = _download_model_dir()
        return _DOWNLOADED_DIR


def is_available():
    """True when the fireredasr2s package and model weights are both present."""
    model_dir = resolve_model_dir()
    if not model_dir or not os.path.isdir(model_dir):
        return False
    try:
        import fireredasr2s.fireredvad  # noqa: F401
    except Exception:
        return False
    return True


def _load_vad():
    """Load and cache the FireRedVAD model (CPU — it is far too small for GPU)."""
    global _VAD_INSTANCE
    with _VAD_LOCK:
        if _VAD_INSTANCE is None:
            from fireredasr2s.fireredvad import FireRedVad, FireRedVadConfig

            model_dir = resolve_model_dir()
            logger.info("Loading FireRedVAD from %s", model_dir)
            _VAD_INSTANCE = FireRedVad.from_pretrained(
                model_dir, FireRedVadConfig(use_gpu=False)
            )
        return _VAD_INSTANCE


def _to_vad_wav(audio_path):
    """Convert any input to the 16 kHz mono PCM wav FireRedVAD requires."""
    handle, wav_path = tempfile.mkstemp(suffix="_vad16k.wav")
    os.close(handle)
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", audio_path,
            "-ar", "16000", "-ac", "1", "-acodec", "pcm_s16le",
            "-f", "wav", wav_path,
        ],
        capture_output=True,
        check=True,
    )
    return wav_path


def detect_speech_segments(audio_path, speech_threshold=0.4):
    """
    Detect speech spans in ``audio_path``.

    Returns a list of ``(start_s, end_s)`` tuples, or ``None`` when VAD is
    unavailable or fails, so callers can fall back to fixed-interval splitting.
    """
    if not is_available():
        logger.warning(
            "FireRedVAD unavailable (model dir %s); skipping VAD",
            resolve_model_dir(),
        )
        return None

    wav_path = None
    try:
        wav_path = _to_vad_wav(audio_path)
        vad = _load_vad()
        result, _probs = vad.detect(wav_path)
        segments = [(float(s), float(e)) for s, e in result["timestamps"]]
        logger.info(
            "FireRedVAD found %d speech segments in %s",
            len(segments),
            os.path.basename(audio_path),
        )
        return segments
    except Exception as exc:
        logger.warning("FireRedVAD failed on %s: %s", audio_path, exc, exc_info=True)
        return None
    finally:
        if wav_path and os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except OSError:
                pass
