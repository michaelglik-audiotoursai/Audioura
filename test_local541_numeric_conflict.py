"""[LOCAL-541] 12 million and 43.5 million passengers in the same tour.

LOCAL-536 shipped four self-contradiction sub-checks; this adds the fifth,
`numeric_conflict`: the same measured quantity stated twice with values that
cannot both be right. Round 9 LOGAN_1 states its annual passenger throughput as
BOTH "nearly 12 million passengers annually" (stop 1) and "a record 43.5 million
passengers in 2024" (stop 3). 43.5M is correct; the tour refutes itself, and this
needs no knowledge of the world.

Every offending string below is asserted to be PRESENT in the real round-9 file
before it is fed to the checker, so the test cannot drift from the evidence — if
the generator ever rewords these, the test fails loudly rather than passing against
a string that is no longer in the file.

The heart of the task is deciding what "the same quantity" means. The negative
controls, drawn from the same tour, are the real test:
  * 285 feet (tower height) vs 400,000 flights — different unit AND noun, never
    compared;
  * "1943" renaming stated three times with the same value — a year is not a
    measurement, and repetition of a consistent figure is not a conflict;
  * 1923 (opening) vs 1959 (a later event) — different events, both correct;
  * 413,409 aircraft operations vs 43.5 million passengers — same airport, same
    year, but a different measured noun.

Deterministic and offline: no corpus, no grounding call, no outside knowledge —
that is the whole point of self-contradiction as a defect class (D577).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tour_quality as tq

_HERE = os.path.dirname(os.path.abspath(__file__))
_R9 = os.path.join(_HERE, 'TOURS_FOR_REVIEW', 'round9')


def _read(*parts):
    with open(os.path.join(*parts), errors='ignore') as fh:
        return fh.read()


LOGAN_1 = _read(_R9, 'LOGAN_1.txt')


# ── The two verbatim quotes the case turns on, asserted present in the real file ─
N_STOP1 = ("the architectural design facilitates the efficient flow of nearly 12 "
           "million passengers annually")
N_STOP3 = ("Boston Logan International Airport, which saw a record 43.5 million "
           "passengers in 2024")
# Negative-control strings, all present in the very same file.
NC_HEIGHT = "rises 285 feet into the sky"
NC_FLIGHTS = "over 400,000 flights annually"
NC_1943 = "renamed in 1943"
NC_OPENED_1923 = "originated on September 8, 1923"


def test_verbatim_quotes_are_present_in_the_real_file():
    """The case is built from strings that actually appear in round-9 LOGAN_1."""
    for q in (N_STOP1, N_STOP3, NC_HEIGHT, NC_FLIGHTS):
        assert q in LOGAN_1, f"LOGAN_1 no longer contains: {q!r}"
    # The 1943 renaming is stated more than once, with the same value each time.
    assert LOGAN_1.count("1943") >= 3, "the 1943 renaming should recur consistently"


# ── The positive: the two passenger figures collide ─────────────────────────
def test_numeric_conflict_is_found_in_logan_1():
    found = tq._find_numeric_conflict(LOGAN_1)
    assert found is not None, "the 12M-vs-43.5M passenger conflict must be found"
    cls, quote_a, quote_b = found
    assert cls == 'passengers'
    # Both offending sentences are reported so the decision is inspectable, and
    # each is a real sentence lifted verbatim from the tour.
    joined = quote_a + ' || ' + quote_b
    assert N_STOP1 in joined, "the stop-1 12-million sentence must be a reported quote"
    assert N_STOP3 in joined, "the stop-3 43.5-million sentence must be a reported quote"


def test_the_two_values_are_actually_different():
    """Guard the premise: the two figures really are 12,000,000 and 43,500,000."""
    found = tq._find_numeric_conflict(LOGAN_1)
    assert found is not None
    both = found[1] + ' ' + found[2]
    assert '12 million' in both
    assert '43.5 million' in both


# ── score_tour end to end: numeric_conflict joins the existing report ────────
def test_score_tour_reports_numeric_and_attribution_conflict():
    """Adding numeric_conflict must not remove the attribution_conflict that
    LOCAL-536 already reports here — BOTH must appear."""
    subs = [c[0] for c in tq._find_self_contradictions(LOGAN_1)]
    assert 'numeric_conflict' in subs, "the new sub-check must fire on LOGAN_1"
    assert 'attribution_conflict' in subs, \
        "the pre-existing attribution_conflict must still fire on LOGAN_1"
    result = tq.score_tour(LOGAN_1)
    assert 'self_contradiction' in result['defects']
    assert result['clean'] is False


# ── Negative controls: the real test. Every one must stay CLEAN. ─────────────
def _tour(body):
    """Wrap a body in the minimum tour scaffold so venue detection works."""
    return ("Step-by-Step Audio Guided Tour: Boston Logan International Airport, "
            "Boston MA - Facility Tour\nStop 1: Control Tower\n" + body)


def test_height_and_flights_do_not_conflict():
    """285 feet (a height) and 400,000 flights (air movements) are different unit
    AND different noun — never the same quantity, though both are numbers about the
    same tower in the same stop. Uses the file's own two sentences."""
    body = ("Its distinctive silhouette rises 285 feet into the sky. Controllers "
            "guide over 400,000 flights annually through Boston's busy airspace.")
    assert tq._find_numeric_conflict(_tour(body)) is None


def test_repeated_consistent_year_is_not_a_conflict():
    """The 1943 renaming stated three times with the SAME value is repetition, not
    contradiction — and a bare year is not a measured quantity at all."""
    body = ("The airport was renamed in 1943 to honor Logan. By 1943, the airport "
            "was renamed. In 1943, legislators decided to name the airport after "
            "him.")
    assert tq._find_numeric_conflict(_tour(body)) is None


def test_different_events_different_years_do_not_conflict():
    """1923 (opening) against a later year is two different events, both correct —
    years carry no measured noun, so they never enter the comparison."""
    body = ("This mechanism originated on September 8, 1923. Massport was formed "
            "in 1959 to run it.")
    assert tq._find_numeric_conflict(_tour(body)) is None


def test_operations_and_passengers_are_different_quantities():
    """413,409 aircraft operations and 43.5 million passengers are the same airport
    in the same year but a DIFFERENT measured noun — not the same quantity."""
    body = ("The tower oversaw 413,409 aircraft operations. The airport saw a "
            "record 43.5 million passengers in 2024.")
    assert tq._find_numeric_conflict(_tour(body)) is None


def test_event_crowd_counts_do_not_conflict():
    """Attendances at distinct events (a vigil of 400, a homily of 850, a march of
    1,000) are different measurements, all correct — the same principle as the
    different-events year control. A church tour reciting three crowds stays clean."""
    church = ("Step-by-Step Audio Guided Tour: Our Lady Help of Christians, "
              "Newton MA\nStop 1: Nave\n"
              "Around 400 parishioners gathered for an all-night vigil. Over 850 "
              "parishioners attended his homily. More than 1,000 parishioners "
              "marched to the chancery.")
    assert tq._find_numeric_conflict(church) is None


def test_comparison_to_another_airport_does_not_conflict():
    """A Logan tour may cite Atlanta's numbers for scale: 43.5 million (Boston) and
    106.3 million (Hartsfield-Jackson Atlanta) are two airports, two measurements.
    The foreign figure is bucketed to its own subject and never compared."""
    body = ("In 2024, this airport welcomed 43.5 million passengers. Consider "
            "Hartsfield-Jackson Atlanta International Airport, which served 106.3 "
            "million passengers in 2025.")
    assert tq._find_numeric_conflict(_tour(body)) is None


# ── False-positive survey: EVERY tour file in TOURS_FOR_REVIEW ───────────────
# A check that fires on everything is worse than none. numeric_conflict must fire
# on exactly one file in the corpus — round9/LOGAN_1 — and be silent on the other
# 47. This is the measured false-positive rate the ticket demands.
def _all_txts():
    root = os.path.join(_HERE, 'TOURS_FOR_REVIEW')
    return sorted(os.path.join(d, f)
                  for d, _, fs in os.walk(root) for f in fs if f.endswith('.txt'))


def test_numeric_conflict_fires_on_exactly_one_file_across_the_corpus():
    files = _all_txts()
    # [2026-09-23, LEAD at merge] Was `== 48`. Pinning the corpus SIZE makes this
    # test fail every time a new round is generated -- round 10 and round 11 broke it
    # within the hour -- while saying nothing about the check itself. What matters is
    # that the corpus is non-trivial and that exactly one file trips numeric_conflict.
    assert len(files) >= 48, f"expected at least 48 tour files, found {len(files)}"
    hits = {os.path.relpath(p, _HERE): tq._find_numeric_conflict(_read(p))
            for p in files}
    firing = sorted(k for k, v in hits.items() if v is not None)
    assert firing == [os.path.join('TOURS_FOR_REVIEW', 'round9', 'LOGAN_1.txt')], \
        f"numeric_conflict should fire on exactly round9/LOGAN_1, got: {firing}"


if __name__ == '__main__':
    fns = [v for k, v in sorted(globals().items())
           if k.startswith('test_') and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"PASS {fn.__name__}")
    print(f"\n{passed}/{len(fns)} tests passed")


def test_a_different_airport_is_not_a_contradiction():
    """[2026-09-23, LEAD] Round 11 produced this false positive and it had to be
    fixed the same night, because since LOCAL-540 this defect GATES: a false
    positive spends real money regenerating correct content.

        A  "This airport, sprawls across 2,384 acres ..."          -> the venue
        B  "JFK, the busiest in the New York airport system,
            covers 5,200 acres ..."                                -> NOT the venue

    Both are true. `_AIRPORT_NAME` does not match a bare acronym, so "JFK" resolved
    to the venue and Logan's acreage was reported as contradicting JFK's.
    """
    text = _read(_HERE, 'TOURS_FOR_REVIEW', 'round11', 'LOGAN_1.txt')
    subchecks = [c[0] for c in tq._find_self_contradictions(text)]
    assert 'numeric_conflict' not in subchecks, (
        "two different airports' acreage is not a self-contradiction; got %r"
        % (subchecks,))


def test_the_real_pair_still_fires_after_that_fix():
    """The guard above must not buy its silence by breaking the true positive."""
    subchecks = [c[0] for c in tq._find_self_contradictions(LOGAN_1)]
    assert 'numeric_conflict' in subchecks, (
        "round 9's 'nearly 12 million' vs 'a record 43.5 million' must still fire; "
        "got %r" % (subchecks,))
