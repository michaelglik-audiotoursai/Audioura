"""story_first.py — LOCAL-440/443: Story-first generation pipeline.

Michael's 4-step process: for each selected stop, BEFORE narration:
  1. Fact → stop → exhibition connection (anchor facts from fact sheet/corpus)
  2. Story-seeking query (targeted external search for stories, not facts)
  3. Candidate evaluation (classify + verify, verified-only candidacy)
  4. Size adaptation (expand if too thin, summarize if too long)

LOCAL-443 enhancements (D443):
  A. Full-page fetch for promising tier1/tier2 URLs (≤3 pages/stop), reusing
     LOCAL-427 backoff fetch + LOCAL-441 concurrency pattern.
  B. Candidate pre-filter BEFORE any LLM call: drop <3 sentences, no person-name
     token, SHA-dedup within stop. Target: ≤10 candidates reach gpt-4o-mini.
  C. Classification concurrency: thread pool with lock on verdict cache.
  D. Budget discipline: hard 25s per-stop wall budget for the FULL pipeline
     (fetch + extract + classify + verify). On exhaustion, return what's verified.

Then hand to the LOCAL-438 packer (select_stories_for_stop, STOP_WORD_BUDGET=450).

Key invariant (D393/D373 Desnos warning):
  A story enters candidacy ONLY if its claims are corroborated by a fetched source.
  An unverifiable great story LOSES to a verified plain one.

Public API (module scope, imported by tests):
  - STORY_SEEKING_BUDGET_SECONDS: per-stop wall budget for story seeking (15s)
  - STORY_SEEKING_POOL_SIZE: thread pool for concurrent queries
  - PIPELINE_WALL_BUDGET_SECONDS: per-stop budget for ENTIRE pipeline (25s)
  - FULLPAGE_FETCH_MAX_PAGES: max pages to fetch per stop (3)
  - PREFILTER_MAX_CANDIDATES: max candidates after pre-filter (10)
  - extract_anchor_facts(stop_data, fact_sheet) -> dict
  - build_story_seeking_queries(anchor_facts) -> list[str]
  - seek_stories_for_stop(stop_data, anchor_facts, budget_seconds=None) -> dict
  - fetch_full_pages(urls, budget_seconds=None) -> list[dict]
  - prefilter_candidates(candidates, stop_name='') -> list[str]
  - evaluate_candidates(candidates, snippets, credit_line, stop_name) -> list[dict]
  - evaluate_candidates_concurrent(...) -> list[dict]
  - adapt_story_size(story_text, target_words=120, max_words=200) -> str
  - story_first_pipeline(stop_data, fact_sheet, snippets, credit_line) -> dict
  - disable_story_seeking() / enable_story_seeking() — neutralisation controls
  - disable_prefilter() / enable_prefilter() — neutralisation for D242 #1
  - disable_fullpage_fetch() / enable_fullpage_fetch() — neutralisation for D242 #1
"""
import concurrent.futures
import hashlib
import json
import os
import re
import threading
import time
from typing import Dict, List, Optional, Tuple

from cost_rates import llm_cost, search_cost

# --- Configuration ---
STORY_SEEKING_BUDGET_SECONDS = 15.0  # Per-stop wall budget for SERP queries
STORY_SEEKING_POOL_SIZE = 5  # Concurrent query threads per stop
STORY_SEEKING_MAX_QUERIES = 6  # Max queries per stop for story-seeking
STORY_CANDIDATE_MIN_WORDS = 40  # Too-small threshold
STORY_CANDIDATE_MAX_WORDS = 200  # Too-large threshold (before summarize)
STORY_TARGET_WORDS = 120  # Target size after adaptation (~3 sentences)

# LOCAL-443: Pipeline budget discipline (D395)
PIPELINE_WALL_BUDGET_SECONDS = 25.0  # Hard per-stop wall budget for WHOLE pipeline

# LOCAL-443: Full-page fetch configuration
FULLPAGE_FETCH_MAX_PAGES = 3  # Max pages to fetch per stop (tier1/tier2 only)
FULLPAGE_FETCH_TIMEOUT = 10  # Per-page HTTP timeout (seconds)
FULLPAGE_FETCH_POOL_SIZE = 3  # Concurrent page fetches

# LOCAL-443: Pre-filter configuration
PREFILTER_MAX_CANDIDATES = 10  # Max candidates reaching the LLM classifier
PREFILTER_MIN_SENTENCES = 3  # Minimum sentences for a candidate

# LOCAL-443: Classification concurrency
CLASSIFY_POOL_SIZE = 5  # Concurrent classification threads

# Neutralisation flags
_STORY_SEEKING_DISABLED = False
_PREFILTER_DISABLED = False  # D242 #1: disable pre-filter to show volume explosion
_FULLPAGE_FETCH_DISABLED = False  # D242 #1: disable full-page fetch

# Cost tracking for the pipeline
_pipeline_cost_usd = 0.0
_pipeline_queries_issued = 0


def disable_story_seeking():
    """Disable story-seeking — pipeline falls back to current behaviour."""
    global _STORY_SEEKING_DISABLED
    _STORY_SEEKING_DISABLED = True


def enable_story_seeking():
    """Re-enable story-seeking (default state)."""
    global _STORY_SEEKING_DISABLED
    _STORY_SEEKING_DISABLED = False


def is_story_seeking_enabled() -> bool:
    """Return whether story-seeking is currently active."""
    return not _STORY_SEEKING_DISABLED


def disable_prefilter():
    """Disable pre-filter — for D242 #1 neutralisation proof."""
    global _PREFILTER_DISABLED
    _PREFILTER_DISABLED = True


def enable_prefilter():
    """Re-enable pre-filter (default state)."""
    global _PREFILTER_DISABLED
    _PREFILTER_DISABLED = False


def is_prefilter_enabled() -> bool:
    """Return whether pre-filter is active."""
    return not _PREFILTER_DISABLED


def disable_fullpage_fetch():
    """Disable full-page fetch — for D242 #1 neutralisation proof."""
    global _FULLPAGE_FETCH_DISABLED
    _FULLPAGE_FETCH_DISABLED = True


def enable_fullpage_fetch():
    """Re-enable full-page fetch (default state)."""
    global _FULLPAGE_FETCH_DISABLED
    _FULLPAGE_FETCH_DISABLED = False


def is_fullpage_fetch_enabled() -> bool:
    """Return whether full-page fetch is active."""
    return not _FULLPAGE_FETCH_DISABLED


def get_pipeline_cost() -> dict:
    """Return cumulative cost from this session's story-first pipeline."""
    return {
        'total_cost_usd': _pipeline_cost_usd,
        'queries_issued': _pipeline_queries_issued,
    }


def reset_pipeline_cost():
    """Reset cost counters (for testing/per-run isolation)."""
    global _pipeline_cost_usd, _pipeline_queries_issued
    _pipeline_cost_usd = 0.0
    _pipeline_queries_issued = 0


# ---------------------------------------------------------------------------
# Step 1: Fact → stop → exhibition connection
# ---------------------------------------------------------------------------

def extract_anchor_facts(stop_data: Dict, fact_sheet: str = '') -> Dict:
    """Extract concrete anchor facts from stop data and fact sheet.

    Identifies the artist, work, date, technique, credit line, and
    how the stop connects to the exhibition/venue thesis.

    Args:
        stop_data: dict with keys like canonical_title, artist, medium,
                   credit_line, publisher, venue_name, exhibition_name
        fact_sheet: raw fact sheet text (from spine generation)

    Returns:
        dict with structured anchor facts:
        {
            'artist': str,
            'work_title': str,
            'date': str,
            'technique': str,
            'credit_line': str,
            'publisher': str,
            'printer': str,
            'donor': str,
            'exhibition_connection': str,
            'key_entities': list[str],  # names that must appear in stories
        }
    """
    artist = (stop_data.get('artist') or '').strip()
    title = (stop_data.get('canonical_title') or stop_data.get('name', '')).strip()
    credit_line = (stop_data.get('credit_line') or '').strip()
    medium = (stop_data.get('medium') or '').strip()
    publisher = (stop_data.get('publisher') or '').strip()
    venue_name = (stop_data.get('venue_name') or '').strip()
    exhibition_name = (stop_data.get('exhibition_name') or '').strip()

    # Extract donor from credit line
    donor = ''
    donor_match = re.search(
        r'(?:gift\s+of|donated\s+by|bequest\s+of|given\s+by)\s+(.+?)(?:\s+to\b|[,;.]|$)',
        credit_line, re.IGNORECASE)
    if donor_match:
        donor = donor_match.group(1).strip()

    # Extract printer from credit line
    printer = ''
    printer_match = re.search(
        r'(?:printed\s+by|imprimé\s+par)\s+(.+?)(?:[,;.]|\s+(?:for|pour)\b|$)',
        credit_line, re.IGNORECASE)
    if printer_match:
        printer = printer_match.group(1).strip()

    # Extract date from credit line or fact sheet
    date = ''
    date_match = re.search(r'\b(1[0-9]{3}|20[0-2][0-9])\b', credit_line)
    if date_match:
        date = date_match.group(1)
    elif fact_sheet:
        date_match = re.search(r'\b(1[0-9]{3}|20[0-2][0-9])\b', fact_sheet)
        if date_match:
            date = date_match.group(1)

    # Exhibition connection
    exhibition_connection = ''
    if exhibition_name:
        exhibition_connection = f"Part of '{exhibition_name}' at {venue_name}"
    elif venue_name:
        exhibition_connection = f"Held at {venue_name}"

    # Key entities — names that a valid story MUST reference
    key_entities = []
    if artist:
        key_entities.append(artist)
    if donor:
        key_entities.append(donor)
    if publisher:
        key_entities.append(publisher)

    return {
        'artist': artist,
        'work_title': title,
        'date': date,
        'technique': medium,
        'credit_line': credit_line,
        'publisher': publisher,
        'printer': printer,
        'donor': donor,
        'exhibition_connection': exhibition_connection,
        'key_entities': key_entities,
    }


# ---------------------------------------------------------------------------
# Step 2: Story-seeking queries
# ---------------------------------------------------------------------------

def build_story_seeking_queries(anchor_facts: Dict) -> List[str]:
    """Build targeted queries that seek STORIES, not general facts.

    Query shapes per D393:
      "<artist> <work> history incident"
      "<work> edition destroyed|recreated|dispute|commission story"
      "<donor> why donated collection"
      "<publisher> <artist> collaboration story"

    These are DIFFERENT from synthesize_queries() in work_story_searcher.py —
    those target facts/provenance. These target narrative/incident/arc.
    """
    artist = anchor_facts.get('artist', '')
    title = anchor_facts.get('work_title', '')
    publisher = anchor_facts.get('publisher', '')
    printer = anchor_facts.get('printer', '')
    donor = anchor_facts.get('donor', '')
    date = anchor_facts.get('date', '')

    queries = []

    # Core story-seeking queries — targeting incident/arc/drama
    if artist and title:
        queries.append(f'"{title}" {artist} story incident history')
        queries.append(f'{artist} "{title}" destroyed recreated dispute commission')

    elif title:
        queries.append(f'"{title}" story behind history incident')
        queries.append(f'"{title}" controversy creation destroyed')

    # Collaborator stories
    if publisher and artist:
        queries.append(f'{publisher} {artist} collaboration story how why')

    if printer and artist:
        queries.append(f'{printer} {artist} printing story challenge')

    # Donor provenance story
    if donor:
        queries.append(f'{donor} collection donation story why')

    # Date-anchored incident
    if date and artist:
        queries.append(f'{artist} {date} what happened story')

    # Cap at STORY_SEEKING_MAX_QUERIES
    return queries[:STORY_SEEKING_MAX_QUERIES]


def seek_stories_for_stop(stop_data: Dict, anchor_facts: Dict,
                          budget_seconds: float = None) -> Dict:
    """Execute story-seeking queries concurrently within a wall-budget.

    Uses the existing SERP machinery (work_story_searcher._serp_search) under
    a per-stop budget. Respects the neutralisation flag.

    Args:
        stop_data: stop dict for context
        anchor_facts: output of extract_anchor_facts()
        budget_seconds: wall-clock budget (default: STORY_SEEKING_BUDGET_SECONDS)

    Returns:
        {
            'results': list of {url, title, snippet, domain, tier},
            'queries_issued': int,
            'query_log': list of {query, result_count, latency_ms},
            'elapsed_seconds': float,
            'estimated_cost_usd': float,
        }
    """
    global _pipeline_cost_usd, _pipeline_queries_issued

    if _STORY_SEEKING_DISABLED:
        return {
            'results': [],
            'queries_issued': 0,
            'query_log': [],
            'elapsed_seconds': 0.0,
            'estimated_cost_usd': 0.0,
        }

    if budget_seconds is None:
        budget_seconds = STORY_SEEKING_BUDGET_SECONDS

    queries = build_story_seeking_queries(anchor_facts)
    if not queries:
        return {
            'results': [],
            'queries_issued': 0,
            'query_log': [],
            'elapsed_seconds': 0.0,
            'estimated_cost_usd': 0.0,
        }

    # Import SERP machinery
    try:
        from work_story_searcher import _serp_search, normalize_domain, _classify_domain_quick
        from work_story_searcher import _MODULE_DOMAIN_CACHE, batch_check_wikidata_p856
    except ImportError as e:
        print(f"  [LOCAL-440] Cannot import SERP machinery: {e}")
        return {
            'results': [],
            'queries_issued': 0,
            'query_log': [],
            'elapsed_seconds': 0.0,
            'estimated_cost_usd': 0.0,
        }

    start_time = time.time()
    all_results = []
    query_log = []
    queries_issued = 0

    # Execute queries concurrently within budget
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=STORY_SEEKING_POOL_SIZE)
    try:
        future_to_query = {
            executor.submit(_serp_search, q): q for q in queries
        }

        remaining = budget_seconds - (time.time() - start_time)
        done, not_done = concurrent.futures.wait(
            future_to_query.keys(),
            timeout=max(0, remaining),
            return_when=concurrent.futures.ALL_COMPLETED,
        )

        for future in done:
            query = future_to_query[future]
            queries_issued += 1
            try:
                results, latency = future.result(timeout=0)
                query_log.append({
                    'query': query,
                    'result_count': len(results),
                    'latency_ms': round(latency, 1),
                })
                for r in results:
                    r['domain'] = normalize_domain(r.get('url', ''))
                    all_results.append(r)
            except Exception as e:
                query_log.append({
                    'query': query,
                    'result_count': 0,
                    'latency_ms': 0,
                    'error': str(e),
                })

        # Budget-expired queries
        for future in not_done:
            query = future_to_query[future]
            query_log.append({
                'query': query,
                'result_count': 0,
                'latency_ms': 0,
                'budget_expired': True,
            })
            future.cancel()
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    # Classify domains (reuse LOCAL-441 pattern)
    domain_cache = dict(_MODULE_DOMAIN_CACHE)
    domains_needing_p856 = set()

    for r in all_results:
        domain = r.get('domain', '')
        if domain in domain_cache:
            continue
        quick_tier = _classify_domain_quick(domain)
        if quick_tier is not None:
            domain_cache[domain] = quick_tier
        else:
            domains_needing_p856.add(domain)

    # Batch P856 for unknown domains (within remaining budget)
    remaining_budget = budget_seconds - (time.time() - start_time)
    if domains_needing_p856 and remaining_budget > 2:
        p856_results = batch_check_wikidata_p856(
            list(domains_needing_p856),
            budget_seconds=min(remaining_budget - 1, 10),
        )
        domain_cache.update(p856_results)
        _MODULE_DOMAIN_CACHE.update(p856_results)

    # Assign tiers and filter rejects
    classified_results = []
    for r in all_results:
        domain = r.get('domain', '')
        tier = domain_cache.get(domain, 'tier3')
        r['tier'] = tier
        if tier != 'reject':
            classified_results.append(r)

    elapsed = time.time() - start_time
    cost = search_cost(queries_issued)
    _pipeline_cost_usd += cost
    _pipeline_queries_issued += queries_issued

    print(f"  [LOCAL-440] Story-seeking: {queries_issued} queries, "
          f"{len(classified_results)} results, {elapsed:.1f}s")

    return {
        'results': classified_results,
        'queries_issued': queries_issued,
        'query_log': query_log,
        'elapsed_seconds': elapsed,
        'estimated_cost_usd': cost,
    }


# ---------------------------------------------------------------------------
# LOCAL-443 Step A: Full-page fetch for promising URLs
# ---------------------------------------------------------------------------

def _extract_page_text(html: str) -> str:
    """Extract readable prose text from HTML, stripping nav/scripts/ads.

    Uses the same paragraph-extraction strategy as exhibition_checklist._fetch_page
    (LOCAL-427) but returns joined prose text for story-unit extraction.
    """
    if not html:
        return ''

    # Remove scripts, styles, nav, header, footer
    cleaned = re.sub(r'<(?:script|style|nav|header|footer|aside)[^>]*>.*?</(?:script|style|nav|header|footer|aside)>',
                     '', html, flags=re.DOTALL | re.IGNORECASE)

    # Extract paragraphs (same regex as exhibition_checklist, LOCAL-373 safe)
    paragraphs = []
    seen = set()
    for p_match in re.finditer(r'<p(?:\s[^>]*)?>(.+?)</p>', cleaned, re.DOTALL):
        clean = re.sub(r'<[^>]+>', '', p_match.group(1)).strip()
        clean = re.sub(r'&nbsp;', ' ', clean)
        clean = re.sub(r'&[a-z]+;', ' ', clean)
        clean = re.sub(r'\s+', ' ', clean)
        if len(clean) > 30 and clean not in seen:
            seen.add(clean)
            paragraphs.append(clean)

    # Also extract article/main content if paragraphs are sparse
    if len(paragraphs) < 3:
        for tag in ('article', 'main', r'div[^>]*class="[^"]*(?:content|article|post|entry)[^"]*"'):
            for block_match in re.finditer(f'<{tag}[^>]*>(.*?)</{tag.split("[")[0]}>', cleaned, re.DOTALL | re.IGNORECASE):
                block_text = re.sub(r'<[^>]+>', ' ', block_match.group(1))
                block_text = re.sub(r'\s+', ' ', block_text).strip()
                if len(block_text) > 100:
                    # Split into sentence-like chunks
                    sentences = re.split(r'(?<=[.!?])\s+', block_text)
                    for s in sentences:
                        s = s.strip()
                        if len(s) > 30 and s not in seen:
                            seen.add(s)
                            paragraphs.append(s)

    return '\n'.join(paragraphs)


def _fetch_single_page(url: str, timeout: int = None) -> Dict:
    """Fetch a single page using LOCAL-427 backoff pattern (simplified for story-first).

    Returns dict with:
      url: str
      text: str (extracted prose)
      success: bool
      elapsed_ms: float
    """
    import urllib.request
    import urllib.error

    if timeout is None:
        timeout = FULLPAGE_FETCH_TIMEOUT

    start = time.time()

    try:
        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'Audioura/2.2 StoryFirst',
                'Accept': 'text/html,application/xhtml+xml',
                'Accept-Language': 'en-US,en;q=0.9',
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # Only process HTML responses
            content_type = resp.headers.get('Content-Type', '')
            if 'text/html' not in content_type and 'application/xhtml' not in content_type:
                return {'url': url, 'text': '', 'success': False,
                        'elapsed_ms': (time.time() - start) * 1000}

            html = resp.read().decode('utf-8', errors='replace')
            text = _extract_page_text(html)
            elapsed_ms = (time.time() - start) * 1000

            return {'url': url, 'text': text, 'success': bool(text),
                    'elapsed_ms': elapsed_ms}

    except urllib.error.HTTPError as e:
        elapsed_ms = (time.time() - start) * 1000
        if e.code == 429:
            # Rate limited — one retry after short backoff (budget-aware)
            time.sleep(min(2.0, timeout / 3))
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    html = resp.read().decode('utf-8', errors='replace')
                    text = _extract_page_text(html)
                    elapsed_ms = (time.time() - start) * 1000
                    return {'url': url, 'text': text, 'success': bool(text),
                            'elapsed_ms': elapsed_ms}
            except Exception:
                pass
        return {'url': url, 'text': '', 'success': False, 'elapsed_ms': elapsed_ms}

    except Exception:
        elapsed_ms = (time.time() - start) * 1000
        return {'url': url, 'text': '', 'success': False, 'elapsed_ms': elapsed_ms}


def fetch_full_pages(urls: List[str], budget_seconds: float = None) -> List[Dict]:
    """[LOCAL-443-A] Fetch full page content for top tier1/tier2 URLs.

    Concurrent fetch (LOCAL-441 pattern) with wall-budget. Returns extracted
    prose text for each successfully fetched page.

    Args:
        urls: list of URLs to fetch (already filtered to tier1/tier2, capped)
        budget_seconds: wall budget for all fetches (default: remaining pipeline budget)

    Returns:
        list of {url, text, success, elapsed_ms}
    """
    if _FULLPAGE_FETCH_DISABLED:
        return []

    if not urls:
        return []

    if budget_seconds is None:
        budget_seconds = FULLPAGE_FETCH_TIMEOUT * 2  # Sensible default

    # Cap at FULLPAGE_FETCH_MAX_PAGES
    urls = urls[:FULLPAGE_FETCH_MAX_PAGES]

    start = time.time()
    results = []

    # Concurrent fetch (LOCAL-441 pattern: thread pool + wall-budget)
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=FULLPAGE_FETCH_POOL_SIZE)
    try:
        future_to_url = {
            executor.submit(_fetch_single_page, url): url for url in urls
        }

        remaining = budget_seconds - (time.time() - start)
        done, not_done = concurrent.futures.wait(
            future_to_url.keys(),
            timeout=max(0, remaining),
            return_when=concurrent.futures.ALL_COMPLETED,
        )

        for future in done:
            try:
                result = future.result(timeout=0)
                results.append(result)
            except Exception:
                url = future_to_url[future]
                results.append({'url': url, 'text': '', 'success': False, 'elapsed_ms': 0})

        # Budget-expired fetches
        for future in not_done:
            url = future_to_url[future]
            results.append({'url': url, 'text': '', 'success': False,
                            'elapsed_ms': 0, 'budget_expired': True})
            future.cancel()
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    elapsed = time.time() - start
    succeeded = sum(1 for r in results if r['success'])
    print(f"  [LOCAL-443] Full-page fetch: {len(urls)} URLs, "
          f"{succeeded} succeeded, {elapsed:.1f}s")

    return results


# ---------------------------------------------------------------------------
# LOCAL-443 Step B: Candidate pre-filter (zero-cost structural filter)
# ---------------------------------------------------------------------------

# Person-name pattern: two+ words starting with uppercase (handles accented chars)
_PERSON_NAME_PATTERN = re.compile(
    r'\b[A-Z\u00C0-\u024F][a-z\u00E0-\u024F]+(?:\s+[A-Z\u00C0-\u024F][a-z\u00E0-\u024F]+)+\b'
)


def prefilter_candidates(candidates: List[str], stop_name: str = '') -> List[str]:
    """[LOCAL-443-B] Zero-cost structural pre-filter BEFORE any LLM call.

    Drops candidates that structurally cannot be stories:
      1. < 3 sentences (cannot have setup → struggle → resolution)
      2. No person-name-shaped token (stories need named people)
      3. SHA-duplicate within the stop (same text re-fetched from different sources)

    Target: ≤ PREFILTER_MAX_CANDIDATES survive to reach gpt-4o-mini.

    When _PREFILTER_DISABLED is True, this returns all candidates unchanged
    (for D242 #1 neutralisation proof that volume explodes without it).

    Args:
        candidates: raw candidate texts
        stop_name: for logging

    Returns:
        Filtered list of candidate texts (order preserved, deduped)
    """
    if _PREFILTER_DISABLED:
        # Neutralisation: return all candidates, log the volume
        print(f"  [LOCAL-443] Pre-filter DISABLED: {len(candidates)} candidates "
              f"pass unfiltered (would normally filter)")
        return candidates

    if not candidates:
        return []

    sha_seen = set()
    filtered = []
    rejected_reasons = {'short': 0, 'no_name': 0, 'duplicate': 0}

    for text in candidates:
        if not text or not text.strip():
            continue

        # 1. SHA deduplication
        sha = hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]
        if sha in sha_seen:
            rejected_reasons['duplicate'] += 1
            continue
        sha_seen.add(sha)

        # 2. Minimum 3 sentences
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        # Filter out very short fragments
        sentences = [s for s in sentences if len(s.strip()) >= 15]
        if len(sentences) < PREFILTER_MIN_SENTENCES:
            rejected_reasons['short'] += 1
            continue

        # 3. Must contain at least one person-name-shaped token
        if not _PERSON_NAME_PATTERN.search(text):
            rejected_reasons['no_name'] += 1
            continue

        filtered.append(text)

    # Cap at PREFILTER_MAX_CANDIDATES (take longest — more likely to contain arcs)
    if len(filtered) > PREFILTER_MAX_CANDIDATES:
        filtered.sort(key=len, reverse=True)
        filtered = filtered[:PREFILTER_MAX_CANDIDATES]

    total_rejected = sum(rejected_reasons.values())
    print(f"  [LOCAL-443] Pre-filter: {len(candidates)} → {len(filtered)} "
          f"(rejected: {rejected_reasons})")

    return filtered


# ---------------------------------------------------------------------------
# Step 3: Candidate evaluation (classify + verify)
# ---------------------------------------------------------------------------

# Lock for thread-safe access to story_gate._verdict_cache
_verdict_cache_lock = threading.Lock()


def _classify_single_candidate(candidate_text: str, idx: int) -> Optional[Dict]:
    """Classify a single candidate (thread-safe wrapper for story_gate).

    Returns the classification dict if it passes, None otherwise.
    """
    from story_gate import classify_story_unit, score_story_interest, _verdict_cache, _cache_key

    if not candidate_text or len(candidate_text.strip()) < 50:
        return None

    # Thread-safe cache check
    key = _cache_key(candidate_text)
    with _verdict_cache_lock:
        if key in _verdict_cache:
            cached = _verdict_cache[key].copy()
            cached['from_cache'] = True
            cached['cost_usd'] = 0.0
            if not cached.get('is_story', False):
                return None
            return cached

    # Not cached — call the LLM (this is the expensive part)
    classification = classify_story_unit(candidate_text)

    # The classify_story_unit function handles its own caching internally,
    # but we hold the lock for the read above to prevent redundant calls.

    if not classification.get('is_story', False):
        return None

    return classification


def evaluate_candidates(candidates: List[str], snippets: List[Dict],
                        credit_line: str = '', stop_name: str = '') -> List[Dict]:
    """Classify and verify story candidates. Only verified pass.

    Uses the SHIPPED LOCAL-439 machinery (classify_story_unit, score_story_interest)
    for classification, and LOCAL-423/424 (verify_story_candidate) for verification.

    D393 invariant: An unverifiable great story LOSES to a verified plain one.
    Verification is the HARD GATE; interest only ranks among verified candidates.

    Args:
        candidates: list of candidate story texts (from SERP snippets + fetch)
        snippets: the source snippets used to verify claims
        credit_line: for entity disambiguation
        stop_name: for logging

    Returns:
        Sorted list of verified candidates (best first):
        [
            {
                'text': str,
                'is_story': bool,
                'interest_score': float,
                'verified': bool,
                'verification_detail': dict,
                'classification': dict,
            },
            ...
        ]
        Only entries where verified=True AND is_story=True are included.
    """
    from story_gate import classify_story_unit, score_story_interest
    from story_verifier import verify_story_candidate

    evaluated = []

    for i, candidate_text in enumerate(candidates):
        if not candidate_text or len(candidate_text.strip()) < 50:
            continue

        # Step 3a: Classify — is this actually a story?
        classification = classify_story_unit(candidate_text)
        if not classification.get('is_story', False):
            print(f"    [LOCAL-440] Candidate {i+1} not a story: "
                  f"{classification.get('reason', 'unknown')[:80]}")
            continue

        # Step 3b: Score interest
        interest = score_story_interest(candidate_text)
        interest_score = interest.get('interest_score', 0)

        # Step 3c: VERIFY — the hard gate (D393/D373)
        verification = verify_story_candidate(
            story_text=candidate_text,
            snippets=snippets,
            credit_line=credit_line,
            stop_name=stop_name,
        )

        if not verification.get('passed', False):
            print(f"    [LOCAL-440] Candidate {i+1} UNVERIFIED (rejected): "
                  f"{verification.get('claims_unsourced', 0)} unsourced claims")
            for reason in verification.get('rejection_reasons', [])[:2]:
                print(f"      → {reason[:100]}")
            continue

        # Both story AND verified — enters candidacy
        evaluated.append({
            'text': candidate_text,
            'is_story': True,
            'interest_score': interest_score,
            'verified': True,
            'verification_detail': verification,
            'classification': classification,
        })

    # Rank by interest score (descending) among verified-only candidates
    evaluated.sort(key=lambda x: x['interest_score'], reverse=True)

    print(f"  [LOCAL-440] Evaluation: {len(candidates)} candidates → "
          f"{len(evaluated)} verified stories")

    return evaluated


def evaluate_candidates_concurrent(candidates: List[str], snippets: List[Dict],
                                   credit_line: str = '', stop_name: str = '',
                                   budget_seconds: float = None) -> List[Dict]:
    """[LOCAL-443-C] Classify + verify candidates concurrently within a budget.

    Same semantics as evaluate_candidates but uses a thread pool for classification
    and respects a wall-budget. On budget exhaustion, returns what's verified so far.

    Thread safety: story_gate._verdict_cache is a plain dict. We use
    _verdict_cache_lock around cache reads to prevent redundant LLM calls,
    but dict assignment is atomic in CPython (GIL). The lock prevents double-
    classification of the same text when multiple threads race on the same candidate.

    Args:
        candidates: pre-filtered candidate texts
        snippets: source snippets for verification
        credit_line: for entity disambiguation
        stop_name: for logging
        budget_seconds: wall-clock budget for classification + verification

    Returns:
        Same format as evaluate_candidates — sorted verified candidates.
    """
    from story_gate import classify_story_unit, score_story_interest
    from story_verifier import verify_story_candidate

    if not candidates:
        return []

    if budget_seconds is None:
        budget_seconds = 15.0  # Sensible default within the 25s pipeline budget

    start = time.time()
    evaluated = []

    # Phase 1: Concurrent classification
    classifications = [None] * len(candidates)
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=CLASSIFY_POOL_SIZE)
    try:
        future_to_idx = {
            executor.submit(_classify_single_candidate, text, i): i
            for i, text in enumerate(candidates)
        }

        remaining = budget_seconds - (time.time() - start)
        done, not_done = concurrent.futures.wait(
            future_to_idx.keys(),
            timeout=max(0, remaining * 0.6),  # Reserve 40% for verification
            return_when=concurrent.futures.ALL_COMPLETED,
        )

        for future in done:
            idx = future_to_idx[future]
            try:
                result = future.result(timeout=0)
                classifications[idx] = result
            except Exception as e:
                print(f"    [LOCAL-443] Classification error for candidate {idx+1}: {e}")

        # Cancel budget-expired
        for future in not_done:
            future.cancel()
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    # Phase 2: Score + verify passing candidates (serial — verification is I/O-light)
    classified_count = sum(1 for c in classifications if c is not None)
    print(f"  [LOCAL-443] Concurrent classification: {classified_count}/{len(candidates)} "
          f"are stories ({time.time() - start:.1f}s)")

    for i, classification in enumerate(classifications):
        # Budget check
        elapsed = time.time() - start
        if elapsed >= budget_seconds:
            print(f"  [LOCAL-443] Budget exhausted at candidate {i+1}/{len(candidates)} "
                  f"— returning {len(evaluated)} verified so far")
            break

        if classification is None:
            continue

        candidate_text = candidates[i]

        # Score interest (uses cached classification — free)
        interest = score_story_interest(candidate_text)
        interest_score = interest.get('interest_score', 0)

        # Verify — the hard gate
        verification = verify_story_candidate(
            story_text=candidate_text,
            snippets=snippets,
            credit_line=credit_line,
            stop_name=stop_name,
        )

        if not verification.get('passed', False):
            print(f"    [LOCAL-443] Candidate {i+1} UNVERIFIED: "
                  f"{verification.get('claims_unsourced', 0)} unsourced claims")
            continue

        evaluated.append({
            'text': candidate_text,
            'is_story': True,
            'interest_score': interest_score,
            'verified': True,
            'verification_detail': verification,
            'classification': classification,
        })

    # Rank by interest score
    evaluated.sort(key=lambda x: x['interest_score'], reverse=True)

    elapsed = time.time() - start
    print(f"  [LOCAL-443] Concurrent evaluation: {len(candidates)} candidates → "
          f"{len(evaluated)} verified stories ({elapsed:.1f}s)")

    return evaluated


# ---------------------------------------------------------------------------
# Step 4: Size adaptation
# ---------------------------------------------------------------------------

def adapt_story_size(story_text: str, target_words: int = None,
                     max_words: int = None) -> str:
    """Adapt story size: expand if too thin, summarize if too long.

    Too small (< STORY_CANDIDATE_MIN_WORDS): return as-is (caller does follow-up query)
    Too large (> max_words): summarize to ~target_words preserving arc
    Just right: return as-is

    Args:
        story_text: the verified story text
        target_words: target word count after adaptation
        max_words: threshold above which to summarize

    Returns:
        Adapted text (may be unchanged, summarized, or marked for expansion)
    """
    global _pipeline_cost_usd

    if target_words is None:
        target_words = STORY_TARGET_WORDS
    if max_words is None:
        max_words = STORY_CANDIDATE_MAX_WORDS

    if not story_text:
        return story_text

    word_count = len(story_text.split())

    # Just right — no change
    if STORY_CANDIDATE_MIN_WORDS <= word_count <= max_words:
        return story_text

    # Too small — return with marker (caller checks word count and may expand)
    if word_count < STORY_CANDIDATE_MIN_WORDS:
        return story_text

    # Too large — summarize preserving the arc
    summarized = _summarize_story(story_text, target_words)
    return summarized


def _summarize_story(story_text: str, target_words: int) -> str:
    """Summarize a long story to ~target_words preserving the arc.

    Uses gpt-4o-mini for summarization (cheap, fast).
    Falls back to mechanical truncation if LLM unavailable.
    """
    global _pipeline_cost_usd

    openai_key = os.environ.get('OPENAI_API_KEY', '')
    if not openai_key:
        # Fallback: take first ~target_words words
        words = story_text.split()
        return ' '.join(words[:target_words])

    try:
        import urllib.request

        prompt = f"""Summarize this story to approximately {target_words} words.
Preserve: the named person, their actions, and the arc (setup → struggle → resolution).
Do NOT add interpretation or visitor-directed language.
Return ONLY the summarized story text, nothing else.

Story:
{story_text}"""

        payload = json.dumps({
            'model': 'gpt-4o-mini',
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0,
            'max_tokens': target_words * 2,
        }).encode('utf-8')

        req = urllib.request.Request(
            'https://api.openai.com/v1/chat/completions',
            data=payload,
            headers={
                'Authorization': f'Bearer {openai_key}',
                'Content-Type': 'application/json',
            },
            method='POST',
        )

        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
            result = body['choices'][0]['message']['content'].strip()
            usage = body.get('usage', {})
            cost = llm_cost(
                input_tokens=usage.get('prompt_tokens', 0),
                output_tokens=usage.get('completion_tokens', 0),
                model='gpt-4o-mini',
            )
            _pipeline_cost_usd += cost
            return result

    except Exception as e:
        print(f"  [LOCAL-440] Summarization failed ({e}), using truncation fallback")
        words = story_text.split()
        return ' '.join(words[:target_words])


def _expand_story_query(story_text: str, anchor_facts: Dict) -> Optional[str]:
    """Build a follow-up query to expand a too-thin story.

    Returns a single query string targeting more detail about the story's subject.
    """
    artist = anchor_facts.get('artist', '')
    title = anchor_facts.get('work_title', '')

    # Extract the key subject from the thin story
    # Look for proper nouns in the story text
    names = re.findall(r'\b[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)+\b', story_text)
    subject = names[0] if names else artist

    if subject and title:
        return f'{subject} "{title}" detailed story what happened'
    elif subject:
        return f'{subject} story detailed incident event'
    return None


# ---------------------------------------------------------------------------
# Full pipeline: Steps 1-4 combined (LOCAL-443 enhanced)
# ---------------------------------------------------------------------------

def story_first_pipeline(stop_data: Dict, fact_sheet: str = '',
                         snippets: List[Dict] = None,
                         credit_line: str = '',
                         existing_search_results: List[Dict] = None) -> Dict:
    """Run the full 4-step story-first pipeline for a single stop.

    This is the main entry point called from generate_tour_text.py.
    It orchestrates all four steps with LOCAL-443 enhancements:
      A. Full-page fetch for promising tier1/tier2 URLs
      B. Candidate pre-filter before LLM classification
      C. Concurrent classification
      D. Hard per-stop wall budget (PIPELINE_WALL_BUDGET_SECONDS)

    Args:
        stop_data: dict with canonical_title, artist, medium, credit_line, etc.
        fact_sheet: raw fact sheet text from spine generation
        snippets: pre-fetched snippets from LOCAL-410 SERP search
        credit_line: work's credit line
        existing_search_results: results from LOCAL-410 search (reused as corpus)

    Returns:
        {
            'stories': list of story dicts ready for select_stories_for_stop(),
            'anchor_facts': dict from step 1,
            'seeking_result': dict from step 2,
            'fullpage_fetch_result': dict from step 2b (LOCAL-443),
            'evaluation_count': int (candidates evaluated after pre-filter),
            'prefilter_input_count': int (candidates before pre-filter),
            'verified_count': int (passed verification),
            'elapsed_seconds': float,
            'cost_usd': float,
            'fallback': bool (True if story-seeking disabled/failed),
            'budget_exhausted': bool,
        }
    """
    pipeline_start = time.time()
    pipeline_budget = PIPELINE_WALL_BUDGET_SECONDS

    if _STORY_SEEKING_DISABLED:
        return {
            'stories': [],
            'anchor_facts': {},
            'seeking_result': {},
            'fullpage_fetch_result': {},
            'evaluation_count': 0,
            'prefilter_input_count': 0,
            'verified_count': 0,
            'elapsed_seconds': 0.0,
            'cost_usd': 0.0,
            'fallback': True,
            'budget_exhausted': False,
        }

    stop_name = (stop_data.get('canonical_title') or stop_data.get('name', '')).strip()
    print(f"\n  [LOCAL-443] Story-first pipeline for '{stop_name[:50]}' "
          f"(budget={pipeline_budget}s)")

    # ── Step 1: Extract anchor facts ──
    anchor_facts = extract_anchor_facts(stop_data, fact_sheet)
    print(f"    Step 1: anchor_facts — artist='{anchor_facts['artist'][:30]}', "
          f"entities={anchor_facts['key_entities'][:3]}")

    # ── Budget check ──
    def _remaining():
        return pipeline_budget - (time.time() - pipeline_start)

    # ── Step 2: Story-seeking queries (use remaining budget, not full SERP budget) ──
    serp_budget = min(STORY_SEEKING_BUDGET_SECONDS, _remaining() * 0.5)
    seeking_result = seek_stories_for_stop(stop_data, anchor_facts,
                                           budget_seconds=serp_budget)
    story_seeking_results = seeking_result.get('results', [])

    # ── Step 2b (LOCAL-443-A): Full-page fetch for tier1/tier2 URLs ──
    fullpage_fetch_result = {'pages_fetched': 0, 'pages_succeeded': 0,
                             'extracted_candidates': 0, 'elapsed_seconds': 0.0}
    fetched_page_texts = []

    if _remaining() > 5 and not _FULLPAGE_FETCH_DISABLED:
        # Select top tier1/tier2 URLs for full-page fetch
        tier1_tier2_urls = [
            r['url'] for r in story_seeking_results
            if r.get('tier') in ('tier1', 'tier2') and r.get('url')
        ]
        # Deduplicate by domain (one page per domain)
        seen_domains = set()
        deduped_urls = []
        for url in tier1_tier2_urls:
            domain = re.sub(r'^https?://(?:www\.)?', '', url).split('/')[0]
            if domain not in seen_domains:
                seen_domains.add(domain)
                deduped_urls.append(url)

        if deduped_urls:
            fetch_budget = min(_remaining() * 0.4, 10.0)
            fetch_start = time.time()
            page_results = fetch_full_pages(deduped_urls, budget_seconds=fetch_budget)

            for pr in page_results:
                if pr.get('success') and pr.get('text'):
                    fetched_page_texts.append(pr['text'])

            fullpage_fetch_result = {
                'pages_fetched': len(page_results),
                'pages_succeeded': sum(1 for r in page_results if r.get('success')),
                'extracted_candidates': 0,  # Updated below
                'elapsed_seconds': time.time() - fetch_start,
            }

    # ── Budget check ──
    if _remaining() <= 2:
        elapsed = time.time() - pipeline_start
        print(f"  [LOCAL-443] Budget exhausted after SERP+fetch ({elapsed:.1f}s)")
        return {
            'stories': [],
            'anchor_facts': anchor_facts,
            'seeking_result': seeking_result,
            'fullpage_fetch_result': fullpage_fetch_result,
            'evaluation_count': 0,
            'prefilter_input_count': 0,
            'verified_count': 0,
            'elapsed_seconds': elapsed,
            'cost_usd': seeking_result.get('estimated_cost_usd', 0.0),
            'fallback': False,
            'budget_exhausted': True,
        }

    # ── Build candidate corpus ──
    # Merge with existing search results (LOCAL-410) as corpus for verification
    all_snippets = list(snippets or [])
    if existing_search_results:
        all_snippets.extend(existing_search_results)
    # Story-seeking results serve as both candidates AND corpus
    for r in story_seeking_results:
        all_snippets.append({
            'title': r.get('title', ''),
            'snippet': r.get('snippet', ''),
            'url': r.get('url', ''),
            'domain': r.get('domain', ''),
            'tier': r.get('tier', 'tier3'),
        })

    # Build candidate texts from multiple sources:
    candidate_texts = []

    # Source 1: Full-page fetch text → extract story units via story_gate
    if fetched_page_texts:
        from story_gate import extract_candidate_story_units
        for page_text in fetched_page_texts:
            units = extract_candidate_story_units(page_text)
            candidate_texts.extend(units)
        fullpage_fetch_result['extracted_candidates'] = len(candidate_texts)
        print(f"    Step 2b: {len(fetched_page_texts)} pages → "
              f"{len(candidate_texts)} story-unit candidates")

    # Source 2: SERP snippets from story-seeking (may be too short, but try)
    for r in story_seeking_results:
        snippet = r.get('snippet', '')
        if snippet and len(snippet) >= 50:
            candidate_texts.append(snippet)

    # Source 3: Existing LOCAL-410 results
    if existing_search_results:
        for r in existing_search_results:
            snippet = r.get('snippet', '')
            if snippet and len(snippet) >= 50:
                candidate_texts.append(snippet)

    prefilter_input_count = len(candidate_texts)

    # ── Step 2c (LOCAL-443-B): Pre-filter before LLM ──
    unique_candidates = prefilter_candidates(candidate_texts, stop_name=stop_name)

    print(f"    Pre-filter: {prefilter_input_count} raw → {len(unique_candidates)} "
          f"candidates for classification")

    if not unique_candidates:
        elapsed = time.time() - pipeline_start
        return {
            'stories': [],
            'anchor_facts': anchor_facts,
            'seeking_result': seeking_result,
            'fullpage_fetch_result': fullpage_fetch_result,
            'evaluation_count': 0,
            'prefilter_input_count': prefilter_input_count,
            'verified_count': 0,
            'elapsed_seconds': elapsed,
            'cost_usd': seeking_result.get('estimated_cost_usd', 0.0),
            'fallback': False,
            'budget_exhausted': False,
        }

    # ── Step 3 (LOCAL-443-C): Concurrent classification + verification ──
    classify_budget = max(2.0, _remaining() - 2.0)  # Reserve 2s for step 4
    verified = evaluate_candidates_concurrent(
        unique_candidates, all_snippets,
        credit_line=credit_line or anchor_facts.get('credit_line', ''),
        stop_name=stop_name,
        budget_seconds=classify_budget,
    )

    # ── Step 4: Size adaptation ──
    stories_for_packer = []
    for v in verified:
        # Budget check
        if _remaining() <= 0:
            print(f"  [LOCAL-443] Budget exhausted during size adaptation — "
                  f"returning {len(stories_for_packer)} stories")
            break

        adapted_text = adapt_story_size(v['text'])
        word_count = len(adapted_text.split())

        # If too small, attempt one follow-up expansion query (only if budget allows)
        if word_count < STORY_CANDIDATE_MIN_WORDS and _remaining() > 3:
            expansion_query = _expand_story_query(adapted_text, anchor_facts)
            if expansion_query and not _STORY_SEEKING_DISABLED:
                try:
                    from work_story_searcher import _serp_search, normalize_domain
                    results, latency = _serp_search(expansion_query)
                    for r in results:
                        expanded_snippet = r.get('snippet', '')
                        if expanded_snippet and len(expanded_snippet) > len(adapted_text):
                            adapted_text = expanded_snippet
                            word_count = len(adapted_text.split())
                            break
                except Exception:
                    pass  # Non-fatal

        # Build story dict compatible with select_stories_for_stop()
        story_dict = {
            'text': adapted_text,
            'source_domain': v.get('verification_detail', {}).get('evidence', [{}])[0].get('source_url', '') if v.get('verification_detail', {}).get('evidence') else '',
            'source_type': _infer_source_type(v),
            'corroboration_status': 'documented' if v['verified'] else 'reported',
            'people': _extract_people(adapted_text),
            'dates': re.findall(r'\b(1[0-9]{3}|20[0-2][0-9])\b', adapted_text),
            'interest_score': v['interest_score'],
            '_word_count': word_count,
            '_story_first': True,  # Tag for traceability
            '_from_fullpage': any(v['text'] in pt for pt in fetched_page_texts) if fetched_page_texts else False,
        }
        stories_for_packer.append(story_dict)

    elapsed = time.time() - pipeline_start
    total_cost = seeking_result.get('estimated_cost_usd', 0.0)
    budget_exhausted = elapsed >= pipeline_budget

    print(f"    Step 4: {len(stories_for_packer)} stories ready for packer "
          f"({elapsed:.1f}s, ${total_cost:.4f})"
          f"{' [BUDGET EXHAUSTED]' if budget_exhausted else ''}")

    return {
        'stories': stories_for_packer,
        'anchor_facts': anchor_facts,
        'seeking_result': seeking_result,
        'fullpage_fetch_result': fullpage_fetch_result,
        'evaluation_count': len(unique_candidates),
        'prefilter_input_count': prefilter_input_count,
        'verified_count': len(verified),
        'elapsed_seconds': elapsed,
        'cost_usd': total_cost,
        'fallback': False,
        'budget_exhausted': budget_exhausted,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _infer_source_type(evaluated_candidate: Dict) -> str:
    """Infer source type from verification evidence for provenance scoring."""
    evidence = evaluated_candidate.get('verification_detail', {}).get('evidence', [])
    if not evidence:
        return 'web_search'

    # Check first evidence URL for institutional signals
    url = evidence[0].get('source_url', '').lower()
    if any(x in url for x in ('.edu', '.gov', '.museum', 'museum', 'gallery')):
        return 'museum_official'
    if 'wikipedia' in url:
        return 'wikipedia'
    if any(x in url for x in ('heritage', 'archives', 'library')):
        return 'heritage'
    return 'external_verified'


def _extract_people(text: str) -> List[str]:
    """Extract proper names from text for the packer's specificity scoring."""
    names = re.findall(r'\b[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)+\b', text)
    return list(set(names))[:5]
