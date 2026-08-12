"""work_story_searcher.py — SQ-S1 (query synthesis) + SQ-S2 (SERP + source tier classification).

Part of Story Quality pipeline. Deterministic query generation + bounded SERP search
+ source reputation classification. Never fails the tour — degrades gracefully.
"""
import json, os, re, time, unicodedata, urllib.request, urllib.parse, urllib.error
import concurrent.futures
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

# --- Configuration ---
RULES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'source_tier_rules.json')
GENERATION_TIER = os.environ.get('GENERATION_TIER', 'plus')
SERP_API_KEY = os.environ.get('SERP_API_KEY', '')
SERP_PROVIDER = os.environ.get('SERP_PROVIDER', 'serper')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
CORPUS_VERSION = 1

# --- LOCAL-441: Concurrent lookup configuration ---
EXTERNAL_LOOKUP_BATCH_BUDGET_SECONDS = 20.0  # Wall-budget for a batch of P856 lookups
EXTERNAL_LOOKUP_POOL_SIZE = 10  # Thread pool size for concurrent lookups
EXTERNAL_LOOKUP_PER_TIMEOUT = 8  # Per-lookup timeout (seconds), unchanged from original

# Module-level domain tier cache — persists across calls within the same process/run
_MODULE_DOMAIN_CACHE: Dict[str, str] = {}

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
def _classify_domain_quick(domain: str) -> Optional[str]:
    """[LOCAL-441] Fast-path classification without P856 network call.

    Returns the tier if determinable from rules alone, or None if P856 is needed.
    Same logic as classify_domain steps 1-4, extracted for batch pre-classification.
    """
    domain = normalize_domain(domain) if '/' in domain else domain.lower()

    # Step 1: Reject check FIRST (R1b)
    if domain in _RULES.get('reject_photo_hosts', []):
        return 'reject'
    if domain in _RULES.get('reject_satire_domains', []):
        return 'reject'
    _commerce_patterns = ['shop.', 'store.', 'buy.', 'prints.', 'poster']
    if any(p in domain for p in _commerce_patterns):
        return 'reject'

    # Step 1b: Platform/UGC hosts → reject (F2: before P856)
    if domain in _RULES.get('reject_platforms', []):
        return 'reject'
    for platform in _RULES.get('reject_platforms', []):
        if domain.endswith('.' + platform):
            return 'reject'

    # Step 2: Wikipedia/mirrors → tier1
    if domain in ('en.wikipedia.org', 'wikipedia.org', 'britannica.com'):
        return 'tier1'
    if domain in _RULES.get('wikipedia_mirrors', []):
        return 'tier1'

    # Step 3: Tier 2 news/journalism check
    if domain in _RULES.get('tier2_news_domains', []):
        return 'tier2'

    # Step 4: TLD-based institutional signals
    if domain.endswith('.edu') or domain.endswith('.gov') or domain.endswith('.museum'):
        return 'tier1'
    if domain.endswith('.gouv.fr') or domain.endswith('.ac.uk'):
        return 'tier1'

    # Step 4b: Institutional domain seed
    if domain in _RULES.get('institutional_domain_seed', []):
        return 'tier1'

    # Cannot determine without P856 lookup
    return None


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

    # Step 1b: Platform/UGC hosts → reject (F2: before P856)
    if domain in _RULES.get('reject_platforms', []):
        return 'reject'
    # Also check if domain is a subdomain of a platform
    for platform in _RULES.get('reject_platforms', []):
        if domain.endswith('.' + platform):
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

    # Step 4b: Institutional domain seed (cache-equivalent, data not class rule)
    if domain in _RULES.get('institutional_domain_seed', []):
        return 'tier1'

    # Step 5: Wikidata P856 check with class constraint (R1a)
    # Check domain_cache first
    if domain_cache and domain in domain_cache:
        return domain_cache[domain]

    # [LOCAL-441] Check module-level cache (persists across calls within a run)
    if domain in _MODULE_DOMAIN_CACHE:
        result = _MODULE_DOMAIN_CACHE[domain]
        if domain_cache is not None:
            domain_cache[domain] = result
        return result

    # Try SPARQL (P856 + P31 class constraint)
    tier = _check_wikidata_p856(domain)
    if domain_cache is not None:
        domain_cache[domain] = tier
    _MODULE_DOMAIN_CACHE[domain] = tier  # [LOCAL-441] Persist for future calls
    return tier


def _check_wikidata_p856(domain: str) -> str:
    """Check Wikidata for institutional classification via P856 + P31 class constraint.
    On timeout/failure → 'tier3' (leads-only, logged). Never 'tier1', never skipped."""
    institutional_classes = _RULES.get('tier1_institutional_classes', [])
    if not institutional_classes:
        return 'tier3'

    # Build SPARQL ASK with P31/P279* class constraint (R1a)
    classes_values = ' '.join(f'wd:{qid}' for qid in institutional_classes)
    # F2: Compare registrable HOST for equality, not substring
    sparql = f"""ASK {{
        ?entity wdt:P856 ?url .
        ?entity wdt:P31/wdt:P279* ?class .
        VALUES ?class {{ {classes_values} }}
        FILTER(LCASE(STR(?url)) = "https://{domain}/" || 
               LCASE(STR(?url)) = "http://{domain}/" ||
               CONTAINS(LCASE(STR(?url)), "://{domain}/") ||
               CONTAINS(LCASE(STR(?url)), "://www.{domain}/"))
    }}"""

    try:
        encoded = urllib.parse.urlencode({'query': sparql, 'format': 'json'})
        req = urllib.request.Request(
            f"https://query.wikidata.org/sparql?{encoded}",
            headers={'User-Agent': 'AudiouraBot/1.0 (story-quality-pipeline)'}
        )
        with urllib.request.urlopen(req, timeout=EXTERNAL_LOOKUP_PER_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
            if data.get('boolean', False):
                return 'tier1'
            return 'tier3'
    except Exception as e:
        print(f"  [SQ-S2] Wikidata P856 check failed for {domain}: {e}")
        return 'tier3'  # Fail → tier3, never tier1, never skipped


def batch_check_wikidata_p856(domains: List[str], budget_seconds: float = None,
                               pool_size: int = None) -> Dict[str, str]:
    """[LOCAL-441] Concurrently check multiple domains against Wikidata P856.

    Runs lookups in parallel with a global wall-budget. When the budget expires,
    unanswered lookups are treated as tier3 (same as timeout today).

    Args:
        domains: list of unique domains to check (already filtered for cache hits)
        budget_seconds: wall-clock budget for the whole batch (default: module constant)
        pool_size: thread pool size (default: module constant)

    Returns:
        dict mapping domain → tier result ('tier1' or 'tier3')
    """
    if budget_seconds is None:
        budget_seconds = EXTERNAL_LOOKUP_BATCH_BUDGET_SECONDS
    if pool_size is None:
        pool_size = EXTERNAL_LOOKUP_POOL_SIZE

    if not domains:
        return {}

    results: Dict[str, str] = {}
    batch_start = time.time()

    print(f"  [LOCAL-441] Batch P856 check: {len(domains)} domains, "
          f"budget={budget_seconds}s, pool={pool_size}")

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=pool_size)
    try:
        future_to_domain = {
            executor.submit(_check_wikidata_p856, domain): domain
            for domain in domains
        }

        # Wait with the global budget as the timeout
        remaining = budget_seconds - (time.time() - batch_start)
        done, not_done = concurrent.futures.wait(
            future_to_domain.keys(),
            timeout=max(0, remaining),
            return_when=concurrent.futures.ALL_COMPLETED
        )

        # Collect completed results
        for future in done:
            domain = future_to_domain[future]
            try:
                results[domain] = future.result(timeout=0)
            except Exception as e:
                print(f"  [LOCAL-441] P856 exception for {domain}: {e}")
                results[domain] = 'tier3'

        # Budget-expired lookups → tier3 (same treatment as timeout)
        for future in not_done:
            domain = future_to_domain[future]
            print(f"  [LOCAL-441] P856 budget-expired for {domain} → tier3")
            results[domain] = 'tier3'
            future.cancel()
    finally:
        # shutdown(wait=False, cancel_futures=True) — don't block on still-running threads
        executor.shutdown(wait=False, cancel_futures=True)

    elapsed = time.time() - batch_start
    resolved = sum(1 for v in results.values() if v == 'tier1')
    expired = len(not_done)
    print(f"  [LOCAL-441] Batch complete: {elapsed:.1f}s, "
          f"{resolved} tier1, {len(results) - resolved} tier3, "
          f"{expired} budget-expired")

    return results


# --- Query Synthesis (SQ-S1) ---
def _strip_trailing_numeral(title: str) -> Optional[str]:
    """Strip trailing Roman or Arabic numeral from a title to get cycle/series-level form.
    Returns the stripped form if different from original, else None.
    E.g. "Le Cantique des Cantiques IV" → "Le Cantique des Cantiques"
         "Blue Nude II" → "Blue Nude"
         "Landscape 3" → "Landscape"
    """
    # Roman numeral pattern (I, II, III, IV, V, VI, VII, VIII, IX, X, etc.)
    stripped = re.sub(r'\s+(?:[IVXLCDM]+|[0-9]+)\s*$', '', title, flags=re.IGNORECASE).strip()
    if stripped and stripped != title:
        return stripped
    return None


def _is_biography_only(snippet_text: str, snippet_title: str = '') -> bool:
    """[LOCAL-406] Detect generic artist biography snippets.

    A snippet is biography-only if it is dominated by birth/death, nationality,
    and "was a <profession>" patterns WITHOUT mentioning an event tied to the work,
    collaborators, or the livre d'artiste form.

    Returns True if the snippet should be rejected for story purposes.
    """
    text = f"{snippet_title} {snippet_text}".lower()

    # Biography signals
    _BIO_SIGNALS = [
        r'\bborn\b.*\d{4}',
        r'\(\d{4}\s*[-–—]\s*\d{4}\)',
        r'\bwas\s+(?:a|an)\s+(?:spanish|catalan|french|italian|german|american|dutch|'
        r'belgian|swiss|austrian|russian|mexican|brazilian|british|'
        r'painter|sculptor|printmaker|artist|lithographer|ceramicist|'
        r'surrealist|cubist|abstract)\b',
        r'\bnationality\b',
        r'\bgrew\s+up\b',
        r'\bfamily\s+of\b',
        r'\bchildhood\b',
        r'\bearly\s+(?:life|years|career)\b',
    ]

    bio_signal_count = sum(1 for pat in _BIO_SIGNALS if re.search(pat, text))

    # Work/collaborator signals that RESCUE a biography snippet
    _WORK_SIGNALS = [
        r'\blivre[s]?\s+d[\'\u2019]artiste\b',
        r'\blithograph(?:s|y|ie)?\b',
        r'\bpublish(?:ed|er|ing)\b',
        r'\bprint(?:ed|er|ing|s)\b',
        r'\bedition\b',
        r'\bworkshop\b',
        r'\batelier\b',
        r'\bcollection\b',
        r'\bdonat(?:ed|ion|or)\b',
        r'\bcommission(?:ed)?\b',
        r'\bcollaborat(?:ed|ion|or)\b',
        r'\bpatron(?:age)?\b',
        r'\bexhibit(?:ed|ion)\b',
    ]

    work_signal_count = sum(1 for pat in _WORK_SIGNALS if re.search(pat, text))

    # Reject if: ≥2 biography signals AND 0 work signals
    if bio_signal_count >= 2 and work_signal_count == 0:
        return True

    return False


def synthesize_queries(stop: Dict, tour_type: str = 'contained') -> List[str]:
    """[LOCAL-406] Generate deterministic base queries for a stop.

    Parameters: stop dict with keys: canonical_title, local_title, artist,
        venue_city, venue_lang, publisher, collaborator, credit_line
    Returns: list of query strings — targeted at the WORK and its collaborators,
        not just the artist biography.

    Design (D335-D336): queries must be built around the work and the people
    who made it happen. Four targeted queries beat twenty generic ones.
    """
    title = stop.get('canonical_title', '')
    local_title = stop.get('local_title', '')
    artist = stop.get('artist', '')
    city = stop.get('venue_city', '')
    lang = stop.get('venue_lang', 'en')
    publisher = (stop.get('publisher') or '').strip()
    collaborator = (stop.get('collaborator') or '').strip()
    credit_line = (stop.get('credit_line') or '').strip()

    # [LOCAL-406] Extract donor and printer from credit_line if not explicit
    donor = (stop.get('donor') or '').strip()
    printer = (stop.get('printer') or '').strip()

    if not donor and credit_line:
        # "Gift of Boris Fridman" → "Boris Fridman"
        _donor_match = re.search(
            r'(?:gift\s+of|donated\s+by|bequest\s+of|given\s+by)\s+(.+?)(?:\s+to\b|[,;.]|$)',
            credit_line, re.IGNORECASE)
        if _donor_match:
            donor = _donor_match.group(1).strip()

    if not printer and credit_line:
        _printer_match = re.search(
            r'(?:printed\s+by|imprimé\s+par)\s+(.+?)(?:[,;.]|\s+(?:for|pour)\b|$)',
            credit_line, re.IGNORECASE)
        if _printer_match:
            printer = _printer_match.group(1).strip()

    queries = []

    # [LOCAL-415] Venue name for contextualized queries
    venue_name = (stop.get('venue_name') or '').strip()

    # [LOCAL-423] Exhibition name for Michael's query shape (Step 2)
    exhibition_name = (stop.get('exhibition_name') or '').strip()

    # [LOCAL-415] Medium detection — needed for query selection below
    _medium = (stop.get('medium') or '').lower()
    _is_book_form = any(kw in _medium for kw in ('lithograph', 'book', 'etching', 'aquatint', 'woodcut'))
    if not _is_book_form and credit_line:
        _is_book_form = any(kw in credit_line.lower() for kw in ('lithograph', 'book', 'published'))

    # [LOCAL-423] Michael's query shape (Step 2):
    # "What story can be told to visitors of {exhibition} about {work}, {credit_line}?"
    # This framing is materially different from querying the work title alone.
    # It targets VISITOR-FACING stories, not encyclopedic facts.
    if exhibition_name and title:
        _423_credit_short = credit_line[:100] if credit_line else ''
        queries.append(f'"{title}" {artist} story visitors {exhibition_name}')
        if _423_credit_short:
            queries.append(f'"{title}" {_423_credit_short[:50]} history story')

    # ── PRIMARY: The work itself (quoted title + artist) ──
    if tour_type == 'contained':
        if artist:
            queries.append(f'"{title}" {artist}')
            queries.append(f'"{title}" history')
        else:
            # [LOCAL-415] No artist: contextualize with venue to avoid generic results
            # "Adam and Eve" alone returns biblical content; "Adam and Eve" Museum of Fine Arts
            # returns the actual artwork/exhibition.
            if venue_name:
                queries.append(f'"{title}" {venue_name}')
                queries.append(f'"{title}" {venue_name} history')
            else:
                queries.append(f'"{title}" art museum')
                queries.append(f'"{title}" exhibition history')
        # [LOCAL-415] Only add "edition lithographs" query when medium suggests prints
        if _is_book_form:
            queries.append(f'"{title}" edition lithographs')
    else:
        queries.append(f'"{title}" {city} history')
        queries.append(f'"{title}" {city} story behind')

    # ── COLLABORATOR QUERIES: publisher–artist, printer, donor ──
    if publisher and artist:
        # e.g. "Louis Broder Miró"
        queries.append(f'{publisher} {artist}')
    if printer:
        # e.g. "Mourlot Frères workshop history"
        queries.append(f'{printer} workshop history')
    if donor:
        # e.g. "Boris Fridman collection livres d'artiste"
        queries.append(f'{donor} collection')
        # [LOCAL-421] Story query: who is the donor, why did they give it
        queries.append(f'{donor} "{title}" donation why')
    if collaborator and artist:
        queries.append(f'{collaborator} {artist}')
        # [LOCAL-421] Story query: why this collaboration happened
        queries.append(f'{collaborator} {artist} relationship why collaborated')

    # ── [LOCAL-421] STORY-TYPED QUERIES: relationships and consequences ──
    # These target the WHY and the CONSEQUENCE, not just the WHO and WHAT.
    # A fact says "printed by Mourlot". A story says "Mourlot was the only
    # printer in Paris who could handle chromolithography at this scale."
    if artist and title:
        # Why the artist chose this subject / collaborator
        queries.append(f'{artist} "{title}" why created motivation')
    if publisher and printer:
        # Publisher–printer relationship (e.g. why Broder chose Mourlot)
        queries.append(f'{publisher} {printer} collaboration')
    if collaborator and not publisher:
        # Writer–artist: why the writer's text was chosen
        queries.append(f'"{title}" {collaborator} why chose subject')

    # ── FORM QUERY: livre d'artiste tied to artist ──
    # Only when medium/credit_line suggests this IS a livre d'artiste
    # (_medium and _is_book_form already computed above for query selection)
    if _is_book_form and artist:
        queries.append(f'livre d\'artiste {artist}')

    # W4: Query granularity — also query the series/cycle-level title
    series_title = _strip_trailing_numeral(title)
    if series_title:
        if tour_type == 'contained':
            queries.append(f'"{series_title}" {artist} history')
        else:
            queries.append(f'"{series_title}" {city} history')

    # W5: Title language split — query BOTH canonical and local_title if different
    if local_title and local_title.strip().lower() != title.strip().lower():
        if tour_type == 'contained':
            queries.append(f'"{local_title}" {artist}')
        else:
            queries.append(f'"{local_title}" {city} history')

    # Q3: English title query
    english_title = stop.get('english_title', '')
    if english_title and english_title.strip().lower() != title.strip().lower():
        if tour_type == 'contained':
            queries.append(f'"{english_title}" {artist}')
        else:
            queries.append(f'"{english_title}" {city} history')

    # E1: Composed English-series query
    if english_title:
        english_series = _strip_trailing_numeral(english_title)
        if english_series and english_series.strip().lower() != english_title.strip().lower():
            if tour_type == 'contained':
                queries.append(f'"{english_series}" {artist}')
            else:
                queries.append(f'"{english_series}" {city} history')

    # Localization: add query in venue language if not English
    if lang and lang != 'en':
        _LANG_STORY_TERMS = {'fr': 'histoire', 'it': 'storia', 'es': 'historia', 'de': 'Geschichte'}
        story_term = _LANG_STORY_TERMS.get(lang, 'story')
        queries.append(f'"{title}" {artist} {story_term}')

    # W9: Collection/venue-level provenance queries
    venue_name = stop.get('venue_name', '')
    if venue_name and tour_type == 'contained':
        queries.append(f'{venue_name} {artist} donation history')
        if lang and lang != 'en':
            _LANG_DONATION = {'fr': 'donation', 'it': 'donazione', 'es': 'donación', 'de': 'Schenkung'}
            donation_term = _LANG_DONATION.get(lang, 'donation')
            queries.append(f'{venue_name} {artist} {donation_term}')

    return queries


def synthesize_class_targeted_queries(stop: Dict, tour_type: str = 'contained',
                                       category: str = '') -> Dict[str, List[str]]:
    """[LOCAL-37] Generate queries targeted at each of the three classes.
    
    Extends synthesize_queries with class-specific query strategies:
    - Details: material, dimensions, technique, medium
    - Historical: category-level origin, era, evolution (NOT object-specific)
    - Social: people, commissions, reception, controversy
    
    Args:
        stop: dict with canonical_title, artist, venue_city, etc.
        tour_type: 'contained' or 'distributed'
        category: the object category for Historical-class queries
        
    Returns:
        Dict {"details": [...], "historic": [...], "social": [...]}
    """
    title = stop.get('canonical_title', '') or stop.get('name', '')
    artist = stop.get('artist', '')
    city = stop.get('venue_city', '')
    
    queries = {"details": [], "historic": [], "social": []}
    
    # ── Details: physical properties of the entity ──
    if title:
        queries["details"].append(f'"{title}" material dimensions technique medium')
        if artist:
            queries["details"].append(f'"{title}" {artist} technique materials')
    
    # ── Historical: CATEGORY level (the key insight) ──
    if category:
        queries["historic"].append(f'"{category}" origin era history evolution')
        queries["historic"].append(f'"{category}" ancient tradition cultural significance')
    if title:
        queries["historic"].append(f'"{title}" history period era style')
    
    # ── Social: the people ──
    if title:
        queries["social"].append(f'"{title}" commissioned owned reception provenance')
    if artist:
        queries["social"].append(f'"{artist}" "{title}" patron collector who')
        queries["social"].append(f'"{artist}" controversy relationship circle')
    elif title:
        queries["social"].append(f'"{title}" who made commissioned owned donated')
    
    return queries


# --- LLM Refinement Round (SQ-S1, F5) ---
def _refine_queries_llm(stop: Dict, tier3_leads: List[str], canonical_title: str) -> List[str]:
    """Bounded LLM refinement: propose 1-2 queries when T1/T2 yield is thin.
    Hard rule: every refined query MUST contain the exact canonical title."""
    if not OPENAI_API_KEY or not tier3_leads:
        return []

    prompt = f"""Given these search snippets about "{canonical_title}":
{chr(10).join(f'- {s}' for s in tier3_leads[:5])}

Propose 1-2 refined search queries that might find more authoritative sources.
Each query MUST contain the exact text: "{canonical_title}"
Return JSON array of query strings only."""

    try:
        data = json.dumps({
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        }).encode()
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=data,
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
            content = body['choices'][0]['message']['content']
            parsed = json.loads(content)
            queries = parsed.get('queries', parsed) if isinstance(parsed, dict) else parsed
            if not isinstance(queries, list):
                return []
            # Hard rule: title containment enforced
            valid = [q for q in queries if canonical_title.lower() in q.lower()]
            return valid[:2]
    except Exception as e:
        print(f"  [SQ-S1] Refinement LLM failed: {e}")
        return []


# --- W7: Fact-Targeted Refinement ---
# High-value element types that warrant a second search pass when single-source
_HIGH_VALUE_TYPES = {'dedication', 'origin', 'turning_point', 'provenance'}


def synthesize_fact_targeted_queries(stop: Dict, reported_elements: List[Dict]) -> List[str]:
    """Generate fact-targeted queries when high-value elements are single-source (reported).

    W7 fix: triggers refinement when a high-value element (dedication/origin/turning_point)
    is 'reported' (single-source), using the element's people/dates for a targeted query.

    Parameters:
      - stop: dict with canonical_title, artist
      - reported_elements: list of scored elements with corroboration_status == 'reported'
        and type in _HIGH_VALUE_TYPES

    Returns: list of fact-targeted query strings (0-2)
    """
    title = stop.get('canonical_title', '')
    artist = stop.get('artist', '')
    queries = []

    for elem in reported_elements:
        if elem.get('type') not in _HIGH_VALUE_TYPES:
            continue
        if elem.get('corroboration_status') != 'reported':
            continue

        # Build a fact-targeted query from the element's specifics
        people = elem.get('people', [])
        dates = elem.get('dates', [])
        elem_type = elem.get('type', '')

        # Use the cycle-level title if available (W4 synergy)
        query_title = _strip_trailing_numeral(title) or title

        # Type-specific query terms
        type_terms = {
            'dedication': 'dedication|donation|donated',
            'origin': 'origin|created|commissioned',
            'turning_point': 'turning point|breakthrough|transformation',
            'provenance': 'donation|provenance|donated|gift',
        }
        type_suffix = type_terms.get(elem_type, '')

        # Assemble: title + artist + key person/date + type hint
        parts = [f'"{query_title}"', artist]
        if people:
            # Q1: Skip any person whose name matches the artist to avoid duplication
            # (people[0] is usually the artist themselves)
            artist_lower = artist.lower().strip() if artist else ''
            non_artist_people = [p for p in people if p.lower().strip() != artist_lower]
            if non_artist_people:
                parts.append(non_artist_people[0])  # First NON-artist person
        if dates:
            # D5: Only use a date if it appears in the source_sentence (avoid noise dates)
            source_sentence = elem.get('source_sentence', '')
            valid_dates = [d for d in dates if d in source_sentence] if source_sentence else dates
            if valid_dates:
                parts.append(valid_dates[0])  # First date confirmed in source text
        parts.append(type_suffix.split('|')[0])  # Primary type term

        query = ' '.join(p for p in parts if p)
        queries.append(query)

        if len(queries) >= 2:
            break

    return queries


# --- SERP Execution ---
def _serp_search(query: str) -> Tuple[List[Dict], float]:
    """Execute a single SERP query via Serper.dev. Returns (results, latency_ms).
    On failure → ([], latency_ms) + logged with full request/response detail."""
    if not SERP_API_KEY:
        print(f"  [SQ-S2] No SERP_API_KEY — skipping query")
        return [], 0.0

    start = time.time()
    payload = {"q": query, "num": 8}
    try:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
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
    except urllib.error.HTTPError as e:
        latency = (time.time() - start) * 1000
        # [LOCAL-409] Print full request and response body for diagnosis
        response_body = ''
        try:
            response_body = e.read().decode('utf-8', errors='replace')
        except Exception:
            response_body = '<unreadable>'
        print(f"  [SQ-S2] SERP HTTP {e.code}: {e.reason}")
        print(f"  [SQ-S2]   request payload: {json.dumps(payload, ensure_ascii=False)}")
        print(f"  [SQ-S2]   response body:   {response_body[:500]}")
        return [], latency
    except Exception as e:
        latency = (time.time() - start) * 1000
        print(f"  [SQ-S2] SERP query failed: {type(e).__name__}: {e}")
        print(f"  [SQ-S2]   request payload: {json.dumps(payload, ensure_ascii=False)}")
        return [], latency


# --- Main search function ---
def search_stories_for_stop(stop: Dict, tour_type: str = 'contained',
                            generation_tier: str = None,
                            query_budget: int = None) -> Dict:
    """Run the full SQ-S1 + SQ-S2 pipeline for one stop.

    Parameters:
      - stop: dict with canonical_title, artist, venue_city, venue_lang
      - tour_type: 'contained' or 'distributed'
      - generation_tier: 'free', 'plus', or 'max'
      - query_budget: optional remaining tour-level budget (F3). If provided,
        effective cap = min(tier_cap, query_budget).

    Returns a dict with:
      - results: list of {url, title, snippet, domain, tier}
      - query_log: list of {query, result_count, latency_ms}
      - story_mining_status: 'ok' | 'degraded_serp_fail' | 'cache_only'
      - total_queries: int
      - estimated_cost: float (USD)
    """
    tier = generation_tier or GENERATION_TIER
    query_cap = _RULES.get('query_caps', {}).get(tier, 40)

    # F3: If tour-level budget provided, use it as the effective cap
    if query_budget is not None:
        effective_cap = min(query_cap, query_budget)
    else:
        effective_cap = query_cap

    # F4: Cache read — check work_stories BEFORE search (all tiers including free)
    _work_key = normalize_work_key(stop.get('canonical_title', ''), stop.get('artist', ''))
    cached = work_stories_get(_work_key)
    if cached:
        return {
            'results': [],
            'query_log': cached.get('query_log', []),
            'story_mining_status': 'cache_only',
            'total_queries': 0,
            'estimated_cost': 0.0,
            'cached_elements': cached.get('elements', []),
        }

    # R6: free tier = ZERO SERP calls (enforced by construction)
    if tier == 'free' or effective_cap <= 0:
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
    domain_cache = dict(_MODULE_DOMAIN_CACHE)  # Start with module-level cache (per-host across runs)

    # [LOCAL-441] Phase 1: Execute all SERP queries, collect raw results
    raw_serp_results = []  # list of (result_dict, query_index)

    for query in queries:
        if total_queries >= effective_cap:
            print(f"  [SQ-S2] Query cap ({effective_cap}) reached — degrading gracefully")
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

        for r in results:
            r['domain'] = normalize_domain(r['url'])
            raw_serp_results.append(r)

    # [LOCAL-441] Phase 2: Identify domains needing P856 lookup (not resolvable from rules/cache)
    domains_needing_p856 = set()
    for r in raw_serp_results:
        domain = r['domain']
        if domain in domain_cache:
            continue  # Already resolved
        # Check if resolvable without P856 (reject, tier1, tier2 rules)
        quick_tier = _classify_domain_quick(domain)
        if quick_tier is not None:
            domain_cache[domain] = quick_tier
        else:
            domains_needing_p856.add(domain)

    # [LOCAL-441] Phase 3: Batch concurrent P856 lookups with wall-budget
    if domains_needing_p856:
        p856_results = batch_check_wikidata_p856(list(domains_needing_p856))
        domain_cache.update(p856_results)
        _MODULE_DOMAIN_CACHE.update(p856_results)  # Persist for future calls in this run

    # [LOCAL-441] Phase 4: Classify all results using the now-populated cache
    for r in raw_serp_results:
        domain = r['domain']
        tier_class = domain_cache.get(domain, 'tier3')
        r['tier'] = tier_class
        if tier_class != 'reject':
            # [LOCAL-406] Reject biography-only snippets
            if _is_biography_only(r.get('snippet', ''), r.get('title', '')):
                print(f"  [LOCAL-406] snippet rejected: biography-only '{r.get('title', '')[:60]}'")
                continue
            all_results.append(r)

    # SQ-S1 refinement round (F5): if T1/T2 yield < 2, try refined queries
    t1_t2_count = sum(1 for r in all_results if r.get('tier') in ('tier1', 'tier2'))
    if t1_t2_count < 2 and total_queries < effective_cap:
        tier3_snippets = [r.get('snippet', '') for r in all_results if r.get('tier') == 'tier3'][:5]
        refined = _refine_queries_llm(stop, tier3_snippets, stop.get('canonical_title', ''))
        for query in refined:
            if total_queries >= effective_cap:
                break
            results, latency = _serp_search(query)
            total_queries += 1
            query_log.append({'query': query, 'result_count': len(results), 'latency_ms': round(latency, 1), 'refinement': True})
            if not results:
                serp_failures += 1
            for r in results:
                domain = normalize_domain(r['url'])
                r['domain'] = domain
                # Use cache or quick-classify; only P856 if truly unknown
                if domain not in domain_cache:
                    quick_tier = _classify_domain_quick(domain)
                    if quick_tier is not None:
                        domain_cache[domain] = quick_tier
                    else:
                        # Single lookup — acceptable here as refinement is rare
                        tier_result = _check_wikidata_p856(domain)
                        domain_cache[domain] = tier_result
                        _MODULE_DOMAIN_CACHE[domain] = tier_result
                tier_class = domain_cache.get(domain, 'tier3')
                r['tier'] = tier_class
                if tier_class != 'reject':
                    # [LOCAL-406] Reject biography-only snippets
                    if _is_biography_only(r.get('snippet', ''), r.get('title', '')):
                        print(f"  [LOCAL-406] snippet rejected: biography-only '{r.get('title', '')[:60]}'")
                        continue
                    all_results.append(r)

    # Determine mining status (R5)
    if serp_failures == len(queries) and len(queries) > 0:
        status = 'degraded_serp_fail'
    else:
        status = 'ok'

    # Cost estimate: Serper ~$1/1000 queries
    from cost_rates import search_cost
    estimated_cost = search_cost(total_queries)

    return {
        'results': all_results,
        'query_log': query_log,
        'story_mining_status': status,
        'total_queries': total_queries,
        'estimated_cost': estimated_cost,
    }


def execute_fact_refinement(fact_queries: List[str], existing_results: List[Dict],
                            query_budget_remaining: int, domain_cache: dict = None) -> Dict:
    """W7 orchestration: execute fact-targeted queries from extraction feedback.
    
    Called AFTER extract_and_score_stop returns fact_refinement_queries.
    One bounded round, within remaining tour budget. Results classified and returned
    for a second extraction pass.
    
    Parameters:
      - fact_queries: list of fact-targeted query strings from synthesize_fact_targeted_queries
      - existing_results: results already fetched (to avoid re-fetching same URLs)
      - query_budget_remaining: queries still available within tour budget
      - domain_cache: shared domain tier cache
    
    Returns:
      - new_results: classified results from fact-targeted queries (excluding already-seen URLs)
      - query_log: log entries for the fact-targeted queries
      - queries_used: number of queries consumed
    """
    if not fact_queries or query_budget_remaining <= 0:
        return {'new_results': [], 'query_log': [], 'queries_used': 0}

    if domain_cache is None:
        domain_cache = {}

    existing_urls = {r.get('url', '') for r in existing_results}
    new_results = []
    query_log = []
    queries_used = 0

    for query in fact_queries:
        if queries_used >= query_budget_remaining:
            break
        results, latency = _serp_search(query)
        queries_used += 1
        query_log.append({
            'query': query,
            'result_count': len(results),
            'latency_ms': round(latency, 1),
            'fact_refinement': True,
        })
        for r in results:
            if r.get('url', '') in existing_urls:
                continue  # Skip already-fetched URLs
            domain = normalize_domain(r['url'])
            tier_class = classify_domain(domain, domain_cache)
            r['domain'] = domain
            r['tier'] = tier_class
            if tier_class != 'reject':
                new_results.append(r)
                existing_urls.add(r['url'])

    return {
        'new_results': new_results,
        'query_log': query_log,
        'queries_used': queries_used,
    }


def search_stories_for_tour(stops: List[Dict], tour_type: str = 'contained',
                            generation_tier: str = None) -> Dict:
    """Run story search for all stops in a tour. Aggregates query counts + cost.

    F3: Tour-level aggregate query cap — passes remaining budget to each stop call.

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

    # F3: Tour-level aggregate query cap
    remaining_budget = _RULES.get('query_caps', {}).get(tier, 40)

    for stop in stops:
        if remaining_budget <= 0:
            # Budget exhausted — remaining stops get cache_only
            result = {'results': [], 'query_log': [], 'story_mining_status': 'cache_only', 'total_queries': 0, 'estimated_cost': 0.0}
        else:
            result = search_stories_for_stop(stop, tour_type, tier, query_budget=remaining_budget)
            remaining_budget -= result['total_queries']
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


# --- work_stories cache (SQ-S8, F4) ---
_WORK_STORIES_TABLE_ENSURED = False


def _ensure_work_stories_table(conn):
    global _WORK_STORIES_TABLE_ENSURED
    if _WORK_STORIES_TABLE_ENSURED:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS work_stories (
                    id SERIAL PRIMARY KEY,
                    work_key VARCHAR(512) NOT NULL UNIQUE,
                    work_qid VARCHAR(20),
                    title TEXT NOT NULL,
                    artist TEXT,
                    core_data JSONB NOT NULL,
                    elements_json JSONB,
                    sources_json JSONB,
                    query_log JSONB,
                    core_expires_at TIMESTAMP NOT NULL,
                    elements_expires_at TIMESTAMP NOT NULL,
                    corpus_version INT NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_work_stories_qid ON work_stories(work_qid) WHERE work_qid IS NOT NULL")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_work_stories_expires ON work_stories(elements_expires_at)")
            conn.commit()
        _WORK_STORIES_TABLE_ENSURED = True
    except Exception as e:
        print(f"  [work_stories] Table creation failed: {e}")
        conn.rollback()


def work_stories_get(work_key: str) -> Optional[Dict]:
    """Read cached story elements for a work. Returns None if miss or expired."""
    conn = None
    try:
        conn = _get_db_connection()
        if not conn:
            return None
        _ensure_work_stories_table(conn)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT elements_json, sources_json, query_log, title, artist
                FROM work_stories
                WHERE work_key = %s AND elements_expires_at > NOW() AND corpus_version = %s
            """, (work_key, CORPUS_VERSION))
            row = cur.fetchone()
            if row:
                print(f"  [work_stories] HIT for {work_key[:40]}")
                return {
                    'elements': row[0] if row[0] else [],
                    'sources': row[1] if row[1] else [],
                    'query_log': row[2] if row[2] else [],
                    'title': row[3],
                    'artist': row[4],
                }
            print(f"  [work_stories] MISS for {work_key[:40]}")
            return None
    except Exception as e:
        print(f"  [work_stories] Read error: {e}")
        return None
    finally:
        if conn:
            conn.close()


def work_stories_put(work_key: str, title: str, artist: str, work_qid: str,
                     elements: list, sources: list, query_log: list):
    """Persist mined story elements to cache. Elements TTL ~30d, core 90d."""
    conn = None
    try:
        conn = _get_db_connection()
        if not conn:
            return
        _ensure_work_stories_table(conn)
        elements_expires = datetime.utcnow() + timedelta(days=30)
        core_expires = datetime.utcnow() + timedelta(days=90)
        core_data = json.dumps({'title': title, 'artist': artist, 'work_qid': work_qid})

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO work_stories (work_key, work_qid, title, artist, core_data,
                    elements_json, sources_json, query_log, core_expires_at, elements_expires_at, corpus_version)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (work_key) DO UPDATE SET
                    elements_json = EXCLUDED.elements_json,
                    sources_json = EXCLUDED.sources_json,
                    query_log = EXCLUDED.query_log,
                    elements_expires_at = EXCLUDED.elements_expires_at,
                    updated_at = CURRENT_TIMESTAMP
            """, (work_key, work_qid or None, title, artist, core_data,
                  json.dumps(elements), json.dumps(sources), json.dumps(query_log),
                  core_expires, elements_expires, CORPUS_VERSION))
            conn.commit()
            print(f"  [work_stories] STORED {work_key[:40]} ({len(elements)} elements)")
    except Exception as e:
        print(f"  [work_stories] Write error: {e}")
    finally:
        if conn:
            conn.close()
