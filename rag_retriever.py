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
            return ""

        if response.status_code != 200:
            logger.warning(f"Wikipedia API returned {response.status_code} for '{topic}'")
            return ""

        data = response.json()
        extract = data.get("extract", "")

        if not extract:
            logger.info(f"Wikipedia: empty extract for '{topic}'")
            return ""

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

    Builds 2 lookup topics:
      - artist_context: the creator/artist associated with the venue or POI
      - period_context: the historical period, movement, or cultural context

    For museum tours, uses venue_name to derive the artist lookup.

    Args:
        poi_name: Name of the point of interest (e.g. "Biblical Message Room").
        venue_name: The venue/museum name (e.g. "Musée National Marc Chagall").
        tour_category: 'museum', 'walking', 'restaurant', 'book'.

    Returns:
        dict with keys:
            artist_context: str — Wikipedia summary about the artist/creator
            period_context: str — Wikipedia summary about the period/context
    """
    artist_context = ""
    period_context = ""

    if tour_category == "museum" and venue_name:
        # Extract artist name from venue name (e.g. "Marc Chagall" from "Musée National Marc Chagall")
        # Common patterns: "Museum of X", "X Museum", "Musée X", "The X Gallery"
        import re
        # Try to extract a proper noun (the artist/subject name)
        # Remove common museum prefixes/suffixes
        cleaned = re.sub(
            r"(?i)(mus[ée]+e?|museum|gallery|national|the|of|art|centre|center)\s*",
            " ", venue_name
        ).strip()
        # Use the longest remaining word group as the artist topic
        artist_topic = " ".join(w for w in cleaned.split() if w and len(w) > 1).strip()
        if artist_topic:
            artist_context = fetch_wikipedia_summary(artist_topic)

        # Period context: look up the venue itself, then fall back to related topics
        period_context = fetch_wikipedia_summary(venue_name)
        if not period_context:
            # Try the venue name with common Wikipedia article patterns
            period_context = fetch_wikipedia_summary(venue_name.replace("Musee", "Musée"))
        if not period_context and artist_topic:
            # Fall back to the artist's primary article (different angle from artist_context)
            # This gets the artist's movement/period information
            period_context = fetch_wikipedia_summary(f"{artist_topic} (artist)")
        if not period_context and artist_topic:
            # Last resort: the broader cultural movement
            period_context = fetch_wikipedia_summary("Modern art")
    else:
        # Walking/restaurant/book: use the POI name directly for context
        artist_context = fetch_wikipedia_summary(poi_name)
        # And the broader area/venue for period context
        if venue_name:
            period_context = fetch_wikipedia_summary(venue_name)
        else:
            period_context = ""

    return {
        "artist_context": artist_context,
        "period_context": period_context,
    }
