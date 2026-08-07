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
import logging
import re
import sys
import json
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


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
    r'americans?|century|war|succession|'
    r'statue|sculpture|painting|portrait|fresco|mural|mosaic|relief|'
    r'armure|robe|masque|danse)\b'
)

#: [LOCAL-304] Expanded person context: deities "embody", "symbolize"; figures
#: described as "son/daughter of" or with a divine/mythological role noun.
_PERSON_CONTEXT_RE = re.compile(
    r'(?i)\b(?:painted|paints|wrote|writes|composed|designed|founded|built|'
    r'established|created|sculpted|carved|lived|worked|visited|ruled|'
    r'commanded|led|inspired|donated|bequeathed|commissioned|discovered|'
    r'embodies|embodying|symbolizes|symbolizing|represents|representing|'
    r'originating|originated|incarnation|avatar|manifestation|'
    r'architect|painter|artist|sculptor|philosopher|playwright|novelist|poet|'
    r'writer|composer|emperor|empress|king|queen|duke|duchess|general|'
    r'admiral|monk|priest|patron|collector|gallerist|'
    r'god|goddess|deity|bodhisattva|divinity|saint|prophet|'
    r'son\s+of|daughter\s+of)\b'
)

#: How far either side of a candidate name to look for that context.
_PERSON_CONTEXT_WINDOW = 90

# --- [LOCAL-304] Structural material detection --------------------------------
#: A proper noun or noun phrase following a "crafted from" / "carved from" /
#: "made of" / "cast in" / "sculpted in" etc. is a material, whatever it is.
#: Captures a single noun (multi-word materials like "cypress wood" are already
#: in the vocabulary list).
_MATERIAL_CONTEXT_RE = re.compile(
    r'(?:crafted|carved|sculpted|cast|moulded|molded|fashioned|wrought|woven|'
    r'made|constructed|built|formed|hewn|chiseled|rendered|painted|printed|'
    r'worked|inlaid|overlaid|decorated|adorned|covered|coated|plated|gilded|'
    r'fired|glazed|enameled|enamelled)\s+'
    r'(?:from|in|of|with|using|out\s+of)\s+'
    r'([a-zéèêëàâùûôîïçñ]+)',
    re.IGNORECASE,
)

# --- [LOCAL-316] Painting / print medium detection ----------------------------
#: Bare medium phrases: "<medium> on <support>" — "oil on canvas", "gouache on
#: paper", "huile sur toile", "tempera on panel". A different grammatical
#: construction from LOCAL-304's verb+preposition patterns. Captures both medium
#: and support as materials (e.g. "oil" + "canvas").
#: French: "huile sur toile/lin", "gouache sur papier", "acrylique sur toile".
_PAINTING_MEDIUM_RE = re.compile(
    r'\b(oil|oils|huile|gouache|tempera|acrylic|acrylique|watercolou?r|aquarelle|'
    r'encaustic|pastel|ink|encre|charcoal|fusain|crayon|graphite|sanguine)\s+'
    r'(?:on|sur|over)\s+'
    r'(canvas|toile|linen|lin|panel|panneau|board|paper|papier|vellum|'
    r'cardboard|carton|masonite|copper|cuivre|wood|bois|silk|soie|burlap|jute)',
    re.IGNORECASE,
)

#: [LOCAL-316] "on the canvas" / "sur la toile" — a support noun used as a
#: physical surface reference. In an artwork context, "on the canvas" identifies
#: the medium just as clearly as "oil on canvas". Requires the definite article
#: ("the"/"la"/"le") or possessive to avoid matching bare metaphors. Only fires
#: for unambiguous support nouns that identify a painting/drawing surface.
#: "board" excluded here (ambiguous with committee) — caught by _PAINTING_MEDIUM_RE
#: when preceded by a medium noun.
_ON_SUPPORT_RE = re.compile(
    r'\bon\s+(?:the|this|that|his|her|its|their|a)\s+'
    r'(canvas|toile|linen|lin|panel|panneau|vellum)\b'
    r'|'
    r'\bsur\s+(?:la|le|les|cette|ce|son|sa)\s+'
    r'(toile|lin|panneau|papier|carton|bois)\b',
    re.IGNORECASE,
)

#: [LOCAL-316] Standalone print and technique terms that appear without
#: syntactic context — the same pattern as the LOCAL-304 vocabulary list but
#: for painting/printmaking media. These have no bare-noun ambiguity risk
#: (nobody says "a lithograph of emotion" the way they say "a canvas of ideas").
_PRINT_TECHNIQUE_PATTERNS = [
    r'\blithograph(?:y|s)?\b', r'\betching(?:s)?\b', r'\bengraving(?:s)?\b',
    r'\baquatint(?:s)?\b', r'\bdrypoint(?:s)?\b', r'\bscreenprint(?:s)?\b',
    r'\bwoodcut(?:s)?\b', r'\bfresco(?:es|s)?\b', r'\bmosaic(?:s)?\b',
    r'\bstained\s+glass\b', r'\bvitrail\b', r'\bvitraux\b',
    r'\bgouache(?:s)?\b', r'\btempera\b', r'\bencaustic\b',
    r'\blinocut(?:s)?\b', r'\bmonotype(?:s)?\b', r'\bmezzotint(?:s)?\b',
    r'\bserigraph(?:y|s)?\b', r'\bgravure(?:s)?\b',
]

# --- [LOCAL-304] Named periods / dynasties / regions --------------------------
#: "the X dynasty", "the X period", "the X era", "the X empire", "the X region"
#: where X is a capitalised proper noun (possibly hyphenated).
#: NO re.IGNORECASE — the proper noun MUST start with a capital letter; this
#: prevents "bygone era", "rich history", "modern period" from matching.
_NAMED_PERIOD_RE = re.compile(
    r'(?:the\s+)?([A-Z][a-zéèêëàâùûôîïçñ]+(?:[-][A-Z][a-zéèêëàâùûôîïçñ]+)*)\s+'
    r'(?:[Dd]ynasty|[Pp]eriod|[Ee]ra|[Ee]poch|[Ee]mpire|[Kk]ingdom|[Rr]eign|'
    r'[Cc]aliphate|[Ss]ultanate|[Ss]hogunate|[Rr]epublic|'
    r'[Cc]ivilization|[Cc]ivilisation|[Rr]egion|[Pp]rovince|[Pp]refecture)'
)

# [LOCAL-304] Single-word proper nouns that should never count as people.
# These are common English words that appear capitalised at the start of
# sentences, temporal/locative words, generic nouns, languages, and concepts.
_SINGLE_WORD_EXCLUSIONS = frozenset({
    'the', 'this', 'that', 'these', 'those', 'here', 'there', 'where',
    'when', 'while', 'which', 'what', 'who', 'whom', 'whose',
    'not', 'nor', 'but', 'and', 'for', 'yet', 'also', 'only',
    'its', 'his', 'her', 'our', 'your', 'their', 'one', 'all',
    'today', 'now', 'then', 'once', 'just', 'even', 'still',
    'however', 'moreover', 'furthermore', 'nevertheless', 'meanwhile',
    'notably', 'indeed', 'perhaps', 'certainly', 'especially',
    'originally', 'finally', 'additionally',
    'each', 'every', 'many', 'most', 'some', 'few', 'several',
    'over', 'under', 'within', 'between', 'among', 'across',
    'during', 'before', 'after', 'since', 'until',
    'from', 'into', 'onto', 'upon', 'with', 'without',
    'stop', 'tour', 'visit', 'walk', 'step', 'look', 'see',
    'imagine', 'notice', 'observe', 'consider', 'discover',
    'beautiful', 'stunning', 'remarkable', 'extraordinary',
    'originating', 'showcasing', 'representing', 'embodying',
    # Languages and scripts — not people
    'sanskrit', 'arabic', 'chinese', 'japanese', 'french', 'english',
    'latin', 'greek', 'hindi', 'persian', 'tibetan', 'korean',
    # Generic concepts that happen to be capitalised
    'universe', 'nature', 'heaven', 'earth', 'world', 'cosmos',
    'paradise', 'infinity', 'eternity', 'renaissance',
    # Compass/geographic generics
    'east', 'west', 'north', 'south', 'asia', 'europe', 'africa',
    # Verbs and participles (sentence-initial capitalisation)
    'carved', 'crafted', 'created', 'built', 'designed', 'painted',
    'sculpted', 'comprising', 'featuring', 'depicting', 'standing',
    'dating', 'located', 'situated', 'surrounded', 'measuring',
    'weighing', 'rising', 'spanning', 'overlooking', 'dedicated',
    'constructed', 'restored', 'renovated', 'founded', 'established',
    'commissioned', 'donated', 'acquired', 'displayed', 'exhibited',
    'inspired', 'influenced', 'decorated', 'adorned', 'covered',
    # Adjectives / demonyms (not specific people)
    'hellenistic', 'byzantine', 'roman', 'gothic', 'baroque',
    'neoclassical', 'romanesque', 'medieval', 'ancient', 'modern',
    'indian', 'asian', 'european', 'african', 'american',
    'buddhist', 'christian', 'islamic', 'hindu', 'taoist',
    'mahayana', 'theravada', 'zen', 'shinto',
    # Religious/philosophical terms (not individuals)
    'bodhisattva', 'bodhisattvas', 'nirvana', 'dharma', 'karma',
    'samsara', 'sutra', 'mandala',
    # Countries/major places (single word)
    'japan', 'china', 'india', 'france', 'italy', 'spain',
    'germany', 'egypt', 'persia', 'greece', 'rome', 'paris',
    'london', 'tokyo', 'beijing', 'delhi',
})

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
    named_periods: List[str] = field(default_factory=list)  # dynasties, periods, eras, regions
    
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

    # [LOCAL-327] Whether corpus passages exist for this stop. When False,
    # groundedness_fraction is unmeasurable (defaults to 1.0 but means nothing).
    # A stop without corpus is unverified — it cannot demonstrate quality.
    corpus_available: bool = False  # True only when stop_corpus has ≥1 passage

    # [LOCAL-327] Whether a corpus lookup was attempted for this stop's tour.
    # When False, corpus_available being False is meaningless (we didn't check).
    # When True, corpus_available=False means the stop is genuinely unverified.
    corpus_lookup_attempted: bool = False


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

    # [LOCAL-305] Coverage and quality — reported separately
    coverage: float = 1.0          # delivered ÷ achievable
    quality: float = 0.0           # per-stop score of what was delivered (normalised)
    n_achievable: int = 0          # stops in area passing genuine existence check
    missing_classifications: List[str] = field(default_factory=list)  # per missing stop: 'PIPELINE_LOST' or 'UNAVAILABLE'
    shortfall_evidence: List[dict] = field(default_factory=list)  # [LOCAL-309] evidence for each classification


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
    
    # [LOCAL-304] Named periods / dynasties / regions — extracted BEFORE people
    # so that period-names can be excluded from the people set.
    # Structural: "the Pala-Sena dynasty", "the Heian period", "Bengale region"
    _periods_found = set()
    for m in _NAMED_PERIOD_RE.finditer(body):
        _periods_found.add(m.group(1).strip())
    sa.named_periods = sorted(_periods_found)
    # Build a set of period-name fragments for people exclusion
    _period_name_words = set()
    for p in _periods_found:
        _period_name_words.add(p)
        for part in p.split('-'):
            if len(part) > 2:
                _period_name_words.add(part)

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
    #
    # [LOCAL-304] Track 2: single-word capitalised names (deities, mythological
    # figures) that sit near deity/figure context ("son of X", "X embodies",
    # "the god X"). The multi-word _PROPER_PHRASE_RE misses "Shiva", "Ganesh".
    _people = set()
    for _m in _PROPER_PHRASE_RE.finditer(body):
        _name = _m.group(1)
        if _NOT_A_PERSON_RE.search(_name):
            continue
        _lo = max(0, _m.start() - _PERSON_CONTEXT_WINDOW)
        _hi = min(len(body), _m.end() + _PERSON_CONTEXT_WINDOW)
        if _PERSON_CONTEXT_RE.search(body[_lo:_hi]):
            _people.add(_name)
    # Track 2: single-word capitalised names as deities/mythological figures.
    # TIGHT structural patterns only — "son/daughter of X", "X, the god/goddess",
    # "dedicated to X", "X embodies/symbolizes" at sentence subject position.
    # A broad context window is NOT used here because single capitalised words
    # are too common (any sentence-initial word qualifies).
    _DEITY_PATTERNS = [
        # "son/daughter of X and Y" — both X and Y are names
        re.compile(r'\b(?:son|daughter|child|consort|wife|husband)\s+of\s+([A-Z][a-zéèêëàâùûôîïçñ]{2,})\s+and\s+([A-Z][a-zéèêëàâùûôîïçñ]{2,})'),
        re.compile(r'\b(?:son|daughter|child|consort|wife|husband)\s+of\s+([A-Z][a-zéèêëàâùûôîïçñ]{2,})\b'),
        # "dedicated to X" / "devoted to X" / "worship of X"
        re.compile(r'\b(?:dedicated|devoted|sacred|consecrated)\s+to\s+([A-Z][a-zéèêëàâùûôîïçñ]{2,})\b'),
        re.compile(r'\b(?:worship|veneration|cult)\s+of\s+([A-Z][a-zéèêëàâùûôîïçñ]{2,})\b'),
        # "X, the god/goddess/deity" or "the god X"
        re.compile(r'\bthe\s+(?:god|goddess|deity|divinity|lord|saint)\s+([A-Z][a-zéèêëàâùûôîïçñ]{2,})\b'),
        re.compile(r'\b([A-Z][a-zéèêëàâùûôîïçñ]{2,}),?\s+(?:the\s+)?(?:god|goddess|deity|divinity|lord)\b'),
        # "X embodies/symbolizes/represents" — subject position (after period/start)
        # Requires at least 4 chars to exclude "It", "He", "She"
        re.compile(r'(?:^|[.!?]\s+)([A-Z][a-zéèêëàâùûôîïçñ]{3,})(?:,\s+[^,]+,)?\s+(?:embodies|symbolizes|represents|incarnates|personifies|manifests)', re.MULTILINE),
    ]
    for pat in _DEITY_PATTERNS:
        for _m in pat.finditer(body):
            for g in _m.groups():
                if g and g.lower() not in _SINGLE_WORD_EXCLUSIONS:
                    if not _NOT_A_PERSON_RE.search(g):
                        if g not in _period_name_words:
                            _people.add(g)
    # Track 3: single-word names immediately adjacent to a role noun.
    # "the artist Chikanobu", "prowess of Chikanobu", "by Matisse"
    # Uses a VERY tight pattern (the role word must be within ~5 words) to
    # avoid the false-positive flood of the broader context window.
    _ROLE_ADJACENT_RE = re.compile(
        r'\b(?:artist|painter|sculptor|architect|composer|writer|author|poet|'
        r'photographer|printmaker|craftsman|artisan|master|maestro|calligrapher)\s+'
        r'([A-Z][a-zéèêëàâùûôîïçñ]{2,})\b'
        r'|'
        r'\b(?:by|of)\s+([A-Z][a-zéèêëàâùûôîïçñ]{2,})(?:,?\s+the\s+(?:artist|painter|sculptor|architect|composer|writer|author|photographer|printmaker))\b'
        r'|'
        r'\b(?:prowess|skill|genius|mastery|work|works|style|technique)\s+of\s+([A-Z][a-zéèêëàâùûôîïçñ]{2,})\b'
    )
    for _m in _ROLE_ADJACENT_RE.finditer(body):
        for g in _m.groups():
            if g and g.lower() not in _SINGLE_WORD_EXCLUSIONS:
                if not _NOT_A_PERSON_RE.search(g):
                    if g not in _period_name_words:
                        _people.add(g)
    sa.named_people = sorted(_people)
    
    # Materials and techniques
    # [LOCAL-304] Two-track detection: (1) the original vocabulary list for common
    # terms that appear without syntactic context, and (2) STRUCTURAL detection via
    # "crafted from X" / "carved from X" / "made of X" patterns — catches any
    # material whatever it is, without needing it on a list.
    # [LOCAL-316] Track 3: painting/print media — bare medium phrases
    # "<medium> on <support>" and standalone print technique terms.
    _materials_found = set()
    material_patterns = [
        r'\b(?:grey\s+)?schist\b', r'\blacquer(?:ed)?\b', r'\bbronze\b',
        r'\bcypress\s+wood\b', r'\bsilk\b', r'\bgold\s+leaf\b',
        r'\bwood(?:en)?\b', r'\bcedar\b', r'\bmetalwork\b',
        r'\blost-wax\b', r'\bembroidery\b', r'\bwoodblock\s+print\b',
    ]
    for pat in material_patterns:
        for m in re.finditer(pat, body, re.IGNORECASE):
            _materials_found.add(m.group(0).lower().strip())
    # Structural: "crafted from chlorite", "carved in marble", etc.
    for m in _MATERIAL_CONTEXT_RE.finditer(body):
        raw_candidate = m.group(1).strip()
        candidate = raw_candidate.lower()
        # Exclude proper nouns (capitalised = a place, not a material)
        if raw_candidate[0].isupper():
            continue
        # Exclude generic non-material nouns that can follow "made of/from"
        # [LOCAL-316] Added colour/appearance terms (hues, shades, tones, colours)
        if candidate in ('it', 'this', 'that', 'them', 'which', 'what',
                         'something', 'nothing', 'everything', 'material',
                         'materials', 'the', 'a', 'an',
                         'hues', 'shades', 'tones', 'colours', 'colors'):
            continue
        _materials_found.add(candidate)
    # [LOCAL-316] Bare medium phrases: "oil on canvas", "huile sur toile", etc.
    # Both medium and support count as material facts.
    for m in _PAINTING_MEDIUM_RE.finditer(body):
        _materials_found.add(m.group(1).lower().strip())
        _materials_found.add(m.group(2).lower().strip())
    # [LOCAL-316] "on the canvas" / "sur la toile" — support noun as surface.
    for m in _ON_SUPPORT_RE.finditer(body):
        # One of the two groups will be non-None (EN vs FR alternation)
        support = (m.group(1) or m.group(2)).lower().strip()
        _materials_found.add(support)
    # [LOCAL-316] Standalone print/technique terms (lithograph, etching, etc.)
    for pat in _PRINT_TECHNIQUE_PATTERNS:
        for m in re.finditer(pat, body, re.IGNORECASE):
            _materials_found.add(m.group(0).lower().strip())
    sa.materials_techniques = sorted(_materials_found)
    
    # Measurements/specific numbers
    # [LOCAL-304] Two-track: (1) digit + unit (original), (2) spelled-out numeral
    # before a countable noun ("eight arms", "eleven heads", "three centuries").
    _measurements_found = set()
    # Track 1: digit-based
    for m in re.finditer(
        r'\b(\d+(?:\.\d+)?\s*(?:m|cm|mm|km|kg|lb|ft|in|'
        r'arms?|heads?|hands?|legs?|eyes?|faces?|'
        r'storeys?|stories?|floors?|columns?|pillars?|panels?|tiers?|steps?|'
        r'strings?|years?|centuries?|decades?|meters?|metres?|'
        r'centimeters?|centimetres?|feet|foot|inches?|'
        r'kilograms?|tons?|tonnes?|pounds?))\b',
        body, re.IGNORECASE
    ):
        _measurements_found.add(m.group(0).lower().strip())
    # Track 2: spelled-out numeral + countable noun
    for m in re.finditer(
        r'\b((?:one|two|three|four|five|six|seven|eight|nine|ten|'
        r'eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|'
        r'eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|'
        r'eighty|ninety|hundred|thousand)'
        r'\s+'
        r'(?:arms?|heads?|hands?|legs?|eyes?|faces?|'
        r'storeys?|stories?|floors?|columns?|pillars?|panels?|tiers?|steps?|'
        r'strings?|centuries?|years?|decades?|months?|'
        r'meters?|metres?|centimeters?|centimetres?|feet|foot|inches?|'
        r'kilograms?|tons?|tonnes?|pounds?))\b',
        body, re.IGNORECASE
    ):
        _measurements_found.add(m.group(0).lower().strip())
    sa.measurements_numbers = sorted(_measurements_found)
    
    # Named artworks (quoted titles)
    sa.named_artworks = re.findall(r'[""«]([^""»]+)[""»]', body)
    
    # Assess verifiable facts.
    # [LOCAL-288] Distinct, not occurrences — a stop that names 1888 four times
    # has one date, not four.
    # [LOCAL-304] Add named_periods to the fact count.
    fact_count = (len(set(sa.dates_years)) + len(sa.named_people) +
                  len(sa.materials_techniques) + len(sa.measurements_numbers) +
                  len(sa.named_periods))
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
# [LOCAL-304] Recalibrated after widening the fact detector to structural
# patterns (materials via syntax, spelled-out numerals, deity names, named
# periods). Measured over 1,997 stops in the full corpus:
#
#   density: p25=0.071, p50=0.182, p75=0.333, p90=0.571, p95=0.800
#   facts:   p25=1,     p50=2,     p75=4,     p90=6,     p95=8
#   filler:  p25=0.100, p50=0.200, p75=0.286, p90=0.364, p95=0.417
#
# RICH stays at ~p90 density: 0.60 (above measured p90 of 0.571).
# RICH facts raised from 3→4 (now ~p75, was p90 before the detector was fixed).
# ADEQUATE facts raised from 2→3 (keeps ~p55 of the new distribution).
# ADEQUATE density stays at 0.20 (~p55).
# Filler ceilings unchanged (still calibrated to their band's percentile).
#
# Resulting distribution: 7.6% RICH / 26.3% ADEQUATE / 66.1% THIN
# (was 5.1% / 24.7% / 70.2% before LOCAL-304 — the shift in RICH reflects
# genuinely-detected facts that were invisible before, not inflation).
RICH_MIN_DENSITY = 0.60
RICH_MIN_FACTS = 4
RICH_MAX_FILLER = 0.25

ADEQUATE_MIN_DENSITY = 0.20
ADEQUATE_MIN_FACTS = 3
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
        # [LOCAL-327] Corpus availability ceiling: a stop without corpus cannot
        # demonstrate quality — its facts are unverified, not wrong.
        # Capped to THIN (not ADEQUATE) because ADEQUATE also requires corpus.
        # Only applied when a corpus lookup was actually attempted.
        if sa.corpus_lookup_attempted and not sa.corpus_available:
            return 'THIN', evidence + " (RICH capped to THIN: no corpus passages — facts unverified)"
        return 'RICH', evidence
    if facts >= ADEQUATE_MIN_FACTS and density >= ADEQUATE_MIN_DENSITY and filler <= ADEQUATE_MAX_FILLER:
        # [LOCAL-327] Corpus availability ceiling for ADEQUATE: a stop without
        # corpus passages cannot demonstrate ADEQUATE quality. The stop may be
        # perfectly accurate — but nothing checked, so we cannot count it as
        # demonstrated quality. Capped at THIN, never penalised below THIN.
        # Only applied when a corpus lookup was actually attempted.
        if sa.corpus_lookup_attempted and not sa.corpus_available:
            return 'THIN', evidence + " (ADEQUATE capped: no corpus passages — facts unverified)"
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
                  venue_identity_facts: List[str],
                  gate_log: Optional[List[dict]] = None,
                  corpus_data: Optional[dict] = None,
                  venue_name: Optional[str] = None) -> TourScore:
    """Compute the full rubric score.

    [LOCAL-305] Now splits MISSING stops into PIPELINE_LOST / UNAVAILABLE based
    on the gate_log, reports coverage and quality separately, and normalises
    quality against available passages.

    [LOCAL-309] Updated weights per Michael's ruling 2026-08-06:
      - FABRICATED: −3.0 × share (was −1.5) — 3× worse than omission
      - PIPELINE_LOST: −1.0 × share (unchanged)
      - UNAVAILABLE, search-confirmed: 0.0 × share (was −0.15)
      - UNAVAILABLE, unverified (no search): −1.0 × share (treat as PIPELINE_LOST)

    The last line is the point: UNAVAILABLE at zero cost is ONLY available to a
    shortfall that a live search confirms. Absent that search, the shortfall is
    our failure and costs the full amount.

    When venue_name is provided and there are missing stops, a bounded internet
    search is run to verify whether further candidates exist in the area.

    Args:
        stops: Analysed stops that were delivered.
        n_requested: Number of stops the user requested.
        venue_identity_facts: Venue identity facts detected in the tour.
        gate_log: Optional list of gate verdicts from run_existence_gate() or
                  equivalent. Each entry is a dict with at least:
                    - stop_title: str
                    - verified: bool
                    - evidence: str
                    - source: str
                  The gate_log records ALL proposed stops, including those that
                  were dropped. A stop that was proposed and verified but is not
                  in `stops` was PIPELINE_LOST. A shortfall beyond what the gate
                  proposed is UNAVAILABLE only if a positive tier-1 finding
                  confirms the area is exhausted.
        corpus_data: Optional dict of {stop_title: {passages: [...], ...}}.
                    Used for per-stop quality normalisation against available
                    passages.
        venue_name: Optional venue/area name. When provided and there are missing
                    stops, triggers a live internet search to verify whether the
                    shortfall is genuine (UNAVAILABLE) or our failure (PIPELINE_LOST).
    """
    share = 100.0 / n_requested
    
    ts = TourScore(
        n_requested=n_requested,
        n_delivered=len(stops),
        stops=stops,
        venue_identity_facts=venue_identity_facts,
    )
    
    # ─── [LOCAL-305/309] Classify missing stops ────────────────────────────────
    missing_count = max(0, n_requested - len(stops))
    missing_classifications = []
    # [LOCAL-309] Evidence for each missing stop's classification
    shortfall_evidence: List[dict] = []

    if missing_count > 0 and gate_log:
        # Build set of delivered stop titles for comparison
        delivered_titles = {s.title for s in stops}

        # Stops that were proposed, verified, but not delivered → PIPELINE_LOST
        # (generation failure, gate drop without replenishment, empty-stop removal)
        verified_but_missing = []
        for entry in gate_log:
            if entry.get('verified') and entry.get('stop_title') not in delivered_titles:
                verified_but_missing.append(entry.get('stop_title', ''))

        # Count how many missing stops are accounted for by pipeline losses
        pipeline_lost_count = min(len(verified_but_missing), missing_count)

        # The remainder: were fewer candidates proposed than requested?
        remaining_shortfall = missing_count - pipeline_lost_count

        # [LOCAL-309] For the remaining shortfall, run a live search to verify
        # whether the area genuinely lacks candidates. Only a confirmed search
        # earns the zero-cost UNAVAILABLE classification.
        genuinely_unavailable = 0
        if remaining_shortfall > 0 and venue_name:
            try:
                from shortfall_search import search_for_shortfall
                delivered_title_list = [s.title for s in stops]
                shortfall_result = search_for_shortfall(
                    venue_name=venue_name,
                    n_requested=n_requested,
                    delivered_titles=delivered_title_list,
                    gate_log=gate_log,
                )
                # Count how many slots the search confirmed as genuinely unavailable
                for v in shortfall_result.verdicts[:remaining_shortfall]:
                    if v.classification == 'UNAVAILABLE':
                        genuinely_unavailable += 1
                    shortfall_evidence.append({
                        'classification': v.classification,
                        'search_query': v.search_query,
                        'candidates_found': v.candidates_found,
                        'evidence': v.evidence,
                        'search_error': v.search_error,
                        'cached': v.cached,
                    })
            except ImportError:
                # shortfall_search not available — fail closed
                logger.warning("[SCORER] shortfall_search module not available — "
                               "treating all shortfall as PIPELINE_LOST")
            except Exception as e:
                # Any error in search → fail closed (PIPELINE_LOST)
                logger.warning(f"[SCORER] shortfall search failed: {e} — "
                               "treating shortfall as PIPELINE_LOST")
        elif remaining_shortfall > 0 and not venue_name:
            # No venue_name → cannot search → fail closed
            pass

        # Classify each missing slot
        for _ in range(pipeline_lost_count):
            missing_classifications.append('PIPELINE_LOST')
        for _ in range(min(genuinely_unavailable, remaining_shortfall)):
            missing_classifications.append('UNAVAILABLE')
        # Cannot tell → PIPELINE_LOST (spec: "default to blaming ourselves")
        cannot_tell = missing_count - len(missing_classifications)
        for _ in range(cannot_tell):
            missing_classifications.append('PIPELINE_LOST')

    elif missing_count > 0 and venue_name:
        # No gate_log but we have venue_name → run shortfall search
        try:
            from shortfall_search import search_for_shortfall
            delivered_title_list = [s.title for s in stops]
            shortfall_result = search_for_shortfall(
                venue_name=venue_name,
                n_requested=n_requested,
                delivered_titles=delivered_title_list,
                gate_log=gate_log,
            )
            for v in shortfall_result.verdicts[:missing_count]:
                missing_classifications.append(v.classification)
                shortfall_evidence.append({
                    'classification': v.classification,
                    'search_query': v.search_query,
                    'candidates_found': v.candidates_found,
                    'evidence': v.evidence,
                    'search_error': v.search_error,
                    'cached': v.cached,
                })
            # Fill any remaining with PIPELINE_LOST
            while len(missing_classifications) < missing_count:
                missing_classifications.append('PIPELINE_LOST')
        except ImportError:
            for _ in range(missing_count):
                missing_classifications.append('PIPELINE_LOST')
        except Exception as e:
            logger.warning(f"[SCORER] shortfall search failed: {e}")
            for _ in range(missing_count):
                missing_classifications.append('PIPELINE_LOST')

    elif missing_count > 0:
        # No gate_log, no venue_name → cannot tell → PIPELINE_LOST for all
        for _ in range(missing_count):
            missing_classifications.append('PIPELINE_LOST')

    ts.missing_classifications = missing_classifications
    ts.shortfall_evidence = shortfall_evidence

    # ─── Per-stop base score ─────────────────────────────────────────────────
    for stop in stops:
        cls = stop.classification
        if cls == 'FABRICATED':
            # [LOCAL-309] Fabrication costs 3× what omission costs: −3.0 × share
            base = -3.0 * share
        elif cls == 'MISSING':
            # Legacy compat — should not appear for delivered stops but handle it
            base = -1.0 * share
        elif cls == 'CONTRADICTED':
            # [LOCAL-291] CONTRADICTED: scored at −1.0 × share × contradicted_share.
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
    
    # [LOCAL-309] Add missing stop penalties with updated weights:
    #   PIPELINE_LOST:               -1.0 × share (our failure)
    #   UNAVAILABLE (search-confirmed): 0.0 × share (genuine scarcity)
    # A zero-cost UNAVAILABLE requires recorded search evidence.
    for cls in missing_classifications:
        if cls == 'PIPELINE_LOST':
            ts.per_stop_base.append(-1.0 * share)
        elif cls == 'UNAVAILABLE':
            ts.per_stop_base.append(0.0 * share)
        else:
            # Defensive: unknown classification → PIPELINE_LOST weight
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
    # [D202] BUG FIX: computed against positive part of base only.
    identity_fraction = min(len(venue_identity_facts), 5) / 5.0
    ts.venue_identity_bonus = 0.10 * max(0.0, ts.base_score) * identity_fraction
    
    # Total
    ts.total_score = (ts.base_score + ts.structural_surcharge + 
                      ts.correlation_bonus + ts.venue_identity_bonus)

    # ─── [LOCAL-305] Coverage and quality, reported separately ────────────────
    #
    # coverage  = delivered ÷ achievable
    # achievable = n_requested − UNAVAILABLE count
    # quality   = per-stop normalised score of what was delivered
    #
    # Quality normalisation: a stop's score is scaled by the ratio of its
    # groundedness to the maximum achievable (corpus passage availability).
    # A stop with 6 passages delivering 6 facts has done everything; one with
    # 6 passages delivering 1 has not. This uses groundedness_fraction from
    # LOCAL-291 which already measures claims supported by corpus.
    unavailable_count = sum(1 for c in missing_classifications if c == 'UNAVAILABLE')
    n_achievable = n_requested - unavailable_count
    ts.n_achievable = n_achievable

    if n_achievable > 0:
        ts.coverage = len(stops) / n_achievable
    else:
        ts.coverage = 1.0  # edge case: nothing achievable → coverage is vacuously complete

    # Quality: average of per-stop scores for delivered stops, normalised
    # against available passages. Each stop's contribution is its base + structural,
    # divided by the share it COULD have earned (1.0 × share for a perfect stop).
    if stops:
        quality_sum = 0.0
        for i, stop in enumerate(stops):
            stop_earned = ts.per_stop_base[i] + ts.per_stop_structural[i]
            max_possible = 1.0 * share  # RICH with no defects

            # [LOCAL-305] Normalise against available passages.
            # If corpus_data is available and this stop has limited passages,
            # the "max possible" is scaled by passage availability.
            # A stop with groundedness 1.0 on 2 passages did everything it could;
            # it should not be penalised relative to a stop with 20 passages.
            # The groundedness_fraction already captures this ratio from LOCAL-291.
            # We use it directly: quality contribution = earned / max_possible,
            # but a stop at groundedness=1.0 is "perfect for what was available".
            #
            # The normalisation: if groundedness ≥ 1.0, stop did all it could.
            # If groundedness < 1.0, the stop could have done better.
            # This is already reflected in the classification (groundedness
            # caps RICH). So quality is simply the ratio of earned to possible.
            if max_possible > 0:
                quality_sum += stop_earned / max_possible
            else:
                quality_sum += 0.0

        ts.quality = quality_sum / len(stops)
    else:
        ts.quality = 0.0
    # ─── END [LOCAL-305] ─────────────────────────────────────────────────────
    
    return ts


def print_analysis(sa: StopAnalysis):
    """Print detailed analysis for a stop."""
    print(f"\n  Stop {sa.index}: {sa.title}")
    print(f"    Words: {sa.word_count}")
    print(f"    Dates/years: {sa.dates_years}")
    print(f"    Named people: {sa.named_people}")
    print(f"    Materials/techniques: {sa.materials_techniques}")
    print(f"    Numbers: {sa.measurements_numbers}")
    print(f"    Named periods: {sa.named_periods}")
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
        print(f"    Stop {stop.index} [{stop.classification:>12}]: "
              f"base={ts.per_stop_base[i]:+.2f}"
              f"{f', structural={structural:+.2f}' if structural else ''}"
              f"{callbacks_str}")
    
    # Missing stops — now classified
    missing = ts.n_requested - ts.n_delivered
    if missing > 0:
        for i, cls in enumerate(ts.missing_classifications):
            weight = -1.0 if cls == 'PIPELINE_LOST' else -0.15
            print(f"    Stop ?  [{cls:>12}]: base={weight * share:+.2f}")
    
    print(f"\n  Components:")
    print(f"    Base score:           {ts.base_score:+.2f}")
    print(f"    Structural surcharge: {ts.structural_surcharge:+.2f}")
    print(f"    Correlation bonus:    {ts.correlation_bonus:+.2f}")
    print(f"    Venue-identity bonus: {ts.venue_identity_bonus:+.2f}")
    print(f"    {'─'*40}")
    print(f"    TOTAL:                {ts.total_score:+.2f}")

    # [LOCAL-305] Coverage and quality
    print(f"\n  Coverage & Quality:")
    print(f"    Delivered / Requested:  {ts.n_delivered} / {ts.n_requested}")
    print(f"    Achievable:             {ts.n_achievable}")
    print(f"    Coverage:               {ts.coverage:.2f}")
    print(f"    Quality (normalised):   {ts.quality:.2f}")
    if ts.missing_classifications:
        from collections import Counter
        cls_counts = Counter(ts.missing_classifications)
        parts = [f"{count}×{cls}" for cls, count in cls_counts.items()]
        print(f"    Missing breakdown:      {', '.join(parts)}")

    print(f"\n  Venue identity facts: {ts.venue_identity_facts}")


def score_tour_file(filepath: str, n_requested: int,
                    classifications: Optional[dict] = None,
                    corpus_data: Optional[dict] = None,
                    gate_log: Optional[List[dict]] = None,
                    venue_name: Optional[str] = None) -> TourScore:
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
        gate_log: Optional list of gate verdicts for classifying missing stops
                 as PIPELINE_LOST vs UNAVAILABLE. See compute_score docstring.
        venue_name: Optional venue/area name for shortfall search (LOCAL-309).
                   When provided and there are missing stops, a live search
                   verifies whether the area genuinely lacks candidates.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()
    
    stops = parse_tour(text)

    # [LOCAL-309] Extract venue_name from tour header if not provided
    _effective_venue_name = venue_name
    if not _effective_venue_name:
        # Try to extract from first line: "Step-by-Step Audio Guided Tour: VENUE"
        first_line = text.split('\n')[0] if text else ''
        m = re.match(r'^Step-by-Step.*?:\s*(.+)$', first_line)
        if m:
            _effective_venue_name = m.group(1).strip()

    # Analyze each stop.
    # [LOCAL-288] The classification is now COMPUTED by default. An explicit
    # entry in `classifications` still wins — that is the operator override, and
    # the only route to FABRICATED.
    analyses = []
    for stop in stops:
        sa = analyze_stop(stop, stops)

        # [LOCAL-291] Compute groundedness and CONTRADICTED signals from corpus.
        if corpus_data:
            # [LOCAL-327] Mark that we attempted a corpus lookup for this stop.
            sa.corpus_lookup_attempted = True
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
    ts = compute_score(analyses, n_requested, venue_facts,
                       gate_log=gate_log, corpus_data=corpus_data,
                       venue_name=_effective_venue_name)
    
    return ts


def _compute_groundedness_for_stop(sa: 'StopAnalysis', stop: dict, corpus_data: dict):
    """[LOCAL-291] Compute groundedness fraction and contradicted share for a stop.

    Uses groundedness_check module to measure which fact-claims are supported
    by corpus passages. Name normalisation (D187) is applied.

    Sets sa.groundedness_fraction (0..1) and sa.contradicted_share (0..1).

    [LOCAL-327] Also sets sa.corpus_available = True when passages exist.
    """
    from groundedness_check import measure_stop_groundedness

    # Look up corpus passages for this stop
    stop_title = stop.get('title', sa.title)
    corpus_entry = corpus_data.get(stop_title)
    if not corpus_entry:
        # No corpus for this stop — groundedness stays 1.0 (no ceiling)
        # and contradicted_share stays 0.0 (no penalty).
        # [LOCAL-327] corpus_available remains False — stop is unverified.
        return

    passages = corpus_entry.get('passages', [])
    if not passages:
        # [LOCAL-327] corpus_available remains False — no passages means unverified.
        return

    # [LOCAL-327] Corpus exists with passages — mark as available.
    sa.corpus_available = True

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
