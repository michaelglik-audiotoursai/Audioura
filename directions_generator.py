"""
Directions Generator — museum room-to-room navigation guidance (Storied).
==========================================================================
Generates contextual directions between stops in a museum tour.
Uses GPT-3.5-turbo with explicit constraints against fabricating distances
or compass bearings inside buildings.
"""
import json
import logging
import requests

logger = logging.getLogger(__name__)


def generate_real_directions(
    from_poi: dict,
    to_poi: dict,
    api_key: str,
    venue_name: str = "",
    tour_category: str = "museum",
) -> str:
    """Generate real, grounded directions between two POIs.

    For MUSEUM tours: contextual room-to-room guidance referencing stop names.
    Never fabricates street distances, compass bearings, or walking times
    inside a building.

    Args:
        from_poi: dict with at least 'name' key (the departing stop).
        to_poi: dict with at least 'name' key (the destination stop).
        api_key: OpenAI API key.
        venue_name: The museum/venue name (for context).
        tour_category: 'museum', 'walking', 'restaurant', etc.

    Returns:
        1–3 sentences of navigation guidance. Empty string on failure.
    """
    from_name = from_poi.get("name", "the previous stop") if isinstance(from_poi, dict) else str(from_poi)
    to_name = to_poi.get("name", "the next stop") if isinstance(to_poi, dict) else str(to_poi)

    if tour_category == "museum":
        system_prompt = (
            "You write short, natural navigation cues for a museum audio guide. "
            "RULES: "
            "1. Do NOT invent street distances, compass bearings (north/south/east/west), "
            "or walking times inside a building — you don't know the floor plan. "
            "2. Reference the DESTINATION room/gallery by name. "
            "3. Use phrases like 'Continue to…', 'Head towards…', 'Look for the entrance to…', "
            "'The next gallery is…'. "
            "4. Keep it to 1–3 sentences maximum. "
            "5. Be helpful and conversational, not robotic."
        )
        user_prompt = (
            f"Museum: {venue_name}\n"
            f"You are leaving: {from_name}\n"
            f"Your next stop is: {to_name}\n\n"
            f"Write a brief, natural transition cue (1–3 sentences) guiding the listener "
            f"from '{from_name}' to '{to_name}'. Reference the destination by name."
        )
    else:
        # Walking/restaurant tours — can include real-world directions
        system_prompt = (
            "You write short walking directions between two points of interest. "
            "Keep it to 1–3 sentences. Be specific but concise."
        )
        user_prompt = (
            f"From: {from_name}\n"
            f"To: {to_name}\n\n"
            f"Write 1–3 sentences of walking directions."
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
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.6,
                "max_tokens": 150,
            },
            timeout=15,
        )

        if response.status_code != 200:
            logger.error(f"Directions API error: {response.status_code} — {response.text[:200]}")
            return ""

        result = response.json()
        text = result["choices"][0]["message"]["content"].strip()

        # Cost logging
        tokens = result.get("usage", {}).get("total_tokens", 0)
        cost = tokens / 1000 * 0.002
        logger.info(f"Directions: {from_name} → {to_name} | {tokens} tokens | ${cost:.4f}")

        return text

    except requests.Timeout:
        logger.warning(f"Directions timeout: {from_name} → {to_name}")
        return ""
    except Exception as e:
        logger.error(f"Directions error: {e}")
        return ""
