"""LOCAL-669C — the FINAL identity gate before narration, on every museum path.

The 2026-10-10 side-by-side proved the SAME National Treasure shipped TWICE in
BOTH arms, because LOCAL-669B's dedup pass (a) lived inside the thin branch and
never ran on the exhibition path, and (b) collapsed NOTHING on tour 670: the
grounded-highlights stop "Vườn xuân Trung Nam Bắc" carried no QID and its English
GLOSS said "Center" where the SPARQL English label said "Central", so the
order-ignored token sets differed by one word and the bilingual-title bridge
missed.

These tests pin the fix (identity_dedup.final_identity_gate):

  * TOUR 670 FIXTURE (normal arm): "North Central South Spring Garden" (SPARQL,
    QID) + "Vườn xuân Trung Nam Bắc" (highlights, no QID, gloss "Center") + three
    distinct real works → the two Spring Gardens collapse to ONE, five DISTINCT
    works survive (the freed slot refilled from the reserve), no Spring Garden
    twice.
  * TOUR 671 FIXTURE (cheap arm): "North Central South Spring Garden" +
    "Central South and North Spring Garden" (word order) + 3 area stops → the two
    Spring Gardens collapse; the area stops survive.
  * TRIGGER: the gate stamps a QID by EXACT label even when the token sets differ
    (Center vs Central), so the collapse is by QID, language-agnostic.
  * BILINGUAL HEADER: a surviving stop gets "<local> (<English>)", local first,
    one header per work; a mono-lingual work is left unchanged.
  * REGRESSION: a QID CONFLICT is never merged; distinct works are preserved;
    the gate is a no-op on an already-clean list; refill never repeats and
    prefers works over area stops.

Run: python3 -m pytest test_local669c_final_gate.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import identity_dedup as idd  # noqa: E402

# Surface forms of the ONE National Treasure (Q109406846).
_SPRING_EN = "North Central South Spring Garden"            # SPARQL English label
_SPRING_EN_ALT = "Central South and North Spring Garden"    # reordered altLabel
_SPRING_VN = "Vườn xuân Trung Nam Bắc"                       # Vietnamese label_local
_SPRING_GLOSS = "Spring Garden of the Center, South, and North"  # US "Center" gloss
_QID = "Q109406846"


def _poi(name, **kw):
    d = {"name": name}
    d.update(kw)
    return d


# The D1v2 evidence log entry the SPARQL English stop carries: QID + the work's
# BOTH-language SPARQL labels (label_local is the Vietnamese).
def _evidence_log_670():
    return {
        _SPRING_EN: {
            "status": "VERIFIED",
            "qid": _QID,
            "canonical_title": _SPRING_EN,
            "sparql_labels": {
                "label_local": _SPRING_VN,
                "label_en": _SPRING_EN,
                "aliases": [_SPRING_EN_ALT],
            },
        },
    }


class TestTour670Fixture(unittest.TestCase):
    """Normal arm, tour 670: SPARQL English stop + highlights Vietnamese stop are
    the SAME work; the English gloss uses 'Center' (US) so the token sets differ
    from the SPARQL 'Central'. The gate must still collapse them — by QID stamped
    from the evidence log's sparql_labels (the highlights stop is literally named
    the work's label_local)."""

    def _poi_list(self):
        return [
            # Stop 1: the SPARQL-verified English work (carries QID via evidence log).
            _poi(_SPRING_EN, verified=True),
            # Stop 2: the grounded-highlights Vietnamese stop — NO QID, gloss "Center".
            _poi(_SPRING_VN, verified=True,
                 title_local=_SPRING_VN, title_en=_SPRING_GLOSS,
                 highlight_sources=[{"origin": "saigoneer.com", "detail": ""},
                                    {"origin": "asiabankersclub.com", "detail": ""}]),
            _poi("Thanh niên Thành đồng", verified=True),
            _poi("Bác Hồ với thiếu nhi", verified=True),
            _poi("Bóng xế tà", verified=True),
        ]

    def test_two_spring_gardens_collapse_to_one(self):
        res = idd.final_identity_gate(
            self._poi_list(), needed_stops=5, evidence_log=_evidence_log_670())
        names = [p["name"] for p in res.poi_list]
        spring = [n for n in names if "Spring Garden" in n or "xuân" in n]
        self.assertEqual(len(spring), 1,
                         f"exactly one Spring Garden must survive, got {spring}")

    def test_collapse_was_by_qid(self):
        res = idd.final_identity_gate(
            self._poi_list(), needed_stops=5, evidence_log=_evidence_log_670())
        self.assertTrue(res.stamped_qids >= 1,
                        "the highlights stop must be stamped with the work's QID")
        self.assertTrue(any(c.reason == "qid" for c in res.collapses),
                        "the Spring Garden collapse must be by QID")

    def test_five_distinct_works_after_refill(self):
        # A reserve work (distinct) refills the slot the collapse frees → 5 stops.
        reserve = [_poi("Em Thúy", verified=True)]
        res = idd.final_identity_gate(
            self._poi_list(), needed_stops=5, evidence_log=_evidence_log_670(),
            reserve_pool=reserve)
        names = [p["name"] for p in res.poi_list]
        self.assertEqual(len(names), 5, f"must ship 5 stops, got {names}")
        self.assertEqual(len(set(names)), 5, f"all 5 must be DISTINCT, got {names}")
        self.assertIn("Em Thúy", names, "the freed slot is refilled with a work")
        spring = [n for n in names if "Spring Garden" in n or "xuân" in n]
        self.assertEqual(len(spring), 1, "still no Spring Garden twice after refill")

    def test_refill_never_repeats_the_collapsed_work(self):
        # The reserve CONTAINS the same Spring Garden (by QID) — it must be skipped.
        reserve = [_poi(_SPRING_VN, verified=True, qid=_QID),
                   _poi("Em Thúy", verified=True)]
        res = idd.final_identity_gate(
            self._poi_list(), needed_stops=5, evidence_log=_evidence_log_670(),
            reserve_pool=reserve)
        names = [p["name"] for p in res.poi_list]
        spring = [n for n in names if "Spring Garden" in n or "xuân" in n]
        self.assertEqual(len(spring), 1,
                         "the duplicate reserve Spring Garden must NOT be re-added")
        self.assertIn("Em Thúy", names)


class TestTour671Fixture(unittest.TestCase):
    """Cheap arm, tour 671: 'North Central South Spring Garden' +
    'Central South and North Spring Garden' (same work, word order) + 3 area
    stops. The two Spring Gardens collapse by the order-ignored title set; the
    area stops survive."""

    def _poi_list(self):
        return [
            _poi(_SPRING_EN, verified=True, qid=_QID),
            _poi(_SPRING_EN_ALT, verified=True, qid=_QID),
            _poi("Main Exhibition Hall", verified=True, _stop_kind="collection_area"),
            _poi("Historic Villa Building", verified=True, _stop_kind="building"),
            _poi("Sculpture Garden", verified=True, _stop_kind="collection_area"),
        ]

    def test_word_order_spring_gardens_collapse(self):
        res = idd.final_identity_gate(self._poi_list(), needed_stops=5)
        names = [p["name"] for p in res.poi_list]
        spring = [n for n in names if "Spring Garden" in n]
        self.assertEqual(len(spring), 1, f"one Spring Garden only, got {spring}")

    def test_area_stops_survive(self):
        res = idd.final_identity_gate(self._poi_list(), needed_stops=5)
        names = [p["name"] for p in res.poi_list]
        for area in ("Main Exhibition Hall", "Historic Villa Building",
                     "Sculpture Garden"):
            self.assertIn(area, names, f"area stop {area!r} must survive")


class TestTriggerQidStampBridgesGloss(unittest.TestCase):
    """The exact-label QID stamp is the bridge the token sets could not make:
    'Center' vs 'Central' in the gloss would defeat a token match, but the
    highlights stop is literally named the work's label_local, so it is stamped
    with the QID and collapses regardless of the gloss."""

    def test_center_vs_central_still_collapses(self):
        poi = [
            _poi(_SPRING_EN, verified=True),
            _poi(_SPRING_VN, verified=True,
                 title_local=_SPRING_VN, title_en=_SPRING_GLOSS),
        ]
        # Prove the gloss token sets really differ (Center vs Central).
        self.assertNotEqual(idd.norm_set(_SPRING_GLOSS), idd.norm_set(_SPRING_EN),
                            "fixture must exercise the Center/Central mismatch")
        res = idd.final_identity_gate(poi, needed_stops=2,
                                      evidence_log=_evidence_log_670())
        self.assertEqual(len(res.poi_list), 1,
                         "QID stamp must collapse despite the gloss mismatch")

    def test_qid_to_labels_map_also_bridges(self):
        # The venue QID→labels map is an alternative source of the exact label.
        qid_to_labels = {_QID: {"label_local": _SPRING_VN, "label_en": _SPRING_EN,
                                "aliases": []}}
        poi = [_poi(_SPRING_EN, verified=True, qid=_QID),
               _poi(_SPRING_VN, verified=True)]
        res = idd.final_identity_gate(poi, needed_stops=2,
                                      qid_to_labels=qid_to_labels)
        self.assertEqual(len(res.poi_list), 1)

    def test_qid_to_labels_bridges_with_empty_per_stop_evidence(self):
        # The live-run failure mode: the per-stop evidence entries carry NO
        # sparql_labels (and no QID), but the venue QID→labels map does. Both
        # Spring Garden surface forms must still collapse — the gate stamps the
        # QID onto EACH by exact label match against the venue map.
        qid_to_labels = {_QID: {"label_local": _SPRING_VN, "label_en": _SPRING_EN,
                                "aliases": [_SPRING_EN_ALT]}}
        poi = [
            _poi(_SPRING_EN, verified=True),
            _poi(_SPRING_VN, verified=True, title_local=_SPRING_VN,
                 title_en=_SPRING_GLOSS),  # gloss "Center" ≠ SPARQL "Central"
            _poi("Thanh niên Thành đồng", verified=True),
        ]
        res = idd.final_identity_gate(
            poi, needed_stops=3, qid_to_labels=qid_to_labels, evidence_log={})
        self.assertEqual(res.stamped_qids, 2,
                         "both Spring Garden forms stamped from the venue map")
        self.assertEqual(len(res.poi_list), 2, "collapsed despite empty evidence")


class TestBilingualHeader(unittest.TestCase):
    """Ticket point 3: an English tour shows '<local> (<English>)', local first,
    one header per work; a mono-lingual work is unchanged."""

    def test_local_first_english_in_parens(self):
        c = _poi(_SPRING_VN, title_local=_SPRING_VN, title_en=_SPRING_EN)
        self.assertEqual(idd.bilingual_display_title(c),
                         f"{_SPRING_VN} ({_SPRING_EN})")

    def test_missing_side_filled_from_qid_labels(self):
        c = _poi(_SPRING_EN, qid=_QID)
        qlab = {_QID: {"local": _SPRING_VN, "en": _SPRING_EN}}
        self.assertEqual(idd.bilingual_display_title(c, qlab),
                         f"{_SPRING_VN} ({_SPRING_EN})")

    def test_monolingual_work_unchanged(self):
        self.assertEqual(idd.bilingual_display_title(_poi("Em Thúy")), "Em Thúy")

    def test_gate_sets_display_title(self):
        res = idd.final_identity_gate(
            [_poi(_SPRING_VN, title_local=_SPRING_VN, title_en=_SPRING_EN,
                  verified=True),
             _poi("Em Thúy", verified=True)],
            needed_stops=2, set_bilingual_titles=True)
        by_name = {p["name"]: p for p in res.poi_list}
        self.assertEqual(by_name[_SPRING_VN]["display_title"],
                         f"{_SPRING_VN} ({_SPRING_EN})")
        self.assertEqual(by_name["Em Thúy"]["display_title"], "Em Thúy")

    def test_never_two_headers_for_one_work(self):
        # After collapse, only one Spring Garden survives → only one header.
        res = idd.final_identity_gate(
            [_poi(_SPRING_EN, verified=True),
             _poi(_SPRING_VN, verified=True, title_local=_SPRING_VN,
                  title_en=_SPRING_GLOSS)],
            needed_stops=2, evidence_log=_evidence_log_670(),
            set_bilingual_titles=True)
        headers = [p.get("display_title") for p in res.poi_list]
        spring_headers = [h for h in headers if h and ("Spring Garden" in h or "xuân" in h)]
        self.assertEqual(len(spring_headers), 1,
                         f"one header per work, got {spring_headers}")


class TestRegression(unittest.TestCase):
    """Distinct works preserved; QID conflict never merged; clean list is a
    no-op; refill prefers works and uses area stops only as a last resort."""

    def test_qid_conflict_never_merged(self):
        poi = [_poi("Work A", qid="Q1", verified=True),
               _poi("Work B", qid="Q2", verified=True)]
        res = idd.final_identity_gate(poi, needed_stops=2)
        self.assertEqual(len(res.poi_list), 2, "different QIDs are distinct works")

    def test_distinct_works_preserved(self):
        poi = [_poi("Em Thúy", verified=True),
               _poi("Thanh niên Thành đồng", verified=True),
               _poi("Bóng xế tà", verified=True)]
        res = idd.final_identity_gate(poi, needed_stops=3)
        self.assertEqual(len(res.poi_list), 3)
        self.assertEqual(len(res.collapses), 0)

    def test_clean_list_is_noop(self):
        poi = [_poi("A", verified=True), _poi("B", verified=True)]
        res = idd.final_identity_gate(poi, needed_stops=2)
        self.assertEqual([p["name"] for p in res.poi_list], ["A", "B"])
        self.assertEqual(res.stamped_qids, 0)

    def test_refill_prefers_work_over_area_stop(self):
        poi = [_poi(_SPRING_EN, qid=_QID, verified=True),
               _poi(_SPRING_VN, qid=_QID, verified=True),
               _poi("Keep 1", verified=True)]
        reserve = [_poi("Area Hall", verified=True, _stop_kind="collection_area"),
                   _poi("Real Work", verified=True)]
        res = idd.final_identity_gate(poi, needed_stops=3, reserve_pool=reserve)
        names = [p["name"] for p in res.poi_list]
        self.assertIn("Real Work", names, "a work is preferred for the freed slot")
        self.assertNotIn("Area Hall", names, "area stop not used when a work exists")

    def test_refill_uses_area_stop_as_last_resort(self):
        poi = [_poi(_SPRING_EN, qid=_QID, verified=True),
               _poi(_SPRING_VN, qid=_QID, verified=True),
               _poi("Keep 1", verified=True)]
        reserve = [_poi("Area Hall", verified=True, _stop_kind="collection_area")]
        res = idd.final_identity_gate(poi, needed_stops=3, reserve_pool=reserve)
        self.assertIn("Area Hall", [p["name"] for p in res.poi_list],
                      "area stop fills the slot when no work remains")

    def test_no_refill_when_no_needed_stops(self):
        poi = [_poi(_SPRING_EN, qid=_QID, verified=True),
               _poi(_SPRING_VN, qid=_QID, verified=True)]
        res = idd.final_identity_gate(poi, reserve_pool=[_poi("Em Thúy")])
        self.assertEqual(len(res.poi_list), 1, "no refill without needed_stops")
        self.assertEqual(res.refilled, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
