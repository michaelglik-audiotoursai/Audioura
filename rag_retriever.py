"""
RAG Retriever — lightweight knowledge-fetch utilities for Storied tour generation.
No OpenAI calls. Fetches factual summaries from public APIs to ground tour narratives.
"""
import requests
import logging
from urllib.parse import quote

logger = logging.getLogger(__name__)


def fetch_wikipedia_summary(topic: str, sentences: int = 5) -> str:
    """Fetch a plain-text summary from Wikipedia's REST API.

    Args:
        topic: The Wikipedia article title (e.g. "Marc Chagall").
        sentences: Not directly supported by the summary endpoint, but the
                   returned extract is typically 3-5 sentences (the page intro).

    Returns:
        The 'extract' field (plain text) from the Wikipedia summary response.
        Returns empty string on 404, redirect loops, network errors, or if
        the topic doesn't exist — never raises.
    """
    if not topic or not topic.strip():
        return ""

    # URL-encode the topic (spaces → underscores is Wikipedia convention)
    encoded_topic = quote(topic.strip().replace(" ", "_"), safe="")
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_topic}"

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

        if response.status_code == 404:
            logger.info(f"Wikipedia: no article found for '{topic}'")
            # Try the action API as fallback (broader search)
            return _fetch_via_action_api(topic)

        if response.status_code != 200:
            logger.warning(f"Wikipedia API returned {response.status_code} for '{topic}' | URL: {url} | body[:200]: {response.text[:200]}")
            return _fetch_via_action_api(topic)

        data = response.json()
        extract = data.get("extract", "")

        if not extract:
            logger.info(f"Wikipedia: empty extract for '{topic}'")
            return _fetch_via_action_api(topic)

        return extract

    except requests.Timeout:
        logger.warning(f"Wikipedia: timeout fetching '{topic}'")
        return ""
    except requests.RequestException as e:
        logger.warning(f"Wikipedia: request error for '{topic}': {e}")
        return ""
    except (ValueError, KeyError) as e:
        logger.warning(f"Wikipedia: parse error for '{topic}': {e}")
        return ""


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
    """Fallback: use Wikipedia's Action API for broader article extracts.
    
    This returns more text than the REST summary endpoint and is rarely blocked.
    """
    import requests as _req
    if not topic or not topic.strip():
        return ""
    
    try:
        response = _req.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "prop": "extracts",
                "exintro": False,  # Get full article, not just intro
                "explaintext": True,
                "titles": topic.strip(),
                "format": "json",
                "exchars": 3000,  # Up to 3000 chars of content
            },
            headers={
                "User-Agent": "Audioura/2.2 (tour-generation; contact: support@audioura.com)",
            },
            timeout=8,
        )
        
        if response.status_code != 200:
            return ""
        
        data = response.json()
        pages = data.get("query", {}).get("pages", {})
        for page_id, page_data in pages.items():
            if page_id == "-1":
                return ""  # Page not found
            extract = page_data.get("extract", "")
            if extract:
                return extract
        return ""
    except Exception as e:
        logger.warning(f"Wikipedia action API error for '{topic}': {e}")
        return ""
