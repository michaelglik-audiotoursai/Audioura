#!/usr/bin/env python3
"""style_validator_detector.py — LOCAL-184 + LOCAL-187: Detect instructions,
questions, prescribed feelings, and hallucinated sensory data in tour text.

Implements rules R1–R4, R7 from ClickUp wdvrdaxaqj (Michael's field-test):

  R1 — Imperatives aimed at the listener (sentence-initial base-form verb, no subject)
  R2 — Questions (? = error; interrogative opener without ? = warning)
  R3 — Suggestive exploration language (generalized: as you + movement verb)
  R4 — Prescribed feeling (you feel, you sense, pressing down upon you…)
  R7 — Hallucinated sensory data: asserts a sensation the listener cannot
       actually be having (historical/absent sound, smell, taste). (D62)

Navigation exemption: the style validator uses a NARROWER navigation test
than the anchor detector. Wayfinding moves the listener along a route
("head south", "turn left", "continue past"); attention-directing ("look
for the walls", "notice the facade") is NOT navigation for style purposes.
LOCAL-187 fix: "look for" directs attention, not movement.

R5 (every abstract claim must be grounded) maps to the existing anchor
detector's ANCHORED / UNLINKED_ENTITY classification. Not reimplemented here.

Deterministic. No LLM. Read-only against the database. $0.00 spend.
"""
import re
import sys
from typing import Dict, List, Tuple

sys.path.insert(0, 'tests')
from db_connection import get_connection
from stop_anchor_detector_v2 import parse_tour_stops

# ═══════════════════════════════════════════════════════════════════════════════
# STYLE-SPECIFIC NAVIGATION EXEMPTION (LOCAL-187)
# ═══════════════════════════════════════════════════════════════════════════════
# The anchor detector's is_navigation_paragraph() is TOO BROAD for style
# purposes. It classifies "Look for the sturdy stone walls" as navigation
# because "look for the" is in its pattern list. But that is attention-
# directing, not route-movement.
#
# For the STYLE validator, navigation means: the sentence moves the listener's
# BODY along a route. "Head south", "Turn left", "Continue past the fountain",
# "Cross the street", "Enter the building" — these are navigation.
#
# NOT navigation for style purposes:
# - "Look for the walls" — directs attention/observation
# - "Notice the facade" — directs attention
# - "Find the painting on the third floor" — could be nav or attention
#
# The distinction: ROUTE verbs (head, turn, walk, proceed, continue, cross,
# follow, go, move, step, exit, enter, approach, navigate, pass) + spatial
# context = navigation. ATTENTION verbs (look for, notice, observe, find,
# see, spot) = NOT exempt from style rules.
# ═══════════════════════════════════════════════════════════════════════════════

# Verbs that genuinely move the listener along a route
_STYLE_NAV_ROUTE_VERBS = [
    'head', 'turn', 'walk', 'proceed', 'continue', 'cross', 'follow',
    'make your way', 'find your way', 'go', 'move', 'step', 'exit',
    'enter', 'approach', 'navigate', 'pass',
]

# Directional / spatial words that confirm route context
_STYLE_NAV_DIRECTIONAL = {
    'left', 'right', 'straight', 'ahead', 'forward', 'north', 'south',
    'east', 'west', 'towards', 'toward', 'along', 'past', 'down', 'up',
    'through', 'across', 'around', 'back', 'onto', 'into',
    'on', 'to', 'the', 'inside', 'outside',
}

# Patterns for style-specific navigation (route movement only)
_STYLE_NAV_PATTERNS = [
    # Route verbs + directional: "Head south", "Turn left", "Walk along"
    r'\b(?:head|turn|walk|proceed|continue|go|move)\s+(?:left|right|straight|ahead|forward|towards?|north|south|east|west|along|past|down|up|around|across|back)\b',
    # "Make/find your way to/toward"
    r'\b(?:make|find)\s+your\s+way\b',
    # "Cross the street/bridge/square"
    r'\bcross\s+(?:the|this)\b',
    # "Follow the path/road/signs"
    r'\bfollow\s+(?:the|this)\b',
    # "Continue on/past/along"
    r'\bcontinue\s+(?:on|past|along|down|up|through|to)\b',
    # "Enter/exit the building/museum"
    r'\b(?:enter|exit)\s+(?:the|this)\b',
    # "Head south on Promenade" — route verb + compass + named road
    r'\b(?:head|turn|walk|proceed|continue)\s+(?:north|south|east|west)\s+(?:on|along|down|past)\b',
    # "Step inside/through/into"
    r'\bstep\s+(?:inside|through|into|out)\b',
]

_STYLE_NAV_COMPILED = [re.compile(p, re.IGNORECASE) for p in _STYLE_NAV_PATTERNS]


def _is_style_navigation_paragraph(paragraph: str) -> bool:
    """Determine if a paragraph is navigation FOR STYLE VALIDATION purposes.

    NARROWER than is_navigation_paragraph() from the anchor detector.
    Only exempts text that moves the listener's body along a route.
    Does NOT exempt attention-directing ("Look for the walls").

    Rules:
    - Short (<150 chars) + 1+ route-movement pattern → navigation
    - Short-to-medium (≤300 chars) + 2+ route-movement patterns → navigation
    - >50% sentence density of route-movement patterns → navigation
    """
    nav_matches = sum(1 for pat in _STYLE_NAV_COMPILED if pat.search(paragraph))

    if len(paragraph) < 150 and nav_matches >= 1:
        return True

    if nav_matches >= 2 and len(paragraph) <= 300:
        return True

    # Density gate
    sentences = re.split(r'[.!?]+', paragraph)
    sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 10]

    if not sentences:
        return False

    nav_sentences = 0
    for sent in sentences:
        sent_matches = sum(1 for pat in _STYLE_NAV_COMPILED if pat.search(sent))
        if sent_matches >= 1:
            nav_sentences += 1

    if len(sentences) >= 2 and nav_sentences / len(sentences) > 0.5:
        return True

    return False


def _is_style_navigation_sentence(sentence: str) -> bool:
    """Check if a single sentence is navigational for style purposes.

    Only route-movement sentences are exempt. "Look for X" is NOT exempt.
    """
    lower = sentence.lower().strip()
    for verb in _STYLE_NAV_ROUTE_VERBS:
        if lower.startswith(verb):
            rest = lower[len(verb):].strip()
            first_word = rest.split()[0] if rest.split() else ''
            if first_word in _STYLE_NAV_DIRECTIONAL:
                return True
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# RULE DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

# ─── R1: Imperatives aimed at the listener ──────────────────────────────────
# Sentence-initial base-form verb with no subject.
# Must be imperative form: "Feel the weight" fires, "Visitors notice" does NOT.

_R1_IMPERATIVE_VERBS = [
    'pay attention to', 'look at', 'look for', 'notice', 'feel', 'imagine',
    'explore', 'discover', 'consider', 'think about', 'observe',
    'picture', 'envision', 'contemplate', 'reflect on', 'ponder',
    'take a moment', 'take in', 'let yourself', 'allow yourself',
    'prepare to', 'prepare yourself',
]

# These verbs are route-movement verbs — when followed by directional content
# they should NOT fire R1.
_NAV_VERBS_R1_EXEMPT = {
    'head', 'turn', 'walk', 'proceed', 'continue', 'cross', 'follow',
    'make your way', 'find your way', 'go', 'move', 'step', 'exit',
    'enter', 'approach', 'navigate', 'pass',
}

# Directional / spatial words that indicate navigation context
_DIRECTIONAL_WORDS = {
    'left', 'right', 'straight', 'ahead', 'forward', 'north', 'south',
    'east', 'west', 'towards', 'toward', 'along', 'past', 'down', 'up',
    'through', 'across', 'around', 'back', 'onto', 'into',
}


def _split_sentences(text: str) -> List[str]:
    """Split text into sentences. Handles abbreviations minimally."""
    # Split on sentence-ending punctuation followed by space+capital or end
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z"\'])', text)
    # Also split on ? and ! that might not be followed by space
    result = []
    for part in parts:
        # Further split on ? if there's content after it
        subparts = re.split(r'(\?)', part)
        i = 0
        while i < len(subparts):
            if i + 1 < len(subparts) and subparts[i + 1] == '?':
                result.append(subparts[i] + '?')
                i += 2
            else:
                if subparts[i].strip():
                    result.append(subparts[i])
                i += 1
    return [s.strip() for s in result if s.strip()]


def _is_navigation_sentence(sentence: str) -> bool:
    """Check if a single sentence is navigational (for mixed-paragraph cases).

    Uses route-movement verbs only. "Look for X" is NOT navigation.
    """
    return _is_style_navigation_sentence(sentence)


def check_r1_imperatives(sentence: str) -> List[Dict]:
    """R1: Detect sentence-initial imperatives aimed at the listener.

    Fires when:
    - Sentence starts with a base-form verb from the list
    - No explicit subject before the verb (imperative form)

    Does NOT fire when:
    - Third person: "Visitors notice the asymmetry"
    - Navigation: "Head south on Promenade de la Croisette"
    """
    findings = []
    stripped = sentence.strip()
    if not stripped:
        return findings

    # Navigation exemption at sentence level
    if _is_navigation_sentence(stripped):
        return findings

    lower = stripped.lower()

    for verb in _R1_IMPERATIVE_VERBS:
        # Word-boundary match: "explore" must not match "Explorers" or "Explored"
        # Use re.match with \b at the end of the verb phrase to enforce this.
        if re.match(rf'{re.escape(verb)}\b', lower):
            # Verify it's imperative (no subject before verb)
            # If the sentence starts directly with the verb, it's imperative
            # "Feel the weight" → imperative
            # "You feel the weight" → R4 (not R1)
            findings.append({
                'rule_id': 'R1_IMPERATIVE',
                'severity': 'error',
                'sentence': stripped,
                'suggestion': f'Rewrite as declarative statement. Remove the imperative "{verb}" and state the fact directly.',
            })
            break  # Only one R1 finding per sentence

    return findings


# ─── R2: Questions ───────────────────────────────────────────────────────────

_INTERROGATIVE_OPENERS = [
    'how', 'what', 'why', 'where', 'when', 'who', 'is', 'are', 'does',
    'do', 'did', 'can', 'could', 'would', 'will', 'have', 'has',
]


def check_r2_questions(sentence: str) -> List[Dict]:
    """R2: Detect questions.

    Hard failure: sentence contains '?'
    Warning: interrogative opener without '?' (weaker signal — many are
    declaratives like "What began as a fishing village became…")
    """
    findings = []
    stripped = sentence.strip()
    if not stripped:
        return findings

    # Hard rule: contains ?
    if '?' in stripped:
        findings.append({
            'rule_id': 'R2_QUESTION',
            'severity': 'error',
            'sentence': stripped,
            'suggestion': 'Convert to a declarative statement about the POI.',
        })
        return findings  # Don't also flag as warning

    # Weaker: interrogative opener without ?
    lower = stripped.lower()
    first_word = lower.split()[0] if lower.split() else ''

    if first_word in _INTERROGATIVE_OPENERS:
        # Check it's NOT a declarative (heuristic: declaratives don't end with
        # a verb or have subject-verb inversion typical of questions)
        # The spec says these are warnings only — report but lower severity
        findings.append({
            'rule_id': 'R2_INTERROGATIVE_OPENER',
            'severity': 'warning',
            'sentence': stripped,
            'suggestion': 'Verify this is declarative, not a disguised question. If declarative (e.g., "What began as…"), ignore.',
        })

    return findings


# ─── R3: Suggestive exploration ──────────────────────────────────────────────
# LOCAL-187: Generalized to catch "as you [movement/discovery verb]" —
# the same construction as "as you explore" but with synonyms. The rule
# targets second-person + movement/discovery verb + implied invitation.

_R3_MOVEMENT_DISCOVERY_VERBS = (
    'explore|wander|stroll|meander|amble|roam|walk|venture|journey|travel|'
    'discover|uncover|find|encounter|traverse|navigate|drift|ramble'
)

_R3_PATTERNS = [
    # "as you explore/wander/stroll/meander…" (the core generalized pattern)
    rf'\bas you (?:{_R3_MOVEMENT_DISCOVERY_VERBS})\b',
    # "if you explore/wander…"
    rf'\bif you (?:{_R3_MOVEMENT_DISCOVERY_VERBS})\b',
    # "you can uncover / discover / find / explore / see / notice"
    r'\byou (?:can|could|will|would|may|might)\s+(?:uncover|discover|find|explore|see|notice|observe|detect|encounter)\b',
    # "explore further to…"
    r'\bexplore\s+further\b',
    # "discover for yourself"
    r'\bdiscover\s+for\s+(?:yourself|yourselves)\b',
    # "you will discover / uncover / find"
    r'\byou\s+will\s+(?:discover|uncover|find|encounter)\b',
    # "take time to explore"
    r'\btake\s+(?:time|a moment)\s+to\s+(?:explore|discover|uncover)\b',
]

_R3_COMPILED = [re.compile(p, re.IGNORECASE) for p in _R3_PATTERNS]


def check_r3_suggestive_exploration(sentence: str) -> List[Dict]:
    """R3: Detect suggestive/conditional exploration language."""
    findings = []
    stripped = sentence.strip()
    if not stripped:
        return findings

    for pat in _R3_COMPILED:
        if pat.search(stripped):
            findings.append({
                'rule_id': 'R3_SUGGESTIVE_EXPLORATION',
                'severity': 'error',
                'sentence': stripped,
                'suggestion': 'Replace with a direct declarative statement about the POI. Remove "you" + exploration verb.',
            })
            break  # One R3 finding per sentence

    return findings


# ─── R4: Prescribed feeling ──────────────────────────────────────────────────

_R4_PATTERNS = [
    # "you feel / you sense / you experience"
    r'\byou\s+(?:feel|sense|experience|perceive)\b',
    # "pressing down upon you"
    r'\b(?:pressing|weighing|bearing)\s+(?:down\s+)?(?:upon|on)\s+you\b',
    # "makes you realize / makes you feel"
    r'\bmakes?\s+you\s+(?:realize|feel|sense|understand|appreciate|experience)\b',
    # "you are overcome / you are struck"
    r'\byou\s+(?:are|\'re)\s+(?:overcome|struck|overwhelmed|moved|transported|enveloped|surrounded)\b',
    # "feel the weight / feel the presence"
    # (sentence-initial "Feel" is R1; mid-sentence "you feel" is R4)
    r'\bfeel\s+the\s+(?:weight|presence|power|force|energy|spirit|atmosphere|pull|warmth|cold|chill)\b',
    # "you can feel"
    r'\byou\s+(?:can|could|will|would|may|might)\s+(?:feel|sense|experience)\b',
    # "let the X wash over you"
    r'\b(?:wash|sweep|flow)\s+over\s+you\b',
    # "immerse yourself"
    r'\bimmerse\s+yourself\b',
    # "you find yourself"
    r'\byou\s+find\s+yourself\b',
]

_R4_COMPILED = [re.compile(p, re.IGNORECASE) for p in _R4_PATTERNS]


def check_r4_prescribed_feeling(sentence: str) -> List[Dict]:
    """R4: Detect prescribed visitor emotions/sensations."""
    findings = []
    stripped = sentence.strip()
    if not stripped:
        return findings

    for pat in _R4_COMPILED:
        if pat.search(stripped):
            findings.append({
                'rule_id': 'R4_PRESCRIBED_FEELING',
                'severity': 'error',
                'sentence': stripped,
                'suggestion': 'Rewrite as objective description. Remove "you" + feeling verb; describe what IS, not what the listener should feel.',
            })
            break  # One R4 finding per sentence

    return findings


# ─── R7: Hallucinated sensory data (D62, LOCAL-187) ─────────────────────────
# Distinct from R4. R4 catches INSTRUCTIONS about feeling ("you feel X").
# R7 catches FALSE CLAIMS about the world — asserting a sensory experience
# the listener cannot actually be having because the source is historical
# or absent.
#
# Examples that SHOULD fire:
#   "let the faint sound of waves lapping against the shore fill your ears"
#   "you can almost hear the echo of his brushstrokes"
#   "breathe in the faint scent of oil paint that still lingers in the air"
#
# Examples that should NOT fire (real present-tense sensory facts):
#   "The market smells of lavender and rotisserie chicken"
#   "The sound of waves is audible from the terrace"
#   "Salt air fills the promenade"
#
# The distinction: R7 targets sensory claims qualified by ABSENCE markers
# (almost, faint, still lingers, echo of, whispers of) or attached to
# something historical/impossible (his brushstrokes, centuries past,
# oil paint from 1936). A plain statement of present fact is fine.
#
# SEVERITY: WARNING — because reliably separating absent from present
# sensation is not 100% achievable with regex. An honest warning beats
# a wrong error. (Per task spec guidance.)

_R7_PATTERNS = [
    # "hear/echo of" + historical/artistic subject
    r'\b(?:you\s+can\s+)?(?:almost\s+)?hear\s+the\s+(?:echo|sound|whisper|murmur)\s+of\s+(?:his|her|their|the)\s+\w+',
    # "let the [faint/soft] sound of X fill your ears"
    r'\blet\s+the\s+(?:faint|soft|gentle|distant)?\s*(?:sound|noise|echo|whisper|murmur)\b.*\bfill\s+your\s+(?:ears|senses)\b',
    # "breathe in the FAINT/LINGERING scent of" — requires absence marker
    r'\bbreathe\s+in\s+the\s+(?:faint|lingering|subtle)\s+(?:scent|smell|fragrance|aroma|odor)\s+of\b',
    # "scent of [historical material] that still lingers"
    r'\b(?:scent|smell|fragrance)\s+of\s+(?:oil\s+paint|incense|gunpowder|spices|timber)\b.*\b(?:still|linger)',
    # "the faint/lingering scent/smell of X" (absence-qualified descriptor)
    r'\b(?:faint|lingering)\s+(?:scent|smell|fragrance|aroma)\s+of\b.*\b(?:still\s+)?linger',
    # "[whispers/echoes] of history/the past"
    r'\b(?:whispers?|echoes?)\s+of\s+(?:history|the\s+past|centuries|bygone|ancient|forgotten)\b',
    # "passageways/walls/halls echo with the whispers of history"
    r'\b(?:echo|resound|ring)\s+with\s+the\s+(?:whispers?|sounds?|echoes?|voices?)\s+of\s+(?:history|the\s+past|centuries|bygone)\b',
    # "almost taste/smell/hear/feel" (impossibility marker)
    r'\b(?:you\s+can\s+)?almost\s+(?:taste|smell|hear|feel)\b',
    # "fill your ears/nose/senses" with something qualified as faint/distant
    r'\b(?:faint|distant|soft|gentle)\s+(?:sound|noise|melody|music|fragrance|scent)\b.*\bfill\s+your\b',
]

_R7_COMPILED = [re.compile(p, re.IGNORECASE) for p in _R7_PATTERNS]


def check_r7_hallucinated_sensory(sentence: str) -> List[Dict]:
    """R7: Detect hallucinated/absent sensory claims (D62).

    Fires on assertions of sensory experience the listener cannot actually
    be having — historical sounds, absent smells, impossible perceptions.

    Does NOT fire on present-tense factual sensory descriptions without
    absence markers (e.g., "The market smells of lavender").

    Severity: WARNING (not error) because regex cannot perfectly distinguish
    absent from present sensation in all cases.
    """
    findings = []
    stripped = sentence.strip()
    if not stripped:
        return findings

    for pat in _R7_COMPILED:
        if pat.search(stripped):
            findings.append({
                'rule_id': 'R7_HALLUCINATED_SENSORY',
                'severity': 'warning',
                'sentence': stripped,
                'suggestion': 'This appears to assert a sensory experience the listener cannot actually have (historical/absent). Rewrite as factual description of what IS present, or remove.',
            })
            break  # One R7 finding per sentence

    return findings


# ═══════════════════════════════════════════════════════════════════════════════
# PARAGRAPH-LEVEL ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

def validate_paragraph(paragraph: str) -> Dict:
    """Validate a single paragraph against R1–R4, R7.

    Returns:
        {
            'is_navigation': bool,
            'findings': [{ rule_id, severity, sentence, suggestion }, ...],
            'rules_violated': set of rule_ids that fired,
        }
    """
    # Navigation exemption — uses STYLE-SPECIFIC test (narrower than anchor's)
    # Only genuine route-movement is exempt; attention-directing is NOT.
    if _is_style_navigation_paragraph(paragraph):
        return {
            'is_navigation': True,
            'findings': [],
            'rules_violated': set(),
        }

    sentences = _split_sentences(paragraph)
    all_findings = []

    for sentence in sentences:
        # Skip very short fragments
        if len(sentence) < 10:
            continue

        # Navigation exemption at sentence level for mixed paragraphs
        if _is_style_navigation_sentence(sentence):
            continue

        all_findings.extend(check_r1_imperatives(sentence))
        all_findings.extend(check_r2_questions(sentence))
        all_findings.extend(check_r3_suggestive_exploration(sentence))
        all_findings.extend(check_r4_prescribed_feeling(sentence))
        all_findings.extend(check_r7_hallucinated_sensory(sentence))

    rules_violated = set(f['rule_id'] for f in all_findings)

    return {
        'is_navigation': False,
        'findings': all_findings,
        'rules_violated': rules_violated,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TOUR-LEVEL ANALYSIS (reads from DB)
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_tour_style(tour_id: int, conn) -> Dict:
    """Analyze a tour for R1–R4 violations. Read-only."""
    import psycopg2.extras
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT id, tour_name, tour_content FROM audio_tours WHERE id = %s", (tour_id,))
    row = cur.fetchone()
    if not row or not row['tour_content']:
        return {'tour_id': tour_id, 'error': 'no content'}

    tour_name = row['tour_name']
    tour_content = row['tour_content']
    stops = parse_tour_stops(tour_content)

    totals = {
        'R1_IMPERATIVE': 0,
        'R2_QUESTION': 0,
        'R2_INTERROGATIVE_OPENER': 0,
        'R3_SUGGESTIVE_EXPLORATION': 0,
        'R4_PRESCRIBED_FEELING': 0,
        'R7_HALLUCINATED_SENSORY': 0,
        'navigation_paragraphs': 0,
        'clean_paragraphs': 0,
        'total_paragraphs': 0,
    }

    stop_results = []
    for stop in stops:
        para_results = []
        for para in stop['paragraphs']:
            result = validate_paragraph(para)
            result['text_preview'] = para[:200]
            para_results.append(result)

            totals['total_paragraphs'] += 1
            if result['is_navigation']:
                totals['navigation_paragraphs'] += 1
            elif not result['findings']:
                totals['clean_paragraphs'] += 1
            else:
                for f in result['findings']:
                    totals[f['rule_id']] += 1

        stop_results.append({
            'title': stop['title'],
            'paragraphs': para_results,
        })

    return {
        'tour_id': tour_id,
        'tour_name': tour_name,
        'stop_count': len(stops),
        'stops': stop_results,
        'totals': totals,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# REPORT
# ═══════════════════════════════════════════════════════════════════════════════

def run_report(tour_ids: List[int]) -> str:
    """Run the style validator over tours and produce the report."""
    conn = get_connection()

    lines = []
    lines.append("=" * 78)
    lines.append("STYLE VALIDATOR — LOCAL-184 + LOCAL-187: Instructions, Questions, Prescribed Feelings & Hallucinated Sensory")
    lines.append("=" * 78)
    lines.append(f"\nTours analyzed: {tour_ids}")
    lines.append("")

    # ── Michael's Buddha paragraph (the canonical test) ──────────────────────
    lines.append("-" * 78)
    lines.append("CANONICAL TEST: Michael's Buddha paragraph from ClickUp wdvrdaxaqj")
    lines.append("-" * 78)

    buddha_para = (
        "As you stand in the presence of the 'Statue de Bouddha', feel the weight "
        "of centuries pressing down upon you, a reminder of the enduring quest for "
        "inner peace and spiritual enlightenment that transcends cultural boundaries. "
        "How does this serenity manifest itself in the different representations of "
        "divinity and wisdom throughout the museum's diverse exhibits? Explore further "
        "and uncover the interconnectedness of human spirituality across time and space."
    )

    lines.append(f"\n  Text: \"{buddha_para}\"")
    lines.append("")

    result = validate_paragraph(buddha_para)
    rules_found = result['rules_violated']

    lines.append(f"  Rules violated: {sorted(rules_found)}")
    lines.append(f"  Total findings: {len(result['findings'])}")
    lines.append("")
    for f in result['findings']:
        lines.append(f"    [{f['rule_id']}] severity={f['severity']}")
        lines.append(f"      sentence: \"{f['sentence'][:120]}\"")
        lines.append(f"      suggestion: {f['suggestion']}")
        lines.append("")

    # Check acceptance criteria
    r1_fired = 'R1_IMPERATIVE' in rules_found
    r2_fired = 'R2_QUESTION' in rules_found
    r4_fired = 'R4_PRESCRIBED_FEELING' in rules_found

    lines.append(f"  Acceptance: R1 fires = {r1_fired} {'✓' if r1_fired else '✗'}")
    lines.append(f"  Acceptance: R2 fires = {r2_fired} {'✓' if r2_fired else '✗'}")
    lines.append(f"  Acceptance: R4 fires = {r4_fired} {'✓' if r4_fired else '✗'}")

    # ── Navigation exemption test ────────────────────────────────────────────
    lines.append("\n" + "-" * 78)
    lines.append("NAVIGATION EXEMPTION TEST")
    lines.append("-" * 78)

    nav_test = "Head south on Promenade de la Croisette"
    result_nav = validate_paragraph(nav_test)
    nav_ok = result_nav['is_navigation'] or (not result_nav['findings'])
    lines.append(f"\n  Text: \"{nav_test}\"")
    lines.append(f"  is_navigation: {result_nav['is_navigation']}")
    lines.append(f"  findings: {len(result_nav['findings'])}")
    lines.append(f"  Does NOT fire: {'✓' if nav_ok else '✗'}")

    # Also test a longer nav sentence
    nav_test2 = "Head south on Promenade de la Croisette and continue past the Palais des Festivals until you reach the old port."
    result_nav2 = validate_paragraph(nav_test2)
    nav_ok2 = result_nav2['is_navigation'] or (not result_nav2['findings'])
    lines.append(f"\n  Text: \"{nav_test2}\"")
    lines.append(f"  is_navigation: {result_nav2['is_navigation']}")
    lines.append(f"  findings: {len(result_nav2['findings'])}")
    lines.append(f"  Does NOT fire: {'✓' if nav_ok2 else '✗'}")

    # ── R1 word-boundary regression test ────────────────────────────────────
    lines.append("\n" + "-" * 78)
    lines.append("R1 WORD-BOUNDARY REGRESSION (must NOT fire — nouns derived from verbs)")
    lines.append("-" * 78)

    r1_false_positives = [
        "Observers considered the design scandalous in 1887.",
        "Discoveries were made beneath the chapel floor in 1932.",
        "Explorers landed here in 1388 and named the cape.",
    ]

    r1_regression_pass = True
    for sent in r1_false_positives:
        result_r1 = validate_paragraph(sent)
        r1_errors = [f for f in result_r1['findings'] if f['rule_id'] == 'R1_IMPERATIVE']
        ok = len(r1_errors) == 0
        if not ok:
            r1_regression_pass = False
        lines.append(f"\n  Text: \"{sent}\"")
        lines.append(f"  R1 fires: {len(r1_errors)} {'✓ (correctly not flagged)' if ok else '✗ FALSE POSITIVE'}")

    lines.append(f"\n  R1 word-boundary regression: {'ALL PASS ✓' if r1_regression_pass else 'FAILURES DETECTED ✗'}")

    # ── Declarative exemption test (R2 warning vs error) ─────────────────────
    lines.append("\n" + "-" * 78)
    lines.append("DECLARATIVE EXEMPTION TEST (R2 — should NOT fire as errors)")
    lines.append("-" * 78)

    declaratives = [
        "What began as a fishing village became the busiest yacht harbour in Europe.",
        "When the museum opened in 1963, Chagall attended in person.",
        "Where the two rivers meet, the ramparts still stand.",
    ]

    for decl in declaratives:
        result_d = validate_paragraph(decl)
        errors = [f for f in result_d['findings'] if f['severity'] == 'error']
        warnings = [f for f in result_d['findings'] if f['severity'] == 'warning']
        lines.append(f"\n  Text: \"{decl}\"")
        lines.append(f"  Errors: {len(errors)} {'✓ (zero errors)' if not errors else '✗ SHOULD NOT ERROR'}")
        if warnings:
            lines.append(f"  Warnings: {len(warnings)} (expected — interrogative opener, non-blocking)")

    # ── Per-tour analysis ────────────────────────────────────────────────────
    lines.append("\n" + "=" * 78)
    lines.append("PER-TOUR RESULTS")
    lines.append("=" * 78)

    grand_totals = {
        'R1_IMPERATIVE': 0,
        'R2_QUESTION': 0,
        'R2_INTERROGATIVE_OPENER': 0,
        'R3_SUGGESTIVE_EXPLORATION': 0,
        'R4_PRESCRIBED_FEELING': 0,
        'R7_HALLUCINATED_SENSORY': 0,
        'navigation_paragraphs': 0,
        'clean_paragraphs': 0,
        'total_paragraphs': 0,
        'failing_paragraphs': 0,
    }

    all_results = []
    for tid in tour_ids:
        result = analyze_tour_style(tid, conn)
        all_results.append(result)

    for result in all_results:
        if 'error' in result:
            lines.append(f"\n  Tour {result['tour_id']}: {result.get('error')}")
            continue

        t = result['totals']
        total = t['total_paragraphs']
        if total == 0:
            continue

        content_paras = total - t['navigation_paragraphs']
        failing = content_paras - t['clean_paragraphs']

        lines.append(f"\n{'─' * 78}")
        lines.append(f"Tour {result['tour_id']}: {result['tour_name']}")
        lines.append(f"  Stops: {result['stop_count']}, Paragraphs: {total}")
        lines.append(f"  Navigation (exempt): {t['navigation_paragraphs']}")
        lines.append(f"  Content paragraphs: {content_paras}")
        lines.append(f"  Clean (no violations): {t['clean_paragraphs']}")
        lines.append(f"  Failing (1+ violation): {failing}")
        if content_paras > 0:
            lines.append(f"  Failure rate: {100*failing/content_paras:.1f}%")
        lines.append(f"")
        lines.append(f"  Per-rule counts (sentences, not paragraphs):")
        lines.append(f"    R1 (imperatives):           {t['R1_IMPERATIVE']}")
        lines.append(f"    R2 (questions — error):     {t['R2_QUESTION']}")
        lines.append(f"    R2 (interrog opener — warn):{t['R2_INTERROGATIVE_OPENER']}")
        lines.append(f"    R3 (suggestive exploration): {t['R3_SUGGESTIVE_EXPLORATION']}")
        lines.append(f"    R4 (prescribed feeling):    {t['R4_PRESCRIBED_FEELING']}")
        lines.append(f"    R7 (hallucinated sensory):  {t['R7_HALLUCINATED_SENSORY']}")

        # Accumulate grand totals
        for k in grand_totals:
            if k == 'failing_paragraphs':
                grand_totals[k] += failing
            elif k in t:
                grand_totals[k] += t[k]

        # Show up to 3 examples per rule per tour
        examples_shown = {'R1_IMPERATIVE': 0, 'R2_QUESTION': 0,
                          'R3_SUGGESTIVE_EXPLORATION': 0, 'R4_PRESCRIBED_FEELING': 0,
                          'R7_HALLUCINATED_SENSORY': 0}
        MAX_EXAMPLES = 2

        for stop in result['stops']:
            for para in stop['paragraphs']:
                for finding in para['findings']:
                    rid = finding['rule_id']
                    if rid in examples_shown and examples_shown[rid] < MAX_EXAMPLES:
                        lines.append(f"    Example [{rid}] @ {stop['title'][:30]}:")
                        lines.append(f"      \"{finding['sentence'][:120]}\"")
                        examples_shown[rid] += 1

    # ── Grand totals ──
    lines.append("\n" + "=" * 78)
    lines.append("GRAND TOTALS")
    lines.append("=" * 78)

    gt = grand_totals
    total = gt['total_paragraphs']
    nav = gt['navigation_paragraphs']
    content = total - nav
    failing = gt['failing_paragraphs']

    lines.append(f"  Total paragraphs: {total}")
    lines.append(f"  Navigation (exempt): {nav}")
    lines.append(f"  Content paragraphs: {content}")
    lines.append(f"  Clean: {gt['clean_paragraphs']}")
    lines.append(f"  Failing (1+ violation): {failing}")
    if content > 0:
        lines.append(f"  Overall failure rate: {100*failing/content:.1f}%")
    lines.append(f"")
    lines.append(f"  Sentence-level counts:")
    lines.append(f"    R1 (imperatives):            {gt['R1_IMPERATIVE']}")
    lines.append(f"    R2 (questions — error):      {gt['R2_QUESTION']}")
    lines.append(f"    R2 (interrog opener — warn): {gt['R2_INTERROGATIVE_OPENER']}")
    lines.append(f"    R3 (suggestive exploration):  {gt['R3_SUGGESTIVE_EXPLORATION']}")
    lines.append(f"    R4 (prescribed feeling):     {gt['R4_PRESCRIBED_FEELING']}")
    lines.append(f"    R7 (hallucinated sensory):   {gt['R7_HALLUCINATED_SENSORY']}")

    # ── R5 note ──
    lines.append("\n" + "-" * 78)
    lines.append("NOTE ON R5 (POI-specific grounding)")
    lines.append("-" * 78)
    lines.append("  R5 maps to the existing stop_anchor_detector_v2.py")
    lines.append("  (ANCHORED / UNLINKED_ENTITY classification).")
    lines.append("  Not reimplemented here — that is the substance detector.")
    lines.append("  This file is the FORM detector (R1–R4, R7).")

    # ── Database verification ──
    lines.append("\n" + "-" * 78)
    lines.append("DATABASE VERIFICATION")
    lines.append("-" * 78)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    count = cur.fetchone()[0]
    lines.append(f"  audio_tours row count: {count}")
    lines.append(f"  Read-only: no INSERT, UPDATE, or DELETE executed")

    conn.close()
    return '\n'.join(lines)


if __name__ == '__main__':
    # 7 baseline tours + tours 152, 156, and 162
    TOUR_IDS = [1, 29, 12, 24, 14, 46, 44, 152, 156, 162]
    report = run_report(TOUR_IDS)
    print(report)
