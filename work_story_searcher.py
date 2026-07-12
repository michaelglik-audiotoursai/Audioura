"""work_story_searcher.py — SQ-S1 (query synthesis) + SQ-S2 (SERP + source tier classification).

Part of Story Quality pipeline. Deterministic query generation + bounded SERP search
+ source reputation classification. Never fails the tour — degrades gracefully.
"""
import json, os, re, time, unicodedata, urllib.request, urllib.parse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

# --- Configuration ---
RULES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'source_tier_rules.json')
GENERATION_TIER = os.environ.get('GENERATION_TIER', 'plus')
SERP_API_KEY = os.environ.get('SERP_API_KEY', '')
SERP_PROVIDER = os.environ.get('SERP_PROVIDER', 'serper')
CORPUS_VERSION = 1

# Load rules
with open(RULES_PATH, 'r') as f:
    _RULES = json.load(f)


# --- DB connection (matches venue_resolver.py pattern) ---
def _get_db_connection():
    import psycopg2
    db_url = os.environ.get('VENUE_CACHE_DB_URL',
             os.environ.get('DATABASE_URL', 'postgresql://admin:password123@postgres-2:5432/audiotours'))
    if '@localhost:' in db_url:
        db_url = db_url.replace('@localhost:', '@postgres-2:')
    if 'admin:admin@' in db_url and 'postgres-2' in db_url:
        db_url = db_url.replace('admin:admin@', 'admin:password123@')
    conn = psycopg2.connect(db_url, connect_timeout=5)
    return conn


# --- work_key normalization (R7) ---
def _normalize_part(text: str) -> str:
    """Normalize a single part (title or artist) for cache key."""
    # Strip diacritics
    nfkd = unicodedata.normalize('NFKD', text)
    ascii_text = ''.join(c for c in nfkd if not unicodedata.combining(c))
    # Lowercase, strip punctuation, collapse whitespace
    ascii_text = ascii_text.lower()
    ascii_text = re.sub(r'[^\w\s]', '', ascii_text)
    ascii_text = re.sub(r'\s+', ' ', ascii_text).strip()
    return ascii_text


def normalize_work_key(title: str, artist: str = '') -> str:
    """Normalize a work key for cache lookup. Deterministic: lowercase, strip diacritics/punctuation, collapse whitespace."""
    title_norm = _normalize_part(title)
    if artist:
        artist_norm = _normalize_part(artist)
        return f"{title_norm}|||{artist_norm}"
    return title_norm


# --- Domain normalization ---
def normalize_domain(url: str) -> str:
    """Extract registrable domain from URL (strip www/scheme, lowercase)."""
    domain = url.lower()
    for prefix in ('https://', 'http://', 'www.'):
        if domain.startswith(prefix):
            domain = domain[len(prefix):]
    domain = domain.split('/')[0].split('?')[0]
    return domain


# --- Source Tier Classification (R1 corrected: Reject first, then tier) ---
def classify_domain(domain: str, domain_cache: dict = None) -> str:
    """Classify a domain into tier1/tier2/tier3/reject.

    Evaluation order (R1): reject signals FIRST, then tier grant.
    SPARQL timeout/failure → tier3 (leads-only), logged.
    """
    domain = normalize_domain(domain) if '/' in domain else domain.lower()

    # Step 1: Reject check FIRST (R1b)
    if domain in _RULES.get('reject_photo_hosts', []):
        return 'reject'
    if domain in _RULES.get('reject_satire_domains', []):
        return 'reject'
    # Known commerce/SEO patterns (extensible)
    _commerce_patterns = ['shop.', 'store.', 'buy.', 'prints.', 'poster']
    if any(p in domain for p in _commerce_patterns):
        return 'reject'

    # Step 2: Wikipedia/mirrors → tier1
    if domain in ('en.wikipedia.org', 'wikipedia.org', 'britannica.com'):
        return 'tier1'
    if domain in _RULES.get('wikipedia_mirrors', []):
        return 'tier1'  # syndication of wikipedia — T1 but counts as same source

    # Step 3: Tier 2 news/journalism check
    if domain in _RULES.get('tier2_news_domains', []):
        return 'tier2'

    # Step 4: TLD-based institutional signals
    if domain.endswith('.edu') or domain.endswith('.gov') or domain.endswith('.museum'):
        return 'tier1'
    if domain.endswith('.gouv.fr') or domain.endswith('.ac.uk'):
        return 'tier1'

    # Step 5: Wikidata P856 check with class constraint (R1a)
    # Check domain_cache first
    if domain_cache and domain in domain_cache:
        return domain_cache[domain]

    # Try SPARQL (P856 + P31 class constraint)
    tier = _check_wikidata_p856(domain)
    if domain_cache is not None:
        domain_cache[domain] = tier
    return tier


def _check_wikidata_p856(domain: str) -> str:
    """Check Wikidata for institutional classification via P856 + P31 class constraint.
    On timeout/failure → 'tier3' (leads-only, logged). Never 'tier1', never skipped."""
    institutional_classes = _RULES.get('tier1_institutional_classes', [])
    if not institutional_classes:
        return 'tier3'

    # Build SPARQL ASK with P31/P279* class constraint (R1a)
    classes_values = ' '.join(f'wd:{qid}' for qid in institutional_classes)
    sparql = f"""ASK {{
        ?entity wdt:P856 ?url .
        ?entity wdt:P31/wdt:P279* ?class .
        VALUES ?class {{ {classes_values} }}
        FILTER(CONTAINS(LCASE(STR(?url)), "{domain}"))
    }}"""

    try:
        encoded = urllib.parse.urlencode({'query': sparql, 'format': 'json'})
        req = urllib.request.Request(
            f"https://query.wikidata.org/sparql?{encoded}",
            headers={'User-Agent': 'AudiouraBot/1.0 (story-quality-pipeline)'}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            if data.get('boolean', False):
                return 'tier1'
            return 'tier3'
    except Exception as e:
        print(f"  [SQ-S2] Wikidata P856 check failed for {domain}: {e}")
        return 'tier3'  # Fail → tier3, never tier1, never skipped


# --- Query Synthesis (SQ-S1) ---
def synthesize_queries(stop: Dict, tour_type: str = 'contained') -> List[str]:
    """Generate deterministic base queries for a stop.

    Parameters: stop dict with keys: canonical_title, artist, venue_city, venue_lang
    Returns: list of query strings (2-3 per stop)
    """
    title = stop.get('canonical_title', '')
    artist = stop.get('artist', '')
    city = stop.get('venue_city', '')

    queries = []
    if tour_type == 'contained':
        # Museum/contained tours: query by work title + artist
        queries.append(f'"{title}" {artist} story behind')
        queries.append(f'"{title}" {artist} history making')
        if artist:
            queries.append(f'"{title}" {artist} controversy')
    else:
        # Distributed/walking tours: query by POI + city
        queries.append(f'"{title}" {city} history story behind')
        queries.append(f'"{title}" {city} who walked here famous visitors')
        queries.append(f'"{title}" {city} controversy')

    return queries


# --- SERP Execution ---
def _serp_search(query: str) -> Tuple[List[Dict], float]:
    """Execute a single SERP query via Serper.dev. Returns (results, latency_ms).
    On failure → ([], latency_ms) + logged."""
    if not SERP_API_KEY:
        print(f"  [SQ-S2] No SERP_API_KEY — skipping query")
        return [], 0.0

    start = time.time()
    try:
        data = json.dumps({"q": query, "num": 8}).encode()
        req = urllib.request.Request(
            "https://google.serper.dev/search",
            data=data,
            headers={"X-API-KEY": SERP_API_KEY, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
            organic = body.get("organic", [])
            latency = (time.time() - start) * 1000
            results = [{'title': r.get('title', ''), 'url': r.get('link', ''), 'snippet': r.get('snippet', '')}
                      for r in organic]
            return results, latency
    except Exception as e:
        latency = (time.time() - start) * 1000
        print(f"  [SQ-S2] SERP query failed: {e} (query: {query[:50]})")
        return [], latency


# --- Main search function ---
def search_stories_for_stop(stop: Dict, tour_type: str = 'contained',
                            generation_tier: str = None) -> Dict:
    """Run the full SQ-S1 + SQ-S2 pipeline for one stop.

    Returns a dict with:
      - results: list of {url, title, snippet, domain, tier}
      - query_log: list of {query, result_count, latency_ms}
      - story_mining_status: 'ok' | 'degraded_serp_fail' | 'cache_only'
      - total_queries: int
      - estimated_cost: float (USD)
    """
    tier = generation_tier or GENERATION_TIER
    query_cap = _RULES.get('query_caps', {}).get(tier, 40)

    # R6: free tier = ZERO SERP calls (enforced by construction)
    if tier == 'free' or query_cap == 0:
        return {
            'results': [],
            'query_log': [],
            'story_mining_status': 'cache_only',
            'total_queries': 0,
            'estimated_cost': 0.0,
        }

    queries = synthesize_queries(stop, tour_type)

    all_results = []
    query_log = []
    total_queries = 0
    serp_failures = 0
    domain_cache = {}  # Per-tour domain tier cache

    for query in queries:
        if total_queries >= query_cap:
            print(f"  [SQ-S2] Query cap ({query_cap}) reached — degrading gracefully")
            break

        results, latency = _serp_search(query)
        total_queries += 1
        query_log.append({
            'query': query,
            'result_count': len(results),
            'latency_ms': round(latency, 1),
        })

        if not results:
            serp_failures += 1

        # Classify each result
        for r in results:
            domain = normalize_domain(r['url'])
            tier_class = classify_domain(domain, domain_cache)
            r['domain'] = domain
            r['tier'] = tier_class
            if tier_class != 'reject':
                all_results.append(r)

    # Determine mining status (R5)
    if serp_failures == len(queries) and len(queries) > 0:
        status = 'degraded_serp_fail'
    else:
        status = 'ok'

    # Cost estimate: Serper ~$1/1000 queries
    estimated_cost = total_queries * 0.001

    return {
        'results': all_results,
        'query_log': query_log,
        'story_mining_status': status,
        'total_queries': total_queries,
        'estimated_cost': estimated_cost,
    }


def search_stories_for_tour(stops: List[Dict], tour_type: str = 'contained',
                            generation_tier: str = None) -> Dict:
    """Run story search for all stops in a tour. Aggregates query counts + cost.

    Returns:
      - per_stop: list of per-stop results
      - serper_queries_total: int
      - serper_cost_estimate: float
      - story_mining_status: 'ok' | 'degraded_serp_fail' | 'cache_only'
    """
    tier = generation_tier or GENERATION_TIER
    per_stop = []
    total_queries = 0
    total_cost = 0.0
    any_degraded = False
    all_cache_only = True

    for stop in stops:
        result = search_stories_for_stop(stop, tour_type, tier)
        per_stop.append(result)
        total_queries += result['total_queries']
        total_cost += result['estimated_cost']
        if result['story_mining_status'] == 'degraded_serp_fail':
            any_degraded = True
        if result['story_mining_status'] != 'cache_only':
            all_cache_only = False

    if all_cache_only:
        overall_status = 'cache_only'
    elif any_degraded:
        overall_status = 'degraded_serp_fail'
    else:
        overall_status = 'ok'

    return {
        'per_stop': per_stop,
        'serper_queries_total': total_queries,
        'serper_cost_estimate': round(total_cost, 4),
        'story_mining_status': overall_status,
    }
