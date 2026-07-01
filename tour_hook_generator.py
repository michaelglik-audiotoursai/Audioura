"""
Tour Hook Generator — expands spine tour_hook into spoken introduction.
========================================================================
Task [S37]: generate_tour_hook_audio(tour_hook, api_key) → 40-60 word
compelling introduction paragraph in second-person present tense.
"""
import logging
import requests

logger = logging.getLogger(__name__)


def generate_tour_hook_audio(tour_hook: str, api_key: str) -> str:
    """Expand a spine tour_hook into a 40-60 word spoken introduction.

    Args:
        tour_hook: The tour_hook string from spine JSON (a compelling statement or question).
        api_key: OpenAI API key.

    Returns:
        A 40-60 word spoken introduction paragraph in second-person present tense.
        Does not end with a question mark. Establishes mystery or stakes.
        Returns empty string on failure.
    """
    if not tour_hook or not api_key:
        return ""

    prompt = f"""Expand this tour hook into a compelling 40-60 word spoken introduction paragraph:

"{tour_hook}"

Requirements:
- Write in second-person present tense ("You are standing...", "You find yourself...")
- Establish a sense of mystery, discovery, or stakes
- Do NOT end with a question mark — make it a statement that creates anticipation
- Keep it exactly 40-60 words
- Make the listener feel they are about to experience something extraordinary

Return ONLY the paragraph, no quotes or commentary."""

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
                    {"role": "system", "content": "You write vivid, immersive audio tour introductions."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.8,
                "max_tokens": 150,
            },
            timeout=15,
        )

        if response.status_code != 200:
            logger.error(f"Tour hook API error: {response.status_code}")
            return ""

        result = response.json()
        text = result["choices"][0]["message"]["content"].strip()

        # Strip any surrounding quotes
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1].strip()

        # Log cost
        usage = result.get("usage", {})
        tokens = usage.get("total_tokens", 0)
        cost = tokens / 1000 * 0.002
        logger.info(f"Tour hook: {tokens} tokens, ${cost:.4f}")

        return text

    except requests.Timeout:
        logger.error("Tour hook generation timed out")
        return ""
    except Exception as e:
        logger.error(f"Tour hook generation error: {e}")
        return ""
