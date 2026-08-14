#!/usr/bin/env python3
"""evaluate_story.py — LOCAL-464: independent story-type scoring.

Returns three independent scores (0–100 each) classifying a story's character,
plus a valuation_index (0–100) measuring its usefulness as an audio-tour story.

The three axes are INDEPENDENT — they do NOT sum to 100 or to any fixed number.
A story can be strongly Historic AND strongly Social at once.

    - Historic:  event sequences over time — multiple years, ordering words,
                 state changes across dates.
    - Detail:    properties of the subject — materials, counts, dimensions,
                 processes, physical descriptions, edition sizes.
    - Social:    named people and their behaviour toward each other — two or
                 more people in relation, verbs of human conduct.

Valuation index formula (documented per spec):

    valuation_index = clamp(0, 100,
        sentence_score          # 0–30: sentence count against Michael's bar of 3
      + agency_score            # 0–30: presence of agency verbs (story_opportunity_scan._AGENCY_VERB)
      + stakes_score            # 0–25: presence of stakes markers (story_opportunity_scan._STAKES)
      + groundedness_bonus      # 0–15: grounded fraction if corpus supplied
    )

    sentence_score:  min(30, sentence_count * 10)  — 3+ sentences → full 30
    agency_score:    min(30, agency_hit_count * 10) — 3+ agency hits → full 30
    stakes_score:    min(25, stakes_hit_count * 12) — 2+ stakes → full 25 (rounding)
    groundedness:    int(grounded_fraction * 15)    — corpus required, else 0

This produces 0–100 where 85+ means a rich, grounded story with action and stakes,
and sub-30 means a catalogue entry with no narrative shape.

Usage:
    from evaluate_story import evaluate_story
    result = evaluate_story(story_text)
    # result = {'historic': 72, 'detail': 15, 'social': 88,
    #           'valuation_index': 67, 'evidence': {...}}

    python3 evaluate_story.py --text "In 1974, Salvador Dalí..."
    python3 evaluate_story.py --file story_lab_state/stop2_prod.json --field tour_prose
"""
import argparse
import json
import math
import os
import re
import sys
from typing import Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from story_opportunity_scan import _AGENCY_VERB, _STAKES, split_sentences  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════════
# HISTORIC — sequences of events over time
# ═══════════════════════════════════════════════════════════════════════════════

# Year patterns — 4-digit years typical of historical narrative
_YEAR_RE = re.compile(r'\b(1[0-9]{3}|20[0-2][0-9])\b')

# Ordering / sequencing words — "then", "later", "by then", "after", "until"
_SEQUENCE_WORDS = re.compile(
    r'\b(then|later|afterwards|subsequently|eventually|by then|after that|'
    r'after this|by this time|in the end|finally|at first|initially|'
    r'meanwhile|soon after|shortly after|before long|the following year|'
    r'years later|decades later|the next year|that same year|'
    r'from that point|from then on|over the next|in the years that followed|'
    r'at the time|by the time|prior to|preceding|thereafter)\b',
    re.IGNORECASE
)

# State-change verbs — things that mark a before/after transition
_STATE_CHANGE = re.compile(
    r'\b(became|transformed|shifted|changed|evolved|turned into|converted|'
    r'moved|transitioned|replaced|superseded|overthrew|was renamed|'
    r'was completed|was published|was founded|was established|opened|closed|'
    r'collapsed|emerged|began|ended|concluded|ceased|died|was born|'
    r'arrived|departed|left|returned|was finished|was destroyed)\b',
    re.IGNORECASE
)


# ═══════════════════════════════════════════════════════════════════════════════
# DETAIL — properties of the credit_line subject
# ═══════════════════════════════════════════════════════════════════════════════

# Material/medium words
_MATERIAL_RE = re.compile(
    r'\b(oil|watercolor|watercolour|gouache|tempera|fresco|acrylic|pastel|'
    r'ink|charcoal|graphite|pencil|crayon|bronze|marble|limestone|granite|'
    r'sandstone|terracotta|ceramic|porcelain|clay|wood|oak|mahogany|walnut|'
    r'glass|crystal|silk|linen|canvas|paper|parchment|vellum|sheepskin|'
    r'copper|iron|steel|gold|silver|ivory|bone|leather|velvet|cotton|'
    r'lithograph|lithographs|etching|etchings|engraving|engravings|'
    r'drypoint|drypoints|woodcut|woodcuts|aquatint|mezzotint|'
    r'screenprint|serigraph|photograph|gelatin|albumen)\b',
    re.IGNORECASE
)

# Dimensions and measurements
_DIMENSION_RE = re.compile(
    r'(\d+\s*(?:x|×|by)\s*\d+|\d+\s*(?:cm|mm|in|inches|feet|ft|m|metres|meters)'
    r'|\d+\s*(?:copies|impressions|prints|plates|pages|volumes|sheets|pieces|works))',
    re.IGNORECASE
)

# Process/technique words
_PROCESS_RE = re.compile(
    r'\b(printed|engraved|etched|cast|carved|woven|embroidered|glazed|fired|'
    r'gilded|painted|drawn|inked|pressed|folded|bound|stitched|mounted|'
    r'hand-coloured|hand-colored|hand-printed|pulled|struck|'
    r'edition|limited edition|numbered|signed|proof|artist.s proof|'
    r'published|reproduced|fabricated)\b',
    re.IGNORECASE
)

# Counts and quantities — "a set of 10", "11 lithographs", "three volumes"
_COUNT_RE = re.compile(
    r'\b(set of \d+|\d+ (?:lithographs|etchings|prints|volumes|plates|pages|'
    r'copies|illustrations|works|pieces|panels|canvases|drawings|'
    r'photographs|engravings|woodcuts|aquatints))\b',
    re.IGNORECASE
)

# Physical description adjectives (colour, texture, finish)
_PHYSICAL_DESC = re.compile(
    r'\b(luxurious|tactile|vibrant|smooth|rough|textured|glossy|matte|'
    r'translucent|opaque|polished|raw|weathered|patinated|burnished|'
    r'embossed|relief|flat|raised|recessed|perforated|layered)\b',
    re.IGNORECASE
)


# ═══════════════════════════════════════════════════════════════════════════════
# SOCIAL — named people and their behaviour toward each other
# ═══════════════════════════════════════════════════════════════════════════════

# Proper noun spans (people)
_PERSON_NAME = re.compile(
    r'\b([A-Z][a-zà-ÿ]+(?:\s+(?:de|du|von|van|di|del|des|et)\s+)?'
    r'\s+[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)?)\b'
)

# Social / relational verbs — how people behave toward each other
_SOCIAL_VERB = re.compile(
    r'\b(met|introduced|married|divorced|collaborated|argued|quarrelled|'
    r'quarreled|persuaded|refused|insisted|befriended|influenced|mentored|'
    r'taught|hired|fired|hosted|visited|invited|wrote to|corresponded|'
    r'commissioned|patronised|patronized|supported|opposed|criticized|'
    r'praised|dedicated|inspired|encouraged|discouraged|forbidden|'
    r'betrayed|reconciled|reconciled with|confided|confided in|'
    r'competed|rivalled|rivaled|championed|denounced|celebrated|mourned)\b',
    re.IGNORECASE
)

# Relational prepositions and constructions
_RELATION_RE = re.compile(
    r'\b(together|with each other|between them|one another|both|'
    r'his (?:wife|husband|friend|rival|colleague|patron|teacher|student)|'
    r'her (?:wife|husband|friend|rival|colleague|patron|teacher|student)|'
    r'their (?:friendship|rivalry|collaboration|relationship|correspondence))\b',
    re.IGNORECASE
)


# ═══════════════════════════════════════════════════════════════════════════════
# SCORING
# ═══════════════════════════════════════════════════════════════════════════════

def _clamp(lo: int, hi: int, v: float) -> int:
    return max(lo, min(hi, int(round(v))))


def _unique_years(text: str) -> List[str]:
    """Extract unique 4-digit years from text."""
    return sorted(set(_YEAR_RE.findall(text)))


def _count_distinct_people(text: str) -> List[str]:
    """Count distinct proper-noun person names in text."""
    raw = _PERSON_NAME.findall(text)
    # Deduplicate by last-name token (case-insensitive)
    seen = set()
    unique = []
    for name in raw:
        key = name.strip().lower()
        # Skip likely non-person names (places, institutions)
        if re.search(r'(?i)\b(museum|gallery|press|university|society|'
                     r'foundation|institute|square|house|church|cathedral|'
                     r'school|library|academy|theatre|theater|hotel)\b', name):
            continue
        if key not in seen:
            seen.add(key)
            unique.append(name.strip())
    return unique


def _score_historic(text: str, sentences: List[str]) -> tuple:
    """Score historic dimension (0–100) and gather evidence."""
    years = _unique_years(text)
    sequence_hits = _SEQUENCE_WORDS.findall(text)
    state_changes = _STATE_CHANGE.findall(text)

    # Sentences containing year references
    year_sentences = sum(1 for s in sentences if _YEAR_RE.search(s))
    # Sentences with sequencing words
    seq_sentences = sum(1 for s in sentences if _SEQUENCE_WORDS.search(s))
    # Sentences with state changes
    change_sentences = sum(1 for s in sentences if _STATE_CHANGE.search(s))

    n = len(sentences) or 1

    # Multi-year spread: how many distinct years across how many sentences
    year_score = min(35, len(years) * 12)  # 3+ distinct years → 35

    # Sequencing density: ordering words per sentence
    seq_score = min(30, (seq_sentences / n) * 80)  # 40%+ sentences w/ seq → 30

    # State change density
    change_score = min(35, (change_sentences / n) * 90)  # ~40%+ → 35

    total = _clamp(0, 100, year_score + seq_score + change_score)

    evidence = {
        'years_found': years,
        'year_count': len(years),
        'sequence_words': list(set(w.lower() for w in sequence_hits))[:10],
        'state_changes': list(set(w.lower() for w in state_changes))[:10],
        'year_sentences': year_sentences,
        'sequence_sentences': seq_sentences,
        'change_sentences': change_sentences,
    }
    return total, evidence


def _score_detail(text: str, sentences: List[str]) -> tuple:
    """Score detail dimension (0–100) and gather evidence."""
    material_hits = _MATERIAL_RE.findall(text)
    dimension_hits = _DIMENSION_RE.findall(text)
    process_hits = _PROCESS_RE.findall(text)
    count_hits = _COUNT_RE.findall(text)
    physical_hits = _PHYSICAL_DESC.findall(text)

    n = len(sentences) or 1

    # Sentences with material/medium references
    mat_sentences = sum(1 for s in sentences if _MATERIAL_RE.search(s))
    # Sentences with dimensions/counts
    dim_sentences = sum(1 for s in sentences if _DIMENSION_RE.search(s) or _COUNT_RE.search(s))
    # Sentences with process descriptions
    proc_sentences = sum(1 for s in sentences if _PROCESS_RE.search(s))
    # Sentences with physical descriptions
    phys_sentences = sum(1 for s in sentences if _PHYSICAL_DESC.search(s))

    # Scoring: each category contributes up to 25
    mat_score = min(25, len(set(m.lower() for m in material_hits)) * 7)
    dim_score = min(25, len(dimension_hits) * 12)
    proc_score = min(25, len(set(p.lower() for p in process_hits)) * 6)
    phys_score = min(25, (len(set(h.lower() for h in physical_hits))
                          + len(count_hits)) * 8)

    total = _clamp(0, 100, mat_score + dim_score + proc_score + phys_score)

    evidence = {
        'materials': sorted(set(m.lower() for m in material_hits)),
        'dimensions': dimension_hits[:5],
        'processes': sorted(set(p.lower() for p in process_hits)),
        'counts': count_hits[:5],
        'physical_descriptions': sorted(set(h.lower() for h in physical_hits)),
        'material_sentences': mat_sentences,
        'dimension_sentences': dim_sentences,
        'process_sentences': proc_sentences,
    }
    return total, evidence


def _score_social(text: str, sentences: List[str]) -> tuple:
    """Score social dimension (0–100) and gather evidence."""
    people = _count_distinct_people(text)
    social_verb_hits = _SOCIAL_VERB.findall(text)
    relation_hits = _RELATION_RE.findall(text)

    # Sentences with 2+ people named
    multi_person_sentences = 0
    for s in sentences:
        names_in_s = _count_distinct_people(s)
        if len(names_in_s) >= 2:
            multi_person_sentences += 1

    # Sentences with social verbs
    social_verb_sentences = sum(1 for s in sentences if _SOCIAL_VERB.search(s))
    # Sentences with relational constructions
    relation_sentences = sum(1 for s in sentences if _RELATION_RE.search(s))

    n = len(sentences) or 1

    # People count contribution: 2+ people needed for social
    people_score = min(30, max(0, (len(people) - 1)) * 15)  # 2 people → 15, 3+ → 30

    # Social verb density
    verb_score = min(35, social_verb_sentences * 12)  # 3+ sentences → 35

    # Multi-person sentence density + relational constructions
    relation_score = min(35, multi_person_sentences * 15 + len(relation_hits) * 8)

    total = _clamp(0, 100, people_score + verb_score + relation_score)

    evidence = {
        'people_found': people,
        'people_count': len(people),
        'social_verbs': sorted(set(v.lower() for v in social_verb_hits)),
        'relational_phrases': list(set(r.lower() for r in relation_hits))[:5],
        'multi_person_sentences': multi_person_sentences,
        'social_verb_sentences': social_verb_sentences,
    }
    return total, evidence


def _compute_valuation_index(text: str, sentences: List[str], corpus: str = '') -> tuple:
    """Compute valuation_index (0–100) from existing signals.

    Formula:
        sentence_score  (0–30): min(30, sentence_count * 10)
        agency_score    (0–30): min(30, agency_hits * 10)
        stakes_score    (0–25): min(25, stakes_hits * 12)
        groundedness    (0–15): int(grounded_fraction * 15) if corpus provided

    See module docstring for rationale.
    """
    n_sentences = len(sentences)
    agency_hits = sum(1 for s in sentences if _AGENCY_VERB.search(s))
    stakes_hits = sum(1 for s in sentences if _STAKES.search(s))

    sentence_score = min(30, n_sentences * 10)
    agency_score = min(30, agency_hits * 10)
    stakes_score = min(25, stakes_hits * 12)

    groundedness_bonus = 0
    grounded_fraction = None
    if corpus.strip():
        # Simple groundedness: what fraction of the story's proper nouns
        # and years appear in the corpus?
        claims = []
        # Collect years and proper nouns from the story
        years = set(_YEAR_RE.findall(text))
        people = _count_distinct_people(text)
        for y in years:
            claims.append(y)
        for p in people:
            # Use last significant name token for matching
            claims.append(p.split()[-1])

        if claims:
            corpus_lower = corpus.lower()
            grounded = sum(1 for c in claims if c.lower() in corpus_lower)
            grounded_fraction = grounded / len(claims)
            groundedness_bonus = int(grounded_fraction * 15)

    total = _clamp(0, 100, sentence_score + agency_score + stakes_score + groundedness_bonus)

    evidence = {
        'sentence_count': n_sentences,
        'sentence_score': sentence_score,
        'agency_hits': agency_hits,
        'agency_score': agency_score,
        'stakes_hits': stakes_hits,
        'stakes_score': stakes_score,
        'groundedness_bonus': groundedness_bonus,
        'grounded_fraction': grounded_fraction,
    }
    return total, evidence


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def evaluate_story(story: str, matrix: Dict = None, corpus: str = '') -> Dict:
    """Evaluate a story and return independent classification scores.

    Args:
        story:  The story text to evaluate.
        matrix: Optional interrogation matrix (reserved for future use).
        corpus: Optional corpus text for groundedness scoring.

    Returns:
        {
            'historic': int,         # 0–100, event sequences over time
            'detail': int,           # 0–100, properties of the subject
            'social': int,           # 0–100, named people and behaviour
            'valuation_index': int,  # 0–100, overall usefulness as audio-tour story
            'evidence': {
                'historic': {...},
                'detail': {...},
                'social': {...},
                'valuation': {...},
            }
        }

    The three type scores are INDEPENDENT — they do NOT add up to 100 or any
    fixed number. A story can be 80 Historic AND 75 Social simultaneously.
    """
    if not story or not story.strip():
        return {
            'historic': 0, 'detail': 0, 'social': 0,
            'valuation_index': 0,
            'evidence': {'historic': {}, 'detail': {}, 'social': {}, 'valuation': {}},
        }

    sentences = split_sentences(story)

    historic, hist_ev = _score_historic(story, sentences)
    detail, det_ev = _score_detail(story, sentences)
    social, soc_ev = _score_social(story, sentences)
    valuation, val_ev = _compute_valuation_index(story, sentences, corpus)

    return {
        'historic': historic,
        'detail': detail,
        'social': social,
        'valuation_index': valuation,
        'evidence': {
            'historic': hist_ev,
            'detail': det_ev,
            'social': soc_ev,
            'valuation': val_ev,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='Evaluate a story for type scores')
    parser.add_argument('--text', help='Inline story text')
    parser.add_argument('--file', help='JSON file path')
    parser.add_argument('--field', default='tour_prose', help='JSON field containing story text')
    parser.add_argument('--corpus-file', help='Corpus file for groundedness')
    parser.add_argument('--tour-file', help='Tour file — scores all stops')
    args = parser.parse_args()

    corpus = ''
    if args.corpus_file:
        with open(args.corpus_file) as f:
            corpus = f.read()

    if args.tour_file:
        # Score all stops in a tour file
        with open(args.tour_file) as f:
            content = f.read()

        # Parse stops from tour text
        stops = re.split(r'\n\nStop \d+:', content)
        if len(stops) > 1:
            # First element is the header
            header = stops[0]
            for i, stop_text in enumerate(stops[1:], 1):
                # Extract the prose body (after Orientation, before Directions)
                parts = stop_text.split('\n\n')
                # Find the body paragraphs (skip address, coordinates, orientation)
                prose_parts = []
                for p in parts:
                    p = p.strip()
                    if not p:
                        continue
                    if p.startswith('Address:') or p.startswith('Coordinates:'):
                        continue
                    if p.startswith('Orientation:'):
                        continue
                    if p.startswith('Directions:'):
                        break
                    if p.startswith("That's"):
                        break
                    # The body paragraph
                    if len(p) > 80:  # likely prose, not metadata
                        prose_parts.append(p)
                prose = ' '.join(prose_parts)
                if prose:
                    title_match = re.match(r'\s*(.+?)(?:\n|$)', stop_text)
                    title = title_match.group(1).strip() if title_match else f'Stop {i}'
                    result = evaluate_story(prose, corpus=corpus)
                    print(f"\nStop {i}: {title}")
                    print(f"  Historic: {result['historic']:3d}  "
                          f"Detail: {result['detail']:3d}  "
                          f"Social: {result['social']:3d}  "
                          f"Valuation: {result['valuation_index']:3d}  "
                          f"Sum: {result['historic'] + result['detail'] + result['social']}")
        return

    if args.file:
        with open(args.file) as f:
            data = json.load(f)
        story = data.get(args.field, '')
    elif args.text:
        story = args.text
    else:
        story = sys.stdin.read()

    result = evaluate_story(story, corpus=corpus)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
