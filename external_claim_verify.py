"""external_claim_verify.py — LOCAL-221: External source verification for UNSUPPORTED claims.

When claim_check marks a claim UNSUPPORTED (corpus has no passage backing it),
this module searches external sources to determine if the claim is actually true.

Design principles (from D100, D51, D62):
- Build a query from the claim AND its stop context, not from keywords alone.
- A search result that mentions the right words is NOT a source (D62).
- The supporting sentence must assert the same fact about the same subject.
- Unit conversions must be checked, not assumed.
- A promoted claim that is wrong is worse than an unpromoted one that is right.
- When uncertain, do NOT promote.

Reuses:
- work_story_searcher._serp_search() for Serper queries
- story_miner._fetch_page_text() for page fetching

New verdict: SUPPORTED_EXTERNAL — distinct from SUPPORTED_PARAPHRASE.
Stores: URL, trust tier (D51), and the sentence that supports it.

Behind DISABLE_EXTERNAL_VERIFY=1 (disabled by default when set).
"""

import os
import re
import json
import logging
import unicodedata
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger("external_claim_verify")

# ─── Verdict ─────────────────────────────────────────────────────────────────

SUPPORTED_EXTERNAL = 'SUPPORTED_EXTERNAL'

# ─── Feature flag ────────────────────────────────────────────────────────────

def is_external_verify_enabled() -> bool:
    """Check if external verification is enabled (default: enabled).
    Set DISABLE_EXTERNAL_VERIFY=1 to disable."""
    return os.environ.get('DISABLE_EXTERNAL_VERIFY', '').strip() != '1'


# ─── Text utilities ──────────────────────────────────────────────────────────

def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def _normalize(text: str) -> str:
    return re.sub(r'\s+', ' ', _strip_accents(text).lower()).strip()


def _tokenize(text: str) -> List[str]:
    return re.findall(r'\w+', _normalize(text))


# ─── Trust tier classification (D51) ────────────────────────────────────────

def classify_source_tier(url: str) -> int:
    """Classify a URL into trust tiers per D51.
    Tier 1: Wikipedia, official government/institutional, major encyclopedias
    Tier 2: Established travel/history sites, regional tourism offices
    Tier 3: Blogs, forums, unverified sites
    Returns 0 for rejected/untrusted sources.
    """
    domain = urlparse(url).netloc.lower()
    # Remove www prefix
    if domain.startswith('www.'):
        domain = domain[4:]

    # Tier 1: Encyclopedic, governmental, academic
    tier1_domains = {
        'wikipedia.org', 'en.wikipedia.org', 'fr.wikipedia.org',
        'britannica.com', 'wikidata.org',
        'culture.gouv.fr', 'pop.culture.gouv.fr',
        'education.gouv.fr', 'archives.gov',
        'loc.gov',  # Library of Congress
    }
    tier1_suffixes = ('.gov', '.edu', '.gouv.fr', '.ac.uk')

    if any(t1 in domain for t1 in tier1_domains):
        return 1
    if any(domain.endswith(s) for s in tier1_suffixes):
        return 1

    # Tier 2: Established reference sites, tourism offices, museums
    tier2_patterns = (
        'nicetourisme', 'cotedazurfrance', 'visitnice',
        'tourisme', 'museum', 'musee', 'musée',
        'francebleu', 'france3', 'bbc.', 'theguardian',
        'smithsonianmag', 'nationalgeographic', 'history.com',
        'atlasobscura', 'tripadvisor',
        'marinetraffic', 'noaa.gov', 'shom.fr',  # Maritime/depth data
    )
    if any(p in domain for p in tier2_patterns):
        return 2

    # Tier 2: Regional/national news
    tier2_news = ('lemonde.fr', 'lefigaro.fr', 'nytimes.com', 'reuters.com')
    if any(domain.endswith(n) for n in tier2_news):
        return 2

    # Tier 3: Everything else that isn't rejected
    rejected_domains = (
        'pinterest.', 'facebook.', 'instagram.', 'twitter.',
        'youtube.', 'tiktok.', 'reddit.',
    )
    if any(r in domain for r in rejected_domains):
        return 0

    return 3


# ─── Query synthesis ─────────────────────────────────────────────────────────

def build_verification_queries(claims: List[Dict], stop_title: str,
                                venue_name: str = "") -> List[Dict]:
    """Build search queries for a batch of UNSUPPORTED claims.
    
    Groups claims by entity/subject when possible to reduce query count.
    Each query maps back to the claims it covers.
    
    Args:
        claims: List of claim dicts with 'text' and 'type' keys.
        stop_title: The stop/POI this paragraph belongs to.
        venue_name: The broader venue/tour name for context.
    
    Returns:
        List of {query: str, claim_indices: [int], context: str}
    """
    if not claims:
        return []

    # Extract location context
    city = ""
    if venue_name:
        parts = venue_name.split(',')
        if len(parts) > 1:
            city = parts[1].strip()
        elif 'nice' in venue_name.lower():
            city = 'Nice'
        elif 'riviera' in venue_name.lower():
            city = 'French Riviera'

    # Group claims by shared entities/subjects for batching
    queries = []
    used_indices = set()

    # Strategy 1: Group claims that share the same subject noun
    subject_groups = {}
    for i, claim in enumerate(claims):
        # Extract the subject (first proper noun or the stop title if mentioned)
        text = claim['text']
        # Strip context annotation
        core_text = text.split(' (')[0].strip() if ' (' in text else text
        
        # LOCAL-221 fix: Use the source sentence for subject extraction when
        # the claim text is bare (a number/date with no proper nouns).
        # "320 feet" has no extractable subject, but "the deep bay provides
        # secure anchorage, with depths reaching 320 feet" does.
        sentence = claim.get('sentence', '')
        subject_source = sentence if sentence else core_text
        subject = _extract_subject(subject_source, stop_title)
        if subject not in subject_groups:
            subject_groups[subject] = []
        subject_groups[subject].append(i)

    # Build one query per subject group
    for subject, indices in subject_groups.items():
        # Collect key facts from all claims in this group
        facts = []
        for idx in indices:
            core = claims[idx]['text'].split(' (')[0].strip() if ' (' in claims[idx]['text'] else claims[idx]['text']
            # LOCAL-221: For bare numeric/date claims, extract key context words
            # from the sentence to make the query meaningful.
            sentence = claims[idx].get('sentence', '')
            if sentence and not any(c.isupper() for c in core if c.isalpha()):
                # Bare claim (no proper nouns) — extract meaningful context words
                # that describe WHAT the number refers to
                context_words = _extract_query_context(sentence, core)
                if context_words:
                    facts.append(f'{context_words} {core}')
                else:
                    facts.append(core)
            else:
                facts.append(core)

        # Build a targeted query
        # Use the most specific fact + location context
        if len(facts) == 1:
            query_text = f'"{subject}" {facts[0]} {city}'.strip()
        else:
            # Multiple facts about same subject — use the most distinctive
            # Prefer numbers/dates as they're most searchable
            key_fact = facts[0]
            for f in facts:
                if any(c.isdigit() for c in f):
                    key_fact = f
                    break
            query_text = f'"{subject}" {key_fact} {city}'.strip()

        # Limit query length
        if len(query_text) > 200:
            query_text = query_text[:200]

        queries.append({
            'query': query_text,
            'claim_indices': indices,
            'context': f'{stop_title} / {subject}',
        })
        used_indices.update(indices)

    # Strategy 2: Individual queries for any remaining claims
    for i, claim in enumerate(claims):
        if i in used_indices:
            continue
        core = claim['text'].split(' (')[0].strip() if ' (' in claim['text'] else claim['text']
        # LOCAL-221: use sentence context for bare claims
        sentence = claim.get('sentence', '')
        if sentence and not any(c.isupper() for c in core if c.isalpha()):
            context_words = _extract_query_context(sentence, core)
            if context_words:
                query_text = f'{context_words} {core} {stop_title} {city}'.strip()
            else:
                query_text = f'{core} {stop_title} {city}'.strip()
        else:
            query_text = f'{core} {stop_title} {city}'.strip()
        if len(query_text) > 200:
            query_text = query_text[:200]
        queries.append({
            'query': query_text,
            'claim_indices': [i],
            'context': f'{stop_title}',
        })

    return queries


def _extract_query_context(sentence: str, claim_value: str) -> str:
    """Extract meaningful context words from a sentence to build a search query.
    
    When the claim is bare (e.g. "320 feet"), we need words from the sentence
    that describe WHAT the number refers to. For "the deep bay provides secure
    anchorage, with depths reaching 320 feet", we want "bay depth anchorage".
    
    Returns a short string of 2-4 context keywords, or '' if nothing useful.
    """
    # Remove the claim value itself from the sentence
    remaining = sentence.replace(claim_value, '').strip()
    
    # Tokenize and remove stop words
    tokens = _tokenize(remaining)
    stop_words = {
        'the', 'a', 'an', 'is', 'was', 'are', 'were', 'has', 'had', 'have',
        'this', 'that', 'its', 'with', 'from', 'for', 'and', 'but', 'not',
        'you', 'your', 'can', 'will', 'would', 'could', 'should', 'may',
        'might', 'into', 'onto', 'upon', 'over', 'under', 'between',
        'through', 'about', 'here', 'there', 'where', 'when', 'which',
        'what', 'who', 'how', 'been', 'being', 'also', 'very', 'just',
        'than', 'then', 'more', 'most', 'some', 'each', 'every', 'both',
        'such', 'only', 'still', 'even', 'well', 'back', 'much',
        'these', 'those', 'other', 'many', 'like', 'make', 'made',
        'providing', 'provides', 'reaching', 'reaches', 'offering',
    }
    meaningful = [t for t in tokens if t not in stop_words and len(t) > 2]
    
    # Take the most distinctive 3-4 words (prefer nouns — longer words)
    # Sort by length descending as a proxy for specificity
    meaningful.sort(key=lambda w: len(w), reverse=True)
    
    return ' '.join(meaningful[:4])


def _extract_subject(claim_text: str, stop_title: str) -> str:
    """Extract the primary subject from a claim for query grouping.
    
    The subject is the entity the claim is ABOUT. For evidence matching,
    the source must mention this subject — otherwise word overlap alone
    is meaningless (D62).
    
    Priority:
    1. If claim_text contains the stop title → stop_title
    2. Multi-word proper noun phrase in the text (≥2 meaningful words)
    3. Fallback: stop_title (forces source to mention the stop)
    
    Common false subjects (articles, generic adjectives) are explicitly excluded.
    """
    # If the claim mentions the stop title, that's the subject
    if _normalize(stop_title) in _normalize(claim_text):
        return stop_title

    # Skip words that are NOT meaningful subjects
    # French and English articles, prepositions, generic adjectives
    skip_words = {
        'The', 'A', 'An', 'In', 'At', 'On', 'By', 'It', 'Its', 'This', 'That',
        'Le', 'La', 'Les', 'Un', 'Une', 'Des', 'Du', 'De', 'L',
        'From', 'For', 'With', 'To', 'As', 'But', 'And', 'Or', 'If',
        'French', 'English', 'Italian', 'Spanish', 'German', 'American',
        'European', 'Mediterranean', 'National', 'Royal', 'Grand',
        'Dans', 'Sur', 'Avec', 'Pour', 'Par', 'Et', 'Ou', 'Cette',
        'Step', 'Stop', 'Here', 'There', 'Today', 'Now', 'Then',
        # Months (often capitalized but not subjects)
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December',
        'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
        'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre',
    }

    # Look for proper noun phrases (capitalized multi-word sequences)
    words = claim_text.split()
    proper_nouns = []
    for w in words:
        # Strip punctuation for matching
        clean_w = w.strip("'\".,;:!?()[]{}«»")
        if not clean_w:
            continue
        # Skip known non-subject words
        if clean_w in skip_words:
            if proper_nouns:
                break
            continue
        # Skip single-letter words (L', D', etc.)
        if len(clean_w) <= 1:
            if proper_nouns:
                break
            continue
        if clean_w and clean_w[0].isupper() and not clean_w.isupper():
            proper_nouns.append(clean_w)
        elif proper_nouns:
            break

    # Require at least 2 characters in the proper noun to be meaningful
    # Single words like "French" or "Step" are too generic
    if proper_nouns and len(' '.join(proper_nouns)) >= 4:
        # Verify it's not just a generic nationality/adjective alone
        subject = ' '.join(proper_nouns)
        generic_lone = {'French', 'English', 'Italian', 'Spanish', 'European',
                       'American', 'National', 'Royal', 'Modern', 'Ancient',
                       'Grand', 'Ancien', 'Nouveau', 'Premier', 'Dernier'}
        if subject not in generic_lone:
            return subject

    # Fallback: use the stop title as subject.
    # This is IMPORTANT for safety: it forces the source sentence to mention
    # the stop, preventing false promotions from unrelated pages that happen
    # to contain the same year/number.
    return stop_title


# ─── Sentence-level evidence matching ───────────────────────────────────────

def _split_sentences(text: str) -> List[str]:
    """Split text into sentences."""
    # Split on period/exclamation/question followed by space+capital or end
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    return [s.strip() for s in sentences if s.strip() and len(s.strip()) > 20]


def _extract_numbers(text: str) -> List[Tuple[float, str]]:
    """Extract numbers with their units from text.
    Returns list of (value, unit) tuples."""
    results = []
    # Match patterns like "320 feet", "97.5 m", "1,200 meters", "1888"
    patterns = [
        r'(\d[\d,]*\.?\d*)\s*(feet|ft|foot|metres?|meters?|m|km|miles?|mi)',
        r'(\d[\d,]*\.?\d*)\s*(years?|centuries?|decades?)',
        r'(\d{4})',  # Years
        r'(\d[\d,]*\.?\d*)\s*(pieces?|works?|paintings?|items?)',
    ]
    for pat in patterns:
        for match in re.finditer(pat, text, re.IGNORECASE):
            val_str = match.group(1).replace(',', '')
            try:
                val = float(val_str)
                unit = match.group(2) if match.lastindex >= 2 else ''
                results.append((val, unit.lower()))
            except ValueError:
                pass
    return results


# Unit conversion factors to meters
_TO_METERS = {
    'feet': 0.3048, 'ft': 0.3048, 'foot': 0.3048,
    'meter': 1.0, 'meters': 1.0, 'metre': 1.0, 'metres': 1.0, 'm': 1.0,
    'km': 1000.0, 'miles': 1609.34, 'mile': 1609.34, 'mi': 1609.34,
}


def _numbers_compatible(claim_nums: List[Tuple[float, str]],
                         source_nums: List[Tuple[float, str]],
                         tolerance: float = 0.15) -> bool:
    """Check if numbers in claim and source are compatible (same measurement).
    
    Handles unit conversions. Returns True only if a source number matches
    the claim's number within tolerance after conversion.
    
    Years (4-digit numbers without units) require EXACT match — a 15%
    tolerance would make 1963 ≈ 1973 which is incorrect for dates.
    """
    if not claim_nums or not source_nums:
        return True  # No numbers to compare = not a numeric mismatch

    for c_val, c_unit in claim_nums:
        # Convert claim value to meters (if spatial unit)
        c_meters = None
        if c_unit in _TO_METERS:
            c_meters = c_val * _TO_METERS[c_unit]

        # Detect if this is a year (4-digit number without a unit)
        is_year = (not c_unit and 1000 < c_val < 2100 and c_val == int(c_val))

        matched = False
        for s_val, s_unit in source_nums:
            # Year comparison: exact match only (LOCAL-221 fix)
            if is_year and not s_unit and 1000 < s_val < 2100 and s_val == int(s_val):
                if c_val == s_val:
                    matched = True
                    break
                else:
                    continue  # Different year — not compatible

            # Direct comparison (same unit or both unitless, non-year)
            if c_unit == s_unit or (not c_unit and not s_unit):
                if not is_year:  # Guard: don't fall through for years
                    if abs(c_val - s_val) / max(c_val, 1) <= tolerance:
                        matched = True
                        break

            # Cross-unit comparison via meters
            if c_meters is not None and s_unit in _TO_METERS:
                s_meters = s_val * _TO_METERS[s_unit]
                if abs(c_meters - s_meters) / max(c_meters, 1) <= tolerance:
                    matched = True
                    break

        if not matched and c_val > 0:
            # This claim number has no match in the source
            return False

    return True


def evaluate_evidence(claim_text: str, source_sentences: List[str],
                      stop_title: str, claim_sentence: str = "") -> Optional[Dict]:
    """Evaluate whether any source sentence actually supports the claim.
    
    Rules (D62, D100):
    - The sentence must assert the same fact about the SAME subject.
    - Unit conversions must be verified, not assumed.
    - Mere word overlap is not support.
    
    Args:
        claim_text: The extracted claim text (may be bare, e.g. '320 feet').
        source_sentences: Candidate supporting sentences from external sources.
        stop_title: The stop/POI name.
        claim_sentence: The FULL source sentence the claim was extracted from.
            Used to reconstruct subject binding when claim_text is bare.
    
    Returns: {sentence, score, reason} or None if no support found.
    """
    claim_core = claim_text.split(' (')[0].strip() if ' (' in claim_text else claim_text
    claim_norm = _normalize(claim_core)
    claim_tokens = set(_tokenize(claim_core))
    claim_numbers = _extract_numbers(claim_core)

    # LOCAL-221 fix: When the claim text is bare (a number or date without
    # surrounding context), use the full sentence for subject binding and
    # for token overlap. This is the integration defect the LEAD review found:
    # claim_check emits NUMBER claims as e.g. '320 feet', but evaluate_evidence
    # needs surrounding context to know WHAT is 320 feet deep/tall/long.
    #
    # Strategy: use claim_sentence for subject extraction and contextual token
    # matching, but still require the specific claim value (the number) to
    # appear in the source.
    context_text = claim_sentence if claim_sentence else claim_core
    context_tokens = set(_tokenize(context_text))

    # What subject is the claim about? Use the sentence for better subject extraction.
    claim_subject = _extract_subject(context_text, stop_title)
    claim_subject_norm = _normalize(claim_subject)

    best_match = None
    best_score = 0.0

    # Pre-compute distinctive subject words (handles hyphenated names like
    # "Villefranche-sur-Mer" → ["villefranche", "mer"])
    _subject_parts = re.split(r'[\s\-]+', claim_subject_norm)
    _distinctive_subject_words = [w for w in _subject_parts
                                  if len(w) > 3 and w not in ('the', 'city', 'town',
                                                              'museum', 'musee', 'sur')]

    # D62 guard: extract location/disambiguator from subject for conflation check.
    # E.g., "Musée Picasso Antibes" → location word "antibes"
    _subject_location_words = set()
    _LOCATION_INDICATORS = ('paris', 'antibes', 'nice', 'monaco', 'cannes',
                           'lyon', 'marseille', 'villefranche', 'eze')
    for sp in _subject_parts:
        if sp in _LOCATION_INDICATORS:
            _subject_location_words.add(sp)

    for sentence in source_sentences:
        sent_norm = _normalize(sentence)
        sent_tokens = set(_tokenize(sentence))

        # Rule 1: The source sentence must mention the same subject
        # Full match first, then partial (distinctive words)
        subject_found = claim_subject_norm in sent_norm
        if not subject_found:
            # Try distinctive parts (e.g., "villefranche" from "villefranche-sur-mer")
            if _distinctive_subject_words:
                subject_found = any(dw in sent_norm for dw in _distinctive_subject_words)
            else:
                subject_found = False
        if not subject_found:
            continue

        # D62 guard: If our subject has a location disambiguator (e.g. "Antibes"),
        # check that the source doesn't mention a DIFFERENT location for the same entity.
        # "Musée Picasso Paris" should NOT support claims about "Musée Picasso Antibes".
        if _subject_location_words:
            _conflation_detected = False
            for loc in _LOCATION_INDICATORS:
                if loc in sent_norm and loc not in _subject_location_words:
                    # Source mentions a different city — potential conflation
                    # Check if it's actually disambiguating the same entity
                    for dw in _distinctive_subject_words:
                        if dw in sent_norm and loc in sent_norm:
                            # Same entity name + different city = conflation
                            _conflation_detected = True
                            break
                if _conflation_detected:
                    break
            if _conflation_detected:
                continue

        # Rule 2: Token overlap — need substantial overlap beyond the subject
        # LOCAL-221 fix: When claim_text is bare (a number/date), use context_tokens
        # from the full sentence to compute meaningful overlap. The bare claim
        # "320 feet" has no context tokens; the sentence "the deep bay provides
        # secure anchorage, with depths reaching 320 feet" has many.
        subject_tokens = set(_tokenize(claim_subject))
        
        # Use context tokens (from sentence) when available and claim is bare
        effective_claim_tokens = context_tokens if claim_sentence else claim_tokens
        non_subject_tokens = effective_claim_tokens - subject_tokens
        
        if non_subject_tokens:
            overlap = non_subject_tokens & sent_tokens
            overlap_ratio = len(overlap) / len(non_subject_tokens)
        else:
            overlap = effective_claim_tokens & sent_tokens
            overlap_ratio = len(overlap) / max(len(effective_claim_tokens), 1)

        # Rule 3: If claim has numbers, source must have compatible numbers
        number_match_bonus = 0.0
        if claim_numbers:
            source_numbers = _extract_numbers(sentence)
            if not source_numbers:
                # Source has no numbers but claim does — weak evidence
                continue
            if not _numbers_compatible(claim_numbers, source_numbers):
                # Numbers don't match — this is a different measurement
                continue
            # Numbers ARE compatible — but only count as a bonus if there's also
            # some textual overlap beyond just the number. A date like "1998" appearing
            # on a random page from 1998 is not evidence about the claim's subject.
            if overlap_ratio >= 0.15:
                number_match_bonus = 0.35

        # For non-numeric claims, require at least 0.3 overlap
        # For numeric claims with SOME text overlap + number match, threshold is 0.15
        min_overlap = 0.15 if number_match_bonus > 0 else 0.3
        if overlap_ratio < min_overlap:
            continue

        # Score: combination of token overlap, number match, and subject match
        score = overlap_ratio + number_match_bonus
        if claim_subject_norm in sent_norm:
            score += 0.2  # Exact subject mention bonus

        if score > best_score:
            best_score = score
            best_match = {
                'sentence': sentence,
                'score': round(score, 3),
                'reason': f'overlap={overlap_ratio:.2f}, subject_match={claim_subject_norm in sent_norm}',
            }

    # Threshold: require at least 0.5 combined score to promote.
    # For numeric claims with verified unit conversion, 0.5 is sufficient.
    # For text-only claims, require higher confidence (0.7) to avoid
    # weak matches like "North and South" matching travel articles.
    min_threshold = 0.5 if claim_numbers else 0.7
    if best_match and best_score >= min_threshold:
        return best_match
    return None


# ─── Main verification pipeline ─────────────────────────────────────────────

def verify_unsupported_claims(
    claims: List[Dict],
    stop_title: str,
    venue_name: str = "",
    query_budget: int = 5,
) -> Dict:
    """Verify UNSUPPORTED claims against external sources.
    
    Args:
        claims: List of claim dicts from check_paragraph with verdict=UNSUPPORTED.
        stop_title: The stop/POI name.
        venue_name: Broader venue/tour name.
        query_budget: Max Serper queries for this batch.
    
    Returns:
        {
            'results': [{claim_text, verdict, url, tier, supporting_sentence, score}],
            'queries_issued': int,
            'cost': float,
            'promoted_count': int,
            'refused_count': int,
            'query_log': [{query, results_count}],
        }
    """
    from work_story_searcher import _serp_search
    from story_miner import _fetch_page_text
    from cost_rates import SERPER_COST_PER_QUERY

    if not claims:
        return {
            'results': [],
            'queries_issued': 0,
            'cost': 0.0,
            'promoted_count': 0,
            'refused_count': 0,
            'query_log': [],
        }

    # Filter out claims too short/generic to meaningfully verify externally.
    # A claim like "pop art" or "North and South" alone carries no verifiable fact.
    # Claims must be verifiable externally. A claim is verifiable if:
    # - It has a number/date (verifiable by comparison with sources), OR
    # - It has a proper noun + predicate (a falsifiable assertion), OR
    # - Its source SENTENCE provides enough context for a meaningful query.
    #
    # LOCAL-221 fix: bare claim text may be short ("21 juin 1990" = 3 tokens),
    # but if the sentence carries the subject and predicate, the claim IS
    # verifiable. The sentence is what we search with, not the bare text.
    MIN_CLAIM_TOKENS = 3  # Reduced: "320 feet" is 2 tokens but verifiable with sentence
    MIN_SENTENCE_TOKENS = 5  # The sentence must carry enough context
    verifiable_claims = []
    non_verifiable_indices = []
    for i, claim in enumerate(claims):
        core_text = claim['text'].split(' (')[0].strip() if ' (' in claim['text'] else claim['text']
        tokens = _tokenize(core_text)
        sentence = claim.get('sentence', '')
        sentence_tokens = _tokenize(sentence) if sentence else []
        
        # A claim is verifiable if it has a number/date (the thing we compare)
        has_number = any(c.isdigit() for c in core_text)
        has_predicate_signal = any(w in core_text.lower() for w in
                                    ('built', 'designed', 'founded', 'established',
                                     'created', 'opened', 'named', 'known as',
                                     'located', 'constructed', 'completed'))
        
        # With sentence context, even short claims like "1990" or "320 feet"
        # are verifiable if the sentence names the subject.
        if has_number and sentence and len(sentence_tokens) >= MIN_SENTENCE_TOKENS:
            verifiable_claims.append((i, claim))
            continue
        
        # Predicate claims with sentence context
        if has_predicate_signal and sentence and len(sentence_tokens) >= MIN_SENTENCE_TOKENS:
            verifiable_claims.append((i, claim))
            continue
        
        # Claims with enough tokens on their own (e.g. "known as 'the Biblical Message series'")
        if len(tokens) >= 4:
            verifiable_claims.append((i, claim))
            continue
            
        # Claims too short AND no sentence context — can't verify
        if len(tokens) < MIN_CLAIM_TOKENS and not sentence:
            non_verifiable_indices.append(i)
            continue
            
        # Short claims without number/predicate and insufficient sentence
        if not has_number and not has_predicate_signal and len(sentence_tokens) < MIN_SENTENCE_TOKENS:
            non_verifiable_indices.append(i)
            continue
        
        # Fallback: movement/composition claims are often short but identifiable
        # in context — allow if sentence provides subject
        if sentence and len(sentence_tokens) >= MIN_SENTENCE_TOKENS:
            verifiable_claims.append((i, claim))
        else:
            non_verifiable_indices.append(i)

    # Build batched queries (only for verifiable claims)
    verifiable_claim_list = [c for _, c in verifiable_claims]
    query_specs = build_verification_queries(verifiable_claim_list, stop_title, venue_name)

    # Map from verifiable index back to original index
    verifiable_to_original = {vi: oi for vi, (oi, _) in enumerate(verifiable_claims)}

    results = [None] * len(claims)  # Parallel to input claims

    # Pre-fill non-verifiable claims as UNSUPPORTED (too short to verify)
    for i in non_verifiable_indices:
        results[i] = {
            'claim_text': claims[i]['text'],
            'claim_type': claims[i].get('type', 'UNKNOWN'),
            'verdict': 'UNSUPPORTED',
            'url': None,
            'tier': None,
            'supporting_sentence': None,
            'score': 0.0,
        }

    queries_issued = 0
    query_log = []
    pages_fetched = {}  # url → text (cache across queries)

    for spec in query_specs:
        if queries_issued >= query_budget:
            break

        query = spec['query']
        claim_indices = spec['claim_indices']  # Indices into verifiable_claim_list
        # Map to original indices
        original_indices = [verifiable_to_original[vi] for vi in claim_indices]

        # Search
        serp_results, _latency = _serp_search(query)
        queries_issued += 1
        query_log.append({
            'query': query,
            'results_count': len(serp_results),
            'claim_indices': original_indices,
        })

        if not serp_results:
            continue

        # Filter by trust tier — only consider tier 1-3
        viable_results = []
        for sr in serp_results[:5]:  # Top 5 results max
            url = sr.get('url', '')
            tier = classify_source_tier(url)
            if tier > 0:
                viable_results.append((url, tier, sr.get('snippet', '')))

        if not viable_results:
            continue

        # For each claim in this batch, try to find evidence
        for vi, oi in zip(claim_indices, original_indices):
            if results[oi] is not None:
                continue  # Already resolved

            claim = verifiable_claim_list[vi]
            claim_text = claim['text']
            # LOCAL-221 fix: carry the source sentence for subject binding
            claim_sentence = claim.get('sentence', '')
            claim_type = claim.get('type', 'UNKNOWN')

            # First: check snippets (free, no fetch needed)
            for url, tier, snippet in viable_results:
                if snippet:
                    snippet_sentences = _split_sentences(snippet)
                    evidence = evaluate_evidence(claim_text, snippet_sentences,
                                                stop_title, claim_sentence)
                    if evidence:
                        results[oi] = {
                            'claim_text': claim_text,
                            'claim_type': claim_type,
                            'verdict': SUPPORTED_EXTERNAL,
                            'url': url,
                            'tier': tier,
                            'supporting_sentence': evidence['sentence'],
                            'score': evidence['score'],
                        }
                        break

            if results[oi] is not None:
                continue

            # Second: fetch top 2 pages for deeper evidence
            for url, tier, snippet in viable_results[:2]:
                if url in pages_fetched:
                    page_text = pages_fetched[url]
                else:
                    page_text, _ = _fetch_page_text(url, max_chars=15000)
                    pages_fetched[url] = page_text

                if not page_text:
                    continue

                # Extract sentences from the page
                page_sentences = _split_sentences(page_text)
                # Limit to relevant sentences (contain at least one claim keyword)
                # LOCAL-221 fix: use sentence tokens for keyword extraction when
                # claim_text is bare (e.g. "320 feet" → use sentence keywords
                # like "depths", "bay", "villefranche" for page filtering)
                keyword_source = claim_sentence if claim_sentence else claim_text
                claim_keywords = [w for w in _tokenize(keyword_source) if len(w) > 3]
                relevant_sentences = []
                for s in page_sentences:
                    s_lower = s.lower()
                    if any(kw in s_lower for kw in claim_keywords[:5]):
                        relevant_sentences.append(s)
                    if len(relevant_sentences) >= 50:
                        break

                evidence = evaluate_evidence(claim_text, relevant_sentences,
                                            stop_title, claim_sentence)
                if evidence:
                    results[oi] = {
                        'claim_text': claim_text,
                        'claim_type': claim_type,
                        'verdict': SUPPORTED_EXTERNAL,
                        'url': url,
                        'tier': tier,
                        'supporting_sentence': evidence['sentence'],
                        'score': evidence['score'],
                    }
                    break

    # Fill in unresolved claims as refused
    for i in range(len(claims)):
        if results[i] is None:
            results[i] = {
                'claim_text': claims[i]['text'],
                'claim_type': claims[i].get('type', 'UNKNOWN'),
                'verdict': 'UNSUPPORTED',  # Stays unsupported
                'url': None,
                'tier': None,
                'supporting_sentence': None,
                'score': 0.0,
            }

    promoted = sum(1 for r in results if r['verdict'] == SUPPORTED_EXTERNAL)
    refused = sum(1 for r in results if r['verdict'] == 'UNSUPPORTED')

    return {
        'results': results,
        'queries_issued': queries_issued,
        'cost': queries_issued * SERPER_COST_PER_QUERY,
        'promoted_count': promoted,
        'refused_count': refused,
        'query_log': query_log,
    }


# ─── Stop corpus writeback ───────────────────────────────────────────────────

def write_external_sources_to_stop_corpus(
    promoted_claims: List[Dict],
    stop_title: str,
    venue_name: str,
    conn,
) -> Dict:
    """Write externally verified sources back into stop_corpus.
    
    Tags them with 'external_verified' so they're distinct from the original
    corpus passages. Does NOT modify existing passages — appends only.
    
    Args:
        promoted_claims: List of results with verdict=SUPPORTED_EXTERNAL
        stop_title: Stop title in stop_corpus
        venue_name: Venue name in stop_corpus
        conn: psycopg2 connection
    
    Returns:
        {passages_added: int, sources_added: int}
    """
    import psycopg2.extras

    if not promoted_claims:
        return {'passages_added': 0, 'sources_added': 0}

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Check if row exists
    cur.execute(
        "SELECT id, passages_json, source_pages FROM stop_corpus WHERE venue_name = %s AND stop_title = %s",
        (venue_name, stop_title)
    )
    row = cur.fetchone()

    new_passages = []
    new_sources = []

    # LOCAL-341: Import relevance gate
    from harvest_relevance_gate import check_passage_relevance

    for claim in promoted_claims:
        if claim.get('verdict') != SUPPORTED_EXTERNAL:
            continue
        sentence = claim.get('supporting_sentence', '')
        url = claim.get('url', '')
        tier = claim.get('tier', 3)

        if sentence:
            # LOCAL-341: Relevance gate — passage must be about the stop
            is_relevant, relevance_reason = check_passage_relevance(sentence, stop_title)
            if not is_relevant:
                logger.warning(
                    f"[LOCAL-341] Relevance gate BLOCKED passage for {stop_title!r}: "
                    f"{relevance_reason} | url={url} | text={sentence[:80]}"
                )
                continue

            new_passages.append({
                'text': sentence,
                'source': 'external_verified',
                'url': url,
                'tier': tier,
                'claim_verified': claim.get('claim_text', ''),
            })

        if url and url not in [s.get('url', '') for s in new_sources]:
            new_sources.append({
                'url': url,
                'tier': tier,
                'type': 'external_verified',
            })

    if not new_passages:
        cur.close()
        return {'passages_added': 0, 'sources_added': 0}

    if row:
        # Append to existing row
        existing_passages = row['passages_json']
        if isinstance(existing_passages, str):
            existing_passages = json.loads(existing_passages)
        existing_passages = existing_passages or []

        existing_sources = row['source_pages']
        if isinstance(existing_sources, str):
            existing_sources = json.loads(existing_sources)
        existing_sources = existing_sources or []

        # Deduplicate: don't add passages we already have
        existing_texts = {_normalize(p.get('text', '') if isinstance(p, dict) else p)
                         for p in existing_passages}
        truly_new_passages = [p for p in new_passages
                             if _normalize(p['text']) not in existing_texts]

        # Handle mixed source_pages formats (some are [int], some are [{url, tier}])
        existing_urls = set()
        for s in existing_sources:
            if isinstance(s, dict):
                existing_urls.add(s.get('url', ''))
            # Skip non-dict entries (legacy format like [4])
        truly_new_sources = [s for s in new_sources if s['url'] not in existing_urls]

        if truly_new_passages or truly_new_sources:
            updated_passages = existing_passages + truly_new_passages
            updated_sources = existing_sources + truly_new_sources
            cur.execute(
                """UPDATE stop_corpus 
                   SET passages_json = %s::jsonb, 
                       source_pages = %s::jsonb,
                       passage_count = %s
                   WHERE id = %s""",
                (json.dumps(updated_passages), json.dumps(updated_sources),
                 len(updated_passages), row['id'])
            )
            conn.commit()
            cur.close()
            return {
                'passages_added': len(truly_new_passages),
                'sources_added': len(truly_new_sources),
            }
        else:
            cur.close()
            return {'passages_added': 0, 'sources_added': 0}
    else:
        # Create new row
        cur.execute(
            """INSERT INTO stop_corpus (venue_name, stop_title, passages_json, source_pages, passage_count)
               VALUES (%s, %s, %s::jsonb, %s::jsonb, %s)""",
            (venue_name, stop_title, json.dumps(new_passages),
             json.dumps(new_sources), len(new_passages))
        )
        conn.commit()
        cur.close()
        return {
            'passages_added': len(new_passages),
            'sources_added': len(new_sources),
        }
