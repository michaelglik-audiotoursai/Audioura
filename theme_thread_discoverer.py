"""
Theme Thread Discoverer — SQ-S6b implementation.
=================================================
Discovers cross-stop narrative threads from story elements, scores them,
and produces thread-conditioned context for the spine and per-stop descriptions.

Design: STORY_QUALITY_DESIGN.md §SQ-S6b (Michael's directive, 2026-07-07).

Flow:
  1. Deterministic entity-overlap pass across stops
  2. One LLM pass naming candidate themes (must cite supporting element IDs)
  3. Theme scoring: coverage, evidence strength, distinctiveness, arc potential
  4. Multi-thread blending with coverage-proportional weights
  5. Degradation: no theme ≥60% coverage → organizing-principle or mosaic mode

LOCAL-37 (element class tagging) has NOT merged; working against existing
element fields: type, text, people, dates, corroboration_status, source_url.
"""
import json
import logging
import os
import re
import time
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# ---------- constants ----------
MIN_COVERAGE_THRESHOLD = 0.60  # below this → degradation
MAX_THREADS = 5                # never score more than this many
IDEAL_THREADS = 3              # target for blending

# Evidence strength weights for scoring
EVIDENCE_WEIGHTS = {
    "documented": 1.0,
    "reported": 0.6,
    "legend": 0.3,
    "disputed": 0.4,
}


# ---------- data structures ----------

class ThemeThread:
    """A candidate cross-stop narrative thread."""

    def __init__(self, name: str, description: str, supporting_elements: List[str],
                 stops_covered: List[int], grounded_on: List[str]):
        self.name = name
        self.description = description
        self.supporting_elements = supporting_elements  # element IDs
        self.stops_covered = stops_covered              # stop indices (0-based)
        self.grounded_on = grounded_on                  # element IDs that ground the theme claim
        # Scores (populated by score_themes)
        self.coverage = 0.0
        self.evidence_strength = 0.0
        self.distinctiveness = 0.0
        self.arc_potential = 0.0
        self.total_score = 0.0
        self.weight = 0.0  # coverage-proportional weight after blending

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "supporting_elements": self.supporting_elements,
            "stops_covered": self.stops_covered,
            "grounded_on": self.grounded_on,
            "coverage": round(self.coverage, 3),
            "evidence_strength": round(self.evidence_strength, 3),
            "distinctiveness": round(self.distinctiveness, 3),
            "arc_potential": round(self.arc_potential, 3),
            "total_score": round(self.total_score, 3),
            "weight": round(self.weight, 3),
        }


class ThreadDiscoveryResult:
    """Complete result of theme thread discovery."""

    def __init__(self):
        self.threads: List[ThemeThread] = []
        self.mode: str = "mosaic"  # "threaded" | "organizing_principle" | "mosaic"
        self.organizing_principle: str = ""  # when mode != threaded
        self.per_stop_thread_context: List[Dict] = []  # one dict per stop
        self.prolog_promise: str = ""
        self.epilog_payoff: str = ""

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "threads": [t.to_dict() for t in self.threads],
            "organizing_principle": self.organizing_principle,
            "per_stop_thread_context": self.per_stop_thread_context,
            "prolog_promise": self.prolog_promise,
            "epilog_payoff": self.epilog_payoff,
        }


# ---------- Step 1: Deterministic entity-overlap clustering ----------

def _extract_entities_from_element(element: dict) -> Dict[str, set]:
    """Extract named entities from a story element for overlap detection.

    Returns dict with keys: people, dates, places, events, materials, eras.
    """
    entities = {
        "people": set(),
        "dates": set(),
        "places": set(),
        "events": set(),
        "materials": set(),
        "eras": set(),
    }

    # Direct fields
    for p in element.get("people", []):
        if p and len(p) > 2:
            entities["people"].add(p.strip().lower())

    for d in element.get("dates", []):
        if d:
            entities["dates"].add(str(d).strip())

    # Parse text for additional entities
    text = element.get("text", "")
    if not text:
        return entities

    # Extract years/centuries
    years = re.findall(r'\b(1[0-9]{3}|20[0-2][0-9])\b', text)
    for y in years:
        entities["dates"].add(y)
        # Derive era from year
        century = (int(y) - 1) // 100 + 1
        entities["eras"].add(f"{century}th century")

    # Extract proper nouns (capitalized multi-word sequences)
    proper_nouns = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', text)
    for pn in proper_nouns:
        if len(pn) > 3 and pn.lower() not in {'the', 'this', 'that', 'these', 'those'}:
            # Heuristic: if it looks like a person name (2+ words, not too long)
            words = pn.split()
            if 2 <= len(words) <= 4:
                entities["people"].add(pn.lower())

    return entities


def _compute_entity_overlap_clusters(
    elements_per_stop: Dict[int, List[dict]],
    total_stops: int,
) -> List[Dict]:
    """Deterministic entity-overlap pass: find shared entities across ≥2 stops.

    Returns list of cluster dicts:
        {entity: str, entity_type: str, stops: [int], element_ids: [str]}
    """
    # Build entity→stops+elements map
    entity_index: Dict[str, Dict] = {}  # key = "type:entity" → {stops: set, element_ids: set}

    for stop_idx, elements in elements_per_stop.items():
        for elem in elements:
            entities = _extract_entities_from_element(elem)
            elem_id = elem.get("id", "?")
            for etype, eset in entities.items():
                for entity in eset:
                    key = f"{etype}:{entity}"
                    if key not in entity_index:
                        entity_index[key] = {"stops": set(), "element_ids": set(), "entity": entity, "type": etype}
                    entity_index[key]["stops"].add(stop_idx)
                    entity_index[key]["element_ids"].add(elem_id)

    # Filter: only entities appearing in ≥2 stops
    clusters = []
    for key, data in entity_index.items():
        if len(data["stops"]) >= 2:
            clusters.append({
                "entity": data["entity"],
                "entity_type": data["type"],
                "stops": sorted(data["stops"]),
                "element_ids": sorted(data["element_ids"]),
                "coverage": len(data["stops"]) / total_stops,
            })

    # Sort by coverage descending
    clusters.sort(key=lambda c: (-c["coverage"], -len(c["element_ids"])))
    return clusters


# ---------- Step 2: LLM theme naming ----------

def _llm_name_themes(
    elements_per_stop: Dict[int, List[dict]],
    entity_clusters: List[Dict],
    poi_names: List[str],
    venue_name: str,
    api_key: str,
    total_stops: int,
) -> List[Dict]:
    """One LLM pass to name candidate themes from entity clusters + elements.

    Returns list of candidate theme dicts with grounded_on element IDs.
    """
    # Format elements summary per stop
    stop_summaries = []
    for i in range(total_stops):
        elems = elements_per_stop.get(i, [])
        if elems:
            elem_lines = [f"    [{e.get('id','?')}] ({e.get('type','?')}) {e.get('text','')[:120]}"
                         for e in elems[:6]]
            stop_summaries.append(f"  Stop {i+1} ({poi_names[i] if i < len(poi_names) else '?'}):\n" + "\n".join(elem_lines))

    elements_text = "\n".join(stop_summaries)

    # Format top entity clusters
    cluster_text = "\n".join(
        f"  - {c['entity']} ({c['entity_type']}): stops {c['stops']}, elements {c['element_ids'][:5]}"
        for c in entity_clusters[:15]
    )

    prompt = f"""You are identifying narrative themes that connect multiple stops in a tour of {venue_name}.

DOCUMENTED ELEMENTS BY STOP:
{elements_text}

SHARED ENTITIES ACROSS STOPS (deterministic overlap analysis):
{cluster_text}

TASK: Name 2-5 candidate narrative themes that could connect these stops into a coherent story.
A theme is NOT a mood ("all works explore identity") — it is a SPECIFIC shared thread:
- A person who connects multiple stops (e.g., a patron, architect, donor)
- A historical event that affected multiple stops (e.g., a war, a political change, a fire)
- A cultural force with documented presence at multiple stops (e.g., a trade route, a religious movement)
- A chronological narrative (e.g., "from village to metropolis")

RULES:
1. Every theme MUST cite the specific element IDs that support it in "grounded_on"
2. A theme without ≥2 supporting elements from ≥2 different stops is REJECTED
3. Never invent connections not present in the elements above
4. Name the theme as a short, specific phrase (5-12 words)
5. Describe what arc it could form: what's the beginning, the turn, the payoff?

Return ONLY valid JSON array:
[
  {{
    "name": "Short specific theme phrase",
    "description": "How this theme connects the stops and what arc it forms (beginning→turn→payoff)",
    "grounded_on": ["se_001", "se_005", "se_012"],
    "stops_covered": [1, 3, 5, 7],
    "arc_sketch": "Begins with X at stop 1, turns when Y at stop 3, pays off with Z at stop 7"
  }}
]
"""

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
                    {"role": "system", "content": "You return ONLY valid JSON. No markdown fences, no commentary."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.4,
                "max_tokens": 1500,
            },
            timeout=30,
        )

        if response.status_code != 200:
            logger.error(f"Theme naming API error: {response.status_code}")
            return []

        result = response.json()
        text = result["choices"][0]["message"]["content"].strip()

        # Log cost
        usage = result.get("usage", {})
        cost = (usage.get("prompt_tokens", 0) / 1000 * 0.005) + (usage.get("completion_tokens", 0) / 1000 * 0.015)
        print(f"  [SQ-S6b] Theme naming: ${cost:.4f}, {usage.get('total_tokens', 0)} tokens")

        # Parse
        clean = text
        m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", clean, re.DOTALL)
        if m:
            clean = m.group(1)

        themes = json.loads(clean)
        if not isinstance(themes, list):
            themes = [themes]

        return themes[:MAX_THREADS]

    except Exception as e:
        logger.error(f"Theme naming failed: {e}")
        return []


# ---------- Step 3: Theme scoring ----------

def _score_themes(
    candidates: List[Dict],
    elements_per_stop: Dict[int, List[dict]],
    all_elements: List[dict],
    total_stops: int,
) -> List[ThemeThread]:
    """Score candidate themes by coverage, evidence, distinctiveness, arc potential."""

    # Build element lookup by ID
    elem_by_id = {e.get("id", ""): e for e in all_elements if e.get("id")}

    scored_threads = []

    for cand in candidates:
        name = cand.get("name", "")
        description = cand.get("description", "")
        grounded_on = cand.get("grounded_on", [])
        stops_covered = cand.get("stops_covered", [])

        # Convert 1-based stop indices from LLM to 0-based
        stops_0based = [s - 1 for s in stops_covered if isinstance(s, int) and s >= 1]

        # Validate: grounded_on elements must actually exist
        valid_grounding = [eid for eid in grounded_on if eid in elem_by_id]
        if len(valid_grounding) < 2:
            print(f"  [SQ-S6b] Theme '{name}' rejected: insufficient valid grounding ({len(valid_grounding)} elements)")
            continue

        # Verify stops_covered: element IDs must actually map to those stops
        actual_stops = set()
        for eid in valid_grounding:
            for stop_idx, elems in elements_per_stop.items():
                if any(e.get("id") == eid for e in elems):
                    actual_stops.add(stop_idx)
        stops_0based = sorted(actual_stops) if actual_stops else stops_0based

        if len(stops_0based) < 2:
            print(f"  [SQ-S6b] Theme '{name}' rejected: covers <2 stops")
            continue

        # --- Coverage score ---
        coverage = len(stops_0based) / total_stops

        # --- Evidence strength ---
        evidence_scores = []
        for eid in valid_grounding:
            elem = elem_by_id.get(eid, {})
            status = elem.get("corroboration_status", "reported")
            evidence_scores.append(EVIDENCE_WEIGHTS.get(status, 0.5))
        evidence_strength = sum(evidence_scores) / len(evidence_scores) if evidence_scores else 0.0

        # --- Distinctiveness ---
        # Penalize if the theme name is generic (short, common words only)
        specificity_words = re.findall(r'\b[A-Z][a-z]+\b', name)  # proper nouns in theme name
        has_dates = bool(re.search(r'\d{4}', name))
        distinctiveness = min(1.0, (len(specificity_words) * 0.2 + (0.3 if has_dates else 0.0) + 0.2))

        # --- Arc potential ---
        # Does the theme span early→late stops? (not clustered in one section)
        if stops_0based:
            span = (max(stops_0based) - min(stops_0based)) / max(1, total_stops - 1)
            arc_potential = span * 0.7 + (0.3 if len(stops_0based) >= 3 else 0.0)
        else:
            arc_potential = 0.0

        # --- Total score (weighted) ---
        total_score = (
            coverage * 0.35 +
            evidence_strength * 0.25 +
            distinctiveness * 0.20 +
            arc_potential * 0.20
        )

        thread = ThemeThread(
            name=name,
            description=description,
            supporting_elements=valid_grounding,
            stops_covered=stops_0based,
            grounded_on=valid_grounding,
        )
        thread.coverage = coverage
        thread.evidence_strength = evidence_strength
        thread.distinctiveness = distinctiveness
        thread.arc_potential = arc_potential
        thread.total_score = total_score
        scored_threads.append(thread)

    # Sort by total_score descending
    scored_threads.sort(key=lambda t: -t.total_score)
    return scored_threads[:MAX_THREADS]


# ---------- Step 4: Multi-thread blending ----------

def _blend_threads(threads: List[ThemeThread], total_stops: int) -> List[ThemeThread]:
    """Assign coverage-proportional weights to scored threads.

    Per Michael's 2026-07-08 revision: with threads covering 7, 5, 4 stops,
    weights are 7/16, 5/16, 4/16. About 3 threads is good.
    """
    if not threads:
        return threads

    # Take top IDEAL_THREADS (or fewer)
    active = threads[:IDEAL_THREADS]

    # Sum of coverages (as stop counts)
    total_coverage = sum(len(t.stops_covered) for t in active)
    if total_coverage == 0:
        for t in active:
            t.weight = 1.0 / len(active)
        return active

    for t in active:
        t.weight = len(t.stops_covered) / total_coverage

    return active


def _build_per_stop_context(
    threads: List[ThemeThread],
    elements_per_stop: Dict[int, List[dict]],
    all_elements: List[dict],
    total_stops: int,
) -> List[Dict]:
    """Build per-stop thread context for injection into description prompts.

    Each stop gets a dict with the active threads for that stop and their contributions.
    """
    elem_by_id = {e.get("id", ""): e for e in all_elements if e.get("id")}
    per_stop = []

    for stop_idx in range(total_stops):
        stop_context = {
            "threads_active": [],
            "thread_angle": "",
            "callbacks": [],
        }

        for thread in threads:
            if stop_idx in thread.stops_covered:
                # Find which elements from this thread are at this stop
                stop_elems = elements_per_stop.get(stop_idx, [])
                stop_elem_ids = {e.get("id") for e in stop_elems}
                thread_elems_here = [eid for eid in thread.supporting_elements if eid in stop_elem_ids]

                if thread_elems_here:
                    elem_texts = [elem_by_id.get(eid, {}).get("text", "")[:100] for eid in thread_elems_here[:3]]
                    stop_context["threads_active"].append({
                        "name": thread.name,
                        "weight": thread.weight,
                        "elements_here": thread_elems_here,
                        "element_summaries": elem_texts,
                    })

        # Build a combined thread_angle for the description prompt
        if stop_context["threads_active"]:
            angles = []
            for ta in stop_context["threads_active"]:
                angles.append(f"[{ta['name']}] (weight {ta['weight']:.2f}): {'; '.join(ta['element_summaries'][:2])}")
            stop_context["thread_angle"] = "\n".join(angles)

        # Identify callbacks: this stop has thread elements that appeared in earlier stops
        for thread in threads:
            if stop_idx in thread.stops_covered:
                earlier_stops = [s for s in thread.stops_covered if s < stop_idx]
                if earlier_stops:
                    # Find specific elements from earlier stops to reference
                    for earlier_idx in earlier_stops:
                        earlier_elems = elements_per_stop.get(earlier_idx, [])
                        for elem in earlier_elems:
                            if elem.get("id") in thread.supporting_elements:
                                stop_context["callbacks"].append({
                                    "from_stop": earlier_idx,
                                    "element_id": elem.get("id"),
                                    "element_text": elem.get("text", "")[:120],
                                    "thread_name": thread.name,
                                })
                    break  # One callback source per thread is enough

        per_stop.append(stop_context)

    return per_stop


# ---------- Step 5: Degradation ----------

def _check_degradation(threads: List[ThemeThread], total_stops: int) -> Tuple[str, str]:
    """Check if themes are strong enough; if not, determine fallback mode.

    Returns (mode, organizing_principle):
        ("threaded", "") — normal thread mode
        ("organizing_principle", "chronological|geographic") — fallback
        ("mosaic", "") — honest mosaic mode
    """
    if not threads:
        return ("mosaic", "")

    best_coverage = threads[0].coverage if threads else 0.0

    if best_coverage >= MIN_COVERAGE_THRESHOLD:
        return ("threaded", "")

    # Check if we can use organizing principle
    # If best theme covers at least 40%, try organizing principle
    if best_coverage >= 0.40:
        return ("organizing_principle", "chronological")

    return ("mosaic", "")


# ---------- Main entry point ----------

def discover_theme_threads(
    story_elements: List[dict],
    poi_names: List[str],
    venue_name: str,
    api_key: str,
    elements_per_stop: Optional[Dict[int, List[dict]]] = None,
) -> ThreadDiscoveryResult:
    """Main entry: discover cross-stop theme threads from story elements.

    Args:
        story_elements: Flat list of all story elements (with 'id' field).
        poi_names: List of POI/stop names in tour order.
        venue_name: Venue or location name.
        api_key: OpenAI API key.
        elements_per_stop: Optional pre-mapped dict {stop_index: [elements]}.
            If not provided, elements are distributed by matching element text to POI names.

    Returns:
        ThreadDiscoveryResult with scored threads, mode, per-stop context,
        prolog promise, and epilog payoff.
    """
    total_stops = len(poi_names)
    result = ThreadDiscoveryResult()

    if not story_elements or total_stops < 2:
        print(f"  [SQ-S6b] Insufficient data for thread discovery (elements={len(story_elements or [])}, stops={total_stops})")
        result.mode = "mosaic"
        result.per_stop_thread_context = [{"threads_active": [], "thread_angle": "", "callbacks": []} for _ in range(total_stops)]
        return result

    # --- Assign elements to stops if not pre-mapped ---
    if elements_per_stop is None:
        elements_per_stop = _assign_elements_to_stops(story_elements, poi_names)

    print(f"  [SQ-S6b] Elements per stop: {', '.join(f's{i}={len(elements_per_stop.get(i, []))}' for i in range(total_stops))}")

    # --- Step 1: Deterministic entity overlap ---
    entity_clusters = _compute_entity_overlap_clusters(elements_per_stop, total_stops)
    print(f"  [SQ-S6b] Entity clusters found: {len(entity_clusters)} (≥2 stops)")
    for c in entity_clusters[:5]:
        print(f"    → {c['entity']} ({c['entity_type']}): {len(c['stops'])} stops, {len(c['element_ids'])} elements")

    # --- Step 2: LLM theme naming ---
    candidates = _llm_name_themes(
        elements_per_stop, entity_clusters, poi_names, venue_name, api_key, total_stops
    )
    print(f"  [SQ-S6b] LLM named {len(candidates)} candidate themes")

    # --- Step 3: Score themes ---
    scored = _score_themes(candidates, elements_per_stop, story_elements, total_stops)
    print(f"  [SQ-S6b] Scored themes: {len(scored)}")
    for t in scored:
        print(f"    → '{t.name}': coverage={t.coverage:.2f}, evidence={t.evidence_strength:.2f}, "
              f"distinct={t.distinctiveness:.2f}, arc={t.arc_potential:.2f}, TOTAL={t.total_score:.3f}")

    # --- Step 5: Check degradation ---
    mode, organizing_principle = _check_degradation(scored, total_stops)
    result.mode = mode
    result.organizing_principle = organizing_principle

    if mode == "mosaic":
        print(f"  [SQ-S6b] DEGRADATION → mosaic mode (no theme ≥{MIN_COVERAGE_THRESHOLD*100:.0f}% coverage)")
        result.per_stop_thread_context = [{"threads_active": [], "thread_angle": "", "callbacks": []} for _ in range(total_stops)]
        return result

    if mode == "organizing_principle":
        print(f"  [SQ-S6b] DEGRADATION → organizing principle ({organizing_principle}), best coverage={scored[0].coverage:.2f}")
        result.threads = scored[:1]  # Keep best thread as supporting texture
        result.per_stop_thread_context = [{"threads_active": [], "thread_angle": "", "callbacks": []} for _ in range(total_stops)]
        return result

    # --- Step 4: Multi-thread blending ---
    blended = _blend_threads(scored, total_stops)
    result.threads = blended
    print(f"  [SQ-S6b] Blended {len(blended)} threads: " +
          ", ".join(f"'{t.name}'={t.weight:.2f}" for t in blended))

    # --- Build per-stop context ---
    result.per_stop_thread_context = _build_per_stop_context(
        blended, elements_per_stop, story_elements, total_stops
    )

    # --- Build prolog promise ---
    if blended:
        top = blended[0]
        result.prolog_promise = (
            f"This tour traces the story of {top.name}. "
            f"{top.description[:200]}"
        )

    # --- Build epilog payoff ---
    if blended:
        top = blended[0]
        # Find the last stop's thread element for payoff
        last_covered = max(top.stops_covered) if top.stops_covered else total_stops - 1
        result.epilog_payoff = (
            f"From {poi_names[min(top.stops_covered)] if top.stops_covered else poi_names[0]} "
            f"to {poi_names[last_covered] if last_covered < len(poi_names) else poi_names[-1]}, "
            f"you have followed the thread of {top.name}."
        )

    return result


def _assign_elements_to_stops(
    story_elements: List[dict],
    poi_names: List[str],
) -> Dict[int, List[dict]]:
    """Heuristic assignment of elements to stops when no explicit mapping exists.

    Strategy:
    1. Match element text against POI names (title words)
    2. Elements matching no specific stop go to a "shared" pool
    3. Shared elements are NOT duplicated to all stops — they are available
       for cross-stop theme discovery but don't inflate per-stop counts

    For museum tours where elements tend to be venue-wide rather than per-work,
    this prevents the degenerate case where every element maps to every stop.
    """
    elements_per_stop: Dict[int, List[dict]] = defaultdict(list)
    shared_elements: List[dict] = []

    # Build normalized POI name tokens for matching
    poi_tokens = []
    for name in poi_names:
        tokens = set(w.lower() for w in re.findall(r'\w+', name)
                    if len(w) > 3 and w.lower() not in {
                        'the', 'this', 'that', 'with', 'from', 'room', 'hall',
                        'gallery', 'museum', 'collection', 'series', 'work',
                        'painting', 'sculpture', 'exhibit', 'display'
                    })
        poi_tokens.append(tokens)

    for elem in story_elements:
        text = (elem.get("text", "") + " " + elem.get("source_sentence", "")).lower()
        matched_stops = []

        for i, tokens in enumerate(poi_tokens):
            if not tokens:
                continue
            # Match if ≥2 content words from POI name appear in element text,
            # or if a single distinctive word (≥5 chars) matches
            matches = sum(1 for t in tokens if t in text)
            if matches >= 2 or (len(tokens) == 1 and matches >= 1 and len(list(tokens)[0]) >= 5):
                matched_stops.append(i)

        if matched_stops:
            for stop_idx in matched_stops:
                elements_per_stop[stop_idx].append(elem)
        else:
            shared_elements.append(elem)

    # Distribute shared elements across stops using round-robin
    # (ensures each stop gets some elements without duplicating all to all)
    if shared_elements and poi_names:
        n_stops = len(poi_names)
        for i, elem in enumerate(shared_elements):
            # Assign to 1-2 stops round-robin to create overlap opportunities
            primary_stop = i % n_stops
            elements_per_stop[primary_stop].append(elem)
            # Secondary stop for overlap detection (if enough elements)
            if len(shared_elements) > n_stops:
                secondary_stop = (i + n_stops // 2) % n_stops
                if secondary_stop != primary_stop:
                    elements_per_stop[secondary_stop].append(elem)

    return dict(elements_per_stop)
