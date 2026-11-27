import pytest

from backend.shared.glossary import apply_glossary, parse_glossary


def _words(tokens, step=0.2):
    return [
        {"word": tok, "start": round(i * step, 3), "end": round(i * step + step, 3)}
        for i, tok in enumerate(tokens)
    ]


def _spelled(words):
    return "".join(w["word"] for w in words)


# --- parse_glossary ---------------------------------------------------------

def test_parse_glossary_splits_terms_and_corrections():
    terms, corrections = parse_glossary("IDA\nO牛debug=>OllyDbg, 線程環境塊")

    assert terms == ["IDA", "OllyDbg", "線程環境塊"]
    assert corrections == {"O牛debug": "OllyDbg"}


def test_parse_glossary_accepts_list_and_ignores_blanks():
    terms, corrections = parse_glossary(["  PEB ", "", None, "x => "])

    assert terms == ["PEB"]
    assert corrections == {}


def test_parse_glossary_none():
    assert parse_glossary(None) == ([], {})


# --- apply_glossary: explicit corrections -----------------------------------

def test_explicit_correction_merges_words_and_keeps_span_timing():
    words = _words(["用", "O", "牛", "debug", "打", "开"])

    out = apply_glossary(words, parse_glossary("O牛debug=>OllyDbg"))

    assert [w["word"] for w in out] == ["用", "OllyDbg", "打", "开"]
    assert out[1]["start"] == words[1]["start"]
    assert out[1]["end"] == words[3]["end"]


def test_correction_keeps_trailing_punctuation_of_last_word():
    words = _words(["O", "牛", "debug，", "好"])

    out = apply_glossary(words, parse_glossary("O牛debug=>OllyDbg"))

    assert out[0]["word"] == "OllyDbg，"


def test_correction_matches_traditional_glossary_against_simplified_words():
    words = _words(list("当前进程环境块"))

    out = apply_glossary(words, parse_glossary("进程环境块=>進程環境塊"))

    assert out[-1]["word"] == "進程環境塊"


def test_no_match_across_internal_punctuation():
    words = _words(["环", "境，", "块"])

    out = apply_glossary(words, parse_glossary("环境块=>環境塊"))

    assert _spelled(out) == "环境，块"


def test_latin_term_does_not_match_inside_a_longer_token():
    words = _words(["看", "PEB", "结", "构"])

    out = apply_glossary(words, parse_glossary("PE=>P.E."))

    assert _spelled(out) == "看PEB结构"


# --- apply_glossary: plain terms --------------------------------------------

def test_plain_term_merges_into_one_unbreakable_word():
    words = _words(list("线程的线程环境块"))

    out = apply_glossary(words, parse_glossary("線程環境塊"))

    assert [w["word"] for w in out][-1] == "線程環境塊"
    assert out[-1]["glossary"] is True
    assert len(out) == 4


def test_plain_latin_term_fixes_case():
    words = _words(["调", "用", "ntqueryinformationprocess", "函", "数"])

    out = apply_glossary(words, parse_glossary("NtQueryInformationProcess"))

    assert out[2]["word"] == "NtQueryInformationProcess"


def test_plain_term_corrects_exact_homophone():
    pytest.importorskip("pypinyin")
    words = _words(list("这个线程环境快里面"))

    out = apply_glossary(words, parse_glossary("線程環境塊"))

    assert "線程環境塊" in _spelled(out)


def test_homophone_needs_two_han_characters():
    pytest.importorskip("pypinyin")
    words = _words(list("他是一个快人"))

    out = apply_glossary(words, parse_glossary("塊"))

    assert _spelled(out) == "他是一个快人"


def test_empty_glossary_returns_words_unchanged():
    words = _words(list("你好"))

    assert apply_glossary(words, ([], {})) == words
