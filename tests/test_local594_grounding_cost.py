"""test_local594_grounding_cost.py — LOCAL-594.

Three things must hold after LOCAL-594:

  1. THE METER COUNTS QUERIES. Google bills grounding by the SEARCH QUERY
     ("Generate content search query gemini 3 paid", $14/1,000), not by request
     and not by token. The meter must tally `groundingMetadata.webSearchQueries`
     from each grounded response and price them at $0.014 each. A grounded
     request that fans out into 3 queries costs 3×$0.014; an ungrounded call
     costs nothing on this channel.

  2. THE CAP HOLDS. The per-stop credit_line loop (story_production_loop) issues
     at most MAX_GROUNDED_PER_STOP grounded narrate requests per stop (default 1),
     regardless of how many credit_lines it examines. r2 adjudication is never
     grounded.

  3. STORY LEADS STILL REACH THE STOP. Capping grounding must not drop stories:
     later credit_lines narrate ungrounded and are still verified and published.
     A stop that produced a passing story before the cap still produces one after.

No network and no API key: `requests.post` is faked to return a Gemini-shaped
response that carries webSearchQueries, and the Serper search is stubbed.

Run:  python3 -m unittest tests.test_local594_grounding_cost -v
"""
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

# A key must be present or the Gemini wrappers short-circuit before issuing a
# request. The network is faked below, so the value never reaches Google.
os.environ.setdefault("GEMINI_API_KEY", "test-key-not-real")

import story_leads  # noqa: E402
from cost_rates import (grounding_query_cost, GROUNDING_COST_PER_QUERY,  # noqa: E402
                        grounding_cost)


# ─── a fake Gemini wire that reports webSearchQueries ────────────────────────
class _FakeResp:
    status_code = 200

    def __init__(self, queries):
        self._queries = queries

    def raise_for_status(self):
        pass

    def json(self):
        # A grounded response carries groundingMetadata.webSearchQueries; an
        # ungrounded one does not. We echo whatever the caller's tools asked for.
        gm = {"webSearchQueries": self._queries} if self._queries else {}
        return {"candidates": [{"content": {"parts": [{"text": "a sentence that happened in 1961."}]},
                                "groundingMetadata": gm}]}


class _Wire:
    """Fake requests.post that mints N webSearchQueries for each grounded request
    and records, independently of story_leads, how many grounded requests and
    queries went out."""

    def __init__(self, queries_per_grounded_request=3):
        self.qpr = queries_per_grounded_request
        self.grounded_requests = 0
        self.ungrounded_requests = 0
        self.queries_issued = 0

    def post(self, url, headers=None, json=None, timeout=None, **kwargs):
        tools = (json or {}).get("tools") or []
        is_grounded = any("google_search" in (t or {}) for t in tools)
        if is_grounded:
            self.grounded_requests += 1
            qs = [f"q{self.queries_issued + i}" for i in range(self.qpr)]
            self.queries_issued += self.qpr
            return _FakeResp(qs)
        self.ungrounded_requests += 1
        return _FakeResp([])


class TestMeterCountsQueries(unittest.TestCase):
    """(1) The meter tallies webSearchQueries and prices at $0.014/query."""

    def setUp(self):
        import requests
        self._orig_post = requests.post
        self._orig_head = requests.head
        self.wire = _Wire(queries_per_grounded_request=3)
        requests.post = self.wire.post
        requests.head = lambda *a, **k: type("H", (), {"url": ""})()
        story_leads.reset_grounding_requests()

    def tearDown(self):
        import requests
        requests.post = self._orig_post
        requests.head = self._orig_head

    def test_rate_is_14_per_1000_queries(self):
        self.assertEqual(GROUNDING_COST_PER_QUERY, 0.014)
        self.assertAlmostEqual(grounding_query_cost(1000), 14.00, places=6)
        self.assertAlmostEqual(grounding_query_cost(3), 0.042, places=6)
        self.assertEqual(grounding_query_cost(0), 0.0)

    def test_queries_counted_not_requests(self):
        # 4 grounded requests, each fanning out into 3 queries => 12 queries.
        for _ in range(4):
            story_leads._gemini("q", grounded=True)
        self.assertEqual(story_leads.get_grounding_requests(), 4)
        self.assertEqual(story_leads.get_grounding_queries(), 12)
        self.assertEqual(story_leads.get_grounding_queries(), self.wire.queries_issued)
        # The dollar figure follows the queries, not the requests.
        self.assertAlmostEqual(
            grounding_query_cost(story_leads.get_grounding_queries()),
            12 * 0.014, places=6)

    def test_ungrounded_calls_cost_nothing_on_this_channel(self):
        for _ in range(5):
            story_leads._gemini("q", grounded=False)
        self.assertEqual(story_leads.get_grounding_requests(), 0)
        self.assertEqual(story_leads.get_grounding_queries(), 0)

    def test_with_sources_counts_queries_too(self):
        for _ in range(2):
            story_leads.gemini_with_sources("q", resolve=False)  # grounded by default
        self.assertEqual(story_leads.get_grounding_requests(), 2)
        self.assertEqual(story_leads.get_grounding_queries(), 6)

    def test_reset_zeroes_both_counters(self):
        story_leads._gemini("q", grounded=True)
        self.assertGreater(story_leads.get_grounding_queries(), 0)
        story_leads.reset_grounding_requests()
        self.assertEqual(story_leads.get_grounding_requests(), 0)
        self.assertEqual(story_leads.get_grounding_queries(), 0)

    def test_meter_matches_michaels_bill_shape(self):
        # Michael's 2026-10-05 line: 1,653 queries billed $23.14 => $14/1,000.
        self.assertAlmostEqual(grounding_query_cost(1653), 23.142, places=3)


# ─── a fake per-stop loop environment ────────────────────────────────────────
class _StopHarness:
    """Patches the network boundaries story_production_loop.run_for_stop uses, so
    the loop runs offline: every grounded r1 and ungrounded r2 goes through a fake
    gemini_with_sources, and the Serper challenge is stubbed. Records how many
    grounded vs ungrounded gemini calls the loop made."""

    def __init__(self):
        self.grounded = 0
        self.ungrounded = 0

    def gemini_with_sources(self, prompt, model=None, resolve=True, timeout=90,
                            grounded=True):
        if grounded:
            self.grounded += 1
        else:
            self.ungrounded += 1
        # r1 narrate: a checkable, eventful sentence. r2 adjudicate: PART 1/PART 2.
        if "PART 2" in prompt or "ADJUDICATE" in prompt or "earlier answer" in prompt:
            text = ("PART 1\nCONFIRMED In 1961 the artist destroyed the first "
                    "edition — the museum's own record.\n"
                    "PART 2\nIn 1961 the artist destroyed the first edition of the "
                    "work after the printer sanded the stones, and only eleven "
                    "proofs survived.")
        else:
            text = ("In 1961 the artist destroyed the first edition of the work "
                    "after the printer sanded the stones. Only eleven proofs "
                    "survived the destruction.")
        return {"text": text, "sources": [{"domain": "museum.example",
                                            "url": "https://museum.example/x"}],
                "supports": [], "queries": (["destroyed 1961"] if grounded else []),
                "error": ""}

    def serp_search(self, query):
        # One carrier-ish result so challenge/adjudication has evidence to chew.
        return ([{"title": "First edition destroyed 1961",
                  "snippet": ("In 1961 the artist destroyed the first edition "
                              "after the printer sanded the stones."),
                  "url": "https://museum.example/record",
                  "domain": "museum.example"}], 0.0)


class TestCapHoldsAndLeadsReachStop(unittest.TestCase):
    """(2) the cap holds and (3) story leads still reach the stop."""

    def _run_stop(self, max_credit_lines, max_grounded):
        import importlib
        import story_production_loop as spl
        import story_leads
        import work_story_searcher
        import snippet_ranker
        import object_record

        h = _StopHarness()

        # Patch the network boundaries the loop reaches through.
        orig = {
            "sl": story_leads.gemini_with_sources,
            "serp": work_story_searcher._serp_search,
            "fetch": snippet_ranker.fetch_pages_for_top_snippets,
            "enrich": object_record.enrich_matrix,
            "maxcl": spl.MAX_CREDIT_LINES,
            "maxg": spl.MAX_GROUNDED_PER_STOP,
            "bestof": spl.BEST_OF,
            "stopat": spl.STOP_AT,
        }
        story_leads.gemini_with_sources = h.gemini_with_sources
        work_story_searcher._serp_search = h.serp_search
        snippet_ranker.fetch_pages_for_top_snippets = lambda raw, max_fetches=3: None
        object_record.enrich_matrix = lambda m, url, verbose=False: (m, {})
        # Force the loop to EXAMINE several credit_lines (BEST_OF on, high STOP_AT
        # so it never short-circuits before trying them all).
        spl.MAX_CREDIT_LINES = max_credit_lines
        spl.MAX_GROUNDED_PER_STOP = max_grounded
        spl.BEST_OF = True
        spl.STOP_AT = 999

        matrix = {
            "canonical_title": "Le Lézard aux plumes d'or",
            "artist": "Joan Miró",
            "publisher": "Louis Broder",
            "printed_by": "Mourlot Frères",
            "printer": "Mourlot Frères",
            "collaborator": "Tériade",
            "credit_line": "Gift of the Lamar Family",
            "medium": "lithograph",
            "venue_name": "McMullen Museum of Art",
        }
        stop_text = ("The work is a livre d'artiste. Mourlot Frères printed it and "
                     "Tériade published related suites. The Lamar Family gave it.")
        try:
            out = spl.run_for_stop(matrix, stop_text,
                                   exhibition="Miró at the McMullen",
                                   venue_url="", extra_entities=["Joan Miró"],
                                   verbose=False)
        finally:
            story_leads.gemini_with_sources = orig["sl"]
            work_story_searcher._serp_search = orig["serp"]
            snippet_ranker.fetch_pages_for_top_snippets = orig["fetch"]
            object_record.enrich_matrix = orig["enrich"]
            spl.MAX_CREDIT_LINES = orig["maxcl"]
            spl.MAX_GROUNDED_PER_STOP = orig["maxg"]
            spl.BEST_OF = orig["bestof"]
            spl.STOP_AT = orig["stopat"]
        return out, h

    def test_cap_holds_even_when_many_credit_lines_examined(self):
        out, h = self._run_stop(max_credit_lines=4, max_grounded=1)
        # Several credit_lines examined...
        self.assertGreater(out.get("examined", 0), 1,
                           "test did not exercise multiple credit_lines")
        # ...but at most ONE grounded narrate request was issued for the stop.
        self.assertLessEqual(h.grounded, 1,
                             f"grounded requests {h.grounded} exceeded cap of 1")
        self.assertEqual(out.get("grounded_requests"), h.grounded,
                         "out['grounded_requests'] must equal grounded calls made")
        # And the loop DID make additional (ungrounded) narrate + adjudicate calls,
        # proving the cap did not simply stop the loop.
        self.assertGreater(h.ungrounded, 1,
                           "cap must leave later credit_lines narrating ungrounded")

    def test_adjudication_is_never_grounded(self):
        # With MAX_GROUNDED=1 and >1 credit_line, if r2 were grounded we would see
        # grounded >= 2. grounded <= 1 proves r2 adjudication did not ground.
        out, h = self._run_stop(max_credit_lines=3, max_grounded=1)
        self.assertLessEqual(h.grounded, 1)

    def test_story_leads_still_reach_the_stop(self):
        # (3) Capping grounding must not CHANGE whether a story reaches the stop.
        # The real publish gate (story_index, material kind, confirmed counts)
        # decides pass/fail; what LOCAL-594 must guarantee is that the grounding
        # cap does not alter that outcome. So we compare the SAME inputs with the
        # cap off (grounded budget = every credit_line) vs on (budget = 1): the
        # story outcome must be identical. A story present uncapped but absent
        # capped would be the bounce the ticket forbids.
        out_uncapped, h_un = self._run_stop(max_credit_lines=4, max_grounded=4)
        out_capped, h_cap = self._run_stop(max_credit_lines=4, max_grounded=1)
        # The cap genuinely reduced grounded requests on these inputs.
        self.assertGreater(h_un.grounded, h_cap.grounded,
                           "test did not actually exercise the cut")
        self.assertLessEqual(h_cap.grounded, 1)
        # Same story outcome: whatever passed uncapped also passes capped.
        self.assertEqual(bool(out_uncapped.get("story")),
                         bool(out_capped.get("story")),
                         "grounding cap changed whether a story reached the stop "
                         "— a drop in story count is a bounce (LOCAL-594)")
        self.assertEqual(len(out_uncapped.get("stories", [])),
                         len(out_capped.get("stories", [])),
                         "grounding cap changed the number of stories at the stop")
        # Every lead still reaches the stop as a CANDIDATE: the cap must not skip
        # credit_lines, only change whether their narrate call is grounded.
        self.assertEqual(out_uncapped.get("examined"), out_capped.get("examined"),
                         "grounding cap skipped credit_lines — leads must still "
                         "reach the stop, just narrated ungrounded")
        self.assertEqual(len(out_uncapped.get("candidates", [])),
                         len(out_capped.get("candidates", [])),
                         "grounding cap produced fewer candidates")

    def test_zero_budget_matches_full_budget_outcome(self):
        # STORY_LOOP_MAX_GROUNDED=0 (never ground) must reach the same story
        # outcome as the fully-grounded run on the same inputs — the ungrounded
        # narrate + Serper challenge path still verifies and publishes.
        out_full, h_full = self._run_stop(max_credit_lines=3, max_grounded=3)
        out_zero, h_zero = self._run_stop(max_credit_lines=3, max_grounded=0)
        self.assertEqual(h_zero.grounded, 0)
        self.assertEqual(bool(out_full.get("story")),
                         bool(out_zero.get("story")),
                         "zero grounded budget changed the story outcome")


if __name__ == "__main__":
    unittest.main()
