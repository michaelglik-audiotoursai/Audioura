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


def select_spine_template(tour_category: str) -> str:
    """Select the correct spine template file path for a tour category.

    Args:
        tour_category: 'museum', 'walking', 'restaurant', or 'specialized'/'book'.

    Returns:
        Full file path to the template. Falls back to spine_walking.txt for unknown types.
    """
    category = tour_category.lower().strip()
    # Map specialized/book/movie to the book template
    if category in ('specialized', 'book', 'movie', 'film'):
        category = 'book'
    filename = _TEMPLATE_MAP.get(category, "spine_walking.txt")
    return os.path.join(_TEMPLATE_DIR, filename)


def generate_spine(
    venue_name: str,
    poi_list: List[str],
    tour_category: str,
    api_key: str,
    theme_name: str = "",
    story_elements: Optional[List[dict]] = None,
) -> Optional[dict]:
    """Generate a narrative spine for a tour.

    Args:
        venue_name: The venue/location name.
        poi_list: List of POI names (strings) in tour order.
        tour_category: 'museum', 'walking', 'restaurant', or 'book'.
        api_key: OpenAI API key.
        theme_name: For book tours, the source work/theme name.
        story_elements: Optional list of documented story elements from story_element_extractor.
                       When provided, the spine must build from these (story_mode: found).

    Returns:
        Parsed spine dict with all 11 fields + optional grounded_on per arc entry.
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

    # [§3] Story-grounded spine: inject story elements into the prompt
    _story_mode = "invented"
    if story_elements and len(story_elements) >= 3:
        _story_mode = "found"
        _elements_text = "\n".join(
            f"  [{e.get('id','?')}] ({e.get('type','?')}) {e.get('text','')}"
            for e in story_elements[:15]  # Cap to avoid token overflow
        )
        _story_injection = f"""

DOCUMENTED STORY ELEMENTS (build the spine arc FROM these — each chapter should declare which element(s) it uses):
{_elements_text}

REQUIREMENTS for story-grounded spine:
- The tour_hook and connecting_thread MUST reference the documented origin story (how/why the collection exists)
- The prolog (tour_hook) MUST tell the origin story using elements marked 'origin', 'intention', 'turning_point'
- Each arc chapter should declare "grounded_on": ["se_001", "se_003"] listing element IDs it uses
- Chapters with no grounding element are allowed only as connective tissue (no factual claims)
- The closing_revelation MUST close the documented arc (return to the origin story's conclusion)
- NEVER invent dates, intentions, quotes, or provenance not in the elements above
"""
        prompt += _story_injection
        print(f"  [§3] Story elements injected into spine prompt ({len(story_elements)} elements, mode=found)")
    else:
        print(f"  [§3] No story elements available — spine will use invented arc (mode=invented)")

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

        # [§3] Add story_mode to spine
        spine["story_mode"] = _story_mode
        
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
