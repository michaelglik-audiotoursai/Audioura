"""test_local662b_bounce.py — LOCAL-662B acceptance (unit level, offline).

The LEAD bounced the Boston walking v9 run for two things the v9 fixes did not
address:

  DEFECT 1 — the stop-existence gate DROPPED REAL places. "Verified" meant
    "named in the stop corpus" (a COVERAGE test). A city walking tour has no
    venue_corpus row, so a real-but-unscraped landmark (Parkman Bandstand, the
    Boston Athenaeum) classified 'unknown' and was dropped though it plainly
    exists. For a walking stop, existence = a Wikidata item (label/alias +
    P625 near the toured city) OR an OSM named feature. Only a stop that fails
    BOTH is dropped. "The State House Park" must still fail. A Wikimedia/OSM
    search error is UNKNOWN → keep (LOCAL-661).

  DEFECT 2a — the "4 of 5" honest shortfall was undone by a back-fill. GEO-CHECK
    logged "delivering 4 of 5", yet the delivered tour (id 648) shipped Stop 5
    "John F." (the JFK Library, ≈4.3 km away). The D558 replenish_to_count block
    runs AFTER GEO-CHECK and, on a city walking tour, had no distance check. It
    must obey the SAME walking-distance limit (LOCAL-658) or deliver the shortfall.

  DEFECT 2b — the "John F." header. The replenishment proposer returned a
    truncation artifact ("John F." = first name + a bare trailing initial); the
    narration LLM expanded it, but the header/directions render poi['name']
    verbatim → "Stop 5: John F.". The LOCAL-658 initials fix in _is_name_corrupted
    neutralized trailing initials so aggressively that this truncation passed as
    clean. A name whose LAST token is a lone letter is now corrupt, while a real
    initial-bearing name (ending on a surname/word) stays clean.

The _is_name_corrupted and walking-distance tests are deterministic (no network).
The existence-verdict tests hit live Wikidata/Nominatim (FREE, not a paid API) and
are gated behind LOCAL662B_LIVE=1 so CI stays offline; run them with:
    LOCAL662B_LIVE=1 python3 -m pytest tests/test_local662b_bounce.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generate_tour_text as gtt
import stop_existence_gate as seg


BOSTON_VENUE = ("Walking tour in Boston dedicated to Massachusetts politics "
                "and current affairs, Boston, MA")


# ── DEFECT 2b: _is_name_corrupted flags a trailing-initial truncation ───────
class TestNameTruncationGuard(unittest.TestCase):
    """A bare truncation ending in a lone initial is corrupt; a real name whose
    initial is followed by a surname/word is clean (the LOCAL-658 contract)."""

    # Truncation artifacts — the header "Stop 5: John F." shape.
    CORRUPT = [
        "John F.",
        "John F",
        "John F. ",
        "Mary B.",
        "W. E. B.",          # all initials, nothing after → truncation
    ]
    # Real names that carry initials but END on a real word — must stay clean.
    CLEAN = [
        "John F. Kennedy Presidential Library and Museum",
        "I. M. Pei",
        "W. E. B. Du Bois",
        "J. P. Morgan",
        "Faneuil Hall",
        "Massachusetts State House",
        "Old State House",
        "Boston City Hall",
        "The Boston Athenaeum",
        "Parkman Bandstand",
    ]

    def test_truncations_are_corrupt(self):
        for n in self.CORRUPT:
            self.assertTrue(gtt._is_name_corrupted(n),
                            f"{n!r} is a truncation and must be flagged corrupt")

    def test_real_names_are_clean(self):
        for n in self.CLEAN:
            self.assertFalse(gtt._is_name_corrupted(n),
                             f"{n!r} is a real name and must NOT be flagged corrupt")

    def test_jfk_full_name_survives_but_abbrev_does_not(self):
        # The exact pair from tour 648.
        self.assertFalse(gtt._is_name_corrupted(
            "John F. Kennedy Presidential Library and Museum"))
        self.assertTrue(gtt._is_name_corrupted("John F."))


# ── DEFECT 2a: the walking-distance limit on the post-GEO-CHECK back-fill ────
class TestWalkingDistancePrune(unittest.TestCase):
    """The prune in the D558 replenishment uses the module helpers _haversine_km,
    _parse_coords, _compute_route_order and the LOCAL-658 limits. These tests
    exercise exactly those building blocks on real Boston coordinates, proving the
    refusal decision the prune makes: downtown originals pass; the JFK Library
    (4.3 km) is refused."""

    # Real downtown-Boston coordinates (all within the 1.75 km per-leg limit).
    ORIGINALS = [
        {"name": "Massachusetts State House", "coordinates": "42.3586, -71.0639"},
        {"name": "Boston City Hall",          "coordinates": "42.3603, -71.0580"},
        {"name": "Faneuil Hall",              "coordinates": "42.3600, -71.0563"},
        {"name": "Old State House",           "coordinates": "42.3588, -71.0575"},
    ]
    # JFK Presidential Library, Columbia Point, Dorchester — ≈4.3 km from downtown.
    JFK = {"name": "John F. Kennedy Presidential Library and Museum",
           "coordinates": "42.3201, -71.0523"}

    def _route_ok(self, cand_list, transport_mode="on_foot"):
        """Mirror of the inline _wl_route_ok prune decision (LOCAL-662B)."""
        total_limit = gtt._TRANSPORT_TOTAL_HARD_KM.get(
            transport_mode, gtt.WALKING_TOTAL_HARD_KM)
        ordered = cand_list
        if len(cand_list) >= 3:
            ordered = gtt._compute_route_order(list(cand_list))
        pts = [(p, gtt._parse_coords(p.get("coordinates", ""))) for p in ordered]
        pts = [(p, c) for p, c in pts if c]
        if len(pts) < 2:
            return True, 0.0, 0.0
        legs = [gtt._haversine_km(pts[k][1], pts[k + 1][1])
                for k in range(len(pts) - 1)]
        tot = sum(legs)
        mx = max(legs) if legs else 0.0
        if transport_mode == "on_foot" and mx > gtt.WALKING_LEG_HARD_KM:
            return False, mx, tot
        if tot > total_limit:
            return False, mx, tot
        return True, mx, tot

    def test_downtown_originals_pass(self):
        ok, mx, tot = self._route_ok(self.ORIGINALS)
        self.assertTrue(ok, f"downtown originals must pass (max leg {mx:.2f} km)")
        self.assertLessEqual(mx, gtt.WALKING_LEG_HARD_KM)

    def test_far_jfk_replacement_refused(self):
        ok, mx, tot = self._route_ok(self.ORIGINALS + [self.JFK])
        self.assertFalse(ok, "adding the 4.3 km JFK Library must break the limit")
        self.assertGreater(mx, gtt.WALKING_LEG_HARD_KM,
                           f"the JFK leg ({mx:.2f} km) exceeds "
                           f"{gtt.WALKING_LEG_HARD_KM} km")

    def test_jfk_leg_is_about_4_3_km(self):
        d = gtt._haversine_km(gtt._parse_coords(self.ORIGINALS[-1]["coordinates"]),
                              gtt._parse_coords(self.JFK["coordinates"]))
        # Straight-line lower bound on the walking distance.
        self.assertGreater(d, 4.0)
        self.assertLess(d, 5.0)

    def test_replenish_to_count_rejects_truncated_name(self):
        """replenish_to_count must reject a truncated proposed name ('John F.')
        at proposal, so it never becomes a stop."""
        poi_list = [{"name": "Faneuil Hall"}, {"name": "Old State House"}]

        def _propose(need, seen):
            # The proposer returns a truncation artifact + one real place.
            return [{"name": "John F."}, {"name": "Boston Public Library"}]

        def _make(name):
            return {"name": name, "coordinates": ""}

        added, rejected, rounds = gtt.replenish_to_count(
            poi_list, want=3, scope="", headers={},
            propose=_propose, make_poi=_make, max_rounds=1)
        names = [p["name"] for p in poi_list]
        self.assertNotIn("John F.", names,
                         "the truncated 'John F.' must be rejected, never added")
        self.assertGreaterEqual(rejected, 1)


# ── DEFECT 1: live Wikidata/OSM existence verdicts (FREE; network-gated) ─────
@unittest.skipUnless(os.environ.get("LOCAL662B_LIVE") == "1",
                     "set LOCAL662B_LIVE=1 to run live Wikidata/Nominatim checks")
class TestWalkingExistenceVerdictsLive(unittest.TestCase):
    """The 7 candidate stops from the LEAD's run. Real landmarks verify; the one
    non-place fails. These hit live Wikidata + Nominatim (free, throttled)."""

    def _verdict(self, name):
        try:
            ok, ev = seg._check_walking_stop_existence(name, BOSTON_VENUE)
            return ok, ev, None
        except RuntimeError as e:  # UNKNOWN — kept, not dropped
            return None, "", str(e)

    def test_real_landmarks_verify(self):
        for name in ("Faneuil Hall", "Massachusetts State House",
                     "Old State House", "Boston City Hall",
                     "Parkman Bandstand", "The Boston Athenaeum"):
            ok, ev, err = self._verdict(name)
            # VERIFIED, or UNKNOWN on a search failure (never a hard False).
            self.assertNotEqual(ok, False,
                                f"{name!r} is a real Boston landmark — must not be "
                                f"a hard-False drop (verdict={ok}, ev={ev}, err={err})")

    def test_non_place_fails(self):
        ok, ev, err = self._verdict("The State House Park")
        if err is not None:
            self.skipTest(f"search failed (UNKNOWN) for the negative case: {err}")
        self.assertFalse(ok, "'The State House Park' is not a real distinct place "
                             "and must fail the existence check")


if __name__ == "__main__":
    unittest.main(verbosity=2)
