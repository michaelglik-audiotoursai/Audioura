"""
Spine Generator — produces narrative spine JSON from a tour template + GPT-4o.
===============================================================================
Loads the correct template by tour_category, substitutes variables, calls OpenAI,
and returns a parsed spine dict. Logs cost + latency.
"""
import json
import logging
import os
import time
from typing import Optional, List

import requests

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")

_TEMPLATE_MAP = {
    "museum": "spine_museum.txt",
    "walking": "spine_walking.txt",
    "restaurant": "spine_restaurant.txt",
    "book": "spine_book.txt",
}

# GPT-4o pricing (per 1K tokens) — for cost logging
_INPUT_COST_PER_1K = 0.005
_OUTPUT_COST_PER_1K = 0.015


def _load_template(tour_category: str) -> str:
    """Load the spine template for the given tour category."""
    filename = _TEMPLATE_MAP.get(tour_category.lower(), "spine_museum.txt")
    path = os.path.join(_TEMPLATE_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def generate_spine(
    venue_name: str,
    poi_list: List[str],
    tour_category: str,
    api_key: str,
    theme_name: str = "",
) -> Optional[dict]:
    """Generate a narrative spine for a tour.

    Args:
        venue_name: The venue/location name.
        poi_list: List of POI names (strings) in tour order.
        tour_category: 'museum', 'walking', 'restaurant', or 'book'.
        api_key: OpenAI API key.
        theme_name: For book tours, the source work/theme name.

    Returns:
        Parsed spine dict with all 11 fields, or None on failure.
        Logs cost and latency to stdout/logger.
    """
    template = _load_template(tour_category)

    # Substitute variables
    poi_str = ", ".join(poi_list)
    prompt = template.replace("{{venue_name}}", venue_name)
    prompt = prompt.replace("{{poi_list}}", poi_str)
    prompt = prompt.replace("{{total_stops}}", str(len(poi_list)))
    if "{{theme_name}}" in prompt:
        prompt = prompt.replace("{{theme_name}}", theme_name or venue_name)

    start = time.time()

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o",
                "messages": [
                    {
                        "role": "system",
                        "content": "You return ONLY valid JSON. No markdown fences, no commentary.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.7,
                "max_tokens": 2000,
            },
            timeout=30,
        )

        elapsed = time.time() - start

        if response.status_code != 200:
            logger.error(f"Spine API error: {response.status_code} — {response.text[:200]}")
            return None

        result = response.json()
        text = result["choices"][0]["message"]["content"].strip()

        # Cost calculation
        usage = result.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)
        cost = (input_tokens / 1000 * _INPUT_COST_PER_1K) + (
            output_tokens / 1000 * _OUTPUT_COST_PER_1K
        )

        print(
            f"SPINE_COST: category={tour_category} venue={venue_name[:30]} "
            f"tokens={total_tokens} (in={input_tokens} out={output_tokens}) "
            f"cost=${cost:.4f} latency={elapsed:.1f}s"
        )
        logger.info(
            f"Spine generated: {tour_category}/{venue_name[:30]} | "
            f"${cost:.4f} | {elapsed:.1f}s | {total_tokens} tokens"
        )

        # Parse JSON (handle markdown fences if model includes them despite instructions)
        import re
        clean = text
        m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", clean, re.DOTALL)
        if m:
            clean = m.group(1)

        spine = json.loads(clean)

        # Validate required fields
        required = [
            "tour_hook", "connecting_thread", "arc",
            "climax_stop", "resolution_stop", "closing_revelation",
        ]
        for field in required:
            if field not in spine:
                logger.error(f"Spine missing field: {field}")
                return None

        # Validate arc entries
        arc_fields = [
            "chapter_role", "emotional_beat", "unique_angle",
            "plant", "callback", "cliffhanger",
        ]
        for stop in spine.get("arc", []):
            for af in arc_fields:
                if af not in stop:
                    logger.warning(f"Arc stop missing field: {af}")

        return spine

    except json.JSONDecodeError as e:
        logger.error(f"Spine JSON parse error: {e}")
        return None
    except requests.Timeout:
        logger.error(f"Spine generation timed out for {venue_name}")
        return None
    except Exception as e:
        logger.error(f"Spine generation error: {e}")
        return None
