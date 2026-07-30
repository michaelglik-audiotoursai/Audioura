"""three_class_retrieval.py — Deliberately acquire stories in three classes.

Michael's framework: Details / Historical / Social.

Instead of measuring these after the fact (as the I-CON evaluator does),
this module *drives retrieval* so that each stop gets material in all three.

The key insight: retrieve at CATEGORY level for Historical, not just object level.
A single object often has no literature of its own, but the category it belongs to does.

GUARD (non-optional): category-level material must be framed as category —
"bowls of this period were fired…", NEVER "this bowl was fired…".
"""
import re
from typing import Dict, List, Optional, Tuple

# ──────────────────────────────────────────────────────────────────────────────
# CLASS DEFINITIONS (Michael's framework)
# ──────────────────────────────────────────────────────────────────────────────
#
# Details  — what the thing physically is: material, size, colour, technique,
#            date as a bare fact.
# Historical — the thing placed in time: era, style, technology, how the form
#              evolved, what came before and after. Cultural context sits here.
# Social   — the people: who is depicted, who made it, who commissioned or
#            owned it, who saw it, their circles, contemporaries' opinions.
# ──────────────────────────────────────────────────────────────────────────────

CLASS_DETAILS = "details"
CLASS_HISTORIC = "historic"
CLASS_SOCIAL = "social"

ALL_CLASSES = (CLASS_DETAILS, CLASS_HISTORIC, CLASS_SOCIAL)

# ──────────────────────────────────────────────────────────────────────────────
# ELEMENT TYPE → CLASS MAPPING (Task §3: justify the mapping)
# ──────────────────────────────────────────────────────────────────────────────
#
# The 13 existing element types map as follows:
#
# DETAILS class:
#   technique   — physical making process, medium, how it was done
#   date        — a bare date/year without broader era narrative
#
# HISTORICAL class:
#   origin      — where/when the form or style originated (era context)
#   reference_work — what influenced it, stylistic lineage
#   legend      — mythological or traditional narrative context
#
# SOCIAL class:
#   person      — a named individual associated with the work
#   dedication  — who it was made for, why (social relationship)
#   turning_point — a moment in someone's life that led to this
#   provenance  — who owned/collected/sold it (chain of people)
#   reception   — how contemporaries/critics reacted (social response)
#   controversy — disagreement among people about the work
#   quote       — words spoken/written by someone about it
#   intention   — the maker's stated purpose (social because it's about the person)
#
# Justification:
# - technique/date → Details because they describe physical properties.
# - origin/reference_work/legend → Historical because they place the work in
#   time and stylistic context (eras, movements, evolution).
# - Everything with "who" → Social: person, dedication, turning_point,
#   provenance, reception, controversy, quote, intention all centre on
#   named humans and their relationships.

ELEMENT_TYPE_TO_CLASS = {
    # Details
    "technique": CLASS_DETAILS,
    "date": CLASS_DETAILS,
    # Historical
    "origin": CLASS_HISTORIC,
    "reference_work": CLASS_HISTORIC,
    "legend": CLASS_HISTORIC,
    # Social
    "person": CLASS_SOCIAL,
    "dedication": CLASS_SOCIAL,
    "turning_point": CLASS_SOCIAL,
    "provenance": CLASS_SOCIAL,
    "reception": CLASS_SOCIAL,
    "controversy": CLASS_SOCIAL,
    "quote": CLASS_SOCIAL,
    "intention": CLASS_SOCIAL,
}


def classify_element(element: Dict) -> str:
    """Return the class (details/historic/social) for an extracted element."""
    etype = element.get("type", "")
    return ELEMENT_TYPE_TO_CLASS.get(etype, CLASS_HISTORIC)


# ──────────────────────────────────────────────────────────────────────────────
# CATEGORY DETERMINATION (Task §2)
# ──────────────────────────────────────────────────────────────────────────────
# Determine the category for each stop from what we already hold:
# catalogue metadata (material, period, type), Wikidata class, venue section headings.

def determine_category(stop: Dict, per_work_contexts: Dict = None,
                       catalogue_works: List[Dict] = None) -> str:
    """Determine the broad object category for a stop.
    
    Uses catalogue metadata (material, period, type fields), Wikidata P31 class,
    and venue section headings. Does NOT ask the model to guess.
    
    Args:
        stop: Dict with at least 'name', optionally 'material', 'period', 'type_label'
        per_work_contexts: Dict {title: [sentences]} from story_miner
        catalogue_works: List of catalogue work dicts from story_miner
        
    Returns:
        A category string like "jade bi disc", "oil painting", "bronze sculpture"
        that can be used to query category-level material.
        Returns empty string if category cannot be determined.
    """
    name = stop.get("name", "")
    
    # 1. Check catalogue_works for structured metadata
    if catalogue_works:
        name_lower = name.lower().strip()
        for cw in catalogue_works:
            cw_title_lower = cw.get("title", "").lower().strip()
            if not cw_title_lower:
                continue
            # Match by prefix containment (same logic as fact_extractor)
            if (name_lower == cw_title_lower or
                (name_lower[:10] in cw_title_lower and cw_title_lower[:10] in name_lower)):
                # Build category from material + type
                parts = []
                if cw.get("material"):
                    parts.append(cw["material"])
                if cw.get("type_label"):
                    parts.append(cw["type_label"])
                elif cw.get("period"):
                    # If we have material + period but no type, use them
                    parts.append(cw["period"])
                if parts:
                    return " ".join(parts)
    
    # 2. Check stop dict itself (may have metadata from D1/venue_resolver)
    material = stop.get("material", "")
    type_label = stop.get("type_label", "")
    wikidata_class = stop.get("wikidata_class", "")
    
    if material and type_label:
        return f"{material} {type_label}"
    if type_label:
        return type_label
    if wikidata_class:
        return wikidata_class
    if material:
        return material
    
    # 3. Infer from per_work_contexts metadata sentences
    if per_work_contexts:
        for title, sentences in per_work_contexts.items():
            title_lower = title.lower().strip()
            if (name_lower == title_lower or
                (len(name_lower) >= 10 and name_lower[:10] in title_lower)):
                # Look for "Material:" prefix in metadata sentences
                for sent in sentences:
                    if sent.startswith("Material:"):
                        mat = sent.replace("Material:", "").strip()
                        return mat
                break
    
    return ""


# ──────────────────────────────────────────────────────────────────────────────
# CLASS-TARGETED QUERY SYNTHESIS (Task §1)
# ──────────────────────────────────────────────────────────────────────────────
# Three targeted retrievals per stop, parameterised by class.

def synthesize_class_queries(stop: Dict, category: str = "") -> Dict[str, List[str]]:
    """Generate class-targeted queries for a stop.
    
    Returns a dict {class_name: [queries]} with queries designed to retrieve
    material specifically for each of the three classes.
    
    Args:
        stop: Dict with canonical_title, artist, venue_city, category, etc.
        category: The object category (from determine_category).
        
    Returns:
        {"details": [...], "historic": [...], "social": [...]}
    """
    title = stop.get("canonical_title", "") or stop.get("name", "")
    artist = stop.get("artist", "")
    city = stop.get("venue_city", "")
    
    queries = {
        CLASS_DETAILS: [],
        CLASS_HISTORIC: [],
        CLASS_SOCIAL: [],
    }
    
    # ── Details queries: physical properties of THIS entity ──
    # "{entity}" material dimensions technique medium
    if title:
        queries[CLASS_DETAILS].append(
            f'"{title}" material dimensions technique medium'
        )
        if artist:
            queries[CLASS_DETAILS].append(
                f'"{title}" {artist} technique materials'
            )
    
    # ── Historical queries: CATEGORY level, not object level ──
    # "{category}" origin era evolution
    # This is the key insight: query the CATEGORY, not the specific object.
    if category:
        queries[CLASS_HISTORIC].append(
            f'"{category}" origin era history evolution'
        )
        queries[CLASS_HISTORIC].append(
            f'"{category}" ancient tradition cultural significance'
        )
    # Fallback: use the entity title for historical context
    if title:
        queries[CLASS_HISTORIC].append(
            f'"{title}" history period era style'
        )
    
    # ── Social queries: the people ──
    # "{entity}" OR "{maker}" commissioned owned reception who
    if title:
        queries[CLASS_SOCIAL].append(
            f'"{title}" commissioned owned reception provenance'
        )
    if artist:
        queries[CLASS_SOCIAL].append(
            f'"{artist}" "{title}" patron collector who'
        )
        queries[CLASS_SOCIAL].append(
            f'"{artist}" controversy relationship circle'
        )
    elif title:
        queries[CLASS_SOCIAL].append(
            f'"{title}" who made commissioned owned donated'
        )
    
    return queries


# ──────────────────────────────────────────────────────────────────────────────
# CLASS-AWARE ELEMENT EXTRACTION PROMPT
# ──────────────────────────────────────────────────────────────────────────────

def build_class_extraction_prompt(page_text: str, canonical_title: str,
                                  artist: str, target_class: str,
                                  is_category_level: bool = False,
                                  category: str = "") -> str:
    """Build an LLM prompt that targets a specific class of information.
    
    Args:
        page_text: The page text to extract from.
        canonical_title: The object title.
        artist: Artist/maker name.
        target_class: One of 'details', 'historic', 'social'.
        is_category_level: If True, extraction is for category material (not object-specific).
        category: The category string (for framing guard).
        
    Returns:
        Prompt string for the LLM.
    """
    if target_class == CLASS_DETAILS:
        type_instruction = (
            "Extract ONLY physical/technical facts: material, dimensions, colour, "
            "weight, technique, medium, condition, date of creation (as bare fact)."
        )
        target_types = ["technique", "date"]
    elif target_class == CLASS_HISTORIC:
        type_instruction = (
            "Extract ONLY historical/era context: when this form/style originated, "
            "how it evolved, what artistic/cultural movement it belongs to, what "
            "came before and after, its place in broader tradition."
        )
        target_types = ["origin", "reference_work", "legend"]
    elif target_class == CLASS_SOCIAL:
        type_instruction = (
            "Extract ONLY people-centered facts: who made it, who commissioned it, "
            "who owned or collected it, who is depicted, their relationships, "
            "what contemporaries said, controversies between people."
        )
        target_types = ["person", "dedication", "turning_point", "provenance",
                        "reception", "controversy", "quote", "intention"]
    else:
        raise ValueError(f"Unknown class: {target_class}")
    
    # Category-level guard
    if is_category_level and category:
        framing_guard = (
            f"\n\nCRITICAL FRAMING RULE: This text is about the CATEGORY "
            f'"{category}", not about a specific individual object. '
            f"ALL extracted facts MUST be framed as category-level statements. "
            f'Use phrasing like "objects of this type were..." or '
            f'"{category} pieces typically..." — '
            f'NEVER "{canonical_title} was..." unless the text explicitly '
            f"names that specific object."
        )
    else:
        framing_guard = ""
    
    prompt = (
        f'You are extracting {target_class.upper()} class story elements about '
        f'"{canonical_title}" by {artist}.\n\n'
        f'{type_instruction}\n\n'
        f'For each element, provide:\n'
        f'- type: one of {target_types}\n'
        f'- text: brief factual claim (1-2 sentences)\n'
        f'- source_sentence: the exact sentence from the text that supports this\n'
        f'- people: list of named people mentioned (empty list if none)\n'
        f'- dates: list of dates/years mentioned (empty list if none)\n'
        f'- is_category_level: {"true" if is_category_level else "false"}\n\n'
        f'Return JSON array. If no relevant elements found, return empty array [].'
        f'{framing_guard}\n\n'
        f'TEXT:\n{page_text[:8000]}'
    )
    return prompt


# ──────────────────────────────────────────────────────────────────────────────
# TOUR-LEVEL CLASS DIVERSITY (Task §4: wire apply_tour_diversity)
# ──────────────────────────────────────────────────────────────────────────────

def compute_stop_class_distribution(elements: List[Dict]) -> Dict[str, float]:
    """Compute the class distribution for a stop's elements.
    
    Returns: {"details": 0.X, "historic": 0.Y, "social": 0.Z}
    """
    counts = {CLASS_DETAILS: 0, CLASS_HISTORIC: 0, CLASS_SOCIAL: 0}
    total = 0
    for elem in elements:
        cls = classify_element(elem)
        counts[cls] += 1
        total += 1
    
    if total == 0:
        return {CLASS_DETAILS: 0.33, CLASS_HISTORIC: 0.34, CLASS_SOCIAL: 0.33}
    
    return {k: round(v / total, 3) for k, v in counts.items()}


def dominant_class(elements: List[Dict]) -> str:
    """Return the dominant class for a stop's elements."""
    dist = compute_stop_class_distribution(elements)
    return max(dist, key=dist.get)


def apply_class_diversity(stops_elements: List[Dict],
                          max_same_dominant: int = 3) -> List[Dict]:
    """Ensure a tour doesn't have too many consecutive stops with the same dominant class.
    
    This replaces/extends the existing apply_tour_diversity by operating on
    the three classes (Details/Historical/Social) rather than element types.
    
    If more than `max_same_dominant` stops share the same dominant class,
    reweight the element selection for excess stops to promote their
    second-strongest class.
    
    Args:
        stops_elements: List of dicts, each with:
            - 'elements': list of scored elements
            - 'selected_elements': list (top picks)
            - 'runner_up_elements': list (alternatives)
        max_same_dominant: Max stops allowed to be dominated by same class.
        
    Returns:
        Modified list with diversity enforced.
    """
    class_counts = {CLASS_DETAILS: 0, CLASS_HISTORIC: 0, CLASS_SOCIAL: 0}
    
    for stop in stops_elements:
        selected = stop.get("selected_elements", [])
        if not selected:
            continue
        
        # Determine dominant class from selected elements
        dom = dominant_class(selected)
        count = class_counts.get(dom, 0)
        
        if count >= max_same_dominant:
            # Promote elements from a different class
            runners = stop.get("runner_up_elements", [])
            # Find a runner-up from a non-dominant class
            for i, runner in enumerate(runners):
                runner_cls = classify_element(runner)
                if runner_cls != dom:
                    # Swap: demote the dominant-class top pick, promote this one
                    demoted = selected[0]
                    stop["selected_elements"] = [runner] + selected[1:]
                    stop["runner_up_elements"] = [demoted] + runners[:i] + runners[i+1:]
                    stop["_diversity_swap"] = {
                        "demoted_class": dom,
                        "promoted_class": runner_cls,
                    }
                    break
        else:
            class_counts[dom] = count + 1
    
    return stops_elements


# ──────────────────────────────────────────────────────────────────────────────
# CATEGORY-LEVEL FRAMING GUARD (Task "guard, not optional")
# ──────────────────────────────────────────────────────────────────────────────

# Patterns that assert object-specific facts ("this X was/is...")
_OBJECT_ASSERTION_PATTERNS = [
    re.compile(r"\bthis\s+(object|piece|work|bowl|disc|vase|sculpture|painting|statue)\s+(was|is|has|dates|weighs)", re.IGNORECASE),
    re.compile(r"\b(it|this one)\s+(was|is)\s+(made|created|fired|carved|cast|polished|crafted)", re.IGNORECASE),
]

# Patterns that correctly frame category-level material
_CATEGORY_FRAMING_PATTERNS = [
    re.compile(r"\b(objects?|pieces?|examples?|works?|bowls?|discs?|vessels?)\s+of\s+this\s+(type|period|kind|era|class)", re.IGNORECASE),
    re.compile(r"\b(such|these|similar)\s+(objects?|pieces?|works?)", re.IGNORECASE),
    re.compile(r"\b(typically|generally|traditionally|often)\s+(were|are|was)", re.IGNORECASE),
]


def check_category_framing_violation(text: str, is_category_level: bool) -> Optional[str]:
    """Check if category-level material is incorrectly presented as object-specific.
    
    Returns a description of the violation if found, None otherwise.
    Only checks elements marked as is_category_level=True.
    """
    if not is_category_level:
        return None
    
    for pattern in _OBJECT_ASSERTION_PATTERNS:
        match = pattern.search(text)
        if match:
            return f"Category material presented as object-specific: '{match.group()}'"
    
    return None


def validate_no_category_collapse(elements: List[Dict]) -> List[Dict]:
    """Filter out elements that violate the category framing guard.
    
    Any element marked is_category_level=True that makes object-specific claims
    is flagged and demoted (its text is reframed or it's dropped).
    
    Returns: filtered list with violations removed.
    """
    valid = []
    violations = []
    
    for elem in elements:
        if not elem.get("is_category_level", False):
            valid.append(elem)
            continue
        
        text = elem.get("text", "")
        violation = check_category_framing_violation(text, True)
        if violation:
            violations.append({"element": elem, "violation": violation})
        else:
            valid.append(elem)
    
    if violations:
        import sys
        print(f"  [CLASS-GUARD] Removed {len(violations)} category-framing violations:",
              file=sys.stderr)
        for v in violations[:3]:
            print(f"    - {v['violation']}: {v['element'].get('text', '')[:80]}",
                  file=sys.stderr)
    
    return valid


# ──────────────────────────────────────────────────────────────────────────────
# FREE-PATH RETRIEVAL (Wikipedia API, venue site, national databases)
# ──────────────────────────────────────────────────────────────────────────────

def fetch_category_context_free(category: str, language: str = "en") -> Dict[str, str]:
    """Fetch category-level context using free sources (Wikipedia API).
    
    This is the Historical-class retrieval at CATEGORY level.
    Cost discipline: Wikipedia API first, no paid search.
    
    Args:
        category: The object category (e.g., "jade bi disc", "bronze ritual vessel")
        language: Language code for localized lookup.
        
    Returns:
        Dict with keys matching the three classes:
        {"details": "...", "historic": "...", "social": "..."}
        Each value is the raw text retrieved for that class.
    """
    import urllib.request
    import json as _json
    
    results = {CLASS_DETAILS: "", CLASS_HISTORIC: "", CLASS_SOCIAL: ""}
    
    if not category:
        return results
    
    # Try Wikipedia for the category
    wiki_hosts = [f"{language}.wikipedia.org"] if language != "en" else []
    wiki_hosts.append("en.wikipedia.org")
    
    for wiki_host in wiki_hosts:
        try:
            params = urllib.parse.urlencode({
                "action": "query",
                "prop": "extracts",
                "explaintext": "1",
                "titles": category,
                "format": "json",
            })
            req = urllib.request.Request(
                f"https://{wiki_host}/w/api.php?{params}",
                headers={"User-Agent": "Audioura/2.2 (three-class-retrieval)"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = _json.loads(resp.read().decode())
                pages = data.get("query", {}).get("pages", {})
                for pid, pdata in pages.items():
                    if pid == "-1" or pdata.get("missing"):
                        continue
                    extract = pdata.get("extract", "")
                    if extract and len(extract) > 200:
                        # We got category-level text — this goes to Historical
                        results[CLASS_HISTORIC] = extract
                        break
        except Exception:
            continue
        
        if results[CLASS_HISTORIC]:
            break
    
    return results


# ──────────────────────────────────────────────────────────────────────────────
# INTEGRATION: run three-class retrieval for a stop
# ──────────────────────────────────────────────────────────────────────────────

def retrieve_three_classes_for_stop(
    stop: Dict,
    per_work_contexts: Dict = None,
    catalogue_works: List[Dict] = None,
    language: str = "en",
) -> Dict:
    """Run the complete three-class retrieval for one stop.
    
    1. Determine category from existing metadata.
    2. Generate class-targeted queries.
    3. Fetch category-level context (free path first).
    4. Return structured result.
    
    Args:
        stop: Stop dict with name, artist, etc.
        per_work_contexts: From story_miner.
        catalogue_works: From story_miner.
        language: Venue language.
        
    Returns:
        Dict with:
            category: str — determined category
            class_queries: {class: [queries]}
            category_context: str — free-path category text (for Historical)
            class_elements: {class: [elements]} — any pre-extracted elements tagged by class
    """
    # Step 1: Determine category
    category = determine_category(stop, per_work_contexts, catalogue_works)
    
    # Step 2: Generate class-targeted queries
    class_queries = synthesize_class_queries(stop, category)
    
    # Step 3: Fetch category-level context (free sources only)
    category_context = {}
    if category:
        category_context = fetch_category_context_free(category, language)
    
    return {
        "category": category,
        "class_queries": class_queries,
        "category_context": category_context,
        "is_category_level": bool(category),
    }


def tag_elements_by_class(elements: List[Dict]) -> List[Dict]:
    """Tag each element with its class and return the annotated list.
    
    Adds 'story_class' key to each element.
    """
    for elem in elements:
        elem["story_class"] = classify_element(elem)
    return elements


def compute_tour_class_balance(all_stops_elements: List[List[Dict]]) -> Dict:
    """Compute class balance across a full tour.
    
    Args:
        all_stops_elements: List of element-lists, one per stop.
        
    Returns:
        Dict with:
            per_stop: [{class_dist}]
            tour_dist: {class: float}
            dominant_per_stop: [class_name]
            is_balanced: bool — True if no class dominates > 60% of stops
    """
    per_stop = []
    dominant_list = []
    
    for elements in all_stops_elements:
        dist = compute_stop_class_distribution(elements)
        per_stop.append(dist)
        dominant_list.append(max(dist, key=dist.get))
    
    # Tour-level distribution
    if per_stop:
        tour_dist = {
            CLASS_DETAILS: round(sum(d[CLASS_DETAILS] for d in per_stop) / len(per_stop), 3),
            CLASS_HISTORIC: round(sum(d[CLASS_HISTORIC] for d in per_stop) / len(per_stop), 3),
            CLASS_SOCIAL: round(sum(d[CLASS_SOCIAL] for d in per_stop) / len(per_stop), 3),
        }
    else:
        tour_dist = {CLASS_DETAILS: 0.33, CLASS_HISTORIC: 0.34, CLASS_SOCIAL: 0.33}
    
    # Count dominance
    dom_counts = {CLASS_DETAILS: 0, CLASS_HISTORIC: 0, CLASS_SOCIAL: 0}
    for d in dominant_list:
        dom_counts[d] = dom_counts.get(d, 0) + 1
    
    n = len(dominant_list) if dominant_list else 1
    is_balanced = all(c / n <= 0.6 for c in dom_counts.values())
    
    return {
        "per_stop": per_stop,
        "tour_dist": tour_dist,
        "dominant_per_stop": dominant_list,
        "is_balanced": is_balanced,
        "dominance_counts": dom_counts,
    }
