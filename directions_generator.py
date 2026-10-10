"""
Directions Generator — navigation guidance between tour stops (Storied).
==========================================================================
Generates contextual directions between stops in a tour.
- Museum tours: room-to-room guidance referencing stop names.
- Outdoor tours: mode-aware directions (cycling, walking, driving, animal).

Uses GPT-3.5-turbo with explicit constraints against fabricating distances
or compass bearings inside buildings.

[LOCAL-253] Transport-mode awareness: directions now respect the tour's
transport mode and include a post-generation guard that rejects directions
containing mode-inappropriate infrastructure (motorways on cycling tours,
public transport suggestions, wrong-mode verbs).
"""
import json
import logging
import re
import requests
# [LOCAL-560] writer-model central setting (directions are prose the listener hears)
from llm_models import write_model as _write_model

logger = logging.getLogger(__name__)


# ─── [LOCAL-253] Mode-inappropriate infrastructure detection ───────────────
# These patterns detect directions that route the user onto infrastructure
# that is illegal, dangerous, or nonsensical for the tour's transport mode.

# Motorway/highway patterns — cycling on these is illegal in most jurisdictions
_MOTORWAY_RE = re.compile(
    r'\b(A\d{1,3}|autoroute|autobahn|motorway|highway|interstate|freeway|expressway)\b',
    re.IGNORECASE,
)

# Public transport patterns — if the tour mode is cycling/walking/driving,
# suggesting public transport means the directions generator gave up on the mode
_PUBLIC_TRANSPORT_RE = re.compile(
    r'\b(take\s+a\s+train|take\s+the\s+train|take\s+a\s+bus|take\s+the\s+bus'
    r'|take\s+a\s+tram|take\s+the\s+tram|take\s+a\s+metro|take\s+the\s+metro'
    r'|take\s+a\s+ferry|take\s+the\s+ferry'
    r'|board\s+(?:a|the)\s+(?:train|bus|tram|metro|ferry)'
    r'|hop\s+on\s+(?:a|the)\s+(?:train|bus|tram|metro|ferry)'
    r'|catch\s+(?:a|the)\s+(?:train|bus|tram|metro|ferry)'
    r'|from\s+\w+\s+(?:train\s+)?station,?\s+take)\b',
    re.IGNORECASE,
)

# Wrong-mode verb patterns per transport mode
_WRONG_MODE_VERBS = {
    'bike': re.compile(
        r'\b(start\s+your\s+walk|enjoy\s+the\s+walk|walking\s+tour'
        r'|start\s+walking|continue\s+walking|walk\s+along'
        r'|continue\s+on\s+foot|stroll\s+along|hike\s+along'
        r'|proceed\s+on\s+foot|travel\s+on\s+foot)\b',
        re.IGNORECASE,
    ),
    'on_foot': re.compile(
        r'\b(start\s+cycling|pedal\s+along|bike\s+along|start\s+driving'
        r'|drive\s+along|ride\s+your\s+bike)\b',
        re.IGNORECASE,
    ),
    'vehicle': re.compile(
        r'\b(start\s+your\s+walk|enjoy\s+the\s+walk|start\s+cycling'
        r'|pedal\s+along|bike\s+along|continue\s+on\s+foot|stroll\s+along)\b',
        re.IGNORECASE,
    ),
    'animal': re.compile(
        r'\b(start\s+your\s+walk|enjoy\s+the\s+walk|start\s+cycling'
        r'|pedal\s+along|drive\s+along|continue\s+on\s+foot)\b',
        re.IGNORECASE,
    ),
}

# Modes where motorways are forbidden (you physically cannot or legally must not)
_MOTORWAY_FORBIDDEN_MODES = {'bike', 'on_foot', 'animal'}

# Modes where public transport suggestions indicate a mode failure
_TRANSPORT_FORBIDDEN_MODES = {'bike', 'on_foot', 'vehicle', 'animal'}


# [LOCAL-650 fix 2] Significant words to ignore when checking that a directions
# line names its destination stop (articles, generic place words that recur
# across many names, and tour-form words).
_DIR_NAME_STOPWORDS = frozenset({
    'the', 'a', 'an', 'of', 'and', 'at', 'in', 'on', 'to', 'for', 'de', 'la',
    'le', 'du', 'des', 'house', 'hall', 'building', 'museum', 'gallery', 'park',
    'square', 'street', 'center', 'centre', 'old', 'new', 'the',
})


def _directions_name_destination(text: str, to_name: str) -> bool:
    """[LOCAL-650] True when ``text`` plausibly names the destination ``to_name``.

    The whole destination phrase appearing is the strongest signal. Otherwise we
    require that EVERY distinctive word of the destination (its words minus
    articles/common place nouns) appears in the text — so "Old State House"
    passes on "the Old State House" and even on "State House", but a line that
    names a totally different stop ("Massachusetts State House" when the next
    stop is "University of Massachusetts Boston") fails because distinctive words
    ("University", "Boston") are absent. When the destination has no distinctive
    words left after filtering, fall back to a substring check on the full name.
    """
    if not text or not to_name:
        return True  # nothing to validate against; don't reject
    low = re.sub(r'\s+', ' ', text.lower())
    full = re.sub(r'\s+', ' ', to_name.strip().lower())
    if full and full in low:
        return True
    words = re.findall(r"[a-z0-9][a-z0-9'\-]*", full)
    distinctive = [w for w in words if w not in _DIR_NAME_STOPWORDS and len(w) > 2]
    if not distinctive:
        # Name is all common words (e.g. "Old State House") — require the full
        # phrase OR its last two words.
        tail = " ".join(words[-2:]) if len(words) >= 2 else full
        return bool(tail) and tail in low
    return all(w in low for w in distinctive)


def validate_directions_mode(directions_text: str, transport_mode: str) -> list:
    """Validate that directions text does not contain mode-inappropriate content.

    Returns a list of violation strings. Empty list = directions are clean.
    This is the LOCAL-253 generation-failure gate for directions.
    """
    violations = []
    if not directions_text or not transport_mode:
        return violations

    # Check motorway references on modes where they're forbidden
    if transport_mode in _MOTORWAY_FORBIDDEN_MODES:
        match = _MOTORWAY_RE.search(directions_text)
        if match:
            violations.append(
                f"MOTORWAY_ON_{transport_mode.upper()}: '{match.group()}' — "
                f"routing a {transport_mode} tour onto a motorway/highway is illegal/dangerous"
            )

    # Check public transport on modes where it indicates failure
    if transport_mode in _TRANSPORT_FORBIDDEN_MODES:
        match = _PUBLIC_TRANSPORT_RE.search(directions_text)
        if match:
            violations.append(
                f"PUBLIC_TRANSPORT_ON_{transport_mode.upper()}: '{match.group()}' — "
                f"a {transport_mode} tour must not suggest public transport"
            )

    # Check wrong-mode verbs
    wrong_verbs_re = _WRONG_MODE_VERBS.get(transport_mode)
    if wrong_verbs_re:
        match = wrong_verbs_re.search(directions_text)
        if match:
            violations.append(
                f"WRONG_MODE_VERB_{transport_mode.upper()}: '{match.group()}' — "
                f"directions use language for a different transport mode"
            )

    return violations


# ─── [LOCAL-660 defect 4] Directions must not pre-announce the end ──────────
# Tour 557 v7 Stop 1→2 directions said:
#   "…you'll soon arrive at Boston City Hall, …, marking the end of your walk
#    exploring Massachusetts politics and current affairs in Boston."
# This is the leg into STOP 2 of 5. Only the leg INTO THE LAST STOP may say the
# walk is ending. And a directions line is a navigation cue, not a place to echo
# the tour's THEME ("exploring Massachusetts politics and current affairs") — a
# D636/D634 echo that belongs to the orientation/conclusion, not the hand-off.

# "final"/"end" language that claims the walk/tour/journey is concluding.
_DIRECTIONS_END_RE = re.compile(
    r'(?i)\b('
    r'mark(?:ing|s|ed)?\s+the\s+(?:end|close|conclusion|finale)\b[^.?!]*|'
    r'the\s+(?:end|close|conclusion|finale)\s+of\s+your\s+(?:walk|tour|journey|visit|stroll|ride)\b[^.?!]*|'
    r'(?:your|the)\s+(?:final|last)\s+stop\b[^.?!]*|'
    r'(?:this|that)\s+(?:is|marks)\s+(?:the\s+)?(?:final|last)\b[^.?!]*|'
    r'(?:ending|concluding|finishing|completing)\s+(?:your|the|this)\s+(?:walk|tour|journey|visit)\b[^.?!]*|'
    r'where\s+your\s+(?:walk|tour|journey)\s+(?:ends|concludes)\b[^.?!]*'
    r')')

# A theme echo attached to a walk/tour/journey noun: "…your walk exploring
# <theme>", "…tour dedicated to <theme>". Restricted to clearly THEMATIC
# connectors so a spatial navigation phrase ("walk through the park", "walk down
# Congress Street", "stroll along the Common") is never mistaken for a theme
# echo — those are the directions, not a restatement of the tour subject.
_DIRECTIONS_THEME_ECHO_RE = re.compile(
    r'(?i)\b(?:walk|tour|journey|visit|stroll|ride|exploration)\s+'
    r'(?:exploring|dedicated\s+to|celebrating|devoted\s+to|focused\s+on|'
    r'centered\s+on|centred\s+on|themed\s+(?:on|around))\s+'
    r'[^.?!]*')


def _strip_dangling_connectors(text: str) -> str:
    """Tidy a sentence after an end/theme clause was excised from its middle:
    drop a dangling trailing connector/comma and re-terminate."""
    s = re.sub(r'[ \t]{2,}', ' ', text)
    # Remove a trailing comma + connector left hanging ("…City Hall, .")
    s = re.sub(r'[\s,;:–—-]+(?=[.?!]|$)', '', s)
    s = re.sub(r'[ \t]+([.?!])', r'\1', s)
    s = s.strip()
    if s and s[-1] not in '.?!':
        s += '.'
    return s


def sanitize_directions_leg(text: str, is_last_leg: bool,
                            next_name: str = "") -> str:
    """[LOCAL-660 defect 4] Clean a directions line for its position in the tour.

    * On a NON-final leg, remove any clause that announces the walk/tour is
      ending ("marking the end of your walk", "your final stop", …). Only the leg
      into the LAST stop may say the walk is finishing.
    * On EVERY leg, strip the tour-theme echo ("…your walk exploring Massachusetts
      politics and current affairs") — a directions line is a navigation cue, not
      a place to restate the theme.

    If stripping empties the line, fall back to "Continue to <next_name>." when a
    destination name is known. Pure, deterministic, idempotent.
    """
    if not text or not text.strip():
        return text
    out = text

    # 1) Theme echo — remove the "<walk/tour> exploring <theme>…" clause on all legs.
    def _theme_sub(m):
        # Keep the leading noun ("walk"/"tour") so the sentence still reads if the
        # echo was the whole predicate; drop the "exploring <theme>" tail.
        head = m.group(0).split()[0]
        return head
    out = _DIRECTIONS_THEME_ECHO_RE.sub(_theme_sub, out)

    # 2) End/final language — only forbidden on a non-final leg.
    if not is_last_leg:
        out = _DIRECTIONS_END_RE.sub('', out)

    if out != text:
        # Re-tidy each sentence after excisions.
        out = _strip_dangling_connectors(out)

    # If we emptied the line (or left only a fragment), fall back to a clean cue.
    if not out or len(out.strip(' .?!,;:')) < 3:
        if next_name:
            return f"Continue to {next_name}."
        return text
    return out


_DIR_STOP_HEADER_RE = re.compile(r'(?mi)^Stop\s+\d+:\s*(.+?)\s*$')
_DIR_LINE_RE = re.compile(r'(?mi)^(\s*Directions:\s*)(\S.*)$')


def sanitize_directions_in_text(tour_text: str) -> "tuple":
    """[LOCAL-660 defect 4] Text-level, every-path guard: sanitize each
    ``Directions:`` line by its position in the tour. Only the Directions line of
    the SECOND-TO-LAST stop (the leg into the last stop) may announce the end of
    the walk; every Directions line is stripped of a tour-theme echo. Returns
    ``(new_text, n_changed)``. Deterministic and idempotent."""
    if not tour_text or 'Directions:' not in tour_text:
        return tour_text, 0
    headers = list(_DIR_STOP_HEADER_RE.finditer(tour_text))
    n_stops = len(headers)
    if n_stops < 2:
        return tour_text, 0
    # The leg into the last stop departs the second-to-last stop; its Directions
    # line sits inside the second-to-last stop's block.
    last_leg_start = headers[n_stops - 2].start()
    last_leg_end = headers[n_stops - 1].start()

    changed = 0

    def _repl(m):
        nonlocal changed
        label, body = m.group(1), m.group(2)
        pos = m.start()
        is_last_leg = (last_leg_start <= pos < last_leg_end)
        new_body = sanitize_directions_leg(body, is_last_leg=is_last_leg)
        if new_body != body:
            changed += 1
            return label + new_body
        return m.group(0)

    out = _DIR_LINE_RE.sub(_repl, tour_text)
    return out, changed


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
                "model": _write_model(site_default="gpt-3.5-turbo"),
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
        from cost_rates import llm_cost
        cost = llm_cost(total_tokens=tokens)
        logger.info(f"Directions: {from_name} → {to_name} | {tokens} tokens | ${cost:.4f}")

        return text

    except requests.Timeout:
        logger.warning(f"Directions timeout: {from_name} → {to_name}")
        return ""
    except Exception as e:
        logger.error(f"Directions error: {e}")
        return ""


def generate_walking_directions(
    from_poi,
    to_poi,
    location: str,
    api_key: str,
    transport_mode: str = "on_foot",
) -> str:
    """Generate landmark-based directions between two outdoor POIs.

    [LOCAL-253] Now transport-mode-aware: generates cycling, walking, driving,
    or animal-mode directions based on the tour's actual transport mode.
    Includes a post-generation guard that rejects mode-inappropriate output.

    Uses street addresses to produce natural directions referencing visible
    landmarks, street names, and storefronts. Never fabricates precise
    distances or turn-by-turn metric measurements.

    Args:
        from_poi: dict with 'name' and optionally 'address', OR a string name.
        to_poi: dict with 'name' and optionally 'address', OR a string name.
        location: The general area/city (for context).
        api_key: OpenAI API key.
        transport_mode: One of 'on_foot', 'bike', 'vehicle', 'animal',
                        'country_scale'. Defaults to 'on_foot'.

    Returns:
        2–4 sentences of mode-appropriate directions. Empty string on failure
        or if directions contain mode-inappropriate content (guard rejection).
    """
    from_name = from_poi.get("name", "previous stop") if isinstance(from_poi, dict) else str(from_poi)
    from_addr = from_poi.get("address", "") if isinstance(from_poi, dict) else ""
    to_name = to_poi.get("name", "next stop") if isinstance(to_poi, dict) else str(to_poi)
    to_addr = to_poi.get("address", "") if isinstance(to_poi, dict) else ""

    # [LOCAL-253] Mode-specific prompt language
    _MODE_PROMPTS = {
        'on_foot': {
            'verb': 'walking',
            'movement': 'Walk',
            'traveler': 'walker',
            'constraint': (
                "The listener is ON FOOT. Never suggest cycling, driving, or public transport. "
                "Use walking verbs: walk, head, stroll, continue on foot."
            ),
        },
        'bike': {
            'verb': 'cycling',
            'movement': 'Cycle',
            'traveler': 'cyclist',
            'constraint': (
                "The listener is on a BICYCLE. CRITICAL RULES:\n"
                "- Use cycling verbs: cycle, pedal, ride, bike along.\n"
                "- NEVER suggest walking, taking a train, bus, tram, metro, or ferry.\n"
                "- NEVER route onto motorways, autoroutes, highways, or expressways — "
                "cycling on these is ILLEGAL.\n"
                "- Prefer coastal roads, scenic routes, designated bike paths, or quiet roads.\n"
                "- Do NOT say 'walk', 'on foot', 'stroll', or 'hike'."
            ),
        },
        'vehicle': {
            'verb': 'driving',
            'movement': 'Drive',
            'traveler': 'driver',
            'constraint': (
                "The listener is DRIVING. Use driving verbs: drive, take the road, "
                "follow the highway, continue along. Never suggest walking or cycling."
            ),
        },
        'animal': {
            'verb': 'riding',
            'movement': 'Ride',
            'traveler': 'rider',
            'constraint': (
                "The listener is on an ANIMAL (horse, camel, etc). Use riding verbs: "
                "ride, trot, follow the trail. Never suggest roads, highways, or public transport."
            ),
        },
        'country_scale': {
            'verb': 'traveling',
            'movement': 'Travel',
            'traveler': 'traveler',
            'constraint': (
                "This is a long-distance tour. Use appropriate travel verbs for the route."
            ),
        },
    }

    mode_info = _MODE_PROMPTS.get(transport_mode, _MODE_PROMPTS['on_foot'])

    system_prompt = (
        f"You write short, natural {mode_info['verb']} directions for an audio tour. "
        "RULES: "
        "1. Do NOT fabricate precise distances ('walk 50 meters', '200 feet'). "
        "2. Do NOT invent turn-by-turn GPS-style directions you can't verify. "
        "3. DO reference visible landmarks, street names, storefronts, or building features "
        "derivable from the addresses. "
        "4. Keep it to 2–4 sentences. "
        "5. Make it feel like a friend giving directions, not a GPS robot. "
        f"6. {mode_info['constraint']}"
    )
    user_prompt = (
        f"Area: {location}\n"
        f"Transport mode: {mode_info['verb']} (the listener is a {mode_info['traveler']})\n"
        f"From: {from_name}" + (f" ({from_addr})" if from_addr else "") + "\n"
        f"To: {to_name}" + (f" ({to_addr})" if to_addr else "") + "\n\n"
        f"Write 2–4 sentences of {mode_info['verb']} directions from '{from_name}' to '{to_name}'. "
        f"Use {mode_info['verb']} language throughout. "
        f"Reference at least one landmark or street name derivable from the addresses."
    )

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": _write_model(site_default="gpt-3.5-turbo"),
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.6,
                "max_tokens": 200,
            },
            timeout=15,
        )

        if response.status_code != 200:
            logger.error(f"Directions API error ({mode_info['verb']}): {response.status_code}")
            return ""

        result = response.json()
        text = result["choices"][0]["message"]["content"].strip()
        tokens = result.get("usage", {}).get("total_tokens", 0)
        from cost_rates import llm_cost
        cost = llm_cost(total_tokens=tokens)
        logger.info(f"Directions ({mode_info['verb']}): {from_name} → {to_name} | {tokens} tokens | ${cost:.4f}")

        # [LOCAL-253] Post-generation mode guard — fail loudly, not silently
        violations = validate_directions_mode(text, transport_mode)
        if violations:
            for v in violations:
                logger.error(f"[LOCAL-253] DIRECTIONS MODE GUARD REJECTED: {v}")
                print(f"  ❌ [LOCAL-253] DIRECTIONS REJECTED: {v}")
            print(f"  ❌ [LOCAL-253] Rejected directions text: {text[:200]}")
            return ""  # Empty triggers the fallback "Continue to {next_stop}."

        # [LOCAL-650 fix 2] Target guard — the directions MUST lead to the next
        # stop. On tour 557 the model wrote Stop 4's directions as "… until you
        # reach the Massachusetts State House …", which is STOP 1, not the next
        # stop. If the generated prose never names the destination (to_name), it
        # is not a hand-off to the next stop — return "" so the deterministic
        # "Continue to {next_stop}." fallback (which names the correct stop) is
        # used instead. A short, meaningful fragment of the destination name must
        # appear in the text.
        if not _directions_name_destination(text, to_name):
            logger.error(
                f"[LOCAL-650] DIRECTIONS TARGET GUARD REJECTED: prose does not "
                f"name the next stop {to_name!r}: {text[:160]}")
            print(f"  ❌ [LOCAL-650] DIRECTIONS do not lead to next stop "
                  f"'{to_name}' — using deterministic fallback")
            return ""

        return text

    except requests.Timeout:
        logger.warning(f"Directions timeout ({mode_info['verb']}): {from_name} → {to_name}")
        return ""
    except Exception as e:
        logger.error(f"Directions error ({mode_info['verb']}): {e}")
        return ""
