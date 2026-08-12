"""[LOCAL-442] Sentence obligation ledger — every suggestion/mention/promise must be
explained or followed.

The defect class: a sentence that writes a pointer and never dereferences it.
Generalizes feel-telling, empty positioning, atmospheric filler into one auditor.

Michael's calibration rules (2026-08-12 session, BINDING):
  1. In-sentence payment counts fully; appositives are payment.
  2. The ledger is CHAINED: a payment can open a new obligation.
  3. Grading, not gating. Score = obligations paid / obligations created.
     Paid anywhere in the stop = full credit.
  4. Unpaid hooks are story-seeking seeds (feed LOCAL-440).
  5. Definitional content counts as payment, even phrased abstractly.
  6. Repair granularity is the FRAGMENT, not the sentence.

Public API (module scope, imported by tests):
  - audit_stop_obligations(stop_text: str) -> dict
  - audit_tour_obligations(tour_text: str) -> dict
  - load_verdict_cache(verdicts: dict)
  - get_verdict_cache() -> dict
  - reset_audit_cost()
  - get_audit_cost() -> float
"""
import hashlib
import json
import logging
import os
import re
from typing import Dict, List, Optional

from cost_rates import llm_cost

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Verdict cache — SHA-256 keyed, same pattern as story_gate.py
# ---------------------------------------------------------------------------
_verdict_cache: Dict[str, dict] = {}

# Cost tracking
_audit_cost_usd = 0.0
_audit_input_tokens = 0
_audit_output_tokens = 0


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def load_verdict_cache(verdicts: dict):
    """Load pre-recorded verdicts into cache (for deterministic CI)."""
    _verdict_cache.update(verdicts)


def get_verdict_cache() -> dict:
    """Return current verdict cache (for inspection/serialisation)."""
    return dict(_verdict_cache)


def reset_audit_cost():
    """Reset cumulative cost counters."""
    global _audit_cost_usd, _audit_input_tokens, _audit_output_tokens
    _audit_cost_usd = 0.0
    _audit_input_tokens = 0
    _audit_output_tokens = 0


def get_audit_cost() -> float:
    """Return cumulative cost in USD."""
    return _audit_cost_usd


# ---------------------------------------------------------------------------
# Prompt for per-stop obligation audit
# ---------------------------------------------------------------------------

_STOP_AUDIT_PROMPT = """You are an expert writing analyst. Analyze the following audio tour stop text sentence by sentence.

For EACH sentence, determine:
1. What obligations it creates (pointers it writes). Obligation types:
   - "directive": tells the visitor to do something (position, look, notice, stand, approach). Fulfilled ONLY if the concrete where/what is in this sentence or adjacent ones.
   - "reference": mentions something specific-sounding without content ("the innovative technique", "his famous collaboration"). Fulfilled if the stop explains what/who/why.
   - "promise": asserts the visitor will perceive/gain something ("this allows you to see X"). Fulfilled if X is concretely identified.
   - "significance": claims importance ("remarkable", "masterpiece", "pivotal"). Fulfilled only if the stop supplies evidence for the claim.
   - "none": no obligation created.

2. Whether each obligation is fulfilled ANYWHERE in the stop text (not just the same sentence).

CRITICAL RULES:
- In-sentence payment counts fully. Appositives count as payment (e.g., "Louis Broder, a notable figure who specialized in artist's books" = named AND explained).
- The ledger is CHAINED: a payment can open a new obligation. Follow the chain.
- Definitional content counts as payment even phrased abstractly. If the text defines a concept, art form, or technique, that IS payload — not filler. Example: "the seamless integration of image, word, and typography as an art form" IS the livre d'artiste definition.
- A sentence can have MULTIPLE obligations. List each separately.
- Payment from anywhere in the same stop counts as fulfilled.

Return JSON (no markdown fencing):
{
  "sentences": [
    {
      "sentence": "the exact sentence text",
      "obligations": [
        {"type": "directive|reference|promise|significance|none", "claim": "what is promised/referenced", "fulfilled": true/false, "fulfilled_by": "brief note of what pays it, or null"}
      ],
      "paid_count": <number of fulfilled obligations>,
      "total_count": <number of non-none obligations>
    }
  ],
  "unfulfilled_count": <total unfulfilled obligations across all sentences>,
  "total_obligations": <total non-none obligations>,
  "score_ratio": <paid / total, as float>
}

TEXT TO ANALYZE:
"""

_TOUR_AUDIT_PROMPT = """You are an expert writing analyst. Analyze the following multi-stop audio tour for CROSS-STOP obligations — promises or references that span stops.

Look for:
- Forward promises: "as we'll see later", "more on this at the next stop", a person/theme introduced as important then dropped.
- Thematic threads introduced but never resolved across the tour.
- Important mentions in early stops never paid off in later stops.

For each cross-stop obligation found, identify:
- Which stop creates it and what is promised
- Whether any later stop fulfills it
- If unfulfilled, note it

Return JSON (no markdown fencing):
{
  "cross_stop_obligations": [
    {
      "source_stop": <stop number>,
      "claim": "what is promised/referenced",
      "fulfilled": true/false,
      "fulfilled_in_stop": <stop number or null>,
      "fulfilled_by": "brief description or null"
    }
  ],
  "unfulfilled_count": <number of unfulfilled cross-stop obligations>
}

TOUR TEXT:
"""


# ---------------------------------------------------------------------------
# Core audit functions
# ---------------------------------------------------------------------------

def audit_stop_obligations(stop_text: str) -> dict:
    """Audit a single stop's text for unfulfilled obligations.

    ONE gpt-4o-mini call per stop (temperature=0, SHA-256 verdict cache).

    Returns:
        {
          "sentences": [...],
          "unfulfilled_count": int,
          "total_obligations": int,
          "score_ratio": float,
          "cost_usd": float,
          "from_cache": bool
        }
    """
    global _audit_cost_usd, _audit_input_tokens, _audit_output_tokens

    if not stop_text or not stop_text.strip():
        return {
            "sentences": [],
            "unfulfilled_count": 0,
            "total_obligations": 0,
            "score_ratio": 1.0,
            "cost_usd": 0.0,
            "from_cache": False,
        }

    key = _cache_key(stop_text)
    if key in _verdict_cache:
        cached = _verdict_cache[key].copy()
        cached['from_cache'] = True
        cached['cost_usd'] = 0.0
        return cached

    # Call gpt-4o-mini
    import requests

    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        _log.warning("[LOCAL-442] OPENAI_API_KEY not set — cannot audit obligations")
        return {
            "sentences": [],
            "unfulfilled_count": 0,
            "total_obligations": 0,
            "score_ratio": 1.0,
            "cost_usd": 0.0,
            "from_cache": False,
            "error": "no_api_key",
        }

    prompt = _STOP_AUDIT_PROMPT + stop_text

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 2000,
        },
        timeout=60,
    )

    if response.status_code != 200:
        error_msg = response.text[:200]
        raise RuntimeError(f"OpenAI API error {response.status_code}: {error_msg}")

    data = response.json()
    usage = data.get("usage", {})
    input_tokens = usage.get("prompt_tokens", 0)
    output_tokens = usage.get("completion_tokens", 0)
    cost = llm_cost(input_tokens=input_tokens, output_tokens=output_tokens, model="gpt-4o-mini")

    _audit_cost_usd += cost
    _audit_input_tokens += input_tokens
    _audit_output_tokens += output_tokens

    content = data["choices"][0]["message"]["content"].strip()
    # Handle markdown fences
    if content.startswith('```'):
        content = content.split('\n', 1)[1].rsplit('```', 1)[0].strip()

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        _log.warning(f"[LOCAL-442] Failed to parse obligation verdict: {content[:300]}")
        parsed = {
            "sentences": [],
            "unfulfilled_count": 0,
            "total_obligations": 0,
            "score_ratio": 1.0,
        }

    result = {
        "sentences": parsed.get("sentences", []),
        "unfulfilled_count": int(parsed.get("unfulfilled_count", 0)),
        "total_obligations": int(parsed.get("total_obligations", 0)),
        "score_ratio": float(parsed.get("score_ratio", 1.0)),
        "cost_usd": cost,
        "from_cache": False,
    }

    _verdict_cache[key] = result
    return result


def audit_tour_obligations(tour_text: str) -> dict:
    """Audit a full tour for cross-stop obligations.

    ONE gpt-4o-mini call over the full tour text.

    Returns:
        {
          "cross_stop_obligations": [...],
          "unfulfilled_count": int,
          "cost_usd": float,
          "from_cache": bool
        }
    """
    global _audit_cost_usd, _audit_input_tokens, _audit_output_tokens

    if not tour_text or not tour_text.strip():
        return {
            "cross_stop_obligations": [],
            "unfulfilled_count": 0,
            "cost_usd": 0.0,
            "from_cache": False,
        }

    key = _cache_key("TOUR_LEVEL:" + tour_text)
    if key in _verdict_cache:
        cached = _verdict_cache[key].copy()
        cached['from_cache'] = True
        cached['cost_usd'] = 0.0
        return cached

    import requests

    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        _log.warning("[LOCAL-442] OPENAI_API_KEY not set — cannot audit tour obligations")
        return {
            "cross_stop_obligations": [],
            "unfulfilled_count": 0,
            "cost_usd": 0.0,
            "from_cache": False,
            "error": "no_api_key",
        }

    prompt = _TOUR_AUDIT_PROMPT + tour_text

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 1500,
        },
        timeout=60,
    )

    if response.status_code != 200:
        error_msg = response.text[:200]
        raise RuntimeError(f"OpenAI API error {response.status_code}: {error_msg}")

    data = response.json()
    usage = data.get("usage", {})
    input_tokens = usage.get("prompt_tokens", 0)
    output_tokens = usage.get("completion_tokens", 0)
    cost = llm_cost(input_tokens=input_tokens, output_tokens=output_tokens, model="gpt-4o-mini")

    _audit_cost_usd += cost
    _audit_input_tokens += input_tokens
    _audit_output_tokens += output_tokens

    content = data["choices"][0]["message"]["content"].strip()
    if content.startswith('```'):
        content = content.split('\n', 1)[1].rsplit('```', 1)[0].strip()

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        _log.warning(f"[LOCAL-442] Failed to parse tour obligation verdict: {content[:300]}")
        parsed = {
            "cross_stop_obligations": [],
            "unfulfilled_count": 0,
        }

    result = {
        "cross_stop_obligations": parsed.get("cross_stop_obligations", []),
        "unfulfilled_count": int(parsed.get("unfulfilled_count", 0)),
        "cost_usd": cost,
        "from_cache": False,
    }

    _verdict_cache[key] = result
    return result


# ---------------------------------------------------------------------------
# Utility: extract description from a stop block
# ---------------------------------------------------------------------------

_STOP_SPLIT_RE = re.compile(r'^Stop\s+\d+:', re.MULTILINE)


def extract_stop_descriptions(tour_text: str) -> List[str]:
    """Extract description paragraphs from each stop in a tour text.

    Returns a list of description texts (one per stop), stripping structural
    lines (Address, Coordinates, Orientation, Directions, Sources).
    """
    stops = _STOP_SPLIT_RE.split(tour_text)
    descriptions = []

    for stop_block in stops[1:]:  # Skip text before first "Stop N:"
        lines = stop_block.strip().splitlines()
        desc_lines = []
        in_description = False

        for line in lines:
            stripped = line.strip()
            # Skip structural lines
            if re.match(r'^(Address|Coordinates|Orientation|Directions|Sources|Tour-Category|Museum Information)\s*:', stripped, re.IGNORECASE):
                if in_description:
                    break  # Description ended
                continue
            # Empty line after content = end of description
            if not stripped and in_description:
                # Check if next non-empty is structural
                continue
            if stripped and not re.match(r'^(Address|Coordinates|Orientation|Directions|Sources)\s*:', stripped, re.IGNORECASE):
                in_description = True
                desc_lines.append(stripped)

        description = ' '.join(desc_lines).strip()
        if description:
            descriptions.append(description)

    return descriptions


# ---------------------------------------------------------------------------
# Score integration hook — unfulfilled_count as deduction
# ---------------------------------------------------------------------------

def obligation_deduction(unfulfilled_count: int, stop_word_count: int = 0) -> float:
    """Compute the score deduction from unfulfilled obligations.

    Proposed weight: -0.5 points per unfulfilled obligation, capped at -3.0
    per stop. LEAD will calibrate at review.

    Justification: Each unfulfilled obligation represents empty prose that
    takes up word budget without delivering content. At ~450 words/stop and
    typical 4-6 sentences, 2 unfulfilled obligations means ~1/3 of the stop
    is placeholder prose. -1.0 for that is proportional.
    """
    deduction_per_unfulfilled = 0.5
    max_deduction = 3.0
    return min(unfulfilled_count * deduction_per_unfulfilled, max_deduction)
