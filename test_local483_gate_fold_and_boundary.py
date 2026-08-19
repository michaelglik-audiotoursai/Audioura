#!/usr/bin/env python3
"""test_local483_gate_fold_and_boundary.py — the gate chain audited as a CLASS.

Mission of 2026-08-18 17:0x, item 1: "Every regex in the gate/scorer chain gets
an accent-folding and a word-boundary test. D243 has now been hit five times; it
is systemic." This is the sixth. Fixing them one at a time is the slow path that
was measured; this suite is the alternative.

Two things make it different from the seven suites that were all green while
three gates were false-rejecting:

1.  It is TABLE-DRIVEN over the grounding predicates, not written per gate. A
    new predicate is added to `PREDICATES` and immediately inherits every probe.
    A gate that forgets to fold goes red on the day it is written, not five
    months later when a French publisher disappears from a tour.

2.  Every gate gets a TRUE SET as well as a FALSE SET (mission item 2,
    STORY_GATE_TIERS.md measure 6). LOCAL-402 was 11/11 green while
    false-rejecting because every case asserted the gate FIRES. Half of the
    assertions here assert that it does NOT.

RED-ON-REVERT — verified 2026-08-18. Against the pre-LOCAL-483 code:
    check_person_grounded('Salvador Dali', "...Salvador Dalí...")  -> False
    _agent_in_text('Editions Verve',       "...Éditions Verve...") -> False
    _agent_in_text('Ars',                  'Arsenal Gallery')      -> True
    _mentions_person('Dali sketched...',   'Salvador Dalí','Dalí') -> False
Four of these assertions fail on the old code. A test that cannot fail is not
evidence (D242 standing check 1).

Run: python3 test_local483_gate_fold_and_boundary.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from prose_entity_grounding_gate import (  # noqa: E402
    check_person_grounded, _mentions_person, _fold_org, check_org_grounded,
)
from stop_claim_audit import _agent_in_text  # noqa: E402
from text_fold import fold, contains_entity  # noqa: E402


PASSED = []
FAILED = []


def check(label, got, want):
    if got == want:
        PASSED.append(label)
        print(f"  ✅ {label}")
    else:
        FAILED.append(f"{label} (got {got!r}, want {want!r})")
        print(f"  ❌ {label} — got {got!r}, want {want!r}")


# ═══════════════════════════════════════════════════════════════════════════════
# THE CORPUS — real spellings from the MFA "Dalí, Miró and the livre d'artiste"
# material, because that is where every one of these defects was measured.
# ═══════════════════════════════════════════════════════════════════════════════

CORPUS = (
    "The exhibition brings together works by Salvador Dalí and Joan Miró, "
    "printed by Éditions Verve in Paris and by Mourlot Frères. "
    "Paul Cézanne and Odilon Redon are represented in the adjoining gallery. "
    "The Musée National d'Art Moderne lent several sheets."
)

# Entities that ARE in the corpus, in both the accented spelling the museum
# uses and the bare-ASCII spelling the model writes. Both must ground.
GROUNDED_PAIRS = [
    ("Salvador Dalí", "Salvador Dali"),
    ("Joan Miró", "Joan Miro"),
    ("Paul Cézanne", "Paul Cezanne"),
    ("Odilon Redon", "Odilon Redon"),      # unaccented control
]

# Entities that are NOT in the corpus. These must NOT ground, or the gate has
# stopped doing its job. 'The Hogarth Press' is the fabrication Michael has
# objected to most (D482) and is the anchor of this set.
UNGROUNDED = [
    "William Hogarth",
    "Sigmund Freud",
    "Pablo Picasso",
    "Marcel Duchamp",
]

# Substrings of real corpus words that must not ground on their own. This is
# the false-ACCEPTANCE half, the one that fails quietly.
SUBSTRING_TRAPS = [
    ("Ars", "Arsenal Gallery"),          # measured: returned True
    ("Red", "Odilon Redon lent a sheet"),
    ("Mir", "Joan Miró signed it"),
    ("Ver", "Éditions Verve, Paris"),
]

# The grounding predicates in the chain, normalised to one signature:
#     predicate(entity, corpus) -> bool
# Adding a gate here is the whole cost of covering it.
PREDICATES = [
    ("5.158  person grounding", lambda e, c: check_person_grounded(e, c)),
    ("5.158b role-claim agent", lambda e, c: _agent_in_text(e, c)),
]


def test_fold_primitive():
    print("\n[1] text_fold primitive")
    check("fold strips accents", fold("Éditions Verve"), "editions verve")
    check("fold collapses whitespace", fold("Editions   Verve"), "editions verve")
    check("fold handles decomposed input",
          fold("Dalí"), fold("Dalí"))
    check("fold of None is empty", fold(None), "")
    check("contains_entity is whole-word",
          contains_entity("Arsenal Gallery", "Ars"), False)
    check("contains_entity allows possessive",
          contains_entity("Dali's etchings", "Dalí"), True)
    check("contains_entity tolerates internal whitespace",
          contains_entity("Editions   Verve", "Éditions Verve"), True)


def test_predicates_fold_accents():
    """TRUE SET — the accented and bare spellings must agree, both grounding."""
    print("\n[2] accent folding — every predicate, both spellings (TRUE set)")
    for gate_name, predicate in PREDICATES:
        for accented, bare in GROUNDED_PAIRS:
            check(f"{gate_name}: {accented!r} grounds",
                  predicate(accented, CORPUS), True)
            check(f"{gate_name}: {bare!r} grounds (folded)",
                  predicate(bare, CORPUS), True)


def test_predicates_still_reject():
    """FALSE SET — folding must not turn the gates into pass-throughs.

    This is the half LOCAL-402 was missing. Widening a match is the easiest way
    to make every accent test pass and every gate useless.
    """
    print("\n[3] fabrications still rejected — every predicate (FALSE set)")
    for gate_name, predicate in PREDICATES:
        for absent in UNGROUNDED:
            check(f"{gate_name}: {absent!r} does NOT ground",
                  predicate(absent, CORPUS), False)


def test_predicates_respect_word_boundaries():
    print("\n[4] word boundaries — a fragment must not ground on a longer word")
    for gate_name, predicate in PREDICATES:
        for fragment, text in SUBSTRING_TRAPS:
            check(f"{gate_name}: {fragment!r} does NOT ground in {text[:24]!r}",
                  predicate(fragment, text), False)


def test_paired_instruments_agree():
    """Mission item 3: cross-check instruments that should agree.

    `check_person_grounded` decides a person is ungrounded; `_mentions_person`
    then locates their mentions to remove. If the two disagree on spelling, the
    gate logs a drop and removes nothing — a decision with no effect, which is
    the shape every defect on 2026-08-18 had.
    """
    print("\n[5] paired instruments agree across spellings")
    sentences = {
        "Dali sketched Freud in 1938.": ("Salvador Dalí", "Dalí"),
        "Dalí sketched Freud in 1938.": ("Salvador Dali", "Dali"),
        "Miro's etchings hang nearby.": ("Joan Miró", "Miró"),
    }
    for sentence, (full, surname) in sentences.items():
        check(f"_mentions_person finds {surname!r} in {sentence[:22]!r}",
              _mentions_person(sentence, full, surname), True)

    # And the negative: a person genuinely absent is not "found".
    check("_mentions_person does not invent a mention",
          _mentions_person("Miro's etchings hang nearby.",
                           "William Hogarth", "Hogarth"), False)

    # The org gate folds too, and its fold must equal the shared one.
    check("_fold_org agrees with text_fold.fold",
          _fold_org("Éditions  Verve"), fold("Éditions  Verve"))


def test_org_gate_true_and_false_sets():
    """The org gate (5.158c) folded correctly already. Its hole was the other half.

    The well-known-org exemption tested containment in BOTH directions, so any
    fabricated name that merely CONTAINED a famous museum's name was grounded for
    free — against a corpus that named none of them. That is a false ACCEPTANCE,
    and it is why this suite asserts both directions for every gate: the
    false-rejection half fails loudly and got fixed four times in one day, while
    this sat untouched.
    """
    print("\n[6] org gate (5.158c) — TRUE and FALSE sets")
    # TRUE set — real orgs, both spellings, and the legitimate exemptions.
    check("org: 'Éditions Verve' grounds",
          check_org_grounded("Éditions Verve", CORPUS, []), True)
    check("org: 'Editions Verve' grounds (folded)",
          check_org_grounded("Editions Verve", CORPUS, []), True)
    check("org: 'Mourlot Freres' grounds (folded)",
          check_org_grounded("Mourlot Freres", CORPUS, []), True)
    check("org: grounded via the stop record, not the corpus",
          check_org_grounded("The Hogarth Press", CORPUS,
                             ["published by The Hogarth Press"]), True)
    check("org: well-known venue is exempt",
          check_org_grounded("Museum of Fine Arts", CORPUS, []), True)
    check("org: well-known venue with a place qualifier is exempt",
          check_org_grounded("Museum of Fine Arts, Boston", CORPUS, []), True)

    # FALSE set — fabrications, including ones wearing a famous name.
    check("org: 'The Hogarth Press' does NOT ground",
          check_org_grounded("The Hogarth Press", CORPUS, []), False)
    for invented in ["Tate Modern Press", "The Met Foundation",
                     "Louvre Editions", "Tate Publishing"]:
        check(f"org: invented {invented!r} does NOT ground on a famous substring",
              check_org_grounded(invented, CORPUS, []), False)


def test_span_patterns_see_accented_capitals():
    """The OTHER half of D243, and the one that fails invisibly.

    `[A-Z]` cannot match `É`. Every span-capturing pattern in the chain that used
    the bare class was blind to accented proper nouns — and because these are
    EXTRACTORS, the symptom is not a wrong answer but no answer: an artist named
    'Édouard Manet' was never recognised as a person, so gate 5.158 never checked
    him, and reported a clean stop.

    Measured before the fix: 2 names in the ASCII sentence, 0 in the accented one,
    for three of the five patterns. `story_validator._NAME_SPAN` was already
    right — the same one-sibling-correct shape as the folding defect.

    The assertion is a comparison between the two spellings, not a fixed count,
    so it stays true if the patterns are retuned for other reasons.
    """
    print("\n[7] span patterns see accented capitals (D243, extraction half)")
    import importlib
    accented = "Édouard Manet met Émile Zola in 1868."
    ascii_twin = "Edouard Manet met Emile Zola in 1868."
    patterns = [
        ('evaluate_story', '_PERSON_NAME'),
        ('story_validator', '_NAME_SPAN'),
        ('story_opportunity_scan', '_PROPER_SPAN'),
        ('prose_entity_grounding_gate', '_PERSON_MULTI_WORD'),
        ('prose_entity_grounding_gate', '_ORG_SPAN_RE'),
    ]
    for module_name, pattern_name in patterns:
        rx = getattr(importlib.import_module(module_name), pattern_name)
        n_accented = len(rx.findall(accented))
        n_ascii = len(rx.findall(ascii_twin))
        check(f"{module_name}.{pattern_name}: accented finds as many as ASCII "
              f"({n_accented} vs {n_ascii})",
              n_accented == n_ascii and n_ascii > 0, True)


def test_person_extractor_does_not_claim_organisations():
    """The regression the unit tests did not catch and the live run did.

    Teaching `_PERSON_MULTI_WORD` to see accented capitals (section 7) made
    'Éditions Verve' visible to the PERSON extractor for the first time. Gate
    5.158 then looked for it on the 4,699-char exhibition page, did not find it,
    and dropped the sentence — the D482 false rejection of the real publisher,
    arriving through a third gate that the fix for the first two had opened.

    In the same run, one phase later, the org gate grounded that exact name
    correctly against the widened corpus. Two instruments disagreeing about the
    same span, which is the shape this whole suite exists to catch; this time we
    were the ones who introduced it.

    Both halves are asserted: organisations are not people, AND people are still
    people — including accented ones, or the section-7 fix has been undone.
    """
    print("\n[8] the person extractor does not claim organisations")
    from prose_entity_grounding_gate import extract_person_names
    text = ("Éditions Verve published the book. Salvador Dalí and Joan Miró met "
            "Louis Broder. Mourlot Frères printed it at the Museum of Fine Arts. "
            "Boris Fridman lent the set. The Hogarth Press issued an edition. "
            "Édouard Manet knew Émile Zola.")
    found = extract_person_names(text)

    # FALSE set — none of these is a person.
    for org in ['Éditions Verve', 'Mourlot Frères', 'The Hogarth Press',
                'Museum of Fine Arts']:
        check(f"{org!r} is NOT extracted as a person", org in found, False)

    # TRUE set — all of these are, accents included.
    for person in ['Salvador Dalí', 'Joan Miró', 'Louis Broder',
                   'Boris Fridman', 'Édouard Manet', 'Émile Zola']:
        check(f"{person!r} IS extracted as a person", person in found, True)


def main():
    print("=" * 62)
    print("  LOCAL-483 — gate chain audited as a class")
    print("  accent folding · word boundaries · TRUE and FALSE sets")
    print("=" * 62)

    test_fold_primitive()
    test_predicates_fold_accents()
    test_predicates_still_reject()
    test_predicates_respect_word_boundaries()
    test_paired_instruments_agree()
    test_org_gate_true_and_false_sets()
    test_span_patterns_see_accented_capitals()
    test_person_extractor_does_not_claim_organisations()

    print("\n" + "=" * 62)
    print(f"  RESULTS: {len(PASSED)}/{len(PASSED) + len(FAILED)} passed, "
          f"{len(FAILED)} failed")
    if FAILED:
        for f in FAILED:
            print(f"    FAILED: {f}")
    print("=" * 62)
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
