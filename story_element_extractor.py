"""story_element_extractor.py — SQ-S3/S4/S5: fetch, work-anchored extraction, corroboration.

Fetches Tier 1-2 pages, checks work-anchor (canonical title present),
extracts story elements via LLM, and scores corroboration across sources.
Syndication detection is deterministic (character-shingle Jaccard, R3).
"""
import json, os, re, time, urllib.request, urllib.parse, hashlib
from typing import Dict, List, Optional, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from work_story_searcher import normalize_work_key, work_stories_put, synthesize_fact_targeted_queries

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')

# Element types from STORY_QUALITY_DESIGN.md §SQ-S4
ELEMENT_TYPES = [
    'origin', 'intention', 'dedication', 'turning_point', 'technique',
    'reference_work', 'controversy', 'reception', 'provenance',
    'person', 'date', 'quote', 'legend'
]

# --- Character-shingle Jaccard for syndication detection (R3) ---
def _char_shingles(text: str, n: int = 5) -> Set[str]:
    """Generate character n-grams (shingles) from normalized text."""
    text = re.sub(r'\s+', ' ', text.lower().strip())
    if len(text) < n:
        return {text}
    return {text[i:i+n] for i in range(len(text) - n + 1)}


def jaccard_similarity(text_a: str, text_b: str, shingle_size: int = 5) -> float:
    """Compute Jaccard similarity between two texts using character shingles.
    Deterministic, reproducible, no embeddings API needed (R3)."""
    if not text_a or not text_b:
        return 0.0
    shingles_a = _char_shingles(text_a, shingle_size)
    shingles_b = _char_shingles(text_b, shingle_size)
    intersection = shingles_a & shingles_b
    union = shingles_a | shingles_b
    if not union:
        return 0.0
    return len(intersection) / len(union)


# --- Work-anchor check (M3 matcher rules) ---
def check_work_anchor(page_text: str, canonical_title: str, artist: str = '') -> bool:
    """Check if a page references the canonical work title.
    Uses content-word matching — stop words ('the', 'a', 'of', 'in', 'and') are not evidence.
    Artist-generic pages that never mention THIS work are dropped.
    For contained tours, also requires artist mention (W2: prevents Bible article anchoring to Chagall paintings)."""
    if not canonical_title or not page_text:
        return False
    
    # Extract content words from title (skip stop words)
    _stop_words = {'the', 'a', 'an', 'of', 'in', 'and', 'or', 'le', 'la', 'les',
                   'de', 'du', 'des', 'un', 'une', 'et', 'l', 'il', 'lo', 'i', 'di'}
    title_words = [w.lower() for w in re.findall(r'\w+', canonical_title)
                   if w.lower() not in _stop_words and len(w) >= 3]
    
    if not title_words:
        # Title is all stop words — fall back to exact substring
        return canonical_title.lower() in page_text.lower()
    
    page_lower = page_text.lower()
    # Require majority of content words present
    matches = sum(1 for w in title_words if w in page_lower)
    threshold = max(1, len(title_words) * 0.6)  # 60% of content words
    title_matches = matches >= threshold
    
    # W2: For contained tours (artist provided), also require artist token
    if artist and title_matches:
        artist_words = [w.lower() for w in re.findall(r'\w+', artist) if len(w) >= 3]
        if artist_words:
            artist_found = any(w in page_lower for w in artist_words)
            if not artist_found:
                return False
    
    return title_matches


# --- Page fetching ---
def _fetch_wikipedia_api(url: str, max_chars: int = 15000) -> Optional[str]:
    """Fetch Wikipedia article via API plaintext extract (W1: avoids HTML stub problem)."""
    try:
        # Extract article title from URL
        title = url.split('/wiki/')[-1].split('#')[0].split('?')[0]
        title = urllib.parse.unquote(title).replace('_', ' ')
        
        # Determine language from subdomain
        lang = 'en'
        if 'wikipedia.org' in url:
            parts = url.split('//')[-1].split('.wikipedia.org')[0]
            if parts and parts != 'www':
                lang = parts
        
        api_url = f"https://{lang}.wikipedia.org/w/api.php?action=query&titles={urllib.parse.quote(title)}&prop=extracts&explaintext=1&format=json&exlimit=1"
        req = urllib.request.Request(api_url, headers={
            'User-Agent': 'AudiouraBot/1.0 (story-quality-pipeline)'
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            pages = data.get('query', {}).get('pages', {})
            for page_id, page_data in pages.items():
                if page_id == '-1':
                    return None  # Page not found
                extract = page_data.get('extract', '')
                if extract:
                    print(f"  [SQ-S3] Wikipedia API: {len(extract)} chars for '{title}'")
                    return extract[:max_chars]
            return None
    except Exception as e:
        print(f"  [SQ-S3] Wikipedia API failed for {url[:60]}: {e}")
        return None


def fetch_page_text(url: str, max_chars: int = 15000) -> Optional[str]:
    """Fetch a URL and extract text content (HTML stripped). Cap at max_chars.
    On failure → None (logged, never raises)."""
    # W1: Wikipedia API for *.wikipedia.org domains
    if 'wikipedia.org/wiki/' in url:
        return _fetch_wikipedia_api(url, max_chars)
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (AudiouraBot/1.0; story-quality-pipeline)'
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            # Only process text/html
            content_type = resp.headers.get('Content-Type', '')
            if 'text' not in content_type and 'html' not in content_type:
                return None
            raw = resp.read(max_chars * 3).decode('utf-8', errors='replace')
            # Strip HTML tags (basic)
            text = re.sub(r'<script[^>]*>.*?</script>', '', raw, flags=re.DOTALL|re.IGNORECASE)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL|re.IGNORECASE)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:max_chars]
    except Exception as e:
        print(f"  [SQ-S3] Fetch failed for {url[:60]}: {e}")
        return None


# --- LLM Element Extraction ---
def extract_elements_from_text(page_text: str, canonical_title: str,
                                artist: str, source_url: str) -> List[Dict]:
    """Extract story elements from page text using GPT-4o-mini.
    Returns list of element dicts with type, text, source_sentence, etc.
    On LLM failure → empty list (logged, never raises)."""
    if not OPENAI_API_KEY or not page_text:
        return []
    
    prompt = f"""You are extracting factual story elements about the artwork "{canonical_title}" by {artist}.

From the following text, extract ONLY claims that are specifically about this work (not general artist biography unless it directly relates to this work's creation).

For each element, provide:
- type: one of {json.dumps(ELEMENT_TYPES)}
- text: brief factual claim (1-2 sentences)
- source_sentence: the exact sentence from the text that supports this claim
- people: list of named people mentioned
- dates: list of dates/years mentioned
- is_satire: true if the context appears comedic/satirical/jest

Return JSON array. If no relevant elements found, return empty array [].

TEXT:
{page_text[:8000]}"""

    try:
        data = json.dumps({
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }).encode()
        
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
            content = body['choices'][0]['message']['content']
            parsed = json.loads(content)
            elements = parsed.get('elements', parsed) if isinstance(parsed, dict) else parsed
            if not isinstance(elements, list):
                elements = []
            
            # Filter satire, attach source metadata
            result = []
            for elem in elements:
                if elem.get('is_satire', False):
                    continue  # Satire dropped regardless of repetition
                elem['source_url'] = source_url
                elem['source_domain'] = source_url.split('/')[2] if '/' in source_url else ''
                result.append(elem)
            return result
    except Exception as e:
        print(f"  [SQ-S4] LLM extraction failed: {e}")
        return []


# --- Corroboration Scoring (SQ-S5) ---
def _normalize_claim_key(text: str) -> str:
    """Deterministic normalization for claim grouping. Lowercase, strip dates/punctuation."""
    text = text.lower().strip()
    text = re.sub(r'\b\d{4}\b', '', text)  # Strip years
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# --- SQ4 M1: LLM Merge Pass ---

def _find_merge_candidates(scored_elements: List[Dict]) -> List[tuple]:
    """Find pairs of reported elements that are candidates for LLM merge.
    
    Candidate gate (RS3-aware): pairs are candidates if ANY of:
    1. Normalized keys share ≥3 content words
    2. source_sentence Jaccard similarity 0.3–0.84 (below syndication, above noise)
    3. Same element type (date, technique, etc.) about the same work — always candidates
       (RS3: widens the gate for the 1952 cluster where tokens barely overlap)
    
    RS2: legend elements are NEVER candidates for merge with non-legend elements.
    """
    candidates = []
    for i in range(len(scored_elements)):
        for j in range(i + 1, len(scored_elements)):
            a, b = scored_elements[i], scored_elements[j]
            
            # RS2: Never cross a legend boundary
            a_legend = a.get('corroboration_status') == 'legend'
            b_legend = b.get('corroboration_status') == 'legend'
            if a_legend or b_legend:
                continue  # Legend elements never merge with anything
            
            # Only merge reported elements (documented already has ≥2 sources)
            if a.get('corroboration_status') != 'reported' or b.get('corroboration_status') != 'reported':
                continue
            
            # Gate 1: same type — always candidates (RS3 widening for date/technique clusters)
            if a.get('type') == b.get('type') and a.get('type') in ('date', 'technique', 'origin', 'provenance', 'dedication'):
                candidates.append((i, j))
                continue
            
            # Gate 2: ≥3 shared content words in normalized key
            a_key = _normalize_claim_key(a.get('text', ''))
            b_key = _normalize_claim_key(b.get('text', ''))
            a_words = set(a_key.split())
            b_words = set(b_key.split())
            if len(a_words & b_words) >= 3:
                candidates.append((i, j))
                continue
            
            # Gate 3: Jaccard on source_sentence (0.3–0.84 range)
            sim = jaccard_similarity(
                a.get('source_sentence', ''),
                b.get('source_sentence', '')
            )
            if 0.3 <= sim < 0.85:
                candidates.append((i, j))
    
    return candidates


def _llm_merge_decision(pairs: List[Dict]) -> List[Dict]:
    """Call GPT-4o-mini to decide which candidate pairs describe the same fact.
    
    Returns list of {pair_idx, verdict: bool, reason: str} decisions.
    The LLM only answers yes/no — it never sees, names, or adds sources (RS4).
    """
    if not pairs:
        return []
    
    # Build prompt with all candidate pairs
    prompt_pairs = []
    for idx, pair in enumerate(pairs):
        prompt_pairs.append(
            f"Pair {idx+1}:\n"
            f"  A: \"{pair['a_text']}\"\n"
            f"  B: \"{pair['b_text']}\"\n"
        )
    
    prompt = (
        "You are a fact-checking assistant. For each pair of claims below about an artwork, "
        "answer YES if they describe the SAME factual claim (even if worded differently), "
        "or NO if they are about different facts.\n\n"
        "Rules:\n"
        "- 'Created in 1952' and 'completed in 1952' and 'created in Spring 1952' are the SAME fact.\n"
        "- 'Gouache cut-outs' and 'gouache on paper, cut and pasted' are the SAME technique.\n"
        "- Different dates, different people, or different events are DIFFERENT facts.\n\n"
        + "\n".join(prompt_pairs) +
        "\n\nRespond with ONLY a JSON array of objects: [{\"pair\": 1, \"same\": true/false},...]\n"
    )
    
    try:
        import openai
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=500,
        )
        import json as _json
        content = response.choices[0].message.content.strip()
        # Parse JSON from response (handle markdown code blocks)
        if content.startswith('```'):
            content = content.split('\n', 1)[1].rsplit('```', 1)[0]
        decisions = _json.loads(content)
        return decisions
    except Exception as e:
        # LLM failure → no merges (fail-closed)
        print(f"  [SQ4-M1] LLM merge call failed: {e}")
        return []


def _llm_merge_pass(scored_elements: List[Dict], syndication_threshold: float = 0.85) -> List[Dict]:
    """SQ4 M1: LLM merge-only pass on scored elements.
    
    After deterministic grouping, finds candidate pairs of 'reported' elements
    and asks GPT-4o-mini if they describe the same fact. If yes, merges their
    source sets and recomputes status (RS4: count distinct domains post-merge).
    
    RS2: legend elements are NEVER merged into non-legend groups.
    RS4: independence recomputed deterministically post-merge.
    """
    candidates = _find_merge_candidates(scored_elements)
    
    if not candidates:
        return scored_elements
    
    # Build pairs for LLM
    llm_pairs = []
    for i, j in candidates:
        llm_pairs.append({
            'a_text': scored_elements[i].get('text', ''),
            'b_text': scored_elements[j].get('text', ''),
            'a_idx': i,
            'b_idx': j,
        })
    
    # Call LLM for merge decisions
    decisions = _llm_merge_decision(llm_pairs)
    
    # Build merge_log
    merge_log = []
    merge_targets = {}  # j → i (element j merges INTO element i)
    
    for decision in decisions:
        pair_num = decision.get('pair', 0) - 1  # 0-indexed
        same = decision.get('same', False)
        
        if pair_num < 0 or pair_num >= len(llm_pairs):
            continue
        
        pair = llm_pairs[pair_num]
        i, j = pair['a_idx'], pair['b_idx']
        
        log_entry = {
            'pair': [i, j],
            'a_text': pair['a_text'][:80],
            'b_text': pair['b_text'][:80],
            'verdict': same,
            'a_domain': scored_elements[i].get('source_domain', ''),
            'b_domain': scored_elements[j].get('source_domain', ''),
        }
        
        if same:
            # Check transitive merges: if j already merges somewhere, follow the chain
            target = i
            while target in merge_targets:
                target = merge_targets[target]
            merge_targets[j] = target
            log_entry['merged_into'] = target
        
        merge_log.append(log_entry)
    
    # Apply merges: union source sets, recompute status (RS4)
    elements_to_remove = set()
    for j, target_i in merge_targets.items():
        # Union the source sets
        target_sources = scored_elements[target_i].get('_all_sources', [])
        merge_sources = scored_elements[j].get('_all_sources', [])
        all_sources = target_sources + merge_sources
        
        # RS4: Count distinct domains after syndication dedup
        unique_domains = set()
        for src in all_sources:
            domain = src.get('source_domain', '')
            if domain:
                unique_domains.add(domain)
        
        n_independent = len(unique_domains)
        scored_elements[target_i]['_all_sources'] = all_sources
        scored_elements[target_i]['independent_source_count'] = n_independent
        
        # Recompute status
        if n_independent >= 2:
            scored_elements[target_i]['corroboration_status'] = 'documented'
        
        # Update syndication_log
        scored_elements[target_i]['syndication_log'] = {
            'total_in_group': len(all_sources),
            'independent_after_dedup': n_independent,
            'sources': [{'domain': s.get('source_domain', ''), 'url': s.get('source_url', '')}
                       for s in all_sources],
            'merged_from': [j],
        }
        
        elements_to_remove.add(j)
    
    # Attach merge_log to first element for evidence
    if merge_log and scored_elements:
        scored_elements[0]['_merge_log'] = merge_log
    
    # Remove merged elements
    result = [e for idx, e in enumerate(scored_elements) if idx not in elements_to_remove]
    
    return result


def score_corroboration(elements: List[Dict], syndication_threshold: float = 0.85) -> List[Dict]:
    """Score corroboration across extracted elements.
    
    Groups by normalized claim key, detects syndication via character-shingle Jaccard (R3),
    then runs an LLM merge-only pass (SQ4 M1) on candidate pairs,
    assigns statuses: documented (≥2 independent T1/T2), reported (1 T1/T2),
    legend (folklore-typed), disputed (conflicting claims from independent sources).
    
    R4: deterministic normalization is PRIMARY grouping. LLM merge pass is SECOND layer —
    may only MERGE near-duplicate groups, never split or create corroboration.
    Legend elements are NEVER merged into non-legend groups (RS2).
    """
    if not elements:
        return []
    
    # Step 1: Group by normalized claim key (deterministic)
    groups = {}
    for elem in elements:
        key = _normalize_claim_key(elem.get('text', ''))
        if not key:
            continue
        if key not in groups:
            groups[key] = []
        groups[key].append(elem)
    
    # Step 2: For each group, check syndication and count independent sources
    scored_elements = []
    for key, group in groups.items():
        # Deduplicate by source domain
        domains_seen = {}
        independent_sources = []
        
        for elem in group:
            domain = elem.get('source_domain', '')
            source_sent = elem.get('source_sentence', '')
            
            # Check syndication against existing sources in this group (R3)
            is_syndicated = False
            for prev_sent, prev_domain in domains_seen.values():
                if domain == prev_domain:
                    is_syndicated = True
                    break
                # Character-shingle Jaccard for cross-domain syndication
                sim = jaccard_similarity(source_sent, prev_sent)
                if sim >= syndication_threshold:
                    is_syndicated = True
                    break
            
            if not is_syndicated:
                source_id = f"{domain}:{hashlib.md5(source_sent.encode()).hexdigest()[:8]}"
                domains_seen[source_id] = (source_sent, domain)
                independent_sources.append(elem)
        
        # Step 3: Assign corroboration status (pre-merge)
        n_independent = len(independent_sources)
        
        # Check for legend/folklore typing
        representative = group[0]
        elem_type = representative.get('type', '')
        
        # W3: Deterministic legend-phrase override (regardless of LLM typing)
        _LEGEND_PHRASES = ['legend has it', 'the story goes', 'according to legend',
                           'allegedly', 'legend says', 'it is said that', 'rumor has it']
        _source_sent_lower = representative.get('source_sentence', '').lower()
        is_legend = (elem_type == 'legend' or
                     any(phrase in _source_sent_lower for phrase in _LEGEND_PHRASES))
        
        if is_legend:
            status = 'legend'
        elif n_independent >= 2:
            status = 'documented'
        elif n_independent == 1:
            status = 'reported'
        else:
            status = 'reported'
        
        # Attach status to representative element
        representative['corroboration_status'] = status
        representative['independent_source_count'] = n_independent
        representative['syndication_log'] = {
            'total_in_group': len(group),
            'independent_after_dedup': n_independent,
            'sources': [{'domain': e.get('source_domain', ''), 'url': e.get('source_url', '')}
                       for e in independent_sources]
        }
        representative['_all_sources'] = independent_sources  # Keep for merge pass
        scored_elements.append(representative)
    
    # Step 4: LLM merge pass (SQ4 M1) — merge semantically-equivalent reported elements
    scored_elements = _llm_merge_pass(scored_elements, syndication_threshold)
    
    # Clean up internal fields
    for elem in scored_elements:
        elem.pop('_all_sources', None)
    
    return scored_elements


# --- Full extraction pipeline for one stop ---
def extract_and_score_stop(search_results: List[Dict], canonical_title: str,
                           artist: str, max_pages: int = 6) -> Dict:
    """Full SQ-S3/S4/S5 pipeline for one stop.
    
    1. Filter to T1/T2 results only
    2. Fetch pages (parallel, capped)
    3. Check work-anchor
    4. Extract elements via LLM
    5. Score corroboration
    
    Returns:
      - elements: scored elements with corroboration statuses
      - fetch_log: per-URL fetch status
      - pages_fetched: int
      - pages_anchored: int  
      - extraction_status: 'ok' | 'no_pages' | 'no_elements'
    """
    # Step 1: Filter to T1/T2 only
    eligible = [r for r in search_results if r.get('tier') in ('tier1', 'tier2')]

    # URL dedup: same URL surfaced by multiple queries → fetch once
    seen_urls = set()
    deduped = []
    for r in eligible:
        url = r.get('url', '')
        if url not in seen_urls:
            seen_urls.add(url)
            deduped.append(r)

    # D1: Domain-diversity cap — max 2 pages per domain, then fill from other domains
    domain_counts = {}
    diverse = []
    overflow = []
    for r in deduped:
        domain = r.get('domain', '')
        count = domain_counts.get(domain, 0)
        if count < 2:
            diverse.append(r)
            domain_counts[domain] = count + 1
        else:
            overflow.append(r)
    # Fill remaining slots with overflow (capped domains) if diversity still has room
    eligible = (diverse + overflow)[:max_pages]
    
    if not eligible:
        return {
            'elements': [],
            'fetch_log': [],
            'pages_fetched': 0,
            'pages_anchored': 0,
            'extraction_status': 'no_pages',
        }
    
    # Step 2: Fetch pages in parallel
    fetch_log = []
    fetched_pages = []
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(fetch_page_text, r['url']): r for r in eligible}
        for future in as_completed(futures):
            result_meta = futures[future]
            try:
                page_text = future.result()
                fetch_log.append({
                    'url': result_meta['url'],
                    'domain': result_meta.get('domain', ''),
                    'tier': result_meta.get('tier', ''),
                    'fetched': page_text is not None,
                    'chars': len(page_text) if page_text else 0,
                })
                if page_text:
                    fetched_pages.append((result_meta, page_text))
            except Exception as e:
                fetch_log.append({
                    'url': result_meta['url'],
                    'domain': result_meta.get('domain', ''),
                    'fetched': False,
                    'error': str(e),
                })
    
    # Step 3: Work-anchor check
    anchored_pages = [(meta, text) for meta, text in fetched_pages
                      if check_work_anchor(text, canonical_title, artist)]
    
    if not anchored_pages:
        return {
            'elements': [],
            'fetch_log': fetch_log,
            'pages_fetched': len(fetched_pages),
            'pages_anchored': 0,
            'extraction_status': 'no_elements',
        }
    
    # Step 4: Extract elements from each anchored page
    all_elements = []
    for meta, text in anchored_pages:
        elements = extract_elements_from_text(text, canonical_title, artist, meta['url'])
        all_elements.extend(elements)
    
    if not all_elements:
        return {
            'elements': [],
            'fetch_log': fetch_log,
            'pages_fetched': len(fetched_pages),
            'pages_anchored': len(anchored_pages),
            'extraction_status': 'no_elements',
        }
    
    # Step 5: Corroboration scoring
    scored = score_corroboration(all_elements)
    
    # W7: Identify high-value reported elements that warrant fact-targeted refinement
    _HIGH_VALUE_TYPES = {'dedication', 'origin', 'turning_point', 'provenance'}
    fact_refinement_queries = []
    reported_hv = [e for e in scored
                   if e.get('corroboration_status') == 'reported'
                   and e.get('type') in _HIGH_VALUE_TYPES]
    if reported_hv:
        _stop_for_queries = {'canonical_title': canonical_title, 'artist': artist}
        fact_refinement_queries = synthesize_fact_targeted_queries(_stop_for_queries, reported_hv)
    
    # F4: Cache write — persist scored elements for future cache hits
    _work_key = normalize_work_key(canonical_title, artist)
    _sources = [{'url': e.get('source_url', ''), 'domain': e.get('source_domain', '')} for e in scored]
    work_stories_put(
        work_key=_work_key,
        title=canonical_title,
        artist=artist,
        work_qid='',  # QID populated when available from GG pipeline
        elements=scored,
        sources=_sources,
        query_log=[],  # Query log stored by search_stories_for_stop
    )
    
    return {
        'elements': scored,
        'fetch_log': fetch_log,
        'pages_fetched': len(fetched_pages),
        'pages_anchored': len(anchored_pages),
        'extraction_status': 'ok',
        'fact_refinement_queries': fact_refinement_queries,
    }
