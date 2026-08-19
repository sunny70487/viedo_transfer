import backend.shared.engine_routing as er


def test_routes_qwen_model_to_qwen_engine(monkeypatch):
    seen = {}
    monkeypatch.setattr(er, "_qwen3_transcribe", lambda **kw: seen.update(kw))
    monkeypatch.setattr(er, "_funasr_transcribe", lambda **kw: seen.update(bad=True))

    er.transcribe_audio(audio_path="a.wav", model_size="qwen3-asr-1.7b")

    assert seen["model_size"] == "qwen3-asr-1.7b"
    assert "bad" not in seen


def test_routes_legacy_model_to_funasr_engine(monkeypatch):
    seen = {}
    monkeypatch.setattr(er, "_funasr_transcribe", lambda **kw: seen.update(kw))
    monkeypatch.setattr(er, "_qwen3_transcribe", lambda **kw: seen.update(bad=True))

    er.transcribe_audio(audio_path="a.wav", model_size="sensevoice")

    assert seen["model_size"] == "sensevoice"
    assert "bad" not in seen


def test_drops_kwargs_the_target_engine_cannot_accept(monkeypatch):
    seen = {}

    def only_basic(*, audio_path, model_size, verbose=True):
        seen.update(audio_path=audio_path, model_size=model_size)

    monkeypatch.setattr(er, "_funasr_transcribe", only_basic)

    er.transcribe_audio(
        audio_path="a.wav",
        model_size="sensevoice",
        speaker_diarization=True,
        hotwords=["IDA"],
    )

    assert seen == {"audio_path": "a.wav", "model_size": "sensevoice"}


def test_keeps_kwargs_the_target_engine_supports(monkeypatch):
    seen = {}

    def rich(*, audio_path, model_size, hotwords=None, context=None):
        seen.update(hotwords=hotwords, context=context)

    monkeypatch.setattr(er, "_qwen3_transcribe", rich)

    er.transcribe_audio(
        audio_path="a.wav",
        model_size="qwen3-asr-1.7b",
        hotwords=["IDA"],
        context="逆向工程",
    )

    assert seen == {"hotwords": ["IDA"], "context": "逆向工程"}


def test_forwards_everything_when_engine_accepts_var_keyword(monkeypatch):
    seen = {}
    monkeypatch.setattr(er, "_qwen3_transcribe", lambda **kw: seen.update(kw))

    er.transcribe_audio(
        audio_path="a.wav", model_size="qwen3-asr-1.7b", anything="kept"
    )

    assert seen["anything"] == "kept"
