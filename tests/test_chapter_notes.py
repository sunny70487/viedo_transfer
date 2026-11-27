import json

import pytest

from backend.shared import chapter_notes as cn

SEGMENTS = [
    {"start": 0.0, "end": 4.0, "text": "大家好"},
    {"start": 5.0, "end": 9.0, "text": "今天講堆疊"},
    {"start": 65.0, "end": 70.0, "text": "push 與 pop"},
    {"start": 130.0, "end": 140.0, "text": "作業下週交"},
    {"start": 200.0, "end": 215.5, "text": "pop 的回傳值"},
]

SECTIONS = [
    {"id": "s001", "title": "開場", "start": 0.0, "end": 65.0,
     "summary": "s1", "importance": "supplementary"},
    {"id": "s002", "title": "堆疊操作", "start": 65.0, "end": 130.0,
     "summary": "s2", "importance": "core"},
    {"id": "s003", "title": "作業說明", "start": 130.0, "end": 200.0,
     "summary": "s3", "importance": "optional"},
    {"id": "s004", "title": "回傳值", "start": 200.0, "end": 215.5,
     "summary": "s4", "importance": "core"},
]

GROUPING = {
    "title": "堆疊入門",
    "overview": "總覽",
    "chapters": [
        {"title": "課程導論", "summary": "c1", "importance": "supplementary",
         "sections": ["s001"]},
        {"title": "堆疊操作", "summary": "c2", "importance": "core",
         "sections": ["s002", "s004"]},
    ],
    "logistics": ["s003"],
}

OUTLINE = {
    "title": "堆疊入門",
    "overview": "總覽",
    "grouped": True,
    "chapters": [
        {"id": "c01", "title": "課程導論", "summary": "c1",
         "importance": "supplementary", "kind": "topic",
         "sections": [SECTIONS[0]]},
        {"id": "c02", "title": "堆疊操作", "summary": "c2",
         "importance": "core", "kind": "topic",
         "sections": [SECTIONS[1], SECTIONS[3]]},
        {"id": "c03", "title": cn.LOGISTICS_TITLE,
         "summary": cn.LOGISTICS_SUMMARY, "importance": "optional",
         "kind": "logistics", "sections": [SECTIONS[2]]},
    ],
}


class _Obj:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _fake_openai(monkeypatch, replies):
    """Each reply is a str (plain completion), a list of str (stream pieces),
    an Exception to raise, or a ready-made stream object returned as is.
    Replies are consumed one per API call."""
    calls = []
    queue = list(replies)

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            reply = queue.pop(0)
            if isinstance(reply, Exception):
                raise reply
            if isinstance(reply, list):
                return iter(
                    _Obj(choices=[_Obj(delta=_Obj(content=piece))])
                    for piece in reply
                )
            if isinstance(reply, str):
                return _Obj(choices=[_Obj(message=_Obj(content=reply))])
            return reply

    class FakeClient:
        chat = _Obj(completions=FakeCompletions())

        def __init__(self, **_kwargs):
            pass

    import openai

    monkeypatch.setattr(openai, "OpenAI", FakeClient)
    return calls


def _raw_section(time, title, summary="重點", importance="core"):
    return {"time": time, "title": title, "summary": summary,
            "importance": importance}


def _dump(data):
    return json.dumps(data, ensure_ascii=False)


def _section_ids(outline):
    return [[s["id"] for s in c["sections"]] for c in outline["chapters"]]


# --- normalize_sections -----------------------------------------------------

def test_normalize_sections_sorts_and_fills_ids_and_boundaries():
    raw = [
        _raw_section("03:20", "回傳值", "s4"),
        _raw_section("00:05", "開場", "s1", "supplementary"),
        _raw_section(65, "堆疊操作", "s2"),
        _raw_section("02:10", "作業說明", "s3", "optional"),
    ]

    assert cn.normalize_sections(raw, SEGMENTS) == SECTIONS


def test_normalize_sections_drops_blank_titles_and_duplicate_starts():
    raw = [
        _raw_section("00:00", "第一節"),
        _raw_section("01:05", "   "),
        _raw_section("01:05", "第二節"),
        _raw_section("01:05", "重複的開始時間"),
        "not a dict",
    ]

    sections = cn.normalize_sections(raw, SEGMENTS)

    assert [s["title"] for s in sections] == ["第一節", "第二節"]


def test_normalize_sections_defaults_unknown_importance():
    raw = [
        _raw_section("00:00", "A", importance="very important"),
        {"time": "01:05", "title": "B"},
    ]

    sections = cn.normalize_sections(raw, SEGMENTS)

    assert [s["importance"] for s in sections] == [
        "supplementary", "supplementary",
    ]
    assert sections[1]["summary"] == ""


def test_normalize_sections_merges_sections_without_segments():
    raw = [
        _raw_section("00:00", "A"),
        _raw_section("00:30", "沒有字幕的小節"),
        _raw_section("01:05", "B"),
        _raw_section("10:00", "超出影片長度"),
    ]

    sections = cn.normalize_sections(raw, SEGMENTS)

    assert [(s["id"], s["title"], s["start"], s["end"]) for s in sections] == [
        ("s001", "A", 0.0, 65.0),
        ("s002", "B", 65.0, 215.5),
    ]


def test_normalize_sections_first_section_always_starts_at_zero():
    sections = cn.normalize_sections(
        [_raw_section("01:05", "只有一節")], SEGMENTS
    )

    assert len(sections) == 1
    assert (sections[0]["start"], sections[0]["end"]) == (0.0, 215.5)


def test_normalize_sections_uses_taiwan_terms():
    sections = cn.normalize_sections(
        [_raw_section("00:00", "內存與線程", "默認的代碼")], SEGMENTS
    )

    assert sections[0]["title"] == "記憶體與執行緒"
    assert sections[0]["summary"] == "預設的程式碼"


def test_normalize_sections_splits_overlong_section(monkeypatch):
    monkeypatch.setattr(cn, "_MAX_TRANSCRIPT_CHARS", 40)
    segments = [
        {"start": float(i * 10), "end": float(i * 10 + 9), "text": "字" * 10}
        for i in range(6)
    ]

    sections = cn.normalize_sections(
        [_raw_section("00:00", "很長的一節")], segments
    )

    assert [(s["id"], s["title"], s["start"], s["end"]) for s in sections] == [
        ("s001", "很長的一節（1/3）", 0.0, 20.0),
        ("s002", "很長的一節（2/3）", 20.0, 40.0),
        ("s003", "很長的一節（3/3）", 40.0, 59.0),
    ]
    assert {s["summary"] for s in sections} == {"重點"}


@pytest.mark.parametrize(
    "raw", [None, {}, [], "nope", [_raw_section("00:00", "")]],
)
def test_normalize_sections_rejects_input_without_sections(raw):
    with pytest.raises(RuntimeError, match="章節規劃格式錯誤"):
        cn.normalize_sections(raw, SEGMENTS)


def test_normalize_sections_rejects_too_many_sections():
    segments = [
        {"start": float(i), "end": float(i) + 0.5, "text": "x"}
        for i in range(301)
    ]
    raw = [_raw_section(i, f"小節 {i}") for i in range(301)]

    with pytest.raises(RuntimeError, match="章節數量過多"):
        cn.normalize_sections(raw, segments)


# --- slice_section_segments -------------------------------------------------

def test_slice_section_segments_uses_half_open_range():
    texts = [s["text"] for s in cn.slice_section_segments(
        SEGMENTS, SECTIONS[0], is_last=False
    )]
    assert texts == ["大家好", "今天講堆疊"]


def test_slice_section_segments_last_section_takes_the_rest():
    section = dict(SECTIONS[2], end=131.0)
    texts = [s["text"] for s in cn.slice_section_segments(
        SEGMENTS, section, is_last=True
    )]
    assert texts == ["作業下週交", "pop 的回傳值"]


# --- build_outline ----------------------------------------------------------

def test_build_outline_groups_distant_sections_and_puts_logistics_last():
    assert cn.build_outline(SECTIONS, GROUPING, SEGMENTS) == OUTLINE


def test_build_outline_keeps_chapter_order_and_sorts_sections_by_time():
    grouping = {"chapters": [
        {"title": "堆疊", "sections": ["s004", "s002"]},
        {"title": "導論", "sections": ["s001"]},
    ], "logistics": ["s003"]}

    outline = cn.build_outline(SECTIONS, grouping, SEGMENTS)

    assert [c["title"] for c in outline["chapters"]] == [
        "堆疊", "導論", cn.LOGISTICS_TITLE,
    ]
    assert _section_ids(outline) == [["s002", "s004"], ["s001"], ["s003"]]


def test_build_outline_uses_each_section_once_and_ignores_unknown_ids():
    grouping = {"chapters": [
        {"title": "甲", "sections": ["s001", "s002", "s999", 7, ["s004"]]},
        {"title": "乙", "sections": ["s002", "s004"]},
        {"title": "沒有有效小節", "sections": ["s001", "nope"]},
        "not a dict",
    ], "logistics": ["s001", "s003", "s998"]}

    outline = cn.build_outline(SECTIONS, grouping, SEGMENTS)

    assert [c["title"] for c in outline["chapters"]] == [
        "甲", "乙", cn.LOGISTICS_TITLE,
    ]
    assert _section_ids(outline) == [["s001", "s002"], ["s004"], ["s003"]]


def test_build_outline_places_sections_the_grouping_forgot():
    sections = SECTIONS + [
        {"id": "s005", "title": "忘記的知識", "start": 215.5, "end": 300.0,
         "summary": "", "importance": "core"},
    ]
    grouping = {"chapters": [
        {"title": "導論", "sections": ["s001"]},
        {"title": "回傳值", "sections": ["s004"]},
    ]}

    outline = cn.build_outline(sections, grouping, SEGMENTS)

    # s002 (core) joins the chapter of the nearest earlier section, s003
    # (optional) goes to logistics, s005 follows s004.
    assert _section_ids(outline) == [
        ["s001", "s002"], ["s004", "s005"], ["s003"],
    ]
    assert outline["chapters"][2]["kind"] == "logistics"


def test_build_outline_forgotten_first_section_joins_the_next_chapter():
    grouping = {"chapters": [{"title": "堆疊", "sections": ["s002", "s004"]}]}

    outline = cn.build_outline(SECTIONS, grouping, SEGMENTS)

    assert _section_ids(outline) == [["s001", "s002", "s004"], ["s003"]]


@pytest.mark.parametrize(
    "grouping", [None, {}, "nope", {"chapters": []},
                 {"chapters": [{"title": "x", "sections": ["s999"]}]}],
)
def test_build_outline_without_usable_grouping_keeps_one_chapter_per_section(
    grouping,
):
    outline = cn.build_outline(
        SECTIONS, grouping, SEGMENTS, title=" 備用標題 ", overview="備用總覽"
    )

    assert outline["grouped"] is False
    assert outline["title"] == "備用標題"
    assert outline["overview"] == "備用總覽"
    assert [(c["id"], c["title"], c["importance"], c["kind"])
            for c in outline["chapters"]] == [
        ("c01", "開場", "supplementary", "topic"),
        ("c02", "堆疊操作", "core", "topic"),
        ("c03", "回傳值", "core", "topic"),
        ("c04", cn.LOGISTICS_TITLE, "optional", "logistics"),
    ]
    assert _section_ids(outline) == [["s001"], ["s002"], ["s004"], ["s003"]]
    assert outline["chapters"][1]["summary"] == "s2"


def test_build_outline_fills_missing_chapter_fields_from_its_sections():
    grouping = {"chapters": [
        {"title": "  ", "summary": 5, "importance": "huge",
         "sections": ["s001", "s002"]},
        {"title": "# 內存管理", "summary": "默認行為", "sections": ["s004"]},
    ], "logistics": ["s003"]}

    first, second, _ = cn.build_outline(SECTIONS, grouping, SEGMENTS)["chapters"]

    assert (first["title"], first["summary"], first["importance"]) == (
        "開場", "s1", "core",
    )
    assert (second["title"], second["summary"]) == ("記憶體管理", "預設行為")


def test_build_outline_has_no_logistics_chapter_when_nothing_is_logistics():
    grouping = {"chapters": [
        {"title": "全部", "sections": ["s001", "s002", "s003", "s004"]},
    ]}

    outline = cn.build_outline(SECTIONS, grouping, SEGMENTS)

    assert [c["kind"] for c in outline["chapters"]] == ["topic"]


def test_build_outline_falls_back_to_default_title():
    outline = cn.build_outline(SECTIONS, {"chapters": []}, SEGMENTS)
    assert outline["title"] == "學習筆記"
    assert outline["overview"] == ""


def test_build_outline_splits_chapter_too_long_for_one_request(monkeypatch):
    monkeypatch.setattr(cn, "_MAX_TRANSCRIPT_CHARS", 30)
    grouping = {"chapters": [
        {"title": "全部", "summary": "c", "importance": "core",
         "sections": ["s001", "s002", "s003", "s004"]},
    ]}

    outline = cn.build_outline(SECTIONS, grouping, SEGMENTS)

    assert [(c["id"], c["title"]) for c in outline["chapters"]] == [
        ("c01", "全部（1/3）"), ("c02", "全部（2/3）"), ("c03", "全部（3/3）"),
    ]
    assert _section_ids(outline) == [["s001"], ["s002"], ["s003", "s004"]]
    assert {c["summary"] for c in outline["chapters"]} == {"c"}


def test_build_outline_rejects_too_many_chapters():
    segments = [
        {"start": float(i), "end": float(i) + 0.5, "text": "x"}
        for i in range(100)
    ]
    sections = cn.normalize_sections(
        [_raw_section(i, f"小節 {i}") for i in range(100)], segments
    )

    with pytest.raises(RuntimeError, match="章節數量過多"):
        cn.build_outline(sections, None, segments)


# --- upgrade_outline --------------------------------------------------------

def test_upgrade_outline_keeps_current_format_unchanged():
    assert cn.upgrade_outline(json.loads(_dump(OUTLINE))) == OUTLINE


def test_upgrade_outline_preserves_excluded_sections():
    stored = cn.apply_section_exclusions(OUTLINE, ["s004"])

    upgraded = cn.upgrade_outline(json.loads(_dump(stored)))

    assert upgraded == stored
    assert upgraded["chapters"][1]["sections"][1]["excluded"] is True


def test_upgrade_outline_converts_flat_chapters_to_single_section_chapters():
    flat = {
        "title": "舊規劃",
        "overview": "舊總覽",
        "chapters": [
            {"id": "c01", "title": "開場", "start": 0.0, "end": 65,
             "summary": "s1", "importance": "optional"},
            {"id": "c02", "title": "堆疊操作", "start": 65.0, "end": 215.5,
             "summary": "s2", "importance": "core"},
        ],
    }

    assert cn.upgrade_outline(flat) == {
        "title": "舊規劃",
        "overview": "舊總覽",
        "grouped": False,
        "chapters": [
            {"id": "c01", "title": "開場", "summary": "s1",
             "importance": "optional", "kind": "topic",
             "sections": [{"id": "s001", "title": "開場", "start": 0.0,
                           "end": 65.0, "summary": "s1",
                           "importance": "optional"}]},
            {"id": "c02", "title": "堆疊操作", "summary": "s2",
             "importance": "core", "kind": "topic",
             "sections": [{"id": "s002", "title": "堆疊操作", "start": 65.0,
                           "end": 215.5, "summary": "s2",
                           "importance": "core"}]},
        ],
    }


@pytest.mark.parametrize(
    "data",
    [
        None, [], "x", {}, {"chapters": []}, {"chapters": "x"},
        {"chapters": ["x"]},
        {"chapters": [{"id": "c1", "title": "t", "start": 0, "end": 1}]},
        {"chapters": [{"id": "c01", "title": "t"}]},
        {"chapters": [{"id": "c01", "title": "t", "start": "a", "end": 1}]},
        {"chapters": [{"id": "c01", "title": "t", "sections": []}]},
        {"chapters": [{"id": "c01", "title": "t", "sections": ["s001"]}]},
        {"chapters": [{"id": "c01", "title": "t", "sections": [
            {"id": "bad", "start": 0, "end": 1}]}]},
        {"chapters": [{"id": "c01", "title": "t", "sections": [
            {"id": "s001", "start": None, "end": 1}]}]},
    ],
)
def test_upgrade_outline_rejects_unusable_data(data):
    assert cn.upgrade_outline(data) is None


# --- apply_section_exclusions -----------------------------------------------

def test_apply_section_exclusions_marks_only_listed_sections():
    outline = cn.apply_section_exclusions(OUTLINE, ["s004", "s999"])

    flags = [
        [s.get("excluded", False) for s in c["sections"]]
        for c in outline["chapters"]
    ]
    assert flags == [[False], [False, True], [False]]
    assert "excluded" not in OUTLINE["chapters"][1]["sections"][1]


def test_apply_section_exclusions_replaces_earlier_exclusions():
    first = cn.apply_section_exclusions(OUTLINE, ["s004"])

    second = cn.apply_section_exclusions(first, ["s002"])

    assert [s.get("excluded", False)
            for s in second["chapters"][1]["sections"]] == [True, False]


def test_apply_section_exclusions_never_empties_a_chapter():
    outline = cn.apply_section_exclusions(OUTLINE, ["s001", "s002", "s004"])

    assert all(
        not s.get("excluded")
        for c in outline["chapters"] for s in c["sections"]
    )


# --- chapter_transcript -----------------------------------------------------

def test_chapter_transcript_labels_each_section_of_the_chapter():
    text = cn.chapter_transcript(SEGMENTS, OUTLINE, OUTLINE["chapters"][1])

    assert text == (
        "【小節】堆疊操作（01:05–02:10）\n[01:05] push 與 pop\n\n"
        "【小節】回傳值（03:20–03:35）\n[03:20] pop 的回傳值"
    )


def test_chapter_transcript_skips_excluded_sections():
    outline = cn.apply_section_exclusions(OUTLINE, ["s002"])

    text = cn.chapter_transcript(SEGMENTS, outline, outline["chapters"][1])

    assert text == "【小節】回傳值（03:20–03:35）\n[03:20] pop 的回傳值"


def test_chapter_transcript_last_section_of_the_video_takes_the_rest():
    segments = SEGMENTS + [{"start": 230.0, "end": 240.0, "text": "補充一句"}]

    text = cn.chapter_transcript(segments, OUTLINE, OUTLINE["chapters"][1])

    assert text.endswith("[03:20] pop 的回傳值\n[03:50] 補充一句")
    assert "補充一句" not in cn.chapter_transcript(
        segments, OUTLINE, OUTLINE["chapters"][2]
    )


# --- plan_note_outline ------------------------------------------------------

WINDOW_REPLY = _dump({
    "title": "堆疊第一段",
    "overview": "逐字稿總覽",
    "sections": [
        _raw_section("00:00", "開場", "s1", "supplementary"),
        _raw_section("01:05", "堆疊操作", "s2"),
        _raw_section("02:10", "作業說明", "s3", "optional"),
        _raw_section("03:20", "回傳值", "s4"),
    ],
})


def test_split_windows_breaks_on_line_boundaries():
    assert cn._split_windows(["aaaa", "bbbb", "cc", "dddddddd"], 9) == [
        "aaaa\nbbbb", "cc", "dddddddd",
    ]
    assert cn._split_windows(["a" * 50], 9) == ["a" * 50]


def test_plan_note_outline_sections_the_transcript_then_groups_it(monkeypatch):
    calls = _fake_openai(
        monkeypatch, [f"```json\n{WINDOW_REPLY}\n```", _dump(GROUPING)]
    )

    outline = cn.plan_note_outline(
        SEGMENTS, api_key="k", model="m", content_hint="組合語言課"
    )

    assert outline == OUTLINE
    assert len(calls) == 2
    assert {call["model"] for call in calls} == {"m"}
    sectioning = calls[0]["messages"][1]["content"]
    assert "【內容描述】組合語言課" in sectioning
    assert "[01:05] push 與 pop" in sectioning
    assert "段" not in sectioning.split("[00:00]")[0]
    grouping = calls[1]["messages"][1]["content"]
    assert "【內容描述】組合語言課" in grouping
    assert "s002 | 01:05–02:10 | core | 堆疊操作 — s2" in grouping
    assert "s003 | 02:10–03:20 | optional | 作業說明 — s3" in grouping
    assert "push 與 pop" not in grouping


def test_plan_note_outline_plans_long_transcripts_in_windows(monkeypatch):
    monkeypatch.setattr(cn, "_MAX_TRANSCRIPT_CHARS", 30)
    replies = [
        _dump({"title": "第一段標題", "overview": "前段。",
               "sections": [_raw_section("00:00", "開場", "s1")]}),
        _dump({"title": "第二段標題", "overview": "中段。",
               "sections": [_raw_section("01:05", "堆疊操作", "s2")]}),
        _dump({"title": "第三段標題", "overview": "後段。",
               "sections": [_raw_section("02:10", "作業說明", "s3"),
                            _raw_section("03:20", "回傳值", "s4")]}),
        _dump(GROUPING),
    ]
    calls = _fake_openai(monkeypatch, replies)

    outline = cn.plan_note_outline(SEGMENTS, api_key="k")

    assert len(calls) == 4
    assert outline["title"] == "堆疊入門"
    assert outline["overview"] == "總覽"
    assert outline["grouped"] is True
    # The 30-char limit that forces three windows also makes the merged
    # chapter (s002 + s004) too long for one request, so it comes back in
    # two parts.
    assert [c["title"] for c in outline["chapters"]] == [
        "課程導論", "堆疊操作（1/2）", "堆疊操作（2/2）", cn.LOGISTICS_TITLE,
    ]
    assert _section_ids(outline) == [["s001"], ["s002"], ["s004"], ["s003"]]
    second = calls[1]["messages"][1]["content"]
    assert "第 2/3 段" in second
    assert "- 開場" in second
    assert "[01:05] push 與 pop" in second
    assert "[00:00]" not in second
    third = calls[2]["messages"][1]["content"]
    assert "- 開場" in third and "- 堆疊操作" in third
    assert "[02:10] 作業下週交\n[03:20] pop 的回傳值" in third
    grouping = calls[3]["messages"][1]["content"]
    assert "<transcript>" not in grouping
    assert grouping.count("\ns00") == 4


def test_plan_note_outline_retries_grouping_once(monkeypatch):
    calls = _fake_openai(
        monkeypatch, [WINDOW_REPLY, "抱歉，我無法處理", _dump(GROUPING)]
    )

    outline = cn.plan_note_outline(SEGMENTS, api_key="k")

    assert len(calls) == 3
    assert outline == OUTLINE


@pytest.mark.parametrize(
    "failures",
    [
        ["not json", '{"chapters": []}'],
        [Exception("rate limited"), Exception("rate limited")],
        ['{"chapters": [{"title": "x", "sections": ["s999"]}]}', "[1, 2]"],
    ],
)
def test_plan_note_outline_keeps_sections_when_grouping_fails(
    monkeypatch, failures
):
    calls = _fake_openai(monkeypatch, [WINDOW_REPLY] + failures)

    outline = cn.plan_note_outline(SEGMENTS, api_key="k")

    assert len(calls) == 3
    assert outline["grouped"] is False
    assert outline["title"] == "堆疊第一段"
    assert outline["overview"] == "逐字稿總覽"
    assert _section_ids(outline) == [["s001"], ["s002"], ["s004"], ["s003"]]


def test_plan_note_outline_drops_stitched_overview_when_grouping_fails(
    monkeypatch,
):
    monkeypatch.setattr(cn, "_MAX_TRANSCRIPT_CHARS", 30)
    replies = [
        _dump({"title": f"第 {n} 段", "overview": f"第 {n} 段的總覽。",
               "sections": [_raw_section(time, f"小節 {n}")]})
        for n, time in enumerate(["00:00", "01:05", "02:10"], 1)
    ] + ["bad", "bad"]
    calls = _fake_openai(monkeypatch, replies)

    outline = cn.plan_note_outline(SEGMENTS, api_key="k")

    assert len(calls) == 5
    assert outline["grouped"] is False
    assert outline["title"] == "第 1 段"
    assert outline["overview"] == ""


def test_plan_note_outline_skips_grouping_for_a_single_section(monkeypatch):
    reply = _dump({"title": "T", "overview": "O",
                   "sections": [_raw_section("00:00", "只有一節")]})
    calls = _fake_openai(monkeypatch, [reply])

    outline = cn.plan_note_outline(SEGMENTS, api_key="k")

    assert len(calls) == 1
    assert outline["grouped"] is True
    assert (outline["title"], outline["overview"]) == ("T", "O")
    assert _section_ids(outline) == [["s001"]]


@pytest.mark.parametrize(
    "reply",
    ["抱歉，我無法處理", "[1, 2, 3]", '{"title": "x"}', '{"sections": "x"}'],
)
def test_plan_note_outline_rejects_malformed_sectioning_reply(
    monkeypatch, reply
):
    _fake_openai(monkeypatch, [reply])
    with pytest.raises(RuntimeError, match="章節規劃格式錯誤"):
        cn.plan_note_outline(SEGMENTS, api_key="k")


def test_plan_note_outline_wraps_api_errors(monkeypatch):
    _fake_openai(monkeypatch, [Exception("rate limited")])
    with pytest.raises(RuntimeError, match="rate limited"):
        cn.plan_note_outline(SEGMENTS, api_key="k")


def test_plan_note_outline_requires_segments_and_key(monkeypatch):
    _fake_openai(monkeypatch, [])
    with pytest.raises(RuntimeError, match="目前沒有字幕資料"):
        cn.plan_note_outline([], api_key="k")
    with pytest.raises(RuntimeError, match="未提供 LLM API Key"):
        cn.plan_note_outline(SEGMENTS, api_key="")


def test_planning_prompts_separate_knowledge_from_course_admin():
    for prompt in (cn._SECTION_SYSTEM_PROMPT, cn._GROUPING_SYSTEM_PROMPT):
        assert "課程行政" in prompt
        assert "作業" in prompt
    assert '"logistics"' in cn._GROUPING_SYSTEM_PROMPT
    assert '"sections"' in cn._SECTION_SYSTEM_PROMPT


# --- generate_chapter_note --------------------------------------------------

def _chapter(monkeypatch, pieces, chapter_id="c02", outline=OUTLINE, **kwargs):
    calls = _fake_openai(monkeypatch, [pieces])
    out = "".join(cn.generate_chapter_note(
        SEGMENTS, outline=outline, chapter_id=chapter_id, api_key="k", **kwargs
    ))
    return out, calls


def test_chapter_note_starts_with_outline_heading(monkeypatch):
    out, calls = _chapter(monkeypatch, ["內文第一段。\n", "更多內容。"])

    assert out == "## 堆疊操作\n\n內文第一段。\n更多內容。"
    assert calls[0]["stream"] is True


def test_chapter_note_drops_heading_written_by_model(monkeypatch):
    out, _ = _chapter(monkeypatch, ["\n#", "# 堆疊操作：推入\n\n內", "文"])
    assert out == "## 堆疊操作\n\n內文"


def test_chapter_note_keeps_leading_subheading(monkeypatch):
    out, _ = _chapter(monkeypatch, ["### 子概念\n內文"])
    assert out == "## 堆疊操作\n\n### 子概念\n內文"


def test_chapter_note_replaces_terms_split_across_chunks(monkeypatch):
    out, _ = _chapter(monkeypatch, ["這是寄", "存器與線", "程的默", "認行為。"])

    assert "暫存器" in out and "執行緒" in out and "預設" in out
    assert "寄存器" not in out and "線程" not in out


def test_chapter_note_replaces_term_straddling_the_emit_boundary(monkeypatch):
    # The term sits in the middle of one chunk, right where the held-back
    # tail begins; cutting there would emit "寄存" and keep "器".
    out, _ = _chapter(monkeypatch, ["甲甲甲寄存器乙乙乙", "丙丙丙匯編語言", "丁"])

    assert out == "## 堆疊操作\n\n甲甲甲暫存器乙乙乙丙丙丙組合語言丁"


def test_chapter_note_keeps_first_line_that_only_looks_like_a_heading(
    monkeypatch,
):
    out, _ = _chapter(monkeypatch, ["#include 是前置處理指令\n內文"])
    assert out == "## 堆疊操作\n\n#include 是前置處理指令\n內文"


def test_chapter_note_prompt_gathers_every_section_of_the_chapter(monkeypatch):
    _, calls = _chapter(monkeypatch, ["內文"], content_hint="組合語言課")

    user = calls[0]["messages"][1]["content"]
    assert "【內容描述】組合語言課" in user
    assert "筆記標題：堆疊入門" in user
    assert "1. 課程導論 — c1" in user
    assert "2. 【本章】堆疊操作 — c2" in user
    assert cn.LOGISTICS_TITLE not in user
    assert (
        "<transcript>\n"
        "【小節】堆疊操作（01:05–02:10）\n[01:05] push 與 pop\n\n"
        "【小節】回傳值（03:20–03:35）\n[03:20] pop 的回傳值\n"
        "</transcript>"
    ) in user
    assert "作業下週交" not in user
    assert "<references>" not in user
    assert "<requirements>" in user
    assert user.rstrip().endswith("</requirements>")


def test_chapter_note_prompt_leaves_out_excluded_sections(monkeypatch):
    outline = cn.apply_section_exclusions(OUTLINE, ["s004"])

    _, calls = _chapter(monkeypatch, ["內文"], outline=outline)

    user = calls[0]["messages"][1]["content"]
    assert "push 與 pop" in user
    assert "pop 的回傳值" not in user


def test_chapter_note_prompt_includes_reference_block(monkeypatch):
    block = '<reference source="講義">\nPUSH 會先遞減 ESP\n</reference>'
    _, calls = _chapter(monkeypatch, ["內文"], reference_block=block)

    user = calls[0]["messages"][1]["content"]
    assert f"<references>\n{block}\n</references>" in user
    assert user.index("<references>") < user.index("<transcript>")


def test_logistics_chapter_is_written_as_course_admin_when_requested(
    monkeypatch,
):
    out, calls = _chapter(monkeypatch, ["下週交作業。"], chapter_id="c03")

    user = calls[0]["messages"][1]["content"]
    assert out.startswith(f"## {cn.LOGISTICS_TITLE}\n\n")
    assert f"3. 【本章】{cn.LOGISTICS_TITLE}" in user
    assert "[02:10] 作業下週交" in user
    assert cn._LOGISTICS_CHAPTER_NOTE in user
    assert cn._LOGISTICS_CHAPTER_NOTE not in _chapter(
        monkeypatch, ["內文"]
    )[1][0]["messages"][1]["content"]


def test_chapter_note_rejects_unknown_chapter(monkeypatch):
    with pytest.raises(RuntimeError, match="找不到這個章節"):
        _chapter(monkeypatch, ["內文"], chapter_id="c09")


def test_chapter_note_rejects_empty_model_output(monkeypatch):
    with pytest.raises(RuntimeError, match="模型沒有產生內容"):
        _chapter(monkeypatch, ["## 只有標題"])


def test_chapter_note_wraps_api_errors(monkeypatch):
    _fake_openai(monkeypatch, [Exception("rate limited")])
    gen = cn.generate_chapter_note(
        SEGMENTS, outline=OUTLINE, chapter_id="c02", api_key="k"
    )
    with pytest.raises(RuntimeError, match="rate limited"):
        list(gen)


class _RecordingStream:
    """Stands in for openai.Stream, which keeps its HTTP response open until
    close() is called (it is part of a reference cycle, so dropping it is not
    enough)."""

    def __init__(self, pieces):
        self.pieces = pieces
        self.closed = 0

    def __iter__(self):
        for piece in self.pieces:
            yield _Obj(choices=[_Obj(delta=_Obj(content=piece))])

    def close(self):
        self.closed += 1


def test_chapter_note_closes_llm_stream_when_abandoned(monkeypatch):
    stream = _RecordingStream(["甲" * 20, "乙" * 20, "丙" * 20])
    _fake_openai(monkeypatch, [stream])
    gen = cn.generate_chapter_note(
        SEGMENTS, outline=OUTLINE, chapter_id="c02", api_key="k"
    )

    assert next(gen) == "## 堆疊操作\n\n"
    assert next(gen).startswith("甲")
    assert stream.closed == 0
    gen.close()

    assert stream.closed == 1


def test_chapter_note_closes_llm_stream_after_normal_completion(monkeypatch):
    stream = _RecordingStream(["內文"])
    _fake_openai(monkeypatch, [stream])

    out = "".join(cn.generate_chapter_note(
        SEGMENTS, outline=OUTLINE, chapter_id="c02", api_key="k"
    ))

    assert out == "## 堆疊操作\n\n內文"
    assert stream.closed == 1


def test_chapter_note_requires_api_key(monkeypatch):
    _fake_openai(monkeypatch, [])
    gen = cn.generate_chapter_note(
        SEGMENTS, outline=OUTLINE, chapter_id="c02", api_key=""
    )
    with pytest.raises(RuntimeError, match="未提供 LLM API Key"):
        list(gen)


def test_chapter_prompts_request_diagrams_and_concept_anim_blocks():
    assert "```concept-anim" in cn._CHAPTER_SYSTEM_PROMPT
    assert "<reference>" in cn._CHAPTER_SYSTEM_PROMPT
    assert "concept-anim" in cn._CHAPTER_REQUIREMENTS
    assert "Mermaid" in cn._CHAPTER_REQUIREMENTS


def test_chapter_prompts_ask_for_one_thread_without_course_admin():
    for prompt in (cn._CHAPTER_SYSTEM_PROMPT, cn._CHAPTER_REQUIREMENTS):
        assert "課程行政" in prompt
        assert "小節" in prompt


# --- linked pages -----------------------------------------------------------

CANDIDATES = [
    {"url": "https://a.test/pointer", "title": "指標篇",
     "context": "指標與陣列"},
    {"url": "https://a.test/stack", "title": "函式呼叫篇",
     "context": "stack frame 與呼叫慣例"},
    {"url": "https://a.test/float", "title": "浮點數篇", "context": ""},
]


def test_chapter_query_joins_titles_and_summaries_of_included_sections():
    outline = cn.apply_section_exclusions(OUTLINE, ["s004"])

    query = cn.chapter_query(outline["chapters"][1])

    assert query == "堆疊操作 c2 堆疊操作 s2"
    assert "回傳值" in cn.chapter_query(OUTLINE["chapters"][1])


def test_select_linked_pages_returns_the_candidates_the_model_picked(
    monkeypatch,
):
    calls = _fake_openai(monkeypatch, ['```json\n{"pages": [2, 1]}\n```'])

    picked = cn.select_linked_pages(
        OUTLINE["chapters"][1], CANDIDATES, api_key="k", model="m",
        content_hint="組合語言課",
    )

    assert [page["url"] for page in picked] == [
        "https://a.test/stack", "https://a.test/pointer",
    ]
    assert len(calls) == 1
    assert calls[0]["model"] == "m"
    assert "stream" not in calls[0]
    user = calls[0]["messages"][1]["content"]
    assert "【內容描述】組合語言課" in user
    assert "標題：堆疊操作" in user
    assert "堆疊操作、回傳值" in user
    assert "1. 指標篇 — 指標與陣列" in user
    assert "2. 函式呼叫篇 — stack frame 與呼叫慣例" in user
    assert "3. 浮點數篇" in user
    assert "https://" not in user


@pytest.mark.parametrize(
    "reply, expected",
    [
        ('{"pages": []}', []),
        ('{"pages": [3, 3, 9, 0, -1, "2", 1.0, true, null, 2, 1]}', [3, 2]),
        ('{"pages": "2"}', []),
        ("[2]", []),
        ("我覺得第 2 個最相關", []),
        ('{"other": [1]}', []),
    ],
)
def test_select_linked_pages_accepts_only_valid_distinct_numbers(
    monkeypatch, reply, expected
):
    _fake_openai(monkeypatch, [reply])

    picked = cn.select_linked_pages(
        OUTLINE["chapters"][1], CANDIDATES, api_key="k"
    )

    assert [CANDIDATES.index(page) + 1 for page in picked] == expected


def test_select_linked_pages_never_raises(monkeypatch):
    _fake_openai(monkeypatch, [Exception("rate limited")])
    assert cn.select_linked_pages(
        OUTLINE["chapters"][1], CANDIDATES, api_key="k"
    ) == []
    assert cn.select_linked_pages(
        OUTLINE["chapters"][1], CANDIDATES, api_key=""
    ) == []


def test_select_linked_pages_skips_the_request_when_there_is_nothing_to_pick(
    monkeypatch,
):
    calls = _fake_openai(monkeypatch, [])

    assert cn.select_linked_pages(
        OUTLINE["chapters"][1], [], api_key="k"
    ) == []
    assert cn.select_linked_pages(
        OUTLINE["chapters"][2], CANDIDATES, api_key="k"
    ) == []
    assert calls == []


def test_linked_sources_footer_lists_the_pages_used():
    pages = [
        {"url": "https://a.test/stack", "title": "函式呼叫篇 [2016]"},
        {"url": "https://a.test/x?<y>", "title": ""},
    ]

    assert cn.linked_sources_footer(pages) == (
        "\n\n> 本章延伸閱讀："
        "[函式呼叫篇 (2016)](<https://a.test/stack>)、"
        "[https://a.test/x?<y>](<https://a.test/x?%3Cy%3E>)\n"
    )
    assert cn.linked_sources_footer([]) == ""


def test_chapter_prompt_explains_linked_pages():
    assert "延伸閱讀" in cn._CHAPTER_SYSTEM_PROMPT


# --- finalize_chapter_markdown ----------------------------------------------

def _anim(anim_id, title="T"):
    body = json.dumps({"id": anim_id, "title": title, "brief": "B"},
                      ensure_ascii=False)
    return f"```concept-anim\n{body}\n```"


def _anim_ids(markdown):
    return [
        json.loads(block.split("\n")[1])["id"]
        for block in markdown.split("```concept-anim")[1:]
    ]


def test_finalize_prefixes_concept_anim_ids_with_chapter_id():
    md = f"## 標題\n\n內文\n\n{_anim('tcp-handshake')}\n\n結尾"

    out = cn.finalize_chapter_markdown(md, "c02")

    assert _anim_ids(out) == ["c02-tcp-handshake"]
    assert '"title": "T"' in out
    assert out.startswith("## 標題\n\n內文")
    assert out.endswith("結尾\n")


def test_finalize_dedupes_and_truncates_anim_ids():
    long_id = "a" * 32
    md = "\n\n".join([_anim("x"), _anim("x"), _anim(long_id), _anim(long_id)])

    ids = _anim_ids(cn.finalize_chapter_markdown(md, "c07"))

    assert ids[0] == "c07-x"
    assert ids[1] == "c07-x-2"
    assert ids[2] == "c07-" + "a" * 28
    assert ids[3] == "c07-" + "a" * 26 + "-2"
    assert all(len(i) <= 32 for i in ids)
    assert len(set(ids)) == 4


def test_finalize_sanitises_invalid_anim_ids():
    md = "\n\n".join([_anim("TCP_Hand shake!"), _anim("中文")])

    ids = _anim_ids(cn.finalize_chapter_markdown(md, "c01"))

    assert ids == ["c01-tcp-hand-shake", "c01-anim"]


def test_finalize_leaves_malformed_anim_blocks_untouched():
    md = "```concept-anim\n{not json}\n```"
    assert cn.finalize_chapter_markdown(md, "c01") == md + "\n"


def test_finalize_closes_unterminated_code_fence():
    md = "## 標題\n\n```mermaid\ngraph LR\n  A --> B"

    out = cn.finalize_chapter_markdown(md, "c01")

    assert out == md + "\n```\n"


# --- assemble_notes ---------------------------------------------------------

def test_assemble_notes_follows_outline_order_and_skips_missing():
    chapters = {"c02": "## 堆疊操作\n\n第二章\n", "c01": "## 課程導論\n\n第一章\n"}

    out = cn.assemble_notes(OUTLINE, chapters, [])

    assert out == (
        "# 堆疊入門\n\n總覽\n\n## 課程導論\n\n第一章\n\n## 堆疊操作\n\n第二章\n"
    )


def test_assemble_notes_lists_successfully_fetched_sources():
    sources = [
        {"url": "https://a.test/x", "title": "A [文件]", "ok": True},
        {"url": "https://b.test/y", "title": "", "ok": True},
        {"url": "https://bad.test", "title": "壞掉", "ok": False},
    ]

    out = cn.assemble_notes(OUTLINE, {"c01": "## 課程導論\n\n內文"}, sources)

    assert out.endswith(
        "## 參考資料\n\n"
        "- [A (文件)](<https://a.test/x>)\n"
        "- [https://b.test/y](<https://b.test/y>)\n"
    )
    assert "bad.test" not in out


def test_assemble_notes_without_overview_or_chapters():
    outline = {"title": "只有標題", "overview": "", "chapters": []}
    assert cn.assemble_notes(outline, {}, []) == "# 只有標題\n"
