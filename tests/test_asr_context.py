from backend.shared.asr_context import build_asr_context


def test_build_asr_context_returns_empty_string_when_no_input():
    assert build_asr_context() == ""


def test_build_asr_context_passes_through_plain_context():
    assert build_asr_context(context="這是一堂 Linux 核心課程") == \
        "這是一堂 Linux 核心課程"


def test_build_asr_context_joins_hotwords_with_commas():
    result = build_asr_context(hotwords=["shellcode", "VirtualAlloc"])

    assert "shellcode" in result
    assert "VirtualAlloc" in result
    assert "shellcode, VirtualAlloc" in result


def test_build_asr_context_accepts_hotwords_as_newline_string():
    result = build_asr_context(hotwords="shellcode\nVirtualAlloc\n\nWin32")

    assert "shellcode, VirtualAlloc, Win32" in result


def test_build_asr_context_combines_context_and_hotwords():
    result = build_asr_context(context="逆向工程課程", hotwords=["IDA"])

    assert result.startswith("逆向工程課程")
    assert "IDA" in result


def test_build_asr_context_deduplicates_hotwords_preserving_order():
    result = build_asr_context(hotwords=["IDA", "PE", "IDA", "pe"])

    assert result.count("IDA") == 1
    assert result.index("IDA") < result.index("PE")


def test_build_asr_context_strips_whitespace_around_hotwords():
    result = build_asr_context(hotwords=["  shellcode  ", "", "  "])

    assert "shellcode" in result
    assert "  " not in result


def test_build_asr_context_truncates_to_max_chars():
    result = build_asr_context(
        hotwords=[f"term{i:04d}" for i in range(500)], max_chars=100
    )

    assert len(result) <= 100


def test_build_asr_context_truncation_does_not_cut_mid_term():
    result = build_asr_context(hotwords=["alpha", "beta", "gamma"],
                               max_chars=12)

    for piece in result.split(", "):
        assert piece in ("alpha", "beta", "gamma")


def test_build_asr_context_sends_only_correct_side_of_corrections():
    result = build_asr_context(hotwords="O牛debug=>OllyDbg\nIDA")

    assert result == "OllyDbg, IDA"


def test_build_asr_context_ignores_non_string_hotwords():
    result = build_asr_context(hotwords=["IDA", None, 42, "PE"])

    assert "IDA" in result
    assert "PE" in result
