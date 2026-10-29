"""test_local815_repin_tours.py — LOCAL-815.

Re-pin EXISTING stored tours with today's pin_snap WITHOUT regenerating. These
tests are fully OFFLINE (an injected reference door — no network, no paid API)
and use a STORED-TOUR FIXTURE built in memory (a fake psycopg2 connection whose
one audio_tours row carries a real tour_content string and a real ZIP byte blob
with per-stop audio_N.txt files and a tour_content.txt map/index copy).

They assert, against repin_tours.process_tour, exactly what the ticket requires:

  AC1  The Coordinates: line is rewritten in ALL THREE places — the DB
       tour_content column, each ZIP per-stop audio_N.txt, and the ZIP
       tour_content.txt map/index copy — for every stop that moves > 50 m.
  AC2  NOTHING ELSE changes — narration text, stop order, titles, the other ZIP
       entries (index.html, mp3s, manifest) are byte-for-byte identical, and only
       the moved stops' coordinate numbers change.
  AC3  A stop that does NOT move more than the threshold is left untouched.
  AC4  The version is bumped via the existing mechanism — an append-only
       audio_tour_versions row (version_no = MAX+1) is INSERTed with the OLD
       content, and the live audio_tours row is UPDATEd (no DELETE anywhere).
  AC5  A backup of the OLD content and the OLD ZIP is written to disk first.
  AC6  DRY-RUN (default) writes NOTHING — no INSERT/UPDATE, no backup.

Run:
    python3 -m pytest tests/test_local815_repin_tours.py -q
"""
import io
import os
import re
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import repin_tours as rt  # noqa: E402


# ───────────────────────── fixture builder ───────────────────────────────────

# A 3-stop walking tour. Stop 1 is ~1.3 km off its real reference (will move),
# stop 2 is ~10 m off (will NOT move), stop 3 has no reference (left unsnapped).
_REF = {
    "Old North Church": (42.36637, -71.05454),   # the true pin
    "Paul Revere House": (42.36366, -71.05360),   # true pin (stop 2 is ~10 m off)
}

# Stop 2's SHIPPED pin: within 50 m of its reference (must stay put).
_STOP2_SHIPPED = (42.36360, -71.05362)   # ~8 m from the reference


def _tour_content() -> str:
    return (
        "Step-by-Step Audio Guided Tour: North End walking tour, Boston\n"
        "Tour-Category: walking\n"
        "\n"
        "Stop 1: Old North Church\n"
        "\n"
        "Address:\n"
        "\n"
        "Coordinates: 42.37800, -71.06000\n"      # ~1.3 km off -> MOVES
        "\n"
        "Type/Specialty: Historic church\n"
        "\n"
        "Orientation: Begin at the Old North Church, famous for the lanterns.\n"
        "\n"
        "Stop 2: Paul Revere House\n"
        "\n"
        "Address:\n"
        "\n"
        f"Coordinates: {_STOP2_SHIPPED[0]}, {_STOP2_SHIPPED[1]}\n"  # ~8 m -> KEPT
        "\n"
        "Type/Specialty: Historic house\n"
        "\n"
        "Orientation: Walk south to the Paul Revere House.\n"
        "\n"
        "Stop 3: A Quiet Courtyard\n"
        "\n"
        "Address:\n"
        "\n"
        "Coordinates: 42.36500, -71.05500\n"       # no reference -> UNSNAPPED
        "\n"
        "Type/Specialty: Courtyard\n"
        "\n"
        "Orientation: Pause in the quiet courtyard.\n"
    )


def _stop_txt(title: str, coord_line: str, body: str) -> str:
    return (f"{title}\n\nAddress:\n\nCoordinates: {coord_line}\n\n"
            f"Type/Specialty: x\n\nOrientation: {body}\n")


def _build_zip(content: str) -> bytes:
    """A realistic tour ZIP: index.html (no coords), audio_N.mp3 (binary),
    audio_N.txt (per-stop, with the Coordinates line the app reads), manifest.json,
    tour_content.txt (the map/index copy = the full content)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("index.html", "<html><body>openMap(1)</body></html>")
        z.writestr("audio_1.mp3", b"\x00\x01FAKE-MP3-1")
        z.writestr("audio_2.mp3", b"\x00\x01FAKE-MP3-2")
        z.writestr("audio_3.mp3", b"\x00\x01FAKE-MP3-3")
        z.writestr("audio_1.txt",
                   _stop_txt("Old North Church", "42.37800, -71.06000",
                             "Begin at the Old North Church."))
        z.writestr("audio_2.txt",
                   _stop_txt("Paul Revere House",
                             f"{_STOP2_SHIPPED[0]}, {_STOP2_SHIPPED[1]}",
                             "Walk south."))
        z.writestr("audio_3.txt",
                   _stop_txt("A Quiet Courtyard", "42.36500, -71.05500",
                             "Pause here."))
        z.writestr("manifest.json", '{"name": "North End walking tour, Boston"}')
        z.writestr("tour_content.txt", content)
    return buf.getvalue()


# ───────────────────────── fake psycopg2 connection ──────────────────────────

class _FakeCursor:
    """A minimal cursor over a single in-memory audio_tours row and an
    audio_tour_versions list. Understands exactly the SQL process_tour issues."""

    def __init__(self, store):
        self.store = store
        self._result = None

    def execute(self, sql, params=()):
        s = " ".join(sql.split()).lower()
        self.store["sql_log"].append((s, params))
        if s.startswith("select tour_name, request_string, tour_content, audio_tour"):
            r = self.store["row"]
            self._result = (r["tour_name"], r["request_string"], r["tour_content"],
                            r["audio_tour"], r["zip_filename"], r["tour_blob_uri"],
                            r["stops_count"], r["lat"], r["lng"])
        elif "from information_schema.columns" in s and "translation_stale" in s:
            self._result = ("translation_stale",)   # column exists → no ALTER
        elif s.startswith("create table if not exists audio_tour_versions"):
            self._result = None
        elif s.startswith("select coalesce(max(version_no), 0) + 1"):
            mx = max([v["version_no"] for v in self.store["versions"]], default=0)
            self._result = (mx + 1,)
        elif s.startswith("insert into audio_tour_versions"):
            (tid, vno, content, zipname, stops, lat, lng, job) = params
            self.store["versions"].append(
                {"tour_id": tid, "version_no": vno, "tour_content": content,
                 "zip_filename": zipname, "stops_count": stops, "lat": lat,
                 "lng": lng, "replaced_by_job": job})
            self._result = None
        elif s.startswith("update audio_tours set tour_content = %s, audio_tour"):
            new_content, bin_zip, tid = params
            self.store["row"]["tour_content"] = new_content
            self.store["row"]["audio_tour"] = bytes(
                bin_zip.adapted if hasattr(bin_zip, "adapted") else bin_zip)
            self._result = None
        elif s.startswith("update audio_tours set tour_content = %s where id"):
            new_content, tid = params
            self.store["row"]["tour_content"] = new_content
            self._result = None
        elif s.startswith("select tour_name, request_string, tour_content from audio_tours"):
            r = self.store["row"]
            self._result = (r["tour_name"], r["request_string"], r["tour_content"])
        else:
            self._result = None

    def fetchone(self):
        return self._result

    def close(self):
        pass


class _FakeConn:
    def __init__(self, store):
        self.store = store
        self.committed = 0
        self.rolled_back = 0

    def cursor(self):
        return _FakeCursor(self.store)

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1

    def close(self):
        pass


def _make_store():
    content = _tour_content()
    return {
        "row": {
            "id": 999, "tour_name": "North End walking tour, Boston",
            "request_string": "North End walking tour, Boston",
            "tour_content": content, "audio_tour": _build_zip(content),
            "zip_filename": "north_end_walking_tour_boston__deadbeef.zip",
            "tour_blob_uri": None, "stops_count": 3,
            "lat": 42.3660, "lng": -71.0540,
        },
        "versions": [],
        "sql_log": [],
    }


def _ref_factory(scope, scope_center):
    """Injected offline reference door: name → (lat, lng, source, name)."""
    def _ref(name):
        hit = _REF.get(name)
        if hit:
            return (hit[0], hit[1], "offline_fixture", name)
        return None
    return _ref


def _coord_lines(text):
    return rt._COORD_LINE_RE.findall(text)


def _zip_entry(zbytes, name):
    with zipfile.ZipFile(io.BytesIO(zbytes)) as z:
        return z.read(name)


def _zip_names(zbytes):
    with zipfile.ZipFile(io.BytesIO(zbytes)) as z:
        return z.namelist()


# ───────────────────────── tests ─────────────────────────────────────────────

class RepinApplyTests(unittest.TestCase):
    def setUp(self):
        self.store = _make_store()
        self.conn = _FakeConn(self.store)
        self.budget = rt.ApiBudget(0.20)
        self.tmp = tempfile.mkdtemp(prefix="repin_test_")
        self.orig_content = self.store["row"]["tour_content"]
        self.orig_zip = self.store["row"]["audio_tour"]

    def _apply(self, move_threshold=50.0):
        return rt.process_tour(
            self.conn, 999, apply_changes=True, move_threshold_m=move_threshold,
            budget=self.budget, backup_dir=self.tmp,
            reference_fn_factory=_ref_factory, log=lambda *_: None)

    def test_ac1_all_three_places_rewritten(self):
        res = self._apply()
        self.assertTrue(res.applied)
        self.assertEqual(res.moved, [0], "only stop 1 should move > 50 m")
        new_content = self.store["row"]["tour_content"]
        new_zip = self.store["row"]["audio_tour"]

        # 1) DB tour_content: stop 1 now at the reference.
        stops = rt.parse_stops(new_content)
        self.assertAlmostEqual(stops[0]["coordinate"][0], _REF["Old North Church"][0], places=4)
        self.assertAlmostEqual(stops[0]["coordinate"][1], _REF["Old North Church"][1], places=4)

        # 2) ZIP per-stop audio_1.txt rewritten to the reference.
        t1 = _zip_entry(new_zip, "audio_1.txt").decode()
        m = rt._COORD_LINE_RE.search(t1)
        self.assertAlmostEqual(float(m.group("lat")), _REF["Old North Church"][0], places=4)
        self.assertAlmostEqual(float(m.group("lng")), _REF["Old North Church"][1], places=4)

        # 3) ZIP tour_content.txt (map/index) rewritten too.
        tc = _zip_entry(new_zip, "tour_content.txt").decode()
        s2 = rt.parse_stops(tc)
        self.assertAlmostEqual(s2[0]["coordinate"][0], _REF["Old North Church"][0], places=4)

    def test_ac2_nothing_else_changed(self):
        self._apply()
        new_content = self.store["row"]["tour_content"]
        new_zip = self.store["row"]["audio_tour"]

        # Narration text + titles unchanged (only the stop-1 coordinate numbers differ).
        for kw in ("Old North Church", "Paul Revere House", "A Quiet Courtyard",
                   "famous for the lanterns", "Tour-Category: walking"):
            self.assertIn(kw, new_content)
        # Stop 2 and stop 3 coordinate lines are untouched.
        stops = rt.parse_stops(new_content)
        self.assertAlmostEqual(stops[1]["coordinate"][0], _STOP2_SHIPPED[0], places=5)
        self.assertAlmostEqual(stops[2]["coordinate"][0], 42.36500, places=5)

        # Only the Coordinates line differs between old and new content (line diff).
        old_lines = self.orig_content.splitlines()
        new_lines = new_content.splitlines()
        self.assertEqual(len(old_lines), len(new_lines))
        diffs = [i for i in range(len(old_lines)) if old_lines[i] != new_lines[i]]
        self.assertEqual(len(diffs), 1, f"exactly one line should change, got {diffs}")
        self.assertTrue(old_lines[diffs[0]].strip().startswith("Coordinates:"))

        # ZIP: same entry names; non-coordinate entries byte-identical.
        self.assertEqual(_zip_names(self.orig_zip), _zip_names(new_zip))
        for name in ("index.html", "audio_1.mp3", "audio_2.mp3", "audio_3.mp3",
                     "manifest.json", "audio_2.txt", "audio_3.txt"):
            self.assertEqual(_zip_entry(self.orig_zip, name),
                             _zip_entry(new_zip, name),
                             f"{name} must be byte-identical")
        # audio_1.txt changed ONLY on its Coordinates line.
        o1 = _zip_entry(self.orig_zip, "audio_1.txt").decode().splitlines()
        n1 = _zip_entry(new_zip, "audio_1.txt").decode().splitlines()
        d1 = [i for i in range(len(o1)) if o1[i] != n1[i]]
        self.assertEqual(len(d1), 1)
        self.assertTrue(o1[d1[0]].strip().startswith("Coordinates:"))

    def test_ac3_near_stop_not_moved(self):
        res = self._apply()
        # Stop 2 (Paul Revere House) is ~8 m off its reference → NOT rewritten.
        self.assertNotIn(1, res.moved)
        row2 = next(r for r in res.rows if r["index"] == 1)
        self.assertFalse(row2["rewrite"])

    def test_ac4_version_bumped_no_delete(self):
        res = self._apply()
        self.assertEqual(len(self.store["versions"]), 1)
        v = self.store["versions"][0]
        self.assertEqual(v["version_no"], 1)                      # MAX(0)+1
        self.assertEqual(v["tour_content"], self.orig_content)    # OLD content archived
        self.assertEqual(v["tour_id"], 999)
        self.assertEqual(res.version_no, 1)
        # No DELETE was ever issued.
        self.assertFalse(any("delete" in s for s, _ in self.store["sql_log"]))
        self.assertEqual(self.conn.committed, 1)
        self.assertEqual(self.conn.rolled_back, 0)

    def test_ac5_backup_written(self):
        res = self._apply()
        self.assertIn("tour_content", res.backup_paths)
        self.assertIn("zip", res.backup_paths)
        with open(res.backup_paths["tour_content"], encoding="utf-8") as f:
            self.assertEqual(f.read(), self.orig_content)
        with open(res.backup_paths["zip"], "rb") as f:
            self.assertEqual(f.read(), self.orig_zip)

    def test_ac6_dry_run_writes_nothing(self):
        res = rt.process_tour(
            self.conn, 999, apply_changes=False, move_threshold_m=50.0,
            budget=self.budget, backup_dir=self.tmp,
            reference_fn_factory=_ref_factory, log=lambda *_: None)
        self.assertFalse(res.applied)
        self.assertEqual(res.moved, [0])                 # still REPORTS the move
        self.assertEqual(self.store["row"]["tour_content"], self.orig_content)
        self.assertEqual(self.store["row"]["audio_tour"], self.orig_zip)
        self.assertEqual(len(self.store["versions"]), 0)
        self.assertFalse(os.listdir(self.tmp))           # no backup files
        self.assertEqual(self.conn.committed, 0)


class RepinUnitTests(unittest.TestCase):
    def test_rewrite_nth_coordinate_only_target(self):
        text = ("Coordinates: 1.0, 2.0\n"
                "Coordinates: 3.0, 4.0\n"
                "Coordinates: 5.0, 6.0\n")
        out = rt.rewrite_nth_coordinate(text, 1, 10.5, 20.25)
        lines = out.splitlines()
        self.assertEqual(lines[0], "Coordinates: 1.0, 2.0")
        self.assertEqual(lines[1], "Coordinates: 10.5, 20.25")
        self.assertEqual(lines[2], "Coordinates: 5.0, 6.0")

    def test_zip_rewrite_preserves_names_and_order(self):
        content = _tour_content()
        zb = _build_zip(content)
        new_zip, changed = rt.rewrite_zip_coordinates(
            zb, {0: _REF["Old North Church"]})
        self.assertEqual(_zip_names(zb), _zip_names(new_zip))
        self.assertEqual(changed["audio_1.txt"], 1)
        self.assertEqual(changed["audio_2.txt"], 0)
        self.assertGreaterEqual(changed["tour_content.txt"], 1)

    def test_coord_format_trims_zeros(self):
        self.assertEqual(rt._fmt_coord_pair(42.366370, -71.054540),
                         "42.36637, -71.05454")
        # A whole number keeps one decimal so the app's [-\d.]+ parser is happy.
        self.assertEqual(rt._fmt_coord_num(42.0), "42.0")


if __name__ == "__main__":
    unittest.main()
