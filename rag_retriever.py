"""
RAG Retriever — lightweight knowledge-fetch utilities for Storied tour generation.
No OpenAI calls. Fetches factual summaries from public APIs to ground tour narratives.

LOCAL-447: DB-first path — checks stop_corpus for existing Wikipedia content before
any network call. If the content was previously fetched and stored, we serve it from
the DB with zero network overhead. This implements D403a step 1 (own DB first).

LOCAL-448: Correctness fixes to LOCAL-447:
  - Defect 1: Containment match removed. Only exact accent-folded matching is used.
    The old `topic in title or title in topic` served wrong corpus (fabrication vector).
  - Defect 2: DB connection uses production pattern (psycopg2 + env vars), not tests/.
    Import failure is now logged at WARNING (not silently swallowed).
  - Defect 3: Wayback fallback removed from production chain. LOCAL-447 measurement
    proved it unfit (7% coverage, 9.6s median, wrong articles). Function retained
    for probe/fixture evidence only.
"""
import os
import requests
import logging
import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import quote
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


# ─── LOCAL-447 chain gate (LEAD, D408) ───────────────────────────────────────
#
# The LOCAL-447 retrieval chain is OFF by default. Both new paths are unsafe as
# merged and LEAD verified each failure by running it:
#
#   DB-first  — the containment match (`title in topic or topic in title`) serves
#               the WRONG stop's corpus. Live proof: asking for "The Dream of Saint
#               Ursula by Carpaccio" returned the Musée international d'Art naïf
#               Anatole Jakovsky, logged as a success, 0 network calls, no warning.
#               It is also silently dead in the container — it imports
#               db_connection from tests/, which Dockerfile.generator never copies.
#   Wayback   — LOCAL-447's own measurement rejected it: 7% coverage, median 9.6s
#               (over the 5s budget), both hits the wrong article. Wiring it puts a
#               ~10s stall back on the exact failure path LOCAL-445 made instant.
#
# LOCAL-448 fixes both; this flag is how it gets turned on. Same precedent as
# D400/D402/D404 — unproven wiring does not ride on the default path.

def _l447_enabled() -> bool:
    """True when the LOCAL-447 retrieval chain is explicitly enabled."""
    return os.environ.get('L447_RETRIEVAL_CHAIN', '').strip().lower() in ('1', 'true', 'yes')


# ─── Accent folding (D243) ───────────────────────────────────────────────────

def _strip_accents(text: str) -> str:
    """Remove accents for matching (D243 pattern)."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


# ─── DB-first lookup (LOCAL-447, D403a step 1; LOCAL-448 correctness fix) ────

def _get_db_connection():
    """Get a production DB connection using the same pattern as other services.

    LOCAL-448 (Defect 2): Production code must NOT import from tests/.
    Uses direct psycopg2 with env vars, same as generate_tour_text_service.py.
    Inside Docker: DB_HOST=postgres-2, DB_PORT=5432 (from DATABASE_URL env).
    Outside Docker (host): DB_HOST=localhost, DB_PORT=5433 (mapped port).
    """
    import psycopg2
    # Parse DATABASE_URL if available (set in docker-compose-master.yml)
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        return psycopg2.connect(database_url)
    # Fallback to individual env vars (same defaults as generate_tour_text_service.py)
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "postgres-2"),
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "audiotours"),
        user=os.environ.get("DB_USER", "admin"),
        password=os.environ.get("DB_PASSWORD", "password123"),
    )


def _fetch_from_stop_corpus(topic: str) -> Optional[str]:
    """Check stop_corpus for existing Wikipedia content matching this topic.

    Returns the concatenated passage text if found, None otherwise.

    LOCAL-448 (Defect 1): Only exact accent-folded matching is used.
    The previous containment match (`topic in title or title in topic`) served
    the WRONG stop's corpus — e.g. "The Dream" inside "The Dream of Saint Ursula
    by Carpaccio" returned a completely unrelated museum's content. A wrong DB
    hit puts false content into a tour; a missed hit costs one network call.
    When in doubt, return None.

    LOCAL-448 (Defect 2): Uses production DB connection pattern, not tests/ import.
    Import failure is logged at WARNING (not silently swallowed).
    """
    if not _l447_enabled():
        return None

    try:
        conn = _get_db_connection()
    except Exception as e:
        logger.warning(f"DB-first: cannot connect to database: {e}")
        return None

    topic_folded = _strip_accents(topic).lower().strip()
    if not topic_folded:
        conn.close()
        return None

    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT stop_title, passages_json, source_pages
            FROM stop_corpus
            WHERE passages_json IS NOT NULL
              AND source_pages::text LIKE '%%wikipedia%%'
        """)
        rows = cur.fetchall()
        conn.close()

        import json
        for stop_title, passages_json, source_pages in rows:
            title_folded = _strip_accents(stop_title).lower().strip()
            # LOCAL-448: EXACT accent-folded match ONLY.
            # No substring/containment — that serves wrong corpus.
            if title_folded != topic_folded:
                continue

            # Found an exact match — extract Wikipedia-sourced passages
            passages = json.loads(passages_json) if isinstance(passages_json, str) else passages_json
            sources = json.loads(source_pages) if isinstance(source_pages, str) else source_pages

            # Verify at least one source is Wikipedia
            has_wiki_source = any(
                s.get('type') == 'wikipedia' or 'wikipedia.org' in s.get('url', '')
                for s in (sources if isinstance(sources, list) else [])
            )
            if not has_wiki_source:
                continue

            # Extract text from passages
            texts = []
            for p in (passages if isinstance(passages, list) else []):
                if isinstance(p, dict):
                    text = p.get('text', '')
                elif isinstance(p, str):
                    text = p
                else:
                    continue
                if text and len(text) > 20:
                    texts.append(text)

            if texts:
                combined = '\n'.join(texts)
                logger.info(f"DB-first: served '{topic}' from stop_corpus ({len(combined)} chars, 0 network calls)")
                return combined

        return None

    except Exception as e:
        logger.warning(f"DB-first lookup failed for '{topic}': {e}")
        return None


# ─── Wayback fallback (LOCAL-447, D403a step 2) — REMOVED FROM CHAIN ─────────
#
# LOCAL-448 (Defect 3): Wayback is removed from the active retrieval chain.
# LOCAL-447 measurement proved it unfit: 7% coverage, median 9.6s (over 5s budget),
# both hits the wrong article. Wiring it puts a ~10s stall back on the failure
# path LOCAL-445 made instant (~77s on an 8-stop tour for 9-year-stale content
# 7% of the time).
#
# The probe (wayback_wikipedia_probe.py) and its fixture remain as evidence that
# settled the question. The parsing code below is retained for reference and for
# the probe to use, but is NOT called from the production retrieval chain.

def _parse_wayback_timestamp(url_or_ts: str) -> Optional[datetime]:
    """Parse a Wayback Machine timestamp (YYYYMMDDHHmmss) from a URL or raw string.
    
    Retained for wayback_wikipedia_probe.py reference. Not used in production chain.
    """
    m = re.search(r'/web/(\d{14})/', url_or_ts)
    if not m:
        m = re.match(r'^(\d{14})$', url_or_ts.strip())
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _fetch_from_wayback_wikipedia(topic: str, timeout: float = 12.0) -> Optional[dict]:
    """Fetch the archived Wikipedia article from Wayback Machine.

    LOCAL-448: REMOVED FROM PRODUCTION CHAIN. This function is retained for the
    probe/fixture evidence but is never called from fetch_wikipedia_summary_with_provenance().

    LOCAL-447 measurement rejected it:
      - 7% coverage (2/30 titles)
      - Median 9.6s latency (over 5s budget)
      - Both hits returned the WRONG article
    """
    # LOCAL-448: This function is no longer called from the production chain.
    # It remains here only so wayback_wikipedia_probe.py can still import it.
    if not _l447_enabled():
        return None

    encoded = quote(topic.strip().replace(' ', '_'), safe='')
    article_url = f"https://en.wikipedia.org/wiki/{encoded}"
    wayback_url = f"https://web.archive.org/web/2/{article_url}"

    try:
        resp = requests.get(
            wayback_url,
            headers={'User-Agent': 'Audioura/2.2 (LOCAL-447 wayback-fallback)'},
            timeout=timeout,
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return None

        # Parse snapshot timestamp
        final_url = resp.url if isinstance(resp.url, str) else str(resp.url)
        snapshot_dt = _parse_wayback_timestamp(final_url)
        snapshot_ts_str = snapshot_dt.strftime('%Y%m%d%H%M%S') if snapshot_dt else ''
        age_days = (datetime.now(timezone.utc) - snapshot_dt).days if snapshot_dt else None

        html = resp.text
        if not html or len(html) < 500:
            return None

        # Extract lead section (before first <h2>)
        lead_html = re.split(r'<h2', html, maxsplit=1)[0]

        paragraphs = []
        for p_match in re.finditer(r'<p(?:\s[^>]*)?>(.+?)</p>', lead_html, re.DOTALL):
            clean = re.sub(r'<[^>]+>', '', p_match.group(1)).strip()
            clean = re.sub(r'\[\d+\]', '', clean).strip()
            if clean and len(clean) > 30:
                paragraphs.append(clean)

        lead_text = '\n'.join(paragraphs)
        if not lead_text or len(lead_text) < 50:
            return None

        logger.info(f"Wayback fallback: served '{topic}' from archive "
                    f"(snapshot {snapshot_ts_str}, age {age_days}d, {len(lead_text)} chars)")

        return {
            'text': lead_text,
            'is_from_archive': True,
            'wayback_snapshot_timestamp': snapshot_ts_str,
            'snapshot_age_days': age_days,
        }

    except Exception as e:
        logger.debug(f"Wayback fallback failed for '{topic}': {e}")
        return None


def fetch_wikipedia_summary(topic: str, sentences: int = 5) -> str:
    """Fetch a plain-text summary from Wikipedia's REST API.

    LOCAL-447 retrieval chain (D403a):
      1. Own DB (stop_corpus) — zero network cost, accent-folded match
      2. Live Wikipedia REST/Action API — existing path
      3. Wayback archived article — only when Wikimedia is cold (dead_host_breaker)

    Args:
        topic: The Wikipedia article title (e.g. "Marc Chagall").
        sentences: Not directly supported by the summary endpoint, but the
                   returned extract is typically 3-5 sentences (the page intro).

    Returns:
        The 'extract' field (plain text) from the Wikipedia summary response.
        Returns empty string on 404, redirect loops, network errors, or if
        the topic doesn't exist — never raises.
        
        When content is from the archive, the return value is still a plain string
        (backwards compatible). Use fetch_wikipedia_summary_with_provenance() if
        you need the archive metadata.
    """
    result = fetch_wikipedia_summary_with_provenance(topic, sentences)
    return result.get('text', '') if result else ''


def fetch_wikipedia_summary_with_provenance(topic: str, sentences: int = 5) -> dict:
    """Fetch Wikipedia summary with provenance metadata.

    LOCAL-448 retrieval chain (simplified — Wayback removed):
      1. Own DB (stop_corpus) — zero network cost, exact accent-folded match
      2. Live Wikipedia REST/Action API — existing path

    Returns:
        dict with keys:
            'text': str — the summary text
            'source': str — 'stop_corpus' or 'wikipedia_live'
            'is_from_archive': bool — always False (Wayback removed)
            'wayback_snapshot_timestamp': str — always '' (Wayback removed)
            'snapshot_age_days': int or None — always None (Wayback removed)
        Returns empty dict on total failure.
    """
    if not topic or not topic.strip():
        return {}

    # ─── Step 1: DB-first (LOCAL-447, D403a step 1; LOCAL-448 fixed) ─────────
    db_content = _fetch_from_stop_corpus(topic)
    if db_content:
        return {
            'text': db_content,
            'source': 'stop_corpus',
            'is_from_archive': False,
            'wayback_snapshot_timestamp': '',
            'snapshot_age_days': None,
        }

    # ─── Step 2: Live Wikipedia (existing path) ──────────────────────────────
    # LOCAL-448 (Defect 3): Wayback removed entirely. When Wikimedia is cold or
    # returns 429, we fall through to the action API (pre-LOCAL-447 behaviour).
    # This avoids the ~10s stall that Wayback imposed for 9-year-stale content
    # with 7% coverage and wrong articles.

    encoded_topic = quote(topic.strip().replace(" ", "_"), safe="")
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_topic}"

    try:
        from dead_host_breaker import is_host_cold, mark_host_cold
        wikimedia_cold = is_host_cold('en.wikipedia.org')
    except ImportError:
        wikimedia_cold = False

    if wikimedia_cold:
        # Wikimedia is cold — skip REST, try action API directly
        logger.info(f"Wikipedia: Wikimedia is cold, trying action API for '{topic}'")
        action_result = _fetch_via_action_api(topic)
        if action_result:
            return {'text': action_result, 'source': 'wikipedia_live',
                    'is_from_archive': False, 'wayback_snapshot_timestamp': '',
                    'snapshot_age_days': None}
        return {}

    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": "Audioura/2.2 (tour-generation; contact: support@audioura.com)",
                "Accept": "application/json",
            },
            timeout=5,
            allow_redirects=True,
        )

        if response.status_code == 429:
            # Rate limited — mark cold, fall through to action API
            try:
                mark_host_cold('en.wikipedia.org', '429 rate limit')
            except Exception:
                pass
            logger.warning(f"Wikipedia: 429 for '{topic}', marked cold, trying action API")
            action_result = _fetch_via_action_api(topic)
            if action_result:
                return {'text': action_result, 'source': 'wikipedia_live',
                        'is_from_archive': False, 'wayback_snapshot_timestamp': '',
                        'snapshot_age_days': None}
            return {}

        if response.status_code == 404:
            logger.info(f"Wikipedia: no article found for '{topic}'")
            action_result = _fetch_via_action_api(topic)
            if action_result:
                return {'text': action_result, 'source': 'wikipedia_live',
                        'is_from_archive': False, 'wayback_snapshot_timestamp': '',
                        'snapshot_age_days': None}
            return {}

        if response.status_code != 200:
            logger.warning(f"Wikipedia API returned {response.status_code} for '{topic}' | URL: {url} | body[:200]: {response.text[:200]}")
            action_result = _fetch_via_action_api(topic)
            if action_result:
                return {'text': action_result, 'source': 'wikipedia_live',
                        'is_from_archive': False, 'wayback_snapshot_timestamp': '',
                        'snapshot_age_days': None}
            return {}

        data = response.json()
        extract = data.get("extract", "")

        if not extract:
            logger.info(f"Wikipedia: empty extract for '{topic}'")
            action_result = _fetch_via_action_api(topic)
            if action_result:
                return {'text': action_result, 'source': 'wikipedia_live',
                        'is_from_archive': False, 'wayback_snapshot_timestamp': '',
                        'snapshot_age_days': None}
            return {}

        # If summary is too short, try action API for richer content
        if len(extract) < 500:
            richer = _fetch_via_action_api(topic)
            if richer and len(richer) > len(extract):
                extract = richer

        return {'text': extract, 'source': 'wikipedia_live',
                'is_from_archive': False, 'wayback_snapshot_timestamp': '',
                'snapshot_age_days': None}

    except requests.Timeout:
        logger.warning(f"Wikipedia: timeout fetching '{topic}'")
        try:
            mark_host_cold('en.wikipedia.org', 'timeout')
        except Exception:
            pass
        # Fall through to action API instead of Wayback
        action_result = _fetch_via_action_api(topic)
        if action_result:
            return {'text': action_result, 'source': 'wikipedia_live',
                    'is_from_archive': False, 'wayback_snapshot_timestamp': '',
                    'snapshot_age_days': None}
        return {}
    except requests.RequestException as e:
        logger.warning(f"Wikipedia: request error for '{topic}': {e}")
        return {}
    except (ValueError, KeyError) as e:
        logger.warning(f"Wikipedia: parse error for '{topic}': {e}")
        return {}


def fetch_poi_rag_context(
    poi_name: str, venue_name: str = "", tour_category: str = "museum"
) -> dict:
    """Fetch RAG context for a POI by looking up related Wikipedia topics.

    [BLOCKER 2 FIX] Context is now POI-specific, not venue-derived.
    The artist/creator attribution is ONLY applied when the POI name suggests
    a specific artist's work (e.g. "Biblical Message" at a Chagall museum).
    For generic room names or non-art POIs, no artist is asserted.

    Args:
        poi_name: Name of the point of interest (e.g. "Biblical Message Room").
        venue_name: The venue/museum name (e.g. "Musée National Marc Chagall").
        tour_category: 'museum', 'walking', 'restaurant', 'book'.

    Returns:
        dict with keys:
            artist_context: str — Wikipedia summary about the POI's creator (if identifiable)
            period_context: str — Wikipedia summary about the POI or venue context
            attribution_confident: bool — True only if we can confidently attribute the POI
    """
    import re
    artist_context = ""
    period_context = ""
    attribution_confident = False

    if tour_category == "museum" and venue_name:
        # [BLOCKER 2] First try to look up the POI itself — this is the most specific context
        poi_context = fetch_wikipedia_summary(poi_name)
        if poi_context and len(poi_context) > 100:
            # The POI has its own Wikipedia article — use that as primary context
            period_context = poi_context
            # Check if the venue artist is mentioned in the POI's context
            _venue_artist = _extract_artist_from_venue(venue_name)
            if _venue_artist and _venue_artist.lower() in poi_context.lower():
                artist_context = fetch_wikipedia_summary(_venue_artist)
                attribution_confident = True
        else:
            # POI doesn't have a standalone article — use venue context
            # but DO NOT assert the venue artist as the POI's creator
            period_context = fetch_wikipedia_summary(venue_name)
            if not period_context:
                period_context = fetch_wikipedia_summary(venue_name.replace("Musee", "Musée"))

            # Only fetch artist context if we can verify the connection
            _venue_artist = _extract_artist_from_venue(venue_name)
            if _venue_artist:
                # Check: does the POI name suggest it's by this artist?
                # (e.g. "Song of Songs" at Chagall museum → likely Chagall)
                # But "Gift Shop" or "Garden" at Chagall museum → NOT Chagall's work
                _NON_ART_INDICATORS = ('shop', 'gift', 'cafe', 'garden', 'entrance',
                                       'lobby', 'restroom', 'parking', 'courtyard',
                                       'auditorium', 'concert hall', 'library')
                _poi_lower = poi_name.lower()
                is_non_art = any(ind in _poi_lower for ind in _NON_ART_INDICATORS)
                if not is_non_art:
                    artist_context = fetch_wikipedia_summary(_venue_artist)
                    # Mark attribution as confident only for a single-artist museum
                    # where the POI is likely an artwork (not a facility room)
                    attribution_confident = True

    elif tour_category == "walking":
        # Walking tours: look up the POI name directly
        period_context = fetch_wikipedia_summary(poi_name)
    elif tour_category == "restaurant":
        # Restaurant tours: look up the restaurant/establishment
        period_context = fetch_wikipedia_summary(poi_name)
    else:
        # Default: try the POI name
        period_context = fetch_wikipedia_summary(poi_name)

    return {
        "artist_context": artist_context,
        "period_context": period_context,
        "attribution_confident": attribution_confident,
    }


def _extract_artist_from_venue(venue_name: str) -> str:
    """Extract a likely artist/subject name from a museum venue name.
    
    E.g. "Musée National Marc Chagall" → "Marc Chagall"
    Returns empty string if no artist can be extracted.
    """
    import re
    cleaned = re.sub(
        r"(?i)(mus[ée]+e?|museum|gallery|national|the|of|art|centre|center)\s*",
        " ", venue_name
    ).strip()
    artist_topic = " ".join(w for w in cleaned.split() if w and len(w) > 1).strip()
    return artist_topic


def _fetch_via_action_api(topic: str) -> str:
    """Fallback: use Wikipedia's Action API for full article text (no char limit).
    
    Returns the complete article extract — much richer than the REST summary endpoint.
    Also tries French Wikipedia for French museums.
    """
    import requests as _req
    if not topic or not topic.strip():
        return ""
    
    # Try English Wikipedia first (full text, no char limit)
    for wiki_host in ['en.wikipedia.org', 'fr.wikipedia.org']:
        try:
            response = _req.get(
                f"https://{wiki_host}/w/api.php",
                params={
                    "action": "query",
                    "prop": "extracts",
                    "explaintext": "1",
                    "titles": topic.strip(),
                    "format": "json",
                    # NO exchars/exintro/formatversion — get FULL article text
                    # formatversion=2 removed: causes 0-char extracts on some pages
                },
                headers={
                    "User-Agent": "Audioura/2.2 (tour-generation; contact: support@audioura.com)",
                },
                timeout=10,
            )
            
            if response.status_code != 200:
                continue
            
            data = response.json()
            pages = data.get("query", {}).get("pages", {})
            if isinstance(pages, list):
                # Shouldn't happen without formatversion=2, but handle gracefully
                for page_data in pages:
                    if page_data.get("missing"):
                        continue
                    extract = page_data.get("extract", "")
                    if extract and len(extract) > 200:
                        logger.info(f"Wikipedia ({wiki_host}): full article for '{topic}' = {len(extract)} chars")
                        return extract
            elif isinstance(pages, dict):
                for page_id, page_data in pages.items():
                    if page_id == "-1" or page_data.get("missing"):
                        continue
                    extract = page_data.get("extract", "")
                    if extract and len(extract) > 200:
                        logger.info(f"Wikipedia ({wiki_host}): full article for '{topic}' = {len(extract)} chars")
                        return extract
        except Exception as e:
            logger.warning(f"Wikipedia action API error ({wiki_host}) for '{topic}': {e}")
            continue
    
    return ""
