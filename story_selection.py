"""story_selection.py — LOCAL-438: Quality-sorted story packing.

Michael's design (D392): per stop, from the pool of stories that passed filters,
score each story's quality, sort by quality, then pack greedily into the per-stop
word budget. The number of stories used is whatever fits — one, two, or three.
It is an outcome, never a target.

Exception: a single story that far exceeds the budget but by less than 50%, and
is clearly the best available, may be used alone.

A story that passed the filters is legitimate by definition. Low rank means
"evaluated worse than others", never "not a story". Do not drop a legitimate
story for any reason except that it does not fit.

Public API (module scope, imported by tests):
  - STOP_WORD_BUDGET: named constant, initial value 450 (D392)
  - STOP_WORD_FLOOR: minimum words per delivered stop (LOCAL-393), 120
  - SOURCE_PROVENANCE_WEIGHTS: shared with corpus_source_quality
  - score_story_quality(story) -> float
  - select_stories_for_stop(stories, budget=None) -> list
"""
import re
from typing import Dict, List, Optional


# ─── Budget constant ─────────────────────────────────────────────────────────
# D392: no cap existed before this task; measured delivery is 169–459 words/stop.
# Initialised at 450 so day-one behaviour does not shrink.
# Michael overrides by changing this constant.
STOP_WORD_BUDGET = 450

# LOCAL-393: the 120-word floor still applies to the delivered stop.
STOP_WORD_FLOOR = 120


# ─── Source provenance weights ───────────────────────────────────────────────
# Reused from corpus_source_quality.compute_quality_score (D392 requirement:
# "reuse corpus_source_quality's weighting, do not invent a second weight table").
# Imported here as a shared constant so both modules reference the same values.
SOURCE_PROVENANCE_WEIGHTS = {
    'museum_official': 3.0,
    'wikipedia': 2.5,
    'external_verified': 2.0,
    'bare_string': 1.5,
    'object_no_type': 1.5,
    'heritage': 2.0,
    'museum_site': 2.0,
    'museum_partner': 2.0,
    'web_search': 0.5,
}


# ─── Verification outcome weights ───────────────────────────────────────────
# A story whose claims all survived verification (LOCAL-423/424) outranks one
# with stripped claims. The corroboration_status from story_element_extractor:
_VERIFICATION_WEIGHTS = {
    'documented': 2.0,   # multi-source corroborated
    'disputed': 1.5,     # engaging — both sides exist (D361/D367)
    'reported': 1.0,     # single source, not contradicted
    'legend': 0.5,       # unverified traditional narrative
}


# ─── Specificity signals ─────────────────────────────────────────────────────
# Named person + concrete action + date/consequence present — the same properties
# the story classifier detects (story_gate.is_story_sentence). Reuse its
# extraction patterns rather than mirroring them.

_PERSON_NAME_RE = re.compile(r'\b[A-Z][a-zà-ÿí]+(?:\s+[A-Z][a-zà-ÿ]+)+\b')
_SURNAME_RE = re.compile(r'\b[A-Z][a-zà-ÿí]{2,}\b')
_DATE_RE = re.compile(r'\b\d{4}\b')
_CONSEQUENCE_RE = re.compile(
    r'\b(?:resulted\s+in|led\s+to|caused|enabled|made\s+possible|'
    r'because|since|due\s+to|as\s+a\s+result|consequently|therefore|'
    r'donated|gave|gifted|bequeathed|commission(?:ed|ing)?|founded|'
    r'decided|refused|insisted|demanded|published|printed|produced|'
    r'collaborated|influenced|inspired|destroyed|abandoned|revived)\b',
    re.IGNORECASE
)


def _count_words(text: str) -> int:
    """Count words in a text string."""
    if not text:
        return 0
    return len(text.split())


def _get_source_provenance_score(story: Dict) -> float:
    """Score based on source domain/type provenance.

    Uses the source_domain field to infer source type, or source_type if present.
    Falls back to the domain-based heuristic used by the pipeline.
    """
    # Direct source_type if available (from corpus_source_quality classification)
    source_type = story.get('source_type', '')
    if source_type and source_type in SOURCE_PROVENANCE_WEIGHTS:
        return SOURCE_PROVENANCE_WEIGHTS[source_type]

    # Infer from source_domain
    domain = (story.get('source_domain', '') or '').lower()
    if not domain:
        return 1.0  # unknown, neutral

    # Museum/official domains
    if any(x in domain for x in ('.edu', '.gov', '.museum', 'museum', 'gallery')):
        return SOURCE_PROVENANCE_WEIGHTS['museum_official']
    if 'wikipedia' in domain or 'wikimedia' in domain:
        return SOURCE_PROVENANCE_WEIGHTS['wikipedia']
    if any(x in domain for x in ('heritage', 'archives', 'library')):
        return SOURCE_PROVENANCE_WEIGHTS['heritage']
    # Verified external (known art sources)
    if any(x in domain for x in ('artsy.net', 'christies.com', 'sothebys.com',
                                   'metmuseum.org', 'nga.gov', 'tate.org')):
        return SOURCE_PROVENANCE_WEIGHTS['external_verified']

    # Default web search tier
    return SOURCE_PROVENANCE_WEIGHTS['web_search']


def _get_verification_score(story: Dict) -> float:
    """Score based on verification/corroboration outcome."""
    status = story.get('corroboration_status', 'reported')
    return _VERIFICATION_WEIGHTS.get(status, 1.0)


def _get_specificity_score(story: Dict) -> float:
    """Score specificity: named person + concrete action + date/consequence.

    Each signal adds 1.0 when present:
      - Named person (multi-word proper noun or surname in people list)
      - Date (4-digit year)
      - Consequence/action verb (decision, gift, creation, etc.)
    Max 3.0.
    """
    text = story.get('text', '')
    score = 0.0

    # Named person: from 'people' field or detected in text
    people = story.get('people', [])
    if people:
        score += 1.0
    elif _PERSON_NAME_RE.search(text):
        score += 1.0

    # Date present
    dates = story.get('dates', [])
    if dates:
        score += 1.0
    elif _DATE_RE.search(text):
        score += 1.0

    # Consequence/action verb
    if _CONSEQUENCE_RE.search(text):
        score += 1.0

    return score


def score_story_quality(story: Dict) -> float:
    """Score a story's quality for packing selection.

    Composition:
      quality = provenance_weight + verification_weight + specificity_score

    Components:
      - Source provenance (0.5–3.0): reuses corpus_source_quality's weighting
      - Verification outcome (0.5–2.0): documented > disputed > reported > legend
      - Specificity (0.0–3.0): +1 per signal (named person, date, consequence)

    Range: 1.0–8.0 (theoretical max provenance 3.0 + verification 2.0 + specificity 3.0)

    Tie-breaking: when two stories score identically, select_stories_for_stop
    breaks ties by word count (shorter first — fits more material) then by
    text content hash (deterministic).

    Args:
        story: dict with at minimum 'text'; optionally 'source_domain',
               'source_type', 'corroboration_status', 'people', 'dates'.

    Returns:
        float quality score (higher is better)
    """
    provenance = _get_source_provenance_score(story)
    verification = _get_verification_score(story)
    specificity = _get_specificity_score(story)

    return round(provenance + verification + specificity, 2)


def select_stories_for_stop(
    stories: List[Dict],
    budget: Optional[int] = None,
) -> List[Dict]:
    """Select stories for a stop using quality-sorted greedy packing.

    Michael's algorithm (D392):
      1. Score each story's quality.
      2. Sort by quality descending (ties broken: shorter first, then text hash).
      3. Pack greedily: take the best story that fits, then the next best that
         fits in the leftover, and so on.
      4. The number of stories used is whatever fits — one, two, or three.
      5. Exception: if the single best story exceeds the budget but by less than
         50%, and it is clearly the best available (score > second-best by ≥1.0),
         use it alone.
      6. A story that passed the filters is legitimate by definition. Low rank
         means "evaluated worse than others", never "not a story".

    The 120-word floor (LOCAL-393) still applies to the delivered stop text;
    it is enforced downstream by the narration prompt, not by this selector.
    Packing selects the material; generation produces the output.

    Args:
        stories: list of story dicts, each with at minimum 'text'.
        budget: word budget for this stop. Defaults to STOP_WORD_BUDGET.

    Returns:
        List of selected story dicts (best first), each annotated with
        '_quality_score' and '_word_count'.
    """
    if budget is None:
        budget = STOP_WORD_BUDGET

    if not stories:
        return []

    # Annotate each story with quality score and word count
    scored = []
    for story in stories:
        s = dict(story)  # shallow copy to avoid mutating input
        s['_quality_score'] = score_story_quality(s)
        s['_word_count'] = _count_words(s.get('text', ''))
        scored.append(s)

    # Sort by quality descending; tie-break: LONGER first (maximises budget fill
    # with greedy packing — Michael's example: equal-quality E(70) before A(30)
    # fills budget 100 exactly), then by text content for determinism.
    scored.sort(key=lambda s: (
        -s['_quality_score'],
        -s['_word_count'],
        s.get('text', ''),
    ))

    # --- 50% single-story exception ---
    # If the best story exceeds the budget but by less than 50%, and it is
    # clearly the best (score > second-best by ≥1.0), use it alone.
    if scored:
        best = scored[0]
        best_words = best['_word_count']
        if best_words > budget and best_words <= budget * 1.5:
            # "Clearly the best" = score ≥1.0 above second-best
            second_score = scored[1]['_quality_score'] if len(scored) > 1 else 0.0
            if best['_quality_score'] - second_score >= 1.0:
                return [best]

    # --- Greedy packing ---
    selected = []
    remaining_budget = budget

    for story in scored:
        word_count = story['_word_count']
        if word_count <= remaining_budget:
            selected.append(story)
            remaining_budget -= word_count

    return selected
