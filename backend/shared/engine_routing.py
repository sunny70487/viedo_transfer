"""
Unified engine routing: dispatches transcription calls to Qwen3-ASR or FunASR
based on the requested model name.
"""

import inspect

from backend.qwen3_asr_transcribe import transcribe_audio as _qwen3_transcribe
from backend.funasr_transcribe import transcribe_audio as _funasr_transcribe

FUNASR_MODEL_NAMES = frozenset(
    {
        "paraformer-zh",
        "paraformer",
        "sensevoice",
        "SenseVoiceSmall",
        "iic/SenseVoiceSmall",
        "large-v3",
        "whisper-large-v3",
        "Whisper-large-v3",
        "large-v3-turbo",
        "whisper-large-v3-turbo",
        "Whisper-large-v3-turbo",
        "fun-asr-nano",
        "nano",
        "FunAudioLLM/Fun-ASR-Nano-2512",
    }
)


def _supported_kwargs(engine, kwargs):
    """Drop kwargs the engine cannot accept.

    Engines do not share a signature: only Qwen3-ASR takes context/hotwords,
    and only it takes speaker_diarization. Forwarding blindly raises TypeError.
    """
    params = inspect.signature(engine).parameters
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return kwargs
    return {k: v for k, v in kwargs.items() if k in params}


def transcribe_audio(**kwargs):
    """根據 model_size 自動路由到 Qwen3-ASR 或 FunASR 引擎"""
    model_size = kwargs.get("model_size", "qwen3-asr-1.7b")
    engine = (
        _funasr_transcribe
        if model_size in FUNASR_MODEL_NAMES
        else _qwen3_transcribe
    )
    return engine(**_supported_kwargs(engine, kwargs))
