#!/usr/bin/env python3
"""LOCAL-884 — unit tests for items 1-3.

  §1 strict_grounding_gate: "no evidence" means "no factual claim". A factual
     sentence with empty/thin evidence is UNSUPPORTED and dropped (no LLM call);
     a no-evidence stop gets an honest non-factual body + the D760 disclosure;
     every stop is labelled, and a stop WITH evidence keeps its supported
     sentences.
  §2 landmark_wikipedia_evidence negative cache: the negative TTL is <= 1 day;
     a negative row is re-fetched (not honoured) when the stop's canonical name
     now differs from the name the miss was cached under; a stale-rules negative
     row is re-fetched.
  §3 evidence relevance: a coordinate-less article is rejected unless it shares a
     DISTINCTIVE token with the stop (never a kind word like "book"/"street"); an
     article WITH a coordinate near the pin is accepted.
"""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import strict_grounding_gate as sgg          # noqa: E402
import landmark_wikipedia_evidence as lwe     # noqa: E402

CITY = "Ho Chi Minh City"


def _cls(verdicts):
    def fn(system, user, model, **kw):
        return ({"verdicts": verdicts}, 100, 50)
    return fn


# ═══════════════════ §1 no-evidence-no-claim ═════════════════════════════════
class NoEvidenceNoClaim(unittest.TestCase):
    def test_founded_1163_dropped_on_empty_evidence(self):
        # the cathedral wave-42 claim (Notre-Dame de Paris) with empty evidence.
        body = ("The cathedral was founded in 1163, built in 1182 and completed "
                "in 1345. You hear bells drift across the square.")
        out, rep = sgg.apply_grounding_gate("Cathedral", body, evidence="",
                                            classify_fn=_cls([]))
        self.assertNotIn("1163", out)
        self.assertNotIn("1182", out)
        self.assertNotIn("1345", out)
        self.assertIn("bells drift", out)          # non-factual kept
        self.assertFalse(rep["called"])            # no LLM call
        self.assertTrue(rep["no_evidence"])
        self.assertGreaterEqual(rep["labelled"], 1)
        self.assertGreaterEqual(rep["unsupported"], 1)

    def test_eiffel_dropped_on_thin_evidence(self):
        # a stray token is not evidence for "designed by Gustave Eiffel".
        body = ("Designed by Gustave Eiffel in 1886. You pause under the clock.")
        out, rep = sgg.apply_grounding_gate("Post Office", body, evidence="post",
                                            classify_fn=_cls([]))
        self.assertNotIn("Eiffel", out)
        self.assertIn("clock", out)
        self.assertTrue(rep["no_evidence"])

    def test_stop_with_evidence_keeps_supported(self):
        body = ("The palace was designed by architect Ngô Viết Thụ in 1962. "
                "It was built by engineer Gustave Eiffel in 1863. "
                "You cross a wide forecourt.")
        cls = _cls([
            {"i": 1, "verdict": "SUPPORTED", "evidence": "designed by Thu 1962", "legend": False},
            {"i": 2, "verdict": "UNSUPPORTED", "evidence": "", "legend": False},
        ])
        out, rep = sgg.apply_grounding_gate(
            "Independence Palace", body,
            evidence="The palace was designed by Ngô Viết Thụ, built from 1962.",
            classify_fn=cls)
        self.assertIn("Ngô Viết Thụ", out)
        self.assertNotIn("Eiffel", out)
        self.assertIn("wide forecourt", out)
        self.assertEqual(rep["labelled"], 2)
        self.assertTrue(rep["called"])
        self.assertFalse(rep["no_evidence"])

    def test_no_history_stop_gets_disclosure_and_no_memory(self):
        # a stop with no evidence and no rebuild gets the honest non-factual body +
        # D760 disclosure; its factual memory claim never returns.
        tour = ("Stop 1: Palace\n"
                "Orientation: You reach a wide forecourt.\n"
                "The bombing was ordered by President Ngô Đình Diệm in 1962. "
                "You stand before the gates.\n"
                "Directions: Continue to the museum.\n")
        out, rep = sgg.ground_tour_text(tour, {}, classify_fn=_cls([]),
                                        max_cost_usd=1.0)
        self.assertNotIn("ordered by", out)
        self.assertNotIn("Diệm", out)
        self.assertIn(sgg.NO_HISTORY_DISCLOSURE[:30], out)
        self.assertEqual(rep["no_history_stops"], 1)
        self.assertGreaterEqual(rep["total_labelled"], 1)

    def test_every_stop_labelled_even_without_evidence(self):
        # the "only 3/10 labelled" bug: a tour of factual stops with NO evidence
        # must still label (and drop) every factual sentence.
        tour = ""
        for i in range(1, 4):
            tour += (f"Stop {i}: Place {i}\n"
                     f"Orientation: You arrive at place {i}.\n"
                     f"This place opened in 190{i} and was designed by someone. "
                     f"You look around.\n"
                     f"Directions: Continue.\n")
        out, rep = sgg.ground_tour_text(tour, {}, classify_fn=_cls([]),
                                        max_cost_usd=1.0)
        self.assertEqual(rep["stops"], 3)
        self.assertEqual(rep["no_history_stops"], 3)
        self.assertGreaterEqual(rep["total_labelled"], 3)
        for d in rep["details"]:
            self.assertGreaterEqual(d["labelled"], 1, d)


# ═══════════════════ §2 negative cache rows ══════════════════════════════════
class _FakeCur:
    def __init__(self, row):
        self._row = row

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, *a, **k):
        self._q = a

    def fetchone(self):
        return self._row


class _FakeConn:
    def __init__(self, row):
        self._row = row

    def cursor(self):
        return _FakeCur(self._row)

    def commit(self):
        pass


class NegativeCache(unittest.TestCase):
    def test_negative_ttl_at_most_one_day(self):
        self.assertLessEqual(lwe.CACHE_NEG_TTL_DAYS, 1)

    def _get(self, row, **kw):
        _oc, _oe = lwe._conn, lwe._ensure
        lwe._conn = lambda: _FakeConn(row)
        lwe._ensure = lambda conn: True
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                res = lwe._cache_get("Post Office", "en", pin=(10.78, 106.70), **kw)
            return res, buf.getvalue()
        finally:
            lwe._conn, lwe._ensure = _oc, _oe

    def test_negative_row_honoured_when_name_matches(self):
        # found=False, current rules_version, stored name == the stop name.
        row = (None, False, lwe.RULES_VERSION, "Post Office")
        res, log = self._get(row, match_name="Post Office")
        self.assertEqual(res, (False, None))
        self.assertIn("negative row honoured", log)

    def test_negative_row_not_honoured_when_canonical_differs(self):
        # the miss was cached under the bare "Post Office"; the stop now resolves
        # to the canonical "Saigon Central Post Office" -> re-fetch, not honoured.
        row = (None, False, lwe.RULES_VERSION, "Post Office")
        res, log = self._get(row, match_name="Saigon Central Post Office")
        self.assertIsNone(res)                       # re-fetch
        self.assertIn("NOT honoured", log)

    def test_stale_rules_negative_row_refetched(self):
        row = (None, False, "old-rules-v0", "Post Office")
        res, log = self._get(row, match_name="Post Office")
        self.assertIsNone(res)
        self.assertIn("STALE rules_version", log)


# ═══════════════════ §3 evidence relevance ═══════════════════════════════════
class EvidenceRelevance(unittest.TestCase):
    def test_coordless_generic_token_rejected(self):
        # "Book Street" vs a coordinate-less "Street Without Joy (book)" naming
        # Saigon: shares only the kind words book/street -> rejected.
        raw = {"pages": [{"title": "Street Without Joy",
                          "lead": "Street Without Joy is a 1961 book on the war in Saigon.",
                          "wikitext": "", "coord": None, "qid": ""}]}
        got = lwe._pick("Book Street", raw, pin=(10.780573, 106.699695), city=CITY)
        self.assertIsNone(got)

    def test_coordless_distinctive_token_accepted(self):
        # a coordinate-less article that shares a DISTINCTIVE token is accepted.
        raw = {"pages": [{"title": "Nguyễn Văn Bình Book Street",
                          "lead": "Đường sách Nguyễn Văn Bình is a book street in Saigon.",
                          "wikitext": "", "coord": None, "qid": ""}]}
        got = lwe._pick("Nguyễn Văn Bình Book Street", raw,
                        pin=(10.780573, 106.699695), city=CITY)
        self.assertIsNotNone(got)

    def test_article_with_coord_near_pin_accepted(self):
        raw = {"pages": [{"title": "Saigon Central Post Office",
                          "lead": "The Saigon Central Post Office in Ho Chi Minh City.",
                          "wikitext": "", "coord": [10.7799, 106.6998], "qid": ""}]}
        got = lwe._pick("Saigon Central Post Office", raw,
                        pin=(10.780000, 106.700000), city=CITY)
        self.assertIsNotNone(got)
        self.assertEqual(got["title"], "Saigon Central Post Office")

    def test_kind_words_are_generic(self):
        for w in ("book", "books", "bar", "cafe", "hotel", "street", "hall"):
            self.assertIn(w, lwe._GENERIC_NAME_WORDS)


if __name__ == "__main__":
    unittest.main()
