#!/usr/bin/env python3
"""stop_claim_audit.py — LOCAL-458: Role-claim audit gate for exhibition-scoped museum tours.

Extracts ROLE → AGENT claims from delivered prose (e.g. "published by The Hogarth Press",
"commissioned by X", "printed by X") and checks each against:
  1. The stop record (publisher, credit_line, artist fields).
  2. The grounding corpus (exhibition page_text).

Verdicts:
  RECORD     — agent matches a stop-record field (publisher/credit_line/artist).
  EVIDENCE   — agent appears in the grounding corpus (page_text).
  INVENTED   — record slot is EMPTY and agent is absent from corpus.
  CONTRADICTS — record slot has a DIFFERENT value (not yet enforced as a drop; logged only).

Gate rule (LOCAL-458):
  A sentence containing a ROLE→AGENT claim with verdict INVENTED is dropped.
  The gate does NOT need to know the true value — only that the system never had one.

Design:
  - No LLM calls. Entirely deterministic.
  - The gate never adds text, only removes.
  - Removal granularity: whole sentences on sentence boundaries.
  - Article-led entity spans ("The Hogarth Press") are checked in BOTH forms:
    with the article AND with the article stripped.
"""

import re
from typing import Dict, List, Optional, Set, Tuple


# ═══════════════════════════════════════════════════════════════════════════════
# ROLE CLAIM EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

# Roles that link an agent to a published/produced/commissioned work.
# Each pattern captures the agent name that follows.
_ROLE_VERBS = (
    'published',
    'produced',
    'commissioned',
    'printed',
    'issued',
    'released',
    'distributed',
    'founded',
    'established',
)

# Pattern: "published by <Agent>" or "<Agent>... published this"
# We also catch possessive forms: "The Hogarth Press's decision to publish"
_ROLE_BY_PATTERN = re.compile(
    r'\b(?:' + '|'.join(_ROLE_VERBS) + r')\s+by\s+'
    r"([A-Z][A-Za-z\u00C0-\u00FF\s'\u2019\-&]+?)(?:\.|,|\s+in\s+|\s+on\s+|\s+at\s+|\s+to\s+|\s+for\s+|\s+this\s+|\s+the\s+|\s+a\s+|\s+through\s+|\s+further\s+)",
    re.IGNORECASE,
)

# [LOCAL-473] ACTIVE VOICE: "<Agent> printed this work", "Tériade published this book".
#
# The gate matched passive voice only, and the D472 release run shipped the Hogarth
# Press fabrication for the FIFTH time with the gate reporting `0 role claims` —
# because the model wrote "The Hogarth Press, known for its groundbreaking
# publications, printed this work". A false negative in a safety gate.
#
# The `(?:,[^,.]{0,80},)?` is the appositive between subject and verb, matched but
# NOT captured, so the agent stays "The Hogarth Press" rather than swallowing
# "known for its groundbreaking publications". The object must be a determiner plus
# a work noun — "this work", "the edition" — which is what keeps
# "Dalí printed his own name" and "the exhibition published a catalogue of visitor
# numbers" from being read as production claims.
_ROLE_ACTIVE_PATTERN = re.compile(
    r"\b((?:The\s+)?[A-Z][A-Za-zÀ-ÿ'’\-&]+"
    r"(?:\s+[A-Z][A-Za-zÀ-ÿ'’\-&]+){0,3})"
    r"(?:\s*,[^,.]{0,80},)?\s+"
    r"(" + '|'.join(_ROLE_VERBS) + r")\s+"
    r"(?:this|the|these|that)\s+"
    r"(?:work|book|edition|volume|portfolio|suite|series|set|album|"
    r"prints?|plates?|lithographs?|etchings?|drypoints?|illustrations?)\b"
)

# Pattern: "<Agent>, <role descriptor>" e.g. "The Hogarth Press, known for its publication"
# or "<Agent>'s decision to publish"
_POSSESSIVE_PUBLISH_PATTERN = re.compile(
    r"\b([A-Z][A-Za-z\u00C0-\u00FF\s'\u2019\-&]+?)(?:'s|\u2019s)\s+"
    r"(?:decision|choice|role|effort|work)\s+to\s+"
    r"(?:publish|print|produce|commission|issue|release|distribute)",
    re.IGNORECASE,
)

# Pattern: "published/produced/printed ... by <Agent>" in passive constructions
# e.g. "this edition, produced by The Hogarth Press" or "a text published by The Hogarth Press"
_PASSIVE_ROLE_PATTERN = re.compile(
    r'(?:text|edition|book|work|volume|publication|series|catalogue|catalog)\s+'
    r'(?:published|produced|printed|issued|released|distributed|commissioned)\s+by\s+'
    r"([A-Z][A-Za-z\u00C0-\u00FF\s'\u2019\-&]+?)(?:\.|,|\s+in\s+|\s+on\s+|\s+at\s+|\s+to\s+|\s+for\s+|\s+this\s+|\s+the\s+|\s+a\s+|\s+further\s+)",
    re.IGNORECASE,
)

# Map from role verb to the stop-record field that would contain the answer
_ROLE_TO_RECORD_FIELD = {
    'published': 'publisher',
    'produced': 'publisher',
    'printed': 'publisher',
    'issued': 'publisher',
    'released': 'publisher',
    'distributed': 'publisher',
    'commissioned': 'credit_line',
    'founded': 'credit_line',
    'established': 'credit_line',
}


def _strip_leading_article(name: str) -> str:
    """Strip leading 'The/A/An' from a name, returning the bare form.

    'The Hogarth Press' → 'Hogarth Press'
    'A New Gallery' → 'New Gallery'
    """
    m = re.match(r'^(?:The|A|An)\s+', name, re.IGNORECASE)
    if m:
        return name[m.end():]
    return name


def _normalize_for_search(text: str) -> str:
    """Lowercase, collapse whitespace for substring search."""
    return re.sub(r'\s+', ' ', text.lower()).strip()


def _agent_in_text(agent: str, text: str) -> bool:
    """Check if agent name (or its article-stripped form) appears in text.

    Checks both the full form and the article-stripped form.
    Case-insensitive substring match.
    """
    if not agent or not text:
        return False
    text_lower = _normalize_for_search(text)
    # Check full name
    if _normalize_for_search(agent) in text_lower:
        return True
    # Check without leading article
    bare = _strip_leading_article(agent)
    if bare != agent and _normalize_for_search(bare) in text_lower:
        return True
    return False


def extract_role_claims(text: str) -> List[Dict]:
    """Extract ROLE → AGENT claims from prose text.

    Returns list of dicts:
        {'role': str, 'agent': str, 'agent_bare': str, 'sentence': str}

    'agent_bare' is the agent with any leading article stripped.
    """
    claims = []
    seen_agents = set()

    # Find "verb by Agent" patterns
    for m in _ROLE_BY_PATTERN.finditer(text):
        agent = m.group(1).strip().rstrip('.')
        if not agent or len(agent) < 3:
            continue
        agent_key = _normalize_for_search(agent)
        if agent_key in seen_agents:
            continue
        seen_agents.add(agent_key)
        # Determine which role verb was used
        match_text = m.group(0).lower()
        role = 'publisher'
        for verb in _ROLE_VERBS:
            if verb in match_text:
                role = _ROLE_TO_RECORD_FIELD.get(verb, 'publisher')
                break
        claims.append({
            'role': role,
            'agent': agent,
            'agent_bare': _strip_leading_article(agent),
            'sentence': _find_sentence_containing(text, m.start(), m.end()),
        })

    # [LOCAL-473] Active voice: "<Agent> printed this work"
    for m in _ROLE_ACTIVE_PATTERN.finditer(text):
        agent = m.group(1).strip().rstrip('.,')
        if not agent or len(agent) < 3:
            continue
        agent_key = _normalize_for_search(agent)
        if agent_key in seen_agents:
            continue
        seen_agents.add(agent_key)
        claims.append({
            'role': _ROLE_TO_RECORD_FIELD.get(m.group(2).lower(), 'publisher'),
            'agent': agent,
            'agent_bare': _strip_leading_article(agent),
            'sentence': _find_sentence_containing(text, m.start(), m.end()),
        })

    # Find possessive publish patterns: "Agent's decision to publish"
    for m in _POSSESSIVE_PUBLISH_PATTERN.finditer(text):
        agent = m.group(1).strip().rstrip('.')
        if not agent or len(agent) < 3:
            continue
        agent_key = _normalize_for_search(agent)
        if agent_key in seen_agents:
            continue
        seen_agents.add(agent_key)
        claims.append({
            'role': 'publisher',
            'agent': agent,
            'agent_bare': _strip_leading_article(agent),
            'sentence': _find_sentence_containing(text, m.start(), m.end()),
        })

    return claims


def _find_sentence_containing(text: str, start: int, end: int) -> str:
    """Find the full sentence in text that contains the span [start:end]."""
    # Walk backwards to find sentence start
    s = start
    while s > 0 and text[s - 1] not in '.!?\n':
        s -= 1
    # If we stopped at a sentence-ending punctuation, skip past it
    if s > 0 and text[s - 1] in '.!?\n':
        pass  # s is already at the start of our sentence
    # Walk forwards to find sentence end
    e = end
    while e < len(text) and text[e] not in '.!?\n':
        e += 1
    if e < len(text) and text[e] in '.!?':
        e += 1  # include the punctuation
    return text[s:e].strip()


# ═══════════════════════════════════════════════════════════════════════════════
# VERDICT CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

def classify_claim(claim: Dict, stop_record: Dict, corpus: str) -> str:
    """Classify a role claim as RECORD, EVIDENCE, INVENTED, or CONTRADICTS.

    Args:
        claim: Dict with 'role', 'agent', 'agent_bare' keys.
        stop_record: Dict with fields like 'publisher', 'credit_line', 'artist'.
        corpus: The grounding corpus (exhibition page_text).

    Returns:
        Verdict string.
    """
    agent = claim['agent']
    agent_bare = claim['agent_bare']
    role_field = claim['role']

    # Get the record value for this role
    record_value = (stop_record.get(role_field) or '').strip()

    # Case 1: record field has a value
    if record_value:
        # Check if agent matches the record value
        if _agent_in_text(agent, record_value) or _agent_in_text(record_value, agent):
            return 'RECORD'
        # Record has a different value — contradiction
        return 'CONTRADICTS'

    # Case 2: record field is empty — check corpus
    if _agent_in_text(agent, corpus):
        return 'EVIDENCE'

    # Case 3: record empty AND agent absent from corpus
    return 'INVENTED'


# ═══════════════════════════════════════════════════════════════════════════════
# SENTENCE REMOVAL
# ═══════════════════════════════════════════════════════════════════════════════

def _split_sentences(text: str) -> List[str]:
    """Split text into sentences on sentence boundaries.

    Preserves sentence-ending punctuation with the sentence.
    """
    # Split on sentence-ending punctuation followed by whitespace or end
    parts = re.split(r'(?<=[.!?])\s+', text)
    return [p for p in parts if p.strip()]


def remove_sentences_with_agent(text: str, agent: str) -> Tuple[str, List[str]]:
    """Remove all sentences that mention the agent (full or bare form).

    Returns (cleaned_text, list_of_dropped_sentences).
    """
    agent_bare = _strip_leading_article(agent)
    sentences = _split_sentences(text)
    kept = []
    dropped = []

    for sent in sentences:
        sent_lower = _normalize_for_search(sent)
        agent_lower = _normalize_for_search(agent)
        bare_lower = _normalize_for_search(agent_bare)

        if agent_lower in sent_lower or (agent_bare != agent and bare_lower in sent_lower):
            dropped.append(sent)
        else:
            kept.append(sent)

    return ' '.join(kept), dropped


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN GATE FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

# Fields to scan (same as the person gate)
GATED_PROSE_FIELDS = ('description', 'orientation')


def audit_stop_claims(prose: str, stop_record: Dict, corpus: str) -> List[Dict]:
    """Audit a single stop's prose for role claims. Module-scope callable.

    Args:
        prose: The stop's prose text (description or orientation).
        stop_record: Dict with 'publisher', 'credit_line', 'artist' fields.
        corpus: The grounding corpus (exhibition page_text).

    Returns:
        List of finding dicts:
            {'role': str, 'agent': str, 'verdict': str, 'sentence': str}
    """
    findings = []
    claims = extract_role_claims(prose)
    for claim in claims:
        verdict = classify_claim(claim, stop_record, corpus)
        findings.append({
            'role': claim['role'],
            'agent': claim['agent'],
            'verdict': verdict,
            'sentence': claim['sentence'],
        })
    return findings


def apply_role_claim_gate(prose: str, stop_record: Dict, corpus: str) -> Tuple[str, List[Dict]]:
    """Apply the role-claim gate to a prose string. Module-scope callable.

    Gate rule: a ROLE→AGENT claim with verdict INVENTED causes its containing
    sentence to be dropped.

    Args:
        prose: The stop's prose text.
        stop_record: Dict with 'publisher', 'credit_line', 'artist' fields.
        corpus: The grounding corpus (exhibition page_text).

    Returns:
        (cleaned_prose, drop_log) where drop_log is a list of dicts:
            {'role': str, 'agent': str, 'reason': str, 'dropped_sentences': [str]}
    """
    if not prose or not prose.strip():
        return prose, []

    drop_log = []
    result_text = prose

    claims = extract_role_claims(prose)
    for claim in claims:
        verdict = classify_claim(claim, stop_record, corpus)
        if verdict == 'INVENTED':
            result_text, dropped = remove_sentences_with_agent(result_text, claim['agent'])
            if dropped:
                drop_log.append({
                    'role': claim['role'],
                    'agent': claim['agent'],
                    'reason': f"record empty, absent from corpus",
                    'dropped_sentences': dropped,
                })

    return result_text.strip(), drop_log


def apply_role_claim_gate_to_poi_list(
    poi_list: List[Dict],
    exhibition_checklist_result,
    corpus: str,
) -> Dict:
    """Apply the role-claim gate to all stops in a POI list. Production entry point.

    Mutates poi_list in place (rewrites prose fields with INVENTED claims removed).

    Args:
        poi_list: List of POI dicts.
        exhibition_checklist_result: ExhibitionChecklistResult (used for works metadata).
        corpus: The grounding corpus (exhibition page_text).

    Returns:
        Stats dict for logging.
    """
    stats = {
        'role_claims_detected': 0,
        'entities_checked': 0,
        'claims_dropped': 0,
        'sentences_dropped': 0,
        'stops_affected': 0,
        'drop_log': [],
    }

    works = getattr(exhibition_checklist_result, 'works', None) or []

    for poi in poi_list:
        stop_name = poi.get('name', '?')
        stop_touched = False

        # Build the stop record from the POI dict + matched work
        stop_record = {
            'publisher': poi.get('publisher', '') or '',
            'credit_line': poi.get('credit_line', '') or '',
            'artist': poi.get('artist', '') or '',
        }

        # Also check works list for matching publisher data
        for work in works:
            work_title = (work.get('title') or '').lower()
            poi_name = (poi.get('name') or '').lower()
            if work_title and poi_name and (work_title in poi_name or poi_name in work_title):
                if not stop_record['publisher']:
                    stop_record['publisher'] = work.get('publisher', '') or ''
                if not stop_record['credit_line']:
                    stop_record['credit_line'] = work.get('credit_line', '') or ''
                break

        for field_key in GATED_PROSE_FIELDS:
            text = poi.get(field_key, '') or ''
            if not text or text.startswith('['):
                continue

            claims = extract_role_claims(text)
            stats['role_claims_detected'] += len(claims)
            stats['entities_checked'] += len(set(c['agent'] for c in claims))

            cleaned, drops = apply_role_claim_gate(text, stop_record, corpus)
            if drops:
                stop_touched = True
                for d in drops:
                    stats['claims_dropped'] += 1
                    stats['sentences_dropped'] += len(d['dropped_sentences'])
                    stats['drop_log'].append({
                        'stop': stop_name,
                        'field': field_key,
                        'role': d['role'],
                        'agent': d['agent'],
                        'reason': d['reason'],
                        'dropped_sentences': d['dropped_sentences'],
                    })
                poi[field_key] = cleaned

        if stop_touched:
            stats['stops_affected'] += 1

    return stats
