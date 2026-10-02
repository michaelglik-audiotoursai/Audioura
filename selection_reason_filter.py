"""selection_reason_filter.py — LOCAL-329: Filter and persist selection-stage reasons.

When Phase 3A returns a "reason" field for a restaurant/landmark candidate,
this module:
  1. Tests whether the reason carries substance (a specific fact) vs. hollow
     ranking mentions ("appears in top lists", "popular among visitors").
  2. Persists substantive reasons in stop_corpus as selection-stage leads
     with source attribution marking them as LLM-reported (not verified facts).

A reason "has substance" if it contains at least one of:
  - A year (founding, renovation, chef tenure)
  - A named person (chef, founder, owner, family name)
  - A named dish or ingredient
  - A documented tradition or technique (wood-fired, family recipe, etc.)
  - An architectural or historical detail (e.g. "17th-century vaulted cellar")
  - A price or price range

A reason is HOLLOW if it only says:
  - "Popular", "well-known", "top-ranked", "highly rated"
  - "Appears frequently in restaurant rankings"
  - "Known for its quality offerings"
  - "Recommended by many visitors"
  - Any sentence whose only content is a ranking/popularity claim

The purpose: we select on DOCUMENTEDNESS — venues that people write about
because they have a story. A venue that exists but nobody writes about yields
a THIN stop no matter how well we search afterwards.
"""

import json
import logging
import os
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── Substance detection ─────────────────────────────────────────────────────

_YEAR_RE = re.compile(r'\b(1[4-9]\d{2}|20[0-2]\d)\b')
_PRICE_RE = re.compile(r'[€$£]\s*\d+|\d+\s*(?:euros?|EUR|dollars?|pounds?)', re.I)

# Named dishes or food items (generic enough for any cuisine)
_DISH_SIGNALS = re.compile(
    r'\b('
    # French/Niçoise
    r'socca|pissaladi[eè]re|ratatouille|daube|bouillabaisse|salade ni[cç]oise|'
    r'tapenade|pan bagnat|farcis|gnocchi|ravioli|aioli|brandade|'
    r'foie gras|confit|tartare|carpaccio|risotto|cassoulet|'
    r'boudin|p[aâ]t[eé]|cr[oô][uû]te|pastilla|moules|'
    # Generic food terms that indicate specific dishes
    r'pasta|pizza|sushi|ramen|dim sum|tapas|paella|'
    r'tagine|couscous|curry|naan|dumpling|'
    # Technique/tradition indicators
    r'wood.fired|charcoal.grill|hand.?made|home.?made|'
    r'family recipe|traditional recipe|secret recipe|'
    r'ferment|smoke[d]?|aged|cured|'
    # Menu terms
    r'tasting menu|prix fixe|set menu|omakase|'
    r'michelin star|gault.?millau|bib gourmand'
    r')\b', re.I
)

# Person-name patterns: capitalized words near chef/owner/founder verbs
_PERSON_NEAR_ROLE_RE = re.compile(
    r'\b(?:chef|owner|founder|patron|propri[eé]taire|family|generation)\s+'
    r'[A-Z\u00C0-\u017F][a-z\u00E0-\u017F]{2,}',
    re.UNICODE
)

# Named family / person in possessive or biographical context
_NAMED_PERSON_RE = re.compile(
    r'[A-Z\u00C0-\u017F][a-z\u00E0-\u017F]{2,}\s+[A-Z\u00C0-\u017F][a-z\u00E0-\u017F]{2,}',
    re.UNICODE
)

# Tradition/technique/historical markers
_TRADITION_RE = re.compile(
    r'\b('
    r'since\s+\d{4}|founded\s+(?:in\s+)?\d{4}|opened\s+(?:in\s+)?\d{4}|'
    r'established\s+(?:in\s+)?\d{4}|dating\s+(?:back\s+)?(?:to|from)\s+|'
    r'century|medieval|historic|heritage|'
    r'generation|ancestor|grandfather|grandmother|'
    r'vaulted|cellar|terrace|courtyard|garden|'
    r'local\s+produce|seasonal\s+menu|farm.to.table|'
    r'natural\s+wine|organic|biodynamic'
    r')\b', re.I
)

# ─── Hollow-reason detection ─────────────────────────────────────────────────

_HOLLOW_PHRASES = [
    'popular among', 'popular with', 'popular for',
    'well-known for its quality', 'well-known for its offerings',
    'known for its quality', 'known for quality',
    'top-ranked', 'top ranked', 'highly ranked',
    'appears frequently in', 'appears in many', 'appears on many',
    'frequently recommended', 'often recommended', 'often cited',
    'featured in many', 'featured on many',
    'one of the best', 'one of the top', 'one of the most popular',
    'consistently receives', 'consistently rated',
    'highly rated', 'high ratings', 'excellent ratings',
    'great reviews', 'excellent reviews', 'positive reviews',
    'attracts visitors', 'attracts tourists', 'draws visitors',
    'beloved by locals', 'favorite among locals',
    'a must-visit', 'must visit', 'must-try',
    'widely regarded', 'widely considered',
    'earned a reputation', 'has a reputation',
    'known for its ambiance', 'known for its atmosphere',
    'known for its charm', 'known for its setting',
    'praised for its', 'lauded for its',
    'earning high marks', 'receiving high marks',
]

_HOLLOW_PATTERNS = [
    re.compile(r'\b(?:popular|famous|renowned|celebrated)\s+(?:for|among|with)\s+(?:its|the|their)\s+(?:quality|cuisine|food|service|atmosphere|ambiance|setting)\b', re.I),
    re.compile(r'\b(?:regularly|consistently|frequently)\s+(?:appears?|features?|ranks?)\s+(?:in|on|among)\s+(?:top|best|popular)\b', re.I),
    re.compile(r'\b(?:top|best)\s+\d+\s+(?:restaurants?|places?|spots?)\b', re.I),
]


def _is_hollow(reason: str) -> bool:
    """Return True if the reason is a hollow ranking/popularity mention.

    A hollow reason contains ONLY vague praise with no specific fact.
    If a reason mixes a hollow phrase with a specific fact, it's NOT hollow.
    """
    reason_lower = reason.lower().strip()

    # Check for hollow phrases
    has_hollow = any(phrase in reason_lower for phrase in _HOLLOW_PHRASES)
    if not has_hollow:
        has_hollow = any(p.search(reason) for p in _HOLLOW_PATTERNS)

    if not has_hollow:
        return False  # No hollow signal at all — pass through

    # The reason has hollow language. But does it ALSO have substance?
    # If it does, the substance saves it (e.g., "Popular for its socca, a chickpea
    # pancake they've made since 1927" — has hollow "popular for" but also year + dish).
    has_substance = (
        bool(_YEAR_RE.search(reason))
        or bool(_PRICE_RE.search(reason))
        or bool(_DISH_SIGNALS.search(reason))
        or bool(_PERSON_NEAR_ROLE_RE.search(reason))
        or bool(_TRADITION_RE.search(reason))
    )

    if has_substance:
        return False  # Substance overrides hollow language

    return True  # Only hollow language, no substance


def reason_has_substance(reason: str) -> bool:
    """Return True if a selection reason carries specific, verifiable content.

    This is the primary API: called from generate_tour_text.py during Phase 3A
    candidate parsing. Returns False for hollow reasons (ranking-only mentions).
    """
    if not reason or len(reason.strip()) < 10:
        return False

    # First: reject if purely hollow
    if _is_hollow(reason):
        return False

    # Second: require at least one substance signal
    # (catches the case where a reason is neither hollow nor substantive —
    # e.g. "A nice restaurant in the old town" — no ranking claim but also no fact)
    has_any_substance = (
        bool(_YEAR_RE.search(reason))
        or bool(_PRICE_RE.search(reason))
        or bool(_DISH_SIGNALS.search(reason))
        or bool(_PERSON_NEAR_ROLE_RE.search(reason))
        or bool(_TRADITION_RE.search(reason))
        or bool(_NAMED_PERSON_RE.search(reason))
    )

    return has_any_substance


# ─── Corpus persistence ──────────────────────────────────────────────────────

def persist_selection_reasons(
    selection_reasons: Dict[str, str],
    surviving_names: List[str],
    venue_name: str,
) -> int:
    """Persist selection-stage reasons in stop_corpus for surviving stops.

    Only persists reasons for stops that survived all gates.
    Stores as a passage with source attribution marking it as an LLM-reported lead.
    Returns count of reasons persisted.

    Does NOT overwrite existing corpus — if a stop already has passages,
    the selection reason is added only if the stop has no existing corpus.
    """
    if not selection_reasons:
        return 0

    persisted = 0
    try:
        import psycopg2
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            db_host = os.environ.get('DB_HOST', 'localhost')
            db_port = os.environ.get('DB_PORT', '5432')
            db_name = os.environ.get('DB_NAME', 'audiotours')
            db_user = os.environ.get('DB_USER', 'admin')
            db_password = os.environ.get('DB_PASSWORD', 'password123')
            db_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

        conn = psycopg2.connect(db_url, connect_timeout=5)
        cur = conn.cursor()

        for stop_name in surviving_names:
            reason = selection_reasons.get(stop_name.lower())
            if not reason:
                continue

            # Check if stop already has corpus — don't overwrite richer data
            cur.execute(
                "SELECT passage_count FROM stop_corpus WHERE venue_name = %s AND stop_title = %s",
                (venue_name, stop_name)
            )
            existing = cur.fetchone()
            if existing and existing[0] > 0:
                logger.debug(f"  [LOCAL-329] {stop_name}: already has {existing[0]} passage(s), skipping reason")
                continue

            # Build the passage and source metadata
            passage_obj = {
                "text": reason,
                "source_type": "selection_reason",
                "verified": False,  # Leads, not claims
            }
            source_obj = {
                "url": "llm:phase3a-selection",
                "tier": 3,
                "type": "selection_reason",
                "title": f"{stop_name} — selection-stage notability reason",
                "tier_reason": "LLM-reported at selection time (lead, not verified fact)",
            }

            passages_json = json.dumps([passage_obj])
            sources_json = json.dumps([source_obj])

            if existing is not None:
                # Row exists but has 0 passages — update it
                cur.execute(
                    """UPDATE stop_corpus
                       SET passages_json = %s, source_pages = %s, passage_count = 1
                       WHERE venue_name = %s AND stop_title = %s""",
                    (passages_json, sources_json, venue_name, stop_name)
                )
            else:
                # Insert new row
                cur.execute(
                    """INSERT INTO stop_corpus (venue_name, stop_title, passages_json, source_pages, passage_count)
                       VALUES (%s, %s, %s, %s, 1)""",
                    (venue_name, stop_name, passages_json, sources_json)
                )
            persisted += 1

        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        logger.warning(f"[LOCAL-329] Failed to persist selection reasons: {e}")
        print(f"  [LOCAL-329] Persistence error (non-fatal): {e}")

    return persisted
