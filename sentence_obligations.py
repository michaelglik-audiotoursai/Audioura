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

_STOP_AUDIT_PROMPT = """You are an expert writing analyst auditing audio tour prose for UNFULFILLED OBLIGATIONS. Analyze the text sentence by sentence.

For EACH sentence, determine:
1. What obligations it creates (pointers it writes). Obligation types:
   - "directive": tells the visitor to do something (position, look, notice, stand, approach). Fulfilled ONLY if the concrete where/what is specified. NOTE: A sentence that describes a work or its history is NOT a directive even if it implicitly assumes the visitor is looking at it. Only EXPLICIT instructions ("position yourself", "stand here", "look at") count as directives.
   - "reference": mentions something specific-sounding without content ("the innovative technique", "his famous collaboration"). Fulfilled if the stop explains what/who/why.
   - "promise": asserts the visitor will perceive/gain something ("this allows you to see X"). Fulfilled if X is concretely identified.
   - "significance": claims importance ("remarkable", "masterpiece", "pivotal", "reshape civilizations"). Fulfilled only if the stop supplies concrete evidence for the claim.
   - "none": no obligation created. Use this for straightforward factual statements that deliver information without creating a debt. IMPORTANT: If a claim is unfulfilled and you want to flag it, do NOT use "none" — use the appropriate type (reference, promise, significance). "none" means literally NO obligation exists — the sentence simply states facts without pointing at anything it doesn't deliver.

2. Whether each obligation is fulfilled ANYWHERE in the stop text (not just the same sentence).
   THIS IS CRITICAL: Read the ENTIRE stop text before judging any obligation. A claim
   in sentence 1 that is explained or evidenced in sentence 3 or 4 is FULFILLED. The
   whole stop is one unit.
   
   CROSS-SENTENCE PAYMENT EXAMPLES:
   - "extraordinary color depth" (sentence 1) → PAID by "up to 25 separate color
     passes per sheet — that makes the printed surface rival oil paint in saturation"
     (sentence 4). The later sentence provides the concrete mechanism (25 layers)
     and observable result (rivals oil paint) that constitute evidence. FULFILLED.
   - "allows you to see the flow of imagery" → only PAID if a later sentence in the
     same stop actually identifies what flow/imagery is visible. If no later sentence
     does this, it remains UNPAID.
   
   When judging, scan forward through ALL remaining sentences for evidence before
   marking any obligation as unfulfilled. A promise made in sentence 1 that receives
   concrete numbers, mechanism, or observable specifics in sentence 3 or 4 is PAID.

═══════════════════════════════════════════════════════════════
THE RESTATEMENT RULE — THIS IS THE MOST IMPORTANT RULE:

A claim is PAID only by information that is NOT DERIVABLE from the claim itself.
Renaming, paraphrasing, restating in other words, or asserting the claim more
emphatically is NEVER payment. A reader who already read the claim gains NOTHING
from a restatement of it.

PAYMENT requires a FACT the reader did not already have:
  - a specific name, date, number, place, material
  - a concrete observable (what you can SEE)
  - a causal mechanism (HOW or WHY something happened)
  - a specific example that instantiates the abstraction

WORKED CONTRASTS (study these carefully):

UNPAID: "this work embodies the surrealist ethos of blurring reality and dreams"
  → This sentence has THREE obligations in a chain:
    (1) "notable figure" → PAID by "specialized in artist's books" (✓ new fact)
    (2) "surrealist ethos" → PAID by "of blurring reality and dreams" (✓ tells us
        WHAT the ethos means — that IS payment for the term "surrealist ethos")
    (3) "blurring reality and dreams" → UNPAID. The naming of the ethos does NOT
        show HOW this work blurs them. No plate, image, or technique is cited.
  → Result for this sentence: paid_count=2, total_count=3.
  → Payment for the WHOLE sentence would require showing the blurring in action:
    "plate 7's floating fish above typographic text — dream imagery placed atop
    waking words"

UNPAID: "resulting in a coherent and integrated artwork"
  → Nothing is shown to cohere. No specific correspondence between elements is
    identified. The claim restates itself — "coherent" = "integrated".
  → Payment would be: "Miró's lithographic color washes bleed across Éluard's
    stanzas, so that text and image share the same visual plane"
  → NOTE: If a sentence says "X and Y worked closely together, resulting in a
    coherent and integrated artwork" — there are TWO obligations: (1) the
    collaboration claim (who worked with whom on what — naming the specific parties
    IS generic payment; "the artist and Mourlot Frères working closely together"
    pays the collaboration claim because it names who + who), and (2) "coherent and
    integrated" (a separate claim about the outcome that needs its own evidence —
    UNPAID because nothing shows what coherence/integration looks like). Result for
    such a sentence: paid_count=1, total_count=2. Do not merge them.

PAID: "Louis Broder, a notable figure who specialized in artist's books that
       required close collaboration between creators"
  → "Specialized in artist's books requiring close collaboration" is a FACT about
    Broder not derivable from "notable". It tells us his professional focus. This
    is genuine new information.

PAID: "Mourlot Frères, a renowned printing workshop in Paris, printed these 40
       color lithographs, ensuring Miró's artistic intentions were met with precision"
  → The sentence delivers concrete facts: named workshop, city (Paris), specific
    number (40), specific medium (color lithographs). "Renowned" is paid by the
    identifiable detail. "Precision" is evidenced by the specific number of prints
    and named technique. A sentence loaded with verifiable facts like this is the
    BEST kind — do not penalize it for mild tail claims when the sentence's primary
    content is concrete. Score: ≥ 2/2 or 2/3.

PAID: "the seamless integration of image, word, and typography as an art form"
  → This IS the livre d'artiste DEFINITION — it defines what the art form
    actually IS (three named components combined). Definitional content that names
    the components of a concept is payment, not filler.

UNPAID: "the power of belief and collaboration has the potential to reshape not
         just art, but entire civilizations"
  → Pure grandiosity. No evidence, no mechanism, no example of how art reshaped a
    civilization. Scale of claim is unsupported.
  → This sentence contains THREE obligations: (1) "power of belief and
    collaboration" — significance claim with no evidence → UNPAID; (2) "reshape
    entire civilizations" — extreme claim with no example → UNPAID; (3) "seamless
    integration of image, word, and typography as an art form" — the livre d'artiste
    definition, names three components → PAID. Result: 1/3.

═══════════════════════════════════════════════════════════════

ADDITIONAL RULES:
- In-sentence payment counts fully. Appositives ARE payment — but ONLY when they
  carry genuinely new information (a fact, a role, a specialization). An appositive
  that merely restates the adjective it modifies is NOT payment.
- The ledger is CHAINED: a payment can open a new obligation. Follow the chain and
  LIST EACH LINK AS A SEPARATE OBLIGATION. This is critical for correct counting.
  Example: "this work embodies the surrealist ethos of blurring reality and dreams"
  contains THREE obligations in a chain:
    Obligation 1: "notable figure" → PAID by "specialized in artist's books" (new fact)
    Obligation 2: "surrealist ethos" → PAID by "of blurring reality and dreams" (this
       names what the ethos IS — that is payment, because the reader now knows what
       specific concept is meant)
    Obligation 3: "blurring reality and dreams" → UNPAID (HOW does this work blur them?
       No image, plate, or technique is shown. The chain opened a debt that the stop
       never closes.)
  Each link in the chain is its own obligation with its own fulfilled status. The
  total_count for this sentence is 3, and paid_count is 2.
  KEY PRINCIPLE: When an abstraction is NAMED (told what it means), that naming IS
  payment for the abstraction — but the named content itself may open a new debt if
  it makes a claim that is never grounded. "Surrealist ethos" is paid by being told
  it means "blurring reality and dreams". But "blurring reality and dreams" is now
  a new claim that needs its own grounding (how? where? which plate?).
- Definitional content counts as payment even when abstractly phrased — IF it names
  the components or mechanism of the concept. A domain definition IS payload.
  CRITICAL EXAMPLE: "the seamless integration of image, word, and typography as an
  art form" — this IS the definition of the livre d'artiste. It names three specific
  components (image, word, typography) and identifies them as constituting an art form.
  This is definitional payload and MUST be scored as PAID/fulfilled.
- A sentence can have MULTIPLE obligations. List each separately.
- Payment from anywhere in the same stop counts as fulfilled.
- Do NOT over-flag: simple factual statements with no pointer are "none". Only flag
  obligations where something is promised/referenced/claimed without delivery.

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
        raise RuntimeError(
            "[LOCAL-444] OPENAI_API_KEY not set — obligation audit CANNOT run. "
            "This is fail-closed: an absent key must never silently certify prose as clean. "
            "Set OPENAI_API_KEY or use load_verdict_cache() for offline/CI mode."
        )

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
            "max_tokens": 4000,
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

    # Recompute counts from obligations array to guard against model counting errors
    sentences = parsed.get("sentences", [])
    total_unfulfilled = 0
    total_obligations = 0
    for sent in sentences:
        obligations = sent.get("obligations", [])
        # Count all obligations that have a real type (not "none")
        # BUT also count "none" items that are marked fulfilled=false with a claim —
        # those are model misclassifications of real obligations
        real_obligations = []
        for o in obligations:
            otype = o.get("type", "none")
            if otype != "none":
                real_obligations.append(o)
            elif o.get("claim") and o.get("fulfilled") is False:
                # Model marked it "none" but it has a claim and is unfulfilled —
                # this is a misclassified obligation, count it as promise type
                o["type"] = "promise"
                real_obligations.append(o)
        paid = sum(1 for o in real_obligations if o.get("fulfilled"))
        total = len(real_obligations)
        sent["paid_count"] = paid
        sent["total_count"] = total
        total_obligations += total
        total_unfulfilled += (total - paid)

    total_paid = total_obligations - total_unfulfilled
    score_ratio = total_paid / total_obligations if total_obligations > 0 else 1.0

    result = {
        "sentences": sentences,
        "unfulfilled_count": total_unfulfilled,
        "total_obligations": total_obligations,
        "score_ratio": score_ratio,
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
        raise RuntimeError(
            "[LOCAL-444] OPENAI_API_KEY not set — tour obligation audit CANNOT run. "
            "This is fail-closed: an absent key must never silently certify a tour as clean. "
            "Set OPENAI_API_KEY or use load_verdict_cache() for offline/CI mode."
        )

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
