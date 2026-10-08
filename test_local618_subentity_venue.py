"""
LOCAL-618 #3: Venue resolution must prefer the collecting institution over a
sub-entity (a P361 part, or a building/wing/depot) with a smaller collection.

Regression: "Museum Boijmans Van Beuningen, Rotterdam" resolved to the
"Robbrecht & Daem wing" (Q134498261, 1 work) instead of the museum (Q679527),
so the D1v2 canonical filter dropped the hallucinated candidates and the tour
clean-failed.

prefer_parent_institution is pure: all I/O (P361/P31 lookup and collection size)
is injected, so these tests run offline and deterministically.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from venue_resolver import prefer_parent_institution, _MUSEUM_TYPES, _BUILDING_WING_TYPES

# Real QIDs from the Boijmans clean-fail.
BOIJMANS = "Q679527"        # Museum Boijmans Van Beuningen (the institution)
WING = "Q134498261"         # Robbrecht & Daem wing / depot (the sub-entity)

ART_MUSEUM = next(iter(_MUSEUM_TYPES & {"Q207694"})) or "Q207694"
BUILDING = next(iter(_BUILDING_WING_TYPES))


def _props_boijmans(qid):
    # The wing is P361-part-of the museum, and is typed as a building/depot.
    if qid == WING:
        return {"part_of": [BOIJMANS], "instance_of": [BUILDING]}
    if qid == BOIJMANS:
        return {"part_of": [], "instance_of": ["Q207694"]}  # art museum
    return {"part_of": [], "instance_of": []}


def _counts_boijmans(qid):
    # The institution owns the collection; the wing has essentially nothing.
    if qid == BOIJMANS:
        return (150, 40)
    if qid == WING:
        return (1, 2)
    return (0, 0)


def test_part_of_sibling_is_dropped():
    """The wing (P361 → museum, both in the set) must be dropped."""
    cands = [(WING, "Robbrecht & Daem wing"), (BOIJMANS, "Museum Boijmans Van Beuningen")]
    out = prefer_parent_institution(cands, _props_boijmans, _counts_boijmans)
    qids = [q for q, _ in out]
    assert BOIJMANS in qids, f"museum must survive, got {qids}"
    assert WING not in qids, f"wing must be dropped, got {qids}"
    assert out[0][0] == BOIJMANS, f"museum must be first, got {out}"


def test_building_only_dropped_when_institution_present():
    """Even without a P361 edge, a building-only candidate yields to a museum."""
    def props(qid):
        if qid == WING:
            return {"part_of": [], "instance_of": [BUILDING]}  # no P361 edge
        if qid == BOIJMANS:
            return {"part_of": [], "instance_of": ["Q207694"]}
        return {"part_of": [], "instance_of": []}
    cands = [(WING, "some wing"), (BOIJMANS, "Museum Boijmans Van Beuningen")]
    out = prefer_parent_institution(cands, props, _counts_boijmans)
    qids = [q for q, _ in out]
    assert qids == [BOIJMANS], f"only the museum should remain, got {qids}"


def test_larger_collection_wins_between_two_institutions():
    """Two genuine museums, neither a part: the larger collection ranks first."""
    small, big = "Q1", "Q2"
    def props(qid):
        return {"part_of": [], "instance_of": ["Q207694"]}
    def counts(qid):
        return {"Q1": (3, 1), "Q2": (90, 20)}.get(qid, (0, 0))
    out = prefer_parent_institution([(small, "small"), (big, "big")], props, counts)
    assert out[0][0] == big, f"larger collection must rank first, got {out}"


def test_dominant_collection_collapses_to_single_winner():
    """Boijmans: the museum (100 works) must WIN OUTRIGHT over the wing (1 work),
    collapsing to a single candidate so geo-disambiguation cannot re-pick the wing
    (they share coordinates). No P361 edge and no museum typing available (the live
    search returned none)."""
    museum, wing = "Q679527", "Q134498261"
    def props(qid):
        return {"part_of": [], "instance_of": []}   # as in the live Boijmans case
    def counts(qid):
        return {museum: (100, 40), wing: (1, 2)}.get(qid, (0, 0))
    out = prefer_parent_institution([(wing, "wing"), (museum, "museum")], props, counts)
    assert out == [(museum, "museum")], f"museum must win outright, got {out}"


def test_close_collections_not_collapsed():
    """Two comparable collections must both survive (collapse only on domination)."""
    def props(qid):
        return {"part_of": [], "instance_of": ["Q207694"]}
    def counts(qid):
        return {"Q1": (40, 5), "Q2": (50, 6)}.get(qid, (0, 0))
    out = prefer_parent_institution([("Q1", "a"), ("Q2", "b")], props, counts)
    assert len(out) == 2, f"comparable collections must not collapse, got {out}"
    assert out[0][0] == "Q2", "but the larger still ranks first"


def test_never_empties():
    """If every candidate is a part of every other (pathological), keep them."""
    def props(qid):
        return {"part_of": ["Qx", "Qy"], "instance_of": []}
    cands = [("Qx", "x"), ("Qy", "y")]
    out = prefer_parent_institution(cands, props, lambda q: (0, 0))
    assert out, "must never return an empty candidate list"


def test_single_candidate_passthrough():
    out = prefer_parent_institution([(BOIJMANS, "m")], _props_boijmans, _counts_boijmans)
    assert out == [(BOIJMANS, "m")]


def test_props_failure_is_tolerated():
    """A raising props_fn must not crash the collapse."""
    def props(qid):
        raise RuntimeError("network down")
    cands = [(WING, "w"), (BOIJMANS, "m")]
    out = prefer_parent_institution(cands, props, lambda q: (0, 0))
    assert len(out) == 2, "with no property signal, keep both rather than guess"


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"  [PASS] {fn.__name__}")
            passed += 1
        except Exception:
            print(f"  [FAIL] {fn.__name__}")
            traceback.print_exc()
    print(f"\n{passed}/{len(fns)} passed")
    sys.exit(0 if passed == len(fns) else 1)
