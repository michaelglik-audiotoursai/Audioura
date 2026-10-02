#!/usr/bin/env python3
"""test_local486_story_worthiness.py — Michael's step 2, with both sets.

STORY_GATE_TIERS.md measure 6, and the lesson of LOCAL-402: a gate tested only
on cases where it FIRES can be 11/11 green while false-rejecting everything. This
suite is deliberately weighted the other way round — **most of it asserts that
stops ARE mined**, because a wrong "no" is the expensive error here and it is the
one nothing downstream would ever reveal.

Run: python3 test_local486_story_worthiness.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from story_worthiness import (  # noqa: E402
    assess_stop_worthiness, agreement_report, WORTHINESS_DISABLED_ENV,
)

PASSED, FAILED = [], []


def check(label, got, want):
    if got == want:
        PASSED.append(label); print(f"  ✅ {label}")
    else:
        FAILED.append(f"{label} (got {got!r}, want {want!r})")
        print(f"  ❌ {label} — got {got!r}, want {want!r}")


# ── TRUE SET: these must ALL be mined. Any regression here loses stories. ──────
WORTH_MINING = [
    ("full matrix", {
        'canonical_title': 'Au Soleil du Plafond', 'artist': 'Joan Miró',
        'publisher': 'Éditions Verve', 'credit_line': 'Gift of Boris Fridman, 2019',
        'medium': 'Illustrated book with 40 color lithographs'}),
    ("artist only", {
        'canonical_title': '', 'artist': 'Salvador Dalí', 'publisher': '',
        'credit_line': '', 'medium': ''}),
    ("publisher only", {
        'canonical_title': '', 'artist': '', 'publisher': 'Mourlot Frères',
        'credit_line': '', 'medium': ''}),
    ("specific title only", {
        'canonical_title': "Le Lézard aux plumes d'or", 'artist': '',
        'publisher': '', 'credit_line': '', 'medium': ''}),
    ("credit line carrying a fact", {
        'canonical_title': '', 'artist': '', 'publisher': '',
        'credit_line': 'Gift of Boris Fridman in honor of the artist, 2019',
        'medium': ''}),
    ("specific medium only", {
        'canonical_title': '', 'artist': '', 'publisher': '', 'credit_line': '',
        'medium': 'Drypoint on vellum, edition of 80'}),
    ("printed_by only", {
        'canonical_title': '', 'artist': '', 'printed_by': 'Atelier Lacourière',
        'publisher': '', 'credit_line': '', 'medium': ''}),
]

# ── FALSE SET: these have nothing a Fact → Stop chain could start from. ───────
NOT_WORTH_MINING = [
    ("gallery number", {'canonical_title': 'Gallery 3'}),
    ("room number", {'canonical_title': 'Room 2', 'medium': 'Mixed media'}),
    ("introduction stop", {'canonical_title': 'Introduction', 'medium': 'Not specified'}),
    ("bare boilerplate credit", {'canonical_title': 'Hall', 'credit_line': 'Gift of'}),
    ("entirely empty matrix", {}),
    ("unknown agent placeholders", {
        'canonical_title': 'Corridor', 'artist': 'Unknown', 'publisher': 'various',
        'credit_line': '', 'medium': 'unknown'}),
]


def test_true_set():
    print("\n[1] TRUE set — anything with material gets mined")
    for label, matrix in WORTH_MINING:
        r = assess_stop_worthiness(matrix)
        check(f"{label} IS mined", r['worth_mining'], True)


def test_false_set():
    print("\n[2] FALSE set — only stops with nothing at all are skipped")
    for label, matrix in NOT_WORTH_MINING:
        r = assess_stop_worthiness(matrix)
        check(f"{label} is NOT mined", r['worth_mining'], False)


def test_asymmetry_is_real():
    """The design claim, asserted rather than left in a comment.

    A single signal is enough. If someone later requires two, this goes red and
    they have to justify trading stories for money with an A/B (D484: 15 runs
    per arm), instead of tightening a threshold in passing.
    """
    print("\n[3] one signal is sufficient — the asymmetry is enforced, not assumed")
    one_signal = {'canonical_title': '', 'artist': 'Joan Miró', 'publisher': '',
                  'credit_line': '', 'medium': ''}
    r = assess_stop_worthiness(one_signal)
    check("exactly one signal present", r['score'], 1)
    check("and that is enough to mine", r['worth_mining'], True)


def test_accents_do_not_hide_material():
    """D243, seen from step 2. An accented agent is still an agent."""
    print("\n[4] accented names count as material")
    for name in ['Joan Miró', 'Mourlot Frères', 'Éditions Verve', 'Atelier Lacourière']:
        r = assess_stop_worthiness({'artist': name})
        check(f"{name!r} counts as a named agent", r['worth_mining'], True)


def test_disable_flag():
    print("\n[5] the env flag disables it — everything mined, as before")
    os.environ[WORTHINESS_DISABLED_ENV] = '1'
    try:
        r = assess_stop_worthiness({'canonical_title': 'Gallery 3'})
        check("disabled reports worth_mining", r['worth_mining'], True)
        check("and says so", r['disabled'], True)
    finally:
        del os.environ[WORTHINESS_DISABLED_ENV]
    check("re-enabled after clearing",
          assess_stop_worthiness({'canonical_title': 'Gallery 3'})['worth_mining'], False)


def test_agreement_report():
    """Mission item 3: the pre-mining call vs the post-draft scan."""
    print("\n[6] agreement report lines the two instruments up")
    pre = [{'worth_mining': True}, {'worth_mining': True}, {'worth_mining': False}]
    post = [{'needs_additional_story': False},   # mined, got a story
            {'needs_additional_story': True},    # mined, got nothing — wasted
            {'needs_additional_story': True}]    # skipped, no story — correct
    cells = agreement_report(pre, post)
    check("mined and produced a story", cells['mined_and_story'], 1)
    check("mined and produced nothing (wasted spend)", cells['wasted'], 1)
    check("skipped and indeed storyless", cells['skipped_no_story'], 1)
    check("bar not too strict in this sample", cells['bar_too_strict'], 0)


def test_wired_into_production():
    print("\n[7] production imports the check (the edge greps can prove)")
    src = open(os.path.join(HERE, 'generate_tour_text.py'), encoding='utf-8').read()
    check("generate_tour_text imports assess_stop_worthiness",
          'from story_worthiness import assess_stop_worthiness' in src, True)
    check("and can skip mining on the result", 'skipped_unworthy' in src, True)


def main():
    print("=" * 62)
    print("  LOCAL-486 — step 2: which stops would benefit from a story")
    print("=" * 62)
    for t in (test_true_set, test_false_set, test_asymmetry_is_real,
              test_accents_do_not_hide_material, test_disable_flag,
              test_agreement_report, test_wired_into_production):
        t()
    print("\n" + "=" * 62)
    print(f"  RESULTS: {len(PASSED)}/{len(PASSED) + len(FAILED)} passed, {len(FAILED)} failed")
    for f in FAILED:
        print(f"    FAILED: {f}")
    print("=" * 62)
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
