r"""test_local873_thin_stop_search.py — LOCAL-873 / D766.

A thin stop (fewer than 3 sourced specifics) escalates to a real web search +
page fetch before the narrator. These tests run OFFLINE with injected
``serp_fn`` / ``fetch_fn`` / ``llm_fn`` / ``escalate_fn`` — no network, no paid
call. They assert the four things the ticket names:

  1. NAME-VARIANT GENERATION — English + Vietnamese, with/without diacritics,
     kind-word synonyms (pier/wharf/quay/bến), "+ history", the natural question.
  2. SNIPPET ACCEPTANCE for "Bach Dang Wharf" (and Quay / Bến) — the exact bug
     that rejected every English snippet for "Bạch Đằng Pier" (the đ-fold and the
     exact-kind-word requirement) is fixed: acceptance is by distinctive token.
  3. PAGE-FETCH FAILURE → graceful fallback (no raise; falls back to the snippet,
     still sourced).
  4. COST CAP respected (≈ $0.01/thin stop): queries stop at the cap, cost is
     logged/returned and never exceeds it.

Plus: thin detection counts sourced specifics; a NOT-thin stop is left alone; the
geo-gate drops a page about a same-name place in another city (no Sydney).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import thin_stop_search as ts  # noqa: E402

STOP = "Bạch Đằng Pier"
CITY = "Ho Chi Minh City"
SCOPE = "Ho Chi Minh City, Vietnam"


def _no_escalate(name, scope, **kw):
    """Offline local_language bundle: Vietnamese, pier subtype, local alias and
    the maritime kind words — no network."""
    return {
        "languages": ["vi"], "dominant": "vi", "country_code": "vn",
        "classification": {"group": "maritime", "subtype": "pier",
                           "confidence": "name"},
        "local_alias": "Bến Bạch Đằng",
        "wikipedia": {}, "kind_words_keys": [],
        "serper": {"queries": [], "gl": "vn", "hl": "vi",
                   "local_name": "Bến Bạch Đằng"},
    }


# ── 1. thin detection ─────────────────────────────────────────────────────────
class TestThinDetection(unittest.TestCase):
    def test_boilerplate_is_thin(self):
        self.assertTrue(ts.is_thin(["A lovely place to relax by the water.",
                                    "A popular spot with locals and tourists."]))

    def test_three_specifics_is_not_thin(self):
        facts = [
            "The pier was built in 1864 on the Saigon River.",
            "Ferries from the quay served the French colonial trade.",
            "A naval battle on the Bạch Đằng river is commemorated here.",
        ]
        self.assertEqual(ts.count_specifics(facts), 3)
        self.assertFalse(ts.is_thin(facts))

    def test_not_thin_stop_is_left_alone(self):
        facts = [
            "Built in 1864 along the Saigon River.",
            "Its length is 200 metres.",
            "Named after the Bạch Đằng battle of 1288.",
            "A ferry terminal for colonial trade.",
        ]
        rep = ts.escalate_thin_stop(STOP, SCOPE, existing_facts=facts,
                                    escalate_fn=_no_escalate,
                                    serp_fn=lambda q: [], fetch_fn=lambda u: "",
                                    log=lambda *_: None)
        self.assertFalse(rep["thin"])
        self.assertFalse(rep["escalated"])
        self.assertEqual(rep["serper_queries"], 0)
        self.assertEqual(rep["facts"], [])


# ── 2a. name-variant generation ───────────────────────────────────────────────
class TestNameVariants(unittest.TestCase):
    def test_variants_cover_the_required_forms(self):
        qs = ts.name_variant_queries(
            STOP, CITY, local_name="Bến Bạch Đằng",
            kind_words_en=["pier", "wharf", "quay"], kind_words_local=["bến"],
            local_lang="vi", max_queries=8)
        joined = " || ".join(qs)
        # the accented name
        self.assertTrue(any("Bạch Đằng" in q for q in qs))
        # the diacritic-stripped name
        self.assertTrue(any("Bach Dang" in q for q in qs))
        # the local alias
        self.assertTrue(any("Bến Bạch Đằng" in q for q in qs))
        # the natural question (Michael's example)
        self.assertTrue(any(q.lower().startswith("what is") for q in qs))
        # a kind-word synonym (wharf or quay), not just "pier"
        self.assertTrue("wharf" in joined or "quay" in joined)
        # all queries carry the city
        self.assertTrue(all(CITY in q for q in qs))

    def test_max_queries_is_respected(self):
        qs = ts.name_variant_queries(STOP, CITY, local_name="Bến Bạch Đằng",
                                     kind_words_en=["pier", "wharf", "quay"],
                                     local_lang="vi", max_queries=4)
        self.assertLessEqual(len(qs), 4)
        self.assertEqual(len(qs), len(set(qs)))  # distinct


# ── 2b. snippet acceptance (the Bạch Đằng Pier bug) ───────────────────────────
class TestSnippetAcceptance(unittest.TestCase):
    def test_wharf_quay_ben_all_accepted(self):
        for snip in [
            "Bach Dang Wharf is a riverside promenade in District 1, Ho Chi Minh City.",
            "Bến Bạch Đằng runs along the Saigon River near Me Linh Square.",
            "Bach Dang Quay offers boat rides on the Saigon River.",
            "Bach Dang Pier is where hydrofoils to Vung Tau once departed.",
        ]:
            self.assertTrue(
                ts.snippet_names_stop(STOP, "", snip),
                msg=f"should accept: {snip!r}")

    def test_unrelated_snippet_rejected(self):
        self.assertFalse(ts.snippet_names_stop(
            STOP, "", "The Mekong Delta is a vast maze of rivers and canals."))

    def test_fold_handles_the_dj_letter(self):
        # the exact fold bug: đ must fold to d so "Dang" matches "Đằng".
        self.assertEqual(ts.fold("Đằng"), "dang")
        self.assertIn("dang", ts.name_tokens(STOP))
        self.assertNotIn("pier", ts.name_tokens(STOP))  # kind word is not distinctive


# ── 2c. end-to-end acceptance with injected backends ──────────────────────────
class TestEscalationEndToEnd(unittest.TestCase):
    def _serp(self, query):
        # One venue-naming result (uses the WHARF synonym, no "pier"), plus noise.
        if "Bach Dang" in query or "Bạch Đằng" in query or "Bến" in query:
            return [
                {"title": "Bach Dang Wharf — Saigon",
                 "url": "https://example.vn/bach-dang",
                 "snippet": "Bach Dang Wharf is a historic quay on the Saigon River "
                            "in Ho Chi Minh City."},
                {"title": "Mekong tours",
                 "url": "https://example.vn/mekong",
                 "snippet": "Explore the Mekong Delta by boat."},
            ]
        return []

    def _fetch(self, url):
        if "bach-dang" in url:
            return ("Bach Dang Wharf (Bến Bạch Đằng) lies on the Saigon River in "
                    "Ho Chi Minh City.\n"
                    "The wharf was built in 1864 under French colonial rule.\n"
                    "Hydrofoils to Vung Tau departed from Bach Dang Wharf until 2014.\n"
                    "The Mekong Delta is elsewhere and unrelated.\n")
        return ""

    def _llm(self, system, user, model, **kw):
        # Deterministic extraction: pull two facts from the passages, each tagged
        # with a passage index that is present in the user message.
        self.assertIn("Bạch Đằng Pier", user)
        return ({"facts": [
            {"text": "Bach Dang Wharf was built in 1864 under French colonial rule.",
             "from": 0},
            {"text": "Hydrofoils to Vung Tau departed from Bach Dang Wharf until 2014.",
             "from": 1},
        ]}, 500, 60)

    def test_thin_stop_gets_sourced_facts_with_urls(self):
        rep = ts.escalate_thin_stop(
            STOP, SCOPE, existing_facts=["A pleasant riverside spot."],
            escalate_fn=_no_escalate, serp_fn=self._serp, fetch_fn=self._fetch,
            llm_fn=self._llm, log=lambda *_: None)
        self.assertTrue(rep["thin"])
        self.assertTrue(rep["escalated"])
        self.assertGreaterEqual(len(rep["facts"]), 2)
        # every fact carries a source URL
        for f in rep["facts"]:
            self.assertTrue(f["url"].startswith("https://"))
        # the facts feed the narrator and the gate
        self.assertIn("1864", rep["narrator_block"])
        self.assertTrue(any("1864" in e for e in rep["evidence"]))
        self.assertTrue(any("source:" in e for e in rep["evidence"]))
        # pages fetched are recorded
        self.assertEqual(rep["pages_fetched"], 1)


# ── 3. page-fetch failure → graceful fallback ─────────────────────────────────
class TestPageFetchFailure(unittest.TestCase):
    def _serp(self, query):
        return [{"title": "Bach Dang Wharf",
                 "url": "https://example.vn/bach-dang",
                 "snippet": "Bach Dang Wharf, built 1864, sits on the Saigon River."}]

    def test_fetch_raises_is_caught_and_snippet_kept(self):
        def _boom(url):
            raise RuntimeError("network down")
        rep = ts.escalate_thin_stop(
            STOP, SCOPE, existing_facts=["thin."], escalate_fn=_no_escalate,
            serp_fn=self._serp, fetch_fn=_boom, llm_fn=lambda *a, **k: (None, 0, 0),
            log=lambda *_: None)
        # no raise; the snippet is kept as a sourced fact so the stop still gains
        self.assertTrue(rep["escalated"])
        self.assertEqual(rep["pages_fetched"], 0)
        self.assertGreaterEqual(len(rep["facts"]), 1)
        self.assertIn("1864", rep["facts"][0]["text"])
        self.assertEqual(rep["facts"][0]["url"], "https://example.vn/bach-dang")

    def test_empty_fetch_falls_back_to_snippet(self):
        rep = ts.escalate_thin_stop(
            STOP, SCOPE, existing_facts=["thin."], escalate_fn=_no_escalate,
            serp_fn=self._serp, fetch_fn=lambda u: "",
            llm_fn=lambda *a, **k: (None, 0, 0), log=lambda *_: None)
        self.assertEqual(rep["pages_fetched"], 0)
        self.assertGreaterEqual(len(rep["facts"]), 1)


# ── 4. cost cap ───────────────────────────────────────────────────────────────
class TestCostCap(unittest.TestCase):
    def test_queries_stop_at_the_cap(self):
        calls = {"n": 0}

        def _serp(q):
            calls["n"] += 1
            return []
        # cap = $0.0025 -> at $0.001/query only 2 queries may run.
        rep = ts.escalate_thin_stop(
            STOP, SCOPE, existing_facts=["thin."], escalate_fn=_no_escalate,
            serp_fn=_serp, fetch_fn=lambda u: "", llm_fn=lambda *a, **k: (None, 0, 0),
            cost_cap=0.0025, max_queries=8, log=lambda *_: None)
        self.assertLessEqual(calls["n"], 2)
        self.assertLessEqual(rep["serper_queries"], 2)
        self.assertLessEqual(rep["cost_usd"], 0.0025 + 1e-9)

    def test_total_cost_within_default_cap(self):
        def _serp(q):
            return [{"title": "Bach Dang Wharf", "url": "https://x.vn/a",
                     "snippet": "Bach Dang Wharf built 1864 on the Saigon River."}]

        def _fetch(u):
            return ("Bach Dang Wharf was built in 1864 on the Saigon River in "
                    "Ho Chi Minh City. It served French colonial trade.\n") * 3

        def _llm(system, user, model, **kw):
            return ({"facts": [{"text": "Bach Dang Wharf was built in 1864.",
                                "from": 0}]}, 800, 80)
        rep = ts.escalate_thin_stop(
            STOP, SCOPE, existing_facts=["thin."], escalate_fn=_no_escalate,
            serp_fn=_serp, fetch_fn=_fetch, llm_fn=_llm, log=lambda *_: None)
        self.assertLessEqual(rep["cost_usd"], ts.COST_CAP_USD + 1e-9)
        self.assertTrue(rep["facts"])


# ── 5. geo-gate: a page about a same-name place elsewhere is dropped ───────────
class TestGeoGate(unittest.TestCase):
    def test_other_city_page_dropped(self):
        # "Bach Dang Wharf" also matches a (hypothetical) Sydney page that names
        # Sydney and never the tour's city — it must be dropped, not narrated.
        def _serp(q):
            return [{"title": "Bach Dang Wharf", "url": "https://x.au/sydney",
                     "snippet": "Bach Dang Wharf is near the harbour."}]

        def _fetch(u):
            return ("Bach Dang Wharf sits on Sydney Harbour in Sydney, Australia, "
                    "beside the Opera House.\n"
                    "It was opened in 1973 on Bennelong Point.\n") * 2

        def _llm(system, user, model, **kw):  # should never be reached for this page
            return ({"facts": []}, 0, 0)
        rep = ts.escalate_thin_stop(
            STOP, SCOPE, existing_facts=["thin."], escalate_fn=_no_escalate,
            serp_fn=_serp, fetch_fn=_fetch, llm_fn=_llm, log=lambda *_: None)
        self.assertEqual(rep["pages_fetched"], 0)   # dropped by the geo-gate
        # the snippet did not name the tour's city either, so no Sydney fact leaks
        self.assertFalse(any("Sydney" in f["text"] for f in rep["facts"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
