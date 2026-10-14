#!/usr/bin/env python3
"""[LOCAL-577] A museum tour must deliver the number of stops the listener asked
for whenever that many real stops exist — even when D1v2 drops one on a
canonical-title mismatch and R4 cannot find a verified replacement.

Field defect (GCloud_Storied, Preview v4, 2026-10-04, job b5982123, tour 431):

    request : Palais Lascaris, Nice, museum, 4 stops
    delivered: 3 stops
    log      :
      [EXISTENCE-GATE] LOG_ONLY - 4/4 stops verified (100%), 0 would be dropped
      [R4] Replenishment round 1/3: need 3 more, asking for 8
      [D1v2] DROPPED 'The Adoration of the Magi' - no canonical title match

Four real stops existed and passed the existence gate. D1v2 then dropped one on
a *canonical-title* mismatch — not non-existence, not a wrong venue. R4 ran but
its freshly generated candidates also failed the canonical match, so the count
was never restored. D592: a thin stop is acceptable, a MISSING one is not.

ROOT CAUSE (generate_tour_text.py):
  - D1v2 records the drop as evidence_log[name] = {"status": "DROPPED",
    "reason": "no canonical match"} (line ~4421) and leaves the real POI only in
    _pre_d1v2_candidates.
  - Every fill path (UNIFIED-FILL, POST-R4-FILL) marks fills verified=False.
  - The LOCAL-16 GATE then strips every verified=False stop for museum tours
    UNLESS it carries user_explicit — so the real, existence-passed stop that
    D1v2 dropped on a title technicality is deleted, and the tour ends at 3.

THE FIX (exercised here through the REAL module, D277 — no mirrors):
  - _title_mismatch_refill_pool() re-admits ONLY the candidates D1v2 dropped for
    a title mismatch ("no canonical match"); never REJECTED (wrong venue), never
    theme/cycle words, never already-present stops. Each comes back verified=False
    and tagged _title_mismatch_refill so the narration hedges (D592), exactly as
    user_explicit stops are restored for LOCAL-547.
  - _local16_gate_survivors() exempts a _title_mismatch_refill stop from the
    verified-only strip the same way it already exempts user_explicit.

RED ON STORIED: neither helper exists on 08ee199, so the import below raises
AttributeError and this file ERRORS there. GREEN after the fix.

Run:  python3 tests/test_local577_museum_refill.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generate_tour_text as gtt  # noqa: E402


def _poi(name, address="", verified=True):
    p = {"name": name, "address": address}
    if not verified:
        p["verified"] = False
    return p


# ── The recorded Palais Lascaris shape: four candidates pass existence ──
# D1v2 verifies three and drops the fourth ("The Adoration of the Magi") for a
# canonical-title mismatch only. R4's two generated candidates also fail the
# canonical match (they go to the R4-dropped pool).
PALAIS_CANDIDATES = [
    _poi("The Annunciation"),
    _poi("The Holy Family"),
    _poi("Baroque Ceiling Frescoes"),
    _poi("The Adoration of the Magi"),   # real stop, dropped on title mismatch
]

# evidence_log exactly as D1v2 writes it for this shape.
PALAIS_EVIDENCE = {
    "The Annunciation": {"status": "VERIFIED", "canonical_title": "The Annunciation", "snippet": "..."},
    "The Holy Family": {"status": "VERIFIED", "canonical_title": "The Holy Family", "snippet": "..."},
    "Baroque Ceiling Frescoes": {"status": "VERIFIED", "canonical_title": "Baroque Ceiling Frescoes", "snippet": "..."},
    # The one real stop D1v2 dropped on a canonical-title technicality:
    "The Adoration of the Magi": {"status": "DROPPED", "reason": "no canonical match"},
    # R4-generated candidates that also failed the canonical match:
    "R4 Guess One": {"status": "DROPPED", "reason": "no canonical match"},
    "R4 Guess Two": {"status": "DROPPED", "reason": "no canonical match"},
}

# After D1v2 the verified-only list is the three that matched.
VERIFIED_AFTER_D1V2 = [
    _poi("The Annunciation"),
    _poi("The Holy Family"),
    _poi("Baroque Ceiling Frescoes"),
]


class TestStoriedReproducesTheDrop(unittest.TestCase):
    """Document the base-commit failure: with only the verified three and the
    existing gate, a museum tour of 4 ends at 3. This is the state the fix must
    change (kept as an explicit statement of the defect)."""

    def test_three_of_four_without_refill(self):
        # The gate, with no title-mismatch refill, keeps only the verified three.
        survivors, removed = gtt._local16_gate_survivors(
            list(VERIFIED_AFTER_D1V2), PALAIS_EVIDENCE)
        self.assertEqual(len(survivors), 3,
                         "verified-only museum list is three — the recorded shortfall")


class TestTitleMismatchRefillPool(unittest.TestCase):
    """[LOCAL-577] Step: re-admit ONLY title-mismatch drops, nothing else."""

    def test_adoration_is_offered_as_refill(self):
        pool = gtt._title_mismatch_refill_pool(
            PALAIS_EVIDENCE, PALAIS_CANDIDATES, VERIFIED_AFTER_D1V2,
            venue_name="Musée du Palais Lascaris")
        names = [p["name"] for p in pool]
        self.assertIn("The Adoration of the Magi", names,
                      "the stop D1v2 dropped on a title mismatch must be offered back")

    def test_refill_is_unverified_and_hedged(self):
        pool = gtt._title_mismatch_refill_pool(
            PALAIS_EVIDENCE, PALAIS_CANDIDATES, VERIFIED_AFTER_D1V2,
            venue_name="Musée du Palais Lascaris")
        for p in pool:
            self.assertIs(p.get("verified"), False,
                          "a refilled stop is explicitly unverified so narration hedges (D592)")
            self.assertTrue(p.get("_title_mismatch_refill"),
                            "a refilled stop carries the gate-exemption tag")

    def test_rejected_is_never_refilled(self):
        """A wrong-venue REJECTED candidate must NEVER be re-admitted (D1)."""
        ev = dict(PALAIS_EVIDENCE)
        ev["Mona Lisa"] = {"status": "REJECTED", "reason": "located at louvre"}
        cands = PALAIS_CANDIDATES + [_poi("Mona Lisa")]
        pool = gtt._title_mismatch_refill_pool(
            ev, cands, VERIFIED_AFTER_D1V2, venue_name="Musée du Palais Lascaris")
        self.assertNotIn("Mona Lisa", [p["name"] for p in pool],
                         "REJECTED (wrong-venue) candidates are not an acceptable refill")

    def test_theme_and_cycle_drops_are_never_refilled(self):
        """Drops for theme/book word or cycle name are prolog material, not stops."""
        ev = dict(PALAIS_EVIDENCE)
        ev["Baroque"] = {"status": "DROPPED", "reason": "theme word: 'baroque'"}
        ev["The Lascaris Cycle"] = {"status": "DROPPED", "reason": "cycle name"}
        cands = PALAIS_CANDIDATES + [_poi("Baroque"), _poi("The Lascaris Cycle")]
        pool = gtt._title_mismatch_refill_pool(
            ev, cands, VERIFIED_AFTER_D1V2, venue_name="Musée du Palais Lascaris")
        names = [p["name"] for p in pool]
        self.assertNotIn("Baroque", names, "theme-word drops are not stops")
        self.assertNotIn("The Lascaris Cycle", names, "cycle-name drops are not stops")

    def test_already_present_is_not_duplicated(self):
        """A stop already in the list is never offered as a refill."""
        pool = gtt._title_mismatch_refill_pool(
            PALAIS_EVIDENCE, PALAIS_CANDIDATES, VERIFIED_AFTER_D1V2,
            venue_name="Musée du Palais Lascaris")
        current = {p["name"].lower() for p in VERIFIED_AFTER_D1V2}
        for p in pool:
            self.assertNotIn(p["name"].lower(), current,
                             "a refill must not duplicate a stop already in the list")


class TestGateExemptsTheRefill(unittest.TestCase):
    """[LOCAL-577] Step: the refilled stop survives the LOCAL-16 GATE while a
    plain unverified fill still does not."""

    def test_refilled_stop_survives_the_gate(self):
        refill = gtt._title_mismatch_refill_pool(
            PALAIS_EVIDENCE, PALAIS_CANDIDATES, VERIFIED_AFTER_D1V2,
            venue_name="Musée du Palais Lascaris")
        poi_list = list(VERIFIED_AFTER_D1V2) + refill[:1]
        survivors, removed = gtt._local16_gate_survivors(poi_list, PALAIS_EVIDENCE)
        names = [p["name"] for p in survivors]
        self.assertIn("The Adoration of the Magi", names,
                      "the title-mismatch refill must survive the verified-only gate")
        self.assertEqual(len(survivors), 4,
                         "the museum tour now delivers the 4 stops the listener asked for")

    def test_plain_unverified_fill_is_still_stripped(self):
        """The gate must still strip an ordinary unverified fill (no exemption tag)."""
        poi_list = list(VERIFIED_AFTER_D1V2) + [_poi("Some Unverified Pad", verified=False)]
        survivors, removed = gtt._local16_gate_survivors(poi_list, PALAIS_EVIDENCE)
        self.assertNotIn("Some Unverified Pad", [p["name"] for p in survivors],
                         "a plain unverified pad is still removed by the gate")

    def test_end_to_end_four_of_four(self):
        """The whole chain: verified three + title-mismatch refill → gate → 4/4."""
        needed = 4 - len(VERIFIED_AFTER_D1V2)
        refill = gtt._title_mismatch_refill_pool(
            PALAIS_EVIDENCE, PALAIS_CANDIDATES, VERIFIED_AFTER_D1V2,
            venue_name="Musée du Palais Lascaris")[:needed]
        poi_list = list(VERIFIED_AFTER_D1V2) + refill
        survivors, removed = gtt._local16_gate_survivors(poi_list, PALAIS_EVIDENCE)
        self.assertEqual(len(survivors), 4,
                         "4 requested, 4 real stops exist, 4 delivered (D592: never a missing stop)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
