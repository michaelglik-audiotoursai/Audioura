#!/usr/bin/env python3
"""test_local669_grounded_highlights.py — LOCAL-669.

A thin-Wikidata museum gets its candidate works from ONE grounded "highlights"
call, verified by that call's OWN citations:

  * a work is verified when ≥1 cited source on the museum's OWN domain names it,
    OR ≥2 INDEPENDENT cited sources name it at this museum;
  * otherwise at most ONE Serper query per candidate may supply the 2nd source;
  * an UNCITED candidate is NEVER accepted.

The headline test is Michael's Ho Chi Minh City Museum of Fine Arts list
(2026-10-10): #1 verified by the museum's own domain, #2 by two independent
sources, #3 by a Serper second source, and the two uncited items (#4, #5)
rejected. Cost is one grounded request plus one Serper query.

Run: python3 -m pytest test_local669_grounded_highlights.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from grounded_highlights import (  # noqa: E402
    build_highlights_prompt,
    parse_highlights,
    verify_highlights,
    grounded_highlights,
    DEFAULT_HIGHLIGHTS,
)

_VENUE = "Ho Chi Minh City Museum of Fine Arts"
_CITY = "Ho Chi Minh City"
_OWN = ["baotangmythuattphcm.com.vn"]

# Michael's Gemini answer (2026-10-10), as a grounded-result the model returned:
# five numbered works with title/artist/year/medium, and per-sentence citations
# that reproduce the real evidence state — #1 on the museum's own site, #2 on two
# independent encyclopaedic sources, #3 on one source only (needs a 2nd), #4/#5
# named but with NO citation attached (unverified "as given").
_HCMC_TEXT = (
    "Notable works in the permanent collection:\n"
    "1. Spring Garden of the Central, South, and North Region (Vườn xuân Trung Nam Bắc) "
    "— Nguyễn Gia Trí — lacquer on wood, 1989 — a designated National Treasure.\n"
    "2. Thanh Niên Thành Đồng (Iron Wall Youth) — Nguyễn Sáng — lacquer, 1978.\n"
    "3. Y-shaped Bridge Battlefield — Huỳnh Phương Đông — oil on canvas, 2001.\n"
    "4. Welcome Spring — Trương Hán Minh — traditional ink, 1951.\n"
    "5. Vietnamese Buffaloes — Quách Phong — modernist painting, 1938.\n"
)


def _own(url="http://baotangmythuattphcm.com.vn/collection"):
    return {"domain": "baotangmythuattphcm.com.vn", "url": url}


def _hcmc_grounded_result():
    return {
        "text": _HCMC_TEXT,
        "sources": [_own()],
        "supports": [
            # #1 — museum's OWN domain names it → verified on one own-domain source.
            {"text": "Spring Garden of the Central, South, and North Region by "
                     "Nguyễn Gia Trí is a National Treasure.",
             "sources": [_own()]},
            # #2 — TWO independent domains → verified by the 2-source rule.
            {"text": "Thanh Niên Thành Đồng (Iron Wall Youth) by Nguyễn Sáng.",
             "sources": [{"domain": "en.wikipedia.org", "url": "https://en.wikipedia.org/wiki/x"},
                         {"domain": "artsandculture.google.com", "url": "https://artsandculture.google.com/y"}]},
            # #3 — ONE independent domain only → needs a Serper 2nd source.
            {"text": "Y-shaped Bridge Battlefield by Huỳnh Phương Đông.",
             "sources": [{"domain": "vnexpress.net", "url": "https://vnexpress.net/z"}]},
            # #4 — named, but NO citation attached → uncited.
            {"text": "Welcome Spring by Trương Hán Minh.", "sources": []},
            # #5 — not attributed by any support → uncited.
        ],
        "queries": ["Ho Chi Minh City Museum of Fine Arts notable works"],
        "error": "",
    }


def _hcmc_serper(query):
    """Serper 2nd-source stub: only #3 gets a second independent domain whose
    snippet actually names the work (an honest 2nd source)."""
    if "Y-shaped Bridge Battlefield" in query:
        return [{"url": "https://nguoilaodong.vn/art/y-bridge",
                 "title": "Y-shaped Bridge Battlefield",
                 "snippet": "Y-shaped Bridge Battlefield by Huỳnh Phương Đông, "
                            "held at the Ho Chi Minh City Museum of Fine Arts."}]
    return []


class TestMichaelHCMCFixture(unittest.TestCase):
    """The headline scenario from the ticket."""

    def setUp(self):
        self.gres = _hcmc_grounded_result()
        self.res = grounded_highlights(
            _VENUE, _CITY,
            research_fn=lambda _p: self.gres,
            serper_fn=_hcmc_serper,
            own_domains=_OWN)

    def test_five_candidates_parsed(self):
        self.assertEqual(len(parse_highlights(self.gres)), 5)

    def test_three_verified_two_rejected(self):
        names = [w["name"] for w in self.res.verified_works]
        self.assertEqual(len(names), 3)
        self.assertTrue(any("Spring Garden" in n for n in names))
        self.assertTrue(any("Thanh" in n for n in names))
        self.assertTrue(any("Y-shaped Bridge Battlefield" in n for n in names))

    def test_uncited_items_rejected(self):
        verified_names = {w["name"] for w in self.res.verified_works}
        self.assertNotIn("Welcome Spring", verified_names)
        self.assertNotIn("Vietnamese Buffaloes", verified_names)
        by_name = {v.name: v for v in self.res.verdicts}
        self.assertFalse(by_name["Welcome Spring"].verified)
        self.assertFalse(by_name["Vietnamese Buffaloes"].verified)
        self.assertEqual(by_name["Welcome Spring"].source_count, 0)
        self.assertEqual(by_name["Vietnamese Buffaloes"].source_count, 0)

    def test_item1_verified_by_own_domain(self):
        v = next(x for x in self.res.verdicts if "Spring Garden" in x.name)
        self.assertTrue(v.verified)
        self.assertTrue(v.own_domain)
        self.assertFalse(v.second_source_query_used)

    def test_item2_verified_by_two_independent(self):
        v = next(x for x in self.res.verdicts if "Thanh" in x.name)
        self.assertTrue(v.verified)
        self.assertFalse(v.own_domain)
        self.assertGreaterEqual(v.source_count, 2)
        self.assertFalse(v.second_source_query_used)

    def test_item3_verified_by_serper_second_source(self):
        v = next(x for x in self.res.verdicts if "Y-shaped" in x.name)
        self.assertTrue(v.verified)
        self.assertTrue(v.second_source_query_used)
        self.assertGreaterEqual(v.source_count, 2)

    def test_cost_one_grounded_one_serper(self):
        self.assertEqual(self.res.grounded_requests, 1)
        self.assertEqual(self.res.serper_queries, 1)

    def test_log_line_shape(self):
        # "[LOCAL-669] highlights: N candidates, M verified, cost ..."
        self.assertIn("[LOCAL-669] highlights:", self.res.log_line)
        self.assertIn("5 candidates", self.res.log_line)
        self.assertIn("3 verified", self.res.log_line)
        self.assertIn("1 grounded request", self.res.log_line)
        self.assertIn("1 Serper queries", self.res.log_line)

    def test_verified_works_carry_fields_and_sources(self):
        w = next(x for x in self.res.verified_works if "Spring Garden" in x["name"])
        self.assertEqual(w["artist"], "Nguyễn Gia Trí")
        self.assertEqual(w["year"], "1989")
        self.assertEqual(w["medium"], "lacquer")
        self.assertTrue(w["verified"])
        self.assertTrue(w["highlight_sources"])


class TestVerificationRule(unittest.TestCase):
    def test_own_domain_single_source_verifies(self):
        gres = {"text": "The Fisherman by Nguyen.",
                "sources": [], "supports": [
                    {"text": "The Fisherman by Nguyen.", "sources": [_own()]}],
                "queries": [], "error": ""}
        v, verdicts, used = verify_highlights(
            [{"name": "The Fisherman"}], gres, _VENUE, own_domains=_OWN)
        self.assertEqual(len(v), 1)
        self.assertEqual(used, 0)
        self.assertTrue(verdicts[0].own_domain)

    def test_two_independent_sources_verify(self):
        gres = {"text": "The Fisherman.", "sources": [], "supports": [
            {"text": "The Fisherman is here.",
             "sources": [{"domain": "a.org", "url": "https://a.org"},
                         {"domain": "b.net", "url": "https://b.net"}]}],
                "queries": [], "error": ""}
        v, verdicts, used = verify_highlights(
            [{"name": "The Fisherman"}], gres, _VENUE, own_domains=_OWN)
        self.assertEqual(len(v), 1)
        self.assertEqual(used, 0)

    def test_one_independent_source_needs_serper(self):
        gres = {"text": "The Fisherman.", "sources": [], "supports": [
            {"text": "The Fisherman is here.",
             "sources": [{"domain": "a.org", "url": "https://a.org"}]}],
                "queries": [], "error": ""}

        def serper(q):
            return [{"url": "https://b.net/fish", "title": "The Fisherman",
                     "snippet": "The Fisherman painting at the museum"}]

        v, verdicts, used = verify_highlights(
            [{"name": "The Fisherman"}], gres, _VENUE, own_domains=_OWN,
            serper_fn=serper)
        self.assertEqual(len(v), 1)
        self.assertEqual(used, 1)
        self.assertTrue(verdicts[0].second_source_query_used)

    def test_serper_result_not_naming_work_does_not_count(self):
        """A Serper hit whose snippet does not name the work is not a 2nd source."""
        gres = {"text": "The Fisherman.", "sources": [], "supports": [
            {"text": "The Fisherman is here.",
             "sources": [{"domain": "a.org", "url": "https://a.org"}]}],
                "queries": [], "error": ""}

        def serper(q):
            return [{"url": "https://b.net/other", "title": "Unrelated",
                     "snippet": "A different artwork entirely."}]

        v, verdicts, used = verify_highlights(
            [{"name": "The Fisherman"}], gres, _VENUE, own_domains=_OWN,
            serper_fn=serper)
        self.assertEqual(v, [])
        self.assertEqual(used, 1)  # the one allowed query was spent
        self.assertFalse(verdicts[0].verified)

    def test_uncited_never_rescued_by_serper(self):
        """A work with NO citation at all is uncited; no Serper query is spent on
        it (there is no first source to be independent of)."""
        gres = {"text": "Welcome Spring by Truong.", "sources": [],
                "supports": [{"text": "Welcome Spring by Truong.", "sources": []}],
                "queries": [], "error": ""}

        calls = {"n": 0}

        def serper(q):
            calls["n"] += 1
            return [{"url": "https://b.net/x", "title": "Welcome Spring",
                     "snippet": "Welcome Spring at the museum"}]

        v, verdicts, used = verify_highlights(
            [{"name": "Welcome Spring"}], gres, _VENUE, own_domains=_OWN,
            serper_fn=serper)
        self.assertEqual(v, [])
        self.assertEqual(used, 0)
        self.assertEqual(calls["n"], 0)
        self.assertFalse(verdicts[0].verified)

    def test_serper_cap_enforced(self):
        """At most max_second_source_queries Serper queries across all candidates."""
        # Three candidates each with exactly one independent cited source.
        supports = [
            {"text": f"Work{i} is here.",
             "sources": [{"domain": f"src{i}.org", "url": f"https://src{i}.org"}]}
            for i in range(3)
        ]
        gres = {"text": "Work0 Work1 Work2.", "sources": [],
                "supports": supports, "queries": [], "error": ""}
        cands = [{"name": f"Work{i}"} for i in range(3)]

        calls = {"n": 0}

        def serper(q):
            calls["n"] += 1
            return []  # never supplies a 2nd source

        v, verdicts, used = verify_highlights(
            cands, gres, _VENUE, own_domains=_OWN, serper_fn=serper,
            max_second_source_queries=2)
        self.assertEqual(used, 2)
        self.assertEqual(calls["n"], 2)  # 3rd candidate got no query (cap hit)


class TestParsing(unittest.TestCase):
    def test_intraword_hyphen_preserved(self):
        gres = {"text": "1. Y-shaped Bridge Battlefield — Huynh — oil, 2001.",
                "sources": [], "supports": [], "queries": [], "error": ""}
        cands = parse_highlights(gres)
        self.assertEqual(cands[0]["name"], "Y-shaped Bridge Battlefield")
        self.assertEqual(cands[0]["artist"], "Huynh")
        self.assertEqual(cands[0]["year"], "2001")
        self.assertEqual(cands[0]["medium"], "oil")

    def test_by_and_paren_year_shape(self):
        gres = {"text": "1. The Fisherman by Nguyen Gia Tri (1943), lacquer.",
                "sources": [], "supports": [], "queries": [], "error": ""}
        c = parse_highlights(gres)[0]
        self.assertEqual(c["name"], "The Fisherman")
        self.assertIn("Nguyen", c["artist"])
        self.assertEqual(c["year"], "1943")

    def test_labelled_fields(self):
        gres = {"text": "1. Title: Lotus Pond; Artist: Le Pho; Year: 1938; Medium: silk.",
                "sources": [], "supports": [], "queries": [], "error": ""}
        c = parse_highlights(gres)[0]
        self.assertEqual(c["name"], "Lotus Pond")
        self.assertEqual(c["artist"], "Le Pho")
        self.assertEqual(c["year"], "1938")
        self.assertEqual(c["medium"], "silk")

    def test_empty_or_error_result(self):
        self.assertEqual(parse_highlights({"text": "", "error": ""}), [])
        self.assertEqual(parse_highlights({"text": "x", "error": "boom"}), [])

    def test_dedup_by_normalised_title(self):
        gres = {"text": "1. The Fisherman — A.\n2. the fisherman — B.",
                "sources": [], "supports": [], "queries": [], "error": ""}
        self.assertEqual(len(parse_highlights(gres)), 1)


class TestOrchestration(unittest.TestCase):
    def test_no_backend_is_safe_noop(self):
        res = grounded_highlights(_VENUE, _CITY, research_fn=None)
        self.assertEqual(res.verified_works, [])
        self.assertEqual(res.grounded_requests, 0)
        self.assertEqual(res.serper_queries, 0)
        self.assertIn("no research backend", res.log_line)

    def test_grounded_error_surfaces(self):
        res = grounded_highlights(
            _VENUE, _CITY,
            research_fn=lambda _p: {"text": "", "error": "no GEMINI_API_KEY"})
        self.assertEqual(res.verified_works, [])
        self.assertEqual(res.grounded_requests, 1)
        self.assertTrue(res.error)

    def test_prompt_mentions_venue_and_citations(self):
        p = build_highlights_prompt(_VENUE, _CITY, n=DEFAULT_HIGHLIGHTS)
        self.assertIn(_VENUE, p)
        self.assertIn("8", p)
        self.assertIn("permanent", p.lower())
        self.assertIn("cite", p.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
