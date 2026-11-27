import importlib
import inspect
import json
import sys
import types
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _load_subtitle_api_module():
    sys.modules.pop("backend.services.subtitle_api", None)
    stub = types.ModuleType("backend.services.retranscribe_service")

    class _DummyRetranscribeService:
        def get_retranscribe_task(self, task_id):
            return None

        def get_all_retranscribe_tasks(self):
            return {}

    setattr(stub, "get_retranscribe_service", lambda: _DummyRetranscribeService())
    sys.modules["backend.services.retranscribe_service"] = stub
    return importlib.import_module("backend.services.subtitle_api")


def _make_task(tmp_path, task_id="task-1"):
    json_path = tmp_path / f"{task_id}.json"
    json_path.write_text(
        json.dumps(
            {
                "segments": [{"start": 0.0, "end": 1.0, "text": "測試字幕"}],
                "language": "zh",
                "model_name": "qwen3-asr-1.7b",
                "duration": 1.0,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return SimpleNamespace(
        status="completed",
        result={"files": {"json": str(json_path)}, "output_dir": str(tmp_path)},
        start_time=1.0,
        end_time=2.0,
    )


def _client(subtitle_api, tasks):
    subtitle_api.set_tasks_storage(tasks)
    app = FastAPI()
    app.include_router(subtitle_api.router)
    return TestClient(app)


def test_resolve_task_output_dir_uses_first_result_file(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    task = _make_task(tmp_path)
    assert subtitle_api._resolve_task_output_dir(task) == str(tmp_path)


def test_resolve_task_output_dir_falls_back_to_output_dir(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    task = SimpleNamespace(result={"files": {}, "output_dir": str(tmp_path)})
    assert subtitle_api._resolve_task_output_dir(task) == str(tmp_path)


def test_resolve_task_output_dir_returns_none_without_result():
    subtitle_api = _load_subtitle_api_module()
    assert subtitle_api._resolve_task_output_dir(SimpleNamespace(result=None)) is None


def test_summarize_endpoint_is_sync():
    subtitle_api = _load_subtitle_api_module()
    assert not inspect.iscoroutinefunction(
        subtitle_api.summarize_subtitles_endpoint
    )


def test_get_notes_still_returns_saved_summary(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    (tmp_path / "task-1_notes.json").write_text(
        json.dumps({"summary": "S", "chapters": []}), encoding="utf-8"
    )
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})
    res = client.get("/api/subtitles/task-1/notes")
    assert res.status_code == 200
    assert res.json()["summary"] == "S"


def _section(section_id, title, start, end, importance="core"):
    return {"id": section_id, "title": title, "start": start, "end": end,
            "summary": f"{title}的重點", "importance": importance}


OUTLINE = {
    "title": "堆疊入門",
    "overview": "總覽",
    "grouped": True,
    "chapters": [
        {"id": "c01", "title": "開場", "summary": "s1",
         "importance": "optional", "kind": "topic",
         "sections": [_section("s001", "開場白", 0.0, 0.5, "optional")]},
        {"id": "c02", "title": "堆疊操作", "summary": "s2",
         "importance": "core", "kind": "topic",
         "sections": [_section("s002", "push", 0.5, 0.8),
                      _section("s003", "pop", 0.8, 1.0)]},
    ],
}
FLAT_OUTLINE = {
    "title": "舊格式規劃",
    "overview": "舊總覽",
    "chapters": [
        {"id": "c01", "title": "開場", "start": 0.0, "end": 0.5,
         "summary": "s1", "importance": "optional"},
        {"id": "c02", "title": "堆疊操作", "start": 0.5, "end": 1.0,
         "summary": "s2", "importance": "core"},
    ],
}
NOTES_URL = "/api/subtitles/task-1/study-notes"
EMPTY_REFERENCES = {
    "text": "", "sources": [], "used_chars": 0, "truncated": False,
}


def _write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _events(text):
    return [
        json.loads(line[len("data: "):])
        for line in text.splitlines()
        if line.startswith("data: ")
    ]


def _fake_chapter_gen(pieces, error=None, seen=None, during=None):
    def _gen(segments, **kwargs):
        if seen is not None:
            seen.update(kwargs)
            seen["segments"] = segments
        for p in pieces:
            yield p
        if during is not None:
            during()
        if error is not None:
            raise error
    return _gen


def test_study_notes_endpoints_are_sync():
    subtitle_api = _load_subtitle_api_module()
    for name in (
        "plan_study_notes_outline", "discard_study_notes_outline",
        "save_study_notes_references", "start_study_notes",
        "generate_chapter_note_endpoint", "get_study_notes",
    ):
        assert not inspect.iscoroutinefunction(getattr(subtitle_api, name)), name


def test_get_study_notes_is_empty_before_anything_is_generated(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    res = client.get(NOTES_URL)

    assert res.status_code == 200
    assert res.json() == {
        "markdown": "", "outline": None, "draft_outline": None,
        "chapters": [], "references": EMPTY_REFERENCES,
    }


def test_get_study_notes_404_for_unknown_task_or_missing_output_dir(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    client = _client(
        subtitle_api,
        {"task-1": SimpleNamespace(status="processing", result=None)},
    )
    assert client.get("/api/subtitles/nope/study-notes").status_code == 404
    res = client.get(NOTES_URL)
    assert res.status_code == 404
    assert res.json()["detail"] == "找不到輸出目錄"


def test_get_study_notes_returns_legacy_single_file_note(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    (tmp_path / "task-1_study_notes.md").write_text("# 舊筆記", encoding="utf-8")
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    body = client.get(NOTES_URL).json()

    assert body["markdown"] == "# 舊筆記"
    assert body["outline"] is None
    assert body["chapters"] == []


def test_get_study_notes_assembles_generated_chapters(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    _write_json(tmp_path / "task-1_notes_outline.json", OUTLINE)
    _write_json(tmp_path / "task-1_notes_outline_draft.json", dict(
        OUTLINE, title="新規劃", overview="", chapters=OUTLINE["chapters"][:1]
    ))
    _write_json(tmp_path / "task-1_notes_refs.json", {
        "text": "貼上的文字",
        "sources": [{"url": "https://a.test", "title": "A", "text": "A" * 30,
                     "ok": True, "error": ""}],
    })
    (tmp_path / "task-1_notes_ch_c02.md").write_text(
        "## 堆疊操作\n\n第二章\n", encoding="utf-8"
    )
    (tmp_path / "task-1_study_notes.md").write_text("# 舊筆記", encoding="utf-8")
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    body = client.get(NOTES_URL).json()

    assert body["outline"] == OUTLINE
    assert body["draft_outline"]["title"] == "新規劃"
    assert [(c["id"], c["markdown"]) for c in body["chapters"]] == [
        ("c01", None), ("c02", "## 堆疊操作\n\n第二章\n"),
    ]
    assert body["chapters"][0]["importance"] == "optional"
    assert [s["id"] for s in body["chapters"][1]["sections"]] == [
        "s002", "s003",
    ]
    assert body["markdown"] == (
        "# 堆疊入門\n\n總覽\n\n## 堆疊操作\n\n第二章\n\n"
        "## 參考資料\n\n- [A](<https://a.test>)\n"
    )
    assert body["references"] == {
        "text": "貼上的文字",
        "sources": [{"url": "https://a.test", "title": "A", "chars": 30,
                     "ok": True, "error": "", "links": 0}],
        "used_chars": 35,
        "truncated": False,
    }


def test_get_study_notes_has_no_markdown_until_a_chapter_exists(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    _write_json(tmp_path / "task-1_notes_outline.json", OUTLINE)
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    body = client.get(NOTES_URL).json()

    assert body["markdown"] == ""
    assert [c["markdown"] for c in body["chapters"]] == [None, None]


def test_get_study_notes_upgrades_outlines_saved_in_the_flat_format(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    _write_json(tmp_path / "task-1_notes_outline.json", FLAT_OUTLINE)
    _write_json(tmp_path / "task-1_notes_outline_draft.json", FLAT_OUTLINE)
    (tmp_path / "task-1_notes_ch_c02.md").write_text(
        "## 堆疊操作\n\n舊章節\n", encoding="utf-8"
    )
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    body = client.get(NOTES_URL).json()

    for key in ("outline", "draft_outline"):
        assert body[key]["grouped"] is False
        assert [(c["id"], c["kind"], [s["id"] for s in c["sections"]])
                for c in body[key]["chapters"]] == [
            ("c01", "topic", ["s001"]), ("c02", "topic", ["s002"]),
        ]
    assert body["outline"]["chapters"][1]["sections"][0] == {
        "id": "s002", "title": "堆疊操作", "start": 0.5, "end": 1.0,
        "summary": "s2", "importance": "core",
    }
    assert [(c["id"], c["markdown"]) for c in body["chapters"]] == [
        ("c01", None), ("c02", "## 堆疊操作\n\n舊章節\n"),
    ]
    assert body["markdown"].startswith("# 舊格式規劃\n\n舊總覽\n\n## 堆疊操作")


def test_get_study_notes_ignores_corrupt_outline_file(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    (tmp_path / "task-1_notes_outline.json").write_text("{oops", encoding="utf-8")
    _write_json(tmp_path / "task-1_notes_outline_draft.json", {"chapters": "x"})
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    body = client.get(NOTES_URL).json()

    assert body["outline"] is None
    assert body["draft_outline"] is None


def test_plan_outline_saves_draft_only(tmp_path, monkeypatch):
    from backend.shared import chapter_notes

    subtitle_api = _load_subtitle_api_module()
    seen = {}

    def fake(segments, **kwargs):
        seen.update(kwargs)
        seen["segments"] = segments
        return OUTLINE

    monkeypatch.setattr(chapter_notes, "plan_note_outline", fake)
    old_outline = dict(OUTLINE, title="舊", overview="")
    _write_json(tmp_path / "task-1_notes_outline.json", old_outline)
    chapter = tmp_path / "task-1_notes_ch_c01.md"
    chapter.write_text("## 舊章節\n", encoding="utf-8")
    anim = tmp_path / "task-1_anim_c01-x.svg"
    anim.write_text("<svg/>", encoding="utf-8")
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    res = client.post(
        f"{NOTES_URL}/outline",
        json={"api_key": "k", "model": "m", "content_hint": "組語課"},
    )

    assert res.status_code == 200
    assert res.json() == {"outline": OUTLINE}
    assert seen["model"] == "m"
    assert seen["content_hint"] == "組語課"
    assert seen["segments"][0]["text"] == "測試字幕"
    draft = json.loads(
        (tmp_path / "task-1_notes_outline_draft.json").read_text(encoding="utf-8")
    )
    assert draft == OUTLINE
    saved = json.loads(
        (tmp_path / "task-1_notes_outline.json").read_text(encoding="utf-8")
    )
    assert saved == old_outline
    assert chapter.exists() and anim.exists()


def test_plan_outline_runtime_error_is_502_and_keeps_existing_draft(
    tmp_path, monkeypatch
):
    from backend.shared import chapter_notes

    subtitle_api = _load_subtitle_api_module()

    def boom(segments, **kwargs):
        raise RuntimeError("章節規劃格式錯誤，請重試")

    monkeypatch.setattr(chapter_notes, "plan_note_outline", boom)
    draft = tmp_path / "task-1_notes_outline_draft.json"
    _write_json(draft, OUTLINE)
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    res = client.post(f"{NOTES_URL}/outline", json={"api_key": "k"})

    assert res.status_code == 502
    assert res.json()["detail"] == "章節規劃格式錯誤，請重試"
    assert json.loads(draft.read_text(encoding="utf-8")) == OUTLINE


def test_plan_outline_reports_save_failure(tmp_path, monkeypatch):
    from backend.shared import chapter_notes

    subtitle_api = _load_subtitle_api_module()
    monkeypatch.setattr(
        chapter_notes, "plan_note_outline", lambda segments, **kw: OUTLINE
    )

    def broken(path, text):
        raise OSError("disk full")

    monkeypatch.setattr(subtitle_api, "_write_text_atomic", broken)
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    res = client.post(f"{NOTES_URL}/outline", json={"api_key": "k"})

    assert res.status_code == 500
    assert res.json()["detail"] == "無法儲存章節規劃"


def test_discard_outline_removes_only_the_draft(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    draft = tmp_path / "task-1_notes_outline_draft.json"
    _write_json(draft, OUTLINE)
    outline = tmp_path / "task-1_notes_outline.json"
    _write_json(outline, OUTLINE)
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    assert client.delete(f"{NOTES_URL}/outline").status_code == 200
    assert not draft.exists()
    assert outline.exists()
    assert client.delete(f"{NOTES_URL}/outline").status_code == 200
    assert client.delete(
        "/api/subtitles/nope/study-notes/outline"
    ).status_code == 404


def test_save_references_fetches_new_urls_and_reuses_cached(
    tmp_path, monkeypatch
):
    from backend.shared import note_references

    subtitle_api = _load_subtitle_api_module()
    fetched = []

    def fake_fetch(url):
        fetched.append(url)
        return {"url": url, "title": "新頁面", "text": "N" * 60, "ok": True,
                "error": "", "links": [{"url": "https://new.test/sub",
                                        "title": "子頁", "context": ""}]}

    monkeypatch.setattr(note_references, "fetch_reference_url", fake_fetch)
    _write_json(tmp_path / "task-1_notes_refs.json", {
        "text": "舊文字",
        "sources": [
            {"url": "https://a.test", "title": "A", "text": "A" * 30,
             "ok": True, "error": "", "links": []},
            {"url": "https://gone.test", "title": "G", "text": "G", "ok": True,
             "error": "", "links": []},
        ],
    })
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    res = client.put(
        f"{NOTES_URL}/references",
        json={"text": "新文字", "urls": ["https://a.test", "https://new.test"]},
    )

    assert res.status_code == 200
    assert fetched == ["https://new.test"]
    assert res.json() == {
        "text": "新文字",
        "sources": [
            {"url": "https://a.test", "title": "A", "chars": 30, "ok": True,
             "error": "", "links": 0},
            {"url": "https://new.test", "title": "新頁面", "chars": 60,
             "ok": True, "error": "", "links": 1},
        ],
        "used_chars": 93,
        "truncated": False,
    }
    stored = json.loads(
        (tmp_path / "task-1_notes_refs.json").read_text(encoding="utf-8")
    )
    assert stored["text"] == "新文字"
    assert [s["url"] for s in stored["sources"]] == [
        "https://a.test", "https://new.test",
    ]
    assert stored["sources"][1]["text"] == "N" * 60
    assert client.get(NOTES_URL).json()["references"] == res.json()


def test_save_references_rejects_too_many_urls(tmp_path, monkeypatch):
    from backend.shared import note_references

    subtitle_api = _load_subtitle_api_module()

    def must_not_fetch(url):
        raise AssertionError("must not fetch")

    monkeypatch.setattr(note_references, "fetch_reference_url", must_not_fetch)
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    res = client.put(
        f"{NOTES_URL}/references",
        json={"text": "", "urls": [f"https://x{i}.test" for i in range(6)]},
    )

    assert res.status_code == 400
    assert res.json()["detail"] == "參考網址最多 5 個"
    assert not (tmp_path / "task-1_notes_refs.json").exists()


def test_start_requires_a_draft(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    _write_json(tmp_path / "task-1_notes_outline.json", OUTLINE)
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    res = client.post(f"{NOTES_URL}/start")

    assert res.status_code == 404
    assert res.json()["detail"] == "沒有待採用的章節規劃"
    assert (tmp_path / "task-1_notes_outline.json").exists()


def test_start_promotes_draft_and_clears_previous_notes(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    new_outline = dict(
        OUTLINE, title="新規劃", overview="新總覽",
        chapters=OUTLINE["chapters"][:1],
    )
    _write_json(tmp_path / "task-1_notes_outline_draft.json", new_outline)
    _write_json(tmp_path / "task-1_notes_outline.json", OUTLINE)
    refs = {"text": "保留的參考", "sources": []}
    _write_json(tmp_path / "task-1_notes_refs.json", refs)
    stale = [
        tmp_path / "task-1_notes_ch_c01.md",
        tmp_path / "task-1_notes_ch_c02.md",
        tmp_path / "task-1_anim_c01-x.svg",
        tmp_path / "task-1_anim_legacy.svg",
        tmp_path / "task-1_study_notes.md",
    ]
    for path in stale:
        path.write_text("old", encoding="utf-8")
    kept = [
        tmp_path / "task-2_notes_ch_c01.md",
        tmp_path / "task-2_anim_x.svg",
        tmp_path / "task-1_notes.json",
        tmp_path / "task-1_mindmap.json",
    ]
    for path in kept:
        path.write_text("{}", encoding="utf-8")
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    res = client.post(f"{NOTES_URL}/start")

    assert res.status_code == 200
    body = res.json()
    assert body["outline"] == new_outline
    assert body["draft_outline"] is None
    assert body["markdown"] == ""
    assert [(c["id"], c["markdown"]) for c in body["chapters"]] == [("c01", None)]
    assert body["references"]["text"] == "保留的參考"
    assert not any(path.exists() for path in stale)
    assert all(path.exists() for path in kept)
    assert not (tmp_path / "task-1_notes_outline_draft.json").exists()
    saved = json.loads(
        (tmp_path / "task-1_notes_outline.json").read_text(encoding="utf-8")
    )
    assert saved == new_outline


def test_start_records_sections_the_user_excluded(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    _write_json(tmp_path / "task-1_notes_outline_draft.json", OUTLINE)
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    res = client.post(
        f"{NOTES_URL}/start", json={"excluded_sections": ["s003", "s999"]}
    )

    assert res.status_code == 200
    saved = json.loads(
        (tmp_path / "task-1_notes_outline.json").read_text(encoding="utf-8")
    )
    flags = [
        [s.get("excluded", False) for s in c["sections"]]
        for c in saved["chapters"]
    ]
    assert flags == [[False], [False, True]]
    assert res.json()["outline"] == saved
    assert res.json()["chapters"][1]["sections"][1]["excluded"] is True


def test_start_upgrades_a_flat_draft_before_saving_it(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    _write_json(tmp_path / "task-1_notes_outline_draft.json", FLAT_OUTLINE)
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    res = client.post(f"{NOTES_URL}/start")

    assert res.status_code == 200
    saved = json.loads(
        (tmp_path / "task-1_notes_outline.json").read_text(encoding="utf-8")
    )
    assert saved["grouped"] is False
    assert [c["sections"][0]["id"] for c in saved["chapters"]] == [
        "s001", "s002",
    ]


def test_start_rejects_malformed_exclusions(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    draft = tmp_path / "task-1_notes_outline_draft.json"
    _write_json(draft, OUTLINE)
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    res = client.post(f"{NOTES_URL}/start", json={"excluded_sections": "s003"})

    assert res.status_code == 422
    assert draft.exists()
    assert not (tmp_path / "task-1_notes_outline.json").exists()


def test_start_keeps_draft_when_old_chapters_cannot_be_cleared(
    tmp_path, monkeypatch
):
    subtitle_api = _load_subtitle_api_module()
    draft = tmp_path / "task-1_notes_outline_draft.json"
    _write_json(draft, OUTLINE)
    (tmp_path / "task-1_notes_ch_c01.md").write_text("old", encoding="utf-8")

    def locked(path):
        raise PermissionError("file in use")

    monkeypatch.setattr(subtitle_api, "_remove_if_exists", locked)
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    res = client.post(f"{NOTES_URL}/start")

    assert res.status_code == 500
    assert res.json()["detail"] == "無法清除舊的章節筆記"
    assert draft.exists()


def test_generate_chapter_streams_and_saves_finalized_markdown(
    tmp_path, monkeypatch
):
    from backend.shared import chapter_notes

    subtitle_api = _load_subtitle_api_module()
    seen = {}
    anim = '```concept-anim\n{"id": "push", "title": "T", "brief": "B"}\n```'
    monkeypatch.setattr(
        chapter_notes,
        "generate_chapter_note",
        _fake_chapter_gen(["## 堆疊操作\n\n", "內文\n\n", anim], seen=seen),
    )
    _write_json(tmp_path / "task-1_notes_outline.json", OUTLINE)
    _write_json(tmp_path / "task-1_notes_refs.json", {
        "text": "講義重點", "sources": [],
    })
    own_anim = tmp_path / "task-1_anim_c02-old.svg"
    other_chapter_anim = tmp_path / "task-1_anim_c01-keep.svg"
    other_task_anim = tmp_path / "task-2_anim_c02-keep.svg"
    for path in (own_anim, other_chapter_anim, other_task_anim):
        path.write_text("<svg/>", encoding="utf-8")
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    res = client.post(
        f"{NOTES_URL}/chapters/c02",
        json={"api_key": "k", "model": "m", "content_hint": "組語課"},
    )

    assert res.status_code == 200
    events = _events(res.text)
    assert [e["type"] for e in events] == ["delta", "delta", "delta", "done"]
    assert events[0]["text"] == "## 堆疊操作\n\n"
    saved = (tmp_path / "task-1_notes_ch_c02.md").read_text(encoding="utf-8")
    assert events[-1]["markdown"] == saved
    assert saved.startswith("## 堆疊操作\n\n內文\n\n```concept-anim\n")
    assert '"id": "c02-push"' in saved
    assert seen["outline"] == OUTLINE
    assert seen["chapter_id"] == "c02"
    assert seen["model"] == "m"
    assert seen["content_hint"] == "組語課"
    assert seen["segments"][0]["text"] == "測試字幕"
    assert seen["reference_block"] == (
        '<reference source="使用者提供的文字">\n講義重點\n</reference>'
    )
    assert not own_anim.exists()
    assert other_chapter_anim.exists()
    assert other_task_anim.exists()
    assert not list(tmp_path.glob("*.tmp"))


INDEX_SOURCE = {
    "url": "https://a.test/index", "title": "講座目錄", "text": "目錄內容" * 10,
    "ok": True, "error": "",
    "links": [
        {"url": "https://a.test/stack", "title": "堆疊篇", "context": "push pop"},
        {"url": "https://a.test/float", "title": "浮點數篇", "context": ""},
    ],
}


def _linked_setup(tmp_path, monkeypatch, *, picked, pages, seen):
    """Chapter generation with stubbed page picking and page fetching."""
    from backend.shared import chapter_notes, note_references

    subtitle_api = _load_subtitle_api_module()
    monkeypatch.setattr(
        chapter_notes, "generate_chapter_note",
        _fake_chapter_gen(["## 堆疊操作\n\n", "內文"], seen=seen),
    )

    def fake_pick(chapter, candidates, **kwargs):
        seen["pick"] = {"chapter": chapter["id"], "candidates": candidates,
                        **kwargs}
        if isinstance(picked, Exception):
            raise picked
        return [c for c in candidates if c["url"] in picked]

    def fake_fetch(url, **kwargs):
        seen.setdefault("fetched", []).append((url, kwargs))
        return dict(pages[url])

    monkeypatch.setattr(chapter_notes, "select_linked_pages", fake_pick)
    monkeypatch.setattr(note_references, "fetch_reference_url", fake_fetch)
    _write_json(tmp_path / "task-1_notes_outline.json", OUTLINE)
    _write_json(tmp_path / "task-1_notes_refs.json", {
        "text": "講義重點", "sources": [INDEX_SOURCE],
    })
    return _client(subtitle_api, {"task-1": _make_task(tmp_path)})


STACK_PAGE = {
    "url": "https://a.test/stack", "title": "堆疊篇", "ok": True, "error": "",
    "links": [], "text": "\n".join(["無關的開場。" * 60, "push 與 pop 的細節。" * 20]),
}


def test_generate_chapter_reads_the_linked_pages_picked_for_it(
    tmp_path, monkeypatch
):
    seen = {}
    client = _linked_setup(
        tmp_path, monkeypatch, picked=["https://a.test/stack"],
        pages={"https://a.test/stack": STACK_PAGE}, seen=seen,
    )

    res = client.post(
        f"{NOTES_URL}/chapters/c02", json={"api_key": "k", "model": "m"}
    )

    events = _events(res.text)
    assert events[-1]["type"] == "done"
    assert seen["pick"]["chapter"] == "c02"
    assert seen["pick"]["model"] == "m"
    assert [c["url"] for c in seen["pick"]["candidates"]] == [
        "https://a.test/stack", "https://a.test/float",
    ]
    assert seen["fetched"] == [("https://a.test/stack", {"max_chars": None})]
    block = seen["reference_block"]
    assert '<reference source="使用者提供的文字">\n講義重點' in block
    assert '<reference source="講座目錄 (https://a.test/index)">' in block
    assert (
        '<reference source="延伸閱讀：堆疊篇 (https://a.test/stack)">' in block
    )
    assert "push 與 pop 的細節" in block
    footer = "\n\n> 本章延伸閱讀：[堆疊篇](<https://a.test/stack>)\n"
    saved = (tmp_path / "task-1_notes_ch_c02.md").read_text(encoding="utf-8")
    assert saved.endswith("內文" + footer)
    assert events[-1]["markdown"] == saved
    assert events[-2] == {"type": "delta", "text": footer}
    cache = json.loads(
        (tmp_path / "task-1_notes_linked.json").read_text(encoding="utf-8")
    )
    assert cache["https://a.test/stack"]["text"] == STACK_PAGE["text"]


def test_generate_chapter_reuses_cached_linked_pages(tmp_path, monkeypatch):
    seen = {}
    client = _linked_setup(
        tmp_path, monkeypatch, picked=["https://a.test/stack"],
        pages={}, seen=seen,
    )
    _write_json(tmp_path / "task-1_notes_linked.json", {
        "https://a.test/stack": STACK_PAGE,
    })

    events = _events(
        client.post(f"{NOTES_URL}/chapters/c02", json={"api_key": "k"}).text
    )

    assert events[-1]["type"] == "done"
    assert "fetched" not in seen
    assert "延伸閱讀：堆疊篇" in seen["reference_block"]


def test_generate_chapter_survives_linked_page_failures(tmp_path, monkeypatch):
    seen = {}
    failed = {"url": "https://a.test/stack", "title": "", "text": "",
              "ok": False, "error": "連線逾時", "links": []}
    client = _linked_setup(
        tmp_path, monkeypatch, picked=["https://a.test/stack"],
        pages={"https://a.test/stack": failed}, seen=seen,
    )

    events = _events(
        client.post(f"{NOTES_URL}/chapters/c02", json={"api_key": "k"}).text
    )

    assert events[-1]["type"] == "done"
    assert "延伸閱讀" not in seen["reference_block"]
    assert "本章延伸閱讀" not in events[-1]["markdown"]
    assert '<reference source="講座目錄 (https://a.test/index)">' in (
        seen["reference_block"]
    )
    assert not (tmp_path / "task-1_notes_linked.json").exists()


def test_generate_chapter_survives_a_crashing_page_picker(tmp_path, monkeypatch):
    seen = {}
    client = _linked_setup(
        tmp_path, monkeypatch, picked=ValueError("unexpected"),
        pages={}, seen=seen,
    )

    events = _events(
        client.post(f"{NOTES_URL}/chapters/c02", json={"api_key": "k"}).text
    )

    assert events[-1]["type"] == "done"
    assert "fetched" not in seen
    assert "本章延伸閱讀" not in events[-1]["markdown"]


def test_generate_chapter_without_links_skips_the_page_picker(
    tmp_path, monkeypatch
):
    from backend.shared import chapter_notes

    subtitle_api = _load_subtitle_api_module()
    seen = {}
    monkeypatch.setattr(
        chapter_notes, "generate_chapter_note",
        _fake_chapter_gen(["## 堆疊操作\n\n內文"], seen=seen),
    )

    def must_not_pick(*args, **kwargs):
        raise AssertionError("no candidates, nothing to pick")

    monkeypatch.setattr(chapter_notes, "select_linked_pages", must_not_pick)
    _write_json(tmp_path / "task-1_notes_outline.json", OUTLINE)
    _write_json(tmp_path / "task-1_notes_refs.json", {
        "text": "講" * 15_000, "sources": [],
    })
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    events = _events(
        client.post(f"{NOTES_URL}/chapters/c02", json={"api_key": "k"}).text
    )

    assert events[-1]["type"] == "done"
    assert seen["reference_block"].count("講") == 15_000


def test_generate_chapter_trims_direct_references_when_linked_pages_are_used(
    tmp_path, monkeypatch
):
    seen = {}
    client = _linked_setup(
        tmp_path, monkeypatch, picked=["https://a.test/stack"],
        pages={"https://a.test/stack": dict(STACK_PAGE, text="頁" * 30_000)},
        seen=seen,
    )
    _write_json(tmp_path / "task-1_notes_refs.json", {
        "text": "講" * 15_000, "sources": [INDEX_SOURCE],
    })

    client.post(f"{NOTES_URL}/chapters/c02", json={"api_key": "k"})

    block = seen["reference_block"]
    assert block.count("講") == 12_000
    assert block.count("頁") == 12_000


def test_start_clears_the_linked_page_cache(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    _write_json(tmp_path / "task-1_notes_outline_draft.json", OUTLINE)
    cache = tmp_path / "task-1_notes_linked.json"
    _write_json(cache, {"https://a.test/stack": STACK_PAGE})
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    assert client.post(f"{NOTES_URL}/start").status_code == 200
    assert not cache.exists()


def test_generate_chapter_error_keeps_previous_chapter(tmp_path, monkeypatch):
    from backend.shared import chapter_notes

    subtitle_api = _load_subtitle_api_module()
    monkeypatch.setattr(
        chapter_notes,
        "generate_chapter_note",
        _fake_chapter_gen(["## 半"], error=RuntimeError("rate limited")),
    )
    _write_json(tmp_path / "task-1_notes_outline.json", OUTLINE)
    chapter = tmp_path / "task-1_notes_ch_c02.md"
    chapter.write_text("## 舊章節\n", encoding="utf-8")
    anim = tmp_path / "task-1_anim_c02-old.svg"
    anim.write_text("<svg/>", encoding="utf-8")
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    events = _events(
        client.post(f"{NOTES_URL}/chapters/c02", json={"api_key": "k"}).text
    )

    assert [e["type"] for e in events] == ["delta", "error"]
    assert events[-1]["message"] == "rate limited"
    assert chapter.read_text(encoding="utf-8") == "## 舊章節\n"
    assert anim.exists()


def test_generate_chapter_reports_save_failure_instead_of_done(
    tmp_path, monkeypatch
):
    from backend.shared import chapter_notes

    subtitle_api = _load_subtitle_api_module()
    monkeypatch.setattr(
        chapter_notes, "generate_chapter_note", _fake_chapter_gen(["## 標題\n\n內文"])
    )

    def broken(path, text):
        raise OSError("disk full")

    monkeypatch.setattr(subtitle_api, "_write_text_atomic", broken)
    _write_json(tmp_path / "task-1_notes_outline.json", OUTLINE)
    anim = tmp_path / "task-1_anim_c02-old.svg"
    anim.write_text("<svg/>", encoding="utf-8")
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    events = _events(
        client.post(f"{NOTES_URL}/chapters/c02", json={"api_key": "k"}).text
    )

    assert [e["type"] for e in events] == ["delta", "error"]
    assert events[-1]["message"] == "無法儲存章節筆記"
    assert anim.exists()


def test_generate_chapter_is_discarded_when_outline_changed_meanwhile(
    tmp_path, monkeypatch
):
    from backend.shared import chapter_notes

    subtitle_api = _load_subtitle_api_module()
    outline_path = tmp_path / "task-1_notes_outline.json"
    _write_json(outline_path, OUTLINE)

    def replace_outline():
        _write_json(outline_path, dict(OUTLINE, title="換了一份規劃"))

    monkeypatch.setattr(
        chapter_notes,
        "generate_chapter_note",
        _fake_chapter_gen(["## 標題\n\n內文"], during=replace_outline),
    )
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    events = _events(
        client.post(f"{NOTES_URL}/chapters/c02", json={"api_key": "k"}).text
    )

    assert [e["type"] for e in events] == ["delta", "error"]
    assert events[-1]["message"] == "章節規劃已變更，請重新產生"
    assert not (tmp_path / "task-1_notes_ch_c02.md").exists()


def test_abandoned_stream_closes_its_sync_generator():
    import anyio

    subtitle_api = _load_subtitle_api_module()
    state = {"closed": False}

    def source():
        try:
            while True:
                yield "data: x\n\n"
        finally:
            state["closed"] = True

    # Kept referenced on purpose: garbage collection must not be what closes it.
    chunks = source()

    async def client_disconnects_after_first_chunk():
        with anyio.CancelScope() as scope:
            async for _chunk in subtitle_api._close_when_abandoned(chunks):
                scope.cancel()

    anyio.run(client_disconnects_after_first_chunk)

    assert state["closed"] is True


def test_fully_consumed_stream_yields_every_chunk():
    import anyio

    subtitle_api = _load_subtitle_api_module()

    async def consume():
        return [
            chunk
            async for chunk in subtitle_api._close_when_abandoned(iter("abc"))
        ]

    assert anyio.run(consume) == ["a", "b", "c"]


def test_generate_chapter_validates_chapter(tmp_path, monkeypatch):
    from backend.shared import chapter_notes

    subtitle_api = _load_subtitle_api_module()

    def must_not_run(segments, **kwargs):
        raise AssertionError("must not generate")

    monkeypatch.setattr(chapter_notes, "generate_chapter_note", must_not_run)
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})
    body = {"api_key": "k"}

    for bad in ["c1", "C01", "c001", "x01", "c0a", "s001"]:
        res = client.post(f"{NOTES_URL}/chapters/{bad}", json=body)
        assert res.status_code == 400, bad
    res = client.post(f"{NOTES_URL}/chapters/c01", json=body)
    assert res.status_code == 404
    assert res.json()["detail"] == "尚未規劃章節"

    _write_json(tmp_path / "task-1_notes_outline.json", OUTLINE)
    res = client.post(f"{NOTES_URL}/chapters/c09", json=body)
    assert res.status_code == 404
    assert res.json()["detail"] == "章節不存在"
    assert client.post(
        "/api/subtitles/nope/study-notes/chapters/c01", json=body
    ).status_code == 404


def test_old_generate_notes_route_is_gone(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})
    res = client.post(
        "/api/subtitles/task-1/generate-notes", json={"api_key": "k"}
    )
    assert res.status_code in (404, 405)


def test_mindmap_endpoints_are_sync():
    subtitle_api = _load_subtitle_api_module()
    assert not inspect.iscoroutinefunction(subtitle_api.generate_mindmap_endpoint)
    assert not inspect.iscoroutinefunction(subtitle_api.get_mindmap)


def test_post_mindmap_saves_and_returns(tmp_path, monkeypatch):
    from backend.shared import llm_postprocess as lp

    subtitle_api = _load_subtitle_api_module()
    mindmap = {"root": {"title": "T", "time": 0.0, "children": []}}
    seen = {}

    def fake(segments, **kwargs):
        seen.update(kwargs)
        seen["segments"] = segments
        return mindmap

    monkeypatch.setattr(lp, "generate_mindmap", fake)
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    res = client.post(
        "/api/subtitles/task-1/mindmap", json={"api_key": "k", "model": "m"}
    )

    assert res.status_code == 200
    assert res.json() == mindmap
    assert seen["model"] == "m"
    assert seen["segments"][0]["text"] == "測試字幕"
    saved = json.loads(
        (tmp_path / "task-1_mindmap.json").read_text(encoding="utf-8")
    )
    assert saved == mindmap
    assert client.get("/api/subtitles/task-1/mindmap").json() == mindmap


def test_post_mindmap_runtime_error_is_502(tmp_path, monkeypatch):
    from backend.shared import llm_postprocess as lp

    subtitle_api = _load_subtitle_api_module()

    def boom(segments, **kwargs):
        raise RuntimeError("心智圖格式錯誤，請重試")

    monkeypatch.setattr(lp, "generate_mindmap", boom)
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})
    res = client.post("/api/subtitles/task-1/mindmap", json={"api_key": "k"})
    assert res.status_code == 502
    assert res.json()["detail"] == "心智圖格式錯誤，請重試"
    assert not (tmp_path / "task-1_mindmap.json").exists()


def test_get_mindmap_404_when_missing(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})
    assert client.get("/api/subtitles/task-1/mindmap").status_code == 404


ANIM_URL = "/api/subtitles/task-1/concept-animations"


def test_concept_animation_endpoints_are_sync():
    subtitle_api = _load_subtitle_api_module()
    assert not inspect.iscoroutinefunction(
        subtitle_api.generate_concept_animation_endpoint
    )
    assert not inspect.iscoroutinefunction(subtitle_api.get_concept_animation)


def test_concept_animation_rejects_invalid_id(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})
    for bad in ["UPPER", "has_underscore", "a" * 33, "dot.dot"]:
        assert client.get(f"{ANIM_URL}/{bad}").status_code == 400
        res = client.post(
            f"{ANIM_URL}/{bad}", json={"title": "T", "brief": "B", "api_key": "k"}
        )
        assert res.status_code == 400


def test_get_concept_animation_404_when_missing(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})
    assert client.get(f"{ANIM_URL}/tcp").status_code == 404


def test_post_concept_animation_saves_and_returns(tmp_path, monkeypatch):
    from backend.shared import llm_postprocess as lp

    subtitle_api = _load_subtitle_api_module()
    seen = {}

    def fake(**kwargs):
        seen.update(kwargs)
        return "<svg/>"

    monkeypatch.setattr(lp, "generate_concept_svg", fake)
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})

    res = client.post(
        f"{ANIM_URL}/tcp-1",
        json={"title": "TCP", "brief": "B", "api_key": "k", "model": "draw"},
    )

    assert res.status_code == 200
    assert res.json() == {"svg": "<svg/>"}
    assert seen["model"] == "draw"
    assert seen["title"] == "TCP"
    saved = tmp_path / "task-1_anim_tcp-1.svg"
    assert saved.read_text(encoding="utf-8") == "<svg/>"
    assert client.get(f"{ANIM_URL}/tcp-1").json() == {"svg": "<svg/>"}


def test_post_concept_animation_runtime_error_is_502(tmp_path, monkeypatch):
    from backend.shared import llm_postprocess as lp

    subtitle_api = _load_subtitle_api_module()

    def boom(**kwargs):
        raise RuntimeError("SVG 生成失敗，請重試")

    monkeypatch.setattr(lp, "generate_concept_svg", boom)
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})
    res = client.post(
        f"{ANIM_URL}/tcp", json={"title": "T", "brief": "B", "api_key": "k"}
    )
    assert res.status_code == 502
    assert not (tmp_path / "task-1_anim_tcp.svg").exists()


def test_post_concept_animation_validates_lengths(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    client = _client(subtitle_api, {"task-1": _make_task(tmp_path)})
    res = client.post(
        f"{ANIM_URL}/tcp",
        json={"title": "T" * 101, "brief": "B", "api_key": "k"},
    )
    assert res.status_code == 422


def test_post_concept_animation_unknown_task_404(tmp_path):
    subtitle_api = _load_subtitle_api_module()
    client = _client(subtitle_api, {})
    res = client.post(
        f"{ANIM_URL}/tcp", json={"title": "T", "brief": "B", "api_key": "k"}
    )
    assert res.status_code == 404
