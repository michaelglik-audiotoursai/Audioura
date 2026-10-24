#!/usr/bin/env python3
"""test_local752_translation_inherits_community.py — LOCAL-752 A1 (RED first).

Michael's retest (2026-10-23): the Russian translation (row 737) of a community
tour (row 736, community_id 10, visibility members) got NO community_id and NO
community_visibility, so the community page (communities_api._tours_for,
WHERE community_id = %s) never listed it and the Russian appeared nowhere.

A translation of a community tour must INHERIT its source's community_id and
community_visibility — written on the translation row at INSERT time, in BOTH
insert paths (translate_tour_with_audio and _translate_tour_from_zip).

The decision lives in a pure helper
translation_service.TranslationService._append_community_cols(cursor, cols,
vals, source_tour_id) so both insert paths and this test exercise the EXACT same
code without running Polly/LLM. It:

  * reads the SOURCE tour's community_id + community_visibility (schema-guarded
    against a DB without those columns);
  * when the source HAS a community, appends 'community_id' and
    'community_visibility' to the cols/vals lists so the translation row carries
    them;
  * is a NO-OP when the source has no community (ordinary tour), when the
    columns are absent (older schema), or on any read error — never raising.

Hermetic: a scripted fake cursor, no Postgres, writes NO rows (same style as
test_local666_translation_source_version.py). Stubs boto3 so the module imports
without the service container.

Run: python3 -m pytest tests/test_local752_translation_inherits_community.py -q
"""
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_TRDIR = os.path.join(_ROOT, "translation-service")
if _TRDIR not in sys.path:
    sys.path.insert(0, _TRDIR)


class _FakeCursor:
    """Answers each execute() from a scripted plan of (needle, rows) pairs: the
    first pair whose needle appears (case-insensitively) in the normalised SQL
    wins. Mirrors psycopg2 tuples without a DB."""

    def __init__(self, plan):
        self._plan = plan
        self._rows = []

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split()).lower()
        for needle, result in self._plan:
            if needle.lower() in text:
                self._rows = list(result)
                return
        self._rows = []

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def close(self):
        pass


# information_schema probe answers for the community columns (COUNT(*) shape).
_COLS_PRESENT = ("information_schema", [(2,)])
_COLS_ABSENT = ("information_schema", [(0,)])


class AppendCommunityColsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if "boto3" not in sys.modules:
            _boto3 = types.ModuleType("boto3")
            _boto3.client = lambda *a, **k: object()
            sys.modules["boto3"] = _boto3
        import translation_service as tr
        cls.tr = tr
        cls.svc = tr.TranslationService.__new__(tr.TranslationService)

    def test_helper_exists(self):
        self.assertTrue(
            hasattr(self.svc, "_append_community_cols"),
            "TranslationService._append_community_cols is missing — the translation "
            "insert paths have no way to inherit community_id/community_visibility "
            "(LOCAL-752 A1).")

    def test_appends_inherited_community_for_community_source(self):
        # Source tour 736 is community 10, members. The helper must append both
        # columns with the inherited values.
        cur = _FakeCursor([
            _COLS_PRESENT,
            ("select community_id, community_visibility from audio_tours",
             [(10, "members")]),
        ])
        cols = ["tour_name", "content_language"]
        vals = ["Пешеходная экскурсия", "ru"]
        self.svc._append_community_cols(cur, cols, vals, 736)
        self.assertIn("community_id", cols)
        self.assertIn("community_visibility", cols)
        self.assertEqual(vals[cols.index("community_id")], 10)
        self.assertEqual(vals[cols.index("community_visibility")], "members")
        # cols and vals stay the same length (one value per column).
        self.assertEqual(len(cols), len(vals))

    def test_public_visibility_inherited(self):
        cur = _FakeCursor([
            _COLS_PRESENT,
            ("select community_id, community_visibility from audio_tours",
             [(10, "public")]),
        ])
        cols, vals = ["tour_name"], ["x"]
        self.svc._append_community_cols(cur, cols, vals, 736)
        self.assertEqual(vals[cols.index("community_visibility")], "public")

    def test_noop_for_ordinary_tour(self):
        # Source has no community → nothing appended.
        cur = _FakeCursor([
            _COLS_PRESENT,
            ("select community_id, community_visibility from audio_tours",
             [(None, None)]),
        ])
        cols, vals = ["tour_name"], ["x"]
        self.svc._append_community_cols(cur, cols, vals, 500)
        self.assertNotIn("community_id", cols)
        self.assertNotIn("community_visibility", cols)
        self.assertEqual(cols, ["tour_name"])

    def test_noop_when_columns_absent(self):
        # Older schema without the community columns → nothing appended, no raise.
        cur = _FakeCursor([_COLS_ABSENT])
        cols, vals = ["tour_name"], ["x"]
        self.svc._append_community_cols(cur, cols, vals, 736)
        self.assertNotIn("community_id", cols)
        self.assertEqual(cols, ["tour_name"])

    def test_never_raises_on_error(self):
        class _Boom:
            def execute(self, *a, **k):
                raise RuntimeError("db gone")

            def fetchone(self):
                return None
        cols, vals = ["tour_name"], ["x"]
        # Must not raise — a read failure degrades to an ordinary (untagged) row.
        self.svc._append_community_cols(_Boom(), cols, vals, 736)
        self.assertEqual(cols, ["tour_name"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
