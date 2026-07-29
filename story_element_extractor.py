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


def check_collection_anchor(page_text: str, artist: str, venue_name: str,
                            venue_city: str = '') -> bool:
    """W9: Collection-level anchor for provenance/dedication elements.
    
    Returns True if the page mentions BOTH the artist AND venue-specific tokens
    that are NOT part of the artist name, with tightened precision rules:
    
    Requires non-artist venue token match AND EITHER:
      - venue_city present in page, OR
      - ≥2 non-artist venue tokens present in the page
    
    This prevents generic tokens like "national" alone from matching unrelated articles
    (e.g. "National Gallery of Canada" when the venue is "Musée national Marc Chagall" in Nice).
    """
    if not page_text or not artist or not venue_name:
        return False
    
    page_lower = page_text.lower()
    
    # Check artist present
    artist_words = set(w.lower() for w in re.findall(r'\w+', artist) if len(w) >= 3)
    if not artist_words or not any(w in page_lower for w in artist_words):
        return False
    
    # Extract ALL venue words (do NOT strip institution words — they're the distinguishing tokens)
    _minimal_stop = {'the', 'a', 'an', 'of', 'in', 'and', 'or', 'le', 'la', 'les',
                     'de', 'du', 'des', 'un', 'une', 'et', 'l'}
    venue_words = set(w.lower() for w in re.findall(r'\w+', venue_name)
                      if w.lower() not in _minimal_stop and len(w) >= 3)
    
    # Identify non-artist venue tokens (the ones that provide collection specificity)
    non_artist_venue = venue_words - artist_words
    
    if not non_artist_venue:
        # Degenerate case: venue name is entirely artist tokens (shouldn't happen in practice)
        # Fall back to requiring ≥2 venue words total present
        venue_matches = sum(1 for w in venue_words if w in page_lower)
        return venue_matches >= 2
    
    # Require ≥1 non-artist venue token present in the page (baseline)
    non_artist_found = [w for w in non_artist_venue if w in page_lower]
    if not non_artist_found:
        return False
    
    # Tightened precision: require venue_city OR ≥2 non-artist venue tokens
    # This prevents "national" alone matching "National Gallery of Canada"
    if venue_city and venue_city.lower() in page_lower:
        return True  # City match is strong evidence
    
    # Otherwise require ≥2 non-artist venue tokens present
    return len(non_artist_found) >= 2


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


def extract_collection_provenance(page_text: str, artist: str, venue_name: str,
                                  source_url: str) -> List[Dict]:
    """W9: Collection-scoped extraction for provenance/dedication facts.
    
    Uses a prompt focused on collection-level donations/bequests/gifts rather than
    a work-specific prompt. This yields elements from museum-about pages that discuss
    donations at the collection level (e.g. "seventeen paintings offered to the French State").
    
    Returns elements typed as 'provenance' or 'dedication'.
    On LLM failure → empty list (logged, never raises).
    """
    if not OPENAI_API_KEY or not page_text:
        return []
    
    prompt = f"""From this text about {venue_name}, extract any facts about donations, bequests, or gifts of artwork by {artist} to this institution. Include: who donated, when, what was donated.

For each fact, provide:
- type: one of ["provenance", "dedication"]
- text: brief factual claim (1-2 sentences)
- source_sentence: the exact sentence from the text that supports this claim
- people: list of named people mentioned
- dates: list of dates/years mentioned

Return a JSON object with key "elements" containing an array. If no relevant facts found, return {{"elements": []}}.

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
            
            # Only keep provenance/dedication types, attach source metadata
            result = []
            for elem in elements:
                elem_type = elem.get('type', '')
                if elem_type not in ('provenance', 'dedication'):
                    elem['type'] = 'provenance'  # Force to provenance if LLM returns other type
                elem['source_url'] = source_url
                elem['source_domain'] = source_url.split('/')[2] if '/' in source_url else ''
                result.append(elem)
            return result
    except Exception as e:
        print(f"  [W9] Collection provenance extraction failed: {e}")
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
    
    Candidate gate (B1 fix — same-type ONLY):
    - Pairs must share the same element `type` (date↔date, technique↔technique)
    - Cross-type pairs are NEVER candidates (a date and a technique are different claims)
    - RS2: legend elements are NEVER candidates for merge with anything
    
    This prevents the over-collapse where all elements about the same artwork
    get merged into a single blob.
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
            
            # B1 FIX: SAME TYPE ONLY — a date and a technique are NEVER the same claim
            if a.get('type') != b.get('type'):
                continue
            
            candidates.append((i, j))
    
    return candidates


def _llm_merge_decision(pairs: List[Dict]) -> List[Dict]:
    """Call GPT-4o-mini to decide which candidate pairs describe the same fact.
    
    Returns list of {pair_idx, verdict: bool, conflicting: bool, reason: str} decisions.
    The LLM only answers yes/no — it never sees, names, or adds sources (RS4).
    RS8: Also detects conflicts (same subject, contradictory values → disputed).
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
        "determine:\n"
        "1. Do they describe the SAME SPECIFIC FACTUAL CLAIM? (same_subject: true/false)\n"
        "2. If same subject, do they give INCOMPATIBLE values? (conflicting: true/false)\n\n"
        "IMPORTANT — 'same factual claim' means the SAME predicate about the SAME subject:\n"
        "- SAME: 'Created in 1952' vs 'completed in 1952' vs 'created in Spring 1952' (all = creation date)\n"
        "- SAME: 'Gouache cut-outs' vs 'gouache on paper, cut and pasted' (both = medium/technique)\n"
        "- DIFFERENT: 'Created in 1952' vs 'gouache on paper' (date ≠ medium)\n"
        "- DIFFERENT: 'Shown at MoMA 2014' vs 'created in 1952' (exhibition ≠ creation date)\n"
        "- DIFFERENT: 'Part of Musée national collection' vs 'created in 1952' (provenance ≠ date)\n"
        "- DIFFERENT: 'Inspired by African sculpture' vs 'shown at MoMA' (inspiration ≠ exhibition)\n"
        "- CONFLICTING: 'Created in 1952' vs 'created in 1958' (same predicate, incompatible values)\n\n"
        "Only answer same_subject:true when BOTH the subject AND the predicate match.\n\n"
        + "\n".join(prompt_pairs) +
        "\n\nRespond with ONLY a JSON array: [{\"pair\": 1, \"same_subject\": true/false, \"conflicting\": true/false},...]\n"
    )
    
    try:
        import openai
        # Support both openai v0.x and v1.x+
        if hasattr(openai, 'OpenAI'):
            # v1.x+ (new client-based API)
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=500,
            )
            content = response.choices[0].message.content.strip()
        else:
            # v0.x (legacy API)
            openai.api_key = OPENAI_API_KEY
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=1000,
            )
            content = response['choices'][0]['message']['content'].strip()
        
        import json as _json
        # Parse JSON from response (handle markdown code blocks)
        if content.startswith('```'):
            content = content.split('\n', 1)[1].rsplit('```', 1)[0]
        decisions = _json.loads(content)
        # Normalize field names for backward compat
        for d in decisions:
            if 'same' in d and 'same_subject' not in d:
                d['same_subject'] = d['same']
            if 'same_subject' not in d:
                d['same_subject'] = d.get('same', False)
            if 'conflicting' not in d:
                d['conflicting'] = False
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
    
    # Call LLM for merge decisions (batch max 5 pairs to avoid response truncation)
    all_decisions = []
    BATCH_SIZE = 5
    for batch_start in range(0, len(llm_pairs), BATCH_SIZE):
        batch = llm_pairs[batch_start:batch_start + BATCH_SIZE]
        batch_for_llm = [{'a_text': p['a_text'], 'b_text': p['b_text']} for p in batch]
        batch_decisions = _llm_merge_decision(batch_for_llm)
        # Remap pair numbers: LLM returns 1-indexed within batch → adjust to global 1-indexed
        for d in batch_decisions:
            local_pair = d.get('pair', 1)  # 1-indexed within batch
            d['pair'] = local_pair + batch_start  # Global 1-indexed
        all_decisions.extend(batch_decisions)
    decisions = all_decisions
    
    # B3 FIX: Use connected-components instead of broken union-find
    # Each element lands in exactly ONE group; recompute independence once per final group
    
    # Build adjacency from merge decisions
    merge_edges = []  # (i, j) pairs that should be in the same group
    disputed_pairs = []  # RS8: conflicting pairs → disputed
    merge_log = []
    
    for decision in decisions:
        pair_num = decision.get('pair', 0) - 1  # 0-indexed
        same_subject = decision.get('same_subject', False)
        conflicting = decision.get('conflicting', False)
        
        if pair_num < 0 or pair_num >= len(llm_pairs):
            continue
        
        pair = llm_pairs[pair_num]
        i, j = pair['a_idx'], pair['b_idx']
        
        log_entry = {
            'pair': [i, j],
            'a_text': pair['a_text'][:80],
            'b_text': pair['b_text'][:80],
            'same_subject': same_subject,
            'conflicting': conflicting,
            'a_domain': scored_elements[i].get('source_domain', ''),
            'b_domain': scored_elements[j].get('source_domain', ''),
        }
        
        if same_subject and not conflicting:
            merge_edges.append((i, j))
            log_entry['action'] = 'merged'
        elif same_subject and conflicting:
            disputed_pairs.append((i, j))
            log_entry['action'] = 'disputed'
        else:
            log_entry['action'] = 'no_merge'
        
        merge_log.append(log_entry)
    
    # Build connected components from merge edges
    # Each element appears in exactly one component
    parent = list(range(len(scored_elements)))
    
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # Path compression
            x = parent[x]
        return x
    
    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[py] = px
    
    for i, j in merge_edges:
        union(i, j)
    
    # Group elements by their component root
    components = {}
    for idx in range(len(scored_elements)):
        root = find(idx)
        if root not in components:
            components[root] = []
        components[root].append(idx)
    
    # For each component with >1 element, merge source sets and recompute status (RS4)
    elements_to_remove = set()
    for root, members in components.items():
        if len(members) <= 1:
            continue
        
        # Representative = first element in the component
        representative_idx = members[0]
        
        # Union all sources from the component
        all_sources = []
        for idx in members:
            all_sources.extend(scored_elements[idx].get('_all_sources', []))
        
        # RS4: Count distinct domains after syndication dedup
        unique_domains = set()
        for src in all_sources:
            domain = src.get('source_domain', '')
            if domain:
                unique_domains.add(domain)
        
        n_independent = len(unique_domains)
        scored_elements[representative_idx]['_all_sources'] = all_sources
        scored_elements[representative_idx]['independent_source_count'] = n_independent
        
        # Recompute status
        if n_independent >= 2:
            scored_elements[representative_idx]['corroboration_status'] = 'documented'
        
        # Update syndication_log
        scored_elements[representative_idx]['syndication_log'] = {
            'total_in_group': len(all_sources),
            'independent_after_dedup': n_independent,
            'sources': [{'domain': s.get('source_domain', ''), 'url': s.get('source_url', '')}
                       for s in all_sources],
            'merged_from': [idx for idx in members[1:]],
        }
        
        # Mark non-representative members for removal
        for idx in members[1:]:
            elements_to_remove.add(idx)
    
    # RS8: Mark disputed pairs (only if both elements still exist after merge)
    for i, j in disputed_pairs:
        if i not in elements_to_remove and j not in elements_to_remove:
            scored_elements[i]['corroboration_status'] = 'disputed'
            scored_elements[j]['corroboration_status'] = 'disputed'
            scored_elements[i]['dispute_pair'] = j
            scored_elements[j]['dispute_pair'] = i
    
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
                           artist: str, max_pages: int = 6, venue_name: str = '',
                           venue_city: str = '') -> Dict:
    """Full SQ-S3/S4/S5 pipeline for one stop.
    
    1. Filter to T1/T2 results only
    2. Fetch pages (parallel, capped)
    3. Check work-anchor (+ W9 collection-anchor for provenance/dedication)
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
    
    # Step 3: Work-anchor check + W9 collection-anchor for provenance/dedication
    anchored_pages = []
    collection_anchored_pages = []
    
    for meta, text in fetched_pages:
        url = meta.get('url', '')
        work_anch = check_work_anchor(text, canonical_title, artist)
        coll_anch = False
        if work_anch:
            anchored_pages.append((meta, text))
        elif venue_name:
            coll_anch = check_collection_anchor(text, artist, venue_name, venue_city)
            if coll_anch:
                collection_anchored_pages.append((meta, text))
        # Update fetch_log with anchor decisions (Fault B fix from 6831)
        for entry in fetch_log:
            if entry.get('url') == url:
                entry['work_anchored'] = work_anch
                entry['collection_anchored'] = coll_anch
                break
    
    if not anchored_pages and not collection_anchored_pages:
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
        # Per-page extraction logging (Fault B fix)
        for entry in fetch_log:
            if entry.get('url') == meta.get('url', ''):
                entry['elements_extracted'] = len(elements)
                entry['types'] = list(set(e.get('type', '') for e in elements))
                break
    
    # W9: Extract from collection-anchored pages using collection-scoped prompt
    for meta, text in collection_anchored_pages:
        coll_elements = extract_collection_provenance(text, artist, venue_name, meta['url'])
        # All elements from collection-scoped extraction are provenance/dedication
        kept = []
        for elem in coll_elements:
            elem['_collection_anchored'] = True  # Mark for audit
            all_elements.append(elem)
            kept.append(elem)
        # Per-page extraction logging
        for entry in fetch_log:
            if entry.get('url') == meta.get('url', ''):
                entry['elements_extracted'] = len(kept)
                entry['types'] = list(set(e.get('type', '') for e in kept))
                break
    
    if not all_elements:
        return {
            'elements': [],
            'fetch_log': fetch_log,
            'pages_fetched': len(fetched_pages),
            'pages_anchored': len(anchored_pages) + len(collection_anchored_pages),
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


# --- SQ4: Story Ranking (SQ-S6) ---

# Type value weights for ranking
_TYPE_VALUES = {
    'origin': 3.0, 'dedication': 3.0, 'turning_point': 3.0,
    'controversy': 2.5,
    'technique': 2.0, 'reference_work': 2.0,
    'reception': 1.5, 'provenance': 1.5,
    'date': 1.0, 'person': 1.0, 'quote': 1.0,
    'legend': 2.0,  # Legends are narratively valuable
    'intention': 2.5,
}

# Corroboration bonus
_CORROBORATION_BONUS = {
    'documented': 2.0,
    'reported': 1.0,
    'legend': 0.5,
    'disputed': 1.5,  # Disputes are engaging (per design §SQ-S6)
}


def rank_stop_elements(elements: List[Dict]) -> List[Dict]:
    """Rank extracted elements by story value for a single stop.
    
    Score = type_value + corroboration_bonus + specificity_bonus.
    Returns elements sorted by score descending, with 'rank_score' attached.
    """
    for elem in elements:
        score = 0.0
        
        # Type value
        elem_type = elem.get('type', '')
        score += _TYPE_VALUES.get(elem_type, 1.0)
        
        # Corroboration bonus
        status = elem.get('corroboration_status', 'reported')
        score += _CORROBORATION_BONUS.get(status, 0.5)
        
        # Specificity bonus
        if elem.get('people'):
            score += 0.5
        if elem.get('dates'):
            score += 0.5
        if elem.get('type') == 'quote':
            score += 0.5
        
        elem['rank_score'] = round(score, 2)
    
    # Sort by score descending
    elements.sort(key=lambda e: e.get('rank_score', 0), reverse=True)
    return elements


def select_stop_elements(elements: List[Dict], max_selected: int = 3) -> Dict:
    """Select top elements for a stop and designate runner-ups.
    
    Returns: {'selected_elements': [...], 'runner_up_elements': [...]}
    """
    ranked = rank_stop_elements(elements)
    return {
        'selected_elements': ranked[:max_selected],
        'runner_up_elements': ranked[max_selected:],
    }


def apply_tour_diversity(stops_selections: List[Dict], max_same_type: int = 2) -> List[Dict]:
    """Apply B5 tour-level diversity: no story type dominates.
    
    Max `max_same_type` stops may share the same top-ranked element type.
    If violated, demote the 3rd+ stop's top pick to runner-up, promote next.
    
    Input: list of {'selected_elements': [...], 'runner_up_elements': [...]} per stop
    Returns: adjusted list with diversity enforced.
    """
    type_counts = {}
    
    for stop_sel in stops_selections:
        selected = stop_sel.get('selected_elements', [])
        if not selected:
            continue
        
        top_type = selected[0].get('type', '')
        count = type_counts.get(top_type, 0)
        
        if count >= max_same_type:
            # Demote top pick, promote from runner-ups
            runners = stop_sel.get('runner_up_elements', [])
            if runners:
                demoted = selected[0]
                promoted = runners[0]
                stop_sel['selected_elements'] = [promoted] + selected[1:]
                stop_sel['runner_up_elements'] = [demoted] + runners[1:]
        else:
            type_counts[top_type] = count + 1
    
    return stops_selections


# --- Wrappers expected by generate_tour_text.py §3 ---

def extract_story_elements_from_pages(pages: List[Dict], venue_name: str,
                                       api_key: str = '', max_pages: int = 5) -> List[Dict]:
    """Extract story elements from corpus pages (wrapper for §3 integration).

    Args:
        pages: List of page dicts from _story_corpus_result['pages'].
               Each page has 'url', 'text', and optionally 'canonical_title', 'artist'.
        venue_name: The museum/venue name (used as fallback canonical_title).
        api_key: OpenAI API key (uses env var if empty).
        max_pages: Maximum pages to process.

    Returns:
        Flat list of story element dicts (merged from all pages).
    """
    if api_key:
        global OPENAI_API_KEY
        OPENAI_API_KEY = api_key

    all_elements = []
    for page in pages[:max_pages]:
        page_text = page.get('text', '')
        if not page_text or len(page_text) < 50:
            continue
        canonical_title = page.get('canonical_title', venue_name)
        artist = page.get('artist', '')
        source_url = page.get('url', '')
        elements = extract_elements_from_text(page_text, canonical_title, artist, source_url)
        all_elements.extend(elements)

    # Score corroboration if we have enough elements
    if len(all_elements) >= 2:
        try:
            all_elements = score_corroboration(all_elements)
        except Exception:
            pass

    return all_elements


def persist_story_elements(elements: List[Dict], output_path: str) -> None:
    """Persist story elements to a JSON file for downstream QA (G4 check).

    Args:
        elements: List of story element dicts.
        output_path: File path to write JSON to.
    """
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(elements, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"  [§3] Failed to persist story elements: {e}")
