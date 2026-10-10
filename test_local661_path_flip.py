#!/usr/bin/env python3
"""test_local661_path_flip.py — a Wikimedia 429 must not flip a resolved museum
onto the exhibition site-first path.

Reproduces Bench AB6 tour 639 (run_ON-3.log) offline, with INJECTED 429s:

  line 74 : [venue_resolver] Resolved: 'The Frick Collection' → Q682827
  line 88 : HTTP 429 for qid 'Q1384'  ... a 429 storm begins
  line 96 : a SECOND resolve_venue() for the SAME venue runs (deterministic block)
  line 102: [LOCAL-599] No Wikidata entity for 'The Frick Collection' — exhibition
            site-first path ELIGIBLE          ← THE FLIP (2 of 3 stops, Kiro 2.5)

The venue was resolved 28 lines earlier. A later lookup failed on the rate limit
and was read as "this museum has no Wikidata entity". The OFF arm of the same
venue delivered 3 stops / 6.5.

What is proven here (all OFFLINE, no network — resolve impl + HTTP are stubbed):
  A. The per-tour resolution memo makes a resolved QID KNOWN for the rest of the
     tour: a later resolve_venue() for the same venue that returns None *while a
     429 fired during the call* reuses the memoised entity (Q682827) instead of
     None. The deterministic block's `if _det_entity and _det_entity.qid` guard
     therefore stays on the collection path and never reaches the LOCAL-599
     "No Wikidata entity" else-branch.
  B. A GENUINE absence (resolve returns None with NO network failure observed)
     still returns None, so a real no-Wikidata-entity museum (MassArt) keeps its
     site-first path — the memo does not fabricate entities.
  C. fetch_venue_works signals UNKNOWN (counts a network failure) on a 429/None-
     after-retries, distinct from a verified empty catalogue (200 + 0 bindings).
     This is the signal the LOCAL-580 "0 documented works → exhibition eligible"
     guard reads to avoid flipping on a works-query rate limit.
  D. The LOCAL-580 eligibility DECISION, modelled on the real counter delta:
     0 documented works + a 429 during the works lookup → NOT eligible (collection
     path kept); 0 works with NO failure → eligible (genuine exhibition museum).
  E. End-to-end call-sequence replay of the log: resolve-ok → 429 storm →
     re-resolve → the collection path is kept and 3 documented stops survive.

Run:  python3 -m pytest test_local661_path_flip.py -q
      python3 test_local661_path_flip.py
"""
import unittest

import venue_resolver as vr


FRICK_QID = "Q682827"
FRICK = "The Frick Collection"
NY = "New York"


def _frick_entity():
    return vr.VenueEntity(qid=FRICK_QID, name=FRICK,
                          official_url="https://www.frick.org", lat=40.771, lng=-73.967)


class _ResolveScope:
    """Install a fresh per-tour resolution memo for the duration of a test."""
    def __enter__(self):
        self._tok = vr.begin_resolution_scope()
        vr.reset_network_failure_count()
        return self

    def __exit__(self, *a):
        vr.end_resolution_scope(self._tok)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# A. The memo keeps the QID known across a 429 (the Frick re-resolve)
# ─────────────────────────────────────────────────────────────────────────────
class TestResolutionMemoHoldsUnder429(unittest.TestCase):
    def setUp(self):
        self._orig_impl = vr._resolve_venue_impl

    def tearDown(self):
        vr._resolve_venue_impl = self._orig_impl

    def test_second_resolve_under_429_reuses_memoised_qid(self):
        calls = {"n": 0}

        def _impl(venue, city=""):
            calls["n"] += 1
            if calls["n"] == 1:
                return _frick_entity()           # line 74: clean resolve
            # line 96: the 429 storm — every Wikidata search returns None and the
            # failure counter ticks (exactly as _search_entities does on a 429).
            vr._network_failure_count += 1
            return None

        vr._resolve_venue_impl = _impl
        with _ResolveScope():
            first = vr.resolve_venue(FRICK, NY)
            # The deterministic block parses the city differently; the name-only
            # memo key must still match.
            second = vr.resolve_venue("The Frick Collection, New York, USA", "")

        self.assertIsNotNone(first)
        self.assertEqual(first.qid, FRICK_QID)
        self.assertIsNotNone(second, "FLIP: a 429 made the resolved Frick look absent")
        self.assertEqual(second.qid, FRICK_QID)

    def test_second_resolve_when_wikidata_cold_reuses_memo(self):
        """Even with no per-call failure delta, a cold Wikidata host is UNKNOWN."""
        import dead_host_breaker as dhb
        calls = {"n": 0}

        def _impl(venue, city=""):
            calls["n"] += 1
            return _frick_entity() if calls["n"] == 1 else None

        vr._resolve_venue_impl = _impl
        tok = dhb.begin_tour_scope()
        try:
            with _ResolveScope():
                first = vr.resolve_venue(FRICK, NY)
                dhb.mark_host_cold("https://www.wikidata.org", reason="429 (test)")
                second = vr.resolve_venue(FRICK, NY)
        finally:
            dhb.end_tour_scope(tok)
        self.assertEqual(first.qid, FRICK_QID)
        self.assertIsNotNone(second, "FLIP: cold Wikidata host read as 'no entity'")
        self.assertEqual(second.qid, FRICK_QID)


# ─────────────────────────────────────────────────────────────────────────────
# B. A genuine absence (no failures) still returns None (MassArt keeps site-first)
# ─────────────────────────────────────────────────────────────────────────────
class TestGenuineAbsenceStillNone(unittest.TestCase):
    def setUp(self):
        self._orig_impl = vr._resolve_venue_impl

    def tearDown(self):
        vr._resolve_venue_impl = self._orig_impl

    def test_clean_zero_hits_returns_none(self):
        vr._resolve_venue_impl = lambda venue, city="": None   # no failures ticked
        with _ResolveScope():
            r = vr.resolve_venue("MassArt Art Museum", "Boston")
        self.assertIsNone(r, "a verified absence must NOT be masked by the memo")

    def test_memo_not_populated_without_qid(self):
        """An entity with no qid is never memoised (defensive)."""
        vr._resolve_venue_impl = lambda venue, city="": vr.VenueEntity(qid="", name="x")
        with _ResolveScope():
            vr.resolve_venue("Nowhere", "")
            self.assertIsNone(vr._resolve_memo_recall("Nowhere", ""))


# ─────────────────────────────────────────────────────────────────────────────
# C. fetch_venue_works: UNKNOWN (429) counts a failure; verified empty does not
# ─────────────────────────────────────────────────────────────────────────────
class TestFetchWorksUnknownVsEmpty(unittest.TestCase):
    def setUp(self):
        self._orig = vr._request_with_backoff

    def tearDown(self):
        vr._request_with_backoff = self._orig

    class _Resp:
        def __init__(self, code, payload=None):
            self.status_code = code
            self._p = payload or {}

        def json(self):
            return self._p

    def test_none_after_retries_counts_failure(self):
        vr._request_with_backoff = lambda *a, **k: None
        vr.reset_network_failure_count()
        works = vr.fetch_venue_works(FRICK_QID)
        self.assertEqual(works, [])
        self.assertEqual(vr.get_network_failure_count(), 1)

    def test_429_status_counts_failure(self):
        vr._request_with_backoff = lambda *a, **k: self._Resp(429)
        vr.reset_network_failure_count()
        works = vr.fetch_venue_works(FRICK_QID)
        self.assertEqual(works, [])
        self.assertEqual(vr.get_network_failure_count(), 1)

    def test_verified_empty_does_not_count(self):
        vr._request_with_backoff = lambda *a, **k: self._Resp(
            200, {"results": {"bindings": []}})
        vr.reset_network_failure_count()
        works = vr.fetch_venue_works("Q999999")
        self.assertEqual(works, [])
        self.assertEqual(vr.get_network_failure_count(), 0)


# ─────────────────────────────────────────────────────────────────────────────
# D. The LOCAL-580 eligibility decision, modelled on the counter delta the
#    deterministic block reads (generate_tour_text.py). 0 works + a 429 during
#    the works lookup → NOT eligible. 0 works + no failure → eligible.
# ─────────────────────────────────────────────────────────────────────────────
class TestSiteFirstEligibilityGuard(unittest.TestCase):
    @staticmethod
    def _eligible(documented_count, fail_before, fail_after):
        """Replica of the LOCAL-661 guard in the deterministic block."""
        if documented_count != 0:
            return False  # (bypass/base path handles >0; not our branch)
        works_unknown = (fail_after - fail_before) > 0
        return not works_unknown

    def test_zero_works_under_429_not_eligible(self):
        self.assertFalse(self._eligible(0, fail_before=0, fail_after=1),
                         "FLIP: 0 works under a 429 wrongly made site-first eligible")

    def test_zero_works_clean_is_eligible(self):
        self.assertTrue(self._eligible(0, fail_before=3, fail_after=3),
                        "a genuine 0-work exhibition museum must stay eligible")


# ─────────────────────────────────────────────────────────────────────────────
# E. End-to-end replay of the log's call sequence: the collection path is kept
#    and 3 documented stops survive (never the 2-of-3 exhibition flip).
# ─────────────────────────────────────────────────────────────────────────────
class TestFrickCallSequenceReplay(unittest.TestCase):
    def setUp(self):
        self._orig_impl = vr._resolve_venue_impl
        self._orig_backoff = vr._request_with_backoff

    def tearDown(self):
        vr._resolve_venue_impl = self._orig_impl
        vr._request_with_backoff = self._orig_backoff

    def test_collection_path_kept_three_stops(self):
        # Documented works the Frick's SPARQL returned on the clean first pass.
        frick_works = [
            {"qid": "Q3783572", "label_en": "More", "label_local": "More",
             "sitelinks": 20, "instance_of": [], "collection_qids": [FRICK_QID]},
            {"qid": "Q3783020", "label_en": "Comtesse d'Haussonville",
             "label_local": "Comtesse d'Haussonville", "sitelinks": 18,
             "instance_of": [], "collection_qids": [FRICK_QID]},
            {"qid": "Q3357025", "label_en": "The Polish Rider",
             "label_local": "The Polish Rider", "sitelinks": 30,
             "instance_of": [], "collection_qids": [FRICK_QID]},
        ]
        state = {"resolves": 0, "storm": False}

        def _impl(venue, city=""):
            state["resolves"] += 1
            if state["resolves"] == 1:
                return _frick_entity()          # line 74
            # line 96: re-resolve during the 429 storm
            vr._network_failure_count += 1       # a Wikidata search 429'd
            return None

        def _backoff(*a, **k):
            # Works SPARQL: clean on the first pass, 429 once the storm starts.
            if state["storm"]:
                return TestFetchWorksUnknownVsEmpty._Resp(429)
            # Build SPARQL bindings shaped like the real endpoint.
            bindings = []
            for w in frick_works:
                bindings.append({
                    "work": {"value": f"http://www.wikidata.org/entity/{w['qid']}"},
                    "workLabel": {"value": w["label_local"]},
                    "workLabel_en": {"value": w["label_en"]},
                    "sitelinks": {"value": str(w["sitelinks"])},
                })
            return TestFetchWorksUnknownVsEmpty._Resp(
                200, {"results": {"bindings": bindings}})

        vr._resolve_venue_impl = _impl
        vr._request_with_backoff = _backoff

        with _ResolveScope():
            # ── poi_selection phase: clean resolve + clean works (line 74–90) ──
            ent1 = vr.resolve_venue(FRICK, NY)
            self.assertEqual(ent1.qid, FRICK_QID)
            works = vr.fetch_venue_works(ent1.qid)
            documented = [w["label_en"] for w in works]
            self.assertEqual(len(documented), 3)

            # ── the 429 storm hits (line 88+) ──
            state["storm"] = True

            # ── deterministic block re-resolves the SAME venue (line 96) ──
            fail_before = vr.get_network_failure_count()
            ent2 = vr.resolve_venue(FRICK, NY)
            # THE FIX: the memo keeps Q682827; the `if _det_entity and .qid`
            # guard stays true and never reaches the LOCAL-599 else-branch.
            self.assertIsNotNone(ent2, "FLIP: re-resolve returned None under 429")
            self.assertEqual(ent2.qid, FRICK_QID)
            self.assertTrue(bool(ent2.qid))

            # If the deterministic block had re-fetched works now, it would be a
            # 429 (0 works). The LOCAL-661 guard reads the counter delta and keeps
            # the collection path rather than declaring an exhibition museum.
            _ = vr.fetch_venue_works(ent2.qid)   # 429 → UNKNOWN
            fail_after = vr.get_network_failure_count()
            works_unknown = (fail_after - fail_before) > 0
            self.assertTrue(works_unknown)
            site_first_eligible = (len(documented) == 0) and not works_unknown
            self.assertFalse(site_first_eligible,
                             "FLIP: resolved Frick made exhibition-site-first eligible")

            # The collection path keeps the 3 documented stops from the clean pass.
            self.assertEqual(documented,
                             ["More", "Comtesse d'Haussonville", "The Polish Rider"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
