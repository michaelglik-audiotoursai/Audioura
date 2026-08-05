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
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

# Import dependencies from tests/ — these are shared helpers used by both
# the production validator and the test suite.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))
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

# ── TRANSPORT-MODE ROUTE VERBS ──────────────────────────────────────────────
# Derived from the transport modes the pipeline actually generates
# (generate_tour_text.py: _TRANSPORT_MODE_KEYWORDS → on_foot, bike, animal,
# vehicle, country_scale). Each mode has verbs describing route movement in
# that mode. A new transport mode added there should get verbs here — this
# is the SINGLE place to update.
#
# WHY THIS DOES NOT REINTRODUCE D69's PROBLEM:
# D69 said closed DETECTION lists miss the next verb. R1's design is inverted
# — it detects ANY sentence-initial base-form verb, then subtracts exemptions.
# These transport verbs are EXEMPTION entries, not detection entries. Each one
# still requires a directional word after it (verb + directional = route
# movement). "Cycle" alone won't exempt; "Cycle south on the main road" will.
# The exemption set is structurally bounded: finite transport modes × finite
# verbs per mode, each gated by directional context.
_TRANSPORT_MODE_ROUTE_VERBS = {
    # on_foot (default/walking tours)
    'on_foot': ['walk', 'step', 'hike', 'stroll'],
    # bike mode (generate_tour_text.py: bike|biking|cycling)
    'bike': ['cycle', 'bike', 'pedal', 'ride'],
    # animal mode (camel, horse, dogsled, etc.)
    'animal': ['ride', 'trot', 'gallop'],
    # vehicle mode (car, jeep, motorcycle, scooter, etc.)
    'vehicle': ['drive', 'ride', 'cruise'],
    # country_scale (road trip, safari, cross-country)
    'country_scale': ['drive', 'cruise', 'ride'],
}

# Verbs that genuinely move the listener along a route.
# Core verbs (mode-independent) + all transport-mode verbs merged.
_STYLE_NAV_ROUTE_VERBS_CORE = [
    'head', 'turn', 'proceed', 'continue', 'cross', 'follow',
    'make your way', 'find your way', 'go', 'move', 'exit',
    'enter', 'approach', 'navigate', 'pass', 'start', 'set off',
]
# Merge core + all transport mode verbs (deduplicated, order preserved)
_STYLE_NAV_ROUTE_VERBS = list(dict.fromkeys(
    _STYLE_NAV_ROUTE_VERBS_CORE +
    [v for verbs in _TRANSPORT_MODE_ROUTE_VERBS.values() for v in verbs]
))

# Directional / spatial words that confirm route context
_STYLE_NAV_DIRECTIONAL = {
    'left', 'right', 'straight', 'ahead', 'forward', 'north', 'south',
    'east', 'west', 'northeast', 'northwest', 'southeast', 'southwest',
    'towards', 'toward', 'along', 'past', 'down', 'up',
    'through', 'across', 'around', 'back', 'onto', 'into',
    'on', 'to', 'the', 'inside', 'outside',
}

# Patterns for style-specific navigation (route movement only)
# RECONCILIATION (LOCAL-224): The paragraph-level patterns now use the same
# verb set as _STYLE_NAV_ROUTE_VERBS so both heuristics agree. The sentence-
# level check (_is_style_navigation_sentence) is AUTHORITATIVE — it is precise
# (verb + directional = route). The paragraph-level check is a fallback density
# heuristic for mixed paragraphs where no single sentence qualifies but the
# overall paragraph is clearly navigational (e.g. "Continue straight until the
# roundabout, then look for parking."). When they disagree, sentence-level wins
# at the sentence grain, paragraph-level only exempts the WHOLE paragraph.

# Build the verb alternation from the canonical verb list (single-word only)
_NAV_SINGLE_WORD_VERBS = [v for v in _STYLE_NAV_ROUTE_VERBS if ' ' not in v]
_NAV_VERB_ALT = '|'.join(sorted(_NAV_SINGLE_WORD_VERBS, key=len, reverse=True))

_STYLE_NAV_PATTERNS = [
    # Route verbs + directional: "Head south", "Cycle along", "Ride north"
    r'\b(?:' + _NAV_VERB_ALT + r')\s+(?:left|right|straight|ahead|forward|towards?|north|south|east|west|along|past|down|up|around|across|back)\b',
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
    # Route verb + compass + named road: "Cycle south on the main road"
    r'\b(?:' + _NAV_VERB_ALT + r')\s+(?:north|south|east|west|northeast|northwest|southeast|southwest)\s+(?:on|along|down|past)\b',
    # "Step inside/through/into"
    r'\bstep\s+(?:inside|through|into|out)\b',
    # "Start cycling/biking/riding + directional" — composite verb phrase
    r'\bstart\s+(?:cycling|biking|riding|driving|walking|hiking)\s+(?:north|south|east|west|northeast|northwest|southeast|southwest|along|towards?|down|up|through|across)\b',
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

    LOCAL-224: Also handles composite verb phrases where a route verb is followed
    by a transport gerund before the directional word:
      "Start cycling south…" → start + cycling + south → navigation
      "Start biking southeast…" → start + biking + southeast → navigation
    The gerund must be a known transport-movement word; "Start looking south"
    does NOT exempt (looking is attention, not transport).

    LOCAL-255: Also handles "Start your ride/journey/trip at X and pedal..."
    where the transport mode is explicit as a noun after "your".
    """
    lower = sentence.lower().strip()

    # Transport gerunds that indicate route movement (not attention)
    _TRANSPORT_GERUNDS = {
        'cycling', 'biking', 'riding', 'driving', 'walking', 'hiking',
        'pedaling', 'pedalling', 'cruising', 'trotting', 'galloping',
        'strolling',
    }

    # Transport nouns after "your" that indicate navigation intent:
    # "Start your ride at...", "Begin your journey from..."
    _TRANSPORT_NOUNS = {
        'ride', 'journey', 'trip', 'route', 'tour', 'trek', 'hike',
        'walk', 'cycle', 'bike',
    }

    # Verbs too general-purpose to be confirmed by weak directional words
    # like 'the', 'on', 'to'. These need either a strong directional (compass,
    # left/right, along, etc.) or a transport gerund + directional.
    _NEEDS_STRONG_DIRECTIONAL = {'start', 'set'}
    _STRONG_DIRECTIONAL = _STYLE_NAV_DIRECTIONAL - {'the', 'on', 'to'}

    for verb in _STYLE_NAV_ROUTE_VERBS:
        if lower.startswith(verb):
            rest = lower[len(verb):].strip()
            words = rest.split()
            if not words:
                continue
            first_word = words[0]

            # Pick directional set based on verb generality
            verb_base = verb.split()[0]  # 'set off' → 'set', 'make your way' → 'make'
            directional_set = (_STRONG_DIRECTIONAL
                               if verb_base in _NEEDS_STRONG_DIRECTIONAL
                               else _STYLE_NAV_DIRECTIONAL)

            # Direct match: verb + directional → navigation
            if first_word in directional_set:
                return True
            # Composite match: verb + transport gerund + directional → navigation
            # e.g. "Start cycling south", "Set off riding north"
            if first_word in _TRANSPORT_GERUNDS and len(words) >= 2:
                second_word = words[1]
                if second_word in _STYLE_NAV_DIRECTIONAL:
                    return True
            # LOCAL-255: Possessive match: verb + "your" + transport noun → navigation
            # e.g. "Start your ride at Cap d'Antibes and pedal east"
            if first_word == 'your' and len(words) >= 2:
                second_word = words[1]
                if second_word in _TRANSPORT_NOUNS:
                    # Confirm there's a transport verb later in the sentence
                    # (pedal, cycle, ride, walk, etc.) OR a directional word
                    rest_of_sentence = ' '.join(words[2:])
                    has_transport_verb = bool(re.search(
                        r'\b(?:pedal|cycle|bike|ride|walk|hike|drive|cruise)\b',
                        rest_of_sentence
                    ))
                    has_directional = any(d in rest_of_sentence.split()
                                         for d in _STRONG_DIRECTIONAL)
                    if has_transport_verb or has_directional:
                        return True
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# RULE DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

# ─── R1: Imperatives aimed at the listener ──────────────────────────────────
# LOCAL-196: INVERTED DESIGN — detect sentence-initial base-form verb with no
# subject (the grammatical form of an imperative), then subtract exemptions.
#
# Why inverted: English imperatives are OPEN-CLASS. A closed verb list (the old
# design, 22 entries) will always miss the next verb. Exemptions are closed —
# you can enumerate the small set of non-verb words that legitimately start
# English sentences.
#
# TECHNIQUE: Morphological heuristics (no POS tagger dependency).
#   1. Extract the first word (or multi-word phrase for known patterns).
#   2. Reject if it matches a NON-VERB gate (determiners, pronouns, prepositions,
#      conjunctions, known nouns/adjectives that commonly start sentences).
#   3. Reject if the word has non-base-form morphology (-ed, -ing, -s/-es with
#      exceptions for verbs that naturally end in -s like "pass").
#   4. Reject if the word is capitalized AND the next word is also lowercase
#      (heuristic: "Visitors notice…" — capitalized noun + verb).
#   5. What remains is a sentence-initial base-form verb = imperative.
#
# FAILURE MODES:
#   - False positives on rare nouns not in the exemption set that happen to
#     look like verb base forms. Mitigated by the large exemption set.
#   - False negatives on imperative multi-word phrases not in _R1_MULTI_WORD_VERBS.
#     Mitigated by catching the first word alone in most cases.
#   - Words ending in -ss (pass, cross) need explicit handling since the -s
#     filter would incorrectly reject them.

# ── Multi-word imperative phrases (detected before single-word analysis) ────
_R1_MULTI_WORD_VERBS = [
    'pay attention to', 'look at', 'look for', 'look up', 'look around',
    'think about', 'think of',
    'take a moment', 'take in', 'take note',
    'let yourself', 'let the', 'let this',
    'allow yourself', 'allow the',
    'prepare to', 'prepare yourself',
    'make your way', 'find your way',
    'reflect on', 'reflect upon',
    'keep in mind', 'bear in mind',
]

# ── Route-movement verbs — exempt ONLY when followed by directional content ─
# LOCAL-196 FIX: The old design exempted these unconditionally. "Turn your
# attention" is NOT navigation. Now require directional words after the verb.
# LOCAL-224: Derived from _STYLE_NAV_ROUTE_VERBS (transport-mode-aware) —
# single source of truth for which verbs count as route movement.
_NAV_VERBS_R1 = set(v for v in _STYLE_NAV_ROUTE_VERBS if ' ' not in v)

# Directional / spatial words that confirm navigation context
_DIRECTIONAL_WORDS = {
    'left', 'right', 'straight', 'ahead', 'forward', 'north', 'south',
    'east', 'west', 'towards', 'toward', 'along', 'past', 'down', 'up',
    'through', 'across', 'around', 'back', 'onto', 'into',
    'northeast', 'northwest', 'southeast', 'southwest',
}

# ── NON-VERB GATE: words that start sentences but are NOT imperative verbs ──
# This is the EXEMPTION list — the thing that needs enumerating.
_R1_NON_VERB_STARTERS = {
    # Determiners / articles
    'the', 'a', 'an', 'this', 'that', 'these', 'those', 'each', 'every',
    'some', 'any', 'all', 'both', 'few', 'many', 'much', 'most', 'no',
    'several', 'such', 'either', 'neither',
    # Pronouns
    'i', 'you', 'he', 'she', 'it', 'we', 'they', 'one', 'who', 'what',
    'which', 'whom', 'whose', 'there', 'here', 'everyone', 'someone',
    'anyone', 'nobody', 'nothing', 'something', 'everything', 'whoever',
    'its', 'his', 'her', 'their', 'our', 'my', 'your',
    # Prepositions starting adverbial phrases
    'in', 'on', 'at', 'by', 'for', 'with', 'from', 'to', 'of', 'about',
    'after', 'before', 'during', 'between', 'among', 'through', 'above',
    'below', 'under', 'over', 'behind', 'beside', 'beyond', 'within',
    'without', 'throughout', 'beneath', 'upon', 'against', 'along',
    'inside', 'outside', 'despite', 'unlike', 'near', 'across',
    'amidst', 'amid', 'amongst', 'atop', 'versus',
    # Conjunctions / connectors
    'and', 'but', 'or', 'nor', 'so', 'yet', 'although', 'because',
    'since', 'while', 'whereas', 'unless', 'until', 'though', 'however',
    'moreover', 'furthermore', 'meanwhile', 'nevertheless', 'otherwise',
    'therefore', 'thus', 'hence', 'accordingly', 'consequently',
    'additionally', 'alternatively', 'conversely', 'similarly',
    # Interrogatives (handled by R2, not R1)
    'how', 'why', 'where', 'when', 'whether',
    # Adverbs that commonly start sentences
    'today', 'now', 'then', 'once', 'soon', 'already', 'still', 'just',
    'also', 'only', 'even', 'never', 'always', 'often', 'perhaps',
    'certainly', 'clearly', 'obviously', 'apparently', 'unfortunately',
    'remarkably', 'interestingly', 'historically', 'originally',
    'eventually', 'finally', 'initially', 'subsequently', 'recently',
    'formerly', 'previously', 'currently', 'notably', 'importantly',
    'significantly', 'essentially', 'fundamentally', 'traditionally',
    'typically', 'generally', 'specifically', 'particularly', 'especially',
    # Time words
    'yesterday', 'tomorrow', 'later', 'earlier', 'annually', 'daily',
    # Common sentence-initial nouns/adjectives that look like verbs
    # (This is the set that prevents false positives on derived forms)
    'visitors', 'explorers', 'travelers', 'travellers', 'observers',
    'pilgrims', 'tourists', 'locals', 'residents', 'architects',
    'artists', 'builders', 'craftsmen', 'designers', 'engineers',
    'historians', 'merchants', 'monks', 'painters', 'scholars',
    'sculptors', 'settlers', 'soldiers', 'traders', 'workers',
    'walking', 'running', 'swimming', 'cycling', 'hiking',
    'located', 'built', 'designed', 'constructed', 'established',
    'founded', 'created', 'completed', 'opened', 'dedicated',
    'commissioned', 'renovated', 'restored', 'demolished', 'abandoned',
    'surrounded', 'situated', 'nestled', 'perched', 'overlooking',
    # Adjectives
    'ancient', 'modern', 'old', 'new', 'great', 'small', 'large',
    'beautiful', 'stunning', 'impressive', 'magnificent', 'grand',
    'famous', 'renowned', 'notable', 'prominent', 'significant',
    'original', 'unique', 'distinctive', 'remarkable', 'extraordinary',
    'local', 'national', 'international', 'royal', 'imperial',
    'medieval', 'gothic', 'baroque', 'classical', 'contemporary',
    'bold', 'bright', 'dark', 'tall', 'vast', 'wide', 'long', 'deep',
    'rich', 'rare', 'fine', 'pure', 'plain', 'stark', 'sheer',
    # Nouns commonly starting tour sentences
    'construction', 'renovation', 'restoration', 'completion',
    'establishment', 'foundation', 'discovery', 'exploration',
    'art', 'architecture', 'history', 'culture', 'music', 'nature',
    'stone', 'marble', 'glass', 'iron', 'bronze', 'gold', 'silver',
    'water', 'light', 'color', 'colour', 'space', 'time',
    'people', 'men', 'women', 'children', 'families', 'generations',
    'years', 'centuries', 'decades', 'days',
    # Number words
    'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten',
    'hundred', 'thousand', 'million',
    # Proper-noun-like starters (will also be caught by capitalization heuristic)
    'french', 'italian', 'spanish', 'english', 'german', 'roman',
    'greek', 'european', 'mediterranean', 'african', 'asian',
}

# ── Words that end in -s/-es but ARE valid base-form verbs ──────────────────
# (Not 3rd-person singular — they genuinely end in -ss, -us, etc.)
_BASE_FORM_DESPITE_S = {
    'pass', 'cross', 'toss', 'miss', 'kiss', 'press', 'stress', 'address',
    'assess', 'access', 'process', 'express', 'focus', 'plus', 'bus',
    'witness', 'harness', 'bypass',
}

# ── Words ending in nominalization suffixes that ARE valid verbs ─────────────
# These would otherwise be rejected by the suffix filter.
_VERB_DESPITE_SUFFIX = {
    'position', 'mention', 'question', 'station', 'fashion', 'function',
    'motion', 'section', 'auction', 'portion', 'ration', 'sanction',
    'petition', 'commission', 'condition', 'audition', 'transition',
    'imagine', 'determine', 'examine', 'combine', 'decline', 'define',
    'discipline', 'undermine', 'outline', 'confine',
    'marvel', 'travel', 'channel', 'model', 'level', 'label',
    'total', 'signal', 'rival', 'spiral',
    'experience', 'reference', 'sentence', 'silence', 'balance', 'influence',
    'note', 'practice', 'notice', 'place', 'trace', 'embrace', 'face',
    'surface', 'replace', 'advance',
    'involve', 'resolve', 'dissolve', 'evolve',
    'sample', 'tremble', 'tumble', 'stumble', 'fumble', 'humble',
    'savor', 'savour', 'favour', 'favor', 'honour', 'honor',
}

# ── Suffixes that indicate NON-base-form (past, progressive, 3rd person) ────
_NON_BASE_SUFFIXES = re.compile(
    r'(?:'
    r'ed$|'          # past tense / past participle
    r'ing$|'         # present participle / gerund
    r'tion$|'        # nominalization (construction, restoration)
    r'ment$|'        # nominalization (establishment, movement)
    r'ness$|'        # nominalization (darkness, awareness)
    r'ity$|'         # nominalization (acity, university)
    r'ance$|ence$|'  # nominalization (distance, presence)
    r'ism$|'         # nominalization (modernism)
    r'ist$|'         # agent noun (artist, tourist)
    r'ous$|'         # adjective (famous, gorgeous)
    r'ful$|'         # adjective (beautiful, powerful)
    r'ive$|'         # adjective (impressive, massive)
    r'ble$|'         # adjective (remarkable, notable)
    r'al$|'          # adjective (original, medieval)
    r'ial$|'         # adjective (imperial, commercial)
    r'ical$|'        # adjective (historical, classical)
    r'ary$|'         # adjective (ordinary, legendary)
    r'ly$'           # adverb (recently, remarkably)
    r')',
    re.IGNORECASE
)

# ── Words ending in -s that are likely 3rd-person (NOT base form) ───────────
def _looks_like_third_person_s(word: str) -> bool:
    """Heuristic: word ends in -s/-es and is likely 3rd-person singular.

    Returns True for "stands", "remains", "features" etc.
    Returns False for "pass", "cross" (genuine base forms ending in -ss).
    """
    lower = word.lower()
    if lower in _BASE_FORM_DESPITE_S:
        return False
    # Words ending in -ss are base forms (pass, cross, toss)
    if lower.endswith('ss'):
        return False
    # Words ending in -s (but not -ss) after a consonant or vowel+consonant
    # are likely 3rd person: "stands", "remains", "features", "rises"
    if lower.endswith('s') and len(lower) > 3:
        return True
    return False


def _is_likely_noun_subject(sentence: str) -> bool:
    """Heuristic: Does the sentence start with a noun phrase (subject)?

    Catches: "Visitors notice…", "The building stands…", "Walking tours began…"
    Pattern: Capitalized word followed by a lowercase verb-like word.

    Key insight: In English, a capitalized word at sentence start followed by
    a lowercase word is almost always Noun + Verb (declarative), not an
    imperative. Imperatives start with the verb directly.

    But we must NOT reject single-word-start sentences like "Stand at the entrance"
    — "Stand" is capitalized only because it's sentence-initial.
    """
    words = sentence.split()
    if len(words) < 2:
        return False

    first = words[0]
    # If the first word ends in -s/-ers/-ors/-ants/-ents — likely a plural noun
    lower_first = first.lower()
    if re.match(r'.*(?:ers|ors|ants|ents|ists|ians|ites|ives|ures)$', lower_first):
        return True
    # "Discoveries", "Observations" etc — nominalized plurals
    if re.match(r'.*(?:tions|ments|nesses|ities|ances|ences|isms)$', lower_first):
        return True

    return False


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


def _check_nav_sentence_suggestive_tail(sentence: str) -> List[Dict]:
    """LOCAL-233: Clause-level navigation exemption.

    A sentence that starts with genuine navigation may have a suggestive tail
    after a comma, conjunction, or participle phrase. The navigation exemption
    covers ONLY the route-movement clause, not the whole sentence.

    Example:
      "Pedal along the coastline, envisioning the hidden coves and immersing
       yourself in the beauty."
      → "Pedal along the coastline" = navigation (exempt)
      → "envisioning the hidden coves and immersing yourself..." = suggestive

    The SPLIT: find the first comma after the navigation verb phrase.
    The tail after that split point is checked for:
      1. R3/R4 patterns (existing rules for suggestive/prescribed feeling)
      2. Prescriptive gerund participials — "envisioning", "immersing yourself",
         "absorbing", "imagining" — which are imperative-equivalent in context.
         These only fire in navigation tails (a gerund in free prose is not
         automatically prescriptive).
      3. Mid-sentence imperatives (base-form verb after the comma)

    Returns findings from the tail, or empty list if the tail is clean.
    """
    findings = []
    stripped = sentence.strip()
    if not stripped:
        return findings

    # Find the split point: first comma after the navigation verb phrase
    comma_idx = stripped.find(',')
    if comma_idx < 0:
        return findings  # No comma → entire sentence is navigation, exempt

    tail = stripped[comma_idx + 1:].strip()
    if not tail:
        return findings

    # Check if the tail is ALSO navigation (e.g. "Turn left, then continue straight")
    # If so, the whole sentence is navigation — exempt.
    if _is_style_navigation_sentence(tail):
        return findings

    # ── Check R3 (suggestive) and R4 (prescribed feeling) on the tail ──
    findings.extend(check_r3_suggestive_exploration(tail))
    findings.extend(check_r4_prescribed_feeling(tail))

    # ── LOCAL-233: Prescriptive gerund participials in navigation tails ──
    # "envisioning the hidden coves", "immersing yourself in the beauty",
    # "absorbing the atmosphere", "imagining the past" — these are
    # imperative-equivalent when attached to a navigation clause.
    # They prescribe what the listener should experience while moving.
    if not findings:  # Only check if R3/R4 didn't already fire
        _NAV_TAIL_PRESCRIPTIVE_GERUNDS = re.compile(
            r'\b(?:'
            r'envisioning|imagining|picturing|visualizing|visualising|'
            r'absorbing|embracing|savoring|savouring|relishing|'
            r'contemplating|pondering|reflecting|marveling|marvelling|'
            r'immersing\s+yourself|letting\s+yourself|allowing\s+yourself'
            r')\b',
            re.IGNORECASE
        )
        if _NAV_TAIL_PRESCRIPTIVE_GERUNDS.search(tail):
            findings.append({
                'rule_id': 'R4_PRESCRIBED_FEELING',
                'severity': 'error',
                'sentence': stripped,
                'suggestion': 'The navigation clause is exempt, but the participial tail prescribes feeling/experience. Rewrite the tail as factual content or remove it.',
            })

    # ── Check if the tail itself starts with a mid-sentence imperative ──
    # (after the comma). This catches "Pedal along, take in the sight of..."
    if not findings:  # Only if nothing else fired
        tail_verb = _check_clause_for_imperative(tail)
        if tail_verb:
            findings.append({
                'rule_id': 'R1_IMPERATIVE',
                'severity': 'error',
                'sentence': stripped,
                'suggestion': f'Rewrite as declarative statement. Remove the imperative "{tail_verb}" and state the fact directly.',
            })

    return findings


def _extract_clause_after_subordinate(sentence: str):
    """Extract the main clause after a leading subordinate clause.

    LOCAL-233: Detects the pattern "<subordinate clause>, <main clause>" where
    the subordinate clause starts with a known subordinating conjunction or
    adverbial phrase (As, While, When, After, Before, Once, Upon, If).

    Returns the main clause (after the comma) if the pattern matches, else None.

    The pattern is: sentence starts with a subordinating word, has a comma
    followed by a space and then content that could be an imperative.

    Examples that match:
      "As you arrive at X, pause to take in..." → "pause to take in..."
      "While cycling past Z, notice the..." → "notice the..."
      "As you stand before Y, take in the sight of..." → "take in the sight of..."

    Examples that do NOT match (no subordinate clause):
      "Pause to take in the view." → None (no leading clause)
      "The chapel, built in 1648, stands..." → None (comma is parenthetical)
    """
    lower = sentence.lower().strip()

    # Known subordinating openers that introduce a temporal/conditional clause
    # before the imperative. These are the ONLY patterns where a mid-sentence
    # imperative legitimately appears in our pipeline's house style.
    _SUBORDINATE_STARTERS = (
        'as you ', 'as we ', 'as the ',
        'while you ', 'while cycling', 'while walking', 'while biking',
        'while riding', 'while hiking', 'while pedaling', 'while pedalling',
        'while driving', 'while strolling',
        'when you ', 'when the ',
        'after you ', 'after the ',
        'before you ', 'before the ',
        'once you ', 'once the ',
        'upon ',
        'if you ',
    )

    starts_with_subordinate = False
    for starter in _SUBORDINATE_STARTERS:
        if lower.startswith(starter):
            starts_with_subordinate = True
            break

    if not starts_with_subordinate:
        return None

    # Find the first comma that separates the subordinate clause from the main clause.
    # Must be followed by a space (not inside a quoted phrase or parenthetical).
    # Skip commas inside quoted strings.
    in_quote = False
    paren_depth = 0
    for i, ch in enumerate(sentence):
        if ch == '"' or ch == '\u201c' or ch == '\u201d':
            in_quote = not in_quote
        elif ch == '(' and not in_quote:
            paren_depth += 1
        elif ch == ')' and not in_quote:
            paren_depth = max(0, paren_depth - 1)
        elif ch == ',' and not in_quote and paren_depth == 0:
            # Found the clause-separating comma
            rest = sentence[i + 1:].strip()
            if rest:
                return rest
            break

    return None


def _check_clause_for_imperative(clause: str) -> str:
    """Check if a clause (after a subordinate intro) starts with an imperative verb.

    Same logic as the sentence-initial check but adapted for mid-sentence position:
    - The clause is NOT capitalized (lowercase after comma+space)
    - No need for Gate D2/D3 (proper noun / quoted heuristics) since
      mid-sentence clauses don't start with capitalized words unless forced
    - Navigation exemption still applies (if the clause itself is navigational,
      it's exempt)

    Returns the matched verb if imperative detected, else None.
    """
    if not clause:
        return None

    # Navigation exemption at clause level
    if _is_style_navigation_sentence(clause):
        return None

    lower = clause.lower().strip()
    words = lower.split()
    if not words:
        return None

    # ── Check multi-word imperative phrases first ──
    for phrase in _R1_MULTI_WORD_VERBS:
        if re.match(rf'{re.escape(phrase)}\b', lower):
            return phrase

    # ── Single-word analysis ──
    first_word = words[0]

    # Strip leading punctuation
    first_word = re.sub(r'^["\'\u201c\u201d\u2018\u2019\u2014\u2013\u2014\u2013-]+', '', first_word)
    if not first_word:
        return None

    # Gate A: Known non-verb starters
    if first_word in _R1_NON_VERB_STARTERS:
        return None

    # Gate B: Non-base-form morphology (but allow known verb exceptions)
    if first_word not in _VERB_DESPITE_SUFFIX and _NON_BASE_SUFFIXES.search(first_word):
        return None

    # Gate C: Third-person -s
    if _looks_like_third_person_s(first_word):
        return None

    # Gate D: Likely noun subject — adapted for mid-sentence
    # In mid-sentence position, a noun subject is less likely (the subject
    # is usually in the subordinate clause), but still possible:
    # "As you arrive, visitors gather..." — but this is rare in our corpus.
    if _is_likely_noun_subject(clause):
        return None

    # Gate E: Navigation verbs — exempt ONLY with directional content
    if first_word in _NAV_VERBS_R1:
        rest_words = words[1:] if len(words) > 1 else []
        for w in rest_words[:3]:
            clean_w = re.sub(r'[^a-z]', '', w)
            if clean_w in _DIRECTIONAL_WORDS:
                return None  # Genuine navigation — exempt
        # NOT followed by directional content → this IS an imperative
        return first_word

    # Gate F: Very short words (1-2 chars) are unlikely imperatives
    if len(first_word) <= 2:
        return None

    return first_word


def check_r1_imperatives(sentence: str) -> List[Dict]:
    """R1: Detect imperatives aimed at the listener.

    LOCAL-196 INVERTED DESIGN: Detects ANY sentence-initial base-form verb
    with no subject, then subtracts exemptions. Imperatives are open-class;
    the exemption list is the closed, enumerable part.

    LOCAL-233 EXTENSION: Also detects mid-sentence imperatives after a leading
    subordinate clause. Pattern: "<As you X>, <imperative>". The pipeline's
    house style puts imperatives after subordinate clauses ("As you arrive at X,
    pause to take in..."), which the original R1 could not see.

    Fires when:
    - Sentence starts with a base-form verb (morphological heuristic)
    - OR: Sentence has a leading subordinate clause followed by a base-form verb
    - No explicit subject before the verb (imperative form)
    - Not a navigation sentence (route verb + directional content)

    Does NOT fire when:
    - Starts with a known non-verb (determiner, pronoun, preposition, etc.)
    - Word has non-base-form morphology (-ed, -ing, -tion, -ness, etc.)
    - Likely 3rd person (-s ending): "Visitors notice the asymmetry"
    - Navigation: "Head south", "Turn left at the fountain"
    - Starts with a plural/agent noun: "Explorers arrived in 1890"
    """
    findings = []
    stripped = sentence.strip()
    if not stripped:
        return findings

    # Navigation exemption at sentence level (existing check)
    if _is_navigation_sentence(stripped):
        # LOCAL-233: Even if the sentence as a whole is "navigation", check
        # whether it has a suggestive tail after the route-movement clause.
        # "Pedal along the coastline, envisioning the hidden coves..." — the
        # first clause is navigation, but the second is pure suggestion.
        # This is handled by _check_nav_sentence_tail below.
        findings.extend(_check_nav_sentence_suggestive_tail(stripped))
        return findings

    lower = stripped.lower()
    words = lower.split()
    if not words:
        return findings

    # ── Step 1: Check multi-word imperative phrases first ──
    matched_verb = None
    for phrase in _R1_MULTI_WORD_VERBS:
        if re.match(rf'{re.escape(phrase)}\b', lower):
            matched_verb = phrase
            break

    if not matched_verb:
        # ── Step 2: Single-word analysis ──
        first_word = words[0]

        # Strip leading punctuation (quotes, em-dash)
        first_word = re.sub(r'^["\'\u201c\u201d\u2018\u2019\u2014\u2013—–-]+', '', first_word)
        if not first_word:
            # Fall through to mid-sentence check
            pass
        else:
            # Gate A: Known non-verb starters
            if first_word in _R1_NON_VERB_STARTERS:
                # Not a sentence-initial imperative, but check for mid-sentence
                pass
            # Gate B: Non-base-form morphology (but allow known verb exceptions)
            elif first_word not in _VERB_DESPITE_SUFFIX and _NON_BASE_SUFFIXES.search(first_word):
                pass
            # Gate C: Third-person -s (but not -ss base forms like "pass", "cross")
            elif _looks_like_third_person_s(first_word):
                pass
            # Gate D: Likely noun subject (plural agent nouns, nominalizations)
            elif _is_likely_noun_subject(stripped):
                pass
            else:
                # Gate D2: Proper noun heuristic
                if len(words) > 1:
                    second_word = stripped.split()[1] if len(stripped.split()) > 1 else ''
                    # Possessive: "Klein's", "Niki's", "Saint Phalle's"
                    if second_word.endswith("'s") or second_word.endswith("\u2019s"):
                        pass
                    # Comma after first word: "Klein, a pioneer..." (appositive)
                    elif stripped.split()[0].endswith(','):
                        pass
                    # Second word is capitalized (proper noun continuation): "Saint Phalle"
                    elif len(second_word) > 1 and second_word[0].isupper() and not stripped.startswith('"'):
                        pass
                    # Foreign name particles
                    elif second_word.lower() in {'de', 'von', 'van', 'di', 'del', 'la', 'le', 'les',
                                                  'des', 'du', 'da', 'das', 'den', 'der', 'het', 'el'}:
                        pass
                    else:
                        # Gate D3: Quoted content at sentence start
                        if stripped.startswith('"') or stripped.startswith('\u201c') or stripped.startswith("'"):
                            pass
                        # Gate E: Navigation verbs — exempt ONLY with directional content
                        elif first_word in _NAV_VERBS_R1:
                            rest_words = words[1:] if len(words) > 1 else []
                            for w in rest_words[:3]:
                                clean_w = re.sub(r'[^a-z]', '', w)
                                if clean_w in _DIRECTIONAL_WORDS:
                                    break  # Genuine navigation — exempt
                            else:
                                # NOT followed by directional content → imperative
                                matched_verb = first_word
                        # Gate F: Very short words (1-2 chars)
                        elif len(first_word) <= 2:
                            pass
                        else:
                            matched_verb = first_word
                else:
                    # Single word sentence — Gate D3 and D2 don't apply
                    if stripped.startswith('"') or stripped.startswith('\u201c') or stripped.startswith("'"):
                        pass
                    elif first_word in _NAV_VERBS_R1:
                        pass  # Single nav verb with nothing after — not useful
                    elif len(first_word) <= 2:
                        pass
                    else:
                        matched_verb = first_word

    # ── Step 3 (LOCAL-233): Mid-sentence imperative detection ──
    # If no sentence-initial imperative was found, check for imperatives after
    # a leading subordinate clause: "As you arrive at X, pause to take in..."
    if not matched_verb:
        main_clause = _extract_clause_after_subordinate(stripped)
        if main_clause:
            mid_verb = _check_clause_for_imperative(main_clause)
            if mid_verb:
                matched_verb = mid_verb

    # Final confirmation: we have a matched verb
    if matched_verb:
        findings.append({
            'rule_id': 'R1_IMPERATIVE',
            'severity': 'error',
            'sentence': stripped,
            'suggestion': f'Rewrite as declarative statement. Remove the imperative "{matched_verb}" and state the fact directly.',
        })

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
    # LOCAL-247: Fabricated multi-sensory scene + abstract emotional result.
    # Pattern: "the [sensory] + [sensory verb] ... creates/evokes a [feeling] ambiance/atmosphere"
    # Michael's 1/5: "guessing what one would feel: very annoying to humans"
    # Fires when: sentence has a sensory carrier (breeze, scent, sound, waves)
    # AND attributes an abstract emotional quality (ambiance, serenity, atmosphere)
    # via a causation verb (creates, evokes, produces, offers, provides).
    # Does NOT fire on factual sensory ("The market smells of lavender") — no abstract result.
    r'\b(?:the\s+)?(?:salty|gentle|soft|warm|cool|sweet|fresh)\s+(?:breeze|wind|air|scent|aroma|fragrance)\s+(?:carries|brings|fills|wafts)\b.*\b(?:ambiance|ambience|atmosphere|serenity|tranquility|tranquillity|calm|peace)\b',
    # Sound + abstract emotional causation: "the sound of X creates a [feeling]"
    r'\bthe\s+sound\s+of\s+.*\b(?:creates?|produces?|evokes?|offers?|provides?|conjures?)\s+(?:a\s+)?(?:soothing|calming|serene|peaceful|tranquil|harmonious|magical|enchanting)\s+(?:ambiance|ambience|atmosphere|backdrop|setting|mood)\b',
    # LOCAL-251: "breathe in the [scent/aroma] of X" without absence marker —
    # When the inhaled sensory combines MULTIPLE invented details (sea + pastries,
    # lavender + baking) that the narrator cannot source, this is fabrication.
    # Pattern: "breathe in" + scent/aroma + "mingling/mixed/combined" (multi-source indicator)
    r'\bbreathe\s+in\s+.*\b(?:scent|smell|aroma|fragrance)\b.*\b(?:mingling|mixed|combined|blending|intertwined)\b',
    # LOCAL-251: "The sound of X" + "provide/offer" + "backdrop/soundtrack/accompaniment"
    # Fabricated ambient scene presented as stage-setting. The narrator
    # invents a soundscape for atmosphere. Does NOT fire on factual statements
    # about real audible things ("The sound of the fountain is audible from the square").
    r'\b(?:the\s+)?sound\s+of\s+\w+.*\b(?:provide|offer|create|lend|give|add)\w*\s+(?:a\s+)?(?:sensory|sonic|auditory|natural|perfect|soothing)?\s*(?:backdrop|soundtrack|accompaniment|setting|tapestry)\b',
    # LOCAL-251: "the gentle lapping of waves" + sensory descriptor
    # Fabricated seaside ambiance — cannot be sourced from documents.
    # Does NOT fire on "waves crash against the seawall" (bare factual observation).
    r'\b(?:gentle|soft|rhythmic)\s+(?:lapping|lapping|crashing|splashing)\s+of\s+(?:waves|water)\b.*\b(?:provide|create|offer|lend|add|give)\b',
    # LOCAL-256: "gentle/salty/fresh [WORD]* breeze/wind carries/brings the scent/smell"
    # The round 12 pattern "gentle sea breeze carries the scent" has an intervening
    # word between the sensory adjective and the carrier noun. Catches multi-sensory
    # fabrication where the narrator invents a scent + sound + breeze scene.
    # Requires BOTH a sensory carrier verb AND "mingling/sounds/waves" later in the
    # sentence to confirm it's an invented multi-sensory ambiance, not a bare
    # factual observation.
    r'\b(?:salty|gentle|soft|warm|cool|sweet|fresh)\s+\w*\s*(?:breeze|wind|air)\s+(?:carries|brings|fills|wafts)\s+(?:the\s+)?(?:scent|smell|fragrance|aroma)\b.*\b(?:mingling|sounds?\s+of|waves?\s+lapping|seagulls?)\b',
    # LOCAL-256: "the scent/smell/fragrance of X mingles/mixes/blends with the
    # fragrance/scent/aroma of Y" — dual-sensory fabrication without "breathe in".
    # The narrator invents TWO scent sources combined. Does NOT fire on a single
    # factual scent ("The scent of lavender fills the garden" — one source, factual).
    r'\b(?:the\s+)?(?:scent|smell|fragrance|aroma)\s+of\s+.+?\b(?:mingles?|mixes?|blends?|intertwines?|combines?)\s+with\s+(?:the\s+)?(?:scent|smell|fragrance|aroma)\b',
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
# R1 REWRITE LOGIC (assembly-time) — LOCAL-255
# ═══════════════════════════════════════════════════════════════════════════════
# Michael (Round 2, twice 2/5): "provides instructions; I thought we should have
# overcome that error by now." R1 fires at 36.2% of paragraphs corpus-wide.
#
# At this rate, DELETION would gut every tour. R1 needs a REWRITE path:
# - The instruction becomes a statement; the content survives intact.
# - Only pure instructions with no content ("Take a moment to absorb the
#   atmosphere.") are deleted.
#
# Michael's endorsed transformation (Round 2, "Fixes / Pair 1"):
#   BEFORE: "Position yourself at the entrance of Eze Village, a medieval gem..."
#   AFTER:  "Eze Village is a medieval gem..."
#   Verdict: "absolutely agree! After immeasurably better than before."
#
# Navigation is exempt (D107): "Start cycling south on the main road..." survives.
#
# Behind DISABLE_R1_REWRITE=1 env var — caller checks this.

# ── Deterministic rewrite rules ─────────────────────────────────────────────
# The common imperative shapes are few and regular. These handle the majority.
# An LLM pass is permitted for the residue (ceiling $0.60 per task), but it may
# only RESTATE the sentence — it must not add a fact. If a deterministic rule
# and the model disagree, prefer the deterministic one.

_R1_REWRITE_RULES = [
    # "Position yourself at X, a Y" → "X is a Y"
    # Handles "at the entrance of X", "at the edge of X", "at X" etc.
    (re.compile(
        r'^(?:Position yourself|Place yourself|Station yourself|Stand)\s+'
        r'(?:at|near|by|beside|before|in front of)\s+'
        r'(?:the\s+)?(?:(?:entrance|edge|top|foot|base|center|centre|heart|start|beginning|end)\s+(?:of|to)\s+)?'
        r'(?:the\s+)?(.+?),\s+(.+)$',
        re.IGNORECASE | re.DOTALL),
     lambda m: f"{m.group(1).strip().rstrip(',')} is {m.group(2).strip()}"
    ),

    # "As you arrive at X, take in / observe / admire the Y" → "From X, the Y..."
    # or "At X, the Y..." or "From this vantage point, you can admire the Y..."
    (re.compile(
        r'^As you (?:arrive|approach|reach|come)\s+'
        r'(?:at|to|near)?\s*(.+?),\s*'
        r'(?:take in|observe|admire|notice|see|behold|absorb|enjoy|appreciate|discover|find)\s+'
        r'(.+)$',
        re.IGNORECASE | re.DOTALL),
     lambda m: f"From {m.group(1).strip().rstrip(',')}, you can admire {m.group(2).strip()}"
    ),

    # "Take in / Admire / Observe the X [that VERB ...]" → supply a predicate
    # LOCAL-256: The old rule just produced "The X" which is a fragment.
    # Now: if the captured tail contains a relative clause ("that ..." / "which ..."),
    # hoist the relative verb to main-clause position. Otherwise supply "is visible".
    (re.compile(
        r'^(?:Take in|Admire|Observe|Appreciate|Enjoy|Behold|Absorb|Notice|See)\s+'
        r'(?:the\s+)?(.+)$',
        re.IGNORECASE | re.DOTALL),
     '_take_in_handler'  # LOCAL-256: delegate to handler that ensures a finite verb
    ),

    # "Look for the X" → supply a predicate to avoid fragments
    # LOCAL-256: "Look for the Fondation Maeght, founded in 1964..." → must remain a sentence.
    (re.compile(
        r'^(?:Look for|Look at|Look upon|Seek out|Search for|Find)\s+'
        r'(?:the\s+)?(.+)$',
        re.IGNORECASE | re.DOTALL),
     '_look_for_handler'  # LOCAL-256: delegate to handler that ensures a finite verb
    ),

    # "Take a moment to X" → delete if X is pure feeling; rewrite otherwise
    # Pure feeling: "absorb the atmosphere", "enjoy the view", "reflect"
    (re.compile(
        r'^Take a moment to\s+(.+)$',
        re.IGNORECASE | re.DOTALL),
     '_take_a_moment_handler'  # Special handler below
    ),

    # "Let yourself X" / "Allow yourself to X" → remove or rewrite
    (re.compile(
        r'^(?:Let yourself|Allow yourself to|Let the)\s+(.+)$',
        re.IGNORECASE | re.DOTALL),
     '_let_yourself_handler'
    ),

    # "Prepare to X" / "Get ready to X" → remove (pure instruction)
    (re.compile(
        r'^(?:Prepare to|Prepare yourself|Get ready to)\s+(.+)$',
        re.IGNORECASE | re.DOTALL),
     None  # Always delete
    ),

    # "Find your way to X" / "Make your way to X" → navigation-like but not
    # truly navigational unless followed by directional content
    (re.compile(
        r'^(?:Find your way|Make your way)\s+(?:to|towards|toward)\s+(.+)$',
        re.IGNORECASE | re.DOTALL),
     lambda m: f"{m.group(1).strip()}" if ',' in m.group(1) else None
    ),

    # Mid-sentence: "As you X, pause/take in/notice/observe/admire Y"
    # → "From this vantage point, Y"
    (re.compile(
        r'^(?:As you|While you|When you)\s+.+?,\s*'
        r'(?:pause to |stop to )?'
        r'(?:take in|observe|admire|notice|absorb|appreciate|enjoy|discover|look at|look for)\s+'
        r'(.+)$',
        re.IGNORECASE | re.DOTALL),
     lambda m: f"From this vantage point, you can admire {m.group(1).strip()}"
    ),

    # "Imagine X" → "X ..." (just state it)
    (re.compile(
        r'^(?:Imagine|Picture|Envision|Visualize|Visualise)\s+(.+)$',
        re.IGNORECASE | re.DOTALL),
     lambda m: m.group(1).strip() if len(m.group(1).strip()) > 20 else None
    ),

    # "Consider X" → "X ..." (just state it) — only if it has content
    (re.compile(
        r'^Consider\s+(?:the\s+)?(.+)$',
        re.IGNORECASE | re.DOTALL),
     lambda m: f"The {m.group(1).strip()}" if len(m.group(1).strip()) > 20
     else None
    ),

    # "Immerse yourself in X" → "X surrounds you" / just state X
    (re.compile(
        r'^(?:Immerse yourself|Lose yourself|Plunge yourself)\s+'
        r'(?:in|into)\s+(.+)$',
        re.IGNORECASE | re.DOTALL),
     lambda m: m.group(1).strip() if len(m.group(1).strip()) > 20 else None
    ),

    # "Listen to/for X" → "The sound of X..." / "X can be heard"
    (re.compile(
        r'^Listen\s+(?:to|for)\s+(?:the\s+)?(.+)$',
        re.IGNORECASE | re.DOTALL),
     lambda m: f"The sound of {m.group(1).strip()}" if 'sound' not in m.group(1).lower()
     else f"The {m.group(1).strip()}"
    ),

    # "Keep in mind X" / "Bear in mind X" → "X ..."
    (re.compile(
        r'^(?:Keep in mind|Bear in mind|Remember)\s+(?:that\s+)?(.+)$',
        re.IGNORECASE | re.DOTALL),
     lambda m: m.group(1).strip()
    ),
]

# ── Pure-instruction patterns (deletion, not rewrite) ────────────────────────
# These sentences contain NO factual content. They only instruct or prescribe.
_R1_PURE_INSTRUCTION_PATTERNS = [
    re.compile(r'^Take a moment to (?:absorb|soak in|enjoy|savor|savour|relish|appreciate|reflect on|breathe in|feel|embrace)\s+(?:the )?(?:atmosphere|ambiance|ambience|view|scenery|beauty|moment|surroundings|experience|serenity|tranquility|magic|charm|energy|vibe|spirit)\s*\.?$', re.IGNORECASE),
    re.compile(r'^(?:Enjoy|Savor|Savour|Relish|Embrace|Absorb|Soak in)\s+(?:the )?(?:view|scenery|atmosphere|moment|beauty|experience|surroundings|sights?|sounds?)\s*\.?$', re.IGNORECASE),
    re.compile(r'^(?:Pause|Stop|Wait)\s+(?:here\s+)?(?:to\s+)?(?:for a moment|and\s+)?(?:absorb|enjoy|take in|appreciate|soak in|reflect)\s*\.?$', re.IGNORECASE),
    re.compile(r'^(?:Take|Spare|Give yourself) a (?:moment|minute|second|breath)\s*\.?$', re.IGNORECASE),
    re.compile(r'^(?:Breathe|Inhale|Exhale)\s+(?:in|out|deeply)\s*\.?$', re.IGNORECASE),
    re.compile(r'^(?:Let|Allow)\s+(?:yourself|the\s+(?:atmosphere|moment|view|scenery))\s+(?:sink in|wash over you|envelop you|surround you)\s*\.?$', re.IGNORECASE),
]

# ── Feeling/experience terms that signal a "take a moment" is contentless ────
_FEELING_TERMS = re.compile(
    r'\b(?:absorb|soak\s+in|enjoy|savor|savour|relish|appreciate|embrace|'
    r'reflect\s+on|breathe\s+in|feel|experience|immerse|lose\s+yourself)\b'
    r'.*\b(?:atmosphere|ambiance|ambience|view|scenery|beauty|moment|'
    r'surroundings|serenity|tranquility|magic|charm|energy|spirit|vibe)\b',
    re.IGNORECASE
)


def _take_in_handler(m):
    """Handle 'Take in / Admire / Observe the X' — LOCAL-256 fragment fix.

    The old rule just produced "The X" which is a bare noun phrase (fragment).
    Now: detect whether the captured tail already contains a finite verb
    (via relative clause "that stretches" or "which stands"). If so, promote
    it to the main verb. Otherwise supply "stretches out before you" or
    "is visible before you" depending on context.
    """
    tail = m.group(1).strip()
    if not tail:
        return None

    # Case 1: tail contains "that VERB" relative clause → hoist verb to main
    # "panoramic view that stretches out before you, with ..."
    # → "The panoramic view stretches out before you, with ..."
    rel_match = re.match(
        r'^(.+?)\s+that\s+((?:stretch|extend|spread|open|unfold|sweep|reach|rise|tower|stand|lie|sit|overlook|face)\w*\s+.+)$',
        tail, re.IGNORECASE | re.DOTALL
    )
    if rel_match:
        subject = rel_match.group(1).strip().rstrip(',')
        predicate = rel_match.group(2).strip()
        # Ensure subject has "The" prefix — don't capitalize internal words
        if not re.match(r'^(?:the|a|an|this|that)\b', subject, re.IGNORECASE):
            subject = f"The {subject}"
        elif subject[0].islower():
            subject = subject[0].upper() + subject[1:]
        return f"{subject} {predicate}"

    # Case 2: tail contains "which VERB" → same treatment
    rel_match2 = re.match(
        r'^(.+?),?\s+which\s+((?:stretch|extend|spread|open|unfold|sweep|reach|rise|tower|stand|lie|sit|overlook|face)\w*\s+.+)$',
        tail, re.IGNORECASE | re.DOTALL
    )
    if rel_match2:
        subject = rel_match2.group(1).strip().rstrip(',')
        predicate = rel_match2.group(2).strip()
        if subject and subject[0].islower():
            subject = subject[0].upper() + subject[1:]
        if not re.match(r'^(?:the|a|an|this|that)\b', subject, re.IGNORECASE):
            subject = f"The {subject}"
        return f"{subject} {predicate}"

    # Case 3: no relative clause — supply a predicate
    # "the breathtaking views of the azure waters" → "The breathtaking views of the azure waters stretch out before you."
    if tail and tail[0].islower():
        tail = tail[0].upper() + tail[1:]
    if not re.match(r'^(?:The|A|An|This|That)\b', tail):
        tail = f"The {tail}"
    # Rstrip period so we can add our predicate
    tail_clean = tail.rstrip('.')
    return f"{tail_clean} stretches out before you."


def _look_for_handler(m):
    """Handle 'Look for / Search for the X' — LOCAL-256 fragment fix.

    The old rule just produced "The X" which has no verb. Now: detect whether
    the tail contains a participle that can be hoisted ("X, founded in Y")
    or supply a copula ("X was founded in Y" / "X stands here").
    """
    tail = m.group(1).strip()
    if not tail:
        return None

    # Case 1: "X, PARTICIPLE ..." (past participle as reduced relative)
    # "Fondation Maeght, founded in 1964 by Marguerite and Aimé Maeght."
    # → "The Fondation Maeght was founded in 1964 by Marguerite and Aimé Maeght."
    participle_match = re.match(
        r'^(.+?),\s+(founded|built|created|established|constructed|designed|'
        r'opened|completed|erected|dedicated|commissioned|painted|sculpted|'
        r'carved|written|composed|named|known|located|situated|dating|placed)\b(.*)$',
        tail, re.IGNORECASE | re.DOTALL
    )
    if participle_match:
        subject = participle_match.group(1).strip()
        participle = participle_match.group(2)
        rest = participle_match.group(3).strip()
        # Ensure "The" prefix
        if not re.match(r'^(?:the|a|an)\b', subject, re.IGNORECASE):
            subject = f"The {subject}"
        # Choose auxiliary: "dating" gets "is", others get "was"
        aux = "is" if participle.lower() in ('dating', 'known', 'located', 'situated') else "was"
        result = f"{subject} {aux} {participle}{' ' + rest if rest else ''}"
        # Ensure ends with period
        if not result.rstrip().endswith('.'):
            result = result.rstrip() + '.'
        return result

    # Case 2: tail has no participle — supply "stands here" / "can be found here"
    if tail and tail[0].islower():
        tail = tail[0].upper() + tail[1:]
    if not re.match(r'^(?:The|A|An)\b', tail):
        tail = f"The {tail}"
    tail_clean = tail.rstrip('.')
    return f"{tail_clean} can be found here."


def _take_a_moment_handler(m):
    """Handle 'Take a moment to X' — delete if pure feeling, rewrite otherwise."""
    rest = m.group(1).strip()
    # If the rest is purely about feeling/absorbing with no factual content, delete
    if _FEELING_TERMS.search(rest):
        return None  # Signal deletion
    # Otherwise, the sentence has some content — rewrite as statement
    # "Take a moment to admire the Fondation Maeght, founded in 1964..."
    # → "The Fondation Maeght was founded in 1964..."
    # Strip the imperative prefix verb
    content_match = re.match(
        r'(?:admire|observe|notice|examine|study|inspect|appreciate|explore|discover|look at)\s+(.+)',
        rest, re.IGNORECASE | re.DOTALL
    )
    if content_match:
        extracted = content_match.group(1).strip()
        # LOCAL-256: Check for participle pattern (same as _look_for_handler)
        # "the Fondation Maeght, founded in 1964 by ..." → supply copula
        participle_match = re.match(
            r'^(?:the\s+)?(.+?),\s+(founded|built|created|established|constructed|designed|'
            r'opened|completed|erected|dedicated|commissioned|painted|sculpted|'
            r'carved|written|composed|named|known|located|situated|dating|placed)\b(.*)$',
            extracted, re.IGNORECASE | re.DOTALL
        )
        if participle_match:
            subject = participle_match.group(1).strip()
            participle = participle_match.group(2)
            p_rest = participle_match.group(3).strip()
            if not re.match(r'^(?:the|a|an)\b', subject, re.IGNORECASE):
                subject = f"The {subject}"
            aux = "is" if participle.lower() in ('dating', 'known', 'located', 'situated') else "was"
            result = f"{subject} {aux} {participle}{' ' + p_rest if p_rest else ''}"
            if not result.rstrip().endswith('.'):
                result = result.rstrip() + '.'
            return result
        # No participle — add "The" prefix if needed
        if extracted and extracted[0].islower():
            # Add "The" if it doesn't already start with a determiner
            if not re.match(r'^(?:the|a|an|this|that|these|those)\b', extracted, re.IGNORECASE):
                return f"The {extracted}"
        return extracted
    # Fallback: just state it directly
    return rest


def _let_yourself_handler(m):
    """Handle 'Let yourself X' — delete if pure feeling."""
    rest = m.group(1).strip()
    if _FEELING_TERMS.search(rest):
        return None
    # "Let yourself be transported by the story of X" → "The story of X..."
    content_match = re.match(
        r'(?:be\s+(?:transported|carried|moved|inspired|guided)\s+by\s+)(.+)',
        rest, re.IGNORECASE | re.DOTALL
    )
    if content_match:
        return content_match.group(1).strip()
    return None  # Can't rewrite safely — delete


def _is_pure_instruction(sentence: str) -> bool:
    """Check if a sentence is a pure instruction with no factual content."""
    stripped = sentence.strip().rstrip('.')
    for pattern in _R1_PURE_INSTRUCTION_PATTERNS:
        if pattern.match(stripped):
            return True
    # Additional heuristic: very short imperative with no proper nouns, dates, or numbers
    if len(stripped.split()) <= 8:
        has_content = bool(re.search(r'\d{3,4}|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', stripped))
        if not has_content and not re.search(r'(?:founded|built|created|established|opened|dating|century)', stripped, re.IGNORECASE):
            return True
    return False


# ── LOCAL-256/257: Finite-verb checker ────────────────────────────────────────
# A sentence without a finite main verb is a fragment. Every R1 rewrite must
# pass this check; if it fails, the original sentence is kept (an imperative
# is better than a fragment).
#
# Heuristic: A sentence has a finite verb if it contains a word that is
# (a) a common English finite form (is, was, are, were, has, had, stands, etc.)
# OR (b) a verb-like word (ends -s, -ed, -es) that is NOT inside a relative
# clause modifier ("that stretches") — wait, relative clause verbs ARE finite,
# but they don't make the main clause complete. The key insight:
#
# "The X that stretches before you" → "stretches" is finite but it's in the
# relative clause, not the main clause. The main clause is "The X" — no verb.
#
# Strategy: strip relative clauses (that/which + ...) and participial phrases
# (, founded in ..., , perched high ...) then check if ANYTHING remains that
# looks like a finite verb.
#
# LOCAL-257: MASK QUOTED SPANS before any verb search. A verb inside a book
# title, artwork name, or other quoted text is part of a noun phrase, not the
# sentence's predicate. E.g. "Tender is the Night" — "is" here does not make
# the sentence containing it a complete clause.

# Regex to match quoted spans: "…", '…', «…», *…* (emphasis/italic markers)
_QUOTED_SPAN = re.compile(
    '\u201c[^\u201d]*\u201d'    # "curly" double quotes (U+201C…U+201D)
    '|"[^"]*"'                   # straight double quotes
    '|\u2018[^\u2019]*\u2019'    # 'curly' single quotes (U+2018…U+2019)
    r"|(?<!\w)'[^']*'(?!\w)"     # straight single quotes (not contractions)
    '|\xab[^\xbb]*\xbb'         # «guillemets» (U+00AB…U+00BB)
    r'|\*[^*]+\*'               # *emphasis*
    r'|_[^_]+_'                  # _italic_
    , re.UNICODE
)

_FINITE_VERB_FORMS = re.compile(
    r'\b(?:is|are|was|were|has|have|had|does|do|did|can|could|will|would|'
    r'shall|should|may|might|must|stands|stretches|extends|spreads|opens|'
    r'unfolds|sweeps|reaches|rises|towers|lies|sits|overlooks|faces|'
    r'remains|holds|carries|contains|features|offers|provides|marks|'
    r'dates|runs|winds|leads|connects|separates|dominates|reveals|'
    r'houses|displays|showcases|preserves|reflects|represents|serves|'
    r'forms|includes|combines|embodies|captures|draws|creates|transforms|'
    r'attracts|hosts|produces|joins|crowns|graces|defines|illustrates|'
    # LOCAL-257: additional verbs found in generation output
    r'held|drew|found|built|wrote|lived|came|became|began|grew|went|'
    r'took|made|saw|gave|knew|fell|brought|kept|left|stood|'
    r'lay|sat|ran|won|met|paid|told|sent|led|'
    r'shimmers?|glimmers?|gleams?|glows?|sparkles?|'
    r'beckons?|buzzes?|echoes?|whispers?|resonates?|'
    r'flourished|thrived|emerged|evolved|survived|endured|'
    r'witnessed|experienced|underwent|bore|borne)\b',
    re.IGNORECASE
)

# Patterns for subordinate/relative clauses and participial phrases
_RELATIVE_CLAUSE = re.compile(r'\bthat\s+\w+|\bwhich\s+\w+', re.IGNORECASE)
_PARTICIPIAL_PHRASE = re.compile(
    r',\s*(?:founded|built|created|established|constructed|designed|opened|'
    r'completed|erected|dedicated|commissioned|painted|sculpted|carved|'
    r'written|composed|named|known|located|situated|dating|placed|'
    r'perched|nestled|surrounded|overlooking|facing|rising|towering|'
    r'stretching|extending|winding)\b[^,]*', re.IGNORECASE
)


def _has_finite_main_verb(sentence: str) -> bool:
    """Check if a sentence has a finite verb in the main clause.

    LOCAL-256: Used to reject rewrites that produce fragments.
    LOCAL-257: Masks quoted spans before checking. A verb inside a title
    (e.g. "Tender is the Night") does not make the sentence complete.

    Returns True if the sentence appears to have a complete main clause.

    Design: conservative — returns True (allow) in ambiguous cases. The
    purpose is to catch the SPECIFIC fragment patterns our R1 rewrite rules
    can produce:
      "The X, founded in Y." (noun + participial — no main verb)
      "The X that stretches..." (noun + relative clause — no main verb)
    Anything that doesn't match these fragment shapes passes.
    """
    stripped = sentence.strip().rstrip('.')
    if not stripped:
        return False

    # LOCAL-257: Strip field-label prefixes that precede actual content
    # "Orientation: Start cycling..." → check "Start cycling..."
    _label_match = re.match(r'^(?:Orientation|Directions|Description|Address|Type/Specialty|Specific Examples|Coordinates|Tour-Category):\s*', stripped)
    if _label_match:
        stripped = stripped[_label_match.end():]
        if not stripped:
            return False

    # LOCAL-257: Imperative sentences ARE grammatically complete — the verb
    # is finite in imperative mood. "Start cycling south..." is a sentence.
    # Check before masking quotes since the imperative verb is at the start.
    _first_word = stripped.split()[0].lower() if stripped.split() else ''
    if _first_word in ('start', 'head', 'turn', 'follow', 'continue', 'cross',
                       'walk', 'cycle', 'ride', 'pedal', 'take', 'go', 'proceed',
                       'look', 'find', 'explore', 'discover', 'enter', 'exit',
                       'pass', 'climb', 'descend', 'stop', 'notice', 'observe',
                       'admire', 'enjoy', 'imagine', 'picture', 'consider',
                       'remember', 'note', 'keep', 'bear', 'let', 'make',
                       'prepare', 'position', 'place', 'stand', 'listen',
                       'park', 'hey', 'once'):
        return True

    # LOCAL-257: "Once/When/As you [verb]..." has a finite verb in the subordinate
    if re.match(r'^(?:Once|When|As|After|Before)\s+you\s+\w+', stripped, re.IGNORECASE):
        return True

    # LOCAL-257: Mask quoted spans — verbs inside titles/quotes are not predicates
    stripped = _QUOTED_SPAN.sub(' QUOTED ', stripped)

    # Strip relative clauses and participial phrases to isolate main clause
    main_clause = _RELATIVE_CLAUSE.sub('', stripped)
    main_clause = _PARTICIPIAL_PHRASE.sub('', main_clause)
    main_clause = main_clause.strip().rstrip(',').strip()

    # If after stripping, nothing substantial remains (just a noun phrase),
    # it's a fragment. "The Fondation Maeght" after stripping ", founded in..."
    # But "The Fondation Maeght was founded in 1964" → "The Fondation Maeght was founded in 1964" (not stripped)

    # Check for finite verb forms in what remains
    if _FINITE_VERB_FORMS.search(main_clause):
        return True

    # "you can" pattern (modal + infinitive)
    if re.search(r'\byou\s+can\b', main_clause, re.IGNORECASE):
        return True

    # "From X, ..." patterns with a verb after the comma
    from_match = re.match(r'^From\s+.+?,\s*(.+)$', main_clause, re.IGNORECASE)
    if from_match:
        rest = from_match.group(1)
        if _FINITE_VERB_FORMS.search(rest) or re.search(r'\byou\s+can\b', rest, re.IGNORECASE):
            return True

    # Heuristic: any word ending in -ed/-es/-s after an article/determiner
    # Catches "the village buzzed", "the foundation embodies", "beckons with"
    if re.search(r'\b[a-z]+(?:ed|es|ons|ens)\b', main_clause):
        return True

    # Check for verbs ending in -s (3rd person present): "beckons", "holds"
    # But exclude words that are commonly nouns ending in -s: "views", "streets", "walls"
    # LOCAL-257: Also exclude possessives and adjectives ending in -ous/-ious/-us
    _COMMON_NOUN_S = {'views', 'streets', 'walls', 'trees', 'arts', 'works',
                      'examples', 'gardens', 'galleries', 'paths', 'stones',
                      'waters', 'waves', 'sounds', 'scents', 'facts', 'years',
                      'words', 'names', 'steps', 'stops', 'tours', 'times',
                      'heights', 'lights', 'nights', 'sights', 'rights',
                      'twenties', 'forties', 'sixties', 'things', 'buildings',
                      'paintings', 'carvings', 'surroundings', 'proceedings',
                      'artists', 'inhabitants', 'visitors', 'residents',
                      'mountains', 'islands', 'ruins', 'remains', 'hills',
                      'cliffs', 'fields', 'banks', 'shores', 'woods', 'plains',
                      'this', 'thus', 'plus', 'minus', 'versus', 'atlas'}
    # Adjectives/adverbs ending in -s that are NOT verbs
    _ADJ_S_SUFFIXES = ('ous', 'ious', 'eous', 'uous', 'ous', 'less', 'ness')
    words = main_clause.split()
    for w in words:
        wl = w.lower().rstrip('.,;:!?')
        # LOCAL-257: Skip possessives — "Fitzgerald's" is not a verb
        if "'s" in wl or "\u2019s" in wl:
            continue
        # Skip adjectives ending in -ous, -less, etc.
        if any(wl.endswith(suf) for suf in _ADJ_S_SUFFIXES):
            continue
        if wl.endswith('s') and len(wl) > 3 and wl not in _COMMON_NOUN_S:
            # Check if preceded by a noun phrase (likely verb position)
            idx = main_clause.lower().find(wl)
            if idx > 0:
                before = main_clause[:idx].strip()
                # If what's before looks like a subject (ends with a capitalized word or pronoun)
                if before and (before[-1] not in '.,;:' and
                    (re.search(r'[A-Z][a-z]+$', before) or
                     re.search(r'\b(?:it|he|she|they|we|one|this|that|which)\s*$', before, re.IGNORECASE))):
                    return True

    # "In YEAR/decade" pattern — virtually always has a verb
    if re.search(r'^In\s+(?:the\s+)?\d{3,4}s?\b', main_clause):
        return True

    # If the main clause is very short (< 5 words) after stripping, likely a fragment
    words_remaining = [w for w in main_clause.split() if len(w) > 2]
    if len(words_remaining) <= 4:
        return False

    # LOCAL-257: Instead of blindly passing long sentences, check for verb
    # indicators more broadly. A long noun-phrase fragment like
    # "Scott Fitzgerald's QUOTED a vivid portrayal of the Roaring Twenties..."
    # has 15 words but no verb.
    #
    # Broader verb check: any past tense (-ed), 3rd-person present that looks
    # like a verb in context (preceded by a noun/pronoun), or common verb
    # patterns we may have missed above.
    if re.search(r'\b(?:became|began|came|gave|grew|knew|made|saw|went|took|'
                 r'found|built|wrote|lived|died|born|moved|worked|arrived|'
                 r'created|painted|composed|inspired|captured|attracted|'
                 r'transformed|developed|produced|hosted|gathered|brought|'
                 r'flourished|thrived|emerged|evolved|survived|endured|'
                 r'welcomed|celebrated|exhibited|inaugurated|embarked|'
                 r'experimented|discovered|explored|settled|constructed|'
                 r'restored|renovated|demolished|expanded|connected|'
                 r'commissioned|dedicated|renamed|merged|split|formed|'
                 r'introduced|launched|published|recorded|documented|'
                 r'established|erected|sculpted|adorned|permeates|emanates|'
                 r'beckons|buzzes|buzzed|echoes|breathes|pulses|pulsed|'
                 r'whispers|resonates|embodies)\b', main_clause, re.IGNORECASE):
        return True

    # Check for any word that looks like a past-tense verb (ending in -ed)
    # but NOT after a comma (which would be participial)
    if re.search(r'(?:^|(?<![,]))\s+\w+ed\b', main_clause):
        # Extra check: the -ed word should not be an adjective before a noun
        ed_matches = re.finditer(r'\b(\w+ed)\b', main_clause)
        for em in ed_matches:
            word = em.group(1).lower()
            # Skip known adjectives that end in -ed
            if word in ('renowned', 'famed', 'named', 'storied', 'sacred',
                        'detailed', 'cobbled', 'walled', 'gilded', 'vaulted',
                        'arched', 'terraced', 'landscaped', 'elevated',
                        'illustrated', 'animated', 'documented', 'rugged'):
                continue
            # If followed by a preposition or end-of-clause, likely a verb
            after_pos = em.end()
            after_text = main_clause[after_pos:after_pos+10].strip()
            if not after_text or after_text[0] in '.,;:!?' or \
               re.match(r'^(?:in|on|at|by|to|for|with|from|of|the|a|an|and|but|or|that|this|it|he|she|they)\b', after_text, re.IGNORECASE):
                return True

    # If main clause has > 12 meaningful words AND contains what looks like
    # a subject-verb pattern (capitalized word followed by lowercase word
    # that could be a verb), cautiously allow
    if len(words_remaining) > 12:
        # Look for patterns like "Name verb" or "The Noun verbs"
        if re.search(r'(?:[A-Z][a-z]+|the\s+\w+)\s+(?:is|are|was|were|has|have|had|'
                     r'does|did|will|would|can|could|shall|should|may|might|must)\b',
                     main_clause, re.IGNORECASE):
            return True

    return False


# ── LOCAL-257: Determiner restoration ────────────────────────────────────────
# When stripping an imperative ("Explore the charming village of X…"), the LLM
# or a deterministic rule may drop the article along with the verb, producing
# "Charming village of X is…" instead of "The charming village of X is…".
# This function detects the pattern and restores "The".

# Common adjectives that frequently precede nouns in tour text
_BARE_ADJ_START = re.compile(
    r'^(?:charming|quaint|bustling|ancient|historic|medieval|majestic|opulent|'
    r'picturesque|stunning|beautiful|magnificent|narrow|famous|renowned|'
    r'legendary|hidden|tranquil|serene|vibrant|colourful|colorful|elegant|'
    r'grand|imposing|impressive|scenic|idyllic|enchanting|lovely|striking|'
    r'dramatic|remarkable|spectacular|breathtaking|winding|cobbled|steep|'
    r'rugged|lush|verdant|azure|golden|crimson|pristine|sleepy|tiny|vast|'
    r'enormous|sprawling|compact|towering|crumbling|weathered|ornate|'
    r'delicate|exquisite|intricate)\s+'
    r'(?:village|town|city|street|streets|road|path|trail|castle|church|'
    r'chapel|cathedral|abbey|monastery|palace|fortress|tower|bridge|'
    r'garden|gardens|park|square|plaza|courtyard|harbour|harbor|port|'
    r'beach|bay|coast|coastline|cliff|cliffs|cape|peninsula|island|'
    r'hill|hills|mountain|mountains|valley|river|lake|fountain|statue|'
    r'museum|gallery|market|quarter|district|promenade|boulevard|avenue|'
    r'building|mansion|villa|hotel|restaurant|café|cafe|terrace|'
    r'landscape|panorama|view|vista|area|region|neighborhood|neighbourhood)\b',
    re.IGNORECASE
)

# Bare common nouns without preceding determiner (no article, no possessive)
_BARE_NOUN_START = re.compile(
    r'^(?:village|town|city|castle|church|chapel|cathedral|abbey|monastery|'
    r'palace|fortress|tower|bridge|garden|gardens|park|square|plaza|'
    r'courtyard|harbour|harbor|port|museum|gallery|market|quarter|'
    r'district|promenade|boulevard|avenue|building|mansion|villa|hotel|'
    r'restaurant|café|cafe|terrace|landscape|panorama|area|region|'
    r'neighbourhood|neighborhood)\s+(?:of|at|in|on|near|by|along|beside)\b',
    re.IGNORECASE
)


def _restore_determiner(sentence: str) -> str:
    """LOCAL-257: Restore 'The' when a rewrite stripped it with the imperative.

    "Charming village of X is…" → "The charming village of X is…"
    Only triggers when the sentence starts with an adjective+noun or bare
    common noun followed by a preposition — patterns that require an article
    in English.
    """
    stripped = sentence.strip()
    if not stripped:
        return stripped

    # Don't add "The" if already starts with a determiner or proper noun
    first_word = stripped.split()[0] if stripped.split() else ''
    if first_word.lower() in ('the', 'a', 'an', 'this', 'that', 'these', 'those',
                               'my', 'your', 'his', 'her', 'its', 'our', 'their'):
        return stripped

    # Check if first word is capitalized and might be a proper noun
    # (proper nouns don't need articles). But adjectives at sentence start
    # are also capitalized, so we check the pattern.
    if _BARE_ADJ_START.match(stripped) or _BARE_NOUN_START.match(stripped):
        # Restore "The" with proper capitalization
        return 'The ' + stripped[0].lower() + stripped[1:]

    return stripped


def rewrite_r1_sentence_deterministic(sentence: str) -> str:
    """Attempt deterministic rewrite of an R1-flagged sentence.

    Returns:
        - The rewritten sentence (if a deterministic rule matched)
        - None if the sentence should be DELETED (pure instruction, no content)
        - The sentinel string '__LLM_NEEDED__' if no deterministic rule matched
          and an LLM pass is needed for this residue.
    """
    stripped = sentence.strip()

    # Step 1: Is this a pure instruction? → Delete
    if _is_pure_instruction(stripped):
        return None

    # Step 2: Try deterministic rewrite rules in order
    for pattern, handler in _R1_REWRITE_RULES:
        m = pattern.match(stripped)
        if m:
            if handler is None:
                return None  # Rule says delete
            elif handler == '_take_a_moment_handler':
                result = _take_a_moment_handler(m)
                if result is None:
                    return None  # Delete
                return result
            elif handler == '_let_yourself_handler':
                result = _let_yourself_handler(m)
                if result is None:
                    return None
                return result
            elif handler == '_take_in_handler':
                result = _take_in_handler(m)
                if result is None:
                    return None
                return result
            elif handler == '_look_for_handler':
                result = _look_for_handler(m)
                if result is None:
                    return None
                return result
            elif callable(handler):
                result = handler(m)
                if result is None:
                    return None  # Handler says delete
                # Ensure it ends with a period if the original did
                result = result.strip()
                if stripped.endswith('.') and not result.endswith('.'):
                    result += '.'
                # Capitalize first letter
                if result and result[0].islower():
                    result = result[0].upper() + result[1:]
                return result

    # Step 3: No deterministic rule matched — signal LLM needed
    return '__LLM_NEEDED__'


def rewrite_r1_sentence_llm(sentence: str, api_key: str, model: str = None) -> str:
    """Rewrite an R1 sentence using an LLM call.

    The LLM may only RESTATE the sentence — it must not add a fact.
    Returns the rewritten sentence, or None if deletion is the outcome.
    """
    import requests as _req

    if not model:
        model = os.environ.get('TOUR_LLM_MODEL', 'gpt-4o-mini')

    prompt = f"""Rewrite this sentence to remove the imperative/instruction while preserving ALL factual content.

SENTENCE: "{sentence}"

RULES:
1. Convert the imperative (command to the listener) into a declarative statement.
2. DO NOT add any facts, dates, names, or information not in the original.
3. DO NOT delete any facts, dates, names, or quoted content from the original.
4. The rewritten sentence must contain every proper noun and every number from the original.
5. If the sentence is purely an instruction with no factual content (e.g., "Take a moment to absorb the atmosphere."), respond with exactly: DELETE
6. Return ONLY the rewritten sentence. No explanation, no quotes around it.

EXAMPLES:
- "Position yourself at the entrance of Eze Village, a medieval gem perched high above the French Riviera." → "Eze Village is a medieval gem perched high above the French Riviera."
- "Take in the stunning views of the azure Mediterranean Sea." → "The stunning views of the azure Mediterranean Sea stretch out from here."
- "Look for the Fondation Maeght, founded in 1964 by Marguerite and Aimé Maeght." → "The Fondation Maeght, founded in 1964 by Marguerite and Aimé Maeght, stands here."
- "As you arrive, take in the breathtaking views of the azure waters." → "From this vantage point, the breathtaking views of the azure waters are visible."
- "Take a moment to absorb the atmosphere." → DELETE
- "Enjoy the view." → DELETE
"""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a copy editor. You rewrite imperative sentences as declarative statements. You never add information."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 200,
    }

    try:
        resp = _req.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            data=json.dumps(data),
            timeout=30,
        )
        if resp.status_code == 200:
            result = resp.json()
            text = result["choices"][0]["message"]["content"].strip()
            tokens_used = result["usage"]["total_tokens"]

            # Check for DELETE signal
            if text.upper().strip() == 'DELETE':
                return None, tokens_used

            # Strip quotes if wrapped
            if text.startswith('"') and text.endswith('"'):
                text = text[1:-1].strip()
            if text.startswith('\u201c') and text.endswith('\u201d'):
                text = text[1:-1].strip()

            # Content preservation check: every proper noun and number in the
            # original must appear in the rewrite.
            orig_proper_nouns = set(re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', sentence))
            orig_numbers = set(re.findall(r'\b\d{3,4}\b', sentence))
            new_proper_nouns = set(re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text))
            new_numbers = set(re.findall(r'\b\d{3,4}\b', text))

            # If proper nouns or numbers were dropped, reject the LLM rewrite
            # and fall back to keeping the original (better imperative than lost content)
            lost_nouns = orig_proper_nouns - new_proper_nouns
            lost_numbers = orig_numbers - new_numbers
            # Filter out very common words that happen to be capitalized
            _common_caps = {'The', 'This', 'That', 'Here', 'From', 'You', 'As', 'In', 'At', 'On'}
            lost_nouns -= _common_caps

            if lost_nouns or lost_numbers:
                # Content loss — reject LLM rewrite, keep original
                return '__KEEP_ORIGINAL__', tokens_used

            return text, tokens_used
        else:
            return '__KEEP_ORIGINAL__', 0
    except Exception:
        return '__KEEP_ORIGINAL__', 0


def apply_r1_rewrites(paragraph: str, api_key: str = None, model: str = None) -> tuple:
    """Apply R1 rewrites to a paragraph.

    Rewrites imperative sentences to declarative form. Deletes only pure
    instructions with no factual content.

    Args:
        paragraph: The paragraph text
        api_key: OpenAI API key for LLM fallback (optional)
        model: LLM model name (optional, defaults to TOUR_LLM_MODEL or gpt-4o-mini)

    Returns:
        (new_paragraph, sentences_rewritten, sentences_deleted, llm_tokens_used)

    Behind DISABLE_R1_REWRITE=1 — caller must check.
    """
    if not paragraph or not paragraph.strip():
        return paragraph, 0, 0, 0

    sentences = _split_sentences(paragraph)
    if not sentences:
        return paragraph, 0, 0, 0

    kept = []
    rewritten_count = 0
    deleted_count = 0
    llm_tokens = 0

    for sentence in sentences:
        if len(sentence) < 10:
            kept.append(sentence)
            continue

        # Navigation sentences are never touched (D107)
        if _is_style_navigation_sentence(sentence):
            kept.append(sentence)
            continue

        # Check if this sentence fires R1
        findings = check_r1_imperatives(sentence)
        if not findings:
            kept.append(sentence)
            continue

        # This sentence is R1-flagged → attempt rewrite
        result = rewrite_r1_sentence_deterministic(sentence)

        if result is None:
            # Pure instruction → delete
            deleted_count += 1
            continue
        elif result == '__LLM_NEEDED__':
            # No deterministic rule matched → try LLM if key available
            if api_key:
                llm_result, tokens = rewrite_r1_sentence_llm(sentence, api_key, model)
                llm_tokens += tokens
                if llm_result is None:
                    # LLM says delete
                    deleted_count += 1
                    continue
                elif llm_result == '__KEEP_ORIGINAL__':
                    # LLM failed or dropped content → keep original
                    kept.append(sentence)
                    continue
                else:
                    # LLM rewrite accepted — LOCAL-256: verify finite verb
                    if not _has_finite_main_verb(llm_result):
                        # LLM produced a fragment — keep original
                        kept.append(sentence)
                        continue
                    # LOCAL-257: restore determiner if rewrite stripped it
                    llm_result = _restore_determiner(llm_result)
                    kept.append(llm_result)
                    rewritten_count += 1
                    continue
            else:
                # No API key — keep original (safe fallback)
                kept.append(sentence)
                continue
        else:
            # Deterministic rewrite succeeded — LOCAL-256: verify finite verb
            if not _has_finite_main_verb(result):
                # Rewrite produced a fragment — keep original (D156: an imperative
                # is better than a fragment)
                kept.append(sentence)
                continue
            # LOCAL-257: restore determiner if rewrite stripped it
            result = _restore_determiner(result)
            kept.append(result)
            rewritten_count += 1
            continue

    if not kept:
        return '', rewritten_count, deleted_count, llm_tokens

    # Reassemble
    result_text = ' '.join(kept)

    # Fix dangling connective on the new first sentence
    for pat in _DANGLING_CONNECTIVE_COMPILED:
        new_text = pat.sub('', result_text, count=1)
        if new_text != result_text:
            new_text = new_text.strip()
            if new_text and new_text[0].islower():
                new_text = new_text[0].upper() + new_text[1:]
            result_text = new_text
            break

    return result_text.strip(), rewritten_count, deleted_count, llm_tokens


def apply_r1_to_description(description: str, api_key: str = None, model: str = None) -> tuple:
    """Apply R1 rewrites to a full stop description (multiple paragraphs).

    Returns:
        (new_description, sentences_rewritten, sentences_deleted, llm_tokens_used)

    Behind DISABLE_R1_REWRITE=1 — caller must check.
    """
    if not description or not description.strip():
        return description, 0, 0, 0

    paragraphs = [p for p in description.split('\n\n') if p.strip()]
    if not paragraphs:
        return description, 0, 0, 0

    new_paragraphs = []
    total_rewritten = 0
    total_deleted = 0
    total_llm_tokens = 0

    for para in paragraphs:
        para = para.strip()
        if len(para) <= 30:
            new_paragraphs.append(para)
            continue

        result, rewritten, deleted, llm_tok = apply_r1_rewrites(para, api_key, model)
        total_rewritten += rewritten
        total_deleted += deleted
        total_llm_tokens += llm_tok

        if result:
            new_paragraphs.append(result)
        # else: entire paragraph was deleted (all sentences were pure instructions)

    new_description = '\n\n'.join(new_paragraphs)
    return new_description, total_rewritten, total_deleted, total_llm_tokens


# ═══════════════════════════════════════════════════════════════════════════════
# R7 DELETION LOGIC (assembly-time) — LOCAL-251
# ═══════════════════════════════════════════════════════════════════════════════
# Michael scored this class 1/5: "guessing what one would feel: very annoying
# to humans." R7 fires on fabricated sensory claims; until now it only reported.
#
# The distinction between legitimate and invented sensory:
#   LEGITIMATE: "the Mediterranean is visible below" — observable fact
#   INVENTED:   "breathe in the salty scent mingling with freshly baked pastries"
#               — the narrator cannot know this from any source
#
# R7's patterns already encode this distinction (absence markers, multi-sensory
# fabrication, fabricated soundscapes). The deletion path trusts the detection.
#
# Behind DISABLE_R7_DELETION=1 env var — caller checks this.

def apply_r7_deletions(paragraph: str) -> str:
    """Apply R7 deletions to a paragraph.

    - Removes sentences flagged by check_r7_hallucinated_sensory
    - Strips dangling connectives from the resulting first sentence
    - Returns empty string if all sentences are deleted

    Behind DISABLE_R7_DELETION=1 env var — caller checks this.
    """
    if not paragraph or not paragraph.strip():
        return paragraph

    sentences = _split_sentences(paragraph)
    if not sentences:
        return paragraph

    kept = []
    for sentence in sentences:
        if len(sentence) < 10:
            kept.append(sentence)
            continue
        # Navigation sentences are never deleted
        if _is_style_navigation_sentence(sentence):
            kept.append(sentence)
            continue
        findings = check_r7_hallucinated_sensory(sentence)
        if not findings:
            kept.append(sentence)
        # else: sentence is fabricated sensory — drop it

    if not kept:
        return ''  # All sentences deleted — caller removes the paragraph

    # Fix dangling connective on the new first sentence
    result_text = ' '.join(kept)
    for pat in _DANGLING_CONNECTIVE_COMPILED:
        new_text = pat.sub('', result_text, count=1)
        if new_text != result_text:
            new_text = new_text.strip()
            if new_text and new_text[0].islower():
                new_text = new_text[0].upper() + new_text[1:]
            result_text = new_text
            break

    return result_text.strip()


def apply_r7_to_description(description: str) -> Tuple[str, int, int]:
    """Apply R7 deletions to a full stop description (multiple paragraphs).

    Returns:
        (new_description, sentences_deleted, paragraphs_emptied)

    Behind DISABLE_R7_DELETION=1 — caller must check.
    """
    if not description or not description.strip():
        return description, 0, 0

    paragraphs = [p for p in description.split('\n\n') if p.strip()]
    if not paragraphs:
        return description, 0, 0

    new_paragraphs = []
    total_deleted = 0
    paragraphs_emptied = 0

    for para in paragraphs:
        para = para.strip()
        if len(para) <= 30:
            new_paragraphs.append(para)
            continue

        sentences_before = _split_sentences(para)
        result = apply_r7_deletions(para)

        if not result:
            paragraphs_emptied += 1
            total_deleted += len([s for s in sentences_before if len(s) >= 10])
        else:
            sentences_after = _split_sentences(result)
            deleted_count = (
                len([s for s in sentences_before if len(s) >= 10]) -
                len([s for s in sentences_after if len(s) >= 10])
            )
            total_deleted += max(0, deleted_count)
            new_paragraphs.append(result)

    new_description = '\n\n'.join(new_paragraphs)
    return new_description, total_deleted, paragraphs_emptied


# ─── R8: Prompt leakage (LOCAL-213) ──────────────────────────────────────────
# The model restates its own instructions as narration. The listener hears
# the recipe instead of the dish. Error severity — this is never acceptable.
#
# The leakage has a distinctive syntactic fingerprint:
#   "One concrete sensory detail that [verb] you..." — the prompt said
#   "include one concrete sensory detail"; the model turned the instruction
#   into a topic sentence.
#
# Other patterns: "What makes this stop notable is...", "A concrete sensory
# detail that envelops you in the atmosphere of X is...", meta-references to
# paragraphs, instructions, or tasks.
#
# MUST FIRE on (from real stored tours):
#   "One concrete sensory detail that envelops you in the atmosphere of
#    Cap d'Antibes is the sound of the waves crashing..."
#   "One concrete sensory detail that immerses you in the experience is
#    the rhythmic sound of fishmongers..."
#   "A concrete sensory detail that envelops you in the atmosphere of the
#    park is the sound of seagulls..."
#   "What makes this stop notable is its connection to Picasso..."
#   "What makes this stop notable is its strategic role during World War II..."
#
# MUST NOT FIRE on (legitimate narration):
#   "The sound of waves carries up the cliff face."
#   "The carving repays a closer look at one detail in particular."
#   "What makes the chapel unusual is its octagonal floor plan."
#   "One detail stands out: the iron bolt holes where chains once ran."
#   "A sensory world opens when you step inside — incense, cool stone, silence."
#
# Design: match the SYNTACTIC FRAME of "One/A [qualifier] sensory detail
# that [verb] you" or "What makes this stop [adjective] is" — these are
# the model filling in a template sentence, not writing free prose.

_R8_PATTERNS = [
    # "One concrete sensory detail that [verb] you" — the canonical leak
    r'\b(?:one|a)\s+(?:concrete\s+)?sensory\s+detail\s+that\s+\w+s?\s+(?:you|the\s+listener)',
    # "A concrete/vivid sensory detail that envelops/immerses/places you"
    r'\b(?:one|a)\s+(?:concrete|vivid|specific)?\s*sensory\s+detail\b',
    # "What makes this stop notable/interesting/unique is" — prompt scaffold
    r'\bwhat\s+makes\s+this\s+stop\s+(?:notable|interesting|unique|special|remarkable)\s+is\b',
    # "envelops you in the atmosphere of" — exact prompt residue
    r'\benvelops?\s+you\s+in\s+the\s+atmosphere\b',
    # "places the listener" — prompt meta-language
    r'\bplaces?\s+the\s+listener\b',
    # "in this paragraph" — narration doesn't have paragraphs
    r'\bin\s+this\s+paragraph\b',
    # "as instructed" — model acknowledging its instructions
    r'\bas\s+instructed\b',
    # "your task" — model exposing task framing
    r'\byour\s+task\b',
    # "this description will" — model narrating its own output
    r'\bthis\s+description\s+will\b',
    # "Paragraph N:" — numbered paragraph header leaked
    r'\bParagraph\s+\d+\s*:',
    # "anchors the listener in time" — opening style instruction
    r'\banchors?\s+the\s+listener\b',
    # "a sound, material, smell" — the exact prompt triple
    r'\ba\s+sound,?\s*(?:a\s+)?material,?\s*(?:a\s+)?smell\b',
    # LOCAL-247: "this stop aligns with the tour's theme" — model restating
    # its structural purpose instead of narrating content
    r'\bthis\s+stop\s+aligns\s+with\b',
    # "aligns with the tour's/overall theme" — same family
    r'\baligns?\s+with\s+the\s+(?:tour|overall|main)\b.*\btheme\b',
    # "the tour's theme of [gerund]" — model announcing purpose
    r"\bthe\s+tour's\s+theme\s+of\b",
]

_R8_COMPILED = [re.compile(p, re.IGNORECASE) for p in _R8_PATTERNS]

# Negative set: patterns that look similar but are legitimate narration.
# Used to suppress false positives.
_R8_FALSE_POSITIVE_GUARDS = [
    # "One detail [verb]" without "sensory" is fine: "One detail stands out"
    re.compile(r'\bone\s+detail\s+(?:stands|catches|draws|repays|rewards)', re.IGNORECASE),
    # "What makes the/this [noun other than 'stop']" is fine: "What makes the chapel unusual"
    re.compile(r'\bwhat\s+makes\s+(?:the|this)\s+(?!stop\b)\w+', re.IGNORECASE),
]


def check_r8_prompt_leakage(sentence: str) -> List[Dict]:
    """R8: Detect prompt scaffolding leaked into narration (LOCAL-213).

    Fires when the model restates its instructions as a topic sentence.
    The listener should never hear the recipe — only the dish.

    Severity: ERROR — prompt leakage is never acceptable in narration.

    Does NOT fire on:
    - "One detail stands out" (no "sensory" qualifier)
    - "What makes the chapel unusual" (not "this stop")
    - Normal use of "detail", "sound", "atmosphere" in free prose
    """
    findings = []
    stripped = sentence.strip()
    if not stripped:
        return findings

    # Check false-positive guards first
    for guard in _R8_FALSE_POSITIVE_GUARDS:
        if guard.search(stripped):
            return findings

    for pat in _R8_COMPILED:
        if pat.search(stripped):
            findings.append({
                'rule_id': 'R8_PROMPT_LEAKAGE',
                'severity': 'error',
                'sentence': stripped,
                'suggestion': 'This sentence restates the prompt\'s instructions as narration. Remove the scaffolding frame and state the sensory fact directly (e.g., "Waves crash against the rocks" not "One concrete sensory detail is the sound of waves...").',
            })
            break  # One R8 finding per sentence

    return findings


# ─── R9: Generic sentence detection (LOCAL-216, D89) ─────────────────────────
# A sentence is GENERIC when it carries nothing that ties it to THIS stop:
# no proper noun, no date, no number, no venue- or stop-specific referent —
# only stance, atmosphere, or transition filler.
#
# Michael's verdict: "Should be removed! As it can be placed in millions of
# stops: nothing related to this one." His action is DELETE, not score low.
#
# MUST FIRE on (0/5 in Michael's evaluation):
#   "As you continue your journey through this charming town, consider how
#    these hidden paths have shaped the stories of this place, leading you
#    to uncover more of its intriguing history."
#   "From Cap d'Antibes to Villefranche-sur-Mer — a collection that spans
#    more ground than these stops alone."
#
# MUST NOT FIRE on (scored 1-5 by Michael — these are rewritable or good):
#   Navigation (5/5): "Start biking southeast on the main road..."
#   Sourced facts (5/5): "The town's strategic location east of Nice and
#     southwest of Monaco has been pivotal in its history."
#   Content with specifics (3/5): "In January 1888, the renowned artist
#     Claude Monet visited..."
#   Style failures (1/5): "listen to the gentle lapping of waves" —
#     these are R1/R4 problems, NOT generic. They name specific things.
#
# DETECTION APPROACH:
# A sentence is generic if ALL of these are true:
#   1. No proper noun (capitalized word not at sentence start, or known places)
#   2. No date (year, month, century reference)
#   3. No number (measurement, distance, count)
#   4. No place-specific referent (named landmark, street, geographic feature)
#   5. Contains generic filler signals (journey, charming, hidden, stories,
#      collection, spans, uncover, intriguing, timeless)
#
# The key insight: absence of specifics + presence of filler = generic.
# NEITHER ALONE suffices. A short connective with no specifics but also no
# filler is just terse — not generic.
#
# SEVERITY: 'delete' — a new severity distinct from 'error' and 'warning'.
# The assembly step uses this to DROP the sentence rather than rewrite it.

# ── Proper noun detection ────────────────────────────────────────────────────
# A proper noun is a capitalized word that is NOT:
# - The first word of the sentence (always capitalized)
# - A common word that sometimes appears capitalized after certain punctuation
# - Part of a generic phrase like "French Riviera" used only as a vague locator

_R9_KNOWN_VAGUE_LOCATORS = {
    # These name a region but don't tie to THIS stop specifically
    # Only block R9 exemption when they're the ONLY proper noun and the
    # sentence has no other specifics. Actually — if the sentence names
    # a real place, even a region, it has some specificity. The 0/5 sentences
    # that DO name places ("From Cap d'Antibes to Villefranche-sur-Mer") show
    # that even proper nouns don't save a sentence if the PREDICATE is generic.
    # So we check: does the sentence SAY something specific about the named
    # thing, or just use it as a geographic label in a filler frame?
}

# Words that commonly start sentences capitalized but aren't proper nouns
_R9_SENTENCE_STARTERS_NOT_PROPER = {
    'the', 'a', 'an', 'this', 'that', 'these', 'those', 'as', 'from',
    'in', 'on', 'at', 'by', 'for', 'with', 'it', 'its', 'if', 'when',
    'while', 'here', 'there', 'each', 'every', 'some', 'many', 'one',
}

# ── Date/time detection ──────────────────────────────────────────────────────
_R9_DATE_PATTERNS = [
    r'\b\d{4}\b',                          # Year: 1888, 2023
    r'\b\d{1,2}(?:st|nd|rd|th)\s+century\b',  # "13th century"
    r'\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b',
    r'\b\d{1,2}\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)\b',
    r'\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
]
_R9_DATE_COMPILED = [re.compile(p, re.IGNORECASE) for p in _R9_DATE_PATTERNS]

# ── Number/measurement detection ─────────────────────────────────────────────
_R9_NUMBER_PATTERNS = [
    r'\b\d+\.?\d*\s*(?:km|m|ft|feet|miles?|meters?|metres?|inches?|yards?)\b',
    r'\b\d+\.?\d*\s*(?:kg|lb|tons?|tonnes?)\b',
    r'\b\d+(?:,\d{3})*\b',                # Numbers with commas: 1,200
    r'\b\d+\.?\d+\b',                      # Decimal numbers: 2.7
    r'\b(?:320|130|2\.7)\b',               # Specific numbers from Michael's 5/5 text
]
_R9_NUMBER_COMPILED = [re.compile(p, re.IGNORECASE) for p in _R9_NUMBER_PATTERNS]

# ── Generic filler signals ───────────────────────────────────────────────────
# These phrases/words appear in sentences that could be placed in "millions
# of stops." They signal stance/atmosphere/transition with no specifics.
_R9_FILLER_PATTERNS = [
    # Journey/continue patterns
    r'\bcontinue\s+your\s+journey\b',
    r'\bas\s+you\s+continue\s+your\b',
    r'\bon\s+your\s+journey\b',
    # "charming town/place/village" — generic descriptor
    r'\b(?:charming|quaint|picturesque|enchanting|delightful)\s+(?:town|place|village|city|area|neighborhood|neighbourhood)\b',
    # "hidden paths/stories/secrets/tales"
    r'\bhidden\s+(?:paths?|stories?|secrets?|tales?|treasures?|gems?)\b',
    # "stories of this place"
    r'\bstories\s+of\s+this\s+place\b',
    # "uncover/discover more" (without specific object)
    r'\b(?:uncover|discover)\s+more\s+of\s+(?:its|the|this)\b',
    # "intriguing history" (unspecified)
    r'\bintriguing\s+(?:history|past|heritage|stories?)\b',
    # "a collection that spans"
    r'\ba\s+collection\s+that\s+spans\b',
    # "more ground than these stops alone"
    r'\bmore\s+(?:ground|territory|area)\s+than\s+(?:these|those)\s+stops?\b',
    # "timeless charm/elegance/beauty"
    r'\btimeless\s+(?:charm|elegance|beauty|allure|appeal)\b',
    # "consider how" + vague object
    r'\bconsider\s+how\s+(?:these|those|the)\b',
    # "shaped the stories"
    r'\bshaped\s+the\s+(?:stories?|history|narrative)\b',
    # "leading you to"
    r'\bleading\s+you\s+to\b',
    # Generic closers: "every corner holds..."
    r'\bevery\s+corner\s+holds?\b',
    # "spans more ground"
    r'\bspans?\s+more\s+ground\b',
    # LOCAL-247: "inspired countless/many [X] over the years/centuries"
    r'\binspired\s+(?:countless|many|numerous|innumerable)\s+\w+\s+over\s+the\s+(?:years|centuries|decades|generations)\b',
    # LOCAL-247: "stunning/breathtaking [landscape/scenery] that has inspired"
    r'\b(?:stunning|breathtaking|beautiful|magnificent)\s+(?:coastal\s+)?(?:landscape|scenery|view|vista|panorama)\s+that\s+has\b',
]
_R9_FILLER_COMPILED = [re.compile(p, re.IGNORECASE) for p in _R9_FILLER_PATTERNS]


def _has_proper_noun(sentence: str) -> bool:
    """Check if sentence contains a proper noun that provides SUBSTANTIVE specificity.

    A proper noun is a capitalized word that isn't the first word and isn't
    a common word. Also detects multi-word proper nouns like "Cap d'Antibes".

    CRITICAL NUANCE (D89): A proper noun only provides specificity if the
    sentence SAYS something about that place. If the proper nouns are just
    used as geographic labels in a generic frame ("From X to Y — [filler]"),
    they don't save the sentence. We detect this by checking if the predicate
    (the part after the place-name frame) has substance.

    LOCAL-247: Extended beyond "From X to Y" to catch the broader pattern:
    place names as subject with entirely generic predicate. E.g.:
    "The Cap d'Antibes, along with Cap Ferrat, forms a stunning coastal
    landscape that has inspired countless creatives over the years."
    The proper nouns are geographic labels; the predicate delivers nothing.
    """
    words = sentence.split()
    if len(words) < 2:
        return False

    proper_nouns_found = []

    # Skip the first word (always capitalized)
    for i, word in enumerate(words[1:], start=1):
        # Strip punctuation
        clean = re.sub(r'[^a-zA-Z\'-]', '', word)
        if not clean:
            continue
        # Check if capitalized
        if clean[0].isupper() and len(clean) > 1:
            # Not a common word that happens to be capitalized
            if clean.lower() not in _R9_SENTENCE_STARTERS_NOT_PROPER:
                proper_nouns_found.append(clean)

    if not proper_nouns_found:
        return False

    # Check if the proper nouns are just in a "From X to Y" frame with generic predicate
    lower = sentence.lower()
    if re.match(r'^from\s+', lower) and ('\u2014' in sentence or '\u2013' in sentence or ' - ' in sentence):
        # Split on em-dash/en-dash/spaced-hyphen to get the predicate
        predicate = re.split(r'[\u2014\u2013]|\s-\s', sentence, maxsplit=1)
        if len(predicate) > 1:
            pred_text = predicate[1].strip()
            # If the predicate has no specifics of its own and matches filler,
            # the proper nouns are just labels
            pred_has_specifics = False
            for w in pred_text.split():
                clean_w = re.sub(r'[^a-zA-Z0-9\'-]', '', w)
                if not clean_w:
                    continue
                if len(clean_w) > 1 and clean_w[0].isupper() and clean_w.lower() not in _R9_SENTENCE_STARTERS_NOT_PROPER:
                    pred_has_specifics = True
                    break
                if re.match(r'\d', clean_w):
                    pred_has_specifics = True
                    break
            if not pred_has_specifics and _has_filler_signal(pred_text):
                return False  # Proper nouns are just geographic labels in filler

    # LOCAL-247: Generalized D89 check — if ALL proper nouns in the sentence
    # are place-name-like, and the verb/predicate portion is generic filler,
    # then the proper nouns don't provide substantive specificity.
    # Pattern: "[Place], along with [Place], [generic verb phrase]"
    #
    # Strategy: check if all proper nouns are geographic, then check if
    # the predicate is pure filler with no factual content.
    _geo_prefixes = {'cap', 'mont', 'monte', 'jardin', 'château', 'chateau',
                     'lac', 'île', 'ile', 'fort', 'villa', 'hôtel', 'hotel',
                     'col', 'val', 'port', 'pointe', 'baie', 'pic',
                     'rue', 'place', 'avenue', 'boulevard', 'piazza',
                     'via', 'corso', 'calle', 'plage', 'sentier', 'chemin'}
    _geo_proper_set = {'riviera', 'mediterranean', 'adriatic', 'atlantic',
                       'pacific', 'alps', 'pyrenees', 'sahara', 'amazon',
                       'danube', 'rhine', 'seine', 'loire', 'nile'}
    _nationality_set = {'french', 'italian', 'spanish', 'german', 'english',
                        'british', 'greek', 'roman', 'turkish', 'portuguese',
                        'dutch', 'belgian', 'swiss', 'austrian', 'russian',
                        'chinese', 'japanese', 'indian', 'african', 'european',
                        'asian', 'american', 'northern', 'southern', 'eastern',
                        'western'}
    # Check if at least one proper noun is a geographic prefix — if so,
    # unknown adjacent proper nouns are likely place-name components
    has_geo_prefix = any(pn.lower() in _geo_prefixes for pn in proper_nouns_found)

    all_place_like = True
    for pn in proper_nouns_found:
        pn_lower = pn.lower()
        pn_stem = _normalize_for_place_check(pn)
        if pn_lower in _PLACE_WORDS or pn_stem in _PLACE_WORDS:
            continue
        if pn_lower in _geo_proper_set:
            continue
        if pn_lower in _nationality_set:
            continue
        if pn_lower in _geo_prefixes:
            continue
        # Unknown word — is it a place-name component (like "Ferrat" in "Cap Ferrat")?
        # If there's a geographic prefix among the other proper nouns, treat
        # unknown adjacent capitalized words as part of a place name.
        if has_geo_prefix:
            continue
        # No geographic prefix sibling — this could be a person name
        all_place_like = False
        break

    if all_place_like and proper_nouns_found:
        # All proper nouns are geographic. Check if the sentence has
        # any non-geographic factual content (dates, numbers, specific events)
        has_date = _has_date(sentence)
        has_number = _has_number(sentence)
        if not has_date and not has_number:
            # Check if the predicate portion has generic filler patterns
            _generic_predicate_patterns = [
                # "inspired countless/many X over the years"
                r'\binspired\s+(?:countless|many|numerous|innumerable)\b',
                # "forms/creates a stunning/beautiful/gorgeous [landscape/scene]"
                r'\bforms?\s+(?:a\s+)?(?:stunning|beautiful|gorgeous|breathtaking|magnificent|spectacular)\b',
                # "has attracted/drawn [visitors/tourists/artists] for [decades/centuries]"
                r'\b(?:attracted|drawn|lured|beckoned)\s+(?:visitors?|tourists?|artists?|creatives?|travelers?|travellers?)\b.*\b(?:for|over)\s+(?:decades|centuries|years|generations)\b',
                # "has inspired countless creatives over the years"
                r'\binspired\s+.*\bover\s+the\s+(?:years|centuries|decades|generations)\b',
                # "showcases the region's [abstract quality]"
                r'\bshowcases?\s+the\s+(?:region|area|coast|city|town)\'?s?\s+(?:unspoiled\s+)?(?:beauty|charm|elegance|history|heritage|culture)\b',
                # "that has inspired [anyone] over the years/centuries"
                r'\bthat\s+has\s+inspired\b.*\bover\s+the\s+(?:years|centuries|decades|generations)\b',
            ]
            for pat in _generic_predicate_patterns:
                if re.search(pat, sentence, re.IGNORECASE):
                    return False  # Place-name labels + generic predicate = no specificity
            # Also check standard filler signal
            if _has_filler_signal(sentence):
                return False

    return True


def _has_date(sentence: str) -> bool:
    """Check if sentence contains a date or time reference."""
    for pat in _R9_DATE_COMPILED:
        if pat.search(sentence):
            return True
    return False


def _has_number(sentence: str) -> bool:
    """Check if sentence contains a meaningful number/measurement."""
    for pat in _R9_NUMBER_COMPILED:
        if pat.search(sentence):
            return True
    return False


def _has_filler_signal(sentence: str) -> bool:
    """Check if sentence contains generic filler language.

    CONSERVATIVE: requires a STRONG filler signal — distinctive patterns from
    Michael's 0/5 verdicts. Weaker signals like "timeless elegance" alone are
    NOT sufficient, because they can appear in sentences that are part of
    groups scored 3/5 (where the group's substance comes from other sentences).

    The 0/5 sentences share a structural trait: they are SELF-CONTAINED transition
    or closer sentences that reference no specific content from any stop.
    """
    count = 0
    for pat in _R9_FILLER_COMPILED:
        if pat.search(sentence):
            count += 1
    # Require at least 2 filler signals to fire, OR one very strong signal
    # that is distinctive of the "millions of stops" pattern
    if count >= 2:
        return True

    # Single strong signals — patterns that are definitively generic closers/transitions
    _STRONG_FILLER = [
        r'\bcontinue\s+your\s+journey\b',
        r'\bas\s+you\s+continue\s+your\b',
        r'\ba\s+collection\s+that\s+spans\b',
        r'\bmore\s+(?:ground|territory|area)\s+than\s+(?:these|those)\s+stops?\b',
        r'\bspans?\s+more\s+ground\b',
        r'\bleading\s+you\s+to\s+(?:uncover|discover)\b',
        r'\bstories\s+of\s+this\s+place\b',
    ]
    for pat_str in _STRONG_FILLER:
        if re.search(pat_str, sentence, re.IGNORECASE):
            return True

    return False


def _has_contentless_signal(sentence: str) -> bool:
    """LOCAL-251: Detect sentences with NO content — metaphorical language about nothing.

    Michael's round 2 review: "senseless combination of words and facts with no
    interconnectedness… they make listener confused instead of informed."

    These sentences have no proper noun, no date, no number, AND use metaphorical
    or abstract language that says nothing concrete about the stop. They differ from
    filler (which uses journey/charming/uncover patterns) in that they use:
      - Metaphorical verbs with abstract objects (bear the weight of, echo with,
        exude, intertwine, linger)
      - "portal to a world" / "journey through the annals" type constructions
      - Abstract nouns as the entire substance (history, culture, creativity,
        warmth, spirit) with no concrete predicate

    CONSERVATIVE: Only fires when the sentence is ENTIRELY metaphorical/abstract.
    A sentence that has metaphorical language but ALSO contains a fact should NOT
    fire — the fact saves it. The caller ensures no specifics are present.

    Guard: this is called ONLY when _has_proper_noun, _has_date, and _has_number
    have all returned False. So by the time we get here, the sentence has no
    anchoring specifics at all.
    """
    lower = sentence.lower()

    # Pattern 1: Metaphorical verbs paired with abstract objects
    # "bear the weight of history", "echo with the footsteps", "exude warmth"
    _METAPHORICAL_PATTERNS = [
        # [subject] bear/carry/hold the weight/burden of [abstract]
        r'\b(?:bear|bears|carry|carries|carried|hold|holds)\s+the\s+(?:weight|burden)\s+of\b',
        # [subject] echo/resound/ring with [abstract]
        r'\b(?:echo|echoes|echoed|echoing|resound|resounds|ring|rings)\s+with\b',
        # [subject] exude/radiate/emanate [abstract]
        r'\b(?:exude|exudes|exuded|radiate|radiates|emanate|emanates|emanating)\s+(?:\w+\s+){0,3}(?:warmth|charm|elegance|beauty|sense|aura|energy|spirit)\b',
        # [subject] intertwine/weave/blend seamlessly/together
        r'\b(?:intertwine|intertwines|weave|weaves|blend|blends)\s+(?:seamlessly|together|harmoniously)\b',
        # "lingers in the very air" / "infusing every corner"
        r'\blingers?\s+in\s+the\s+(?:very\s+)?(?:air|atmosphere|streets?|walls?)\b',
        r'\binfusing\s+(?:every|each|the)\s+(?:corner|street|wall|stone)\b',
        # "testament to the enduring power/spirit of"
        r'\btestament\s+to\s+the\s+(?:enduring|lasting|timeless|eternal)\b',
        # "palpable" as standalone quality claim
        r'\b(?:is|are|was|were)\s+palpable\b',
        # "living testament" / "a living [metaphor]"
        r'\ba\s+living\s+(?:testament|proof|reminder|example|embodiment)\b',
    ]

    # Pattern 2: Journey/portal metaphors (not the "continue your journey" filler
    # but the "is a portal to a world" / "journey through the annals" type)
    _JOURNEY_METAPHORS = [
        # "is a portal/gateway to a world where"
        r'\b(?:is|becomes?|serves?\s+as)\s+(?:a\s+)?(?:portal|gateway|window|bridge|doorway)\s+(?:to|into|between)\b',
        # "a journey through the annals of"
        r'\bjourney\s+through\s+the\s+(?:annals|pages|chapters|corridors)\s+of\b',
        # "is not merely a destination" (meta-comment about the place)
        r'\bnot\s+merely\s+a\s+(?:destination|stop|place|village|town|city)\b',
        # "each step taken is a [metaphor]"
        r'\beach\s+step\s+(?:taken\s+)?(?:is|becomes)\s+a\b',
    ]

    # Pattern 3: Abstract nouns as entire predicate with no concrete detail
    # "the enduring power of human expression"
    # "a sense of creative energy"
    _ABSTRACT_PREDICATE = [
        # "the enduring/timeless [power/spirit/essence] of [abstract]"
        r'\bthe\s+(?:enduring|timeless|eternal|lasting|profound)\s+(?:power|spirit|essence|allure|beauty|charm|nature)\s+of\b',
        # "a sense of [abstract noun]"
        r'\ba\s+(?:sense|feeling|aura|air|atmosphere)\s+of\s+(?:creative|artistic|historic|historical|cultural|spiritual|timeless|ancient)\b',
        # "[noun]'s artistic/creative/cultural spirit is"
        r"\b(?:artistic|creative|cultural|spiritual)\s+spirit\s+(?:is|are|was|were)\b",
    ]

    for patterns in (_METAPHORICAL_PATTERNS, _JOURNEY_METAPHORS, _ABSTRACT_PREDICATE):
        for pat in patterns:
            if re.search(pat, lower):
                return True

    return False


def check_r9_generic(sentence: str) -> List[Dict]:
    """R9: Detect generic sentences that carry no stop-specific content.

    A sentence is generic when:
    1. It has NO proper noun, date, or number (nothing tying it to this stop)
    2. It HAS generic filler signals (stance/atmosphere/transition language)

    LOCAL-251 extension: ALSO fires when:
    1. It has NO proper noun, date, or number (nothing tying it to this stop)
    2. It HAS contentless signals — metaphorical/abstract language about nothing
       (the "senseless combination of words" class Michael identified in round 2)

    BOTH conditions must be true. A terse factual sentence without specifics
    but also without filler is NOT generic — it's just short.

    Navigation is exempt (handled before this is called).

    Severity: 'delete' — this sentence should be removed, not rewritten.
    """
    findings = []
    stripped = sentence.strip()
    if not stripped:
        return findings

    # Navigation exemption (already handled at caller level, but belt+suspenders)
    if _is_style_navigation_sentence(stripped):
        return findings

    # Check for specifics: proper nouns, dates, numbers
    has_specifics = (
        _has_proper_noun(stripped) or
        _has_date(stripped) or
        _has_number(stripped)
    )

    if has_specifics:
        return findings  # Has something tying it to a specific place/time

    # Check for filler signals (original path)
    if _has_filler_signal(stripped):
        findings.append({
            'rule_id': 'R9_GENERIC',
            'severity': 'delete',
            'sentence': stripped,
            'suggestion': 'This sentence carries nothing specific to this stop — it could be placed in millions of stops. Delete it.',
        })
        return findings

    # LOCAL-251: Check for contentless signals — metaphorical/abstract language
    # that says nothing concrete. This catches "The ancient pathways bear the
    # weight of history on their worn stones" and "Each step taken is a journey
    # through the annals of creativity and culture."
    if _has_contentless_signal(stripped):
        findings.append({
            'rule_id': 'R9_GENERIC',
            'severity': 'delete',
            'sentence': stripped,
            'suggestion': 'This sentence uses metaphorical language about nothing concrete — no fact, no date, no specific claim. Delete it.',
        })
        return findings

    return findings


# ═══════════════════════════════════════════════════════════════════════════════
# R9 DELETION LOGIC (assembly-time)
# ═══════════════════════════════════════════════════════════════════════════════

# Dangling connective patterns — if a paragraph starts with one of these after
# deletion of the preceding sentence, the connective should be stripped.
_DANGLING_CONNECTIVE_PATTERNS = [
    r'^(?:And|But|So|Yet|However|Moreover|Furthermore|Additionally|Also|Meanwhile|Nevertheless|Therefore|Thus|Hence)\s*,?\s*',
    r'^(?:In addition|On top of that|What is more|As a result)\s*,?\s*',
]
_DANGLING_CONNECTIVE_COMPILED = [re.compile(p, re.IGNORECASE) for p in _DANGLING_CONNECTIVE_PATTERNS]


def apply_r9_deletions(paragraph: str) -> str:
    """Apply R9 deletions to a paragraph.

    - Removes sentences flagged as R9_GENERIC
    - Strips dangling connectives from the resulting first sentence
    - Returns empty string if all sentences are deleted (caller handles)

    Behind DISABLE_R9_DELETION=1 env var — caller checks this.
    """
    if not paragraph or not paragraph.strip():
        return paragraph

    sentences = _split_sentences(paragraph)
    if not sentences:
        return paragraph

    kept = []
    for sentence in sentences:
        if len(sentence) < 10:
            kept.append(sentence)
            continue
        # Navigation sentences are never deleted
        if _is_style_navigation_sentence(sentence):
            kept.append(sentence)
            continue
        findings = check_r9_generic(sentence)
        if not findings:
            kept.append(sentence)
        # else: sentence is generic — drop it

    if not kept:
        return ''  # All sentences deleted — caller removes the paragraph

    # Fix dangling connective on the new first sentence
    result_text = ' '.join(kept)

    # If the first remaining sentence starts with a dangling connective
    # (because the sentence before it was deleted), strip the connective.
    for pat in _DANGLING_CONNECTIVE_COMPILED:
        new_text = pat.sub('', result_text, count=1)
        if new_text != result_text:
            # Re-capitalize the first letter
            new_text = new_text.strip()
            if new_text and new_text[0].islower():
                new_text = new_text[0].upper() + new_text[1:]
            result_text = new_text
            break

    return result_text.strip()


def apply_r9_to_description(description: str) -> Tuple[str, int, int]:
    """Apply R9 deletions to a full stop description (multiple paragraphs).

    Returns:
        (new_description, sentences_deleted, paragraphs_emptied)

    Handles:
    - Sentence-level deletion within paragraphs
    - Empty paragraph removal (when all sentences in a paragraph are generic)
    - Dangling connective cleanup

    Behind DISABLE_R9_DELETION=1 — caller must check.
    """
    if not description or not description.strip():
        return description, 0, 0

    paragraphs = [p for p in description.split('\n\n') if p.strip()]
    if not paragraphs:
        return description, 0, 0

    new_paragraphs = []
    total_deleted = 0
    paragraphs_emptied = 0

    for para in paragraphs:
        para = para.strip()
        if len(para) <= 30:
            # Short segments (assembly lines, spacing) pass through unchanged
            new_paragraphs.append(para)
            continue

        # Count sentences before and after
        sentences_before = _split_sentences(para)
        result = apply_r9_deletions(para)

        if not result:
            # All sentences deleted — drop the paragraph
            paragraphs_emptied += 1
            total_deleted += len([s for s in sentences_before if len(s) >= 10])
        else:
            sentences_after = _split_sentences(result)
            deleted_count = len([s for s in sentences_before if len(s) >= 10]) - len([s for s in sentences_after if len(s) >= 10])
            total_deleted += max(0, deleted_count)
            new_paragraphs.append(result)

    new_description = '\n\n'.join(new_paragraphs)
    return new_description, total_deleted, paragraphs_emptied


# ═══════════════════════════════════════════════════════════════════════════════
# R10: Unfulfilled promise detection (LOCAL-235)
# ═══════════════════════════════════════════════════════════════════════════════
# Michael's rule (said seven times): "Either tell us the story or get rid of
# the sentence!" If a sentence names a subject that requires substantiation
# (a story, a tale, history, a legacy, a connection, a testament, an allure,
# a chapter, a secret, a witness to centuries) and NEITHER that sentence NOR
# its neighbours deliver it — delete.
#
# Delivery means a concrete payload: a date, a named person or event, a
# documented fact. Not another abstraction.
#
# MUST FIRE on (his complaints from Round 2):
#   "each crack and crevice holding a story"
#   "The hillsides hold a multitude of tales from a bygone era."
#   "serves as a bridge between ancient civilizations and contemporary life…"
#   "a harmonious symphony of past and present"
#   "a testament to the enduring allure…"
#   "Cycling along the shimmering waters, you are not just exploring a physical
#    landscape but also delving into a rich tapestry of history…"
#
# MUST NOT FIRE on (his own rewrite text — what good looks like):
#   "In 200 BC, the area surrounding Èze saw its first inhabitants settle
#    near Mount Bastide."
#   "The Antonine Itinerary mentions the bay of Èze as Avisionis portus."
#   "Start cycling south on the main road…" (navigation)
#   "F. Scott Fitzgerald based the opening hotel of his 1934 novel on Eden-Roc."
#   "the Hôtel du Cap-Eden-Roc, was built here in 1870, at the southern tip"
#
# SEVERITY: 'error' — wired to deletion behind DISABLE_R10_DELETION=1.
# ─────────────────────────────────────────────────────────────────────────────

# ── Promise trigger phrases ──────────────────────────────────────────────────
# These signal the sentence is PROMISING something — a story, tale, history,
# connection, etc. — that requires follow-through.
_R10_PROMISE_PATTERNS = [
    # "holding a story / holding stories"
    r'\bhold(?:s|ing)?\s+(?:a\s+)?(?:stor(?:y|ies)|tale[s]?|secret[s]?|chapter[s]?)\b',
    # "a multitude of tales / tales from a bygone era"
    r'\b(?:multitude|wealth|treasure)\s+of\s+(?:tales?|stories?|secrets?|legends?)\b',
    # "a rich tapestry of history/culture"
    r'\brich\s+tapestry\s+of\s+(?:history|culture|stories?|heritage)\b',
    # "a testament to the enduring allure/legacy"
    r'\ba\s+testament\s+to\s+(?:the\s+)?(?:enduring\s+)?(?:allure|legacy|spirit|charm|beauty|power)\b',
    # "bridge between ancient civilizations"
    r'\bbridge\s+between\s+(?:ancient|past|old)\b',
    # "symphony of past and present"
    r'\bsymphony\s+of\s+(?:past\s+and\s+present|old\s+and\s+new)\b',
    # "witness to centuries / stood witness to"
    r'\bwitness\s+to\s+(?:centuries|generations|ages|history|time)\b',
    # "delving into a rich tapestry / exploring a rich tapestry"
    r'\b(?:delving|diving|exploring|dipping)\s+into\s+(?:a\s+)?(?:rich\s+)?(?:tapestry|world|realm)\b',
    # "whisper tales / whispers of" (personification as filler)
    r'\bwhisper[s]?\s+(?:tales?|stories?|of\s+(?:a\s+)?bygone)\b',
    # "tales from a bygone era"
    r'\btales?\s+(?:from|of)\s+(?:a\s+)?bygone\b',
    # "steeped in history / steeped in tradition"
    r'\bsteeped\s+in\s+(?:history|tradition|heritage|legend|lore)\b',
    # "echoes of a bygone era / echoes of the past"
    r'\bechoes?\s+of\s+(?:a\s+)?(?:bygone|the\s+past|history|time)\b',
    # "a chapter in" (metaphorical, no specific chapter)
    r'\ba\s+chapter\s+in\s+(?:the|its|a)\b',
    # "enduring legacy / enduring spirit / enduring allure"
    r'\benduring\s+(?:legacy|spirit|allure|charm|beauty|appeal)\b',
    # "centuries of history" (without specifying WHICH centuries/events)
    r'\bcenturies\s+of\s+(?:history|tradition|heritage|culture|stories?)\b',
    # "palpable sense of antiquity / sense of history"
    r'\bsense\s+of\s+(?:antiquity|history|heritage|the\s+past|time)\b',
    # "thread weaving through the fabric of time"
    r'\b(?:thread|fabric)\s+(?:weaving|of\s+time|through\s+time)\b',
    # "connection between past and present"
    r'\bconnection\s+between\s+(?:past\s+and\s+present|old\s+and\s+new|then\s+and\s+now)\b',
    # "transport visitors back through the annals of time"
    r'\b(?:transport|take|carry)\s+(?:visitors?|you|us)\s+back\s+(?:through|in|to)\b',
    # "timeless allure... resides in its ability" — only when paired with
    # words that promise content delivery (allure, appeal = abstract promise)
    # NOT "timeless charm" which is just a descriptor
    r'\btimeless\s+(?:allure|appeal)\s+(?:of|resides)\b',
]
_R10_PROMISE_COMPILED = [re.compile(p, re.IGNORECASE) for p in _R10_PROMISE_PATTERNS]

# ─── Structural promise detection (LOCAL-240) ────────────────────────────────
# Widens R10 from a phrase list to the SHAPE: a narrative-promising noun
# governed by a verb of possession or concealment.  "Villages hold forgotten
# tales" promises; "the villages were fortified in 1388" states.
#
# A sentence triggers if it contains BOTH:
#   1. A promise noun — a word that inherently promises narrative content
#   2. A promise verb — a verb of possession, concealment, or revelation
#      (NOT a verb of statement like "mentions", "was built", "settled")
#
# This is ADDITIVE to the regex patterns above — either path fires the promise.

_R10_STRUCTURAL_PROMISE_NOUNS = frozenset({
    'tale', 'tales', 'story', 'stories', 'secret', 'secrets',
    'chapter', 'chapters', 'legacy', 'legacies', 'roots',
    'tapestry', 'whispers', 'whisper', 'essence',
    'juxtaposition', 'symphony',
})

_R10_STRUCTURAL_PROMISE_VERBS = re.compile(
    r'\b(?:'
    r'hold[s]?|holding|'
    r'mask[s]?|masking|masked|'
    r'conceal[s]?|concealing|concealed|'
    r'carry|carries|carrying|carried|'
    r'whisper[s]?|whispering|whispered|'
    r'reveal[s]?|revealing|revealed|'
    r'stand[s]?\s+sentinel|'
    r'unravel[s]?|unraveling|unravelled|'
    r'shape[s]?|shaping|shaped|'
    r'discover(?!ed\s+(?:in|by|that|when))|'  # "discover X" promises; "discovered in 1870" states
    r'hide[s]?|hiding|hidden|'
    r'guard[s]?|guarding|guarded|'
    r'unveil[s]?|unveiling|unveiled|'
    r'beckon[s]?|beckoning|beckoned|'
    r'woven|weav(?:e[s]?|ing)'
    r')\b',
    re.IGNORECASE,
)


def _sentence_has_structural_promise(sentence: str) -> bool:
    """Check if sentence has the SHAPE of a promise: noun + verb.

    LOCAL-240: catches "villages hold a tapestry", "masks the secrets",
    "forgotten tales that shape its identity" — shapes that the regex list
    misses because it only matched fixed phrases.
    """
    # Tokenize to check for promise nouns
    words = set(re.findall(r'[a-z]+', sentence.lower()))
    if not (words & _R10_STRUCTURAL_PROMISE_NOUNS):
        return False
    # Check for promise verb
    if not _R10_STRUCTURAL_PROMISE_VERBS.search(sentence):
        return False
    return True


# ─── Subject-matter promise detection (LOCAL-249) ────────────────────────────
# Michael's complaint: R10 relies on matching verb+noun idioms, but a language
# model rephrases endlessly. "hinting at the secrets", "echoing with stories",
# "reveal different facets" — all promise subject matter without delivering it,
# and none match the verb whitelist.
#
# The structural insight: the PRESENCE of abstract subject-matter nouns as the
# point of the sentence IS the promise, regardless of verb. A sentence that
# asserts the existence of "secrets", "stories", "facets", "grandeur" etc.
# without concrete substantiation (date, person, measurement) is making a
# promise by construction.
#
# Guard against false positives: sentences with concrete payload self-deliver
# and are handled downstream by _sentence_has_concrete_payload in the R10 flow.
# Navigation sentences are exempt via _is_navigation_sentence.
#
# This is VERB-INDEPENDENT: we do not require a specific carrying verb.
# The abstract noun itself, positioned as the object of the sentence's claim,
# is sufficient.

_R10_SUBJECT_MATTER_NOUNS = frozenset({
    # Core narrative-promise nouns (from existing _R10_STRUCTURAL_PROMISE_NOUNS)
    'tale', 'tales', 'story', 'stories', 'secret', 'secrets',
    'chapter', 'chapters', 'legacy', 'legacies', 'roots',
    'tapestry', 'whispers', 'whisper', 'essence', 'juxtaposition', 'symphony',
    # Extended set (LOCAL-249): abstract nouns Michael identified as the defect
    'allure', 'grandeur', 'opulence', 'elegance', 'splendor', 'splendour',
    'intrigue', 'mystique', 'enigma',
    'facets', 'facet',
    'spirit',
    'treasures',  # "hidden treasures" with no follow-up
    'wonders',
    'mysteries', 'mystery',
    'introspection',  # "quiet introspection" — what introspection?
})

# NOTE: "history", "heritage", "culture", "beauty", "charm", "tradition",
# "modernity" are intentionally EXCLUDED. They are too common as incidental
# words in substantiated sentences (e.g., "the hotel's history began in 1870")
# and their inclusion pushed R10 beyond the 3x corpus-wide threshold.
# They ARE part of the defect Michael describes, but catching them requires
# a syntactic role check (are they the POINT of the sentence?) which is
# beyond deterministic detection without an LLM. Future work (LOCAL-249+).


def _sentence_has_subject_matter_promise(sentence: str) -> bool:
    """LOCAL-249: Detect promise by subject-matter noun presence (verb-independent).

    A sentence that puts forward abstract subject-matter nouns as its assertion
    is making a promise regardless of the verb carrying them. "hinting at the
    secrets", "echoing with stories", "reveal different facets" all promise
    without the specific verbs in the old whitelist.

    Returns True if the sentence contains subject-matter nouns that make it a
    promise. The concrete-payload check downstream prevents false positives on
    sentences that self-deliver (have dates, names, measurements).
    """
    words = set(re.findall(r'[a-z]+', sentence.lower()))
    if words & _R10_SUBJECT_MATTER_NOUNS:
        return True
    return False


def _extract_subject_matter(sentence: str) -> list:
    """Extract the abstract subject-matter nouns from a sentence.

    Returns a list of the abstract nouns found, for evidence/reporting purposes.
    """
    words = set(re.findall(r'[a-z]+', sentence.lower()))
    found = []
    for noun in sorted(words & _R10_SUBJECT_MATTER_NOUNS):
        found.append(noun)
    return found


def _sentence_has_promise(sentence: str) -> bool:
    """Check if a sentence contains a promise-trigger phrase or shape."""
    # Path 1: original regex patterns (exact phrases)
    for pat in _R10_PROMISE_COMPILED:
        if pat.search(sentence):
            return True
    # Path 2: structural detection (LOCAL-240) — noun + verb shape
    if _sentence_has_structural_promise(sentence):
        return True
    # Path 3: subject-matter detection (LOCAL-249) — verb-independent
    # The sentence puts forward abstract nouns as its assertion.
    if _sentence_has_subject_matter_promise(sentence):
        return True
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# UNIFIED PLACE VOCABULARY (LOCAL-247)
# ═══════════════════════════════════════════════════════════════════════════════
# One set consulted by BOTH _is_place_name AND _sentence_has_concrete_payload.
# Prior to LOCAL-247, _place_suffixes and _place_only_words disagreed:
#   - 'path' was in _place_only_words but not _place_suffixes
#   - 'coastal' (adjective of 'coast') was unrecognized
# This caused "Coastal Path" to be classified as a person name.

_PLACE_WORDS = {
    # Infrastructure / routes
    'village', 'town', 'city', 'park', 'garden', 'bay', 'beach',
    'coast', 'cape', 'peninsula', 'island', 'mountain', 'hill',
    'street', 'road', 'path', 'trail', 'square', 'plaza', 'port',
    'bridge', 'palace', 'castle', 'church', 'chapel', 'cathedral',
    'museum', 'hotel', 'tower', 'gate', 'pass', 'lighthouse',
    'fort', 'fortress', 'citadel', 'abbey', 'monastery', 'priory',
    'basilica', 'shrine', 'temple', 'harbour', 'harbor', 'pier',
    'wharf', 'quay', 'dam', 'reservoir', 'falls', 'gorge', 'canyon',
    # Additional route/path words (the gap that caused this bug)
    'walk', 'way', 'lane', 'passage', 'route', 'promenade',
    'esplanade', 'terrace', 'corniche', 'lookout', 'viewpoint',
    # Foreign route words likely in tour stop names
    'sentier', 'chemin', 'allée', 'corso', 'passeggiata',
    # Landscape features
    'cliff', 'cove', 'inlet', 'headland', 'point', 'bluff',
    'ridge', 'valley', 'peak', 'summit', 'plateau',
    # From _place_only_words that were missing from _place_suffixes
    'riviera', 'mediterranean', 'french', 'european', 'italian',
}

# Adjective-to-stem mapping: resolves adjective forms to their base place word.
# "Coastal Path" → stem('coastal')='coast' → 'coast' ∈ _PLACE_WORDS → place name.
_ADJECTIVE_TO_PLACE_STEM = {
    'coastal': 'coast',
    'mountainous': 'mountain',
    'alpine': 'mountain',
    'oceanic': 'ocean',
    'maritime': 'port',
    'riverside': 'river',
    'lakeside': 'lake',
    'hillside': 'hill',
    'seaside': 'beach',
    'cliffside': 'cliff',
    'hilltop': 'hill',
    'clifftop': 'cliff',
    'woodland': 'forest',
    'forested': 'forest',
    'volcanic': 'volcano',
    'glacial': 'glacier',
    'peninsular': 'peninsula',
    'insular': 'island',
    'suburban': 'town',
    'urban': 'city',
    'rural': 'village',
    'tropical': 'island',
    'panoramic': 'viewpoint',
    'scenic': 'route',
}

# French/Italian/Spanish/Dutch/German lowercase particles that appear inside
# multi-word place names and must NOT break a capitalized-word run.
# "Cap d'Antibes", "Hôtel du Cap-Eden-Roc", "Villa della Rotonda",
# "Ludwig van Beethoven" (also persons — that's fine, we keep the run intact
# and let _is_place_name decide afterwards).
_NAME_PARTICLES = {
    "d'", "l'", "de", "du", "des", "la", "le", "les",
    "di", "del", "della", "delle", "dei", "degli", "dall'", "dall",
    "van", "von", "den", "der", "het", "ten", "ter",
    "el", "al", "bin", "ibn",
}


def _normalize_for_place_check(word: str) -> str:
    """Resolve a word to its place-vocabulary stem if it's an adjective form."""
    lower = word.lower()
    return _ADJECTIVE_TO_PLACE_STEM.get(lower, lower)


def _is_place_name(cap_words: List[str], place_suffixes: set) -> bool:
    """Determine if a sequence of capitalized words is likely a place name.

    Place names: "Eze Village", "Cap d'Antibes", "Jardin Exotique",
    "Mont Bastide", "Eden-Roc", "French Riviera", "Coastal Path"
    Person names: "F. Scott Fitzgerald", "Claude Monet", "Saracen raiders"

    Heuristic: if the last word (lowercased or adjective-resolved) is a
    place-type word, or if the sequence matches geographic patterns, treat
    it as a place name rather than a person name.

    LOCAL-247: uses _PLACE_WORDS (unified vocabulary) and resolves adjective
    forms via _ADJECTIVE_TO_PLACE_STEM.
    """
    if not cap_words:
        return False
    # Strip trailing possessive ('s) for matching
    last_clean = re.sub(r"'s$", '', cap_words[-1]).lower()
    first_clean = re.sub(r"'s$", '', cap_words[0]).lower()

    # Resolve adjective forms
    last_stem = _normalize_for_place_check(cap_words[-1])
    first_stem = _normalize_for_place_check(cap_words[0])

    # If last word (or its stem) is a place word
    if last_clean in _PLACE_WORDS or last_stem in _PLACE_WORDS:
        return True
    # If first word (or its stem) is a place word
    if first_clean in _PLACE_WORDS or first_stem in _PLACE_WORDS:
        return True

    # Known geographic proper nouns (regions, seas, etc.)
    _geo_proper = {'riviera', 'mediterranean', 'adriatic', 'atlantic',
                   'pacific', 'alps', 'pyrenees', 'sahara', 'amazon',
                   'danube', 'rhine', 'seine', 'loire', 'nile'}
    if last_clean in _geo_proper or first_clean in _geo_proper:
        return True
    # "Cap", "Mont", "Monte", "Jardin", "Château" at start = geographic
    if first_clean in {'cap', 'mont', 'monte', 'jardin', 'château', 'chateau',
                       'lac', 'île', 'ile', 'fort', 'villa', 'hôtel', 'hotel',
                       'col', 'val', 'port', 'pointe', 'baie', 'pic',
                       'rue', 'place', 'avenue', 'boulevard', 'piazza',
                       'via', 'corso', 'calle', 'plage', 'sentier', 'chemin'}:
        return True
    # Nationality/region adjectives at start (French, Italian, etc.)
    if first_clean in {'french', 'italian', 'spanish', 'german', 'english',
                       'british', 'greek', 'roman', 'turkish', 'portuguese',
                       'dutch', 'belgian', 'swiss', 'austrian', 'russian',
                       'chinese', 'japanese', 'indian', 'african', 'european',
                       'asian', 'american', 'northern', 'southern', 'eastern',
                       'western'}:
        return True
    # Check any word in the sequence (or its stem) against _PLACE_WORDS
    for w in cap_words:
        w_lower = re.sub(r"'s$", '', w).lower()
        w_stem = _normalize_for_place_check(w)
        if w_lower in _PLACE_WORDS or w_stem in _PLACE_WORDS:
            return True
    # Exactly 2 words where one is a known geographic modifier
    if len(cap_words) == 2:
        all_lower = {re.sub(r"'s$", '', w).lower() for w in cap_words}
        geo_modifiers = {'bay', 'lake', 'mount', 'cape', 'port', 'isle',
                         'point', 'valley', 'peak', 'village', 'old', 'new',
                         'east', 'west', 'north', 'south', 'upper', 'lower',
                         'grande', 'petit', 'saint', 'san', 'santa'}
        if all_lower & geo_modifiers:
            return True
    return False


def _sentence_has_concrete_payload(sentence: str) -> bool:
    """Check if a sentence delivers concrete substantiation.

    Concrete means: a date, a named person or event, a documented fact,
    a measurement. NOT another abstraction or metaphor.

    CRITICAL DISTINCTION from R9's _has_proper_noun:
    For R10, a PLACE NAME alone does not constitute delivery of a promise.
    "Eze Village serves as a bridge between ancient civilizations" names Eze
    but delivers nothing about it. Delivery requires:
      - A date/year
      - A named PERSON (not just a place)
      - A measurement/number with factual context
      - A specific event or documented fact (multi-word proper noun that's
        not a known place name)

    Single place names (Eze Village, Cap d'Antibes, Jardin Exotique) provide
    geographic ANCHORING but not SUBSTANTIATION of a promise.
    """
    # 1. Has a year (4-digit number in plausible range)
    if re.search(r'\b(?:1[0-9]{3}|20[0-2][0-9])\b', sentence):
        return True

    # 2. Has a century reference
    if re.search(r'\b\d{1,2}(?:st|nd|rd|th)[\s-]+century\b', sentence, re.IGNORECASE):
        return True

    # 3. Has a specific measurement/distance
    if re.search(r'\b\d+\.?\d*\s*(?:km|m|ft|feet|miles?|meters?|metres?|kilometers?)\b', sentence, re.IGNORECASE):
        return True

    # 4. Has a named person (two+ consecutive capitalized words that aren't
    #    a place name — "F. Scott Fitzgerald", "Claude Monet", "Mount Bastide")
    #
    # LOCAL-247 fixes:
    #   a) French/Italian/Spanish particles (d', de, du, van, von, etc.) do NOT
    #      break a capitalized run. "Cap d'Antibes Coastal Path" is one name.
    #   b) Uses _PLACE_WORDS (unified vocabulary) instead of separate sets.
    #   c) Adjective forms resolved via _normalize_for_place_check.
    #
    # LOCAL-251 fix: A person's name ALONE is not delivery. It must be paired
    # with a date, an event, or a named work. "The legacy of artists like Marc
    # Chagall lingers in the very air you breathe" names Chagall but tells you
    # NOTHING about Chagall — it is anchoring, not substantiation.
    # Same reasoning LOCAL-247 applied to place names now applied to people.
    #
    # A person name IS delivery when paired with:
    #   - A date/year (already caught by checks 1-2 above, so won't reach here)
    #   - An event verb: hosted, visited, painted, wrote, built, founded, etc.
    #   - A named work: title in quotes, or "novel"/"painting"/"book" nearby
    #   - A documented fact about what the person DID at this place
    words = sentence.split()
    has_person_name = False
    consecutive_caps = 0
    consecutive_cap_words = []
    _skip_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'by',
        'for', 'to', 'of', 'is', 'was', 'are', 'were', 'has', 'had',
        'its', 'their', 'this', 'that', 'these', 'those',
    }
    for i, word in enumerate(words):
        if i == 0:
            consecutive_caps = 0
            consecutive_cap_words = []
            continue
        clean = re.sub(r'[^a-zA-Z\u00C0-\u024F\'-]', '', word)
        if not clean:
            # Check accumulated caps before resetting
            if consecutive_caps >= 2 and not _is_place_name(consecutive_cap_words, _PLACE_WORDS):
                has_person_name = True
            consecutive_caps = 0
            consecutive_cap_words = []
            continue

        # LOCAL-247: Lowercase particles are transparent — they don't break
        # the capitalized run. "Cap d'Antibes" stays together.
        clean_lower = clean.lower()
        # Check if this word is a name particle (d', de, du, van, von, etc.)
        is_particle = False
        if clean_lower in _NAME_PARTICLES:
            is_particle = True
        elif "'" in clean:
            # Handle "d'Antibes" as a single token: split on apostrophe,
            # check if prefix is a particle, and if suffix is capitalized
            parts = clean.split("'", 1)
            if len(parts) == 2 and (parts[0].lower() + "'") in _NAME_PARTICLES:
                # The suffix after the particle (e.g., "Antibes") is the cap word
                suffix = parts[1]
                if suffix and suffix[0].isupper() and len(suffix) > 1:
                    consecutive_caps += 1
                    consecutive_cap_words.append(suffix)
                is_particle = True  # Don't process further

        if is_particle and "'" not in clean:
            # Pure particle word like "de", "van" — skip without breaking run
            continue

        if not is_particle:
            if clean[0].isupper() and len(clean) > 1 and clean_lower not in _skip_words:
                consecutive_caps += 1
                consecutive_cap_words.append(clean)
            else:
                if consecutive_caps >= 2 and not _is_place_name(consecutive_cap_words, _PLACE_WORDS):
                    has_person_name = True
                consecutive_caps = 0
                consecutive_cap_words = []
    # Final check
    if consecutive_caps >= 2 and not _is_place_name(consecutive_cap_words, _PLACE_WORDS):
        has_person_name = True

    # LOCAL-251: If a person name was found, check whether the sentence also
    # contains a substantiating context (event, date, or work). A name floating
    # in an abstraction ("the legacy of artists like X lingers in the air") is
    # NOT delivery. A name paired with a factual claim IS delivery.
    if has_person_name:
        # Event verbs: the sentence says what the person DID or what happened
        # involving them. "hosted", "painted", "wrote", "visited", "built", etc.
        _EVENT_VERB_RE = re.compile(
            r'\b(?:hosted|visited|painted|wrote|built|founded|created|composed|'
            r'performed|directed|established|designed|sculpted|discovered|'
            r'invented|published|recorded|filmed|opened|launched|introduced|'
            r'lived|stayed|resided|settled|retreated|frequented|gathered|'
            r'died|born|married|arrived|departed|fled|exiled|returned|'
            r'became|served|worked|taught|studied|graduated|'
            r'won|awarded|received|commissioned|donated|'
            r'inspired|influenced|mentored|collaborated|'
            r'hosting|painting|writing|building|creating|performing)\b',
            re.IGNORECASE
        )
        if _EVENT_VERB_RE.search(sentence):
            return True

        # Named work: quotes in the sentence suggest a title
        if '"' in sentence or '\u201c' in sentence or '\u201d' in sentence:
            return True

        # Work-type nouns already checked in #5 below, but also here:
        if re.search(r'\b(?:novel|book|work|painting|poem|opera|film|song|'
                     r'sculpture|composition|masterpiece|series|collection|'
                     r'exhibition|memoir|autobiography|biography)\b',
                     sentence, re.IGNORECASE):
            return True

        # Decades pattern: "In the 1960s" — not caught by check #1's strict
        # year pattern but is a factual temporal anchor
        if re.search(r'\b\d{4}s\b', sentence):
            return True

        # If none of the above, the person name is just ANCHORING, not DELIVERY.
        # Same reasoning as LOCAL-247 for place names: naming ≠ substantiating.
        # Fall through to remaining checks (5, 6, 7) which may still trigger.
        pass

    # 5. Named entity that's clearly a DOCUMENT, WORK, or PERSON
    #    (contains title-indicators like "novel", "itinerary", "book")
    if re.search(r'\b(?:novel|book|work|itinerary|manuscript|treaty|painting|poem|opera)\b', sentence, re.IGNORECASE):
        # If sentence mentions a literary/historical work by reference
        for i, word in enumerate(words):
            if i == 0:
                continue
            clean = re.sub(r'[^a-zA-Z\'-]', '', word)
            if not clean or len(clean) <= 2:
                continue
            if clean[0].isupper() and clean.lower() not in _R9_SENTENCE_STARTERS_NOT_PROPER:
                if clean.lower() not in _PLACE_WORDS:
                    return True

    # 6. Has a specific numeric fact (number of 3+ digits suggests a year,
    #    measurement, or population — genuine fact)
    if re.search(r'\b\d{3,}\b', sentence):
        return True

    # 7. Has a 2-digit number with measurement context (not just "the" + number)
    if re.search(r'\b\d{2}\b', sentence):
        # Only count if it's clearly a measurement or specific quantity
        if re.search(r'\b\d+\s*(?:%|percent|degrees?|floors?|rooms?|steps?|paintings?|works?|pieces?)\b', sentence, re.IGNORECASE):
            return True

    return False


# Look-ahead window: how far forward to look for delivery.
# One sentence forward is the minimum; we look 2 forward for robustness.
_R10_LOOKAHEAD = 2

# ── Topic-aware delivery matching (LOCAL-235 R2 bounce fix) ──────────────────
# LEAD's key finding: "Delivery has to be about the thing promised, not merely
# nearby. A date about Mount Bastide does not pay a promise about stone walls."
#
# A concrete payload only counts as delivery if it shares topic overlap with
# the promise sentence. We extract content words from both and require at least
# one shared non-trivial word (excluding stopwords, abstract fillers, and
# place-only terms that appear in BOTH sentences as geographic context).

_R10_STOPWORDS = frozenset({
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'by', 'for',
    'with', 'to', 'of', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
    'being', 'has', 'have', 'had', 'do', 'does', 'did', 'will', 'would',
    'could', 'should', 'may', 'might', 'shall', 'can', 'not', 'no', 'nor',
    'so', 'yet', 'both', 'each', 'every', 'all', 'any', 'few', 'more',
    'most', 'other', 'some', 'such', 'than', 'too', 'very', 'just', 'also',
    'still', 'about', 'above', 'after', 'before', 'below', 'between',
    'during', 'into', 'through', 'under', 'until', 'upon', 'within',
    'without', 'against', 'along', 'among', 'around', 'that', 'this',
    'these', 'those', 'which', 'what', 'where', 'when', 'who', 'whom',
    'whose', 'how', 'here', 'there', 'then', 'now', 'its', 'it', 'you',
    'your', 'we', 'our', 'they', 'their', 'them', 'us', 'me', 'my', 'he',
    'she', 'his', 'her', 'him', 'as', 'if', 'while', 'once', 'since',
    'only', 'even', 'much', 'many', 'well', 'back', 'over', 'out', 'up',
    'down', 'off', 'away', 'again', 'further', 'one', 'two', 'three',
})

# Abstract filler words that are common in promise sentences and don't
# constitute topic-grounding when shared with a delivery sentence
_R10_ABSTRACT_FILLERS = frozenset({
    'history', 'story', 'stories', 'tale', 'tales', 'past', 'present',
    'time', 'era', 'centuries', 'legacy', 'heritage', 'culture', 'allure',
    'charm', 'beauty', 'spirit', 'essence', 'atmosphere', 'journey',
    'experience', 'connection', 'testament', 'witness', 'chapter',
    'secret', 'secrets', 'tapestry', 'symphony', 'bridge', 'thread',
    'fabric', 'ancient', 'timeless', 'enduring', 'bygone', 'rich',
    'profound', 'palpable', 'harmonious', 'medieval', 'historic',
    'historical', 'region', 'area', 'place', 'spot', 'site', 'location',
    'visitors', 'travellers', 'travelers', 'explore', 'exploring',
    'discover', 'discovering', 'landscape', 'surroundings', 'world',
})


def _extract_content_words(sentence: str) -> set:
    """Extract meaningful content words from a sentence for topic matching.

    Returns lowercased words that are neither stopwords nor abstract fillers,
    after stripping punctuation. These are the words that ground a sentence
    to a specific topic.
    """
    # Tokenize: split on whitespace, strip punctuation
    raw_words = re.findall(r"[a-zA-Z\u00C0-\u024F'-]+", sentence.lower())
    content = set()
    for w in raw_words:
        w_clean = w.strip("'-")
        if len(w_clean) < 3:
            continue
        if w_clean in _R10_STOPWORDS:
            continue
        if w_clean in _R10_ABSTRACT_FILLERS:
            continue
        content.add(w_clean)
    return content


def _delivery_matches_promise(promise_sent: str, delivery_sent: str) -> bool:
    """Check if a concrete delivery sentence is topically relevant to a promise.

    Returns True if the delivery shares at least one content word with the
    promise sentence (after excluding stopwords and abstract fillers), OR if
    the delivery sentence self-evidently concerns the same entity (e.g. same
    geographic anchor within 1 sentence of the promise).

    The key insight from LEAD's bounce: "In 200 BC, the area surrounding Èze
    saw its first inhabitants settle near Mount Bastide" does NOT deliver
    "each crack and crevice holding a story" — there's no shared subject.
    But "These walls were built in 1388 when the village was fortified" DOES
    deliver it because "walls" appears in both.
    """
    promise_words = _extract_content_words(promise_sent)
    delivery_words = _extract_content_words(delivery_sent)

    # Find overlap
    shared = promise_words & delivery_words
    if shared:
        return True

    # Stemming fallback: check if any word in delivery is a prefix/suffix of
    # a promise word (handles "wall"/"walls", "village"/"villages", etc.)
    for pw in promise_words:
        for dw in delivery_words:
            # Shared root of 4+ chars
            if len(pw) >= 4 and len(dw) >= 4:
                if pw.startswith(dw[:4]) or dw.startswith(pw[:4]):
                    return True

    return False


def check_r10_unfulfilled_promise(sentences: List[str], index: int) -> Optional[Dict]:
    """R10: Detect an unfulfilled promise at sentence[index].

    A sentence PROMISES something (names a story, tale, history, legacy, etc.)
    and neither it nor the next _R10_LOOKAHEAD sentences DELIVER a concrete
    payload (date, named person/event, documented fact) ABOUT THE SAME SUBJECT.

    CRITICAL (LOCAL-235 R2 bounce): Delivery must be topically related to the
    promise. A date about Mount Bastide does NOT deliver a promise about stone
    walls. The delivery sentence must share content words with the promise.

    Args:
        sentences: All sentences in the paragraph (or paragraph + next paragraph)
        index: Index of the sentence to check

    Returns:
        Finding dict if unfulfilled, None if OK.
    """
    sentence = sentences[index]
    stripped = sentence.strip()
    if not stripped or len(stripped) < 15:
        return None

    # Navigation sentences are exempt
    if _is_style_navigation_sentence(stripped):
        return None

    # Does this sentence contain a promise?
    if not _sentence_has_promise(stripped):
        return None

    # Does THIS sentence also deliver? (promise + delivery in same sentence = OK)
    if _sentence_has_concrete_payload(stripped):
        return None

    # Look forward: do any of the next _R10_LOOKAHEAD sentences deliver
    # ON THE SAME TOPIC?
    for offset in range(1, _R10_LOOKAHEAD + 1):
        next_idx = index + offset
        if next_idx >= len(sentences):
            break
        next_sent = sentences[next_idx].strip()
        if not next_sent:
            continue
        if _sentence_has_concrete_payload(next_sent):
            # NEW: Check topic overlap — delivery must be about the same subject
            if _delivery_matches_promise(stripped, next_sent):
                return None  # Delivery found on-topic — promise is fulfilled

    # Also look backward 1 sentence — if the PREVIOUS sentence delivered
    # ON THE SAME TOPIC, this sentence may be a legitimate continuation/summary
    if index > 0:
        prev_sent = sentences[index - 1].strip()
        if prev_sent and _sentence_has_concrete_payload(prev_sent):
            if _delivery_matches_promise(stripped, prev_sent):
                return None  # Previous sentence delivered on-topic

    # Unfulfilled promise
    return {
        'rule_id': 'R10_UNFULFILLED_PROMISE',
        'severity': 'error',
        'sentence': stripped,
        'suggestion': (
            'This sentence names a subject (story, tale, history, legacy) '
            'without delivering a concrete, on-topic payload (date, name, fact) '
            f'in itself or the next {_R10_LOOKAHEAD} sentences. '
            'Either follow up with specifics or delete the sentence.'
        ),
        'lookahead': _R10_LOOKAHEAD,
    }


def apply_r10_deletions(paragraph: str, next_paragraph: str = '') -> str:
    """Apply R10 deletions to a paragraph.

    Checks each sentence for unfulfilled promises, considering the full
    context window (this paragraph + start of next paragraph for look-ahead).

    Returns the paragraph with unfulfilled-promise sentences removed.
    Empty string if all sentences are deleted.

    Behind DISABLE_R10_DELETION=1 env var — caller checks this.
    """
    if not paragraph or not paragraph.strip():
        return paragraph

    sentences = _split_sentences(paragraph)
    if not sentences:
        return paragraph

    # Build extended context: this paragraph's sentences + next paragraph's
    # first few sentences (for look-ahead across paragraph boundaries)
    next_sentences = []
    if next_paragraph and next_paragraph.strip():
        next_sentences = _split_sentences(next_paragraph)

    all_sentences = sentences + next_sentences

    kept = []
    for i, sentence in enumerate(sentences):
        if len(sentence) < 15:
            kept.append(sentence)
            continue
        # Navigation sentences are never deleted
        if _is_style_navigation_sentence(sentence):
            kept.append(sentence)
            continue
        finding = check_r10_unfulfilled_promise(all_sentences, i)
        if finding is None:
            kept.append(sentence)
        # else: sentence is an unfulfilled promise — drop it

    if not kept:
        return ''  # All sentences deleted — caller removes the paragraph

    # Fix dangling connective on the new first sentence
    result_text = ' '.join(kept)
    for pat in _DANGLING_CONNECTIVE_COMPILED:
        new_text = pat.sub('', result_text, count=1)
        if new_text != result_text:
            new_text = new_text.strip()
            if new_text and new_text[0].islower():
                new_text = new_text[0].upper() + new_text[1:]
            result_text = new_text
            break

    return result_text.strip()


def apply_r10_to_description(description: str) -> Tuple[str, int, int]:
    """Apply R10 deletions to a full stop description (multiple paragraphs).

    Returns:
        (new_description, sentences_deleted, paragraphs_emptied)

    Behind DISABLE_R10_DELETION=1 — caller must check.
    """
    if not description or not description.strip():
        return description, 0, 0

    paragraphs = [p for p in description.split('\n\n') if p.strip()]
    if not paragraphs:
        return description, 0, 0

    new_paragraphs = []
    total_deleted = 0
    paragraphs_emptied = 0

    for pi, para in enumerate(paragraphs):
        para = para.strip()
        if len(para) <= 30:
            new_paragraphs.append(para)
            continue

        # Get next paragraph for cross-boundary look-ahead
        next_para = paragraphs[pi + 1] if pi + 1 < len(paragraphs) else ''

        sentences_before = _split_sentences(para)
        result = apply_r10_deletions(para, next_para)

        if not result:
            paragraphs_emptied += 1
            total_deleted += len([s for s in sentences_before if len(s) >= 15])
        else:
            sentences_after = _split_sentences(result)
            deleted_count = (
                len([s for s in sentences_before if len(s) >= 15]) -
                len([s for s in sentences_after if len(s) >= 15])
            )
            total_deleted += max(0, deleted_count)
            new_paragraphs.append(result)

    new_description = '\n\n'.join(new_paragraphs)
    return new_description, total_deleted, paragraphs_emptied


# ═══════════════════════════════════════════════════════════════════════════════
# PARAGRAPH-LEVEL ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

def validate_paragraph(paragraph: str) -> Dict:
    """Validate a single paragraph against R1–R4, R7, R8.

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
        # LOCAL-233: Even navigation paragraphs need clause-level analysis.
        # "Pedal along the coastline, envisioning..." — the route-movement clause
        # is exempt, but the suggestive tail is NOT. Check tails ONLY.
        #
        # IMPORTANT: Do NOT apply full R1 to sentences within a navigation
        # paragraph. The paragraph-level exemption covers them. "Take the
        # second exit" in a navigation paragraph is exempt even if the
        # sentence-level heuristic doesn't individually classify it as nav.
        # Only suggestive tails lose their exemption.
        sentences = _split_sentences(paragraph)
        tail_findings = []
        for sentence in sentences:
            if len(sentence) < 10:
                continue
            # Check for suggestive tails on ALL sentences in a nav paragraph
            tail_findings.extend(_check_nav_sentence_suggestive_tail(sentence))
        if tail_findings:
            rules_violated = set(f['rule_id'] for f in tail_findings)
            return {
                'is_navigation': True,
                'findings': tail_findings,
                'rules_violated': rules_violated,
            }
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
        # LOCAL-233: Still check the suggestive tail of navigation sentences
        if _is_style_navigation_sentence(sentence):
            all_findings.extend(_check_nav_sentence_suggestive_tail(sentence))
            continue

        all_findings.extend(check_r1_imperatives(sentence))
        all_findings.extend(check_r2_questions(sentence))
        all_findings.extend(check_r3_suggestive_exploration(sentence))
        all_findings.extend(check_r4_prescribed_feeling(sentence))
        all_findings.extend(check_r7_hallucinated_sensory(sentence))
        all_findings.extend(check_r8_prompt_leakage(sentence))
        all_findings.extend(check_r9_generic(sentence))

    # LEAD fixup on merge: R10 was implemented and never called from here.
    # It fires on 8 of 12 sentences in tour 180's Eze paragraph — exactly
    # Michael's complaints — but validate_paragraph reported none, because the
    # rule needs the whole sentence list (it looks for delivery in neighbours)
    # and the loop above passes one sentence at a time.
    for _i in range(len(sentences)):
        _f = check_r10_unfulfilled_promise(sentences, _i)
        if _f:
            all_findings.append(_f)

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
        'R8_PROMPT_LEAKAGE': 0,
        'R9_GENERIC': 0,
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
        'R8_PROMPT_LEAKAGE': 0,
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
        lines.append(f"    R8 (prompt leakage):        {t['R8_PROMPT_LEAKAGE']}")

        # Accumulate grand totals
        for k in grand_totals:
            if k == 'failing_paragraphs':
                grand_totals[k] += failing
            elif k in t:
                grand_totals[k] += t[k]

        # Show up to 3 examples per rule per tour
        examples_shown = {'R1_IMPERATIVE': 0, 'R2_QUESTION': 0,
                          'R3_SUGGESTIVE_EXPLORATION': 0, 'R4_PRESCRIBED_FEELING': 0,
                          'R7_HALLUCINATED_SENSORY': 0, 'R8_PROMPT_LEAKAGE': 0}
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
    lines.append(f"    R8 (prompt leakage):         {gt['R8_PROMPT_LEAKAGE']}")

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
