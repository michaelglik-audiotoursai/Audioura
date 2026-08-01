#!/usr/bin/env python3
"""
Tour Rubric Scorer — Michael's 75 gate rubric.

Implements the scoring rubric from TOUR_IMPROVEMENT_LOOP_asian_arts_museum.md:
  - N = requested stop count, share = 100/N points per stop-slot.
  - FABRICATED/MISSING = -1.0 × share
  - THIN = +0.5 × share
  - ADEQUATE = +0.75 × share
  - RICH = +1.0 × share
  - Structural surcharge = -0.25 × share, capped at -0.5 × share per stop
  - Cross-stop correlation bonus = +50% of affected stops' value (can exceed 100)
  - Venue-identity bonus = up to +10% of tour total

Usage:
    python tour_rubric_scorer.py /path/to/tour.txt --n 8

The scorer classifies stops and reports per-stop evidence. It does NOT
auto-classify — the operator must review and confirm/override each
classification. This script provides the FRAMEWORK and helper analysis;
the final classification is manual to honor the "do not game" constraint.
"""
import re
import sys
import json
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class StopAnalysis:
    index: int
    title: str
    text: str
    word_count: int = 0
    
    # Fact indicators
    dates_years: List[str] = field(default_factory=list)
    named_people: List[str] = field(default_factory=list)
    materials_techniques: List[str] = field(default_factory=list)
    measurements_numbers: List[str] = field(default_factory=list)
    named_artworks: List[str] = field(default_factory=list)
    
    # Quality signals
    has_specific_verifiable_facts: bool = False
    has_generic_filler: bool = False
    generic_filler_fraction: float = 0.0
    
    # Structural defects
    structural_defects: List[str] = field(default_factory=list)
    
    # Cross-stop callbacks
    callbacks_from: List[int] = field(default_factory=list)  # stops this references
    callbacks_to: List[int] = field(default_factory=list)    # stops that reference this
    
    # Classification (manual)
    classification: str = ""  # FABRICATED, MISSING, THIN, ADEQUATE, RICH
    classification_evidence: str = ""


@dataclass 
class TourScore:
    n_requested: int
    n_delivered: int
    stops: List[StopAnalysis]
    
    # Score components
    base_score: float = 0.0
    structural_surcharge: float = 0.0
    correlation_bonus: float = 0.0
    venue_identity_bonus: float = 0.0
    total_score: float = 0.0
    
    # Per-stop breakdown
    per_stop_base: List[float] = field(default_factory=list)
    per_stop_structural: List[float] = field(default_factory=list)
    
    # Venue identity
    venue_identity_facts: List[str] = field(default_factory=list)


def parse_tour(text: str) -> List[dict]:
    """Parse tour text into stops."""
    stops = []
    lines = text.split('\n')
    current_stop = None
    
    for line in lines:
        # Match "Stop N: Title" pattern
        m = re.match(r'^Stop\s+(\d+)\s*:\s*(.+)$', line)
        if m:
            if current_stop:
                stops.append(current_stop)
            current_stop = {
                'index': int(m.group(1)),
                'title': m.group(2).strip(),
                'lines': [],
            }
        elif current_stop:
            current_stop['lines'].append(line)
    
    if current_stop:
        stops.append(current_stop)
    
    # Extract body text (exclude Address, Coordinates, Museum Information, Directions)
    for stop in stops:
        body_lines = []
        skip_prefixes = ('Address:', 'Coordinates:', 'Museum Information:', 'Directions:')
        for line in stop['lines']:
            stripped = line.strip()
            if not stripped:
                continue
            if any(stripped.startswith(p) for p in skip_prefixes):
                continue
            # Also skip "Orientation:" lines but keep them noted
            if stripped.startswith('Orientation:'):
                continue
            body_lines.append(stripped)
        stop['body'] = '\n'.join(body_lines)
    
    return stops


def analyze_stop(stop: dict, all_stops: List[dict]) -> StopAnalysis:
    """Analyze a single stop for fact content and quality signals."""
    body = stop['body']
    sa = StopAnalysis(
        index=stop['index'],
        title=stop['title'],
        text=body,
        word_count=len(body.split()),
    )
    
    # Extract dates/years/centuries
    sa.dates_years = re.findall(
        r'\b\d{3,4}\b|\b\d{1,2}(?:st|nd|rd|th)\s+century\b|\b(?:1[0-9]|20)th\s+century\b',
        body, re.IGNORECASE
    )
    # Filter out numbers that aren't dates (e.g. "405" from address remnants)
    sa.dates_years = [d for d in sa.dates_years 
                      if not re.match(r'^\d{3}$', d) or int(d) > 100]
    
    # Named people (proper nouns with 2+ capitalized words)
    sa.named_people = re.findall(
        r'\b([A-Z][a-zéèêëàâùûôîïç]+(?:\s+(?:de|des|du|di|van|von|le|la))?\s+[A-Z][a-zéèêëàâùûôîïç]+(?:\s+[A-Z][a-zéèêëàâùûôîïç]+)?)\b',
        body
    )
    # Filter common non-person patterns
    non_persons = {'Musée des', 'Arts Asiatiques', 'Kannon à', 'Prom des', 'Nice France',
                   'United States', 'Musée des Arts', 'Imperial Palace'}
    sa.named_people = [p for p in sa.named_people if p not in non_persons]
    
    # Materials and techniques
    material_patterns = [
        r'\b(?:grey\s+)?schist\b', r'\blacquer(?:ed)?\b', r'\bbronze\b',
        r'\bcypress\s+wood\b', r'\bsilk\b', r'\bgold\s+leaf\b',
        r'\bwood(?:en)?\b', r'\bcedar\b', r'\bmetalwork\b',
        r'\blost-wax\b', r'\bembroidery\b', r'\bwoodblock\s+print\b',
    ]
    for pat in material_patterns:
        matches = re.findall(pat, body, re.IGNORECASE)
        sa.materials_techniques.extend(matches)
    
    # Measurements/specific numbers
    sa.measurements_numbers = re.findall(
        r'\b\d+(?:\.\d+)?\s*(?:m|cm|kg|arms?|heads?|years?|centuries?)\b',
        body, re.IGNORECASE
    )
    
    # Named artworks (quoted titles)
    sa.named_artworks = re.findall(r'[""«]([^""»]+)[""»]', body)
    
    # Assess verifiable facts
    fact_count = (len(sa.dates_years) + len(sa.named_people) + 
                  len(sa.materials_techniques) + len(sa.measurements_numbers))
    sa.has_specific_verifiable_facts = fact_count >= 3
    
    # Detect generic filler
    generic_phrases = [
        r'invit(?:es?|ing) (?:you )?(?:to )?(?:contemplate|explore|consider|reflect|ponder|delve)',
        r'transcend(?:s|ing)?\s+(?:time|boundaries|cultural)',
        r'(?:profound|deep|rich)\s+(?:sense|cultural|spiritual)\s+(?:of|significance)',
        r'consider\s+(?:how|the)',
        r'as you (?:continue|gaze|admire|explore|marvel)',
        r'testament to',
        r'resonat(?:es?|ing)',
        r'interconnect(?:ed)?(?:ness)?',
        r'tapestry of',
        r'echoe?(?:s|ing)',
        r'you (?:can\'t|cannot) help but',
        r'wash(?:es)? over you',
    ]
    
    sentences = re.split(r'(?<=[.!?])\s+', body)
    generic_count = 0
    for sent in sentences:
        if any(re.search(pat, sent, re.IGNORECASE) for pat in generic_phrases):
            # Only count as generic if the sentence ALSO lacks specific facts
            has_fact = bool(re.search(r'\b\d{3,4}\b|schist|bronze|lacquer|cypress|silk|century', sent, re.IGNORECASE))
            if not has_fact:
                generic_count += 1
    
    total_sentences = len([s for s in sentences if len(s.strip()) > 15])
    sa.generic_filler_fraction = generic_count / max(1, total_sentences)
    sa.has_generic_filler = sa.generic_filler_fraction > 0.4
    
    # Structural defects
    if re.search(r'\[.*?\]', body):  # Template placeholders
        sa.structural_defects.append('template_placeholder')
    if re.search(r"(?:One time, I|I asked|I remember)", body):  # Voice break
        sa.structural_defects.append('voice_break')
    if re.search(r"Stop \d+", body):  # Meta-reference
        sa.structural_defects.append('meta_reference')
    
    # Cross-stop callbacks: check if this stop references other stops' titles
    for other in all_stops:
        if other['index'] == stop['index']:
            continue
        other_title = other['title']
        # Check if the title (or significant fragment) appears in this stop's body
        if len(other_title) > 10 and other_title.lower() in body.lower():
            sa.callbacks_from.append(other['index'])
        else:
            # Check distinctive multi-word fragments
            title_words = [w for w in other_title.split() 
                          if len(w) > 4 and w.lower() not in {'musée', 'museum', 'stop'}]
            if len(title_words) >= 2:
                matches = sum(1 for w in title_words if w.lower() in body.lower())
                if matches >= 2:
                    sa.callbacks_from.append(other['index'])
    
    return sa


def detect_venue_identity(tour_text: str) -> List[str]:
    """Detect venue-identity facts in the tour (architect, founding, etc.)."""
    facts = []
    
    patterns = [
        (r'Kenzo Tange', 'architect_named'),
        (r'(?:inaugurated|opened|founded).*?(?:1998|1997|1996)', 'founding_date'),
        (r'October 16,?\s*1998', 'exact_founding_date'),
        (r'Pierre-Yves Trémois', 'founder/donor_named'),
        (r'(?:square|circle|rotunda|cylindrical)', 'architectural_description'),
    ]
    
    for pat, label in patterns:
        if re.search(pat, tour_text, re.IGNORECASE):
            facts.append(label)
    
    return facts


def compute_score(stops: List[StopAnalysis], n_requested: int,
                  venue_identity_facts: List[str]) -> TourScore:
    """Compute the full rubric score."""
    share = 100.0 / n_requested
    
    ts = TourScore(
        n_requested=n_requested,
        n_delivered=len(stops),
        stops=stops,
        venue_identity_facts=venue_identity_facts,
    )
    
    # Handle missing stops (requested but not delivered)
    missing_count = max(0, n_requested - len(stops))
    
    # Per-stop base score
    for stop in stops:
        cls = stop.classification
        if cls == 'FABRICATED':
            base = -1.0 * share
        elif cls == 'MISSING':
            base = -1.0 * share
        elif cls == 'THIN':
            base = 0.5 * share
        elif cls == 'ADEQUATE':
            base = 0.75 * share
        elif cls == 'RICH':
            base = 1.0 * share
        else:
            base = 0.0  # unclassified
        ts.per_stop_base.append(base)
    
    # Add missing stop penalties
    for _ in range(missing_count):
        ts.per_stop_base.append(-1.0 * share)
    
    ts.base_score = sum(ts.per_stop_base)
    
    # Structural surcharge
    for stop in stops:
        if stop.structural_defects:
            surcharge = -0.25 * share * len(stop.structural_defects)
            surcharge = max(surcharge, -0.5 * share)  # cap
            ts.per_stop_structural.append(surcharge)
        else:
            ts.per_stop_structural.append(0.0)
    
    ts.structural_surcharge = sum(ts.per_stop_structural)
    
    # Cross-stop correlation bonus: +50% of affected stops' value
    # "Affected stops" = stops that have genuine callbacks
    stops_with_callbacks = set()
    for stop in stops:
        if stop.callbacks_from:
            stops_with_callbacks.add(stop.index)
        if stop.callbacks_to:
            stops_with_callbacks.add(stop.index)
    
    if stops_with_callbacks:
        affected_value = 0.0
        for i, stop in enumerate(stops):
            if stop.index in stops_with_callbacks:
                affected_value += ts.per_stop_base[i]
        ts.correlation_bonus = 0.5 * affected_value
    
    # Venue-identity bonus: up to +10% 
    # Scale by how many identity facts present (max 5 categories)
    identity_fraction = min(len(venue_identity_facts), 5) / 5.0
    ts.venue_identity_bonus = 0.10 * ts.base_score * identity_fraction
    
    # Total
    ts.total_score = (ts.base_score + ts.structural_surcharge + 
                      ts.correlation_bonus + ts.venue_identity_bonus)
    
    return ts


def print_analysis(sa: StopAnalysis):
    """Print detailed analysis for a stop."""
    print(f"\n  Stop {sa.index}: {sa.title}")
    print(f"    Words: {sa.word_count}")
    print(f"    Dates/years: {sa.dates_years}")
    print(f"    Named people: {sa.named_people}")
    print(f"    Materials/techniques: {sa.materials_techniques}")
    print(f"    Numbers: {sa.measurements_numbers}")
    print(f"    Artwork refs: {sa.named_artworks}")
    print(f"    Verifiable facts: {sa.has_specific_verifiable_facts}")
    print(f"    Generic filler fraction: {sa.generic_filler_fraction:.0%}")
    print(f"    Structural defects: {sa.structural_defects}")
    print(f"    Callbacks from stops: {sa.callbacks_from}")
    print(f"    Classification: {sa.classification}")
    if sa.classification_evidence:
        print(f"    Evidence: {sa.classification_evidence}")


def print_score(ts: TourScore):
    """Print the full score breakdown."""
    share = 100.0 / ts.n_requested
    
    print(f"\n{'='*70}")
    print(f"  SCORE BREAKDOWN (N={ts.n_requested}, share={share:.2f})")
    print(f"{'='*70}")
    
    print(f"\n  Per-stop:")
    for i, stop in enumerate(ts.stops):
        structural = ts.per_stop_structural[i] if i < len(ts.per_stop_structural) else 0
        callbacks_str = f" (refs: {stop.callbacks_from})" if stop.callbacks_from else ""
        print(f"    Stop {stop.index} [{stop.classification:>9}]: "
              f"base={ts.per_stop_base[i]:+.2f}"
              f"{f', structural={structural:+.2f}' if structural else ''}"
              f"{callbacks_str}")
    
    # Missing stops
    missing = ts.n_requested - ts.n_delivered
    if missing > 0:
        for i in range(missing):
            print(f"    Stop ?  [  MISSING]: base={-share:+.2f}")
    
    print(f"\n  Components:")
    print(f"    Base score:           {ts.base_score:+.2f}")
    print(f"    Structural surcharge: {ts.structural_surcharge:+.2f}")
    print(f"    Correlation bonus:    {ts.correlation_bonus:+.2f}")
    print(f"    Venue-identity bonus: {ts.venue_identity_bonus:+.2f}")
    print(f"    {'─'*40}")
    print(f"    TOTAL:                {ts.total_score:+.2f}")
    print(f"\n  Venue identity facts: {ts.venue_identity_facts}")


def score_tour_file(filepath: str, n_requested: int,
                    classifications: Optional[dict] = None) -> TourScore:
    """Score a tour file with the rubric.
    
    Args:
        filepath: Path to tour text file
        n_requested: Number of stops requested (N)
        classifications: Optional dict of {stop_index: (classification, evidence)}
                        If not provided, stops are analyzed but not classified.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()
    
    stops = parse_tour(text)
    
    # Analyze each stop
    analyses = []
    for stop in stops:
        sa = analyze_stop(stop, stops)
        if classifications and stop['index'] in classifications:
            cls, evidence = classifications[stop['index']]
            sa.classification = cls
            sa.classification_evidence = evidence
        analyses.append(sa)
    
    # Cross-populate callbacks_to
    for sa in analyses:
        for ref_idx in sa.callbacks_from:
            for other_sa in analyses:
                if other_sa.index == ref_idx:
                    other_sa.callbacks_to.append(sa.index)
    
    # Venue identity
    venue_facts = detect_venue_identity(text)
    
    # Compute score
    ts = compute_score(analyses, n_requested, venue_facts)
    
    return ts


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python tour_rubric_scorer.py <tour_file> [--n N]")
        sys.exit(1)
    
    filepath = sys.argv[1]
    n = 8  # default
    if '--n' in sys.argv:
        idx = sys.argv.index('--n')
        n = int(sys.argv[idx + 1])
    
    # Run analysis without classification (for inspection)
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()
    
    stops = parse_tour(text)
    print(f"Parsed {len(stops)} stops from {filepath}")
    print(f"Requested N={n}")
    
    analyses = []
    for stop in stops:
        sa = analyze_stop(stop, stops)
        analyses.append(sa)
        print_analysis(sa)
    
    venue_facts = detect_venue_identity(text)
    print(f"\nVenue identity facts: {venue_facts}")
