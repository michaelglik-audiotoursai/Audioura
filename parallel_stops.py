"""parallel_stops.py — LOCAL-649: plan → parallel write → stitch.

Behind the flag ``PARALLEL_STOPS=1`` (default OFF). When OFF this module is never
imported by the pipeline, so behaviour is byte-identical to today.

The three steps:

  PLAN  (``plan_tour``)   One LLM call AFTER stop selection. Produces the tour
                          THREAD plus, per stop: one assigned story (from that
                          stop's OWN research), a VARIED angle, a ``do_not_tell``
                          list (facts another stop owns, so no two stops tell the
                          same thing), and the ALLOWED CALLBACKS. The callback
                          budget max(1, (n+1)//3) (D636) is enforced
                          DETERMINISTICALLY after the model answers, and a callback
                          may only target an EARLIER, delivered stop.

  WRITE (``write_stops_parallel``)
                          Every stop's narration is written CONCURRENTLY (one
                          ThreadPool), each stop seeing the WHOLE plan plus its own
                          research, through the EXISTING narration prompt/contract.
                          This module does NOT own a narration prompt — the caller
                          passes the existing per-stop narration callable; the plan
                          reaches it through the pipeline's existing ``spine_stop``
                          channel (emotional_beat / unique_angle / callback), so the
                          LOCAL-617/638/640 contract is reused unchanged.

  STITCH (``stitch_plan_into_spine`` + the pipeline's own stitch)
                          Deterministic and sequential. The plan is converted into
                          the spine-arc shape the pipeline already consumes, so the
                          pipeline's existing stitch — directions from the fixed
                          order, the D533/S27 repetition pass, the D636 callback
                          ENFORCEMENT (``limit_thematic_bridges_in_text``), the
                          LOCAL-628 editor and the LOCAL-619B conclusion — runs
                          unchanged over the parallel-written stops.

The prototype's three flaws are fixed here:
  (1) more callbacks than allowed → ``enforce_callback_budget`` caps the plan to
      the budget AND the pipeline's text-level ``limit_thematic_bridges_in_text``
      still runs in stitch (belt and braces);
  (2) a stop whose stored title is an ARTIST name → ``resolve_stop_work_name``
      pulls the WORK title from the work record so the narration names the work;
  (3) every stop saying "transformation" → ``assign_varied_angles`` guarantees a
      distinct angle per stop (the plan is validated and repaired if the model
      repeats one).
"""

from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Flag ─────────────────────────────────────────────────────────────────────

FLAG_ENV = "PARALLEL_STOPS"


def is_enabled() -> bool:
    """True only when PARALLEL_STOPS=1 is explicitly set. Default OFF."""
    return os.environ.get(FLAG_ENV, "") == "1"


# ─── Callback budget (D636) — reuse the canonical function ─────────────────────

def callback_budget(n_stops: int) -> int:
    """max(1, (n_stops + 1) // 3): 3 stops → 1, 5 → 2, 8 → 3.

    Delegates to cross_stop_reference_guard.callback_budget so there is ONE
    definition of the budget in the codebase. Falls back to the identical formula
    if that module cannot be imported (keeps the planner usable in isolation/tests).
    """
    try:
        from cross_stop_reference_guard import callback_budget as _cb
        return _cb(n_stops)
    except Exception:
        return max(1, (int(n_stops or 0) + 1) // 3)


# ─── Varied angles (fix 3) ─────────────────────────────────────────────────────

# A deterministic palette of distinct narrative angles. The planner asks the model
# for a varied angle per stop; if it repeats one (the prototype's "transformation"
# everywhere), assign_varied_angles repairs the collision from this palette so no
# two stops share an angle.
_ANGLE_PALETTE = [
    "the maker's hand and technique",
    "the moment of commission or creation",
    "a human conflict or rivalry behind it",
    "its journey — how it arrived here",
    "the material and what it reveals",
    "a single telling detail most visitors miss",
    "its place in a larger movement or era",
    "the people who used, owned, or saw it",
    "a reversal or surprise in its story",
    "what it meant to its first audience",
]


def _norm_angle(a: str) -> str:
    return re.sub(r"\s+", " ", (a or "").strip().lower())


def assign_varied_angles(angles: List[str]) -> List[str]:
    """Return a list the same length as ``angles`` with NO two equal angles.

    Keeps the first occurrence of each distinct angle; replaces any later
    duplicate (or empty) with the next unused angle from ``_ANGLE_PALETTE``, then
    with a numbered fallback if the palette is exhausted. Deterministic.
    """
    out: List[str] = []
    used = set()
    palette_i = 0
    for raw in angles:
        a = (raw or "").strip()
        key = _norm_angle(a)
        if a and key not in used:
            out.append(a)
            used.add(key)
            continue
        # collision or empty — pick the next unused palette angle
        chosen = None
        while palette_i < len(_ANGLE_PALETTE):
            cand = _ANGLE_PALETTE[palette_i]
            palette_i += 1
            if _norm_angle(cand) not in used:
                chosen = cand
                break
        if chosen is None:
            n = 1
            while _norm_angle(f"a distinct angle ({n})") in used:
                n += 1
            chosen = f"a distinct angle ({n})"
        out.append(chosen)
        used.add(_norm_angle(chosen))
    return out


# ─── Work-name resolution (fix 2) ──────────────────────────────────────────────

# Stored stop titles that are really an ARTIST name (Courtauld "Georges Seurat")
# must be shown as the WORK ("Young Woman Powdering Herself"). We resolve the work
# title from the stop's work record when the stored title matches the record's
# creator rather than its title.

def resolve_stop_work_name(poi: Dict[str, Any],
                           work_record: Optional[Dict[str, Any]]) -> Optional[str]:
    """Return the WORK title to narrate for ``poi`` when its stored title is an
    artist name, else None (keep the stored title).

    ``work_record`` is the matched exhibition-checklist / catalogue work dict
    (title, creator/artist, …) as produced by generate_tour_text.match_work_for_stop.
    When the stored stop title equals the record's creator (and the record has a
    distinct title), the title is returned so the caller can narrate the work.
    """
    if not isinstance(poi, dict) or not isinstance(work_record, dict):
        return None
    stored = (poi.get("name") or "").strip()
    title = (work_record.get("title") or "").strip()
    creator = (work_record.get("creator") or work_record.get("artist") or "").strip()
    if not stored or not title:
        return None

    def _n(s: str) -> str:
        return re.sub(r"[^a-z0-9 ]+", "", (s or "").lower()).strip()

    # Only override when the stored title clearly IS the artist, not the work.
    if creator and _n(stored) == _n(creator) and _n(title) != _n(stored):
        return title
    # Also handle "Artist" stored where title contains the artist but differs.
    if creator and _n(stored) == _n(creator) and _n(title):
        return title
    return None


# ─── Callback budget enforcement (fix 1) ───────────────────────────────────────

def enforce_callback_budget(plan_stops: List[Dict[str, Any]],
                            n_stops: Optional[int] = None) -> List[Dict[str, Any]]:
    """Cap and legalise the callbacks across a plan DETERMINISTICALLY.

    Rules (D636):
      * a callback may only target an EARLIER stop (``target`` index < this stop's
        index); forward/self references are dropped;
      * the WHOLE tour keeps at most ``callback_budget(n)`` callbacks; the earliest
        legal callbacks (by stop order) are kept, the rest dropped;
      * each surviving stop keeps at most one callback (continuity, not clutter).

    Mutates copies; returns a new list of stop dicts with a cleaned ``callbacks``
    list (each item: {"target": int, "note": str}). Pure given its input.
    """
    stops = [dict(s) for s in plan_stops]
    n = int(n_stops if n_stops is not None else len(stops))
    budget = callback_budget(n)
    kept_total = 0
    for i, s in enumerate(stops):
        legal: List[Dict[str, Any]] = []
        for cb in (s.get("callbacks") or []):
            try:
                tgt = int(cb.get("target"))
            except (TypeError, ValueError):
                continue
            if tgt < 0 or tgt >= i:          # only earlier, delivered stops
                continue
            legal.append({"target": tgt, "note": (cb.get("note") or "").strip()})
        # at most one callback per stop
        legal = legal[:1]
        # tour-wide budget
        if legal and kept_total < budget:
            s["callbacks"] = [legal[0]]
            kept_total += 1
        else:
            s["callbacks"] = []
    return stops


# ─── do_not_tell derivation ────────────────────────────────────────────────────

def derive_do_not_tell(plan_stops: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ensure each stop carries a ``do_not_tell`` list of the OTHER stops' owned
    facts, so no two stops tell the same thing.

    If the model already supplied ``do_not_tell`` it is kept and augmented; the
    augmentation is every OTHER stop's ``assigned_story`` headline / owned facts.
    Deterministic.
    """
    stops = [dict(s) for s in plan_stops]
    owned: List[List[str]] = []
    for s in stops:
        facts: List[str] = []
        story = (s.get("assigned_story") or "").strip()
        if story:
            facts.append(story)
        for f in (s.get("owned_facts") or []):
            f = (f or "").strip()
            if f:
                facts.append(f)
        owned.append(facts)
    for i, s in enumerate(stops):
        dnt = list(s.get("do_not_tell") or [])
        seen = {_norm_angle(x) for x in dnt}
        for j, facts in enumerate(owned):
            if j == i:
                continue
            for f in facts:
                k = _norm_angle(f)
                if k and k not in seen:
                    dnt.append(f)
                    seen.add(k)
        s["do_not_tell"] = dnt
    return stops


# ─── Plan validation ───────────────────────────────────────────────────────────

class PlanValidationError(ValueError):
    pass


def validate_plan(plan: Dict[str, Any], n_stops: int) -> Dict[str, Any]:
    """Validate and NORMALISE a plan dict. Raises PlanValidationError on a shape
    that cannot be repaired; otherwise returns a plan guaranteed to satisfy:

      * ``thread`` is a non-empty string;
      * ``stops`` has exactly ``n_stops`` entries;
      * every stop has a non-empty ``assigned_story`` and ``angle``;
      * angles are all distinct (repaired via assign_varied_angles);
      * ``callbacks`` obey the D636 budget and point only at earlier stops;
      * every stop has a ``do_not_tell`` list.
    """
    if not isinstance(plan, dict):
        raise PlanValidationError("plan is not a dict")
    thread = (plan.get("thread") or "").strip()
    if not thread:
        raise PlanValidationError("plan.thread is empty")
    stops = plan.get("stops")
    if not isinstance(stops, list) or len(stops) != n_stops:
        raise PlanValidationError(
            f"plan.stops must have {n_stops} entries, got "
            f"{len(stops) if isinstance(stops, list) else type(stops).__name__}")

    norm: List[Dict[str, Any]] = []
    for i, s in enumerate(stops):
        if not isinstance(s, dict):
            raise PlanValidationError(f"stop {i} is not a dict")
        story = (s.get("assigned_story") or "").strip()
        if not story:
            raise PlanValidationError(f"stop {i} has empty assigned_story")
        norm.append({
            "index": i,
            "title": (s.get("title") or "").strip(),
            "assigned_story": story,
            "angle": (s.get("angle") or "").strip(),
            "owned_facts": [f for f in (s.get("owned_facts") or []) if (f or "").strip()],
            "do_not_tell": [f for f in (s.get("do_not_tell") or []) if (f or "").strip()],
            "callbacks": list(s.get("callbacks") or []),
            "cliffhanger": (s.get("cliffhanger") or "").strip(),
        })

    # fix 3: varied angles
    repaired = assign_varied_angles([s["angle"] for s in norm])
    for s, a in zip(norm, repaired):
        s["angle"] = a

    # fix 1: callback budget + earlier-only
    norm = enforce_callback_budget(norm, n_stops)

    # do_not_tell completeness
    norm = derive_do_not_tell(norm)

    return {"thread": thread, "stops": norm}


# ─── PLAN LLM call ─────────────────────────────────────────────────────────────

_PLAN_SYSTEM = (
    "You are the lead planner for a spoken audio tour. You design the shape of the "
    "whole tour BEFORE any stop is written, so that each stop can be written "
    "independently and in parallel without repeating another stop or contradicting it."
)


def build_plan_prompt(venue_name: str,
                      stops: List[Dict[str, Any]],
                      n_stops: int) -> str:
    """Build the single planning prompt. ``stops`` is the ordered list of per-stop
    research summaries: each a dict with 'title' and 'research' (that stop's OWN
    research text). The model is told the callback budget and the earlier-only rule
    so its answer starts legal; enforce_callback_budget guarantees it after."""
    budget = callback_budget(n_stops)
    lines = [
        f"Venue: {venue_name}",
        f"Number of stops: {n_stops}",
        "",
        "Each stop below has its OWN research. Using ONLY each stop's own research, "
        "produce a tour plan as STRICT JSON.",
        "",
    ]
    for i, s in enumerate(stops):
        title = (s.get("title") or f"Stop {i+1}").strip()
        research = (s.get("research") or "").strip()
        if len(research) > 1500:
            research = research[:1500] + " …"
        lines.append(f"STOP {i} — {title}")
        lines.append(f"  research: {research or '(none provided)'}")
        lines.append("")
    lines += [
        "Return JSON with this exact shape:",
        "{",
        '  "thread": "<one sentence naming the single thread that connects all stops>",',
        '  "stops": [',
        "    {",
        '      "index": <int, 0-based, matching the STOP number above>,',
        '      "title": "<the stop title>",',
        '      "assigned_story": "<the ONE story this stop tells, drawn ONLY from its own research>",',
        '      "angle": "<a DISTINCT narrative angle for this stop — no two stops may share an angle>",',
        '      "owned_facts": ["<the specific facts THIS stop owns — other stops must not tell them>"],',
        '      "callbacks": [{"target": <index of an EARLIER stop>, "note": "<what to call back to>"}],',
        '      "cliffhanger": "<optional one-line forward hook to the next stop>"',
        "    }",
        "  ]",
        "}",
        "",
        "HARD RULES:",
        f"  - Give each stop a DIFFERENT angle. Do not make every stop about the same idea "
        f"(e.g. not every stop about 'transformation').",
        f"  - Callbacks may reference ONLY an EARLIER stop (a smaller index). Never a later "
        f"stop, never itself.",
        f"  - Use AT MOST {budget} callback(s) across the WHOLE tour (continuity, not clutter).",
        "  - assigned_story and owned_facts for a stop must come ONLY from that stop's own research.",
        "  - Output ONLY the JSON. No prose before or after.",
    ]
    return "\n".join(lines)


def _default_plan_llm(prompt: str, api_key: str) -> Optional[str]:
    """House planner LLM call. Returns the raw content string, or None on failure.
    Priced/attributed via the pipeline's cost wrapper when available."""
    import requests
    model = os.environ.get("PLAN_LLM_MODEL") or os.environ.get("WRITE_LLM_MODEL") or "gpt-4o-mini"
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            data=json.dumps({
                "model": model,
                "messages": [
                    {"role": "system", "content": _PLAN_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.4,
                "max_tokens": 1500,
                "response_format": {"type": "json_object"},
            }),
            timeout=60,
        )
        if resp.status_code != 200:
            logger.error("[LOCAL-649] plan LLM error %s: %s",
                         resp.status_code, resp.text[:200])
            return None
        data = resp.json()
        # best-effort cost attribution
        try:
            from cost_rates import llm_cost as _llm_cost
            _tok = data.get("usage", {}).get("total_tokens", 0)
            _c = _llm_cost(total_tokens=_tok)
            logger.info("[LOCAL-649] plan: %s tokens, $%.4f", _tok, _c)
            global LAST_PLAN_COST
            LAST_PLAN_COST = {"total_tokens": _tok, "cost_usd": _c, "model": model}
        except Exception:
            pass
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error("[LOCAL-649] plan LLM failed: %s", e)
        return None


LAST_PLAN_COST: Dict[str, Any] = {"total_tokens": 0, "cost_usd": 0.0, "model": ""}


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    text = text.strip()
    # strip ```json fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        pass
    # last resort: first {...} block
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def plan_tour(venue_name: str,
              stops: List[Dict[str, Any]],
              api_key: str,
              llm_fn: Optional[Callable[[str, str], Optional[str]]] = None
              ) -> Dict[str, Any]:
    """Run the PLAN step: one LLM call, validated and legalised.

    ``stops`` — ordered list of per-stop research dicts ({'title','research'}).
    Returns a validated plan dict {thread, stops:[{index,title,assigned_story,
    angle,owned_facts,do_not_tell,callbacks,cliffhanger}]}. Raises
    PlanValidationError if the model's output cannot be validated.
    """
    n = len(stops)
    if n == 0:
        raise PlanValidationError("no stops to plan")
    prompt = build_plan_prompt(venue_name, stops, n)
    fn = llm_fn or _default_plan_llm
    raw = fn(prompt, api_key)
    plan = _extract_json(raw or "")
    if plan is None:
        raise PlanValidationError("plan LLM returned no parseable JSON")
    # Fill missing titles from the research list before validating.
    if isinstance(plan.get("stops"), list):
        for i, s in enumerate(plan["stops"]):
            if isinstance(s, dict) and not (s.get("title") or "").strip() and i < n:
                s["title"] = stops[i].get("title", "")
    return validate_plan(plan, n)


# ─── STITCH: plan → spine-arc shape the pipeline already consumes ──────────────

def plan_to_spine_arc(plan: Dict[str, Any],
                      poi_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert a validated plan into the ``arc`` list of spine_stop dicts the
    existing narration prompt already injects (emotional_beat / unique_angle /
    callback / cliffhanger). This lets the parallel-written stops flow through the
    EXISTING prompt channel — no new narration prompt.

    The callback NOTE names the EARLIER stop's title (by index into poi_list) so
    the narration references a delivered stop BY NAME, exactly as the existing
    cross-stop callback contract requires.
    """
    arc: List[Dict[str, Any]] = []
    pstops = plan.get("stops", [])
    for i, ps in enumerate(pstops):
        callback_text = ""
        cbs = ps.get("callbacks") or []
        if cbs:
            tgt = cbs[0].get("target")
            note = (cbs[0].get("note") or "").strip()
            tgt_name = ""
            if isinstance(tgt, int) and 0 <= tgt < len(poi_list):
                tgt_name = (poi_list[tgt].get("name") or "").strip()
            if tgt_name:
                callback_text = f"{tgt_name}: {note}" if note else tgt_name
            elif note:
                callback_text = note
        dnt = ps.get("do_not_tell") or []
        emotional_beat = ps.get("assigned_story", "")
        if dnt:
            # Fold the do_not_tell list into the angle channel as an explicit
            # instruction; the existing prompt renders unique_angle verbatim.
            avoid = "; ".join(dnt[:4])
            unique_angle = (f"{ps.get('angle','')} "
                            f"(Do NOT tell these — they belong to other stops: {avoid})")
        else:
            unique_angle = ps.get("angle", "")
        arc.append({
            "emotional_beat": emotional_beat,
            "unique_angle": unique_angle,
            "callback": callback_text,
            "cliffhanger": ps.get("cliffhanger", ""),
        })
    return arc


# ─── WRITE: concurrent narration reusing the caller's narration unit ───────────

def write_stops_parallel(poi_list: List[Dict[str, Any]],
                         spine_arc: List[Dict[str, Any]],
                         generate_description: Callable[[Tuple], Tuple],
                         executor_factory: Callable[..., Any],
                         max_workers: Optional[int] = None,
                         fact_sheets: Optional[List[Any]] = None
                         ) -> List[Dict[str, Any]]:
    """Write every stop's narration CONCURRENTLY, each with its plan context, by
    submitting the caller's EXISTING ``generate_description`` closure to a
    ThreadPool (the pipeline's ``tour_executor``). Reuses the existing narration
    prompt/contract entirely — this function only schedules it with plan context.

    ``generate_description`` has the pipeline's signature:
        args = (i, poi, spine_stop, fact_sheet, story_type)
        returns (idx, orientation, description, word_count, tokens_used, call_cost)

    Returns ``poi_list`` with each stop's 'orientation'/'description'/'word_count'
    populated (mutated in place, and returned for convenience).
    """
    if max_workers is None:
        max_workers = min(len(poi_list), 5) or 1
    facts = fact_sheets or []
    with executor_factory(max_workers=max_workers) as executor:
        futures = {}
        for i, poi in enumerate(poi_list):
            spine_stop = spine_arc[i] if i < len(spine_arc) else None
            fact_sheet = facts[i] if i < len(facts) else None
            story_type = poi.get("story_type")
            futures[executor.submit(
                generate_description, (i, poi, spine_stop, fact_sheet, story_type))] = i
        for fut in as_completed(futures):
            idx, orientation, description, word_count, tokens_used, call_cost = fut.result()
            if description:
                description = re.sub(r"^Stop\s+\d+:\s*", "", description,
                                     flags=re.IGNORECASE | re.MULTILINE).strip()
            poi_list[idx]["orientation"] = orientation
            poi_list[idx]["description"] = description
            poi_list[idx]["word_count"] = word_count
            poi_list[idx]["_parallel_tokens"] = tokens_used
            poi_list[idx]["_parallel_cost"] = call_cost
    return poi_list
