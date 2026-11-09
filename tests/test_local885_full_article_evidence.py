#!/usr/bin/env python3
"""LOCAL-885 offline tests: full-text parse, paragraph ranking, 6 KB cap, shared
bundle, old-RULES_VERSION re-fetch, rejected article stays rejected."""
import json, os, sys, unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import landmark_wikipedia_evidence as lwe  # noqa: E402

LEAD = "The Saigon Opera House is a theatre in Ho Chi Minh City, opened in 1900."
FULL = (LEAD + "\n\n== Architecture ==\n"
        "The building was designed by the French architects Félix Olivier, Eugène Ferret and Ernest Guichard in 1897.\n"
        "A short line.\n"
        "The lobby has a wide staircase and some pleasant decoration for visitors to look at today and enjoy.\n"
        "\n== History ==\n"
        "In 1944, the theatre was damaged by Allied aerial attacks and stopped functioning; it later served as the National Assembly.\n"
        "\n== See also ==\n"
        "Built in 1901 by Someone Else in a reference-only list that must never be picked up anywhere.\n")
PIN = (10.77639, 106.70278)


def _raw(title="Saigon Opera House", full=FULL, coord=(10.7767, 106.7032)):
    return {"pages": [{"title": title, "lead": LEAD, "wikitext": "", "langlinks": [],
                       "coord": coord, "qid": "", "full_text": full}]}


class Parse(unittest.TestCase):
    def test_sections_and_paragraphs(self):
        self.assertEqual(lwe.article_sections(FULL), ["Architecture", "History", "See also"])
        pars = lwe.split_paragraphs(FULL)
        secs = {s for s, _ in pars}
        self.assertNotIn("See also", secs)                      # reference-like dropped
        self.assertFalse(any(len(p) < 60 for _, p in pars))     # short noise dropped

    def test_ranking_prefers_story_paragraphs(self):
        out = lwe.select_passages(FULL, LEAD)
        self.assertIn("1944", out)
        self.assertIn("Olivier", out)
        self.assertNotIn("pleasant decoration", out)            # score 0 -> not chosen
        self.assertNotIn("Someone Else", out)
        self.assertNotIn("opened in 1900", out)                 # lead paragraph skipped

    def test_cap(self):
        big = "\n".join(f"In {1800+i % 150}, Pierre Dupont designed and built hall number {i} and opened it to the public." for i in range(400))
        out = lwe.select_passages("== History ==\n" + big, "", cap=6000)
        self.assertLessEqual(len(out), 6000)
        self.assertGreater(len(out), 5000)


class Fetch(unittest.TestCase):
    def test_full_text_kept_and_capped_in_art(self):
        art = lwe.fetch_article("Saigon Opera House", "en", fetch_fn=lambda n, l: _raw(),
                                use_cache=False, pin=PIN, city="Ho Chi Minh City")
        self.assertIn("1944", art["full_text"])
        art2 = lwe.fetch_article("Saigon Opera House", "en",
                                 fetch_fn=lambda n, l: _raw(full="x" * 50000),
                                 use_cache=False, pin=PIN, city="Ho Chi Minh City")
        self.assertLessEqual(len(art2["full_text"]), 20000)

    def test_rejected_article_stays_rejected(self):
        # Sydney coordinate: geo-gate rejects regardless of how much text it carries.
        raw = _raw(title="Sydney Opera House", coord=(-33.8568, 151.2153))
        self.assertIsNone(lwe.fetch_article("Opera House", "en", fetch_fn=lambda n, l: raw,
                                            use_cache=False, pin=PIN, city="Ho Chi Minh City"))
        self.assertEqual(lwe.evidence_for("Opera House", "Ho Chi Minh City, Vietnam", ["en"],
                                          fetch_fn=lambda n, l: raw, use_cache=False, pin=PIN), [])

    def test_evidence_item_has_passages_and_split_item(self):
        items = lwe.evidence_for("Saigon Opera House", "Ho Chi Minh City, Vietnam", ["en"],
                                 fetch_fn=lambda n, l: _raw(), use_cache=False, pin=PIN)
        self.assertEqual(len(items), 1)
        p = lwe.split_item(items[0])
        self.assertEqual(p["lead"], LEAD)
        self.assertIn("1944", p["passages"])
        self.assertNotIn("Passages", p["lead"])

    def test_narrator_gets_en_passages_not_local(self):
        en = "Opera - Wikipedia (en). Lead.\nInfobox: built: 1900\nPassages: [History] EN-STORY 1944"
        vi = "Nhà hát - Wikipedia (vi). Dẫn.\nPassages: [Lịch sử] VI-STORY 1944"
        blk = lwe.narrator_block("Opera House", [en, vi])
        self.assertIn("EN-STORY", blk)
        self.assertNotIn("VI-STORY", blk)


class Shared(unittest.TestCase):
    def test_bundle_is_one_object(self):
        lwe._MEMO.clear()
        with mock.patch.object(lwe, "evidence_for", return_value=["A - Wikipedia (en). x"]):
            a = lwe.cached_evidence("Opera House", "HCMC, Vietnam", pin=PIN, city="HCMC")
            b = lwe.cached_evidence("Opera House", "HCMC, Vietnam", pin=PIN, city="HCMC")
        self.assertIs(a, b)                                     # narrator/gate/audit share it
        self.assertIsInstance(a, lwe.EvidenceBundle)
        self.assertGreater(a.chars(), 0)
        import generate_tour_text as g
        g._wiki_evidence_sink_record("k885", "Opera House", a)
        self.assertEqual(g._WIKI_EVIDENCE_SINK["k885"]["Opera House"], list(a))


class CacheVersion(unittest.TestCase):
    def _conn(self, row):
        cur = mock.MagicMock()
        cur.fetchone.return_value = row
        cur.__enter__ = lambda s: cur
        cur.__exit__ = lambda *a: False
        conn = mock.MagicMock()
        conn.cursor.return_value = cur
        return conn

    def test_old_rules_version_refetched(self):
        payload = json.dumps({"title": "Saigon Opera House", "lead": LEAD, "infobox": ""})
        row = (payload, True, "local881-dense300", "Saigon Opera House", 100.0)
        with mock.patch.object(lwe, "_conn", return_value=self._conn(row)), \
             mock.patch.object(lwe, "_ensure", return_value=True):
            self.assertIsNone(lwe._cache_get("Saigon Opera House", "en", PIN, city="Ho Chi Minh City"))

    def test_current_version_without_full_text_refetched_with_is_hit(self):
        base = {"title": "Saigon Opera House", "lead": LEAD, "infobox": "", "coord": [10.7767, 106.7032]}
        for art, expect_hit in ((base, False), (dict(base, full_text=FULL), True)):
            row = (json.dumps(art), True, lwe.RULES_VERSION, "Saigon Opera House", 100.0)
            with mock.patch.object(lwe, "_conn", return_value=self._conn(row)), \
                 mock.patch.object(lwe, "_ensure", return_value=True):
                got = lwe._cache_get("Saigon Opera House", "en", PIN, city="Ho Chi Minh City")
            self.assertEqual(got is not None, expect_hit)
        self.assertEqual(lwe.RULES_VERSION, "local885-fulltext")


if __name__ == "__main__":
    unittest.main()
