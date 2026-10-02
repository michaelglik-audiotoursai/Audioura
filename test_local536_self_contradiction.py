"""[LOCAL-536] A tour must not contradict itself.

Round 9 scored `defects: {}` on both tours and contains contradictions that need
NO knowledge of the world — only a comparison of the tour against its own other
sentences. `self_contradiction` in tour_quality.py is the check; this proves it on
the FOUR real cases, all quoted VERBATIM by reading the round-9 tour files in
TOURS_FOR_REVIEW/round9/ (never retyped — the strings below are asserted to be
present in the files, then fed to the checker, so the test cannot drift from the
evidence).

  A. attribution_conflict     LOGAN_1: Eiffel's Control Tower vs "Designed by ...
                              Kubitz & Papi, Inc. and Desmond & Lord, Inc., this tower"
  B. absent_subject           CHURCH_1: stop titled "Stained Glass Windows" whose
                              body says "In the absence of stained glass ..."
  C. epilog / orientation     LOGAN_1: the closing summary and the orientation both
                              describe a route that is not the delivered one
  D. epilog_stop_mismatch     CHURCH_1: the epilog previews "Mary Immaculate of
                              Lourdes" — a DIFFERENT church its own stop 2 distinguishes

Acceptance also requires a NEGATIVE control (a tour that credits one designer, whose
stop titles match their bodies, whose epilog names delivered stops, stays CLEAN) and
a false-positive survey over round 7 and round 8. Both are here.

Deterministic and offline: no corpus, no grounded call, no outside knowledge — that
is the whole point of self-contradiction as a defect class (D577).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tour_quality as tq

_HERE = os.path.dirname(os.path.abspath(__file__))
_R9 = os.path.join(_HERE, 'TOURS_FOR_REVIEW', 'round9')
_R7 = os.path.join(_HERE, 'TOURS_FOR_REVIEW', 'round7')
_R8 = os.path.join(_HERE, 'TOURS_FOR_REVIEW', 'round8')


def _read(*parts):
    with open(os.path.join(*parts), errors='ignore') as fh:
        return fh.read()


LOGAN_1 = _read(_R9, 'LOGAN_1.txt')
CHURCH_1 = _read(_R9, 'CHURCH_1.txt')


# ── The verbatim quotes the cases turn on, asserted to exist in the real files ──
# If the generator ever rewords these, THIS test fails loudly rather than passing
# against a string that is no longer in the evidence.
A_POSSESSIVE = "Gustave Eiffel's iconic Control Tower mark the endpoints"
A_PASSIVE = ("Designed by the Boston architectural firms Kubitz & Papi, Inc. and "
             "Desmond & Lord, Inc., this tower")
B_TITLE = "Stop 2: Stained Glass Windows"
B_ABSENCE = "In the absence of stained glass"
C_EPILOG = "This tour covered Control Tower and Terminal A Baggage Claim"
C_ORIENT = "mark the endpoints"
D_EPILOG = "Mary Immaculate of Lourdes showcases collaborative stained glass art"


def test_verbatim_quotes_are_present_in_the_real_files():
    """The cases are built from strings that actually appear in round 9."""
    for q in (A_POSSESSIVE, A_PASSIVE, C_EPILOG, C_ORIENT):
        assert q in LOGAN_1, f"LOGAN_1 no longer contains: {q!r}"
    for q in (B_TITLE, B_ABSENCE, D_EPILOG):
        assert q in CHURCH_1, f"CHURCH_1 no longer contains: {q!r}"


# ── Case A: two designers for one structure (LOGAN_1) ────────────────────────
def test_case_a_attribution_conflict():
    conflict = tq._find_attribution_conflict(LOGAN_1)
    assert conflict is not None, "the two-designer conflict must be found"
    struct, quote_a, quote_b = conflict
    assert tq._norm_structure(struct) == 'tower'
    # Both offending quotes are reported so the decision is inspectable, and each
    # is a real sentence from the tour.
    joined = quote_a + ' || ' + quote_b
    assert "Gustave Eiffel's iconic Control Tower" in joined
    assert "Kubitz & Papi" in joined or "Desmond & Lord" in joined


# ── Case B: a stop named after a thing its own text says is absent (CHURCH_1) ─
def test_case_b_absent_subject():
    found = tq._find_absent_subject(CHURCH_1)
    assert found is not None, "the absent-subject contradiction must be found"
    title, quote = found
    assert title == "Stained Glass Windows"
    # The offending sentence is the body's own admission of absence.
    assert 'absence of stained glass' in quote.lower() or \
           'not hold stained glass' in quote.lower()


# ── Case C: the orientation/closing describe a route that is not delivered ────
def test_case_c_orientation_names_a_non_stop_endpoint():
    found = tq._find_orientation_stop_mismatch(LOGAN_1)
    assert found is not None, "the orientation endpoint mismatch must be found"
    name, quote = found
    # LOGAN_1 states its endpoints twice; the second sentence names St. Mary's
    # Cathedral — which is not one of the delivered stops.
    assert 'Cathedral' in name or "Mary" in name
    assert C_ORIENT in quote


def test_case_c_delivered_stops_are_the_four_real_ones():
    titles = tq._delivered_titles(LOGAN_1)
    assert titles == ['Terminal A Main Concourse', 'Jetbridge',
                      'Control Tower', 'Terminal A Baggage Claim']


# ── Case D: the epilog adopts a different church (CHURCH_1) ───────────────────
def test_case_d_epilog_names_a_non_delivered_place():
    found = tq._find_epilog_stop_mismatch(CHURCH_1)
    assert found is not None, "the epilog must be caught naming a non-stop place"
    name, quote = found
    assert 'Mary Immaculate of Lourdes' in name
    assert D_EPILOG in quote


# ── score_tour() end to end: both round-9 tours report self_contradiction ─────
def test_score_tour_flags_both_round9_tours():
    for text, label in ((LOGAN_1, 'LOGAN_1'), (CHURCH_1, 'CHURCH_1')):
        result = tq.score_tour(text)
        assert 'self_contradiction' in result['defects'], \
            f"{label} must report self_contradiction (it currently reports CLEAN — the bug)"
        assert result['clean'] is False, f"{label} must not be clean"


def test_self_contradiction_gates():
    assert 'self_contradiction' in tq.REQUIRED_CLEAN


# ── Negative control: round 8 CHURCH_1 stays CLEAN ───────────────────────────
# It credits ONE designer (James Murphy) for the church, its stop titles (Nave,
# Narthex, Stained Glass Windows, Side Chapels) match their bodies, and its epilog
# names delivered stops (Stained Glass Windows, Side Chapels). It must not fire.
def test_negative_control_round8_church1_is_clean():
    text = _read(_R8, 'CHURCH_1.txt')
    assert tq._find_self_contradictions(text) == []
    result = tq.score_tour(text)
    assert 'self_contradiction' not in result['defects']


# ── False-positive survey: EVERY round 7 and round 8 tour ────────────────────
# A check that fires on everything is worse than none. Round 7 and 8 contain no
# self-contradiction of these four shapes, so the checker must be silent on all of
# them.
def _round_txts(dirpath):
    return sorted(os.path.join(dirpath, f) for f in os.listdir(dirpath)
                  if f.endswith('.txt'))


def test_no_false_positives_across_round7_and_round8():
    offenders = {}
    for path in _round_txts(_R7) + _round_txts(_R8):
        text = _read(path)
        cs = tq._find_self_contradictions(text)
        if cs:
            offenders[os.path.basename(path)] = [c[0] for c in cs]
    assert offenders == {}, f"false positives on healthy tours: {offenders}"


if __name__ == '__main__':
    # Allow running without pytest.
    fns = [v for k, v in sorted(globals().items())
           if k.startswith('test_') and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"PASS {fn.__name__}")
    print(f"\n{passed}/{len(fns)} tests passed")
