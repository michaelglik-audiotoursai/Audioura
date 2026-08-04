#!/usr/bin/env python3
"""sentence_group_scorer.py — LOCAL-220: Score at the sentence group, not the paragraph.

Splits paragraphs into sentence groups (1–3 sentences on one idea),
classifies each group (NAVIGATION / CONTENT / CONNECTIVE), and emits
per-group records with style verdicts, claim verdicts, and a
PUBLISHABLE / BLOCKED flag.

Does NOT compute a combined quality score (Michael has not settled thresholds).
Emits the INPUTS to a score, not a score.

Does NOT wire into generation or rewrite anything.

Deterministic. No LLM. $0.00 spend.
"""
import os
import sys
import re
import json
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))
from db_connection import get_connection

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from style_validator_detector import (
    validate_paragraph,
    check_r1_imperatives,
    check_r2_questions,
    check_r3_suggestive_exploration,
    check_r4_prescribed_feeling,
    check_r7_hallucinated_sensory,
    check_r8_prompt_leakage,
    check_r9_generic,
    _is_style_navigation_sentence,
    _is_style_navigation_paragraph,
    _split_sentences,
)
from claim_check import check_paragraph as check_claims, extract_claims


# ═══════════════════════════════════════════════════════════════════════════════
# SENTENCE GROUP SPLITTING
# ═══════════════════════════════════════════════════════════════════════════════

# Transition / shift markers that suggest a new group begins
_GROUP_BREAK_SIGNALS = [
    # Temporal shift
    r'^(as you|when you|upon|once you)',
    # Spatial shift
    r'^(from (here|this|the)|heading|walking|pedal|continue|proceed)',
    # New subject / topic marker
    r'^(the nearby|nearby|the)',
    # Contrast / addition
    r'^(this historical|this|however|moreover|furthermore|additionally)',
]

_GROUP_BREAK_RE = re.compile(
    '|'.join(_GROUP_BREAK_SIGNALS), re.IGNORECASE
)

# Signals that a sentence introduces a new idea / subject
_SUBJECT_SHIFT_PATTERNS = [
    # New proper noun introduction (sentence starts with a proper-noun-heavy phrase)
    r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+',
    # Date introduction
    r'\b(in|around|by|since|during)\s+\d{3,4}\b',
    # "Known as" / naming patterns
    r'known as',
]


def _sentences_share_subject(s1: str, s2: str) -> bool:
    """Heuristic: do two sentences share a likely subject (proper nouns in common)?"""
    def _extract_proper_nouns(text):
        # Simple heuristic: capitalized multi-word sequences not at sentence start
        words = text.split()
        nouns = set()
        for i, w in enumerate(words):
            if i > 0 and w[0:1].isupper() and w.isalpha():
                nouns.add(w.lower())
            # Also get multi-word proper nouns
            if i > 0 and len(w) > 2 and w[0:1].isupper():
                nouns.add(w.lower())
        return nouns

    nouns1 = _extract_proper_nouns(s1)
    nouns2 = _extract_proper_nouns(s2)
    if not nouns1 or not nouns2:
        return False
    overlap = nouns1 & nouns2
    return len(overlap) >= 1


def split_into_sentence_groups(paragraph: str) -> List[List[str]]:
    """Split a paragraph into sentence groups (1–3 sentences on one idea).

    Approximates Michael's grouping heuristic:
    - Navigation sentences cluster together
    - A shift in subject (new proper noun, new date, spatial change) starts a new group
    - Generic/connective sentences form their own group
    - Groups are capped at 3 sentences (Michael never grouped more)

    Returns a list of groups, each group is a list of sentences.
    """
    sentences = _split_sentences(paragraph)
    sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) >= 10]

    if not sentences:
        return []

    groups: List[List[str]] = []
    current_group: List[str] = [sentences[0]]

    for i in range(1, len(sentences)):
        sent = sentences[i]
        prev = sentences[i - 1]

        should_break = False

        # Rule 1: Cap at 3 sentences per group
        if len(current_group) >= 3:
            should_break = True

        # Rule 2: Navigation vs non-navigation boundary
        elif _is_style_navigation_sentence(sent) != _is_style_navigation_sentence(prev):
            should_break = True

        # Rule 3: Generic sentence (R9 candidate) forms its own group
        elif _is_generic_sentence(sent) and not _is_generic_sentence(prev):
            should_break = True
        elif _is_generic_sentence(prev) and not _is_generic_sentence(sent):
            should_break = True

        # Rule 4: Subject shift — new sentence introduces different proper nouns
        elif _has_subject_shift(sent, prev):
            should_break = True

        # Rule 5: Imperative/instruction shift
        elif _is_instruction(sent) and not _is_instruction(prev):
            should_break = True
        elif _is_instruction(prev) and not _is_instruction(sent):
            should_break = True

        if should_break:
            groups.append(current_group)
            current_group = [sent]
        else:
            current_group.append(sent)

    if current_group:
        groups.append(current_group)

    return groups


def _is_generic_sentence(sentence: str) -> bool:
    """Quick check: does R9 fire on this sentence?"""
    findings = check_r9_generic(sentence)
    return len(findings) > 0


def _is_instruction(sentence: str) -> bool:
    """Does the sentence contain an instruction to the user (R1 imperative)?"""
    findings = check_r1_imperatives(sentence)
    return len(findings) > 0


def _has_subject_shift(current: str, previous: str) -> bool:
    """Does the current sentence introduce a substantially different subject?"""
    # If they share proper nouns, they're on the same topic
    if _sentences_share_subject(current, previous):
        return False

    # If current sentence starts with a new proper noun not in previous
    words_curr = current.split()
    if len(words_curr) >= 2:
        first_two = ' '.join(words_curr[:2])
        # New sentence starting with "The <ProperNoun>" pattern
        if (words_curr[0] == 'The' and len(words_curr) > 1
                and words_curr[1][0:1].isupper() and words_curr[1].isalpha()
                and words_curr[1].lower() not in previous.lower()):
            return True

    # Date shift: current mentions a date not present in previous
    dates_curr = re.findall(r'\b\d{4}\b', current)
    dates_prev = re.findall(r'\b\d{4}\b', previous)
    if dates_curr and not dates_prev:
        # New date introduced — possible topic shift, but only if no shared nouns
        if not _sentences_share_subject(current, previous):
            return True

    return False


# ═══════════════════════════════════════════════════════════════════════════════
# GROUP CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

def classify_group(sentences: List[str]) -> str:
    """Classify a sentence group as NAVIGATION, CONTENT, or CONNECTIVE.

    NAVIGATION: route-movement instructions (directions, wayfinding).
        Includes cycling/biking/driving directions, exit/turn instructions,
        any imperative that moves the listener along a physical route.
    CONTENT: factual/descriptive about a specific place or thing.
    CONNECTIVE: transitions, generic filler, meta-text.
    """
    nav_count = sum(1 for s in sentences if _is_navigation_for_classification(s))
    generic_count = sum(1 for s in sentences if _is_generic_sentence(s))

    # If majority is navigation
    if nav_count > len(sentences) / 2:
        return 'NAVIGATION'

    # If all are generic / no specifics
    if generic_count == len(sentences):
        return 'CONNECTIVE'

    # Check for connective patterns: very short, no proper nouns/dates/numbers
    group_text = ' '.join(sentences)
    has_proper_noun = bool(re.search(r'[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]+)*', group_text))
    has_date = bool(re.search(r'\b\d{3,4}\b', group_text))
    has_number = bool(re.search(r'\b\d+(?:\.\d+)?\s*(?:km|m|feet|ft|meters|miles|century|centuries)\b', group_text, re.IGNORECASE))

    if not has_proper_noun and not has_date and not has_number:
        # No specifics at all — likely connective
        if len(group_text) < 200:
            return 'CONNECTIVE'

    return 'CONTENT'


# Extended navigation patterns for GROUP CLASSIFICATION (broader than style exemption).
# The style validator's navigation test is intentionally narrow (D55 context) —
# it only exempts route-movement from style rules. But for GROUP CLASSIFICATION
# we need to identify all directions/wayfinding, including cycling/biking/driving.
_CLASSIFY_NAV_PATTERNS = re.compile(
    r'(?i)\b('
    r'start\s+(?:biking|cycling|walking|driving|riding|heading|going)'
    r'|take\s+the\s+(?:first|second|third|fourth|next|left|right)\s+(?:exit|turn|road|path|lane)'
    r'|continue\s+(?:straight|on|along|past|down|until|to)'
    r'|head\s+(?:south|north|east|west|left|right|straight|towards?|along)'
    r'|turn\s+(?:left|right|onto|at|into)'
    r'|follow\s+(?:the|this|signs?)'
    r'|cross\s+(?:the|this|at)'
    r'|proceed\s+(?:to|along|straight|down|until)'
    r'|bike\s+(?:along|down|to|towards?|south|north|east|west)'
    r'|cycle\s+(?:along|down|to|towards?|south|north|east|west)'
    r'|ride\s+(?:along|down|to|towards?|south|north|east|west)'
    r'|walk\s+(?:along|down|to|towards?|south|north|east|west)'
    r'|make\s+your\s+way'
    r'|find\s+your\s+way'
    r')\b'
)


def _is_navigation_for_classification(sentence: str) -> bool:
    """Broader navigation test for group classification (not for style exemption).

    Recognizes cycling/biking directions that the style validator's narrower
    test misses. Michael scored cycling directions 5/5 — they must classify
    as NAVIGATION.
    """
    # First check the style validator's test
    if _is_style_navigation_sentence(sentence):
        return True

    # Extended patterns for classification
    if _CLASSIFY_NAV_PATTERNS.search(sentence):
        return True

    return False


# ═══════════════════════════════════════════════════════════════════════════════
# PER-GROUP RECORD
# ═══════════════════════════════════════════════════════════════════════════════

def score_group(
    sentences: List[str],
    stop_title: str,
    venue_name: str,
    passages: List[str],
    other_stop_passages: Optional[List[str]] = None,
) -> Dict:
    """Emit a per-group record with style verdicts, claim verdicts, and publishable flag.

    The PUBLISHABLE / BLOCKED flag is kept SEPARATE from any quality score (D94).
    A group can be excellent quality and still blocked (unsupported claims).
    A group can be publishable and still low quality (vague but true).

    Args:
        sentences: The sentences in this group.
        stop_title: Title of the stop.
        venue_name: Name of the venue.
        passages: Corpus passages for this stop.
        other_stop_passages: Corpus passages for other stops.

    Returns:
        {
            'sentences': [...],
            'group_text': str,
            'classification': 'NAVIGATION' | 'CONTENT' | 'CONNECTIVE',
            'style_verdicts': {
                'rules_violated': [...],
                'findings': [...],
            },
            'claim_verdicts': {
                'claims': [...],
                'unsupported_count': int,
                'verdict_counts': {...},
            },
            'publishable': True | False,
            'block_reasons': [...],
        }
    """
    group_text = ' '.join(sentences)
    classification = classify_group(sentences)

    # ─── Style verdicts (R1–R4, R7, R8, R9) ─────────────────────────────
    # Navigation groups are exempt from style rules
    style_findings = []
    if classification != 'NAVIGATION':
        for sent in sentences:
            if len(sent) < 10:
                continue
            if _is_style_navigation_sentence(sent):
                continue
            style_findings.extend(check_r1_imperatives(sent))
            style_findings.extend(check_r2_questions(sent))
            style_findings.extend(check_r3_suggestive_exploration(sent))
            style_findings.extend(check_r4_prescribed_feeling(sent))
            style_findings.extend(check_r7_hallucinated_sensory(sent))
            style_findings.extend(check_r8_prompt_leakage(sent))
            style_findings.extend(check_r9_generic(sent))

    rules_violated = sorted(set(f['rule_id'] for f in style_findings))

    style_verdicts = {
        'rules_violated': rules_violated,
        'findings': style_findings,
    }

    # ─── Claim verdicts (via claim_check, unchanged) ─────────────────────
    # Check CONTENT groups for claims. Navigation and connective have no
    # checkable claims. Even with empty passages, claim_check identifies
    # claims and marks them UNSUPPORTED — that is the correct two-axis shape
    # (D94): excellent quality AND blocked for being unverifiable.
    if classification == 'CONTENT':
        claim_result = check_claims(
            group_text,
            stop_title=stop_title,
            venue_name=venue_name,
            passages=passages if passages else [],
            other_stop_passages=other_stop_passages,
        )
    else:
        claim_result = {
            'claims': [],
            'unsupported_count': 0,
            'verdict_counts': {
                'supported': 0,
                'supported_elsewhere': 0,
                'unsupported': 0,
                'contradicted': 0,
                'not_checkable': 0,
            },
        }

    # ─── PUBLISHABLE / BLOCKED flag ─────────────────────────────────────
    # Two axes (D94): quality is separate from publishability.
    # Blocked if:
    #   1. Any CONTRADICTED claim (hard block, D99)
    #   2. Any UNSUPPORTED claim (block until sourced or removed)
    #   3. R9_GENERIC fires (sentence should be deleted, not published)
    block_reasons = []

    if claim_result['verdict_counts'].get('contradicted', 0) > 0:
        block_reasons.append('CONTRADICTED_CLAIM')

    if claim_result['verdict_counts'].get('unsupported', 0) > 0:
        block_reasons.append('UNSUPPORTED_CLAIM')

    if 'R9_GENERIC' in rules_violated:
        block_reasons.append('GENERIC_DELETE')

    publishable = len(block_reasons) == 0

    return {
        'sentences': sentences,
        'group_text': group_text,
        'classification': classification,
        'style_verdicts': style_verdicts,
        'claim_verdicts': {
            'claims': claim_result['claims'],
            'unsupported_count': claim_result['unsupported_count'],
            'verdict_counts': claim_result['verdict_counts'],
        },
        'publishable': publishable,
        'block_reasons': block_reasons,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# FULL PARAGRAPH PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def score_paragraph_groups(
    paragraph: str,
    stop_title: str,
    venue_name: str,
    passages: List[str],
    other_stop_passages: Optional[List[str]] = None,
) -> List[Dict]:
    """Split a paragraph into groups, classify, and score each.

    Returns a list of per-group records.
    """
    groups = split_into_sentence_groups(paragraph)
    records = []

    for group_sentences in groups:
        record = score_group(
            sentences=group_sentences,
            stop_title=stop_title,
            venue_name=venue_name,
            passages=passages,
            other_stop_passages=other_stop_passages,
        )
        records.append(record)

    return records
