"""[LOCAL-528] Date-vs-part anachronism — a story cannot predate the part it sits on.

The critic on LOGAN_1 stop 3: a jetbridge is a boarding bridge attached to a gate,
and the stop said Lindbergh "touched down… on the tarmac just beyond the bridge."
Jet bridges did not exist in the 1920s (first operational 1958–59). LOGAN_2 stop 3
had the same shape — a 1632 land grant and Fort Winthrop assigned to a boarding
bridge. D571's venue-parts problem in reverse: the parts were chosen correctly,
then filled with material belonging to the venue as a whole.

The fix lives in `venue_parts.distribute_lore`: a part has an earliest possible
year, and a dated fact older than that year is not placed on it. It is rehomed to a
part that CAN hold it, or dropped and recorded — never forced onto the wrong part.

These tests are built from the TWO REAL LOGAN stops, quoted from the round-7 tour
files in TOURS_FOR_REVIEW/round7/ (verified 2026-09-23), plus the general case the
acceptance criteria require: a 1632 grant cannot sit on a 1970s concourse either.

Deterministic and offline — the kind-floor table needs no network, which is the
point: the round-8 regeneration proved the defect survives on the current tree, and
Gemini is returning 402, so the check must not depend on a grounded call.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import venue_parts as vp


# ── Real material, quoted from the round-7 LOGAN tour files ──────────────────
# LOGAN_1 stop 3 (Jetbridge): the 1927 Lindbergh landing.
LINDBERGH_1927 = (
    "In 1927, aviation pioneer Charles Lindbergh landed the Spirit of St. Louis "
    "at East Boston Airport, which would eventually evolve into Logan Airport."
)
# The Beatles arrived in 1964 — AFTER the jetbridge floor, so it is NOT an
# anachronism and must be allowed to stay.
BEATLES_1964 = (
    "In 1964, The Beatles arrived at Boston Logan during their first tour of the "
    "United States, greeted by throngs of adoring fans."
)
# The same LOGAN stop states this, correctly — the tour already holds the number
# that condemns the 1927 claim.
MASSPORT_1959 = (
    "The Massachusetts Port Authority, established in 1959, operates Logan Airport."
)
# LOGAN_2 stop 3 (Jetbridge): the 1632 land grant and Fort Winthrop.
LAND_GRANT_1632 = (
    "The land was granted to Massachusetts Bay Colony Governor John Winthrop in "
    "1632, a 70-acre island once home to apple orchards and Fort Winthrop."
)
# A fact that truly belongs to a control tower (post-1930) — the era of air traffic
# control — so it can hold the aviation dates the jetbridge cannot.
TOWER_1922 = (
    "In 1922, Governor Channing H. Cox authorized construction of an airfield on "
    "East Boston's tidal flats, with $35,000 for runway preparation."
)


def _chain_from(*facts):
    """Wrap raw fact sentences into the chain shape distribute_lore consumes.

    chain_to_facts extracts sentences that carry a date or a name and end in
    terminal punctuation, so these read as real chain output.
    """
    return {"visitors": {"text": " ".join(facts),
                         "sources": ["https://example.org/logan"]}}


def _all_facts(lore, stop):
    return [f["fact"] for f in lore.get(stop, [])]


def _flat(lore):
    out = []
    for stop, items in lore.items():
        if stop.startswith("_"):
            continue
        out += [f["fact"] for f in items]
    return out


# ── The helpers ──────────────────────────────────────────────────────────────
class TestEarliestYearKnowledge:
    def test_jetbridge_kinds_floor_at_1958(self):
        for name in ("Jetbridge", "Jet Bridge", "Airport Boarding Bridge",
                     "Passenger Boarding Bridge", "Jetway"):
            assert vp.part_kind_earliest_year(name) == 1958, name
        print("  ✅ every jetbridge synonym floors at 1958")

    def test_a_nave_or_altar_has_no_floor(self):
        assert vp.part_kind_earliest_year("Nave") is None
        assert vp.part_kind_earliest_year("Altar") is None
        assert vp.part_kind_earliest_year("Terminal A") is None
        print("  ✅ floorless parts are unconstrained")

    def test_instance_year_overrides_a_lower_kind_floor(self):
        # A concourse (no kind floor) that a source dates to 1975.
        assert vp.part_earliest_year("Concourse", {"Concourse": 1975}) == 1975
        # Kind floor and a LATER instance year -> the later wins.
        assert vp.part_earliest_year("Jetbridge", {"Jetbridge": 2005}) == 2005
        # Kind floor and an EARLIER instance year -> the kind floor still holds.
        assert vp.part_earliest_year("Jetbridge", {"Jetbridge": 1940}) == 1958
        print("  ✅ part_earliest_year takes the later of kind-floor and instance-year")

    def test_fact_year_is_the_earliest_named(self):
        assert vp.fact_earliest_year(LINDBERGH_1927) == 1927
        assert vp.fact_earliest_year("rebuilt in 1973 after the 1927 landing") == 1927
        assert vp.fact_earliest_year("a boarding bridge shelters passengers") is None
        print("  ✅ fact_earliest_year returns the earliest year, None when undated")

    def test_predates_is_positive_knowledge_only(self):
        # Year + floor, year older -> predates.
        assert vp.fact_predates_part(LINDBERGH_1927, "Jetbridge") is True
        # Year + floor, year newer -> fits.
        assert vp.fact_predates_part(BEATLES_1964, "Jetbridge") is False
        # Year but NO floor -> fits (D577: never drop on absence).
        assert vp.fact_predates_part(LINDBERGH_1927, "Nave") is False
        # Floor but NO year -> fits.
        assert vp.fact_predates_part("a boarding bridge", "Jetbridge") is False
        print("  ✅ predates fires only on a year older than a known floor")


# ── The two real LOGAN stops ─────────────────────────────────────────────────
class TestLogan1JetbridgeLindbergh:
    """LOGAN_1 stop 3: 1927 Lindbergh must not sit on the jetbridge."""

    def test_1927_is_refused_at_the_jetbridge(self):
        stops = ["Jetbridge", "Control Tower"]
        chain = _chain_from(LINDBERGH_1927, BEATLES_1964, MASSPORT_1959)
        lore = vp.distribute_lore(stops, placed=[], chain=chain)

        jet = " ".join(_all_facts(lore, "Jetbridge"))
        assert "1927" not in jet, f"1927 Lindbergh landed on the jetbridge: {jet!r}"
        assert "Lindbergh" not in jet, f"Lindbergh anachronism on jetbridge: {jet!r}"
        print("  ✅ the 1927 Lindbergh landing is kept off the jetbridge")

    def test_the_1959_fact_the_tour_already_holds_is_allowed(self):
        stops = ["Jetbridge", "Control Tower"]
        chain = _chain_from(MASSPORT_1959)
        lore = vp.distribute_lore(stops, placed=[], chain=chain)
        # 1959 >= 1958 floor, so it may sit on the jetbridge.
        assert not vp.fact_predates_part(MASSPORT_1959, "Jetbridge")
        assert "1959" in " ".join(_flat(lore)), "the 1959 fact must survive somewhere"
        print("  ✅ the correct 1959 date the tour already states is allowed")

    def test_a_post_1958_jetbridge_fact_survives(self):
        stops = ["Jetbridge", "Control Tower"]
        chain = _chain_from(BEATLES_1964)
        lore = vp.distribute_lore(stops, placed=[], chain=chain)
        assert "1964" in " ".join(_flat(lore)), "the 1964 Beatles arrival must survive"
        print("  ✅ the 1964 Beatles arrival (after the floor) is kept")

    def test_placement_reason_that_is_an_anachronism_is_refused(self):
        # place_stories_in_building put the 1927 story ON the jetbridge — that
        # binding IS the bug, so distribute_lore must refuse it and record it.
        stops = ["Jetbridge", "Control Tower"]
        placed = [{"part": "Jetbridge", "why": LINDBERGH_1927}]
        lore = vp.distribute_lore(stops, placed=placed, chain=_chain_from())
        jet = " ".join(_all_facts(lore, "Jetbridge"))
        assert "1927" not in jet, f"anachronistic placement reason survived: {jet!r}"
        assert "_anachronistic" in lore, "the refusal must be recorded"
        assert any(d.get("part") == "Jetbridge" and d.get("fact_year") == 1927
                   for d in lore["_anachronistic"]), lore["_anachronistic"]
        print("  ✅ an anachronistic placement reason is refused and logged")


class TestLogan2JetbridgeLandGrant:
    """LOGAN_2 stop 3: a 1632 land grant must not sit on the jetbridge."""

    def test_1632_is_refused_at_the_jetbridge(self):
        stops = ["Jetbridge", "Control Tower"]
        chain = _chain_from(LAND_GRANT_1632, TOWER_1922)
        lore = vp.distribute_lore(stops, placed=[], chain=chain)
        jet = " ".join(_all_facts(lore, "Jetbridge"))
        assert "1632" not in jet, f"1632 land grant landed on the jetbridge: {jet!r}"
        assert "Winthrop" not in jet, f"Fort Winthrop anachronism on jetbridge: {jet!r}"
        print("  ✅ the 1632 land grant is kept off the jetbridge")

    def test_1632_is_dropped_and_recorded_when_no_part_can_hold_it(self):
        # Both parts have floors newer than 1632 (jetbridge 1958, control tower
        # 1930), so nowhere can host it — it must be dropped, not forced.
        stops = ["Jetbridge", "Control Tower"]
        chain = _chain_from(LAND_GRANT_1632)
        lore = vp.distribute_lore(stops, placed=[], chain=chain)
        assert "1632" not in " ".join(_flat(lore)), "1632 grant was forced onto a part"
        assert "_anachronistic" in lore and lore["_anachronistic"], \
            "a fact no part can host must be recorded"
        assert any(d.get("fact_year") == 1632 for d in lore["_anachronistic"])
        print("  ✅ a fact older than every part's floor is dropped and recorded")

    def test_1632_survives_when_a_floorless_part_exists(self):
        # Add "Terminal A" (no floor) — the grant CAN sit there, so it is rehomed,
        # not dropped. The check removes anachronisms; it does not delete history.
        stops = ["Jetbridge", "Control Tower", "Terminal A"]
        chain = _chain_from(LAND_GRANT_1632)
        lore = vp.distribute_lore(stops, placed=[], chain=chain)
        assert "1632" not in " ".join(_all_facts(lore, "Jetbridge"))
        assert "1632" in " ".join(_flat(lore)), "the grant should be rehomed, not lost"
        print("  ✅ the 1632 grant is rehomed to a part that can hold it")


# ── The general case the acceptance criteria require ─────────────────────────
class TestGeneralNotJustJetbridges:
    """'a 1632 land grant cannot sit on a 1970s concourse any more than a jetbridge'."""

    def test_1632_refused_on_a_1970s_concourse_instance(self):
        stops = ["Concourse", "Nave"]  # Concourse dated by a source to 1975
        built = {"Concourse": 1975}
        chain = _chain_from(LAND_GRANT_1632)
        lore = vp.distribute_lore(stops, placed=[], chain=chain, part_built_years=built)
        conc = " ".join(_all_facts(lore, "Concourse"))
        assert "1632" not in conc, f"1632 grant sat on a 1970s concourse: {conc!r}"
        # Nave has no floor, so the grant is rehomed there rather than dropped.
        assert "1632" in " ".join(_flat(lore))
        print("  ✅ a 1970s concourse refuses a 1632 grant (general instance-year case)")

    def test_control_tower_kind_floor_refuses_1927(self):
        # A control tower could not exist before ~1930, so even it cannot host 1927.
        assert vp.fact_predates_part(LINDBERGH_1927, "Control Tower") is True
        stops = ["Control Tower", "Nave"]
        lore = vp.distribute_lore(stops, placed=[], chain=_chain_from(LINDBERGH_1927))
        assert "1927" not in " ".join(_all_facts(lore, "Control Tower"))
        print("  ✅ the control-tower kind floor (1930) also refuses a 1927 fact")

    def test_a_floorless_venue_is_untouched(self):
        # A church of naves and altars has no dated floors, so nothing is refused —
        # the check must not disturb venues it knows nothing about.
        stops = ["Nave", "Altar", "Stained Glass Windows"]
        chain = _chain_from(
            "In 1881, James Murphy eliminated the apse windows for an oil painting.",
            "On June 25, 2023, three parishioners were killed in a break-in.")
        lore = vp.distribute_lore(stops, placed=[], chain=chain)
        assert "_anachronistic" not in lore, "a floorless venue must lose nothing"
        assert len(_flat(lore)) >= 2, "both dated church facts should be placed"
        print("  ✅ a venue of floorless parts is left entirely untouched")


def run_all():
    classes = [TestEarliestYearKnowledge, TestLogan1JetbridgeLindbergh,
               TestLogan2JetbridgeLandGrant, TestGeneralNotJustJetbridges]
    total = passed = failed = 0
    for cls in classes:
        print(f"\n{'=' * 64}\n  {cls.__name__}\n{'=' * 64}")
        inst = cls()
        for name in sorted(dir(inst)):
            if not name.startswith("test_"):
                continue
            total += 1
            try:
                getattr(inst, name)()
                passed += 1
            except AssertionError as e:
                failed += 1
                print(f"  ❌ {name}: {e}")
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"  ❌ {name}: EXCEPTION: {type(e).__name__}: {e}")
    print(f"\n{'=' * 64}\n  RESULTS: {passed}/{total} passed, {failed} failed\n{'=' * 64}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_all())
