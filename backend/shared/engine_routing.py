"""
Unified engine routing: dispatches transcription calls to Qwen3-ASR or FunASR
based on the requested model name.
"""

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


def transcribe_audio(**kwargs):
    """根據 model_size 自動路由到 Qwen3-ASR 或 FunASR 引擎"""
    model_size = kwargs.get("model_size", "qwen3-asr-1.7b")
    if model_size in FUNASR_MODEL_NAMES:
        return _funasr_transcribe(**kwargs)
    return _qwen3_transcribe(**kwargs)
