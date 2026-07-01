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
