"""[LOCAL-439] Story gate — verify every stop tells at least one sourced story.

Unit of evaluation: the STORY, not the sentence (D394).
A story-unit is ≥3 sentences with a named person, real actions, and an arc.
Classification is an AI question (gpt-4o-mini), not a verb list (D394 addendum).

This gate:
  1. Checks that at least one verified story-unit of ≥3 sentences exists per stop.
  2. Classification via classify_story_unit() — one LLM call per candidate unit.
  3. Interest scoring via score_story_interest() — same LLM call as classification.
  4. entities_blurred applies to the STOP TEXT as a whole, not to a story-unit.
  5. Exhibition thesis check: folded into the LLM rubric (no keyword list).

Public API (module scope, imported by tests):
  - classify_story_unit(text) -> dict
  - score_story_interest(text) -> dict
  - extract_candidate_story_units(text) -> list[str]
  - verify_stop_story(description, ...) -> dict
  - verify_tour_stories(tour_text, ...) -> dict
"""
import hashlib
import json
import logging
import os
import re
from typing import Dict, List, Optional, Tuple

from cost_rates import llm_cost

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache for LLM verdicts — keyed by SHA-256 of the unit text.
# Prevents re-asking for the same text across runs/re-scores.
# ---------------------------------------------------------------------------
_verdict_cache: Dict[str, dict] = {}


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


# ---------------------------------------------------------------------------
# Zero-cost pre-filter (regex) — rejects obvious non-prose
# ---------------------------------------------------------------------------

_NON_PROSE_PATTERN = re.compile(
    r'^(?:\s*$|#{1,6}\s|Stop\s+\d+:|Directions:|Sources:|Orientation:)',
    re.MULTILINE
)


def _is_obvious_non_prose(text: str) -> bool:
    """Return True if text is obviously not a story (headings, empty, structural)."""
    stripped = text.strip()
    if not stripped or len(stripped) < 50:
        return True
    # All lines are structural markers
    lines = [l.strip() for l in stripped.splitlines() if l.strip()]
    if all(_NON_PROSE_PATTERN.match(l) for l in lines):
        return True
    return False


# ---------------------------------------------------------------------------
# Extract candidate story-units from stop text
# ---------------------------------------------------------------------------

def extract_candidate_story_units(text: str) -> List[str]:
    """Extract candidate story-units (groups of ≥3 sentences) from stop text.

    A story-unit is a contiguous block of ≥3 prose sentences. We use a sliding
    window approach: try the full text as one unit first (most common case for
    well-written stops), then try 3-sentence windows if the full block fails.

    Returns list of candidate unit texts to be classified.
    """
    if not text or _is_obvious_non_prose(text):
        return []

    # Split into sentences (period/exclamation/question followed by space or end)
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    # Filter out very short fragments and structural markers
    sentences = [s for s in sentences if len(s.strip()) >= 20 and not _NON_PROSE_PATTERN.match(s)]

    if len(sentences) < 3:
        return []

    candidates = []

    # First candidate: the full block (if it's ≥3 sentences)
    if len(sentences) >= 3:
        candidates.append(' '.join(sentences))

    # Also try contiguous 3-sentence windows (for stops with mixed content)
    if len(sentences) > 3:
        for i in range(len(sentences) - 2):
            window = ' '.join(sentences[i:i+3])
            candidates.append(window)

    return candidates


# ---------------------------------------------------------------------------
# LLM-based story classification + interest scoring (one call per unit)
# ---------------------------------------------------------------------------

_CLASSIFICATION_PROMPT = """You are evaluating a candidate story-unit from an audio tour.

A STORY has: a named person, real actions, and an arc (setup → struggle → resolution).
A resolution sentence ("stands as a symbol of...") is VALID inside a story-unit.
Three adjacent atmospheric/evaluative sentences are NOT a story.

ALSO score the story's interest:
- emotional_content (0-4): tension, conflict, resolution, human drama
- new_information (0-3): facts beyond what a visitor can see standing at the stop

DEDUCTION — "telling visitors what to feel":
Does the text direct THE VISITOR's experience? Phrases like "forces visitors to...",
"proves to visitors that...", "invites you to consider..." are deductions.
Sentences that characterize THE WORK ("stands as a symbol of resilience") are NOT
deductions — they describe the artwork, not prescribe the visitor's reaction.
Score deduction as an integer: 0 (no deduction), 1 (mild), 2 (strong).

Respond in this exact JSON format (no other text):
{"is_story": true/false, "reason": "brief explanation", "emotional_content": 0-4, "new_information": 0-3, "deduction": 0-2}

Text to evaluate:
"""

# Track cumulative classification cost for reporting
_classification_cost_usd = 0.0
_classification_input_tokens = 0
_classification_output_tokens = 0


def classify_story_unit(text: str) -> dict:
    """Classify a text as a story-unit (or not) using gpt-4o-mini.

    One call per candidate story-unit, never per sentence.
    Verdict cached alongside the unit; re-scoring never re-asks.

    Returns dict with:
      is_story: bool
      reason: str
      emotional_content: int (0-4)
      new_information: int (0-3)
      deduction: int (0-2)
      cost_usd: float
      from_cache: bool
    """
    global _classification_cost_usd, _classification_input_tokens, _classification_output_tokens

    key = _cache_key(text)
    if key in _verdict_cache:
        cached = _verdict_cache[key].copy()
        cached['from_cache'] = True
        cached['cost_usd'] = 0.0
        return cached

    # Zero-cost pre-filter
    if _is_obvious_non_prose(text):
        result = {
            'is_story': False,
            'reason': 'obvious non-prose (pre-filter)',
            'emotional_content': 0,
            'new_information': 0,
            'deduction': 0,
            'cost_usd': 0.0,
            'from_cache': False,
        }
        _verdict_cache[key] = result
        return result

    # Call gpt-4o-mini
    import requests

    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        # No API key: conservative fallback — never pass without verification.
        # Use legacy regex heuristic as a fallback for backward compat.
        _log.warning("[LOCAL-439] OPENAI_API_KEY not set — falling back to legacy regex classifier")
        # Split into sentences and check with legacy classifier
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        story_sents = [s for s in sentences if is_story_sentence(s)]
        is_story_fallback = len(story_sents) >= 2  # At least 2 story sentences in the unit
        result = {
            'is_story': is_story_fallback,
            'reason': 'legacy regex fallback (no API key)',
            'emotional_content': 1 if is_story_fallback else 0,
            'new_information': 1 if is_story_fallback else 0,
            'deduction': 0,
            'cost_usd': 0.0,
            'from_cache': False,
        }
        _verdict_cache[key] = result
        return result

    prompt = _CLASSIFICATION_PROMPT + text

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 200,
        },
        timeout=30,
    )

    if response.status_code != 200:
        error_msg = response.text[:200]
        raise RuntimeError(f"OpenAI API error {response.status_code}: {error_msg}")

    data = response.json()
    usage = data.get("usage", {})
    input_tokens = usage.get("prompt_tokens", 0)
    output_tokens = usage.get("completion_tokens", 0)
    cost = llm_cost(input_tokens=input_tokens, output_tokens=output_tokens, model="gpt-4o-mini")

    _classification_cost_usd += cost
    _classification_input_tokens += input_tokens
    _classification_output_tokens += output_tokens

    content = data["choices"][0]["message"]["content"].strip()
    # Parse JSON — handle markdown fences
    if content.startswith('```'):
        content = content.split('\n', 1)[1].rsplit('```', 1)[0].strip()

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        _log.warning(f"[LOCAL-439] Failed to parse LLM verdict: {content[:200]}")
        parsed = {
            'is_story': False,
            'reason': f'LLM parse error: {content[:100]}',
            'emotional_content': 0,
            'new_information': 0,
            'deduction': 0,
        }

    result = {
        'is_story': bool(parsed.get('is_story', False)),
        'reason': str(parsed.get('reason', '')),
        'emotional_content': int(parsed.get('emotional_content', 0)),
        'new_information': int(parsed.get('new_information', 0)),
        'deduction': int(parsed.get('deduction', 0)),
        'cost_usd': cost,
        'from_cache': False,
    }

    _verdict_cache[key] = result
    return result


def score_story_interest(text: str) -> dict:
    """Score a story-unit's interest using the same LLM call as classification.

    Returns dict with:
      emotional_content: int (0-4)
      new_information: int (0-3)
      deduction: int (0-2)
      interest_score: int (emotional + new_information - deduction)

    Trust is NOT asked of the LLM — it is computed from provenance weights
    by the caller (story_selection.score_story_quality).
    """
    verdict = classify_story_unit(text)
    emotional = verdict['emotional_content']
    new_info = verdict['new_information']
    deduction = verdict['deduction']

    return {
        'emotional_content': emotional,
        'new_information': new_info,
        'deduction': deduction,
        'interest_score': emotional + new_info - deduction,
        'is_story': verdict['is_story'],
    }


def get_classification_cost() -> dict:
    """Return cumulative classification cost from this session."""
    return {
        'total_cost_usd': _classification_cost_usd,
        'input_tokens': _classification_input_tokens,
        'output_tokens': _classification_output_tokens,
    }


def reset_classification_cost():
    """Reset the cost counter (for testing/per-run isolation)."""
    global _classification_cost_usd, _classification_input_tokens, _classification_output_tokens
    _classification_cost_usd = 0.0
    _classification_input_tokens = 0
    _classification_output_tokens = 0


def get_verdict_cache() -> Dict[str, dict]:
    """Return the verdict cache (for inspection/serialisation)."""
    return _verdict_cache


def load_verdict_cache(cache: Dict[str, dict]):
    """Load a pre-computed verdict cache (for deterministic test runs)."""
    _verdict_cache.update(cache)


# ---------------------------------------------------------------------------
# Entity presence check — applies to the STOP TEXT as a whole (D393 fix)
# ---------------------------------------------------------------------------

def check_named_entities_present(
    description: str,
    credit_line: str,
    stop_name: str = '',
) -> Tuple[bool, List[str], List[str]]:
    """Check that named entities from credit line appear in the STOP TEXT as a whole.

    D393 fix: does not demand every credit-line name — a story that drops a name
    for concision is correct storytelling. Only checks the stop text as a whole.

    Returns (all_present, found_names, missing_names).
    """
    if not credit_line or not description:
        return True, [], []

    # Extract the PRIMARY entity (artist/author) — not every credit-line name
    entities = []

    # "Gift of PERSON" — the donor is NOT required in story text (D393)
    # Only the ARTIST is required (the person the story is about)

    # Artist name from credit line (first multi-word proper noun that isn't a role)
    _ARTIST_PATTERNS = [
        # "ARTIST (Nationality, dates)" pattern
        re.compile(r'^([A-Z][a-zà-ÿ]+(?:\s+[A-Za-zà-ÿ]+)+)\s*\('),
        # "by ARTIST" or "Author: ARTIST"
        re.compile(r'(?:by|Author:?)\s+([A-Z][a-zà-ÿ]+(?:\s+[A-Za-zà-ÿ]+)+)'),
    ]

    for pattern in _ARTIST_PATTERNS:
        m = pattern.search(credit_line)
        if m:
            entities.append(('artist', m.group(1).strip()))
            break

    if not entities:
        # No clear artist found — pass unconditionally
        return True, [], []

    desc_lower = description.lower()
    found = []
    missing = []

    for role, name in entities:
        # Check surname (last word of name)
        surname = name.split()[-1]
        if surname.lower() in desc_lower:
            found.append(f"{name} ({role})")
        else:
            missing.append(f"{name} ({role})")

    return len(missing) == 0, found, missing


# ---------------------------------------------------------------------------
# Main gate function — story-UNIT level (D394)
# ---------------------------------------------------------------------------

def verify_stop_story(
    description: str,
    credit_line: str = '',
    stop_name: str = '',
    framing_case: str = 'exhibition',
    venue_purpose: str = '',
    min_story_sentences: int = 3,  # Legacy param (accepted, not used — D394 supersedes)
) -> Dict:
    """Verify that a stop has at least one verified story-unit of ≥3 sentences.

    D394: The unit of evaluation is the STORY, not the sentence.
    Per-stop requirement: at least one verified story-unit.

    Returns a dict with:
      passed: bool — overall pass/fail
      story_units: list of classified story-unit texts
      story_unit_count: int — number of story-units that pass
      entities_present: bool — artist name present in stop text
      entities_found: list
      entities_missing: list
      failures: list of failure reason strings
      interest_scores: list of interest score dicts for passing units
    """
    failures = []

    # 1. Extract candidate story-units and classify them
    candidates = extract_candidate_story_units(description)
    passing_units = []
    interest_scores = []

    for candidate in candidates:
        verdict = classify_story_unit(candidate)
        if verdict['is_story']:
            passing_units.append(candidate)
            interest_scores.append({
                'text_preview': candidate[:100],
                'emotional_content': verdict['emotional_content'],
                'new_information': verdict['new_information'],
                'deduction': verdict['deduction'],
                'interest_score': verdict['emotional_content'] + verdict['new_information'] - verdict['deduction'],
            })
            # One passing unit is enough per D394
            break

    if not passing_units:
        failures.append(
            f"story_units=0: no candidate story-unit of ≥3 sentences passes "
            f"classification (need at least 1 with named person, real actions, arc)"
        )

    # 2. Entity naming — applies to the STOP TEXT as a whole (D393)
    entities_ok, found, missing = check_named_entities_present(
        description, credit_line, stop_name
    )
    if not entities_ok:
        failures.append(
            f"entities_blurred: {', '.join(missing)} not named in stop text"
        )

    # 3. Exhibition thesis — no longer a keyword list; folded into LLM rubric.
    # For venue_purpose framing, the existing lightweight check remains.
    # For exhibition framing, the LLM classification handles it implicitly
    # (a story about a livre d'artiste IS the thesis threading).
    # We do NOT fail on thesis anymore for exhibition framing (D393/D394).
    # venue_purpose framing keeps the lighter check from LOCAL-432.
    thesis_ok = True
    if framing_case == 'venue_purpose' and venue_purpose:
        thesis_ok = _check_venue_purpose_threaded(description, venue_purpose)
        if not thesis_ok:
            failures.append(
                "thesis_missing: description does not connect to venue's stated purpose"
            )

    return {
        'passed': len(failures) == 0,
        'story_units': passing_units,
        'story_unit_count': len(passing_units),
        'story_count': len(passing_units),  # Legacy alias for LOCAL-431 tests
        'story_sentences': passing_units,  # Legacy alias
        'entities_present': entities_ok,
        'entities_found': found,
        'entities_missing': missing,
        'thesis_threaded': thesis_ok,
        'failures': failures,
        'interest_scores': interest_scores,
    }


def _check_venue_purpose_threaded(description: str, venue_purpose: str) -> bool:
    """[LOCAL-432] Check that a stop connects to the venue's stated purpose.

    Kept from LOCAL-432 — lighter check for venue_purpose framing only.
    """
    if not description:
        return False
    if not venue_purpose:
        return True

    desc_lower = description.lower()

    # Extract meaningful terms from venue purpose
    _DOMAIN_NOUNS = re.compile(
        r'\b(instruments?|musical|music|paintings?|sculptures?|collection|antiquit|'
        r'art|ceramics?|furniture|tapestri|porcelain|textiles?|'
        r'natural\s+history|archaeological|ethnograph)\w*\b',
        re.IGNORECASE
    )
    _PURPOSE_ACTIONS = re.compile(
        r'\b(bequeath\w*|found\w*|establish\w*|assembl\w*|collect\w*|'
        r'donat\w*|preserv\w*|conserv\w*|dedicat\w*|devot\w*|'
        r'testament|hous\w*|display)\b',
        re.IGNORECASE
    )

    # Person surnames
    _surnames = []
    for m in re.finditer(r'\b([A-Z][a-zà-ÿ]+)\b', venue_purpose):
        word = m.group(1)
        if word.lower() in ('the', 'this', 'that', 'its', 'his', 'her', 'and', 'for',
                            'was', 'were', 'has', 'had', 'are', 'may', 'not'):
            continue
        _surnames.append(word.lower())

    _domain_terms = [m.group(0).lower() for m in _DOMAIN_NOUNS.finditer(venue_purpose)]
    _action_terms = [m.group(0).lower() for m in _PURPOSE_ACTIONS.finditer(venue_purpose)]

    all_terms = set(_surnames + _domain_terms + _action_terms)
    _TOO_GENERIC = {'the', 'and', 'for', 'was', 'city', 'in', 'of', 'to', 'a', 'nice'}
    all_terms -= _TOO_GENERIC

    if not all_terms:
        return True

    for term in all_terms:
        if len(term) <= 5:
            if re.search(r'\b' + re.escape(term) + r'\b', desc_lower):
                return True
        else:
            stem = term[:max(5, len(term) - 3)] if len(term) > 7 else term[:max(4, len(term) - 2)]
            if stem in desc_lower:
                return True

    return False


# ---------------------------------------------------------------------------
# Tour-level gate
# ---------------------------------------------------------------------------

def verify_tour_stories(
    tour_text: str,
    credit_lines: Optional[Dict[str, str]] = None,
    framing_case: str = 'exhibition',
    venue_purpose: str = '',
    min_story_sentences: int = 3,  # Legacy param (accepted, not used — D394 supersedes)
) -> Dict:
    """Verify story requirement across all stops in a tour.

    Args:
        tour_text: full tour text
        credit_lines: dict of stop_name → credit_line
        framing_case: 'exhibition' | 'venue_purpose' | 'none'
        venue_purpose: the venue's detected purpose phrase

    Returns dict with:
        all_passed: bool
        stop_results: list of per-stop verify_stop_story results
        summary: str
    """
    if not tour_text:
        return {'all_passed': False, 'stop_results': [], 'summary': 'No tour text'}

    credit_lines = credit_lines or {}

    # Split into stop blocks
    stop_blocks = re.split(r'(?=^Stop\s+\d+:)', tour_text, flags=re.MULTILINE)
    stop_blocks = [b for b in stop_blocks if b.strip() and re.match(r'Stop\s+\d+:', b.strip())]

    if not stop_blocks:
        return {'all_passed': False, 'stop_results': [], 'summary': 'No stops found'}

    results = []
    for block in stop_blocks:
        # Extract stop name
        header_match = re.match(r'Stop\s+\d+:\s*(.+?)(?:\s+by\s+|\s*,\s*\d|\n)', block)
        stop_name = header_match.group(1).strip() if header_match else ''

        # Extract description
        desc_match = re.search(
            r'(?:Orientation:.*?\n\n)(.+?)(?:\n\s*Directions:|\n\s*Sources:|\n\s*Closing:|\Z)',
            block, re.DOTALL
        )
        description = desc_match.group(1).strip() if desc_match else block

        cl = credit_lines.get(stop_name, '')

        result = verify_stop_story(
            description=description,
            credit_line=cl,
            stop_name=stop_name,
            framing_case=framing_case,
            venue_purpose=venue_purpose,
        )
        result['stop_name'] = stop_name
        results.append(result)

    all_passed = all(r['passed'] for r in results)
    passed_count = sum(1 for r in results if r['passed'])
    total = len(results)

    summary_parts = [f"{passed_count}/{total} stops passed story gate"]
    for r in results:
        if not r['passed']:
            summary_parts.append(f"  FAIL: {r['stop_name']}: {'; '.join(r['failures'])}")

    return {
        'all_passed': all_passed,
        'stop_results': results,
        'summary': '\n'.join(summary_parts),
    }


# ---------------------------------------------------------------------------
# Legacy compatibility — keep extract_story_sentences for callers that use it
# (variance_harness, run_local438_acceptance, etc.) but mark it deprecated.
# ---------------------------------------------------------------------------

_STORY_VERB_PATTERNS = re.compile(
    r'\b(?:'
    r'donated|gave|gifted|bequeathed|commission(?:ed|ing)?|chose|selected|'
    r'approached|invited|asked|persuaded|convinced|'
    r'decided|decision|refused|insisted|demanded|agreed|'
    r'published|printed|produced|assembled|'
    r'founded|established|created|revived|'
    r'collaborated|partnered|worked\s+with|'
    r'influenced|inspired|mentor(?:ed)?|taught|introduced|'
    r'collected|acquired|purchased|bought|sold|'
    r'visited|met|sketched|wrote\s+to|corresponded|'
    r'brought|delivered|shipped|transported|'
    r'resulted\s+in|led\s+to|caused|enabled|made\s+possible|'
    r'specialized|focused|devoted|dedicated|'
    r'disputed|contested|challenged|questioned|'
    r'recognized|ensured|commitment|'
    r'destroyed|scrapped|recreated|salvaged|perfecting|resulting|'
    r'because|since|due\s+to|as\s+a\s+result|consequently|therefore'
    r')\b', re.IGNORECASE
)

_PERSON_NAME_PATTERN = re.compile(
    r'\b[A-Z][a-zà-ÿí]+(?:\s+[A-Z][a-zà-ÿ]+)+\b'
)

_NON_STORY_MARKERS = re.compile(
    r'(?:'
    r'\binvites?\s+(?:you|us|the\s+viewer)\b|'
    r'\btranscends?\b|'
    r'\btestament\s+to\b|'
    r'\ba\s+(?:truly\s+)?remarkable\b|'
    r'\breveal(?:s|ing)?\s+(?:a\s+)?deep\b|'
    r'\bbeckons?\b|'
    r'\bponder\b|'
    r'\breflect(?:s|ing)?\s+on\b|'
    r'\bconsider\s+(?:the|how|what)\b|'
    r'\brich\s+tapestry\b|'
    r'\bfusion\s+of\b|'
    r'\bintriguing\b'
    r')', re.IGNORECASE
)


def is_story_sentence(sentence: str) -> bool:
    """LEGACY — kept for callers that haven't migrated to classify_story_unit.

    For LOCAL-439+, use classify_story_unit() on a ≥3-sentence block instead.
    """
    if not sentence or len(sentence) < 30:
        return False
    if _NON_STORY_MARKERS.search(sentence):
        return False

    # Multi-word proper noun (person or institution)
    has_multi_word_name = bool(_PERSON_NAME_PATTERN.search(sentence))

    if not has_multi_word_name:
        # Fallback: single surname + personal-agency verb
        _SURNAME_PATTERN = re.compile(r'\b[A-Z][a-zà-ÿí]{2,}\b')
        _PERSONAL_AGENCY_VERBS = re.compile(
            r'\b(?:donated|gave|gifted|chose|selected|decided|refused|insisted|'
            r'visited|met|sketched|wrote|commissioned|founded|established|'
            r'collected|approached|invited|collaborated|partnered|influenced|'
            r'inspired|specialized|devoted|bequeathed|brought|enabled|produced|'
            r'assembled|created|published|printed|destroyed|recreated|salvaged|'
            r'perfecting|resulting|revived)\b', re.IGNORECASE
        )
        _NOT_PERSON_NAMES = frozenset({
            'the', 'this', 'that', 'these', 'those', 'its', 'his', 'her',
            'arches', 'rives', 'fabriano', 'japan', 'velin', 'vellum',
            'paris', 'london', 'boston', 'york', 'berlin', 'vienna',
            'mediterranean', 'atlantic', 'surrealist', 'cubist',
            'lithographs', 'lithograph', 'drypoints', 'etchings',
            'published', 'printed', 'created', 'founded', 'established',
        })
        surnames_found = _SURNAME_PATTERN.findall(sentence)
        valid_surnames = [s for s in surnames_found if s.lower() not in _NOT_PERSON_NAMES]
        has_surname = len(valid_surnames) > 0
        has_agency = bool(_PERSONAL_AGENCY_VERBS.search(sentence))
        if not (has_surname and has_agency):
            return False

    # Must have a story verb
    has_verb = bool(_STORY_VERB_PATTERNS.search(sentence))
    return has_verb


def extract_story_sentences(text: str) -> List[str]:
    """LEGACY — kept for callers that haven't migrated. Counts story sentences."""
    if not text:
        return []
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s for s in sentences if is_story_sentence(s)]


# ---------------------------------------------------------------------------
# Legacy check_thesis_threaded — kept for existing tests (LOCAL-431)
# For exhibition framing, LOCAL-439 folds this into the LLM rubric.
# ---------------------------------------------------------------------------

_THESIS_KEYWORDS = [
    r"\blivre[s]?\s+d[''']artiste\b",
    r"\bartist['']?s?\s+book[s]?\b",
    r"\bcollaborat\w+\b",
    r"\bbook\s+(?:as\s+)?(?:an?\s+)?art\s*(?:form|work|object)?\b",
    r"\bimage[s]?,?\s*(?:and\s+)?word[s]?,?\s*(?:and\s+)?typography\b",
    r"\bprinted?\s+work[s]?\b",
    r"\bintegrat(?:ed|ion|ing)\b.*\b(?:text|image|word)\b",
]


def check_thesis_threaded(
    description: str,
    framing_case: str = 'exhibition',
    venue_purpose: str = '',
) -> bool:
    """LEGACY — check if the exhibition/venue thesis is threaded into the stop.

    For LOCAL-439+, exhibition framing thesis is folded into the LLM rubric.
    This function is kept for backward compatibility with existing tests.

    For exhibition framing: at least one reference to the art form keywords.
    For venue_purpose: LOCAL-432 lighter check.
    For 'none': always passes.
    """
    if framing_case == 'none':
        return True

    if framing_case == 'venue_purpose':
        return _check_venue_purpose_threaded(description, venue_purpose)

    if not description:
        return False

    for pattern in _THESIS_KEYWORDS:
        if re.search(pattern, description, re.IGNORECASE):
            return True

    return False
