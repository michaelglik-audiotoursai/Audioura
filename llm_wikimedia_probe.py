"""
LOCAL-446 — LLM Wikimedia Probe

Measures whether LLM parametric memory can substitute for Wikimedia when it is down.
This module provides probe_llm_for_entity() which asks a model to recall structured
facts that the pipeline currently fetches from Wikidata/Wikipedia.

Three schema types match the real call sites:
  1. wbsearchentities: QID + label (venue_resolver, area_resolver)
  2. page/summary extract: plain-text summary (rag_retriever)
  3. P856 official website: domain string (work_story_searcher)

The prompt explicitly offers "I don't know" and does NOT reward guessing.
Temperature 0, structured JSON output.
"""

import json
import os
import time
import logging
from typing import Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


# The system prompt: adversarial by design.
# It explicitly tells the model that abstention is correct when uncertain.
SYSTEM_PROMPT = """\
You are a factual recall assistant. You will be asked to recall specific facts \
that exist in Wikimedia (Wikipedia and Wikidata). You must answer ONLY from what \
you are confident you know from your training data.

CRITICAL RULES:
1. If you are not confident about ANY field, set that field to null.
2. A null answer is ALWAYS preferable to a guess.
3. Do not infer, deduce, or fabricate. Only state what you clearly remember.
4. "I think it might be" = null. Only certainty counts.
5. Do NOT attempt to be helpful by guessing — an incorrect answer is a failure.

Respond with valid JSON only. No markdown, no explanation outside the JSON."""


ENTITY_PROMPT_TEMPLATE = """\
For the entity "{entity_name}", provide the following factual information \
as remembered from Wikimedia (Wikipedia/Wikidata). For any field you are \
not confident about, use null.

Return this exact JSON structure:
{{
  "qid": "<Wikidata QID like Q12345, or null if unsure>",
  "label": "<the standard English label for this entity, or null>",
  "description": "<Wikidata short description, or null>",
  "wikipedia_extract": "<first paragraph summary from English Wikipedia, or null>",
  "official_website": "<official website domain from Wikidata P856, or null>",
  "instance_of": "<primary P31 class label e.g. 'art museum', or null>",
  "country": "<country where located, or null>",
  "city": "<city where located, or null>",
  "confidence": "<high/medium/low — your overall confidence in these answers>"
}}

Entity: "{entity_name}"
"""


def probe_llm_for_entity(entity_name: str, model: str = "gpt-4o-mini") -> dict:
    """Probe an LLM for Wikimedia-equivalent data about an entity.

    Args:
        entity_name: Name of the entity to look up.
        model: OpenAI model to use.

    Returns:
        dict with keys:
            - response: parsed JSON from the model (or None on failure)
            - latency_ms: wall-clock time for the API call
            - model: model used
            - error: error message if the call failed
            - prompt_tokens: input tokens used
            - completion_tokens: output tokens used
            - raw_text: raw text response before parsing
    """
    client = _get_client()
    prompt = ENTITY_PROMPT_TEMPLATE.format(entity_name=entity_name)

    result = {
        "entity_name": entity_name,
        "model": model,
        "response": None,
        "latency_ms": None,
        "error": None,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "raw_text": "",
    }

    start = time.perf_counter()
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=1000,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        result["latency_ms"] = round(elapsed_ms, 1)

        raw_text = completion.choices[0].message.content.strip()
        result["raw_text"] = raw_text
        result["prompt_tokens"] = completion.usage.prompt_tokens
        result["completion_tokens"] = completion.usage.completion_tokens

        # Parse JSON — strip markdown fences if present
        text_to_parse = raw_text
        if text_to_parse.startswith("```"):
            lines = text_to_parse.split("\n")
            # Remove first and last lines (fences)
            lines = [l for l in lines if not l.strip().startswith("```")]
            text_to_parse = "\n".join(lines)

        parsed = json.loads(text_to_parse)
        result["response"] = parsed

    except json.JSONDecodeError as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        result["latency_ms"] = result["latency_ms"] or round(elapsed_ms, 1)
        result["error"] = f"JSON parse error: {e}"
        logger.warning(f"JSON parse error for {entity_name}: {e}")

    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        result["latency_ms"] = result["latency_ms"] or round(elapsed_ms, 1)
        result["error"] = f"{type(e).__name__}: {e}"
        logger.warning(f"API error for {entity_name} ({model}): {e}")

    return result


def probe_llm_for_entity_strict(entity_name: str, model: str = "gpt-4o-mini") -> dict:
    """Same probe but with an even stricter 'only answer if certain' system instruction.

    This measures the delta when we explicitly ask the model to be maximally conservative.
    """
    client = _get_client()
    prompt = ENTITY_PROMPT_TEMPLATE.format(entity_name=entity_name)

    strict_system = SYSTEM_PROMPT + """

ADDITIONAL CONSTRAINT: Only provide a non-null value if you would bet money on its \
correctness. If there is ANY doubt — even 5% — use null. The purpose of this test \
is to measure your abstention rate when uncertain. Abstaining is the correct behavior \
when you are not absolutely certain."""

    result = {
        "entity_name": entity_name,
        "model": model,
        "mode": "strict",
        "response": None,
        "latency_ms": None,
        "error": None,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "raw_text": "",
    }

    start = time.perf_counter()
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": strict_system},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=1000,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        result["latency_ms"] = round(elapsed_ms, 1)

        raw_text = completion.choices[0].message.content.strip()
        result["raw_text"] = raw_text
        result["prompt_tokens"] = completion.usage.prompt_tokens
        result["completion_tokens"] = completion.usage.completion_tokens

        text_to_parse = raw_text
        if text_to_parse.startswith("```"):
            lines = text_to_parse.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text_to_parse = "\n".join(lines)

        parsed = json.loads(text_to_parse)
        result["response"] = parsed

    except json.JSONDecodeError as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        result["latency_ms"] = result["latency_ms"] or round(elapsed_ms, 1)
        result["error"] = f"JSON parse error: {e}"

    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        result["latency_ms"] = result["latency_ms"] or round(elapsed_ms, 1)
        result["error"] = f"{type(e).__name__}: {e}"

    return result


# Cost per 1M tokens (as of mid-2026, approximate)
MODEL_COSTS = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
}


def estimate_cost(result: dict) -> float:
    """Estimate USD cost of a single probe call."""
    model = result.get("model", "gpt-4o-mini")
    costs = MODEL_COSTS.get(model, MODEL_COSTS["gpt-4o-mini"])
    input_cost = (result.get("prompt_tokens", 0) / 1_000_000) * costs["input"]
    output_cost = (result.get("completion_tokens", 0) / 1_000_000) * costs["output"]
    return round(input_cost + output_cost, 6)
