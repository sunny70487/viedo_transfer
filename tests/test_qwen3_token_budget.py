"""
Regression tests for silent subtitle gaps on long, dense audio.

Qwen3-ASR stops generating after ``max_new_tokens``. With the old fixed cap of
256, every ~60 s chunk of fast speech lost its tail, leaving 10-20 s holes in
the subtitles with no error raised.
"""

import logging
import sys
from types import ModuleType, SimpleNamespace

import pytest

pytest.importorskip("torch")

import backend.qwen3_asr_transcribe as q3  # noqa: E402

# Fast speech produces roughly 5-6 tokens per second; the budget must leave
# headroom above that for every chunk the model can be handed.
FAST_SPEECH_TOKENS_PER_SEC = 8


def _capture_build_kwargs(monkeypatch, word_timestamps):
    captured = {}

    class FakeQwen3ASRModel:
        @classmethod
        def from_pretrained(cls, name, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace()

    fake_module = ModuleType("qwen_asr")
    fake_module.Qwen3ASRModel = FakeQwen3ASRModel
    monkeypatch.setitem(sys.modules, "qwen_asr", fake_module)

    q3._build_qwen3_model("Qwen/Qwen3-ASR-1.7B", "cpu", word_timestamps)
    return captured


@pytest.mark.parametrize("word_timestamps", [True, False])
def test_token_budget_covers_longest_chunk_of_fast_speech(
    monkeypatch, word_timestamps
):
    kwargs = _capture_build_kwargs(monkeypatch, word_timestamps)

    longest_chunk_sec = q3._max_chunk_seconds(word_timestamps)
    assert kwargs["max_new_tokens"] >= longest_chunk_sec * FAST_SPEECH_TOKENS_PER_SEC


def test_token_budget_covers_sixty_second_segment_that_used_to_truncate(
    monkeypatch,
):
    kwargs = _capture_build_kwargs(monkeypatch, word_timestamps=True)

    # A dense 60 s lecture chunk needed well over the old 256-token cap.
    assert kwargs["max_new_tokens"] > 256 * 2


def _fake_model(token_count, max_new_tokens):
    def tokenizer(text, add_special_tokens=False):
        return {"input_ids": list(range(token_count))}

    return SimpleNamespace(
        max_new_tokens=max_new_tokens,
        processor=SimpleNamespace(tokenizer=tokenizer),
    )


def test_output_hit_token_limit_flags_output_at_cap():
    model = _fake_model(token_count=1790, max_new_tokens=1800)
    assert q3._output_hit_token_limit(model, "很長的輸出") is True


def test_output_hit_token_limit_ignores_normal_output():
    model = _fake_model(token_count=300, max_new_tokens=1800)
    assert q3._output_hit_token_limit(model, "正常長度") is False


def test_output_hit_token_limit_is_safe_without_tokenizer():
    model = SimpleNamespace(max_new_tokens=1800, processor=None)
    assert q3._output_hit_token_limit(model, "任何文字") is False


def test_warn_if_truncated_logs_warning_with_time_range(caplog):
    model = _fake_model(token_count=1800, max_new_tokens=1800)

    with caplog.at_level(logging.WARNING, logger="qwen3_asr_transcribe"):
        q3._warn_if_truncated(model, "文字", start_s=60.0, label="片段 2")

    assert any("片段 2" in r.getMessage() for r in caplog.records)
