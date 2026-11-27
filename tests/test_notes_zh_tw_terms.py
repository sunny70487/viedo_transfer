from backend.shared import llm_postprocess as lp


def test_replaces_mainland_terms_with_taiwan_terms():
    src = "寄存器、線程、默認、加載、代碼、鼠標、信息、反匯編"
    out = lp._to_zh_tw_terms(src)
    assert "暫存器" in out
    assert "執行緒" in out
    assert "預設" in out
    assert "載入" in out
    assert "程式碼" in out
    assert "滑鼠" in out
    assert "資訊" in out
    assert "反組譯" in out


def test_no_selfmapping_terms_inflate_buffer():
    for cn, tw in lp._ZH_TW_TERMS:
        assert cn != tw, f"no-op term pair inflates the stream buffer: {cn}"
