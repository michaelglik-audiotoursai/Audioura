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
        
        # Identify subject: look for proper nouns or key entities
        subject = _extract_subject(core_text, stop_title)
        if subject not in subject_groups:
            subject_groups[subject] = []
        subject_groups[subject].append(i)

    # Build one query per subject group
    for subject, indices in subject_groups.items():
        # Collect key facts from all claims in this group
        facts = []
        for idx in indices:
            core = claims[idx]['text'].split(' (')[0].strip() if ' (' in claims[idx]['text'] else claims[idx]['text']
            # Extract the predicate/fact part
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
        query_text = f'{core} {stop_title} {city}'.strip()
        if len(query_text) > 200:
            query_text = query_text[:200]
        queries.append({
            'query': query_text,
            'claim_indices': [i],
            'context': f'{stop_title}',
        })

    return queries


def _extract_subject(claim_text: str, stop_title: str) -> str:
    """Extract the primary subject from a claim for query grouping."""
    # If the claim mentions the stop title, that's the subject
    if _normalize(stop_title) in _normalize(claim_text):
        return stop_title

    # Look for proper noun phrases (capitalized words)
    # Simple heuristic: first sequence of capitalized words
    words = claim_text.split()
    proper_nouns = []
    for w in words:
        # Skip common sentence starters and articles
        if w in ('The', 'A', 'An', 'In', 'At', 'On', 'By', 'It', 'Its', 'This', 'That'):
            if proper_nouns:
                break
            continue
        if w and w[0].isupper() and not w.isupper():
            proper_nouns.append(w)
        elif proper_nouns:
            break

    if proper_nouns:
        return ' '.join(proper_nouns)

    # Fallback: use the stop title as subject
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
    """
    if not claim_nums or not source_nums:
        return True  # No numbers to compare = not a numeric mismatch

    for c_val, c_unit in claim_nums:
        # Convert claim value to meters (if spatial unit)
        c_meters = None
        if c_unit in _TO_METERS:
            c_meters = c_val * _TO_METERS[c_unit]

        matched = False
        for s_val, s_unit in source_nums:
            # Direct comparison (same unit or both unitless)
            if c_unit == s_unit or (not c_unit and not s_unit):
                if abs(c_val - s_val) / max(c_val, 1) <= tolerance:
                    matched = True
                    break

            # Cross-unit comparison via meters
            if c_meters is not None and s_unit in _TO_METERS:
                s_meters = s_val * _TO_METERS[s_unit]
                if abs(c_meters - s_meters) / max(c_meters, 1) <= tolerance:
                    matched = True
                    break

            # Year comparison (exact match only)
            if not c_unit and not s_unit and c_val > 1000 and s_val > 1000:
                if c_val == s_val:
                    matched = True
                    break

        if not matched and c_val > 0:
            # This claim number has no match in the source
            return False

    return True


def evaluate_evidence(claim_text: str, source_sentences: List[str],
                      stop_title: str) -> Optional[Dict]:
    """Evaluate whether any source sentence actually supports the claim.
    
    Rules (D62, D100):
    - The sentence must assert the same fact about the SAME subject.
    - Unit conversions must be verified, not assumed.
    - Mere word overlap is not support.
    
    Returns: {sentence, score, reason} or None if no support found.
    """
    claim_core = claim_text.split(' (')[0].strip() if ' (' in claim_text else claim_text
    claim_norm = _normalize(claim_core)
    claim_tokens = set(_tokenize(claim_core))
    claim_numbers = _extract_numbers(claim_core)

    # What subject is the claim about?
    claim_subject = _extract_subject(claim_core, stop_title)
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
        non_subject_claim_tokens = claim_tokens - set(_tokenize(claim_subject))
        if non_subject_claim_tokens:
            overlap = non_subject_claim_tokens & sent_tokens
            overlap_ratio = len(overlap) / len(non_subject_claim_tokens)
        else:
            overlap = claim_tokens & sent_tokens
            overlap_ratio = len(overlap) / max(len(claim_tokens), 1)

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
    # Claims must contain at least 4 meaningful tokens AND either:
    # - A number/date (verifiable by comparison), or
    # - A proper noun + predicate (a falsifiable assertion)
    MIN_CLAIM_TOKENS = 4
    verifiable_claims = []
    non_verifiable_indices = []
    for i, claim in enumerate(claims):
        core_text = claim['text'].split(' (')[0].strip() if ' (' in claim['text'] else claim['text']
        tokens = _tokenize(core_text)
        # Must have at least MIN_CLAIM_TOKENS meaningful words
        if len(tokens) < MIN_CLAIM_TOKENS:
            non_verifiable_indices.append(i)
            continue
        # Must contain either a number/date or be a genuine predicate
        has_number = any(c.isdigit() for c in core_text)
        has_predicate_signal = any(w in core_text.lower() for w in
                                    ('built', 'designed', 'founded', 'established',
                                     'created', 'opened', 'named', 'known as',
                                     'located', 'constructed', 'completed'))
        # At least 5 tokens if no number/predicate (needs more context)
        if not has_number and not has_predicate_signal and len(tokens) < 5:
            non_verifiable_indices.append(i)
            continue
        verifiable_claims.append((i, claim))

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

            # First: check snippets (free, no fetch needed)
            for url, tier, snippet in viable_results:
                if snippet:
                    snippet_sentences = _split_sentences(snippet)
                    evidence = evaluate_evidence(claim_text, snippet_sentences, stop_title)
                    if evidence:
                        results[oi] = {
                            'claim_text': claim_text,
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
                claim_keywords = [w for w in _tokenize(claim_text) if len(w) > 3]
                relevant_sentences = []
                for s in page_sentences:
                    s_lower = s.lower()
                    if any(kw in s_lower for kw in claim_keywords[:3]):
                        relevant_sentences.append(s)
                    if len(relevant_sentences) >= 50:
                        break

                evidence = evaluate_evidence(claim_text, relevant_sentences, stop_title)
                if evidence:
                    results[oi] = {
                        'claim_text': claim_text,
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

    for claim in promoted_claims:
        if claim.get('verdict') != SUPPORTED_EXTERNAL:
            continue
        sentence = claim.get('supporting_sentence', '')
        url = claim.get('url', '')
        tier = claim.get('tier', 3)

        if sentence:
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
