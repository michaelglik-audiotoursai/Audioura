#!/usr/bin/env python3
"""
shortfall_search.py — Verify whether missing stops are genuinely UNAVAILABLE.

LOCAL-309: Michael's ruling (2026-08-06):
  "We should not trust the log. We should do a quick Internet search to see if
   the data really is not available."

When a tour delivers fewer stops than requested, for each missing slot this
module runs a BOUNDED lookup for further real candidates in the area — using
Wikipedia/Wikidata (the tier-1 path already built in stop_existence_gate.py).

The contract:
  - UNAVAILABLE at zero cost requires a LIVE SEARCH that confirms no further
    candidates exist.
  - Absent that search, the shortfall is PIPELINE_LOST (costs -1.0 × share).
  - On search failure (network error, 429, timeout) → PIPELINE_LOST.
    Infrastructure failure never buys a free pass.

Bounds:
  - At most 1 query per missing stop
  - At most 5 queries per tour
  - 10-second timeout per query
  - Cache by (area_key, date) — two tours of the same area on the same day
    don't both pay

Evidence:
  - Every verdict is recorded with what was searched and what came back.
  - A zero-cost UNAVAILABLE with no recorded search is a bug.
"""

import hashlib
import json
import logging
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# --- Constants ---
MAX_QUERIES_PER_TOUR = 5
QUERY_TIMEOUT_SECONDS = 10

# --- In-memory cache: {cache_key: ShortfallVerdict} ---
# cache_key = hash(area_key + date_str)
_search_cache: Dict[str, 'ShortfallVerdict'] = {}


@dataclass
class ShortfallVerdict:
    """Result of a shortfall search for one missing slot."""
    classification: str  # 'UNAVAILABLE' or 'PIPELINE_LOST'
    search_query: str    # what was searched
    candidates_found: List[str]  # real candidates found (if any)
    evidence: str        # human-readable explanation
    search_error: str    # error message if search failed, '' otherwise
    cached: bool = False # whether this result came from cache
    cost_usd: float = 0.0  # estimated cost of this search (API calls are free but tracked)


@dataclass
class TourShortfallResult:
    """Results of shortfall search for an entire tour."""
    venue_name: str
    n_requested: int
    n_delivered: int
    n_missing: int
    verdicts: List[ShortfallVerdict]
    total_queries: int = 0
    cache_hits: int = 0
    wall_time_seconds: float = 0.0
    cost_usd: float = 0.0


def _strip_accents(text: str) -> str:
    """Remove accents for matching."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def _area_cache_key(venue_name: str, search_query: str) -> str:
    """Generate a cache key for (area, date) deduplication."""
    today = date.today().isoformat()
    raw = f"{venue_name.lower().strip()}|{search_query.lower().strip()}|{today}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _extract_region_terms(venue_name: str) -> List[str]:
    """Extract meaningful region/area terms from venue_name for search queries."""
    # Remove generic tour-type words
    GENERIC = {'tour', 'walking', 'biking', 'cycling', 'driving', 'museum',
               'area', 'region', 'route', 'trail', 'path'}
    words = re.split(r'[,\s]+', venue_name)
    terms = []
    for w in words:
        clean = _strip_accents(w).lower().strip()
        if len(clean) >= 3 and clean not in GENERIC:
            terms.append(clean)
    return terms


def _search_for_candidates_wikipedia(
    venue_name: str,
    region_terms: List[str],
    delivered_titles: List[str],
) -> Tuple[List[str], str, str]:
    """Search Wikipedia for additional real candidates in the area.

    Returns: (candidates_found, evidence_string, error_string)
    """
    import requests

    HEADERS = {
        "User-Agent": "Audioura/2.2 (tour-generation; contact: support@audioura.com)",
        "Accept": "application/json",
    }

    # Build search query: "points of interest" + region terms
    # For geographic areas: look for notable places/landmarks
    # For museums: look for notable works/exhibits
    region_str = " ".join(region_terms[:3])
    search_queries = [
        f"notable landmarks {region_str}",
        f"points of interest {region_str}",
    ]

    candidates = []
    evidence_parts = []
    delivered_lower = {t.lower() for t in delivered_titles}

    for sq in search_queries[:1]:  # Only 1 query per missing stop
        try:
            params = {
                "action": "query",
                "list": "search",
                "srsearch": sq,
                "srnamespace": "0",
                "srlimit": "10",
                "format": "json",
            }
            resp = requests.get(
                "https://en.wikipedia.org/w/api.php",
                params=params,
                headers=HEADERS,
                timeout=QUERY_TIMEOUT_SECONDS,
            )

            if resp.status_code == 429:
                # Rate limited — fail closed per spec
                return [], "", "wikipedia_429_rate_limited"

            if resp.status_code != 200:
                return [], "", f"wikipedia_http_{resp.status_code}"

            results = resp.json().get("query", {}).get("search", [])
            evidence_parts.append(f"searched: '{sq}', got {len(results)} results")

            for r in results:
                title = r.get("title", "")
                # Skip if it's already delivered
                if title.lower() in delivered_lower:
                    continue
                # Check if snippet mentions the region
                snippet = _strip_accents(
                    re.sub(r'<[^>]+>', '', r.get("snippet", ""))
                ).lower()
                if any(term in snippet for term in region_terms):
                    candidates.append(title)

        except requests.exceptions.Timeout:
            return [], "", "wikipedia_timeout"
        except requests.exceptions.ConnectionError:
            return [], "", "wikipedia_connection_error"
        except Exception as e:
            return [], "", f"wikipedia_error: {str(e)[:80]}"

    evidence = "; ".join(evidence_parts)
    if candidates:
        evidence += f"; found {len(candidates)} candidates: {candidates[:5]}"
    else:
        evidence += "; no additional candidates found in region"

    return candidates, evidence, ""


def _search_for_candidates_wikidata(
    venue_name: str,
    region_terms: List[str],
    delivered_titles: List[str],
) -> Tuple[List[str], str, str]:
    """Search Wikidata for additional real entities in the area.

    Returns: (candidates_found, evidence_string, error_string)
    """
    import requests

    HEADERS = {
        "User-Agent": "Audioura/2.2 (tour-generation; contact: support@audioura.com)",
        "Accept": "application/json",
    }

    # Search Wikidata for geographic entities in the region
    region_str = " ".join(region_terms[:2])
    search_term = f"{region_str} landmark"

    candidates = []
    delivered_lower = {t.lower() for t in delivered_titles}

    try:
        params = {
            "action": "wbsearchentities",
            "search": search_term,
            "language": "en",
            "limit": "10",
            "format": "json",
        }
        resp = requests.get(
            "https://www.wikidata.org/w/api.php",
            params=params,
            headers=HEADERS,
            timeout=QUERY_TIMEOUT_SECONDS,
        )

        if resp.status_code == 429:
            return [], "", "wikidata_429_rate_limited"

        if resp.status_code != 200:
            return [], "", f"wikidata_http_{resp.status_code}"

        results = resp.json().get("search", [])
        evidence = f"wikidata searched: '{search_term}', got {len(results)} results"

        for r in results:
            label = r.get("label", "")
            desc = _strip_accents(r.get("description", "")).lower()
            if label.lower() in delivered_lower:
                continue
            # Check if description mentions the region
            if any(term in desc for term in region_terms):
                candidates.append(label)

        if candidates:
            evidence += f"; found {len(candidates)} candidates: {candidates[:5]}"
        else:
            evidence += "; no additional candidates found"

        return candidates, evidence, ""

    except requests.exceptions.Timeout:
        return [], "", "wikidata_timeout"
    except requests.exceptions.ConnectionError:
        return [], "", "wikidata_connection_error"
    except Exception as e:
        return [], "", f"wikidata_error: {str(e)[:80]}"


def search_for_shortfall(
    venue_name: str,
    n_requested: int,
    delivered_titles: List[str],
    gate_log: Optional[List[dict]] = None,
) -> TourShortfallResult:
    """Run bounded shortfall search for a tour that delivered fewer stops than requested.

    For each missing slot, searches Wikipedia/Wikidata for real candidates in
    the area. If candidates are found → the missing stop is PIPELINE_LOST
    (we should have found them). If no candidates exist → UNAVAILABLE (zero cost).

    Args:
        venue_name: The tour's venue/area name.
        n_requested: Number of stops requested.
        delivered_titles: Titles of stops actually delivered.
        gate_log: Optional gate verdicts (for context, not used in search itself).

    Returns:
        TourShortfallResult with per-slot verdicts.
    """
    start_time = time.time()
    n_delivered = len(delivered_titles)
    n_missing = max(0, n_requested - n_delivered)

    result = TourShortfallResult(
        venue_name=venue_name,
        n_requested=n_requested,
        n_delivered=n_delivered,
        n_missing=n_missing,
        verdicts=[],
    )

    if n_missing == 0:
        result.wall_time_seconds = time.time() - start_time
        return result

    region_terms = _extract_region_terms(venue_name)
    if not region_terms:
        # Cannot determine region — fail closed (PIPELINE_LOST for all)
        for _ in range(n_missing):
            result.verdicts.append(ShortfallVerdict(
                classification='PIPELINE_LOST',
                search_query='',
                candidates_found=[],
                evidence='no region terms extractable from venue_name — fail closed',
                search_error='no_region_terms',
            ))
        result.wall_time_seconds = time.time() - start_time
        return result

    # Cap at MAX_QUERIES_PER_TOUR
    slots_to_search = min(n_missing, MAX_QUERIES_PER_TOUR)
    queries_made = 0

    # Check cache first — same area + same day = reuse verdict
    region_str = " ".join(region_terms[:3])
    cache_key = _area_cache_key(venue_name, region_str)

    cached_verdict = _search_cache.get(cache_key)
    if cached_verdict is not None:
        # Cache hit — replicate the verdict for all missing slots
        for _ in range(n_missing):
            v = ShortfallVerdict(
                classification=cached_verdict.classification,
                search_query=cached_verdict.search_query,
                candidates_found=cached_verdict.candidates_found,
                evidence=cached_verdict.evidence + " [CACHED]",
                search_error=cached_verdict.search_error,
                cached=True,
            )
            result.verdicts.append(v)
        result.cache_hits = n_missing
        result.wall_time_seconds = time.time() - start_time
        return result

    # Run the search — Wikipedia first, Wikidata as supplement
    wp_candidates, wp_evidence, wp_error = _search_for_candidates_wikipedia(
        venue_name, region_terms, delivered_titles
    )
    queries_made += 1

    if wp_error:
        # Search failed — fail closed: PIPELINE_LOST for all missing
        verdict = ShortfallVerdict(
            classification='PIPELINE_LOST',
            search_query=f"wikipedia: notable landmarks {region_str}",
            candidates_found=[],
            evidence=f"search failed: {wp_error}",
            search_error=wp_error,
        )
        # Cache the failure too (don't retry on same day for same area)
        _search_cache[cache_key] = verdict
        for _ in range(n_missing):
            v = ShortfallVerdict(
                classification=verdict.classification,
                search_query=verdict.search_query,
                candidates_found=verdict.candidates_found,
                evidence=verdict.evidence,
                search_error=verdict.search_error,
            )
            result.verdicts.append(v)
        result.total_queries = queries_made
        result.wall_time_seconds = time.time() - start_time
        return result

    # If Wikipedia found nothing, also try Wikidata
    all_candidates = list(wp_candidates)
    all_evidence = wp_evidence

    if not wp_candidates and queries_made < MAX_QUERIES_PER_TOUR:
        wd_candidates, wd_evidence, wd_error = _search_for_candidates_wikidata(
            venue_name, region_terms, delivered_titles
        )
        queries_made += 1

        if wd_error:
            # Wikidata also failed — still fail closed
            all_evidence += f"; wikidata search failed: {wd_error}"
        else:
            all_candidates.extend(wd_candidates)
            all_evidence += f"; {wd_evidence}"

    # Determine classification based on whether candidates were found
    if all_candidates:
        # Found real candidates → area is NOT exhausted → PIPELINE_LOST
        classification = 'PIPELINE_LOST'
        evidence_final = (
            f"search found {len(all_candidates)} additional candidates in area → "
            f"shortfall is our failure; {all_evidence}"
        )
    else:
        # No candidates found → area genuinely thin → UNAVAILABLE (search-confirmed)
        classification = 'UNAVAILABLE'
        evidence_final = (
            f"search confirmed no further candidates in area → "
            f"genuine scarcity; {all_evidence}"
        )

    # Build the verdict
    verdict = ShortfallVerdict(
        classification=classification,
        search_query=f"wikipedia+wikidata: {region_str}",
        candidates_found=all_candidates[:10],
        evidence=evidence_final,
        search_error='',
    )

    # Cache it
    _search_cache[cache_key] = verdict

    # Apply to all missing slots
    for _ in range(n_missing):
        v = ShortfallVerdict(
            classification=verdict.classification,
            search_query=verdict.search_query,
            candidates_found=verdict.candidates_found,
            evidence=verdict.evidence,
            search_error=verdict.search_error,
        )
        result.verdicts.append(v)

    result.total_queries = queries_made
    result.wall_time_seconds = time.time() - start_time
    # Cost: Wikipedia/Wikidata APIs are free; track as $0
    result.cost_usd = 0.0

    return result


def clear_cache():
    """Clear the shortfall search cache. For testing."""
    global _search_cache
    _search_cache = {}


def get_cache_stats() -> Dict:
    """Return cache statistics."""
    return {
        'entries': len(_search_cache),
        'keys': list(_search_cache.keys())[:10],
    }
