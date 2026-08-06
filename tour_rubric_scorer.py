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

[LOCAL-288] The classification is now COMPUTED from measured signals — distinct
facts per content sentence, plus generic-filler fraction — with thresholds
calibrated against 1,719 real stops. It was previously a hand-typed argument,
which meant the dominant term of the index was a human judgement and the module
had no callers at all: the CLI stopped before ever calling compute_score.

The "do not game" constraint the manual design protected is preserved two ways:
an explicit classification passed by the operator always overrides the computed
one, and every classification carries an evidence string naming the signals that
produced it, so a reviewer can dispute any band.

FABRICATED remains uncomputable here. Nothing in this module checks whether a
fact is true, so a stop can score RICH on evidence and be entirely invented.
Absence of FABRICATED is never evidence of accuracy.
"""
import re
import sys
import json
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# --- [LOCAL-288] shared patterns -------------------------------------------

#: Every schema field a generated tour can emit. Lines starting with one of
#: these are structure, not narration, and never count toward facts.
SCHEMA_LABEL_RE = re.compile(
    r'^(?:Address|Coordinates|Museum Information|Directions|Orientation|'
    r'Type/Specialty|Specific Examples|Operational Details|Sources|'
    r'Tour-Category|Description)\s*:',
    re.IGNORECASE,
)

#: A capitalised multi-word phrase — a *candidate* person name, nothing more.
_PROPER_PHRASE_RE = re.compile(
    r'\b([A-Z][a-zéèêëàâùûôîïçñ]+'
    r"(?:\s+(?:de|des|du|di|van|von|le|la|d'))?"
    r'\s+[A-Z][a-zéèêëàâùûôîïçñ]+'
    r'(?:\s+[A-Z][a-zéèêëàâùûôîïçñ]+)?)\b'
)

#: Head nouns that make a capitalised phrase a place, an institution or a
#: schema label rather than a person.
_NOT_A_PERSON_RE = re.compile(
    r'(?i)\b(?:sea|ocean|riviera|village|hill|pond|fountain|square|street|road|'
    r'avenue|boulevard|monument|bandstand|house|cathedral|chapel|garden|park|'
    r'beach|island|museum|mus[eé]e|fondation|palais|port|cape|mount|tower|'
    r'bridge|gate|hotel|castle|fort|abbey|basilica|collection|gallery|'
    r'exhibition|exhibit|installation|examples|details|specialty|information|'
    r'americans?|century|war|succession)\b'
)

#: A person name earns its classification only near a verb of doing or a role
#: noun. Without one, a capitalised phrase is just a capitalised phrase.
_PERSON_CONTEXT_RE = re.compile(
    r'(?i)\b(?:painted|paints|wrote|writes|composed|designed|founded|built|'
    r'established|created|sculpted|carved|lived|worked|visited|ruled|'
    r'commanded|led|inspired|donated|bequeathed|commissioned|discovered|'
    r'architect|painter|artist|sculptor|philosopher|playwright|novelist|poet|'
    r'writer|composer|emperor|empress|king|queen|duke|duchess|general|'
    r'admiral|monk|priest|patron|collector|gallerist)\b'
)

#: How far either side of a candidate name to look for that context.
_PERSON_CONTEXT_WINDOW = 90

#: Tokens whose trailing full stop is an abbreviation mark, not a sentence end.
#: "Henry Clews Jr., a talented painter" is correct prose, not a splice.
_NOT_A_SPLICE_ABBREV = {
    'Jr', 'Sr', 'St', 'Ste', 'Mr', 'Mrs', 'Ms', 'Dr', 'Prof', 'Rev', 'Hon',
    'Inc', 'Ltd', 'Co', 'Mt', 'Ft', 'No', 'vs', 'etc', 'al', 'cf', 'ca',
}


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
    distinct_fact_count: int = 0
    content_sentences: int = 0
    fact_density: float = 0.0
    has_specific_verifiable_facts: bool = False
    has_generic_filler: bool = False
    generic_filler_fraction: float = 0.0
    
    # Structural defects
    structural_defects: List[str] = field(default_factory=list)
    
    # Cross-stop callbacks
    callbacks_from: List[int] = field(default_factory=list)  # stops this references
    callbacks_to: List[int] = field(default_factory=list)    # stops that reference this
    
    # Classification (manual)
    classification: str = ""  # FABRICATED, MISSING, THIN, ADEQUATE, RICH, CONTRADICTED
    classification_evidence: str = ""

    # [LOCAL-291] Groundedness — computed from corpus coverage
    groundedness_fraction: float = 1.0  # 1.0 = fully grounded or no claims to check
    contradicted_share: float = 0.0     # fraction of claims contradicted by corpus
    ungrounded_claims: List[str] = field(default_factory=list)  # corpus worklist


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
    
    # Extract body text — every schema field line is excluded.
    #
    # [LOCAL-288] The original skip list covered four labels and missed the rest,
    # so "Type/Specialty:" and "Specific Examples:" text was being scored as
    # narration. Measured cost: "Specific Examples" and "Operational Details"
    # were the two most frequent "named people" in the whole corpus (183 and 140
    # occurrences), because the label itself is two capitalised words.
    for stop in stops:
        body_lines = []
        for line in stop['lines']:
            stripped = line.strip()
            if not stripped:
                continue
            if SCHEMA_LABEL_RE.match(stripped):
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
    
    # Named people.
    #
    # [LOCAL-288] This was "any two consecutive capitalised words", filtered by a
    # hand-maintained blocklist of eight literals. Measured over 1,728 stops it
    # averaged 5–7.5 matches per stop against ~1 date, so it dominated the fact
    # count — and its most frequent matches were the schema labels "Specific
    # Examples" and "Operational Details", followed by places (French Riviera,
    # Frog Pond, Mediterranean Sea). It was not measuring people.
    #
    # Now: a candidate must not carry a place/institution head noun, and must sit
    # near a verb of doing or a role noun. Counted distinct, so repeating a name
    # does not repeatedly earn credit.
    _people = set()
    for _m in _PROPER_PHRASE_RE.finditer(body):
        _name = _m.group(1)
        if _NOT_A_PERSON_RE.search(_name):
            continue
        _lo = max(0, _m.start() - _PERSON_CONTEXT_WINDOW)
        _hi = min(len(body), _m.end() + _PERSON_CONTEXT_WINDOW)
        if _PERSON_CONTEXT_RE.search(body[_lo:_hi]):
            _people.add(_name)
    sa.named_people = sorted(_people)
    
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
    
    # Assess verifiable facts.
    # [LOCAL-288] Distinct, not occurrences — a stop that names 1888 four times
    # has one date, not four.
    fact_count = (len(set(sa.dates_years)) + len(sa.named_people) +
                  len(set(sa.materials_techniques)) + len(set(sa.measurements_numbers)))
    sa.distinct_fact_count = fact_count
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
    sa.content_sentences = total_sentences
    sa.fact_density = fact_count / max(1, total_sentences)
    sa.generic_filler_fraction = generic_count / max(1, total_sentences)
    sa.has_generic_filler = sa.generic_filler_fraction > 0.4
    
    # Structural defects
    if re.search(r'\[.*?\]', body):  # Template placeholders
        sa.structural_defects.append('template_placeholder')
    if re.search(r"(?:One time, I|I asked|I remember)", body):  # Voice break
        sa.structural_defects.append('voice_break')
    if re.search(r"Stop \d+", body):  # Meta-reference
        sa.structural_defects.append('meta_reference')

    # [LOCAL-288] Splice artifacts — text assembled by pasting spans rather than
    # composing clauses. Added because round 34 scored 87.5 and reported ZERO
    # structural defects while carrying "existentialism., and Pablo Picasso",
    # a tour LEAD had already held as undeliverable. An index that cannot see
    # the defect that blocks delivery is not measuring quality.
    # A full stop immediately followed by a comma: a whole sentence has been
    # inserted mid-sentence. Signature of a splice.
    #
    # [LOCAL-288] Abbreviations are NOT splices. The first version of this check
    # flagged "Henry Clews Jr., a talented painter" in a LOCAL-287 tour whose
    # glosses were in fact correct — a false positive that would have bounced
    # good work. Python cannot express this as a variable-width lookbehind, so
    # the preceding token is checked directly.
    for _sm in re.finditer(r'(\w+)\.\,', body):
        if _sm.group(1) not in _NOT_A_SPLICE_ABBREV:
            sa.structural_defects.append('spliced_sentence')
            break
    if re.search(r'(?i)\b(?:on|of|in|at|to|the|a|an|with|for|by|from|and)\.(?:\s|$)', body):
        # A span cut mid-phrase and terminated: "...in 1964 on the."
        sa.structural_defects.append('truncated_span')
    for _pm in _PROPER_PHRASE_RE.finditer(body):
        _nm = _pm.group(1)
        if len(_nm) > 10 and body.count(_nm) > 1:
            _first = body.find(_nm)
            if 0 <= _first and body.find(_nm, _first + 1) - _first < 120:
                sa.structural_defects.append('doubled_name')
                break
    
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


# --- [LOCAL-288] computed classification -----------------------------------
#
# Thresholds are calibrated against the measured distribution over 1,719 stops
# in tours/ AFTER the signal fixes above, not chosen by intuition:
#
#   category    density p25   median   p75    p90     filler median / p75
#   geo             0.00      0.12     0.33   0.67        0.17 / 0.24
#   museum          0.00      0.10     0.22   0.33        0.21 / 0.30
#   restaurant      0.00      0.11     0.33   0.50        0.11 / 0.17
#
# RICH is set at the p90 of the strongest category, so it stays genuinely hard
# to reach. ADEQUATE sits near the overall median. Filler ceilings sit at each
# band's corresponding percentile.
RICH_MIN_DENSITY = 0.50
RICH_MIN_FACTS = 3
RICH_MAX_FILLER = 0.25

ADEQUATE_MIN_DENSITY = 0.20
ADEQUATE_MIN_FACTS = 2
ADEQUATE_MAX_FILLER = 0.40

# [LOCAL-291] Groundedness floor — a stop below this cannot be classified RICH.
# Measured post-289/290 over 37 stops with corpus: p25 = 0.43, median = 0.60.
# Floor set at 0.40 (just below p25) so it captures clearly-ungrounded stops
# without penalising stops near the boundary. This is a ceiling, NEVER a penalty.
RICH_MIN_GROUNDEDNESS = 0.40


def classify_stop(sa: 'StopAnalysis') -> Tuple[str, str]:
    """Derive a classification from the measured signals.

    Returns (classification, evidence).

    Covers RICH / ADEQUATE / THIN only. **FABRICATED is deliberately not
    computable here** — nothing in this module checks whether a fact is true, so
    a stop can be scored RICH on evidence and still be entirely invented.
    Assigning FABRICATED remains an explicit operator override, and the absence
    of it is never proof of accuracy.

    [LOCAL-291] CONTRADICTED is computed from the claim_check CONTRADICTED
    signal: if the CONTRADICTED share (fraction of claims contradicted by
    corpus) exceeds zero, the stop is classified CONTRADICTED with weight
    −1.0 × share, scored as the negative of the CONTRADICTED portion.

    [LOCAL-291] Groundedness is a RICH ceiling: a stop whose groundedness
    fraction (claims verified in stop_corpus) falls below RICH_MIN_GROUNDEDNESS
    cannot be classified RICH, regardless of density. This never reduces a
    score — it only prevents a stop from reaching RICH.

    The original design made all classification manual "to honor the do-not-game
    constraint". That constraint is preserved two ways: an explicit
    classification always wins over this one, and the evidence string records
    exactly which signals produced the band so a reviewer can dispute it.
    """
    facts = sa.distinct_fact_count
    density = sa.fact_density
    filler = sa.generic_filler_fraction
    groundedness = sa.groundedness_fraction

    evidence = (
        f"{facts} distinct facts over {sa.content_sentences} content sentences "
        f"(density {density:.2f}), filler {filler:.0%}, "
        f"groundedness {groundedness:.0%}"
    )

    # [LOCAL-291] CONTRADICTED check — if corpus positively contradicts claims,
    # this is evidence of error (not absence of evidence). Score negatively.
    if sa.contradicted_share > 0:
        return 'CONTRADICTED', evidence + f" — contradicted_share={sa.contradicted_share:.2f}"

    if facts >= RICH_MIN_FACTS and density >= RICH_MIN_DENSITY and filler <= RICH_MAX_FILLER:
        # [LOCAL-291] Groundedness ceiling: a stop below the floor cannot be RICH.
        # It must not reduce the score — it only caps the band.
        if groundedness < RICH_MIN_GROUNDEDNESS:
            return 'ADEQUATE', evidence + f" (RICH capped by groundedness floor {RICH_MIN_GROUNDEDNESS})"
        return 'RICH', evidence
    if facts >= ADEQUATE_MIN_FACTS and density >= ADEQUATE_MIN_DENSITY and filler <= ADEQUATE_MAX_FILLER:
        return 'ADEQUATE', evidence
    return 'THIN', evidence


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
        elif cls == 'CONTRADICTED':
            # [LOCAL-291] CONTRADICTED: scored at −1.0 × share × contradicted_share.
            # A stop with 1 contradicted claim out of 5 total scores
            # −1.0 × share × 0.2 = −0.2 × share, not the full −1.0 × share.
            # This is proportional to the severity: one wrong date in an
            # otherwise-good stop should not destroy the entire stop's value.
            base = -1.0 * share * stop.contradicted_share
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
                    classifications: Optional[dict] = None,
                    corpus_data: Optional[dict] = None) -> TourScore:
    """Score a tour file with the rubric.
    
    Args:
        filepath: Path to tour text file
        n_requested: Number of stops requested (N)
        classifications: Optional dict of {stop_index: (classification, evidence)}
                        If not provided, stops are analyzed but not classified.
        corpus_data: Optional dict of {stop_title: {passages: [...], ...}} from
                    stop_corpus_reader. When provided, groundedness and
                    CONTRADICTED signals are computed. When absent, groundedness
                    defaults to 1.0 (no ceiling applied).
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()
    
    stops = parse_tour(text)

    # Analyze each stop.
    # [LOCAL-288] The classification is now COMPUTED by default. An explicit
    # entry in `classifications` still wins — that is the operator override, and
    # the only route to FABRICATED.
    analyses = []
    for stop in stops:
        sa = analyze_stop(stop, stops)

        # [LOCAL-291] Compute groundedness and CONTRADICTED signals from corpus.
        if corpus_data:
            _compute_groundedness_for_stop(sa, stop, corpus_data)

        if classifications and stop['index'] in classifications:
            cls, evidence = classifications[stop['index']]
            sa.classification = cls
            sa.classification_evidence = f"OPERATOR OVERRIDE: {evidence}"
        else:
            sa.classification, sa.classification_evidence = classify_stop(sa)
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


def _compute_groundedness_for_stop(sa: 'StopAnalysis', stop: dict, corpus_data: dict):
    """[LOCAL-291] Compute groundedness fraction and contradicted share for a stop.

    Uses groundedness_check module to measure which fact-claims are supported
    by corpus passages. Name normalisation (D187) is applied.

    Sets sa.groundedness_fraction (0..1) and sa.contradicted_share (0..1).
    """
    from groundedness_check import measure_stop_groundedness

    # Look up corpus passages for this stop
    stop_title = stop.get('title', sa.title)
    corpus_entry = corpus_data.get(stop_title)
    if not corpus_entry:
        # No corpus for this stop — groundedness stays 1.0 (no ceiling)
        # and contradicted_share stays 0.0 (no penalty).
        return

    passages = corpus_entry.get('passages', [])
    if not passages:
        return

    body = stop.get('body', sa.text)
    result = measure_stop_groundedness(body, stop_title, passages)

    sa.groundedness_fraction = result.groundedness_fraction
    sa.ungrounded_claims = [c['claim_text'] for c in result.corpus_worklist]

    # CONTRADICTED share: fraction of claims that are CONTRADICTED.
    # This uses the claim_check module's CONTRADICTED signal — positive evidence
    # of error, not absence of support.
    if result.total_claims > 0:
        # Use claim_check for the real CONTRADICTED verdict (same-subject + number conflict)
        try:
            from claim_check import check_paragraph, CONTRADICTED as CC_VERDICT
            cc_result = check_paragraph(
                text=body,
                stop_title=stop_title,
                venue_name='',
                passages=passages,
            )
            cc_contradicted = cc_result['verdict_counts']['contradicted']
            total_cc_claims = len(cc_result['claims'])
            if total_cc_claims > 0 and cc_contradicted > 0:
                sa.contradicted_share = cc_contradicted / total_cc_claims
        except ImportError:
            pass  # claim_check not available — no CONTRADICTED signal


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python tour_rubric_scorer.py <tour_file> [--n N] [--quiet]")
        sys.exit(1)

    filepath = sys.argv[1]
    n = 8
    if '--n' in sys.argv:
        n = int(sys.argv[sys.argv.index('--n') + 1])
    quiet = '--quiet' in sys.argv

    # [LOCAL-288] This block used to stop after printing per-stop analysis and
    # never call compute_score, so running the file produced no score at all.
    ts = score_tour_file(filepath, n)

    if not quiet:
        for sa in ts.stops:
            print_analysis(sa)
        venue = ts.venue_identity_facts
        print(f"\nVenue identity facts: {venue}")

    print_score(ts)
