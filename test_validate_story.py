#!/usr/bin/env python3
"""test_validate_story.py — Tests for LOCAL-463 validate_story.py

Acceptance criteria from the task:
1. D434 stop-2 story against stop2_survivors.txt: sentences 2 and 3 → UNSUPPORTED_RELATION;
   sentences 1 and 4 → GROUNDED. Story = REJECTED.
2. Original stop-2 prose: Hogarth sentence → UNSUPPORTED_ENTITY.
3. Control: corpus that DOES state the link → GROUNDED (proves check can pass).
4. No false positives on plain conjunction: "and" joining two supported facts is not causal.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from validate_story import validate_story


CORPUS_PATH = os.path.join(HERE, 'story_lab_state', 'stop2_survivors.txt')
PROD_PATH = os.path.join(HERE, 'story_lab_state', 'stop2_prod.json')


def load_corpus():
    return open(CORPUS_PATH, encoding='utf-8').read()


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 1: D434 stop-2 story — sentences 2,3 UNSUPPORTED_RELATION; 1,4 GROUNDED
# ═══════════════════════════════════════════════════════════════════════════════

def test_d434_story():
    """The D434 stop-2 story with invented causal links."""
    corpus = load_corpus()
    story = (
        'In July of 1938, a 34-year-old Salvador Dalí, a devoted follower of Freud, '
        'finally met the 81-year-old Sigmund Freud in London, marking their first and '
        'only encounter. '
        'This meeting was as surreal as Dalí\u2019s art, leaving a lasting impression '
        'on both the artist and the psychoanalyst. '
        'Years later, Dalí would channel his fascination with Freud into his work, '
        'culminating in the creation of "Moses and Monotheism" in 1974-75. '
        'The piece was printed by Arts Litho, Torrents, Wolfensberger and published '
        'by Editions Art & Valeur S.A., Paris.'
    )

    result = validate_story(story, corpus)

    assert result['verdict'] == 'REJECTED', f"Expected REJECTED, got {result['verdict']}"
    assert len(result['sentences']) == 4, f"Expected 4 sentences, got {len(result['sentences'])}"

    # Sentence 1: GROUNDED (entities all in corpus, no causal claim)
    assert result['sentences'][0]['status'] == 'GROUNDED', \
        f"S1 expected GROUNDED, got {result['sentences'][0]['status']}"

    # Sentence 2: UNSUPPORTED_RELATION ("leaving a lasting impression")
    assert result['sentences'][1]['status'] == 'UNSUPPORTED_RELATION', \
        f"S2 expected UNSUPPORTED_RELATION, got {result['sentences'][1]['status']}"

    # Sentence 3: UNSUPPORTED_RELATION ("would channel... culminating in")
    assert result['sentences'][2]['status'] == 'UNSUPPORTED_RELATION', \
        f"S3 expected UNSUPPORTED_RELATION, got {result['sentences'][2]['status']}"

    # Sentence 4: GROUNDED (plain factual statement, all in corpus)
    assert result['sentences'][3]['status'] == 'GROUNDED', \
        f"S4 expected GROUNDED, got {result['sentences'][3]['status']}"

    print("  PASS: D434 story correctly rejected (S2, S3 = UNSUPPORTED_RELATION)")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 2: Original/delivered prose — "The Hogarth Press" → UNSUPPORTED_ENTITY
# ═══════════════════════════════════════════════════════════════════════════════

def test_original_hogarth():
    """The delivered Original stop-2 prose: Hogarth Press not in corpus."""
    corpus = load_corpus()
    prod = json.load(open(PROD_PATH, encoding='utf-8'))
    story = prod['tour_prose']

    result = validate_story(story, corpus)

    assert result['verdict'] == 'REJECTED', f"Expected REJECTED, got {result['verdict']}"

    # Find the Hogarth sentence
    hogarth_sentences = [s for s in result['sentences']
                         if 'Hogarth' in s['text']]
    assert len(hogarth_sentences) >= 1, "Expected at least one sentence mentioning Hogarth"

    for hs in hogarth_sentences:
        assert hs['status'] == 'UNSUPPORTED_ENTITY', \
            f"Hogarth sentence expected UNSUPPORTED_ENTITY, got {hs['status']}"
        org_findings = [f for f in hs['findings'] if 'Hogarth' in f.get('value', '')]
        assert len(org_findings) >= 1, "Expected finding about Hogarth Press"

    print("  PASS: Original prose correctly flags Hogarth Press as UNSUPPORTED_ENTITY")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 3: Control — corpus DOES state the causal link → GROUNDED
# ═══════════════════════════════════════════════════════════════════════════════

def test_control_corpus_with_links():
    """When the corpus explicitly states the causal link, the sentence is GROUNDED."""
    corpus_with_links = (
        "Salvador Dalí's first and only encounter with Sigmund Freud was fittingly "
        "bizarre. The pair met on 19 July 1938 at Freud's home in London. Freud was 81, "
        "Dali 34.\n"
        "The 1938 meeting left a lasting impression on both Dalí the artist and Freud "
        "the psychoanalyst, as documented in their subsequent correspondence.\n"
        "Dalí would channel his fascination with Freud into his work, culminating in "
        "the creation of Moses and Monotheism in 1974-75.\n"
        "Moses and Monotheism by Salvador Dali, 1974-75. Sold as a set of 10. "
        "Salvador Dali (Spanish, 1904-1989). Drypoints and lithographs on sheepskin.\n"
        "It was printed by Arts Litho, Torrents, Wolfensberger and was published by "
        "Editions Art & Valeur S.A., Paris.\n"
    )

    story = (
        'In July of 1938, a 34-year-old Salvador Dalí, a devoted follower of Freud, '
        'finally met the 81-year-old Sigmund Freud in London, marking their first and '
        'only encounter. '
        'This meeting was as surreal as Dalí\u2019s art, leaving a lasting impression '
        'on both the artist and the psychoanalyst. '
        'Years later, Dalí would channel his fascination with Freud into his work, '
        'culminating in the creation of "Moses and Monotheism" in 1974-75. '
        'The piece was printed by Arts Litho, Torrents, Wolfensberger and published '
        'by Editions Art & Valeur S.A., Paris.'
    )

    result = validate_story(story, corpus_with_links)

    assert result['verdict'] == 'TRUE_TO_SOURCES', \
        f"Expected TRUE_TO_SOURCES, got {result['verdict']}"

    for i, s in enumerate(result['sentences']):
        assert s['status'] == 'GROUNDED', \
            f"S{i+1} expected GROUNDED, got {s['status']}: {s['findings']}"

    print("  PASS: Control test — corpus with stated links → all GROUNDED (check CAN pass)")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 4: Plain conjunction — no false positive
# ═══════════════════════════════════════════════════════════════════════════════

def test_plain_conjunction_not_causal():
    """'and' joining two supported facts is not a causal claim."""
    corpus = load_corpus()

    # Both halves are in the corpus: Dalí met Freud in London, and it was first/only
    story = "Dalí met Freud in London and the pair never met again."

    result = validate_story(story, corpus)

    assert result['verdict'] == 'TRUE_TO_SOURCES', \
        f"Expected TRUE_TO_SOURCES, got {result['verdict']}"
    assert result['sentences'][0]['status'] == 'GROUNDED', \
        f"Expected GROUNDED, got {result['sentences'][0]['status']}"

    print("  PASS: Plain conjunction 'and' not flagged as causal claim")


# ═══════════════════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("\n" + "=" * 70)
    print("TEST SUITE: validate_story.py (LOCAL-463)")
    print("=" * 70 + "\n")

    tests = [
        ("Test 1: D434 story — UNSUPPORTED_RELATION on sentences 2,3", test_d434_story),
        ("Test 2: Original prose — Hogarth = UNSUPPORTED_ENTITY", test_original_hogarth),
        ("Test 3: Control — corpus states the link → GROUNDED", test_control_corpus_with_links),
        ("Test 4: Plain conjunction — no false positive", test_plain_conjunction_not_causal),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        print(f"[RUN] {name}")
        try:
            fn()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{'=' * 70}")
    print(f"RESULTS: {passed} passed, {failed} failed, {passed + failed} total")
    print(f"{'=' * 70}\n")

    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
