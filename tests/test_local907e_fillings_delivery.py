"""LOCAL-907E — fillings reach the phone: fillings.json in the ZIP, full item fields, the
/topic-audio route, and --render-audio with sentence timing. Offline: Kokoro and the DB are mocked."""
import hashlib
import io
import json
import os
import re
import sys
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import fillings_payload as fp
import topic_library as tl
import topic_library_build as tb

TOUR = {"stops": [{"title": "A", "lat": 42.36, "lng": -71.05, "type_specialty": "fort"},
                  {"title": "B", "lat": 42.60, "lng": -71.05, "type_specialty": "beach"}],
        "tour_type": "driving tour", "language": "en"}


def seg(i, **kw):
    d = {"id": i, "region_key": "r", "theme": "history", "title": f"T{i}", "language": "en",
         "text": "", "est_minutes": 8.0, "credit_line": "CC BY-SA", "centroid_lat": 42.4,
         "centroid_lng": -71.05, "radius_km": 80, "status": "ready", "audio_path": f"r/en/s{i}.mp3",
         "sources": [{"title": "Boston", "url": "https://en.wikipedia.org/wiki/Boston"},
                     {"title": "bad", "url": "javascript:alert(1)"}, {"title": "x", "url": "ftp://x"}],
         "sentence_ends": [2.5, 6.0]}
    d.update(kw)
    return d


def items(fillings):
    return [it for leg in fillings for it in leg["items"]]


def test_build_fillings_full_fields():
    out = fp.build_fillings(TOUR, segments=[seg(1)])
    it = items(out)[0]
    assert it["language"] == "en"
    assert it["sources"] == [{"title": "Boston", "url": "https://en.wikipedia.org/wiki/Boston"}]
    assert it["source_url"] == "https://en.wikipedia.org/wiki/Boston"
    assert it["sentence_ends"] == [2.5, 6.0]
    assert it["audio_url"].endswith("/r/en/s1.mp3")


def test_build_fillings_json_columns_as_strings_and_nulls():
    out = fp.build_fillings(TOUR, segments=[seg(1, sources="[]", sentence_ends=None)])
    it = items(out)[0]
    assert it["sources"] == [] and it["source_url"] is None and it["sentence_ends"] == []


def test_item_without_audio_is_skipped_and_leg_uses_next():
    out = fp.build_fillings(TOUR, segments=[seg(1, audio_path=None), seg(2)])
    assert [i["segment_id"] for i in items(out)] == [2]
    assert fp.build_fillings(TOUR, segments=[seg(1, audio_path=None)]) == []


def _make_zip(path):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("index.html", "<html>")
        z.writestr("audio_1.mp3", b"\x00\x01" * 500)
        z.writestr("tour_content.txt", "Stop 1: A")


def _entries(path):
    with zipfile.ZipFile(path) as z:
        return {n: hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist()}


def test_zip_gets_fillings_json_and_existing_entries_are_unchanged(tmp_path):
    p = str(tmp_path / "t.zip")
    _make_zip(p)
    before = _entries(p)
    logs = []
    fillings = fp.build_fillings(TOUR, segments=[seg(1)])
    assert fp.add_fillings_to_zip(p, fillings, log=logs.append) is True
    after = _entries(p)
    assert set(after) - set(before) == {"fillings.json"}
    assert {k: v for k, v in after.items() if k != "fillings.json"} == before
    with zipfile.ZipFile(p) as z:
        assert json.loads(z.read("fillings.json"))["fillings"] == fillings
    assert any(re.match(r"\[LOCAL-907E\] fillings.json: 1 legs, 1 items", m) for m in logs)


def test_zip_without_fillings_has_no_file_and_is_untouched(tmp_path):
    p = str(tmp_path / "t.zip")
    _make_zip(p)
    raw = open(p, "rb").read()
    assert fp.add_fillings_to_zip(p, []) is False
    assert fp.add_fillings_to_zip(p, None) is False
    assert open(p, "rb").read() == raw


def test_zip_bad_path_never_raises(tmp_path):
    assert fp.add_fillings_to_zip(str(tmp_path / "nope" / "x.zip"), [{"items": []}], log=lambda m: None) is False


def test_orchestrator_writes_fillings_before_store():
    src = open(os.path.join(ROOT, "tour_orchestrator_service.py"), encoding="utf-8").read()
    i_add = src.index("add_fillings_to_zip(zip_path")
    i_store = src.index("store_result = store_audio_tour(")
    assert i_add < i_store
    assert 'ACTIVE_JOBS[job_id]["fillings"] = _f907' in src


# ── /topic-audio route ──
@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TOPIC_AUDIO_DIR", str(tmp_path / "audio"))
    d = tmp_path / "audio" / "r" / "en"
    d.mkdir(parents=True)
    (d / "s1.mp3").write_bytes(b"ID3" + bytes(range(256)) * 4)
    (tmp_path / "secret.mp3").write_bytes(b"secret")
    (tmp_path / "audio" / "r" / "en" / "note.txt").write_text("x")
    os.symlink(str(tmp_path / "secret.mp3"), str(d / "link.mp3"))
    import map_delivery_service as md
    return md.app.test_client()


def test_audio_route_serves_with_range(client):
    r = client.get("/topic-audio/r/en/s1.mp3")
    assert r.status_code == 200 and r.mimetype == "audio/mpeg" and r.data.startswith(b"ID3")
    r = client.get("/topic-audio/r/en/s1.mp3", headers={"Range": "bytes=0-9"})
    assert r.status_code == 206 and len(r.data) == 10


@pytest.mark.parametrize("path", ["../secret.mp3", "r/../../secret.mp3", "r/en/../../../secret.mp3",
                                  "%2e%2e/secret.mp3", "r/en/missing.mp3", "r/en/note.txt",
                                  "r/en/link.mp3", "r/en", "r/en/s1.mp3/x", "/etc/passwd"])
def test_audio_route_refuses_and_404s(client, path):
    assert client.get("/topic-audio/" + path, follow_redirects=True).status_code == 404


def test_resolve_refuses_absolute_and_nul(client, tmp_path):
    import map_delivery_service as md
    assert md.resolve_topic_audio("/etc/hosts") is None
    assert md.resolve_topic_audio("a\x00.mp3") is None
    assert md.resolve_topic_audio(str(tmp_path / "secret.mp3")) is None


# ── --render-audio ──
class FakeConn:
    def __init__(self):
        self.sql = []

    def cursor(self):
        outer = self

        class C:
            def execute(self, sql, params=()):
                outer.sql.append((sql, params))

            def close(self):
                pass
        return C()

    def commit(self):
        pass


def test_split_sentences():
    assert tb.split_sentences("One. Two words here! Three?\n\nFour 4. \"Five.\" Six.") == \
        ["One.", "Two words here!", "Three?", "Four 4.", "\"Five.\"", "Six."]


def test_render_audio_sets_audio_path_and_sentence_ends_same_id(tmp_path):
    store = tl.MemorySegmentStore()
    sid = store.insert_segment({"region_key": "r", "theme": "history", "title": "T", "language": "en",
                                "text": "First one. Second one.\n\nThird.", "est_minutes": 1,
                                "status": "ready", "audio_path": None})
    calls = []

    def render(text, voice):
        calls.append(text)
        return b"MP3:" + text.encode()
    durs = {b"MP3:First one.": 1.5, b"MP3:Second one.": 2.0, b"MP3:Third.": 0.75}
    done = tb.run_render_audio("r", store=store, out_dir=str(tmp_path), render_fn=render,
                               duration_fn=lambda b: durs[b], log=lambda m: None)
    assert done == [sid] and calls == ["First one.", "Second one.", "Third."]
    row = store.get_segment(sid)
    assert row["sentence_ends"] == [1.5, 3.5, 4.25] and row["id"] == sid
    assert open(tmp_path / row["audio_path"], "rb").read() == b"MP3:First one.MP3:Second one.MP3:Third."
    assert len(store._rows) == 1


def test_pg_store_updates_by_id_only_no_delete():
    conn = FakeConn()
    tl.PgSegmentStore(conn).set_audio_path(7, "r/en/segment_7.mp3", [1.0, 2.5])
    (sql, params), = conn.sql
    assert sql.startswith("UPDATE topic_segments SET audio_path") and "sentence_ends" in sql
    assert params == ("r/en/segment_7.mp3", "[1.0, 2.5]", 7)
    assert not re.search(r"\bDELETE\b", sql, re.I)
    conn2 = FakeConn()
    tl.PgSegmentStore(conn2).set_audio_path(7, "x.mp3")
    assert "sentence_ends" not in conn2.sql[0][0]


def test_migration_is_additive():
    sql = open(os.path.join(ROOT, "migrations", "local907e_topic_sentence_ends.sql"), encoding="utf-8").read()
    body = re.sub(r"--.*", "", sql)
    assert "ADD COLUMN IF NOT EXISTS sentence_ends JSONB" in body
    assert not re.search(r"\b(DROP|DELETE|TRUNCATE)\b", body, re.I)
