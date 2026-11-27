import pytest

from backend.shared import text_processing as tp

pytestmark = pytest.mark.skipif(
    not tp.OPENCC_AVAILABLE, reason="opencc not installed"
)


def test_convert_to_traditional_keeps_spoken_vocabulary():
    assert tp.convert_to_traditional("调试器 反调试 进程 扩展 软件 函数") == (
        "調試器 反調試 進程 擴展 軟件 函數"
    )


def test_convert_to_traditional_preserves_length():
    text = "前面我花了好几节课的时间给大家讲了软件调试的基本操作"
    assert len(tp.convert_to_traditional(text)) == len(text)


def test_convert_segment_keeps_words_in_sync_with_text():
    seg = {
        "text": "这几行汇编指令，就是标志位",
        "words": [{"word": ch, "start": i * 0.1, "end": (i + 1) * 0.1}
                  for i, ch in enumerate("这几行汇编指令就是标志位")],
    }
    out = tp.convert_segment_to_traditional(seg)
    spelled = "".join(w["word"] for w in out["words"])
    letters = "".join(ch for ch in out["text"] if ch.isalnum())
    assert spelled == letters
    assert out["text"].startswith("這幾行")


def test_convert_segment_handles_multichar_latin_words():
    seg = {
        "text": "调用 isDebuggerPresent 函数",
        "words": [
            {"word": "调", "start": 0.0, "end": 0.1},
            {"word": "用", "start": 0.1, "end": 0.2},
            {"word": "isDebuggerPresent", "start": 0.2, "end": 1.0},
            {"word": "函", "start": 1.0, "end": 1.1},
            {"word": "数", "start": 1.1, "end": 1.2},
        ],
    }
    out = tp.convert_segment_to_traditional(seg)
    assert [w["word"] for w in out["words"]] == [
        "調", "用", "isDebuggerPresent", "函", "數"
    ]
    assert out["text"] == "調用 isDebuggerPresent 函數"
