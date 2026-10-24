#!/usr/bin/env python3
"""test_local752_community_page_languages.py — LOCAL-752 A2 (RED first).

The community page's tour list (communities_api._tours_for) must show, for each
tour, the languages it is available in — the original's own language FIRST, then
every language with a FINISHED (non-draft) translation pointing back at it. This
is the same `languages` contract the new-tours read already returns
(_tour_languages, LOCAL-713), now surfaced on the community page so Michael can
see the Russian of the Danvers tour and the Download can offer it.

Hermetic: a scripted fake cursor, no Postgres, writes NO rows (same style as
test_local713_new_tours.py). The fixture is community 10 with one original
(en) that has a finished ru translation and a draft fr translation, plus a
second original with no translations.

Run: python3 -m pytest tests/test_local752_community_page_languages.py -q
"""
import os
import sys
import datetime
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_UT = os.path.join(_ROOT, "user-tracking")
for p in (_ROOT, _UT):
    if p not in sys.path:
        sys.path.insert(0, p)

import communities_api as ca  # noqa: E402


def _dt(day, hour=9):
    return datetime.datetime(2026, 10, day, hour, 0, 0)


class FakeCursor:
    """Answers the two SQL shapes _tours_for issues: the community's own tours
    (WHERE community_id = %s), and (per tour) its finished translation languages
    (WHERE original_tour_id = %s ... language)."""

    def __init__(self, tours):
        self.tours = tours
        self._result = []

    def execute(self, sql, params=None):
        s = " ".join(sql.split()).lower()
        params = params or ()

        # A tour's finished translation languages.
        if "where original_tour_id = %s" in s and "language" in s:
            (tour_id,) = params
            langs = []
            for t in self.tours:
                if t.get("original_tour_id") == tour_id and not t.get("draft", False):
                    if t.get("language"):
                        langs.append((t["id"], t["language"]))
            langs.sort(key=lambda x: x[0])
            self._result = [(lang,) for (_id, lang) in langs]
            return

        # The community's own non-draft tours. The fix adds the tour's own
        # `language` column to this SELECT so _tour_languages has the original
        # language; it also only lists ORIGINALS (a translation is a language of
        # its original, never its own community-page row).
        if "from audio_tours" in s and "community_id = %s" in s:
            (cid,) = params
            rows = []
            for t in self.tours:
                if t.get("community_id") != cid:
                    continue
                if t.get("draft", False):
                    continue
                if t.get("original_tour_id") is not None:
                    # A translation is never its own row on the community page.
                    continue
                rows.append(t)
            rows.sort(key=lambda t: (t.get("created_at") or datetime.datetime.min, t["id"]),
                      reverse=True)
            version = 1
            self._result = []
            for t in rows:
                # Mirror whatever columns the SELECT asks for; the production
                # query returns id, name, stop_count, created_at, version, and
                # (the A2 fix) the tour's own language as the last column.
                self._result.append((
                    t["id"], t["tour_name"], t.get("stops_count", 0),
                    t.get("created_at"), version, t.get("language"),
                ))
            return

        self._result = []

    def fetchall(self):
        return list(self._result)

    def fetchone(self):
        return self._result[0] if self._result else None


def _fixture():
    return [
        {"id": 736, "tour_name": "Walking tour in Danvers, MA", "stops_count": 5,
         "created_at": _dt(20), "language": "en", "original_tour_id": None,
         "draft": False, "community_id": 10},
        # finished ru translation of 736.
        {"id": 737, "tour_name": "Пешеходная экскурсия в Дэнверсе", "stops_count": 5,
         "created_at": _dt(20), "language": "ru", "original_tour_id": 736,
         "draft": False, "community_id": 10},
        # draft fr translation of 736 — excluded from languages.
        {"id": 738, "tour_name": "Danvers (fr draft)", "stops_count": 5,
         "created_at": _dt(20), "language": "fr", "original_tour_id": 736,
         "draft": True, "community_id": 10},
        # a second original with no translations.
        {"id": 740, "tour_name": "Salem Common", "stops_count": 3,
         "created_at": _dt(19), "language": "en", "original_tour_id": None,
         "draft": False, "community_id": 10},
    ]


class CommunityPageLanguagesTest(unittest.TestCase):
    def setUp(self):
        self.cur = FakeCursor(_fixture())

    def test_tours_for_returns_languages_per_tour(self):
        out = ca._tours_for(self.cur, 10)
        by_id = {t["id"]: t for t in out}
        self.assertIn(736, by_id)
        self.assertIn(740, by_id)
        # A translation is never its own row.
        self.assertNotIn(737, by_id)
        # Each tour row carries a languages list.
        self.assertIn(
            "languages", by_id[736],
            "the community page tour row has no `languages` — the member cannot "
            "see or pick the Russian of the Danvers tour (LOCAL-752 A2).")
        self.assertEqual(by_id[736]["languages"], ["en", "ru"])
        self.assertEqual(by_id[740]["languages"], ["en"])

    def test_existing_fields_preserved(self):
        out = ca._tours_for(self.cur, 10)
        danvers = next(t for t in out if t["id"] == 736)
        self.assertEqual(danvers["name"], "Walking tour in Danvers, MA")
        self.assertEqual(danvers["stop_count"], 5)
        self.assertIn("version", danvers)


class TourLanguagesColumnTest(unittest.TestCase):
    """[LOCAL-752 A2] _tour_languages must read the translation's language from
    content_language (the column the translate INSERT actually writes), NOT the
    legacy `language` column — on real rows every translation has language='en'
    and content_language=<target>, so reading `language` hid every translation."""

    class _ContentLangCursor:
        def __init__(self, rows):
            # rows: list of (id, language, content_language) for translations.
            self.rows = rows
            self._result = []

        def execute(self, sql, params=None):
            s = " ".join(sql.split()).lower()
            # The query must COALESCE content_language first.
            assert "content_language" in s, \
                "_tour_languages must read content_language (LOCAL-752 A2)"
            (tour_id,) = params
            out = []
            for (_id, lang, clang) in self.rows:
                out.append((clang or lang,))
            self._result = out

        def fetchall(self):
            return list(self._result)

    def test_reads_content_language_not_legacy_language(self):
        # The real-data shape: translation row has language='en',
        # content_language='ru'. The result must surface 'ru'.
        cur = self._ContentLangCursor([(737, "en", "ru")])
        self.assertEqual(ca._tour_languages(cur, 736, "en"), ["en", "ru"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
