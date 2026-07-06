"""
Shared transcription pipeline utilities used by both Qwen3-ASR and FunASR engines.
Covers device resolution, output path initialization, subtitle formatting,
and file writing.
"""

import json
from pathlib import Path

from backend.shared.transcribe_helpers import check_gpu, format_timestamp


def resolve_device(device: str, verbose: bool = False) -> str:
    """Normalize device string ('auto'/'cuda' -> 'cuda:0' or 'cpu')."""
    import torch

    if device == "auto":
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
    elif device == "cuda":
        device = "cuda:0"

    if verbose:
        print(f"使用設備: {device}")

    return device


def print_gpu_info(device: str, verbose: bool = False) -> None:
    """Print GPU information when using CUDA."""
    if "cuda" not in device or not verbose:
        return
    gpu_info = check_gpu()
    print(f"檢測到 {gpu_info['device_count']} 個 GPU 設備:")
    for i, gpu in enumerate(gpu_info["devices"]):
        print(f" - GPU {i}: {gpu['name']} ({gpu['max_memory']} 總記憶體)")
        print(f"   已分配: {gpu['memory_allocated']}, 已保留: {gpu['memory_reserved']}")


def init_output_paths(audio_path, output_dir=None):
    """Return (base_output_path, base_filename) and ensure the directory exists."""
    audio_path_obj = Path(audio_path)
    base_output_path = Path(output_dir) if output_dir else audio_path_obj.parent
    base_filename = audio_path_obj.stem
    base_output_path.mkdir(parents=True, exist_ok=True)
    return base_output_path, base_filename


def init_buffers():
    """Return a fresh set of accumulator buffers for transcription output."""
    return {
        "transcript_parts": [],
        "srt_content": "",
        "vtt_content": "WEBVTT\n\n",
        "segments_json": [],
        "words_data": [],
        "output_files": {},
        "detected_language": None,
        "language_probability": None,
    }


def build_srt_entry(index, start, end, text):
    """Build a single SRT subtitle entry string."""
    start_ts = format_timestamp(start, format="srt")
    end_ts = format_timestamp(end, format="srt")
    return f"{index}\n{start_ts} --> {end_ts}\n{text}\n\n"


def build_vtt_entry(start, end, text):
    """Build a single VTT subtitle entry string."""
    start_ts = format_timestamp(start, format="vtt")
    end_ts = format_timestamp(end, format="vtt")
    return f"{start_ts} --> {end_ts}\n{text}\n\n"


def write_output_files(
    base_output_path,
    base_filename,
    output_format,
    transcript_parts,
    srt_content,
    vtt_content,
    segments_json,
    words_data,
    detected_language,
    language_probability,
    output_files,
    *,
    speakers=None,
    model_name=None,
    verbose=False,
    show_in_terminal=False,
):
    """Write .txt, .srt, .vtt, .json output files and return updated output_files dict."""
    txt_path = base_output_path / f"{base_filename}.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(transcript_parts))
    output_files["txt"] = str(txt_path)

    if output_format in ("srt", "all"):
        srt_path = base_output_path / f"{base_filename}.srt"
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)
        output_files["srt"] = str(srt_path)

    if output_format in ("vtt", "all"):
        vtt_path = base_output_path / f"{base_filename}.vtt"
        with open(vtt_path, "w", encoding="utf-8") as f:
            f.write(vtt_content)
        output_files["vtt"] = str(vtt_path)

    full_transcript = "\n".join(transcript_parts)
    json_data = {
        "text": full_transcript,
        "segments": segments_json,
        "language": detected_language,
        "language_probability": language_probability,
        "words": words_data if words_data else None,
        "model_name": model_name,
    }
    if speakers:
        json_data["speakers"] = speakers

    json_path = base_output_path / f"{base_filename}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    output_files["json"] = str(json_path)

    if show_in_terminal and verbose and not segments_json and full_transcript:
        print("\n" + "=" * 50)
        print("轉錄結果:")
        print("=" * 50)
        print(full_transcript)
        print("=" * 50 + "\n")

    return output_files
