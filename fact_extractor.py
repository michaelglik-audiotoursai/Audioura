"""
Fact Extractor — generates structured fact sheets from RAG context + GPT.
==========================================================================
Produces verified facts, uncertain claims, and surprising details for each POI.
Used by the spine generator to ground narrative in reality.
"""
import json
import logging
import re
from typing import Optional

import requests

logger = logging.getLogger(__name__)


def generate_fact_sheet(
    poi_name: str, rag_context: dict, api_key: str
) -> Optional[dict]:
    """Generate a structured fact sheet for a POI using RAG context.

    Args:
        poi_name: Name of the point of interest.
        rag_context: dict with 'artist_context' and 'period_context' from rag_retriever.
        api_key: OpenAI API key.

    Returns:
        dict with keys: confirmed_facts, uncertain_facts, date_created, medium, surprising_detail.
        None on failure.
    """
    artist_ctx = rag_context.get("artist_context", "")
    period_ctx = rag_context.get("period_context", "")

    if not artist_ctx and not period_ctx:
        logger.warning(f"No RAG context for {poi_name} — cannot generate fact sheet")
        return None

    prompt = (
        f"You are a meticulous museum researcher. Given the following Wikipedia context "
        f"about an exhibit/room called '{poi_name}', extract verified facts.\n\n"
        f"--- CONTEXT ---\n"
        f"Artist/Creator: {artist_ctx[:800]}\n\n"
        f"Venue/Period: {period_ctx[:800]}\n"
        f"--- END CONTEXT ---\n\n"
        f"Return ONLY valid JSON with this schema:\n"
        f'{{\n'
        f'  "confirmed_facts": ["fact 1", "fact 2", ...],\n'
        f'  "uncertain_facts": ["unverified claim 1", ...],\n'
        f'  "date_created": "year or date range if known, else null",\n'
        f'  "medium": "materials/medium used if applicable, else null",\n'
        f'  "surprising_detail": "one non-obvious detail that would intrigue a visitor"\n'
        f'}}\n\n'
        f"Rules:\n"
        f"- confirmed_facts: ONLY facts directly supported by the context above.\n"
        f"- uncertain_facts: claims you believe but cannot confirm from the context.\n"
        f"- surprising_detail: must be genuinely unexpected, not a generic statement.\n"
        f"- If you cannot find information, use empty arrays and null values."
    )

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": "You return ONLY valid JSON. No markdown, no commentary."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 500,
            },
            timeout=15,
        )

        if response.status_code != 200:
            logger.error(f"Fact sheet API error: {response.status_code}")
            return None

        result = response.json()
        text = result["choices"][0]["message"]["content"].strip()

        # Cost logging
        tokens = result.get("usage", {}).get("total_tokens", 0)
        cost = tokens / 1000 * 0.002
        logger.info(f"Fact sheet: {poi_name} | {tokens} tokens | ${cost:.4f}")

        # Parse JSON (handle markdown fences)
        clean = text
        m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", clean, re.DOTALL)
        if m:
            clean = m.group(1)

        fact_sheet = json.loads(clean)

        # Validate structure
        required = ["confirmed_facts", "uncertain_facts", "surprising_detail"]
        for field in required:
            if field not in fact_sheet:
                fact_sheet[field] = [] if "facts" in field else None

        # Ensure lists are lists
        if not isinstance(fact_sheet.get("confirmed_facts"), list):
            fact_sheet["confirmed_facts"] = []
        if not isinstance(fact_sheet.get("uncertain_facts"), list):
            fact_sheet["uncertain_facts"] = []

        return fact_sheet

    except json.JSONDecodeError as e:
        logger.error(f"Fact sheet JSON error for {poi_name}: {e}")
        return None
    except Exception as e:
        logger.error(f"Fact sheet error for {poi_name}: {e}")
        return None


def generate_fact_sheets_parallel(
    poi_list: list,
    venue_name: str,
    tour_category: str,
    api_key: str,
    max_workers: int = 5,
) -> list:
    """Generate fact sheets for all POIs in parallel.

    Uses ThreadPoolExecutor to fetch RAG context and generate a fact sheet
    per POI concurrently. Returns results in original order.
    Gracefully handles individual POI failures (None per failed stop).

    Args:
        poi_list: List of POI dicts (each with 'name') or strings.
        venue_name: The venue/location name.
        tour_category: 'museum', 'walking', 'restaurant', or 'book'.
        api_key: OpenAI API key.
        max_workers: Max concurrent threads (default 5).

    Returns:
        List of fact_sheet dicts (or None for failed POIs), in original order.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from rag_retriever import fetch_poi_rag_context

    def _process_one(idx_poi):
        idx, poi = idx_poi
        poi_name = poi.get("name", str(poi)) if isinstance(poi, dict) else str(poi)
        try:
            rag_ctx = fetch_poi_rag_context(poi_name, venue_name, tour_category)
            fact_sheet = generate_fact_sheet(poi_name, rag_ctx, api_key)
            return idx, fact_sheet
        except Exception as e:
            logger.error(f"Fact sheet failed for POI #{idx} ({poi_name}): {e}")
            return idx, None

    # Submit all in parallel
    results = [None] * len(poi_list)
    with ThreadPoolExecutor(max_workers=min(max_workers, len(poi_list))) as executor:
        futures = {
            executor.submit(_process_one, (i, poi)): i
            for i, poi in enumerate(poi_list)
        }
        for future in as_completed(futures):
            idx, fact_sheet = future.result()
            results[idx] = fact_sheet

    success_count = sum(1 for r in results if r is not None)
    logger.info(f"Fact sheets: {success_count}/{len(poi_list)} successful for {venue_name}")
    return results
