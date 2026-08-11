"""[LOCAL-421] Story gate — verify every stop tells at least one sourced story.

A story = a claim about PEOPLE AND CONSEQUENCES: a relationship, a decision, a
dispute, a gift, a reason something was made the way it was.

This gate:
  1. Checks that ≥3 story sentences exist per stop.
  2. Verifies that named entities from the credit line appear by name.
  3. Checks that the exhibition thesis is threaded into each stop.

Returns a verdict per stop: pass/fail with diagnostics.
"""
import re
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Story sentence detection
# ---------------------------------------------------------------------------

# Patterns that indicate a sentence contains a STORY claim (people + consequence)
_STORY_VERB_PATTERNS = re.compile(
    r'\b(?:'
    r'donated|gave|gifted|bequeathed|commissioned|chose|selected|'
    r'approached|invited|asked|persuaded|convinced|'
    r'decided|refused|insisted|demanded|agreed|'
    r'published|printed|produced|assembled|'
    r'founded|established|created|revived|'
    r'collaborated|partnered|worked\s+with|'
    r'influenced|inspired|mentor|taught|introduced|'
    r'collected|acquired|purchased|bought|sold|'
    r'visited|met|sketched|wrote\s+to|corresponded|'
    r'brought|delivered|shipped|transported|'
    r'resulted\s+in|led\s+to|caused|enabled|made\s+possible|'
    r'specialized|focused|devoted|dedicated|'
    r'disputed|contested|challenged|questioned|'
    r'because|since|due\s+to|as\s+a\s+result|consequently|therefore'
    r')\b', re.IGNORECASE
)

# Person-name pattern (at least one capitalized multi-word name or known surname)
_PERSON_NAME_PATTERN = re.compile(
    r'\b[A-Z][a-zà-ÿí]+(?:\s+[A-Z][a-zà-ÿ]+)+\b'
)

# Single-word proper noun (surname like "Fridman", "Mourlot", "Broder")
_SURNAME_PATTERN = re.compile(
    r'\b[A-Z][a-zà-ÿí]{2,}\b'
)

# Non-story markers — sentences that LOOK factual but aren't story
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
    """Determine if a sentence is a story sentence (people + consequences).

    A story sentence must have:
      1. At least one multi-word proper noun (person or institution name)
         OR a known surname with a story verb indicating personal agency
      2. At least one story verb (action, decision, consequence)
      3. NOT be a non-story evaluative claim

    Returns True if the sentence qualifies as a story sentence.
    """
    if not sentence or len(sentence) < 30:
        return False

    # Reject non-story evaluative claims
    if _NON_STORY_MARKERS.search(sentence):
        return False

    # Must have a multi-word proper noun (person or institution)
    # Single-word capitalized nouns like "Arches" (paper) don't count —
    # we need either a multi-word name OR a single name with a personal-agency verb
    has_multi_word_name = bool(_PERSON_NAME_PATTERN.search(sentence))

    if not has_multi_word_name:
        # Check for single surname + personal-agency verb (donated, chose, visited, etc.)
        # Also handles possessive forms like "Fridman's gift brought..."
        _PERSONAL_AGENCY_VERBS = re.compile(
            r'\b(?:donated|gave|gifted|chose|selected|decided|refused|insisted|'
            r'visited|met|sketched|wrote|commissioned|founded|established|'
            r'collected|approached|invited|collaborated|partnered|influenced|'
            r'inspired|specialized|devoted|bequeathed|brought|enabled|produced|'
            r'assembled|created|published|printed)\b', re.IGNORECASE
        )
        # Blocklist: capitalized words that are NOT person names
        _NOT_PERSON_NAMES = frozenset({
            'the', 'this', 'that', 'these', 'those', 'its', 'his', 'her',
            'arches', 'rives', 'fabriano', 'japan', 'velin', 'vellum',
            'paris', 'london', 'boston', 'york', 'berlin', 'vienna',
            'mediterranean', 'atlantic', 'surrealist', 'cubist',
            'lithographs', 'lithograph', 'drypoints', 'etchings',
            'published', 'printed', 'created', 'founded', 'established',
        })
        # Also detect possessive surname ("Fridman's gift brought...")
        has_possessive_name = bool(re.search(
            r"\b[A-Z][a-zà-ÿí]{2,}(?:'s|'s)\b", sentence
        ))
        # Find surnames not in the blocklist
        surnames_found = _SURNAME_PATTERN.findall(sentence)
        valid_surnames = [s for s in surnames_found if s.lower() not in _NOT_PERSON_NAMES]
        has_surname = len(valid_surnames) > 0
        has_agency = bool(_PERSONAL_AGENCY_VERBS.search(sentence))
        if not ((has_surname or has_possessive_name) and has_agency):
            return False

    # Must have a story verb (action, consequence, decision)
    has_story_verb = bool(_STORY_VERB_PATTERNS.search(sentence))
    if not has_story_verb:
        return False

    return True


def extract_story_sentences(text: str) -> List[str]:
    """Extract all story sentences from a description text.

    Returns list of sentences that qualify as story sentences.
    """
    if not text:
        return []

    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s for s in sentences if is_story_sentence(s)]


# ---------------------------------------------------------------------------
# Entity blurring check
# ---------------------------------------------------------------------------

def check_named_entities_present(
    description: str,
    credit_line: str,
    stop_name: str = '',
) -> Tuple[bool, List[str], List[str]]:
    """Check that all named entities from the credit line appear by name in the text.

    Returns (all_present, found_names, missing_names).
    """
    if not credit_line or not description:
        return True, [], []

    # Extract named entities from credit line
    entities = []

    # "Gift of PERSON" pattern
    gift_match = re.search(
        r'(?:Gift|Bequest|Donation)\s+of\s+([A-Z][a-zà-ÿ]+(?:\s+[A-Z]\.?\s*)?[A-Za-zà-ÿ]+(?:\s+[A-Za-zà-ÿ]+)*)',
        credit_line
    )
    if gift_match:
        entities.append(('donor', gift_match.group(1).strip()))

    # "Published by ENTITY" pattern
    pub_match = re.search(
        r'[Pp]ublish(?:ed|er)[:\s]+([A-Z][a-zà-ÿ]+(?:\s+[A-Za-zà-ÿ]+){0,4})',
        credit_line
    )
    if pub_match:
        entities.append(('publisher', pub_match.group(1).strip()))

    # "Printed by ENTITY" pattern
    print_match = re.search(
        r'[Pp]rint(?:ed|er)[:\s]+(?:by\s+)?([A-Z][a-zà-ÿ]+(?:\s+[A-Za-zà-ÿ]+){0,4})',
        credit_line
    )
    if print_match:
        entities.append(('printer', print_match.group(1).strip()))

    # "Author: PERSON" pattern
    author_match = re.search(
        r'[Aa]uthor[:\s]+([A-Z][a-zà-ÿ]+(?:\s+[A-Za-zà-ÿ]+){0,3})',
        credit_line
    )
    if author_match:
        entities.append(('author', author_match.group(1).strip()))

    if not entities:
        return True, [], []

    desc_lower = description.lower()
    found = []
    missing = []

    for role, name in entities:
        # Check surname (last word of name) — more reliable than full name
        surname = name.split()[-1]
        if surname.lower() in desc_lower:
            found.append(f"{name} ({role})")
        else:
            missing.append(f"{name} ({role})")

    return len(missing) == 0, found, missing


# ---------------------------------------------------------------------------
# Exhibition thesis check
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


def check_thesis_threaded(description: str, framing_case: str = 'exhibition') -> bool:
    """Check if the exhibition thesis is threaded into the stop description.

    For exhibition framing: at least one reference to the art form / collaboration / form.
    For venue_purpose: lighter check.
    For 'none': always passes.
    """
    if framing_case == 'none':
        return True

    if not description:
        return False

    for pattern in _THESIS_KEYWORDS:
        if re.search(pattern, description, re.IGNORECASE):
            return True

    return False


# ---------------------------------------------------------------------------
# Main gate function
# ---------------------------------------------------------------------------

def verify_stop_story(
    description: str,
    credit_line: str = '',
    stop_name: str = '',
    framing_case: str = 'exhibition',
    min_story_sentences: int = 3,
) -> Dict:
    """Verify that a stop meets the LOCAL-421 story requirement.

    Returns a dict with:
      passed: bool — overall pass/fail
      story_sentences: list of identified story sentences
      story_count: int — number of story sentences found
      entities_present: bool — all credit line entities named
      entities_found: list of found entity names
      entities_missing: list of missing entity names
      thesis_threaded: bool — exhibition thesis appears in stop
      failures: list of failure reason strings
    """
    failures = []

    # 1. Story sentence count
    story_sents = extract_story_sentences(description)
    story_count = len(story_sents)
    if story_count < min_story_sentences:
        failures.append(
            f"story_count={story_count} < {min_story_sentences} minimum "
            f"(need {min_story_sentences - story_count} more story sentences)"
        )

    # 2. Entity naming
    entities_ok, found, missing = check_named_entities_present(
        description, credit_line, stop_name
    )
    if not entities_ok:
        failures.append(
            f"entities_blurred: {', '.join(missing)} not named in text"
        )

    # 3. Thesis threading
    thesis_ok = check_thesis_threaded(description, framing_case)
    if not thesis_ok:
        failures.append(
            "thesis_missing: no reference to exhibition's art form "
            "(livre d'artiste, artist's book, collaboration, printed work)"
        )

    return {
        'passed': len(failures) == 0,
        'story_sentences': story_sents,
        'story_count': story_count,
        'entities_present': entities_ok,
        'entities_found': found,
        'entities_missing': missing,
        'thesis_threaded': thesis_ok,
        'failures': failures,
    }


def verify_tour_stories(
    tour_text: str,
    credit_lines: Optional[Dict[str, str]] = None,
    framing_case: str = 'exhibition',
    min_story_sentences: int = 3,
) -> Dict:
    """Verify story requirement across all stops in a tour.

    Args:
        tour_text: full tour text
        credit_lines: dict of stop_name → credit_line
        framing_case: 'exhibition' | 'venue_purpose' | 'none'
        min_story_sentences: minimum story sentences per stop

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

        # Extract description (everything after Orientation: ... until Directions: or end)
        desc_match = re.search(
            r'(?:Orientation:.*?\n\n)(.+?)(?:\n\s*Directions:|\n\s*Sources:|\n\s*Closing:|\Z)',
            block, re.DOTALL
        )
        description = desc_match.group(1).strip() if desc_match else block

        # Get credit line for this stop
        cl = credit_lines.get(stop_name, '')

        result = verify_stop_story(
            description=description,
            credit_line=cl,
            stop_name=stop_name,
            framing_case=framing_case,
            min_story_sentences=min_story_sentences,
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
