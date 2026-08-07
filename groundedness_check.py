#!/usr/bin/env python3
"""groundedness_check.py — LOCAL-291: Groundedness measurement and scoring.

Computes per-stop groundedness: the fraction of extracted fact-claims that are
present (SUPPORTED) in that stop's `stop_corpus` passages.

Design principles (from LOCAL-291 task specification):
- Ungrounded ≠ fabricated. An ungrounded fact is unverified, NOT false.
- Groundedness never reduces a score. It only caps the band: a stop below the
  groundedness floor cannot be classified RICH.
- CONTRADICTED is the only signal that can score negative.
- Name normalisation is applied before judging groundedness (D187 fix).

Emits:
- Per-stop groundedness fraction.
- Ungrounded claims as a corpus worklist (for LOCAL-283 harvester).
- CONTRADICTED claims identified from corpus contradiction.
"""
import os
import re
import sys
import json
import unicodedata
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


# ─── Name normalisation (D187) ──────────────────────────────────────────────
#
# "Baroness Béatrice" / "Béatrice Ephrussi" / "Béatrice de Rothschild" are the
# same person. The pre-291 code counts ungrounded when the narration says
# "Baroness Béatrice" and the corpus says "Béatrice de Rothschild".
#
# Normalisation rules:
# 1. Strip accents: é→e, â→a, ô→o, ç→c
# 2. Lowercase
# 3. Remove common titles/honorifics: Baroness, Baron, Sir, Dame, Count, etc.
# 4. Remove particles: de, du, di, von, van, d', la, le, des, della, della
# 5. Sort remaining name tokens alphabetically → canonical form
#
# Two names match if their canonical forms share ≥1 significant token AND
# the Jaccard similarity of their token sets exceeds 0.4.

_TITLES = {
    'baroness', 'baron', 'sir', 'dame', 'count', 'countess', 'duke', 'duchess',
    'prince', 'princess', 'king', 'queen', 'emperor', 'empress', 'cardinal',
    'saint', 'sainte', 'st', 'ste', 'lord', 'lady', 'general', 'admiral',
    'captain', 'colonel', 'major', 'monseigneur', 'archbishop', 'bishop',
    'father', 'mother', 'brother', 'sister', 'reverend', 'professor',
    'monsieur', 'madame', 'mademoiselle', 'mr', 'mrs', 'ms', 'dr',
}

_PARTICLES = {
    'de', 'du', 'di', 'von', 'van', 'le', 'la', 'les', 'des', 'della',
    'del', 'den', 'der', 'het', 'el', 'al', 'da', 'dos', 'das',
}


def _strip_accents(text: str) -> str:
    """Remove diacritics for matching (é→e, ô→o)."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def normalize_name(name: str) -> List[str]:
    """Normalize a person name to canonical token set.

    Returns sorted list of significant tokens (no titles, no particles,
    accent-folded, lowercased).
    """
    # Strip accents and lowercase
    folded = _strip_accents(name).lower()
    # Remove apostrophe-particles ("d'Antibes" → "antibes")
    folded = re.sub(r"\bd'", '', folded)
    # Tokenize
    tokens = re.findall(r'[a-z]+', folded)
    # Remove titles and particles
    significant = [t for t in tokens if t not in _TITLES and t not in _PARTICLES and len(t) > 1]
    return sorted(significant)


def names_match(name_a: str, name_b: str) -> bool:
    """Check if two person names refer to the same individual.

    Uses normalised token sets with Jaccard-like matching:
    - Must share at least 1 significant token
    - Overlap must be ≥ 40% of the smaller set (asymmetric for partial names)
    """
    tokens_a = set(normalize_name(name_a))
    tokens_b = set(normalize_name(name_b))

    if not tokens_a or not tokens_b:
        return False

    overlap = tokens_a & tokens_b
    if not overlap:
        return False

    # Asymmetric: use the smaller set as denominator
    # "Béatrice" (1 token) matches "Béatrice de Rothschild" (2 tokens) = 1/1 = 100%
    # "Baroness Béatrice" (1 after strip) matches "Béatrice Ephrussi" (2) = 1/1 = 100%
    smaller = min(len(tokens_a), len(tokens_b))
    return len(overlap) / smaller >= 0.4


def _normalize_text_for_search(text: str) -> str:
    """Normalize text for substring searching — accent-fold + lowercase."""
    return _strip_accents(text).lower()


# ─── Fact claim extraction (reuses tour_rubric_scorer patterns) ──────────────

#: A capitalised multi-word phrase — a *candidate* person name.
_PROPER_PHRASE_RE = re.compile(
    r'\b([A-Z][a-zéèêëàâùûôîïçñ]+'
    r"(?:\s+(?:de|des|du|di|van|von|le|la|d'))?"
    r'\s+[A-Z][a-zéèêëàâùûôîïçñ]+'
    r'(?:\s+[A-Z][a-zéèêëàâùûôîïçñ]+)?)\b'
)

_NOT_A_PERSON_RE = re.compile(
    r'(?i)\b(?:sea|ocean|riviera|village|hill|pond|fountain|square|street|road|'
    r'avenue|boulevard|monument|bandstand|house|cathedral|chapel|garden|park|'
    r'beach|island|museum|mus[eé]e|fondation|palais|port|cape|mount|tower|'
    r'bridge|gate|hotel|castle|fort|abbey|basilica|collection|gallery|'
    r'exhibition|exhibit|installation|examples|details|specialty|information|'
    r'americans?|century|war|succession|'
    # [LOCAL-340] "Chez X" is a restaurant/business, not a person (mirrors
    # LOCAL-339 fix in tour_rubric_scorer.py).
    r'chez)\b'
)

_PERSON_CONTEXT_RE = re.compile(
    r'(?i)\b(?:painted|paints|wrote|writes|composed|designed|founded|built|'
    r'established|created|sculpted|carved|lived|worked|visited|ruled|'
    r'commanded|led|inspired|donated|bequeathed|commissioned|discovered|'
    r'architect|painter|artist|sculptor|philosopher|playwright|novelist|poet|'
    r'writer|composer|emperor|empress|king|queen|duke|duchess|general|'
    r'admiral|monk|priest|patron|collector|gallerist|buried|resided|'
    r'restored|renovated|purchased|married|born|died|known)\b'
)

_PERSON_CONTEXT_WINDOW = 90


@dataclass
class FactClaim:
    """A single extractable fact from tour narration."""
    text: str          # The claim text
    claim_type: str    # 'person', 'date', 'artwork', 'material', 'measurement', 'period'
    sentence: str      # Source sentence


@dataclass
class GroundednessResult:
    """Per-stop groundedness assessment."""
    stop_title: str
    total_claims: int
    grounded_claims: int
    ungrounded_claims: int
    contradicted_claims: int
    # [LOCAL-343] None when total_claims == 0: nothing was checkable, so
    # groundedness is unmeasured — not vacuously 1.0.
    groundedness_fraction: Optional[float]
    claims_detail: List[Dict] = field(default_factory=list)
    # The ungrounded claims as a worklist
    corpus_worklist: List[Dict] = field(default_factory=list)


def extract_fact_claims(text: str, stop_title: str = "") -> List[FactClaim]:
    """Extract checkable fact-claims from narration text.

    [LOCAL-344] THE PROPERTY: anything the fact detector counts as a fact must
    be represented in the claim set. Enforced structurally — the claim extractor
    delegates to the same analyze_stop() that the scorer uses, then promotes
    every detected fact to a FactClaim. This guarantees alignment without
    enumerating categories (D236: enumeration is how we got blind spots).

    Extracts:
    - Named people (with context-verified person detection)
    - Specific dates/years (4-digit years, centuries)
    - Named artworks (quoted titles)
    - Materials/techniques (structural + vocabulary detection)
    - Measurements/numbers (digit + unit, spelled-out numeral + noun)
    - Named periods (dynasties, eras, epochs, etc.)
    """
    claims = []

    # Split into sentences for context
    sentences = re.split(r'(?<=[.!?])\s+', text)

    for sentence in sentences:
        if len(sentence.strip()) < 15:
            continue

        # Named people
        for m in _PROPER_PHRASE_RE.finditer(sentence):
            name = m.group(1)
            if _NOT_A_PERSON_RE.search(name):
                continue
            lo = max(0, m.start() - _PERSON_CONTEXT_WINDOW)
            hi = min(len(sentence), m.end() + _PERSON_CONTEXT_WINDOW)
            if _PERSON_CONTEXT_RE.search(sentence[lo:hi]):
                claims.append(FactClaim(
                    text=name,
                    claim_type='person',
                    sentence=sentence,
                ))

        # Dates/years (4-digit years)
        for m in re.finditer(r'\b(\d{4})\b', sentence):
            year = int(m.group(1))
            if 1000 <= year <= 2030:
                claims.append(FactClaim(
                    text=m.group(1),
                    claim_type='date',
                    sentence=sentence,
                ))

        # Centuries
        for m in re.finditer(r'\b(\d{1,2}(?:st|nd|rd|th)\s+century)\b', sentence, re.IGNORECASE):
            claims.append(FactClaim(
                text=m.group(1),
                claim_type='date',
                sentence=sentence,
            ))

        # Named artworks (quoted)
        for m in re.finditer(r'["\u201c\u201d\u00ab]([^"\u201c\u201d\u00bb]+)["\u201c\u201d\u00bb]', sentence):
            artwork = m.group(1)
            if len(artwork) > 3:
                claims.append(FactClaim(
                    text=artwork,
                    claim_type='artwork',
                    sentence=sentence,
                ))

    # ─── [LOCAL-344] Structural alignment: delegate to the fact detector ─────
    # Run analyze_stop to get the SAME facts the scorer counts, then promote
    # each to a FactClaim. This closes the gap that caused 55% of stops to
    # have zero groundedness claims despite having counted facts.
    from tour_rubric_scorer import analyze_stop as _analyze_stop
    _stop = {'index': 0, 'title': stop_title or 'untitled', 'body': text}
    _sa = _analyze_stop(_stop, [_stop])

    # Find the sentence containing each fact for context
    def _find_sentence(fact_text: str) -> str:
        """Find the source sentence for a fact, for FactClaim.sentence."""
        fact_lower = fact_text.lower()
        for s in sentences:
            if fact_lower in s.lower():
                return s[:200]
        return text[:200]

    # Materials/techniques
    for mat in _sa.materials_techniques:
        claims.append(FactClaim(
            text=mat,
            claim_type='material',
            sentence=_find_sentence(mat),
        ))

    # Measurements/numbers
    for meas in _sa.measurements_numbers:
        claims.append(FactClaim(
            text=meas,
            claim_type='measurement',
            sentence=_find_sentence(meas),
        ))

    # Named periods
    for per in _sa.named_periods:
        claims.append(FactClaim(
            text=per,
            claim_type='period',
            sentence=_find_sentence(per),
        ))

    # Deduplicate: same claim text in the same stop counts once
    seen = set()
    unique = []
    for c in claims:
        key = (c.claim_type, c.text.lower())
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique


def check_claim_grounded(claim: FactClaim, passages: List[str]) -> Tuple[str, Optional[str]]:
    """Check if a single fact-claim is grounded in corpus passages.

    Returns:
        (verdict, evidence)
        verdict: 'GROUNDED', 'UNGROUNDED', or 'CONTRADICTED'
        evidence: matching passage substring if grounded, or contradicting
                  passage substring if contradicted, or None.
    """
    if not passages:
        return ('UNGROUNDED', None)

    all_passages_text = '\n'.join(passages)
    passages_normalized = _normalize_text_for_search(all_passages_text)

    if claim.claim_type == 'date':
        # A date is grounded if the exact number appears in passages
        if claim.text in all_passages_text:
            # Find the passage containing it
            for p in passages:
                if claim.text in p:
                    # Extract context
                    idx = p.find(claim.text)
                    start = max(0, idx - 40)
                    end = min(len(p), idx + len(claim.text) + 40)
                    return ('GROUNDED', p[start:end].strip())
            return ('GROUNDED', claim.text)

        # Century references: "17th century" → check for 1600-1699 dates or "17th century" text
        century_match = re.match(r'(\d{1,2})(?:st|nd|rd|th)\s+century', claim.text, re.IGNORECASE)
        if century_match:
            century_num = int(century_match.group(1))
            century_text_norm = _normalize_text_for_search(claim.text)
            if century_text_norm in passages_normalized:
                return ('GROUNDED', claim.text)

        # Not found — but is it CONTRADICTED?
        # A date is contradicted only if the passage asserts a DIFFERENT date
        # for the SAME event/subject. We defer full contradiction to claim_check.py.
        return ('UNGROUNDED', None)

    elif claim.claim_type == 'person':
        # A person name is grounded if ANY normalised form appears in passages
        claim_tokens = normalize_name(claim.text)

        # Direct substring match (accent-folded)
        claim_normalized = _normalize_text_for_search(claim.text)
        if claim_normalized in passages_normalized:
            for p in passages:
                if claim_normalized in _normalize_text_for_search(p):
                    idx = _normalize_text_for_search(p).find(claim_normalized)
                    start = max(0, idx - 20)
                    end = min(len(p), idx + len(claim_normalized) + 20)
                    return ('GROUNDED', p[start:end].strip())
            return ('GROUNDED', claim.text)

        # Name normalisation match (D187): check if any person name in
        # passages matches via normalised tokens
        # Extract all proper-noun phrases from passages and check name match
        for p in passages:
            for m in _PROPER_PHRASE_RE.finditer(p):
                passage_name = m.group(1)
                if names_match(claim.text, passage_name):
                    return ('GROUNDED', f"{passage_name} (normalised match for {claim.text})")

        # Also check individual significant tokens as last resort
        # If ALL significant tokens from the claim appear in passages, it's grounded
        if claim_tokens and all(t in passages_normalized for t in claim_tokens):
            return ('GROUNDED', f"all tokens {claim_tokens} found in passages")

        return ('UNGROUNDED', None)

    elif claim.claim_type == 'artwork':
        # Artwork title: check accent-folded substring match
        claim_normalized = _normalize_text_for_search(claim.text)
        if claim_normalized in passages_normalized:
            return ('GROUNDED', claim.text)

        # Check with quotes stripped and partial match (at least 60% of words)
        artwork_tokens = set(re.findall(r'[a-z]+', claim_normalized))
        if artwork_tokens:
            found_tokens = sum(1 for t in artwork_tokens if t in passages_normalized and len(t) > 2)
            if found_tokens / len(artwork_tokens) >= 0.6:
                return ('GROUNDED', f"partial match: {found_tokens}/{len(artwork_tokens)} tokens")

        return ('UNGROUNDED', None)

    # ─── [LOCAL-344] New claim types: material, measurement, period ───────
    elif claim.claim_type == 'material':
        # A material is grounded if the term appears in passages (accent-folded).
        # Matches: "chlorite" in passages, "oil on canvas" in passages, etc.
        claim_normalized = _normalize_text_for_search(claim.text)
        if claim_normalized in passages_normalized:
            for p in passages:
                if claim_normalized in _normalize_text_for_search(p):
                    idx = _normalize_text_for_search(p).find(claim_normalized)
                    start = max(0, idx - 30)
                    end = min(len(p), idx + len(claim_normalized) + 30)
                    return ('GROUNDED', p[start:end].strip())
            return ('GROUNDED', claim.text)
        return ('UNGROUNDED', None)

    elif claim.claim_type == 'measurement':
        # A measurement is grounded if its significant tokens appear in passages.
        # "three Michelin stars" → check all content words present.
        # Also check exact substring match first.
        claim_normalized = _normalize_text_for_search(claim.text)
        if claim_normalized in passages_normalized:
            for p in passages:
                if claim_normalized in _normalize_text_for_search(p):
                    idx = _normalize_text_for_search(p).find(claim_normalized)
                    start = max(0, idx - 30)
                    end = min(len(p), idx + len(claim_normalized) + 30)
                    return ('GROUNDED', p[start:end].strip())
            return ('GROUNDED', claim.text)

        # Token-level: all significant tokens (len>2) must be present
        tokens = [t for t in re.findall(r'[a-z0-9]+', claim_normalized) if len(t) > 2]
        if tokens and all(t in passages_normalized for t in tokens):
            return ('GROUNDED', f"all tokens {tokens} found in passages")

        # Digit equivalence: "three" in claim ↔ "3" in passages (and vice versa)
        _WORD_TO_DIGIT = {
            'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5',
            'six': '6', 'seven': '7', 'eight': '8', 'nine': '9', 'ten': '10',
            'eleven': '11', 'twelve': '12', 'thirteen': '13', 'fourteen': '14',
            'fifteen': '15', 'sixteen': '16', 'seventeen': '17',
            'eighteen': '18', 'nineteen': '19', 'twenty': '20',
            'thirty': '30', 'forty': '40', 'fifty': '50',
            'sixty': '60', 'seventy': '70', 'eighty': '80', 'ninety': '90',
            'hundred': '100', 'thousand': '1000',
        }
        # Try replacing spelled-out numerals with digits
        alt_tokens = []
        for t in tokens:
            if t in _WORD_TO_DIGIT:
                alt_tokens.append(_WORD_TO_DIGIT[t])
            else:
                alt_tokens.append(t)
        if alt_tokens != tokens and all(t in passages_normalized for t in alt_tokens):
            return ('GROUNDED', f"digit-equivalent tokens {alt_tokens} found")

        return ('UNGROUNDED', None)

    elif claim.claim_type == 'period':
        # A period name is grounded if it appears in passages (accent-folded).
        # "Heian" in passages, "Pala-Sena" in passages, etc.
        claim_normalized = _normalize_text_for_search(claim.text)
        if claim_normalized in passages_normalized:
            for p in passages:
                if claim_normalized in _normalize_text_for_search(p):
                    idx = _normalize_text_for_search(p).find(claim_normalized)
                    start = max(0, idx - 30)
                    end = min(len(p), idx + len(claim_normalized) + 30)
                    return ('GROUNDED', p[start:end].strip())
            return ('GROUNDED', claim.text)
        # Also try individual tokens for hyphenated periods (Pala-Sena → Pala, Sena)
        period_tokens = [t for t in re.split(r'[-\s]', claim_normalized) if len(t) > 2]
        if period_tokens and all(t in passages_normalized for t in period_tokens):
            return ('GROUNDED', f"all period tokens {period_tokens} found")
        return ('UNGROUNDED', None)

    return ('UNGROUNDED', None)


def measure_stop_groundedness(
    stop_text: str,
    stop_title: str,
    passages: List[str],
) -> GroundednessResult:
    """Compute groundedness for a single stop.

    Args:
        stop_text: The narration body text for this stop.
        stop_title: Title of the stop.
        passages: Corpus passages for this stop from stop_corpus.

    Returns:
        GroundednessResult with per-claim detail and worklist.
    """
    claims = extract_fact_claims(stop_text, stop_title)

    grounded = 0
    ungrounded = 0
    contradicted = 0
    details = []
    worklist = []

    for claim in claims:
        verdict, evidence = check_claim_grounded(claim, passages)

        details.append({
            'text': claim.text,
            'type': claim.claim_type,
            'verdict': verdict,
            'evidence': evidence,
            'sentence': claim.sentence[:120],
        })

        if verdict == 'GROUNDED':
            grounded += 1
        elif verdict == 'CONTRADICTED':
            contradicted += 1
        else:
            ungrounded += 1
            worklist.append({
                'claim_text': claim.text,
                'claim_type': claim.claim_type,
                'stop_title': stop_title,
                'sentence': claim.sentence[:200],
            })

    total = grounded + ungrounded + contradicted
    # [LOCAL-343] Zero claims → None (unmeasured), NOT 1.0.
    # "Nothing to check" is not "everything checked and verified."
    # A vacuous 1.0 would let a stop pass quality gates it never cleared.
    fraction = grounded / total if total > 0 else None

    return GroundednessResult(
        stop_title=stop_title,
        total_claims=total,
        grounded_claims=grounded,
        ungrounded_claims=ungrounded,
        contradicted_claims=contradicted,
        groundedness_fraction=fraction,
        claims_detail=details,
        corpus_worklist=worklist,
    )


def measure_tour_groundedness(
    tour_text: str,
    venue_name: str,
    conn,
) -> Dict:
    """Measure groundedness across all stops in a tour file.

    Args:
        tour_text: Full tour text content.
        venue_name: The venue name for corpus lookup.
        conn: Database connection.

    Returns dict with per-stop results, aggregates, and corpus worklist.
    """
    from stop_corpus_reader import get_stop_corpus_for_tour

    # Use the scorer's own parser for consistency (it strips schema labels)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from tour_rubric_scorer import parse_tour, SCHEMA_LABEL_RE

    stops_parsed = parse_tour(tour_text)

    if not stops_parsed:
        return {'error': 'No stops found in tour text', 'stops': []}

    # Get corpus data
    stop_names = [s['title'] for s in stops_parsed]
    corpus_data = get_stop_corpus_for_tour(venue_name, stop_names, conn)

    # Measure each stop
    results = []
    total_claims = 0
    total_grounded = 0
    total_ungrounded = 0
    total_contradicted = 0
    full_worklist = []

    for stop in stops_parsed:
        corpus_entry = corpus_data.get(stop['title'])
        passages = corpus_entry['passages'] if corpus_entry else []

        # Use the body text (already schema-stripped by parse_tour)
        result = measure_stop_groundedness(stop['body'], stop['title'], passages)
        results.append(result)

        total_claims += result.total_claims
        total_grounded += result.grounded_claims
        total_ungrounded += result.ungrounded_claims
        total_contradicted += result.contradicted_claims
        full_worklist.extend(result.corpus_worklist)

    # [LOCAL-343] Same principle at aggregate level: zero total claims → None.
    overall_fraction = total_grounded / total_claims if total_claims > 0 else None

    return {
        'stops': results,
        'total_claims': total_claims,
        'total_grounded': total_grounded,
        'total_ungrounded': total_ungrounded,
        'total_contradicted': total_contradicted,
        'overall_groundedness': overall_fraction,
        'corpus_worklist': full_worklist,
    }
