#!/usr/bin/env python3
"""test_local462_request_and_structure.py — acceptance tests for LOCAL-462.

Tests Request_to_AI and Structure_AI_output against the 9 D433 stops:
- TOUR_MFA_20260812_2030.txt (museum exhibition) — stops 1, 2, 3
- fruitlands_museum_tour.txt (museum) — stops 1, 2, 3
- Beacon_Hill__Boston_walking_tour_20260714_135649.txt (walking tour) — stops 1, 2, 3

All tests use fakes for the AI callable — no network, no API key.
"""
import os
import sys
import re

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from request_and_structure import request_to_ai, structure_ai_output, _credit_line_candidates
from interrogation_matrix import (
    build_matrix, extract_stops, extract_tour_header, infer_tour_type, SLOTS
)
from story_opportunity_scan import measure, _fold, split_sentences


def load_tour(filename):
    path = os.path.join(HERE, filename)
    return open(path, encoding='utf-8').read()


def get_matrix_and_context(filename, stop_num):
    """Load a tour and build the matrix + stop_text for a specific stop."""
    full_text = load_tour(filename)
    stops = extract_stops(full_text)
    assert stop_num in stops, f"Stop {stop_num} not found in {filename}"
    tour_type = infer_tour_type(extract_tour_header(full_text), stops[stop_num]['text'])
    matrix = build_matrix(
        stop_text=stops[stop_num]['text'],
        tour_type=tour_type,
        tour_context=full_text,
    )
    return matrix, stops[stop_num]['text'], full_text


MFA_FILE = 'TOUR_MFA_20260812_2030.txt'
FRUITLANDS_FILE = 'fruitlands_museum_tour.txt'
BEACON_FILE = 'Beacon_Hill__Boston_walking_tour_20260714_135649.txt'


# ═══════════════════════════════════════════════════════════════════════════════
# ACCEPTANCE 1: MFA stop 2 request shape
# ═══════════════════════════════════════════════════════════════════════════════

def test_mfa_stop2_request_contains_exhibition_as_medium():
    """MFA stop 2: the exhibition name appears as medium in the request."""
    matrix, _, _ = get_matrix_and_context(MFA_FILE, 2)
    result = request_to_ai(matrix)
    # medium = exhibition name
    assert matrix['medium']['value'] == 'Picasso, Miro, Dali: Unbound'
    assert 'Picasso, Miro, Dali: Unbound' in result['request']


def test_mfa_stop2_request_contains_museum_as_venue():
    """MFA stop 2: the museum appears as venue in the request."""
    matrix, _, _ = get_matrix_and_context(MFA_FILE, 2)
    result = request_to_ai(matrix)
    assert 'Museum of Fine Arts, Boston' in result['request']


def test_mfa_stop2_request_contains_moses_and_monotheism():
    """MFA stop 2: canonical_title Moses and Monotheism is in the request."""
    matrix, _, _ = get_matrix_and_context(MFA_FILE, 2)
    result = request_to_ai(matrix)
    assert 'Moses and Monotheism' in result['request']


def test_mfa_stop2_hogarth_press_in_unverified():
    """MFA stop 2: The Hogarth Press (CLAIMED) appears in unverified_terms."""
    matrix, _, _ = get_matrix_and_context(MFA_FILE, 2)
    result = request_to_ai(matrix)
    assert 'The Hogarth Press' in result['unverified_terms']


def test_mfa_stop2_no_english_title_duplication():
    """MFA stop 2: english_title == canonical_title, should not appear twice."""
    matrix, _, _ = get_matrix_and_context(MFA_FILE, 2)
    result = request_to_ai(matrix)
    # Should have only one occurrence of "Moses and Monotheism"
    count = result['request'].count('Moses and Monotheism')
    assert count == 1, f"Found {count} occurrences, expected 1"


# ═══════════════════════════════════════════════════════════════════════════════
# ACCEPTANCE 2: Walking tour — grammatical with ABSENT slots
# ═══════════════════════════════════════════════════════════════════════════════

def test_beacon_hill_stop1_no_dangling_and():
    """Beacon Hill stop 1: printed_by ABSENT → no dangling 'and'."""
    matrix, _, _ = get_matrix_and_context(BEACON_FILE, 1)
    result = request_to_ai(matrix)
    # Must not have "and ?" or "and?" at the end
    assert 'and ?' not in result['request']
    assert 'and?' not in result['request']
    # Must not have "and None" or "and —"
    assert 'and None' not in result['request']
    assert 'and —' not in result['request']


def test_beacon_hill_printed_by_absent():
    """Beacon Hill: printed_by is ABSENT in the matrix."""
    matrix, _, _ = get_matrix_and_context(BEACON_FILE, 1)
    assert matrix['printed_by']['status'] == 'ABSENT'


def test_all_nine_requests_are_grammatical():
    """All 9 requests are grammatical — no 'and None', no 'and —', no trailing 'and'."""
    tours = [
        (MFA_FILE, [1, 2, 3]),
        (FRUITLANDS_FILE, [1, 2, 3]),
        (BEACON_FILE, [1, 2, 3]),
    ]
    for tour_file, stop_nums in tours:
        full_text = load_tour(tour_file)
        stops = extract_stops(full_text)
        tour_type = infer_tour_type(
            extract_tour_header(full_text), stops[stop_nums[0]]['text'])
        for n in stop_nums:
            matrix = build_matrix(
                stop_text=stops[n]['text'], tour_type=tour_type, tour_context=full_text)
            result = request_to_ai(matrix)
            req = result['request']
            # No dangling connectors
            assert 'and None' not in req, f"{tour_file} stop {n}: 'and None'"
            assert 'and —' not in req, f"{tour_file} stop {n}: 'and —'"
            assert not re.search(r'\band\s*\?$', req), f"{tour_file} stop {n}: trailing 'and'"
            # Must end with ?
            assert req.endswith('?'), f"{tour_file} stop {n}: no trailing '?'"
            # Must start correctly
            assert req.startswith('What story can be told to visitors'), \
                f"{tour_file} stop {n}: bad start"


# ═══════════════════════════════════════════════════════════════════════════════
# ACCEPTANCE 3: Structure_AI_output with fakes
# ═══════════════════════════════════════════════════════════════════════════════

def test_structure_summarize_when_too_long():
    """With a fake returning 8 sentences, the routine issues a summarize call and returns <=5."""
    matrix, stop_text, full_text = get_matrix_and_context(MFA_FILE, 2)

    eight_sentences = (
        "First sentence about the topic. "
        "Second sentence provides more detail. "
        "Third sentence adds context. "
        "Fourth sentence discusses implications. "
        "Fifth sentence considers the history. "
        "Sixth sentence raises a question. "
        "Seventh sentence offers a perspective. "
        "Eighth sentence concludes the thought."
    )
    assert len(split_sentences(eight_sentences)) == 8

    # Fake that returns a 3-sentence summary when asked to summarize
    summary_3 = (
        "A concise summary of the main points. "
        "The key insight connects history to art. "
        "This collaboration remains influential today."
    )
    calls = []

    def fake_ask(prompt):
        calls.append(prompt)
        return summary_3

    result = structure_ai_output(
        answer=eight_sentences,
        matrix=matrix,
        ask=fake_ask,
        _stop_text=stop_text,
        _tour_context=full_text,
    )

    assert result['status'] == 'OK'
    assert result['sentences'] == 3
    # The summarize call was issued
    assert len(calls) == 1
    assert calls[0].startswith("Summarize the following into 3 sentences:")
    assert result['asks'] == 1


def test_structure_retry_when_too_short():
    """With a fake returning 1 sentence, it substitutes credit_line and retries."""
    matrix, stop_text, full_text = get_matrix_and_context(MFA_FILE, 2)

    one_sentence = "A single inadequate sentence about the topic."
    assert len(split_sentences(one_sentence)) == 1

    # On retry with new credit_line, return 4 sentences (acceptable)
    four_sentences = (
        "The substitute topic reveals new connections. "
        "Historical context enriches the narrative. "
        "The audience gains deeper understanding. "
        "This story enhances the visitor experience."
    )
    call_count = [0]

    def fake_ask(prompt):
        call_count[0] += 1
        return four_sentences

    result = structure_ai_output(
        answer=one_sentence,
        matrix=matrix,
        ask=fake_ask,
        _stop_text=stop_text,
        _tour_context=full_text,
    )

    assert result['status'] == 'OK'
    assert result['sentences'] == 4
    # The chain shows the substitution: original credit_line + at least one substitute
    assert len(result['chain']) >= 2, f"Chain should show substitution: {result['chain']}"
    # Original credit_line was 'Sigmund Freud'
    assert result['chain'][0] == 'Sigmund Freud'
    # A substitute was tried
    assert result['chain'][1] != result['chain'][0]
    assert result['asks'] >= 1


def test_structure_retry_chain_shows_substitution():
    """Verify the chain explicitly tracks each credit_line tried."""
    matrix, stop_text, full_text = get_matrix_and_context(MFA_FILE, 2)

    one_sentence = "Too short."
    call_count = [0]

    # First retry also returns too short, second retry returns 3 sentences
    def fake_ask(prompt):
        call_count[0] += 1
        if call_count[0] <= 1:
            return "Still just one sentence here."
        return (
            "Now we have a proper three-sentence response. "
            "The second sentence adds important context. "
            "The third sentence completes the thought."
        )

    result = structure_ai_output(
        answer=one_sentence,
        matrix=matrix,
        ask=fake_ask,
        _stop_text=stop_text,
        _tour_context=full_text,
    )

    assert result['status'] == 'OK'
    # Chain should have original + at least 2 substitutions
    assert len(result['chain']) >= 3, f"Expected chain >= 3, got {result['chain']}"


# ═══════════════════════════════════════════════════════════════════════════════
# ACCEPTANCE 4: Retry exhaustion → INSUFFICIENT, no raise
# ═══════════════════════════════════════════════════════════════════════════════

def test_structure_exhaustion_returns_insufficient():
    """Retry exhaustion returns INSUFFICIENT and does not raise."""
    matrix, stop_text, full_text = get_matrix_and_context(MFA_FILE, 2)

    one_sentence = "Perpetually too short."

    def fake_ask(prompt):
        return "Still just one sentence."

    result = structure_ai_output(
        answer=one_sentence,
        matrix=matrix,
        ask=fake_ask,
        max_retries=2,
        _stop_text=stop_text,
        _tour_context=full_text,
    )

    assert result['status'] == 'INSUFFICIENT'
    assert len(result['chain']) >= 2  # original + retries attempted
    # Did not raise


def test_structure_exhaustion_no_candidates_returns_insufficient():
    """If no more candidates available, returns INSUFFICIENT gracefully."""
    matrix, stop_text, full_text = get_matrix_and_context(MFA_FILE, 2)

    one_sentence = "Too short."

    def fake_ask(prompt):
        return "Also too short."

    # Use high max_retries to exhaust candidates
    result = structure_ai_output(
        answer=one_sentence,
        matrix=matrix,
        ask=fake_ask,
        max_retries=100,  # More than candidates available
        _stop_text=stop_text,
        _tour_context=full_text,
    )

    assert result['status'] == 'INSUFFICIENT'
    # Did not raise


# ═══════════════════════════════════════════════════════════════════════════════
# ACCEPTANCE: 3-5 sentences accepted as-is
# ═══════════════════════════════════════════════════════════════════════════════

def test_structure_accepts_3_to_5_sentences():
    """An answer with 3-5 sentences is accepted directly."""
    matrix, stop_text, full_text = get_matrix_and_context(MFA_FILE, 2)

    four_sentences = (
        "This is a well-structured response. "
        "It provides historical context. "
        "The connection to the artwork is clear. "
        "Visitors will appreciate this narrative."
    )
    calls = []

    def fake_ask(prompt):
        calls.append(prompt)
        return "should not be called"

    result = structure_ai_output(
        answer=four_sentences,
        matrix=matrix,
        ask=fake_ask,
        _stop_text=stop_text,
        _tour_context=full_text,
    )

    assert result['status'] == 'OK'
    assert result['sentences'] == 4
    assert result['text'] == four_sentences
    assert len(calls) == 0  # Never called ask
    assert result['asks'] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# DETERMINISM
# ═══════════════════════════════════════════════════════════════════════════════

def test_request_is_deterministic():
    """Same matrix → same request, always."""
    matrix, _, _ = get_matrix_and_context(MFA_FILE, 2)
    r1 = request_to_ai(matrix)
    r2 = request_to_ai(matrix)
    assert r1 == r2


# ═══════════════════════════════════════════════════════════════════════════════
# CREDIT LINE CANDIDATES — ordered list for Routine 2
# ═══════════════════════════════════════════════════════════════════════════════

def test_credit_line_candidates_ordered():
    """Candidates are ordered FLAT > MENTIONED > DANGLING, never DEVELOPED."""
    full_text = load_tour(MFA_FILE)
    stops = extract_stops(full_text)
    stop_text = stops[2]['text']
    matrix = build_matrix(stop_text=stop_text, tour_context=full_text)
    exclude = [
        matrix.get(s, {}).get('value', '')
        for s in ['canonical_title', 'english_title', 'artist',
                  'publisher', 'printed_by', 'venue', 'medium']
    ]
    candidates = _credit_line_candidates(stop_text, exclude)
    assert len(candidates) >= 2, f"Expected at least 2 candidates, got {candidates}"
    # First one should be the current credit_line (Sigmund Freud)
    assert candidates[0] == 'Sigmund Freud'


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v']))
