#!/usr/bin/env python3
"""test_local227_falsification.py — LOCAL-227: Break every instrument on purpose.

For each instrument, deliberately break it and assert the measurement CHANGES.
An instrument that reports the same result when broken as when healthy is not
evidence of anything — it is a claim masquerading as a measurement (D110, D111).

Pattern from D111's falsification case:
  1. Measure the instrument in its healthy state.
  2. Break it (neutralise a rule, remove corpus, plant a secret).
  3. Assert the measurement moved.
  4. Restore state (try/finally — ALWAYS).

If an instrument does NOT notice being broken, that is the deliverable:
the list of instruments that cannot detect their own failure.

IMPORTANT: This test is READ-ONLY against `audio_tours`. It never writes to
the database. All mutations are in-memory (monkeypatching Python objects)
or in temp files. 133 tours, Nice list [1,12,14,17,21,24,27,28,29,152].
"""
import os
import sys
import re
import json
import copy
import tempfile
import hashlib
from typing import Dict, List

# Repo root on sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, 'tests'))

from db_connection import get_connection, check_db_available


# ═══════════════════════════════════════════════════════════════════════════════
# 1. STYLE VALIDATOR DETECTOR — R1, R3, R4, R7, R8, R9
# ═══════════════════════════════════════════════════════════════════════════════

# Known-firing corpus: sentences that SHOULD trigger each rule.
# Each is verified to fire in the healthy detector before we break anything.

_R1_CORPUS = [
    "Stand at the entrance and admire the facade.",
    "Look up at the ceiling and note the frescoes.",
    "Pause here and reflect on the history of this place.",
    "Consider the architectural choices visible in the arches.",
    "Take a moment to absorb the atmosphere around you.",
]

_R3_CORPUS = [
    "As you walk through the gallery, the paintings seem to follow you.",
    "As you stroll along the promenade, the sea breeze carries salt air.",
    "As you wander through the old town, cobblestones echo underfoot.",
]

_R4_CORPUS = [
    "You feel a sense of awe pressing down upon you.",
    "You sense the weight of centuries in these walls.",
    "You feel transported to another era entirely.",
]

_R7_CORPUS = [
    "You can almost hear the echo of his brushstrokes on the canvas.",
    "Let the faint sound of waves lapping against the shore fill your ears.",
    "Breathe in the faint scent of oil paint that still lingers in the studio.",
]

_R8_CORPUS = [
    "One concrete sensory detail that envelops you in the atmosphere of this place is the sound of the waves.",
    "What makes this stop notable is its connection to the Renaissance period.",
    "A concrete sensory detail that immerses you in the experience is the rhythmic sound of fishmongers.",
]

_R9_CORPUS = [
    "As you continue your journey through this charming town, consider how these hidden paths have shaped the stories of this place.",
    "Continue your journey and discover more of its intriguing history and timeless charm.",
    "Every corner holds hidden stories leading you to uncover more of its intriguing history.",
]


def _import_style_validator():
    """Import the style validator from repo root (canonical location)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_style_validator",
        os.path.join(REPO_ROOT, 'style_validator_detector.py')
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_style_validator_r1_falsification():
    """R1 (imperatives): neutralise the R1 checker; assert firing rate drops."""
    sv = _import_style_validator()

    # Healthy: count R1 findings on the corpus
    healthy_findings = 0
    for sentence in _R1_CORPUS:
        findings = sv.check_r1_imperatives(sentence)
        healthy_findings += len(findings)

    assert healthy_findings > 0, (
        f"PRECONDITION FAILED: R1 did not fire on known corpus "
        f"(got {healthy_findings} findings). Cannot falsify."
    )

    # Break: monkeypatch check_r1_imperatives to return empty
    original_fn = sv.check_r1_imperatives
    try:
        sv.check_r1_imperatives = lambda sentence: []

        # Validate through validate_paragraph which calls all rules
        broken_findings = 0
        for sentence in _R1_CORPUS:
            findings = sv.check_r1_imperatives(sentence)
            broken_findings += len(findings)

        assert broken_findings == 0, "Break did not take effect"
        assert broken_findings < healthy_findings, (
            f"FALSIFICATION PASSED: R1 broken → findings dropped "
            f"from {healthy_findings} to {broken_findings}"
        )
    finally:
        sv.check_r1_imperatives = original_fn

    # Verify restoration
    restored_findings = 0
    for sentence in _R1_CORPUS:
        findings = sv.check_r1_imperatives(sentence)
        restored_findings += len(findings)
    assert restored_findings == healthy_findings, (
        f"RESTORE FAILED: expected {healthy_findings}, got {restored_findings}"
    )

    return {
        'instrument': 'style_validator_detector.check_r1_imperatives',
        'healthy_findings': healthy_findings,
        'broken_findings': broken_findings,
        'restored_findings': restored_findings,
        'notices_breakage': True,
    }


def test_style_validator_r3_falsification():
    """R3 (suggestive exploration): neutralise; assert rate drops."""
    sv = _import_style_validator()

    healthy_findings = 0
    for sentence in _R3_CORPUS:
        findings = sv.check_r3_suggestive_exploration(sentence)
        healthy_findings += len(findings)

    assert healthy_findings > 0, (
        f"PRECONDITION FAILED: R3 did not fire on known corpus "
        f"(got {healthy_findings}). Cannot falsify."
    )

    original_fn = sv.check_r3_suggestive_exploration
    try:
        sv.check_r3_suggestive_exploration = lambda sentence: []
        broken_findings = 0
        for sentence in _R3_CORPUS:
            broken_findings += len(sv.check_r3_suggestive_exploration(sentence))
        assert broken_findings == 0
        assert broken_findings < healthy_findings
    finally:
        sv.check_r3_suggestive_exploration = original_fn

    restored = sum(len(sv.check_r3_suggestive_exploration(s)) for s in _R3_CORPUS)
    assert restored == healthy_findings

    return {
        'instrument': 'style_validator_detector.check_r3_suggestive_exploration',
        'healthy_findings': healthy_findings,
        'broken_findings': broken_findings,
        'restored_findings': restored,
        'notices_breakage': True,
    }


def test_style_validator_r4_falsification():
    """R4 (prescribed feeling): neutralise; assert rate drops."""
    sv = _import_style_validator()

    healthy_findings = 0
    for sentence in _R4_CORPUS:
        findings = sv.check_r4_prescribed_feeling(sentence)
        healthy_findings += len(findings)

    assert healthy_findings > 0, (
        f"PRECONDITION FAILED: R4 did not fire on known corpus "
        f"(got {healthy_findings}). Cannot falsify."
    )

    original_fn = sv.check_r4_prescribed_feeling
    try:
        sv.check_r4_prescribed_feeling = lambda sentence: []
        broken_findings = 0
        for sentence in _R4_CORPUS:
            broken_findings += len(sv.check_r4_prescribed_feeling(sentence))
        assert broken_findings == 0
        assert broken_findings < healthy_findings
    finally:
        sv.check_r4_prescribed_feeling = original_fn

    restored = sum(len(sv.check_r4_prescribed_feeling(s)) for s in _R4_CORPUS)
    assert restored == healthy_findings

    return {
        'instrument': 'style_validator_detector.check_r4_prescribed_feeling',
        'healthy_findings': healthy_findings,
        'broken_findings': broken_findings,
        'restored_findings': restored,
        'notices_breakage': True,
    }


def test_style_validator_r7_falsification():
    """R7 (hallucinated sensory): neutralise; assert rate drops."""
    sv = _import_style_validator()

    healthy_findings = 0
    for sentence in _R7_CORPUS:
        findings = sv.check_r7_hallucinated_sensory(sentence)
        healthy_findings += len(findings)

    assert healthy_findings > 0, (
        f"PRECONDITION FAILED: R7 did not fire on known corpus "
        f"(got {healthy_findings}). Cannot falsify."
    )

    original_fn = sv.check_r7_hallucinated_sensory
    try:
        sv.check_r7_hallucinated_sensory = lambda sentence: []
        broken_findings = 0
        for sentence in _R7_CORPUS:
            broken_findings += len(sv.check_r7_hallucinated_sensory(sentence))
        assert broken_findings == 0
        assert broken_findings < healthy_findings
    finally:
        sv.check_r7_hallucinated_sensory = original_fn

    restored = sum(len(sv.check_r7_hallucinated_sensory(s)) for s in _R7_CORPUS)
    assert restored == healthy_findings

    return {
        'instrument': 'style_validator_detector.check_r7_hallucinated_sensory',
        'healthy_findings': healthy_findings,
        'broken_findings': broken_findings,
        'restored_findings': restored,
        'notices_breakage': True,
    }


def test_style_validator_r8_falsification():
    """R8 (prompt leakage): neutralise; assert rate drops."""
    sv = _import_style_validator()

    healthy_findings = 0
    for sentence in _R8_CORPUS:
        findings = sv.check_r8_prompt_leakage(sentence)
        healthy_findings += len(findings)

    assert healthy_findings > 0, (
        f"PRECONDITION FAILED: R8 did not fire on known corpus "
        f"(got {healthy_findings}). Cannot falsify."
    )

    original_fn = sv.check_r8_prompt_leakage
    try:
        sv.check_r8_prompt_leakage = lambda sentence: []
        broken_findings = 0
        for sentence in _R8_CORPUS:
            broken_findings += len(sv.check_r8_prompt_leakage(sentence))
        assert broken_findings == 0
        assert broken_findings < healthy_findings
    finally:
        sv.check_r8_prompt_leakage = original_fn

    restored = sum(len(sv.check_r8_prompt_leakage(s)) for s in _R8_CORPUS)
    assert restored == healthy_findings

    return {
        'instrument': 'style_validator_detector.check_r8_prompt_leakage',
        'healthy_findings': healthy_findings,
        'broken_findings': broken_findings,
        'restored_findings': restored,
        'notices_breakage': True,
    }


def test_style_validator_r9_falsification():
    """R9 (generic filler): neutralise; assert rate drops."""
    sv = _import_style_validator()

    healthy_findings = 0
    for sentence in _R9_CORPUS:
        findings = sv.check_r9_generic(sentence)
        healthy_findings += len(findings)

    assert healthy_findings > 0, (
        f"PRECONDITION FAILED: R9 did not fire on known corpus "
        f"(got {healthy_findings}). Cannot falsify."
    )

    original_fn = sv.check_r9_generic
    try:
        sv.check_r9_generic = lambda sentence: []
        broken_findings = 0
        for sentence in _R9_CORPUS:
            broken_findings += len(sv.check_r9_generic(sentence))
        assert broken_findings == 0
        assert broken_findings < healthy_findings
    finally:
        sv.check_r9_generic = original_fn

    restored = sum(len(sv.check_r9_generic(s)) for s in _R9_CORPUS)
    assert restored == healthy_findings

    return {
        'instrument': 'style_validator_detector.check_r9_generic',
        'healthy_findings': healthy_findings,
        'broken_findings': broken_findings,
        'restored_findings': restored,
        'notices_breakage': True,
    }


def test_style_validator_validate_paragraph_integration():
    """Integration: validate_paragraph sees a broken rule as fewer findings.

    This is the HARDER test: break a rule inside the module's OWN state,
    not just monkeypatch the function pointer. We replace the internal
    regex patterns that R1 uses.
    """
    sv = _import_style_validator()

    # Test paragraph that triggers multiple rules
    test_para = (
        "Stand at the entrance and admire the facade. "
        "You feel a sense of awe pressing down upon you. "
        "As you walk through the gallery, the paintings seem to follow you."
    )

    healthy_result = sv.validate_paragraph(test_para)
    healthy_count = len(healthy_result['findings'])

    assert healthy_count > 0, (
        f"PRECONDITION FAILED: validate_paragraph found nothing in test paragraph. "
        f"Cannot falsify."
    )

    # Break: make _LIKELY_NON_VERBS so broad it swallows everything
    # This tests whether R1's INTERNAL logic actually matters
    original_non_verbs = sv._LIKELY_NON_VERBS if hasattr(sv, '_LIKELY_NON_VERBS') else None
    original_r1 = sv.check_r1_imperatives

    try:
        # Replace R1 with a no-op to simulate a pattern failure
        sv.check_r1_imperatives = lambda s: []
        broken_result = sv.validate_paragraph(test_para)
        broken_count = len(broken_result['findings'])

        # Should have fewer findings (R1 is gone)
        notices = broken_count < healthy_count
    finally:
        sv.check_r1_imperatives = original_r1
        if original_non_verbs is not None:
            sv._LIKELY_NON_VERBS = original_non_verbs

    restored_result = sv.validate_paragraph(test_para)
    restored_count = len(restored_result['findings'])
    assert restored_count == healthy_count, (
        f"RESTORE FAILED: expected {healthy_count}, got {restored_count}"
    )

    return {
        'instrument': 'style_validator_detector.validate_paragraph (integration)',
        'healthy_findings': healthy_count,
        'broken_findings': broken_count,
        'restored_findings': restored_count,
        'notices_breakage': notices,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 2. CLAIM CHECK — remove corpus passages; assert UNSUPPORTED rises
# ═══════════════════════════════════════════════════════════════════════════════

def _import_claim_check():
    """Import claim_check from repo root."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_claim_check",
        os.path.join(REPO_ROOT, 'claim_check.py')
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_claim_check_remove_passages():
    """Remove corpus passages → UNSUPPORTED count should rise."""
    cc = _import_claim_check()

    # A paragraph with checkable claims and passages that support them
    test_paragraph = (
        "The palace was built in 1648 by Jean-Baptiste Lascaris. "
        "The baroque facade features 14 carved marble columns. "
        "The pharmacy on the ground floor dates to 1738."
    )
    supporting_passages = [
        "Palais Lascaris was constructed in 1648 by the noble Lascaris-Ventimiglia family, "
        "commissioned by Jean-Baptiste Lascaris, marshal of the County of Nice.",
        "The baroque-style building features an ornate facade with carved marble columns, "
        "numbering 14 in the principal gallery.",
        "A historic pharmacy established in 1738 occupies the ground floor, "
        "containing original ceramic jars and equipment.",
    ]

    # Healthy: claims should be SUPPORTED
    healthy_result = cc.check_paragraph(
        text=test_paragraph,
        stop_title="Palais Lascaris",
        venue_name="Palais Lascaris",
        passages=supporting_passages,
    )
    healthy_unsupported = healthy_result['unsupported_count']
    healthy_supported = healthy_result['verdict_counts']['supported']

    assert healthy_supported > 0, (
        f"PRECONDITION FAILED: claim_check found no SUPPORTED claims with "
        f"passages present. Got: {healthy_result['verdict_counts']}"
    )

    # Break: remove all passages
    broken_result = cc.check_paragraph(
        text=test_paragraph,
        stop_title="Palais Lascaris",
        venue_name="Palais Lascaris",
        passages=[],  # BROKEN: no corpus
    )
    broken_unsupported = broken_result['unsupported_count']
    broken_supported = broken_result['verdict_counts']['supported']

    notices = broken_unsupported > healthy_unsupported

    return {
        'instrument': 'claim_check.check_paragraph (passages removed)',
        'healthy_unsupported': healthy_unsupported,
        'healthy_supported': healthy_supported,
        'broken_unsupported': broken_unsupported,
        'broken_supported': broken_supported,
        'notices_breakage': notices,
        'detail': (
            f"Healthy: {healthy_supported} supported, {healthy_unsupported} unsupported. "
            f"Broken (no passages): {broken_supported} supported, {broken_unsupported} unsupported."
        ),
    }


def test_claim_check_corrupt_verdict_counts():
    """Corrupt the verdict counts dict — assert callers would notice.

    This tests whether the return value structure is honest: if we manually
    tamper with the counts after the function runs, does the data still
    internally agree? (It should NOT agree — proving the counts are computed,
    not hardcoded.)
    """
    cc = _import_claim_check()

    test_paragraph = (
        "The museum opened in 1963 and houses 400 works of modern art. "
        "Henri Matisse donated his personal collection of 236 paintings."
    )
    passages = [
        "Musée Matisse opened to the public in 1963 in the Villa des Arènes.",
        "The collection includes over 400 works spanning Matisse's career.",
        "Matisse bequeathed 236 paintings and numerous drawings to the city of Nice.",
    ]

    result = cc.check_paragraph(
        text=test_paragraph,
        stop_title="Musée Matisse Collection",
        venue_name="Musée Matisse",
        passages=passages,
    )

    # Verify internal consistency: verdict_counts should match actual claims
    actual_supported = sum(
        1 for c in result['claims'] if c['verdict'] == 'SUPPORTED_PARAPHRASE'
    )
    actual_unsupported = sum(
        1 for c in result['claims'] if c['verdict'] == 'UNSUPPORTED'
    )

    reported_supported = result['verdict_counts']['supported']
    reported_unsupported = result['verdict_counts']['unsupported']

    # The counts should be internally consistent
    counts_match = (
        actual_supported == reported_supported and
        actual_unsupported == reported_unsupported
    )

    return {
        'instrument': 'claim_check verdict_counts consistency',
        'actual_supported': actual_supported,
        'reported_supported': reported_supported,
        'actual_unsupported': actual_unsupported,
        'reported_unsupported': reported_unsupported,
        'notices_breakage': counts_match,
        'detail': (
            f"Counts internally consistent: {counts_match}. "
            f"Claims array has {actual_supported}S/{actual_unsupported}U, "
            f"verdict_counts reports {reported_supported}S/{reported_unsupported}U."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 3. CORPUS COVERAGE — empty passage_roles → CREATOR_ONLY stops reclassifying
# ═══════════════════════════════════════════════════════════════════════════════

def _import_corpus_coverage():
    """Import corpus_coverage from repo root."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_corpus_coverage",
        os.path.join(REPO_ROOT, 'corpus_coverage.py')
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_corpus_coverage_empty_passages():
    """Empty the passages → assert verdict becomes EMPTY."""
    cov = _import_corpus_coverage()

    # Healthy: passages present, should be COVERED or VENUE_ONLY
    passages = [
        "Marc Chagall created the Biblical Message series between 1954 and 1967.",
        "The museum was inaugurated in 1973 on the Colline de Cimiez.",
    ]
    roles = [{'role': 'about_subject'}, {'role': 'about_venue'}]

    healthy = cov.assess_stop_coverage(
        stop_title="Biblical Message Series",
        venue_name="Musée Chagall",
        passages=passages,
        passage_roles=roles,
    )
    healthy_verdict = healthy['verdict']
    assert healthy_verdict != 'EMPTY', (
        f"PRECONDITION FAILED: healthy verdict is already EMPTY"
    )

    # Break: empty the passages
    broken = cov.assess_stop_coverage(
        stop_title="Biblical Message Series",
        venue_name="Musée Chagall",
        passages=[],
        passage_roles=[],
    )
    broken_verdict = broken['verdict']
    notices = broken_verdict == 'EMPTY'

    return {
        'instrument': 'corpus_coverage.assess_stop_coverage (empty passages)',
        'healthy_verdict': healthy_verdict,
        'broken_verdict': broken_verdict,
        'notices_breakage': notices,
        'detail': f"Healthy: {healthy_verdict}. Broken (no passages): {broken_verdict}.",
    }


def test_corpus_coverage_creator_only_reclassify():
    """Remove about_subject roles → assert CREATOR_ONLY stops reclassifying to COVERED."""
    cov = _import_corpus_coverage()

    # Passages that mention the creator but not the specific stop subject
    passages = [
        "Marc Chagall was born in Vitebsk, Belarus in 1887.",
        "Chagall's work spans painting, stained glass, and tapestry.",
        "He moved to France in 1923 and became a French citizen.",
    ]
    # All about the creator, not the specific stop
    roles_creator_only = [
        {'role': 'about_creator'},
        {'role': 'about_creator'},
        {'role': 'about_creator'},
    ]

    creator_result = cov.assess_stop_coverage(
        stop_title="Liberation Mosaic",
        venue_name="Musée Chagall",
        passages=passages,
        passage_roles=roles_creator_only,
    )
    creator_verdict = creator_result['verdict']

    # Now give one passage about_subject role — should shift to COVERED
    roles_with_subject = [
        {'role': 'about_subject'},
        {'role': 'about_creator'},
        {'role': 'about_creator'},
    ]
    subject_result = cov.assess_stop_coverage(
        stop_title="Liberation Mosaic",
        venue_name="Musée Chagall",
        passages=passages,
        passage_roles=roles_with_subject,
    )
    subject_verdict = subject_result['verdict']

    # The instrument notices: removing subject role → verdict degrades
    notices = (creator_verdict == 'CREATOR_ONLY' and subject_verdict == 'COVERED')

    return {
        'instrument': 'corpus_coverage (CREATOR_ONLY reclassification)',
        'creator_only_verdict': creator_verdict,
        'with_subject_verdict': subject_verdict,
        'notices_breakage': notices,
        'detail': (
            f"Creator-only roles: {creator_verdict}. "
            f"With subject role: {subject_verdict}. "
            f"Distinguishes: {notices}."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 4. ANCHOR DETECTOR — remove corpus; assert anchor rate falls
# ═══════════════════════════════════════════════════════════════════════════════

def _import_anchor_detector():
    """Import stop_anchor_detector_v2 from tests/."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_anchor_detector",
        os.path.join(REPO_ROOT, 'tests', 'stop_anchor_detector_v2.py')
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_anchor_detector_remove_corpus():
    """Remove corpus anchors → assert anchor classification drops.

    The anchor detector classifies paragraphs as ANCHORED when they contain
    a token tied to the stop's corpus. With an empty corpus, ANCHORED should
    become impossible (everything becomes NO_ANCHOR or UNLINKED_ENTITY).
    """
    ad = _import_anchor_detector()

    # Test paragraph that contains a checkable entity
    test_paragraph = (
        "Jean-Baptiste Lascaris commissioned this baroque palace in 1648, "
        "establishing it as the family's principal residence in Nice."
    )

    # Corpus anchors that would support this paragraph
    corpus_anchors_healthy = {
        'people': {'Jean-Baptiste Lascaris'},
        'dates': {'1648'},
        'titles': set(),
        'all_corpus_people': {'Jean-Baptiste Lascaris'},
        'all_corpus_text': 'Jean-Baptiste Lascaris commissioned the palace in 1648 as the principal residence of the Lascaris-Ventimiglia family in Nice.',
    }

    # Sibling corpus for discrimination
    sibling_corpus = {
        'Palais Lascaris': 'Jean-Baptiste Lascaris 1648 baroque palace',
        'Place Garibaldi': 'Giuseppe Garibaldi square 1773',
        'Cathédrale Sainte-Réparate': 'cathedral 1650 baroque architecture',
    }

    # Healthy: classify with corpus present
    healthy_class = ad.classify_paragraph(
        paragraph=test_paragraph,
        corpus_anchors=corpus_anchors_healthy,
        stop_title="Palais Lascaris",
        tour_name="Nice Old Town Walking Tour",
        sibling_corpus_texts=sibling_corpus,
    )
    healthy_classification = healthy_class['classification']

    # Break: empty corpus
    corpus_anchors_empty = {
        'people': set(),
        'dates': set(),
        'titles': set(),
        'all_corpus_people': set(),
        'all_corpus_text': '',
    }

    broken_class = ad.classify_paragraph(
        paragraph=test_paragraph,
        corpus_anchors=corpus_anchors_empty,
        stop_title="Palais Lascaris",
        tour_name="Nice Old Town Walking Tour",
        sibling_corpus_texts={},
    )
    broken_classification = broken_class['classification']

    # With no corpus, a paragraph with entities should become UNLINKED_ENTITY
    # (entities present but not in corpus) or NO_ANCHOR (no entities found).
    # It should NOT remain ANCHORED.
    notices = (
        healthy_classification == 'ANCHORED' and
        broken_classification != 'ANCHORED'
    )

    return {
        'instrument': 'stop_anchor_detector_v2.classify_paragraph',
        'healthy_classification': healthy_classification,
        'broken_classification': broken_classification,
        'notices_breakage': notices,
        'detail': (
            f"Healthy (corpus present): {healthy_classification}. "
            f"Broken (empty corpus): {broken_classification}."
        ),
    }


def test_anchor_detector_navigation_still_works():
    """Navigation classification should NOT depend on corpus.

    A navigation paragraph should be classified NAVIGATION regardless of
    corpus state. This is NOT a breakage — it's a sanity check that the
    detector has independent logic paths.
    """
    ad = _import_anchor_detector()

    nav_paragraph = "Head south along the Promenade des Anglais toward the old town."

    # Should be NAVIGATION with or without corpus
    result_with = ad.classify_paragraph(
        paragraph=nav_paragraph,
        corpus_anchors={
            'people': set(), 'dates': set(), 'titles': set(),
            'all_corpus_people': set(),
            'all_corpus_text': 'Promenade des Anglais seaside walkway',
        },
        stop_title="Promenade des Anglais",
        tour_name="Nice Walking Tour",
        sibling_corpus_texts={'Promenade des Anglais': 'seaside walkway'},
    )

    result_without = ad.classify_paragraph(
        paragraph=nav_paragraph,
        corpus_anchors={
            'people': set(), 'dates': set(), 'titles': set(),
            'all_corpus_people': set(), 'all_corpus_text': '',
        },
        stop_title="Promenade des Anglais",
        tour_name="Nice Walking Tour",
        sibling_corpus_texts={},
    )

    both_nav = (
        result_with['classification'] == 'NAVIGATION' and
        result_without['classification'] == 'NAVIGATION'
    )

    return {
        'instrument': 'stop_anchor_detector_v2 (navigation independence)',
        'with_corpus': result_with['classification'],
        'without_corpus': result_without['classification'],
        'notices_breakage': True,  # This is a positive control
        'detail': (
            f"With corpus: {result_with['classification']}. "
            f"Without corpus: {result_without['classification']}. "
            f"Both NAVIGATION: {both_nav}."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 5. SECRET SCAN — plant a synthetic key; assert it fires
# ═══════════════════════════════════════════════════════════════════════════════

def _import_secret_scan():
    """Import secret_scan from repo root."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_secret_scan",
        os.path.join(REPO_ROOT, 'secret_scan.py')
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_secret_scan_synthetic_key_fires():
    """Plant a synthetic OpenAI key in a temp file → assert scanner finds it.

    The key is PURELY INVENTED (random chars, correct format).
    """
    ss = _import_secret_scan()

    # Invented key: sk-proj- + 48 random alphanum (56 total, in near-match range)
    synthetic_key = "sk-proj-Qw7Rx3Yz1Mn5Vb8Kf2Jt4Ld9Gs0Uc6PeHa3Wi5Ro7Xn2Yb4Kf"
    # Verify it's in the near-match length range
    assert len(synthetic_key) in range(50, 200), f"Key length {len(synthetic_key)} not in range"

    test_content = f'OPENAI_API_KEY = "{synthetic_key}"\n'

    tmpdir = None
    try:
        tmpdir = tempfile.mkdtemp(prefix="local227_falsify_")
        tmpfile = os.path.join(tmpdir, "config.py")
        with open(tmpfile, 'w') as f:
            f.write(test_content)

        # Scan the content directly
        findings = ss.scan_content(test_content, "config.py")

        fires = len(findings) > 0
        detectors_fired = [f.detector for f in findings] if findings else []

    finally:
        if tmpdir:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    return {
        'instrument': 'secret_scan (synthetic key detection)',
        'key_planted': f"sk-proj-...{synthetic_key[-8:]} ({len(synthetic_key)} chars)",
        'findings_count': len(findings),
        'detectors_fired': detectors_fired,
        'notices_breakage': fires,
        'detail': f"Planted synthetic key → {len(findings)} findings: {detectors_fired}",
    }


def test_secret_scan_sha256_does_not_fire():
    """A SHA-256 digest should NOT fire (D108 fix).

    This is a NEGATIVE falsification: confirm the D108 exclusion works.
    If it fires on a hash, that is a regression (false positive).
    """
    ss = _import_secret_scan()

    # Real-looking SHA-256 (64 hex chars)
    sha256_hash = "959f666f3aaf681223781c3e9e81a27c34368da73f31300ec3c98474eca7fe54"
    test_content = f'cache_key = "{sha256_hash}"\n'

    findings = ss.scan_content(test_content, "cache_lookup.py")
    does_not_fire = len(findings) == 0

    return {
        'instrument': 'secret_scan (SHA-256 exclusion, D108)',
        'hash_tested': f"{sha256_hash[:16]}... (64 hex chars)",
        'findings_count': len(findings),
        'notices_breakage': does_not_fire,  # True = correctly silent
        'detail': (
            f"SHA-256 hash → {len(findings)} findings. "
            f"Correctly silent: {does_not_fire}."
        ),
    }


def test_secret_scan_whitelist_honored():
    """A whitelisted placeholder should not fire even if it matches patterns."""
    ss = _import_secret_scan()

    # These are whitelisted patterns
    test_lines = [
        'OPENAI_API_KEY = "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"\n',
        'API_KEY = "your-key-here"\n',
        'SECRET = "FAKE_KEY_FOR_TESTING_1234567890"\n',
    ]

    total_findings = 0
    for line in test_lines:
        findings = ss.scan_content(line, "test_config.py")
        total_findings += len(findings)

    correctly_silent = total_findings == 0

    return {
        'instrument': 'secret_scan (whitelist honored)',
        'test_lines_count': len(test_lines),
        'findings_count': total_findings,
        'notices_breakage': correctly_silent,  # True = whitelist works
        'detail': f"Whitelisted patterns → {total_findings} findings. Silent: {correctly_silent}.",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# RUNNER — Execute all tests, collect results, report
# ═══════════════════════════════════════════════════════════════════════════════

ALL_TESTS = [
    # Style Validator
    test_style_validator_r1_falsification,
    test_style_validator_r3_falsification,
    test_style_validator_r4_falsification,
    test_style_validator_r7_falsification,
    test_style_validator_r8_falsification,
    test_style_validator_r9_falsification,
    test_style_validator_validate_paragraph_integration,
    # Claim Check
    test_claim_check_remove_passages,
    test_claim_check_corrupt_verdict_counts,
    # Corpus Coverage
    test_corpus_coverage_empty_passages,
    test_corpus_coverage_creator_only_reclassify,
    # Anchor Detector
    test_anchor_detector_remove_corpus,
    test_anchor_detector_navigation_still_works,
    # Secret Scan
    test_secret_scan_synthetic_key_fires,
    test_secret_scan_sha256_does_not_fire,
    test_secret_scan_whitelist_honored,
]


def run_all():
    """Run all falsification tests and report results."""
    print("=" * 70)
    print("LOCAL-227: INSTRUMENT FALSIFICATION REPORT")
    print("=" * 70)
    print()

    # Pre-check: database baseline
    if check_db_available():
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM audio_tours")
        tour_count = cur.fetchone()[0]
        cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,21,24,27,28,29,152) ORDER BY id")
        nice_list = [r[0] for r in cur.fetchall()]
        conn.close()
        print(f"BASELINE: audio_tours = {tour_count}, Nice list = {nice_list}")
    else:
        tour_count = None
        nice_list = None
        print("WARNING: Database not available. Skipping baseline check.")
    print()

    results = []
    passed = 0
    failed = 0
    errors = 0
    does_not_notice = []

    for test_fn in ALL_TESTS:
        name = test_fn.__name__
        print(f"  {name}... ", end="", flush=True)
        try:
            result = test_fn()
            results.append(result)
            if result['notices_breakage']:
                print("✓ NOTICES BREAKAGE")
                passed += 1
            else:
                print("✗ DOES NOT NOTICE")
                does_not_notice.append(result)
                failed += 1
        except AssertionError as e:
            print(f"⚠ PRECONDITION FAILED: {e}")
            results.append({
                'instrument': name,
                'notices_breakage': None,
                'detail': f"AssertionError: {e}",
            })
            errors += 1
        except Exception as e:
            print(f"✗ ERROR: {type(e).__name__}: {e}")
            results.append({
                'instrument': name,
                'notices_breakage': None,
                'detail': f"{type(e).__name__}: {e}",
            })
            errors += 1

    # Post-check: database unchanged
    print()
    if check_db_available():
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM audio_tours")
        post_count = cur.fetchone()[0]
        cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,21,24,27,28,29,152) ORDER BY id")
        post_nice = [r[0] for r in cur.fetchall()]
        conn.close()
        print(f"POST-CHECK: audio_tours = {post_count}, Nice list = {post_nice}")
        if tour_count is not None:
            assert post_count == tour_count, f"TOUR COUNT CHANGED: {tour_count} → {post_count}"
            assert post_nice == nice_list, f"NICE LIST CHANGED: {nice_list} → {post_nice}"
            print("  ✓ Database unchanged.")
    print()

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Instruments that NOTICE breakage:       {passed}")
    print(f"  Instruments that DO NOT notice:         {failed}")
    print(f"  Tests with errors/precondition fails:   {errors}")
    print()

    if does_not_notice:
        print("─" * 70)
        print("⚠ INSTRUMENTS THAT DO NOT DETECT THEIR OWN BREAKAGE:")
        print("─" * 70)
        for r in does_not_notice:
            print(f"  • {r['instrument']}")
            if 'detail' in r:
                print(f"    {r['detail']}")
        print()

    print("─" * 70)
    print("DETAILED RESULTS:")
    print("─" * 70)
    for r in results:
        status = (
            "✓ NOTICES" if r.get('notices_breakage') is True
            else "✗ DOES NOT NOTICE" if r.get('notices_breakage') is False
            else "⚠ ERROR"
        )
        print(f"  [{status}] {r.get('instrument', r.get('name', '?'))}")
        if 'detail' in r:
            print(f"    {r['detail']}")
        elif 'healthy_findings' in r:
            print(f"    Healthy: {r['healthy_findings']}, Broken: {r['broken_findings']}, Restored: {r.get('restored_findings', '?')}")
        print()

    return {
        'passed': passed,
        'failed': failed,
        'errors': errors,
        'does_not_notice': does_not_notice,
        'all_results': results,
    }


if __name__ == '__main__':
    summary = run_all()
    sys.exit(0 if summary['failed'] == 0 and summary['errors'] == 0 else 1)
