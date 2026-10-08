"""
practical_facts_gate.py — QA gate for practical visitor information.
====================================================================
LOCAL-36: Verifies provenance of every practical claim (opening hours,
closing days, admission price, address, accessibility) before it ships.

Design principle: PROVENANCE, NOT PLAUSIBILITY.
For each practical claim the pipeline must answer: "which fetched source
says this?" If it cannot, the claim is DROPPED — silence is correct;
a plausible guess is not.

This module:
1. Extracts practical claims from tour text (Museum Information, hours, prices)
2. Verifies each claim against the fetched source content
3. Drops unverifiable claims
4. Produces a per-claim audit log: fact | value | source | verified
"""
import re
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PracticalClaim:
    """A single practical claim extracted from tour text."""
    claim_type: str          # 'hours', 'closed_day', 'admission', 'address', 'accessibility'
    value: str               # The verbatim claim text (e.g., "10am to 6pm")
    source_url: str = ""     # URL the claim was fetched from
    source_text: str = ""    # The fetched source content that should back the claim
    verified: bool = False   # Whether source_text actually supports the claim
    audit_line: str = ""     # Generated audit log line


@dataclass
class PracticalFactsResult:
    """Result of running the practical facts gate on a tour."""
    claims: List[PracticalClaim] = field(default_factory=list)
    passed: bool = True
    dropped_claims: List[PracticalClaim] = field(default_factory=list)
    verified_claims: List[PracticalClaim] = field(default_factory=list)
    audit_log: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Claim extraction from tour text
# ---------------------------------------------------------------------------

# Patterns for practical claim types
_HOURS_PATTERN = re.compile(
    r'(?:open|hours?|ouvert|ouverture)'
    r'[^.]{0,80}'
    r'(?:\d{1,2}(?::\d{2})?\s*(?:am|pm|h)?\s*[-–to,]+\s*\d{1,2}(?::\d{2})?\s*(?:am|pm|h)?)',
    re.IGNORECASE
)

# [LOCAL-353] 24h colon format: "12:00-13:45" without am/pm/h suffix
_HOURS_24H_PATTERN = re.compile(
    r'(?:open|monday|tuesday|wednesday|thursday|friday|saturday|sunday|'
    r'mo|tu|we|th|fr|sa|su)'
    r'[^.]{0,80}'
    r'\d{1,2}:\d{2}\s*[-–,]\s*\d{1,2}:\d{2}',
    re.IGNORECASE
)

# [LOCAL-353] Payment patterns for dining stops
_PAYMENT_PATTERN = re.compile(
    r'(?:cash\s+only|card\s+(?:payments?\s+)?only|no\s+credit\s+cards?|'
    r'accepts?\s+(?:only\s+)?cash)',
    re.IGNORECASE
)

# [LOCAL-353] Reservation patterns for dining stops
_RESERVATION_PATTERN = re.compile(
    r'(?:reservations?\s+(?:required|recommended|accepted|not\s+(?:needed|required))|'
    r'no\s+reservations?)',
    re.IGNORECASE
)

_CLOSED_DAY_PATTERN = re.compile(
    r'(?:'
    r'closed?\s+(?:on\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?|'
    r'ferm[eé]\s+(?:le\s+)?(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)|'
    r'(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)(?:\s*[-–]\s*(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))?\s+off'
    r')',
    re.IGNORECASE
)

_ADMISSION_PATTERN = re.compile(
    r'(?:'
    r'(?:free\s+)?admission(?:\s+(?:free|required|charged?))?|'
    r'entr[eé]e\s+(?:libre|gratuite)|'
    r'(?:admission|entry|ticket)\s*[:.]?\s*(?:€|\$|£)?\s*\d+|'
    r'(?:€|\$|£)\s*\d+(?:\.\d{2})?(?:\s*(?:per\s+person|adult|full\s+(?:price|rate)))?|'
    r'\d+\s*(?:€|EUR|dollars?)'
    r')',
    re.IGNORECASE
)

# [LOCAL-354] Price band pattern: "An average dinner or lunch would cost under €50"
_PRICE_BAND_PATTERN = re.compile(
    r'(?:average\s+)?(?:dinner|lunch|meal)\s+(?:or\s+(?:dinner|lunch)\s+)?'
    r'(?:would\s+)?cost\s+(?:under|less\s+than|about|around)\s*€\s*\d+',
    re.IGNORECASE
)

_OPEN_DAILY_PATTERN = re.compile(
    r'open\s+daily|ouvert\s+tous\s+les\s+jours',
    re.IGNORECASE
)


def extract_practical_claims(tour_text: str) -> List[PracticalClaim]:
    """Extract all practical claims from a tour text.

    Looks at:
    - Museum Information: lines
    - Operational Details: lines
    - Any embedded hours/admission in orientation blocks

    Returns a list of PracticalClaim objects (without source verification yet).
    """
    claims = []

    # 1. Museum Information line (primary location for practical facts)
    museum_info_match = re.search(
        r'^Museum Information:\s*(.+)$', tour_text, re.MULTILINE
    )
    if museum_info_match:
        info_text = museum_info_match.group(1).strip()
        claims.extend(_parse_info_text_into_claims(info_text))

    # 2. Operational Details lines (alternative format)
    for match in re.finditer(
        r'^Operational Details?:\s*(.+)$', tour_text, re.MULTILINE
    ):
        info_text = match.group(1).strip()
        claims.extend(_parse_info_text_into_claims(info_text))

    return claims


def _parse_info_text_into_claims(info_text: str) -> List[PracticalClaim]:
    """Parse a Museum Information or Operational Details line into individual claims."""
    claims = []

    # Split by sentence-like boundaries. [LOCAL-625] A dot BETWEEN two digits is a
    # European clock separator ("10.00"), NOT a sentence end — splitting there turned
    # "10.00-18.00" into "10", "00-18", "00" and leaked a bare "00-18" as hours.
    # Require the '.' separator to be followed by whitespace (a real sentence break);
    # ';' always separates. This keeps dotted clock tokens intact.
    sentences = re.split(r'(?<!\d)\.\s+|\.\s*(?!\d)|;\s*', info_text)

    for sentence in sentences:
        if sentence is None:
            continue
        sentence = sentence.strip()
        if not sentence:
            continue

        # Classify and add claims
        if _CLOSED_DAY_PATTERN.search(sentence):
            claims.append(PracticalClaim(
                claim_type='closed_day',
                value=sentence,
            ))
        elif _HOURS_PATTERN.search(sentence) or _OPEN_DAILY_PATTERN.search(sentence):
            claims.append(PracticalClaim(
                claim_type='hours',
                value=sentence,
            ))
        # [LOCAL-353] 24h colon format: "Monday-Friday 12:00-13:45, 19:00-21:00"
        elif _HOURS_24H_PATTERN.search(sentence):
            claims.append(PracticalClaim(
                claim_type='hours',
                value=sentence,
            ))
        # [LOCAL-354] Price band claims: "An average dinner or lunch would cost under €50"
        elif _PRICE_BAND_PATTERN.search(sentence):
            claims.append(PracticalClaim(
                claim_type='price_band',
                value=sentence,
            ))
        elif _ADMISSION_PATTERN.search(sentence):
            claims.append(PracticalClaim(
                claim_type='admission',
                value=sentence,
            ))
        # [LOCAL-353] Payment claims (cash only, etc.)
        elif _PAYMENT_PATTERN.search(sentence):
            claims.append(PracticalClaim(
                claim_type='payment',
                value=sentence,
            ))
        # [LOCAL-353] Reservation claims
        elif _RESERVATION_PATTERN.search(sentence):
            claims.append(PracticalClaim(
                claim_type='reservation',
                value=sentence,
            ))
        elif re.search(r'(?:free|gratuit)', sentence, re.IGNORECASE):
            # Catch "Free" as admission claim
            claims.append(PracticalClaim(
                claim_type='admission',
                value=sentence,
            ))
        # If a sentence contains hours-like text but wasn't caught above
        elif re.search(r'\d{1,2}(?:am|pm|h)', sentence, re.IGNORECASE):
            claims.append(PracticalClaim(
                claim_type='hours',
                value=sentence,
            ))
        # [LOCAL-353] 24h colon times as standalone (e.g. "12:00-21:00")
        elif re.search(r'\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}', sentence):
            claims.append(PracticalClaim(
                claim_type='hours',
                value=sentence,
            ))

    return claims


# ---------------------------------------------------------------------------
# Source verification
# ---------------------------------------------------------------------------

def verify_claim_against_source(claim: PracticalClaim, source_text: str) -> bool:
    """Verify that a practical claim is actually supported by the source text.

    This is NOT plausibility checking. We verify that the specific factual
    content in the claim can be traced to text in the fetched source.

    Returns True if the claim is supported; False if it cannot be verified.
    """
    if not source_text or not claim.value:
        return False

    source_lower = source_text.lower()
    claim_lower = claim.value.lower()

    if claim.claim_type == 'closed_day':
        return _verify_closed_day(claim_lower, source_lower)
    elif claim.claim_type == 'hours':
        return _verify_hours(claim_lower, source_lower)
    elif claim.claim_type == 'admission':
        return _verify_admission(claim_lower, source_lower)
    elif claim.claim_type == 'payment':
        return _verify_payment(claim_lower, source_lower)
    elif claim.claim_type == 'reservation':
        return _verify_reservation(claim_lower, source_lower)
    # [LOCAL-354] Price band verification
    elif claim.claim_type == 'price_band':
        return _verify_price_band(claim_lower, source_lower)
    else:
        # Unknown claim type — cannot verify
        return False


def _verify_closed_day(claim_lower: str, source_lower: str) -> bool:
    """Verify a closing day claim against the source."""
    # Extract the day from the claim
    day_match = re.search(
        r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday|'
        r'lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)',
        claim_lower
    )
    if not day_match:
        return False

    day = day_match.group(1)

    # Map English to French equivalents for cross-language verification
    _day_map = {
        'monday': 'lundi', 'tuesday': 'mardi', 'wednesday': 'mercredi',
        'thursday': 'jeudi', 'friday': 'vendredi', 'saturday': 'samedi',
        'sunday': 'dimanche',
        'lundi': 'monday', 'mardi': 'tuesday', 'mercredi': 'wednesday',
        'jeudi': 'thursday', 'vendredi': 'friday', 'samedi': 'saturday',
        'dimanche': 'sunday',
    }

    # [LOCAL-353] Map full day names to OSM abbreviations
    _day_to_abbr = {
        'monday': 'mo', 'tuesday': 'tu', 'wednesday': 'we',
        'thursday': 'th', 'friday': 'fr', 'saturday': 'sa', 'sunday': 'su',
    }

    # The source must mention the same day in a closure context
    _other_lang = _day_map.get(day, '')
    _day_abbr = _day_to_abbr.get(day, '')

    # Check if source mentions this day + closed/fermé/off
    _closure_indicators = ['ferm', 'closed', 'closure', 'relâche', 'repos', 'except', 'off']
    for indicator in _closure_indicators:
        if indicator in source_lower:
            # The source mentions closure — check if same day is referenced nearby
            # Find all closure-indicator positions
            for m in re.finditer(re.escape(indicator), source_lower):
                _window = source_lower[max(0, m.start()-100):m.end()+100]
                if day in _window or _other_lang in _window:
                    return True
                # [LOCAL-353] Also check OSM abbreviation (e.g., "sa-su off")
                # Must be word-bounded to avoid matching inside words (e.g. "mo" in "moins")
                if _day_abbr and re.search(rf'(?<![a-z]){_day_abbr}(?![a-z])', _window):
                    return True

    return False


def _verify_hours(claim_lower: str, source_lower: str) -> bool:
    """Verify an opening hours claim against the source.

    Extracts the numeric times from the claim and checks if the source
    contains the same numbers in an hours context. Uses word-boundary matching
    to prevent partial number matches (e.g., "8" matching inside "18h").
    """
    # Extract times from the claim (e.g., "10am", "6pm", "10h", "17h")
    _times = re.findall(r'\d{1,2}(?::\d{2})?\s*(?:am|pm|h\d{0,2})', claim_lower)

    # [LOCAL-353] Also extract 24h colon format times (e.g., "12:00", "19:00")
    _times_24h = re.findall(r'\d{1,2}:\d{2}', claim_lower)

    # [LOCAL-584 r2] "Noon"/"Midnight" are page-literal time words (e.g. the Griffin
    # Museum's "Noon to 4 PM"). Treat them as time tokens that must appear in source.
    _time_words = [w for w in ('noon', 'midnight') if w in claim_lower]

    if not _times and not _times_24h and not _time_words:
        # Try "open daily" type claims
        if 'daily' in claim_lower or 'tous les jours' in claim_lower:
            return ('daily' in source_lower or 'tous les jours' in source_lower
                    or 'every day' in source_lower or 'chaque jour' in source_lower)
        return False

    # At least one time value from the claim must appear in the source
    verified_count = 0

    # Noon/Midnight words: must appear verbatim in the source.
    for _w in _time_words:
        if _w in source_lower:
            verified_count += 1

    # Check am/pm/h format times
    for time_str in _times:
        # Normalize: "10am" -> check for "10" near am/h/open context
        _num = re.search(r'\d{1,2}', time_str)
        if _num:
            num_val = _num.group()
            # Use word-boundary to prevent "8" matching inside "18h"
            # Match: standalone number followed by hour indicator
            _hour_contexts = re.findall(
                rf'(?<!\d){num_val}\s*(?:h\d{{0,2}}|:\d{{2}}|am|pm|heures?)',
                source_lower
            )
            if _hour_contexts:
                verified_count += 1

    # [LOCAL-353] Check 24h colon format times (e.g., "12:00" in source)
    for time_str in _times_24h:
        if time_str in source_lower:
            verified_count += 1

    # Require at least one time value to be verified
    return verified_count >= 1


def _verify_admission(claim_lower: str, source_lower: str) -> bool:
    """Verify an admission/pricing claim against the source.

    For 'free' claims: source must say free/gratuit/libre.
    For priced claims: source must contain a matching price.
    For 'admission fee required': must find a specific price in source.
    """
    # "Free" claims
    if re.search(r'\bfree\b|gratuit|libre', claim_lower):
        # Source must say free/gratuit/libre OR use OSM fee=no tag format...
        _has_free = bool(re.search(r'gratuit|libre|free|fee\s*=\s*no', source_lower))
        if not _has_free:
            return False
        # ...BUT if the source also contains a specific GENERAL ENTRY price,
        # an unconditional "free" claim is suspicious. The source likely has
        # conditional free (e.g., "free for residents") alongside a paid entry.
        # Only reject if the claim itself is PURELY "free" without a condition.
        _claim_is_unconditional_free = bool(
            re.search(r'^(?:free\s*(?:admission|entry)?|admission\s*free|gratuit|entr[eé]e\s*(?:gratuite|libre))$',
                      claim_lower.strip())
        )
        if _claim_is_unconditional_free:
            # Check if source contains a GENERAL ENTRY price (not guided tour/workshop prices).
            # Indicators of general entry: "tarif normal/plein/unique", "entrée unique",
            # "individual", "Musée X – €N", single ticket markers.
            # We must NOT flag prices for workshops, guided tours, groups, etc.
            _source_has_general_entry_price = bool(re.search(
                r'(?:tarif\s+(?:normal|plein|unique)|entr[eé]e\s+unique|'
                r'mus[eé]e\s+\w+\s*[-–:]\s*\d+\s*€|'
                r'mus[eé]e\s+\w+\s*[-–:]\s*€\s*\d+|'
                r'individual\w*\s+[-–:€\d])',
                source_lower
            ))
            if _source_has_general_entry_price:
                return False
        return True

    # "Admission fee required" — vague, must be backed by a specific price
    if 'fee required' in claim_lower or 'charged' in claim_lower:
        # Source must contain a specific price to back this
        return bool(re.search(r'(?:€|\$|£)\s*\d+|\d+\s*(?:€|EUR|dollars?)', source_lower))

    # Specific price claims — the price number must be in the source
    _prices = re.findall(r'(?:€|\$|£)\s*(\d+(?:\.\d{2})?)|(\d+(?:\.\d{2})?)\s*(?:€|EUR)', claim_lower)
    if _prices:
        for price_tuple in _prices:
            price = price_tuple[0] or price_tuple[1]
            if price and price in source_lower:
                return True
        return False

    return False


# [LOCAL-353] Payment verification
def _verify_payment(claim_lower: str, source_lower: str) -> bool:
    """Verify a payment claim against the source.

    'Cash only' verifies if source contains payment:cash = yes AND
    payment:credit_cards = no (or similar evidence of card rejection).
    """
    if 'cash only' in claim_lower or 'cash' in claim_lower:
        # Source must have evidence of cash-only: payment:cash + no cards
        has_cash_yes = ('payment:cash = yes' in source_lower or
                        'cash = yes' in source_lower or
                        'espèces' in source_lower)
        has_no_cards = ('credit_cards = no' in source_lower or
                        'debit_cards = no' in source_lower or
                        'no credit' in source_lower or
                        'pas de carte' in source_lower)
        return has_cash_yes and has_no_cards

    if 'card' in claim_lower and 'only' in claim_lower:
        # Card only: source must show cash = no
        return 'payment:cash = no' in source_lower or 'cash = no' in source_lower

    return False


# [LOCAL-353] Reservation verification
def _verify_reservation(claim_lower: str, source_lower: str) -> bool:
    """Verify a reservation claim against the source.

    Checks if the source contains a matching reservation tag value.
    """
    if 'required' in claim_lower:
        return 'reservation = required' in source_lower or 'reservation=required' in source_lower
    if 'recommended' in claim_lower:
        return 'reservation = recommended' in source_lower or 'reservation=recommended' in source_lower
    if 'accepted' in claim_lower:
        return ('reservation = yes' in source_lower or 'reservation=yes' in source_lower or
                'reservation = accepted' in source_lower)
    if 'no reservation' in claim_lower:
        return 'reservation = no' in source_lower or 'reservation=no' in source_lower

    return False


# [LOCAL-354] Price band verification
def _verify_price_band(claim_lower: str, source_lower: str) -> bool:
    """Verify a price band claim against the guide source text.

    The claim says "cost under €X". The source must contain:
    1. A guide name (Le Fooding, Gault&Millau, Michelin)
    2. A price range whose high end is BELOW the claimed threshold
    3. The word "threshold" with the claimed amount (from our source_text_for_gate)

    This prevents fabricated price claims from passing.
    """
    # Extract the threshold from the claim: "under €50" → 50
    threshold_match = re.search(r'under\s*€\s*(\d+)', claim_lower)
    if not threshold_match:
        return False
    claimed_threshold = int(threshold_match.group(1))

    # Source must identify itself as a guide
    has_guide_provenance = any(
        guide in source_lower
        for guide in ('le fooding', 'gault&millau', 'gault millau', 'michelin')
    )
    if not has_guide_provenance:
        return False

    # Source must contain a price range with numbers
    # Look for "range: €X-Y" or "X to Y" or "€X-Y"
    range_match = re.search(
        r'(?:range|price|carte|indicative)[^€\d]{0,30}€?\s*(\d+)\s*[-–to]+\s*€?\s*(\d+)',
        source_lower
    )
    if not range_match:
        return False

    source_high = float(range_match.group(2))

    # The claimed threshold must be ABOVE the source's high end
    # (conservative: "under €50" is valid if guide says high=43)
    if claimed_threshold <= source_high:
        return False

    # Source must explicitly state this threshold
    # (prevents someone from claiming "under €100" for a €43 restaurant)
    threshold_in_source = f"threshold: under €{claimed_threshold}" in source_lower
    if not threshold_in_source:
        return False

    return True


# ---------------------------------------------------------------------------
# [LOCAL-584] ONE literal-token gate for every practical-facts path
# ---------------------------------------------------------------------------
# The LOCAL-91 corpus fallback used to write visitor_facts_extractor.format_en()
# straight onto the Museum Information line with no verification; LOCAL-39 and the
# LOCAL-582 overview went through verify_claim_against_source + a literal-token
# check, but the corpus fallback did not. That is how tour 391 (Griffin Museum,
# Winchester MA) shipped "Museum Information: 08:00–20:00. €12" — a 24h schedule
# and a euro price that appear NOWHERE on a US museum's AM/PM, $-priced page.
#
# claim_tokens_in_source is the shared, tighter literal check (moved here from
# museum_overview so there is exactly ONE copy). gate_formatted_facts runs the
# WHOLE formatted facts string through both verify_claim_against_source AND the
# literal check, dropping — and logging — any segment that is not supported by the
# source. Every path (LOCAL-35/39, LOCAL-91 corpus fallback, the overview) calls
# the same gate.

_DROP_LOG_PREFIX = "[LOCAL-584] dropped unsupported practical fact:"


def claim_tokens_in_source(claim_value: str, source_lower: str) -> bool:
    """Require a practical claim's DISTINCTIVE content to appear literally in source.

    The LOCAL-35 extractor sometimes emits a normalised/synthetic label whose own
    words are not in the page it was extracted from (e.g. a Nice price table rewritten
    as "free for Métropole residents", or a currency the page never used). Every
    distinctive token the claim carries — a day name, a numeric amount, a currency
    symbol, or a condition word like "métropole"/"resident" — must appear verbatim
    (digit / word-stem / symbol) in the source. Generic words ("free"/"admission")
    are not required to be literal, but any CONDITION or amount on them is.
    """
    cl = (claim_value or '').lower()
    cv = source_lower or ''

    # Day names present in the claim must be present in the source.
    for day in ('monday', 'tuesday', 'wednesday', 'thursday', 'friday',
                'saturday', 'sunday'):
        if day in cl and day not in cv:
            return False

    # Any numeric amount in the claim (hours like 10, price like 12) must be
    # present as a number in the source.
    for num in re.findall(r'\d+', cl):
        if num not in cv:
            return False

    # [LOCAL-584] Any currency symbol in the claim must appear in the source. This
    # is the direct guard against "$12"→"€12": a € claim on a $-only page is dropped.
    for sym in ('€', '£', '$', '¥', '₩', '₹', '₽'):
        if sym in (claim_value or '') and sym not in (source_lower or ''):
            return False

    # Condition words the extractor may synthesise — require them literally.
    for cond in ('métropole', 'metropole', 'resident', 'residents', 'member',
                 'students', 'senior', 'child', 'children'):
        if cond in cl and cond not in cv:
            return False

    return True


def _facts_segment_claim(segment: str) -> Optional[PracticalClaim]:
    """Classify ONE formatted-facts segment into a claim, or None if not practical.

    Reuses _parse_info_text_into_claims, then falls back to a bare time-range
    detector so a page-literal span like "8 AM–8 PM" (which the sentence-oriented
    parser skips because of the space before AM) is still treated as an hours claim
    and verified — never passed through unchecked.
    """
    seg = (segment or '').strip().rstrip('.')
    if not seg:
        return None
    parsed = _parse_info_text_into_claims(seg)
    if parsed:
        return parsed[0]
    # Fallback: a bare clock range with AM/PM, 24h, or the words Noon/Midnight,
    # e.g. "8 AM–8 PM", "10:00–18:00", "Noon–4 PM". The sentence parser skips these
    # because of the space before AM/PM or the word "Noon"; we must still verify them.
    _t = r'(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)?|noon|midnight)'
    if re.search(_t + r'\s*[-–—]\s*' + _t, seg, re.IGNORECASE):
        return PracticalClaim(claim_type='hours', value=seg)
    return None


def gate_formatted_facts(
    formatted_info: str,
    source_text: str,
    source_url: str = "",
    log=None,
) -> Tuple[str, List[str]]:
    """[LOCAL-584] The ONE gate. Return (surviving_facts, dropped_segments).

    Splits a visitor_facts_extractor.format_en() string into its segments (top-level
    parts joined by '. ', seasonal hour ranges by '; '), and keeps a segment ONLY if
    it (a) classifies as a practical claim, (b) passes verify_claim_against_source,
    and (c) passes claim_tokens_in_source. Anything else is dropped and logged with
    the standard prefix. The surviving facts are re-joined with '. ' so the output is
    a valid Museum Information value (or '' when nothing survives — silence is correct).
    """
    _log = log if log is not None else logger.warning
    dropped: List[str] = []
    if not formatted_info or not formatted_info.strip():
        return '', dropped
    if not source_text or not source_text.strip():
        # No source to verify against → drop everything (provenance, not plausibility).
        for seg in re.split(r'\.\s+|;\s+', formatted_info):
            seg = seg.strip().rstrip('.')
            if seg:
                dropped.append(seg)
                _log(f"{_DROP_LOG_PREFIX} {seg!r} (no source text to verify against)"
                     + (f" [{source_url}]" if source_url else ""))
        return '', dropped

    source_lower = source_text.lower()
    survivors: List[str] = []
    for seg in re.split(r'\.\s+|;\s+', formatted_info):
        seg = seg.strip().rstrip('.')
        if not seg:
            continue
        claim = _facts_segment_claim(seg)
        reason = ''
        if claim is None:
            reason = 'not a recognised practical claim'
        elif not verify_claim_against_source(claim, source_text):
            reason = 'not supported by source (gate)'
        elif not claim_tokens_in_source(seg, source_lower):
            reason = 'distinctive token (price/day/currency/condition) absent from source'
        if reason:
            dropped.append(seg)
            _log(f"{_DROP_LOG_PREFIX} {seg!r} — {reason}"
                 + (f" [{source_url}]" if source_url else ""))
        else:
            survivors.append(seg)

    return ('. '.join(survivors), dropped)


# ---------------------------------------------------------------------------
# Main gate function
# ---------------------------------------------------------------------------

def run_practical_facts_gate(
    tour_text: str,
    source_url: str = "",
    source_text: str = "",
) -> PracticalFactsResult:
    """Run the practical facts QA gate on a tour.

    Args:
        tour_text: The generated tour text.
        source_url: The URL that visitor info was fetched from.
        source_text: The raw text content fetched from source_url.

    Returns:
        PracticalFactsResult with per-claim verification and audit log.
    """
    result = PracticalFactsResult()

    # Extract claims
    claims = extract_practical_claims(tour_text)
    if not claims:
        # No practical claims present — gate passes trivially
        result.audit_log.append("NO_CLAIMS | (none) | (none) | PASS — no practical claims to verify")
        return result

    # Verify each claim
    for claim in claims:
        claim.source_url = source_url
        claim.source_text = source_text

        if not source_text:
            # No source content available — claim cannot be verified → DROP
            claim.verified = False
            claim.audit_line = (
                f"{claim.claim_type} | {claim.value} | "
                f"{source_url or '(no source)'} | DROPPED — no source content"
            )
            result.dropped_claims.append(claim)
        else:
            # Verify against source
            claim.verified = verify_claim_against_source(claim, source_text)
            if claim.verified:
                claim.audit_line = (
                    f"{claim.claim_type} | {claim.value} | "
                    f"{source_url} | VERIFIED"
                )
                result.verified_claims.append(claim)
            else:
                claim.audit_line = (
                    f"{claim.claim_type} | {claim.value} | "
                    f"{source_url} | DROPPED — not supported by source"
                )
                result.dropped_claims.append(claim)

        result.claims.append(claim)
        result.audit_log.append(claim.audit_line)

    # Gate passes only if ALL claims are verified (or there are no claims)
    result.passed = len(result.dropped_claims) == 0

    return result


# ---------------------------------------------------------------------------
# Tour text rewriter: drop unverified practical claims
# ---------------------------------------------------------------------------

def strip_unverified_claims(
    tour_text: str,
    gate_result: PracticalFactsResult,
) -> str:
    """Remove unverified practical claims from tour text.

    If the gate found dropped claims, this rewrites the Museum Information
    or Operational Details line to contain ONLY verified claims.
    Silence is correct; a plausible guess is not.
    """
    if gate_result.passed:
        return tour_text  # All claims verified — no changes needed

    if not gate_result.dropped_claims:
        return tour_text

    # Build the verified-only info line
    verified_values = [c.value for c in gate_result.verified_claims]

    # Replace Museum Information line
    def _replace_museum_info(match):
        if verified_values:
            return f"Museum Information: {'. '.join(verified_values)}"
        else:
            return ""  # Drop the entire line if nothing verified

    tour_text = re.sub(
        r'^Museum Information:\s*.+$',
        _replace_museum_info,
        tour_text,
        flags=re.MULTILINE,
    )

    # Replace Operational Details line
    def _replace_operational(match):
        if verified_values:
            return f"Operational Details: {'. '.join(verified_values)}"
        else:
            return ""
        
    tour_text = re.sub(
        r'^Operational Details?:\s*.+$',
        _replace_operational,
        tour_text,
        flags=re.MULTILINE,
    )

    # Clean up any resulting blank lines (max 2 consecutive)
    tour_text = re.sub(r'\n{3,}', '\n\n', tour_text)

    return tour_text


# ---------------------------------------------------------------------------
# Integration helper: run gate and fix tour text in one call
# ---------------------------------------------------------------------------

def gate_and_fix(
    tour_text: str,
    source_url: str = "",
    source_text: str = "",
    verbose: bool = True,
) -> Tuple[str, PracticalFactsResult]:
    """Run practical facts gate, strip unverified claims, return fixed text + result.

    This is the primary integration point. Call it after tour generation
    but before delivery.
    """
    result = run_practical_facts_gate(tour_text, source_url, source_text)

    if verbose:
        print(f"\n  [LOCAL-36] Practical Facts Gate:")
        print(f"    Claims found: {len(result.claims)}")
        print(f"    Verified: {len(result.verified_claims)}")
        print(f"    Dropped: {len(result.dropped_claims)}")
        for line in result.audit_log:
            print(f"    AUDIT: {line}")

    fixed_text = strip_unverified_claims(tour_text, result)

    return fixed_text, result


# ---------------------------------------------------------------------------
# [LOCAL-602 r2 / D617 item 10] "check the website" at most once, tour-wide
# ---------------------------------------------------------------------------
#
# Hours and admission are spoken when the venue publishes them (handled upstream
# by the visiting-sentence composers). When a field is NOT published we point the
# listener at the venue's site — but that pointer must appear AT MOST ONCE in the
# whole tour, and only for the genuinely-missing field. On the overview path the
# overview narration and the Stop-1 opening section each carry their own pointer,
# so a 1-stop WNDR overview could say "check the website" twice. This is a
# deterministic post-pass over the ASSEMBLED tour text: keep the FIRST
# website-pointer sentence, drop every later one. It never adds a pointer and
# never removes a sentence that states a real fact.

# A sentence that merely points the listener at the website for hours/admission.
# Each alternative is one of the pipeline's pointer templates; all share the
# "<verb> … <site> … (before you go/visit | are/were listed/not listed)" shape.
_WEBSITE_POINTER_SENT_RE = re.compile(
    r'(?is)(?<![^.\s])'                       # at a sentence start
    r'('
    r'check\s+[^.?!]*?\b(?:website|\.[a-z]{2,})[^.?!]*?before\s+you\s+(?:go|visit)[^.?!]*?[.?!]'
    r'|(?:opening\s+hours?|admission(?:\s+prices?)?)\s+(?:are|were)\s+(?:listed|not\s+listed)[^.?!]*?[.?!]'
    r'|please\s+check\s+[^.?!]*?before\s+you\s+(?:go|visit)[^.?!]*?[.?!]'
    r'|admission\s+prices?\s+were\s+not\s+listed[^.?!]*?[.?!]'
    # [LOCAL-618 #4] The honest "we couldn't read them" line replaces the
    # dead-end "check the website" pointer when the preflight returns none; it
    # too must appear at most once tour-wide.
    r'|opening\s+hours?\s+(?:weren.?t|were\s+not)\s+published[^.?!]*?[.?!]'
    r')'
)


def is_website_pointer_sentence(sentence: str) -> bool:
    """True when ``sentence`` is only a 'check the website for hours/admission'
    pointer (states no concrete hour or price itself)."""
    return bool(_WEBSITE_POINTER_SENT_RE.search((sentence or "").strip()))


def collapse_website_pointers(text: str) -> Tuple[str, int]:
    """Keep the FIRST website-pointer sentence in ``text``; drop every later one.

    Returns ``(cleaned, n_removed)``. Deterministic, pure. A tour that publishes
    hours and admission has no pointer and is returned unchanged (n_removed == 0).
    Only whole pointer SENTENCES are removed — a sentence that also states a real
    fact does not match the pointer templates and is left alone.
    """
    if not text:
        return text or "", 0
    matches = list(_WEBSITE_POINTER_SENT_RE.finditer(text))
    if len(matches) <= 1:
        return text, 0
    # Remove all but the first, back-to-front so indices stay valid.
    out = text
    removed = 0
    for m in matches[:0:-1]:          # every match except matches[0], reversed
        out = out[:m.start()] + out[m.end():]
        removed += 1
    # Tidy the double spaces / blank lines a removal can leave behind.
    out = re.sub(r'[ \t]{2,}', ' ', out)
    out = re.sub(r'[ \t]+\n', '\n', out)
    out = re.sub(r'\n{3,}', '\n\n', out)
    return out, removed


# ---------------------------------------------------------------------------
# [LOCAL-627 defect 2] Collapse a RAW spoken fare table to one clean sentence
# ---------------------------------------------------------------------------
#
# Tour 488 spoke, inside Stop 1's Orientation, a verbatim fare table:
#   "admission is Single ticket purchased on the day of entry: €25. Single ticket
#    reserved online: €29. Reduced ticket: €2. (Discounts exist for various groups)."
# Practical facts must be spoken ONCE, as at most two short sentences. This guard
# detects a spoken admission RUN that lists multiple ticket lines and collapses it
# to one standard-admission sentence ("A ticket is €25."), keeping the first
# (adult/standard) price it finds. Deterministic; never invents a price.

# A fare-table run: an "admission is …" (or "Admission:") lead followed by two or
# more ticket/price segments. Matches the spoken prose shape, within one paragraph.
_FARE_TABLE_RE = re.compile(
    r"(?i)(?:admission\s+is\s+|admission:\s*)?"
    r"(?:single|standard|full|adult|reduced|concession|day|online)?\s*ticket[^.]*?"
    r"[€£$¥]\s?\d{1,4}"                                   # first priced ticket line
    r"(?:[^.]*?\.\s*(?:single|standard|full|adult|reduced|concession|day|online|"
    r"\(?discount|tickets?)[^.]*?(?:[€£$¥]\s?\d{1,4})?)+"  # >=1 more ticket line
    r"\s*\.?",
)
_FIRST_PRICE_RE = re.compile(r"[€£$¥]\s?\d{1,4}")


def collapse_fare_table(text: str) -> Tuple[str, int]:
    """Collapse any spoken RAW fare table to one 'A ticket is <price>.' sentence.

    Returns ``(cleaned, n_collapsed)``. Deterministic and pure. Only a multi-line
    ticket run (two or more priced ticket segments) is collapsed; a single clean
    admission sentence ("A ticket is 25 euros.") is left untouched. The first
    (standard/adult) price in the run is kept.
    """
    if not text:
        return text or "", 0
    out = text
    collapsed = 0
    while True:
        m = _FARE_TABLE_RE.search(out)
        if not m:
            break
        run = m.group(0)
        price_m = _FIRST_PRICE_RE.search(run)
        if not price_m:
            break
        price = re.sub(r"\s+", "", price_m.group(0))
        replacement = f"A ticket is {price}."
        out = out[:m.start()] + replacement + out[m.end():]
        collapsed += 1
        if collapsed > 10:  # safety against pathological loops
            break
    if collapsed:
        out = re.sub(r'[ \t]{2,}', ' ', out)
        out = re.sub(r'[ \t]+\n', '\n', out)
    return out, collapsed


# ---------------------------------------------------------------------------
# [LOCAL-618 #4] Say the honest unpublished-hours line, once, on EVERY path
# ---------------------------------------------------------------------------
#
# The fresh museum path does not always build the About opening section that
# carries _visiting_fallback_sentence, so a tour whose venue published no hours
# shipped with NOTHING said about hours — three live critiques flagged
# "hours & admission never spoken" as a High defect. This tour-wide guard, run on
# the delivered text, inserts the honest line ONCE after the Stop-1 orientation
# when (a) no concrete hours are spoken anywhere and (b) the line is not already
# present. It never invents hours and never fires when real hours are present.

_UNPUBLISHED_HOURS_LINE = "Opening hours weren't published where we could read them."

# A sentence that STATES concrete opening hours (a time, a weekday range, "open
# daily"), or admission — anything that means the tour already speaks visiting info.
_SPOKEN_HOURS_RE = re.compile(
    r"(?i)(\bis\s+open\b|\bopen\s+daily\b|\d\s*(?:am|pm)\b|\d{1,2}:\d{2}|"
    r"\bopen\s+(?:mon|tue|wed|thu|fri|sat|sun)|admission\s+is\b|\bfree\s+admission\b|"
    r"Museum Information)")


def tour_speaks_hours(text: str) -> bool:
    """True when the delivered text already addresses hours/admission — either by
    stating concrete hours/admission, or by carrying a website-pointer / honest
    'weren't published' sentence. In all these cases there is nothing to add."""
    if _SPOKEN_HOURS_RE.search(text or ""):
        return True
    # An existing pointer / honest line already addresses hours — don't double up.
    if _WEBSITE_POINTER_SENT_RE.search(text or ""):
        return True
    return False


def ensure_unpublished_hours_line(text: str,
                                  hours_genuinely_absent: bool = True) -> Tuple[str, bool]:
    """Insert the honest unpublished-hours line once when no hours are spoken.

    Returns ``(text, inserted)``. Deterministic, pure. Does nothing when the tour
    already speaks hours/admission or already carries the honest line, and only
    fires for a MUSEUM-context tour (a walking/neighbourhood tour has no single
    building whose hours a visitor would check). The line is placed at the end of
    the Stop-1 orientation paragraph, so the listener hears it up front.

    [LOCAL-627 defect 2] ``hours_genuinely_absent`` guards the honest line: it is
    True only when the hours preflight RAN successfully and found no hours. When
    the preflight ERRORED or was skipped (a transient failure, not real evidence
    that the venue publishes no hours — the Prado publishes hours but tour 487's
    preflight failed), the caller passes False and we say NOTHING rather than
    assert "weren't published". Default True keeps the LOCAL-618 contract for
    callers that do not distinguish.
    """
    if not text or not text.strip():
        return text or "", False
    if not hours_genuinely_absent:
        # [LOCAL-627 d2] Preflight did not reliably establish that hours are
        # unpublished — say nothing rather than a false "weren't published".
        return text, False
    if _UNPUBLISHED_HOURS_LINE in text:
        return text, False
    if tour_speaks_hours(text):
        return text, False
    # Museum-context gate: the honest hours line is only meaningful for a venue the
    # visitor enters. Require a museum/gallery signal in the delivered text.
    if not re.search(r"(?i)\b(museum|gallery|galleries|mus[ée]e|museo|kunst|collection)\b", text):
        return text, False

    paras = text.split("\n\n")
    # Prefer the Stop-1 orientation paragraph.
    _target = None
    for i, p in enumerate(paras):
        if re.search(r"(?i)^\s*(?:stop\s*1\b.*)?orientation:", p) or "Orientation:" in p:
            _target = i
            break
    if _target is None:
        # Fall back to the first non-empty paragraph.
        for i, p in enumerate(paras):
            if p.strip():
                _target = i
                break
    if _target is None:
        return text, False

    sep = "" if paras[_target].rstrip().endswith((".", "!", "?")) else "."
    paras[_target] = paras[_target].rstrip() + sep + " " + _UNPUBLISHED_HOURS_LINE
    return "\n\n".join(paras), True


# ---------------------------------------------------------------------------
# [LOCAL-629 item 4] Speak the KNOWN hours, once, on EVERY path
# ---------------------------------------------------------------------------
#
# The Van Gogh / Belvedere live defect: the venue preflight (or the site
# extractor) KNEW the hours, but they ended up only in a "Museum Information:"
# FIELD LINE — which the listener-critique (and the audio) does not read as prose
# — so no hours were ever SPOKEN. The ticket (and criterion 3) require hours to be
# SPOKEN. This guard, run on the delivered text, injects a real spoken sentence
# into the Stop-1 opening when (a) we HAVE hours (from the preflight/site) and
# (b) the delivered PROSE speaks none. It never invents hours (the caller passes
# only grounded values) and is a no-op when prose already states hours.

# Concrete hours/admission IN PROSE — deliberately does NOT match the bare
# "Museum Information" field label (that label is a non-spoken field line that the
# audio/critique strip, so its presence must NOT be read as "hours spoken").
_SPOKEN_HOURS_PROSE_RE = re.compile(
    r"(?i)(\bis\s+open\b|\bopen\s+daily\b|\d\s*(?:am|pm)\b|\d{1,2}:\d{2}|"
    r"\bopen\s+(?:mon|tue|wed|thu|fri|sat|sun)|admission\s+is\b|\bfree\s+admission\b|"
    r"\ba\s+ticket\s+is\b)")


def tour_speaks_hours_in_prose(text: str) -> bool:
    """True when the delivered PROSE states concrete hours/admission.

    Field lines that the audio/critique strip — "Museum Information:",
    "Address:", "Coordinates:", "Directions:", "Orientation:" labels, and
    "Sources:"/"Hours ... source:" notes — are removed first, so a time that
    appears ONLY inside a non-spoken field label does not count as spoken."""
    if not text:
        return False
    _spoken = []
    for line in text.split("\n"):
        if re.match(r"(?i)^\s*(museum information|address|coordinates|directions|"
                    r"type/specialty|tour-category|sources?|hours?/admission source)"
                    r"\s*:", line):
            continue
        _spoken.append(line)
    return bool(_SPOKEN_HOURS_PROSE_RE.search("\n".join(_spoken)))


def ensure_spoken_hours_line(text: str, hours: str = "", admission: str = "") -> "Tuple[str, bool]":
    """Insert the SINGLE composed practical-facts sentence once when the hours are
    KNOWN but the delivered prose speaks none.

    ``hours`` / ``admission`` are grounded values (from the venue preflight or the
    site extractor); at least one must be non-empty for anything to happen.

    [LOCAL-633] The sentence is COMPOSED (``compose_practical_facts``) — one short
    spoken pair, never the raw preflight paste — and it is placed in the Stop-1
    OPENING SECTION (right after the About narration), NEVER inside an Orientation
    paragraph. Practical facts do not belong in an Orientation (D633); the opening
    section is their one spoken home. Deterministic, pure, idempotent. A no-op when
    the prose already speaks hours/admission, when there is no museum context, or
    when both inputs are empty. Returns ``(text, inserted)``.
    """
    if not text or not text.strip():
        return text or "", False
    hours = (hours or "").strip()
    admission = (admission or "").strip()
    if not hours and not admission:
        return text, False
    # Already spoken in prose → nothing to add (the once-guard).
    if tour_speaks_hours_in_prose(text):
        return text, False
    if not re.search(r"(?i)\b(museum|gallery|galleries|mus[ée]e|museo|kunst|collection)\b", text):
        return text, False

    # [LOCAL-633] Compose the single short sentence pair from the structured facts.
    sentence = compose_practical_facts({"hours": hours, "admission": admission})
    if not sentence:
        return text, False
    if not sentence.endswith((".", "!", "?")):
        sentence += "."

    # Place it in the Stop-1 opening section, after the About narration. NEVER an
    # Orientation paragraph, and never a non-spoken field block (Museum Information,
    # Address, Coordinates, Directions, Sources…). Target the Stop-1 OPENING
    # SECTION: a narration prose paragraph that appears BEFORE the first
    # Orientation. Never the title/header block, a field block, a stop header, or
    # an Orientation. If no such prose paragraph exists yet, the sentence is
    # inserted as its OWN new paragraph immediately after the first stop header
    # (the opening-section position), still never inside an Orientation.
    _TITLE_OR_HEADER = re.compile(
        r"(?i)^\s*(step-by-step\b|tour-category:|type/specialty:|address:|"
        r"coordinates:|directions:|sources?:|stop\s*\d+:|orientation:|"
        r"museum information:|operational details:|visiting hours:|opening hours:|"
        r"hours:|specific examples:)")

    def _prose_lines(paragraph):
        out = []
        for ln in paragraph.split("\n"):
            s = ln.strip()
            if not s or _TITLE_OR_HEADER.match(s):
                continue
            out.append(ln)
        return out

    paras = text.split("\n\n")

    # First Orientation / first stop-header positions bound the opening section.
    _first_orientation = next(
        (i for i, p in enumerate(paras) if "Orientation:" in p), len(paras))
    _first_stop = next(
        (i for i, p in enumerate(paras)
         if re.match(r"(?i)^\s*stop\s*\d+:", p.strip())), None)

    # (a) Prefer a narration prose paragraph in the opening section (before the
    #     first Orientation), that is not a header/field/stop block.
    _target = None
    for i, p in enumerate(paras):
        if i >= _first_orientation:
            break
        if "Orientation:" in p:
            continue
        if _prose_lines(p):
            _target = i
            break

    if _target is not None:
        lines = paras[_target].split("\n")
        _li = next((j for j in range(len(lines) - 1, -1, -1)
                    if lines[j].strip() and not _TITLE_OR_HEADER.match(lines[j].strip())),
                   None)
        if _li is None:
            return text, False
        sep = "" if lines[_li].rstrip().endswith((".", "!", "?")) else "."
        lines[_li] = lines[_li].rstrip() + sep + " " + sentence
        paras[_target] = "\n".join(lines)
        return "\n\n".join(paras), True

    # (b) No opening-section prose yet → insert the sentence as its OWN paragraph
    #     right after the first stop header (opening-section position).
    if _first_stop is not None:
        paras.insert(_first_stop + 1, sentence)
        return "\n\n".join(paras), True

    return text, False


# ---------------------------------------------------------------------------
# [LOCAL-630 item 3] Hours spoken EXACTLY once
# ---------------------------------------------------------------------------
#
# The NG 495 defect: the delivered text spoke hours TWICE — once in the
# "Museum Information:" sentence (whose LABEL is stripped at TTS so its VALUE is
# read aloud) and again in a raw injected "The museum is open Open daily…" line.
# LOCAL-627's rule is ONE spoken practical-facts sentence. The two helpers below
# count hours statements as the LISTENER hears them (label stripped, value kept)
# and collapse a duplicate injected sentence down to one.
#
# A "spoken hours statement" is a sentence that, once the field LABEL (but NOT its
# value) is removed, states concrete hours — matched by _SPOKEN_HOURS_PROSE_RE.
# The "Museum Information:" value counts (TTS strips the label and speaks the
# value); a bare "Address:"/"Coordinates:" line does not.

# Label prefixes the TTS strips while KEEPING the value (so the value is spoken).
_HOURS_VALUE_LABEL_RE = re.compile(
    r"(?im)^\s*(museum information|operational details|hours|visiting hours|"
    r"opening hours)\s*:\s*")
# Field lines whose WHOLE content is non-spoken navigation metadata.
_NONSPOKEN_FIELD_RE = re.compile(
    r"(?im)^\s*(address|coordinates|directions|type/specialty|tour-category|"
    r"sources?|hours?/admission source)\s*:")


def _hours_bearing_sentences(text: str) -> "List[str]":
    """Return the SPOKEN sentences in ``text`` that state concrete HOURS, as the
    listener hears them: field LABELS that TTS strips are removed but their VALUE
    kept; whole non-spoken field lines are dropped. Admission-only sentences do
    NOT count here (hours and admission are counted separately). Pure."""
    if not text:
        return []
    # Hours cue: an opening phrase or a clock/day time — NOT the admission cue.
    _hours_cue = re.compile(
        r"(?i)(\bis\s+open\b|\bopen\s+daily\b|\d\s*(?:am|pm)\b|\d{1,2}:\d{2}|"
        r"\bopen\s+(?:mon|tue|wed|thu|fri|sat|sun))")
    spoken_lines = []
    for line in text.split("\n"):
        if _NONSPOKEN_FIELD_RE.match(line):
            continue
        spoken_lines.append(_HOURS_VALUE_LABEL_RE.sub("", line))
    body = "\n".join(spoken_lines)
    out = []
    for sent in re.split(r"(?<=[.!?])\s+|\n+", body):
        s = sent.strip()
        if s and _hours_cue.search(s):
            out.append(s)
    return out


def count_spoken_hours_statements(text: str) -> int:
    """Number of distinct SPOKEN sentences in the delivered text that state HOURS
    (as the listener hears them). LOCAL-627/LOCAL-630 require this to be ≤ 1."""
    return len(_hours_bearing_sentences(text))


def collapse_spoken_hours_statements(text: str) -> "Tuple[str, int]":
    """Ensure hours are SPOKEN at most once (LOCAL-627 / LOCAL-630 item 3).

    Keeps the FIRST spoken hours statement in reading order and removes any later
    duplicate injected sentence of the form "The museum is open …" (optionally
    with "Admission is …"). Returns ``(text, removed_count)``. Deterministic, pure,
    idempotent; a no-op when zero or one hours statement is present.

    Only the deterministic INJECTED sentence shape is removed — never a scraped
    "Museum Information:" line and never arbitrary narration — so the single
    surviving statement is the one already in the prose, and we only drop the
    redundant add-on.
    """
    if not text or not text.strip():
        return text or "", 0
    if count_spoken_hours_statements(text) <= 1:
        return text, 0

    # The injected sentence (ensure_spoken_hours_line / plan_b) always starts with
    # "The museum is open" and may carry a trailing "Admission is …". Remove its
    # SECOND and later occurrences, keeping whatever hours statement came first.
    _injected = re.compile(
        r"(?i)\s*The museum is open\b[^.!?]*(?:[.!?]\s*(?:admission is\b[^.!?]*[.!?])?)?")
    removed = 0

    # Find the position of the first hours statement; only strip injected sentences
    # that appear AFTER it, so the earliest statement always survives.
    first = _hours_bearing_sentences(text)
    first_sent = first[0] if first else ""
    first_pos = text.find(first_sent) if first_sent else -1

    def _sub(m):
        nonlocal removed
        if first_pos >= 0 and m.start() <= first_pos:
            return m.group(0)  # keep the first statement itself
        removed += 1
        return " "

    out = _injected.sub(_sub, text)
    # Tidy whitespace / orphaned punctuation left by the removal.
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\s+([.!?,;])", r"\1", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out, removed


# ---------------------------------------------------------------------------
# [LOCAL-630 item 2] Admission spoken ONCE; general-free beats any price
# ---------------------------------------------------------------------------
#
# NG 495 spoke admission TWICE and wrongly: "Admission is £3." then later "Free
# for general admission." The National Gallery is free; the £3 was a donation or
# an exhibition price mis-read as general admission. The rule: speak admission at
# most once, and a GENERAL-FREE statement beats any price found for a donation, an
# exhibition or the cloakroom. This delivered-text guard keeps a single admission
# statement — preferring a general-free one when present — and removes the rest.

# A spoken admission sentence: "admission is …", "Admission:", "free admission",
# "free to enter", "entry is free", "a ticket is £N", "£/€/$ N".
_ADMISSION_SENTENCE_RE = re.compile(
    r"(?i)(\badmission\s+is\b|\badmission:\b|\bfree\s+admission\b|"
    r"\bfree\s+(?:to\s+(?:enter|all)|for\s+general)\b|\bentry\s+is\b|"
    r"\ba\s+ticket\s+is\b|\btickets?\s+(?:are|cost|start)\b|"
    r"\bgeneral\s+admission\b|[£€$¥]\s?\d)")

# A GENERAL-FREE admission statement (not "free for residents/under-18s only",
# which is conditional). "the gallery is free", "admission is free", "free to
# enter", "free for general admission", "entry is free".
_GENERAL_FREE_RE = re.compile(
    r"(?i)(\bfree\s+admission\b|\badmission\s+is\s+free\b|\bentry\s+is\b[^.!?]*\bfree\b|"
    r"\bfree\s+to\s+(?:enter|all|visit)\b|\bfree\s+for\s+general\s+admission\b|"
    r"\b(?:is|are)\s+free\s+to\s+enter\b|\bgeneral\s+admission\s+is\s+free\b|"
    r"\bno\s+(?:charge|admission\s+fee)\b|\bcharges\s+no\s+admission\b)")

# A PRICE admission statement (carries a currency amount).
_PRICE_IN_ADMISSION_RE = re.compile(r"[£€$¥]\s?\d|\bUSD\b|\bEUR\b|\bGBP\b")


def _admission_sentences_with_pos(text: str) -> "List[Tuple[int, str]]":
    """Return [(char_pos, sentence)] for SPOKEN admission statements (label
    stripped, value kept), in reading order."""
    if not text:
        return []
    out = []
    # Scan over the whole label-stripped text so sentence positions are stable.
    stripped = "\n".join(
        ("" if _NONSPOKEN_FIELD_RE.match(ln) else _HOURS_VALUE_LABEL_RE.sub("", ln))
        for ln in text.split("\n"))
    for m in re.finditer(r"[^.!?\n]*[.!?]", stripped):
        s = m.group(0).strip()
        if s and _ADMISSION_SENTENCE_RE.search(s):
            out.append((m.start(), s))
    return out


def count_spoken_admission_statements(text: str) -> int:
    """Number of SPOKEN admission statements in the delivered text (≤ 1 required)."""
    return len(_admission_sentences_with_pos(text))


def collapse_admission_statements(text: str) -> "Tuple[str, int]":
    """Ensure admission is SPOKEN at most once, with general-free winning over any
    price (LOCAL-630 item 2). Returns ``(text, removed_count)``.

    Policy:
      * If any GENERAL-FREE admission statement is present, that one is the single
        survivor — every other admission statement (a £3 donation, an exhibition
        price, a cloakroom fee) is removed.
      * Otherwise the FIRST admission statement survives and later ones are removed.

    Deterministic, pure, idempotent; a no-op at ≤ 1 admission statement. Only whole
    admission sentences are removed — never other narration.
    """
    if not text or not text.strip():
        return text or "", 0
    sents = _admission_sentences_with_pos(text)
    if len(sents) <= 1:
        return text, 0

    # Pick the survivor sentence text.
    survivor = ""
    for _pos, s in sents:
        if _GENERAL_FREE_RE.search(s):
            survivor = s
            break
    if not survivor:
        survivor = sents[0][1]

    removed = 0
    kept_once = False
    out = text
    # Remove each admission sentence occurrence except the first match of the
    # survivor text.
    for _pos, s in sents:
        if s == survivor and not kept_once:
            kept_once = True
            continue
        # Remove this sentence (first occurrence) from the text.
        idx = out.find(s)
        if idx >= 0:
            out = out[:idx] + out[idx + len(s):]
            removed += 1
    if not kept_once and survivor:
        # ensure the survivor remains (it always does; defensive)
        pass
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\s+([.!?,;])", r"\1", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out, removed


# ---------------------------------------------------------------------------
# [LOCAL-633] compose_practical_facts — ONE short spoken sentence pair
# ---------------------------------------------------------------------------
#
# Bench R1 flagged three tours (Uffizi 488, Reina Sofía 505, Met 507) that spoke
# the RAW preflight dump — the full ticket-office/discount/price-table paragraph —
# inside the first stop. LOCAL-627's rule is ONE short spoken practical-facts
# sentence. This composer turns the STRUCTURED preflight (hours + admission
# strings) into at most two short sentences, spoken naturally:
#
#   "The Uffizi is open Tuesday to Sunday, and closed on Mondays. Adult tickets
#    are 25 euros; under-18s go free."
#
# Rules (binding, D633):
#   * day RANGES, not day lists;
#   * one adult price plus at most one free group;
#   * no parentheses, no discount schemes, no ticket-office details;
#   * the currency as a WORD ("euros"), never a symbol;
#   * only facts present in the structured preflight (never invented).
#
# Pure and deterministic: no network, no LLM. The caller places the returned
# string ONCE, right after the About sentences, with a once-guard.

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday",
             "saturday", "sunday"]
_WEEKDAY_TITLE = {d: d.capitalize() for d in _WEEKDAYS}

# Common weekday ABBREVIATIONS → full lower-case name. Expanded once up front so
# the composer's weekday logic ("Tue-Sun", "closed Mon") sees full names.
_WEEKDAY_ABBR = {
    "mon": "monday", "tue": "tuesday", "tues": "tuesday", "wed": "wednesday",
    "weds": "wednesday", "thu": "thursday", "thur": "thursday", "thurs": "thursday",
    "fri": "friday", "sat": "saturday", "sun": "sunday",
}


def _expand_weekday_abbr(text: str) -> str:
    """Expand bare weekday abbreviations to full names ('Tue-Sun' → 'tuesday-sunday',
    'closed Mon' → 'closed monday'). Only whole-word abbreviations are expanded, so
    'Monday' / 'Sunday' are untouched. Case-insensitive; returns lower-cased text
    (the composer's weekday logic is case-insensitive)."""
    if not text:
        return ""

    def _sub(m):
        return _WEEKDAY_ABBR.get(m.group(0).lower(), m.group(0))

    return re.sub(r"\b(" + "|".join(sorted(_WEEKDAY_ABBR, key=len, reverse=True))
                  + r")\b\.?", _sub, text, flags=re.I)


# Currency symbol → spoken word (always the plural noun; "25 euros").
_CURRENCY_WORD = {"€": "euros", "$": "dollars", "£": "pounds", "¥": "yen"}


def _spoken_price(symbol: str, amount: str) -> str:
    """'€' + '25' → '25 euros'; '$' + '30' → '30 dollars'. The currency is spoken
    as a WORD (D633), never a symbol, and never read back as a numeral+symbol."""
    word = _CURRENCY_WORD.get(symbol, "")
    amt = amount.strip()
    if not amt:
        return ""
    return f"{amt} {word}".strip()


def _extract_closed_days(hours_text: str) -> "List[str]":
    """The weekday names the venue is CLOSED, lower-cased, de-duplicated, in week
    order. Handles 'closed on Mondays', 'Tuesday: Closed', 'closed Wednesdays'.
    Calendar-date closures (January 1, December 25) are ignored — a spoken facts
    line names a weekly closed DAY, not a holiday list."""
    if not hours_text:
        return []
    low = hours_text.lower()
    closed = set()
    # "closed on Monday(s)" / "closed Monday(s)" / "closed: Monday"
    for m in re.finditer(r"closed\b[^.;]*", low):
        seg = m.group(0)
        for d in _WEEKDAYS:
            if re.search(rf"\b{d}s?\b", seg):
                closed.add(d)
    # "Tuesday: Closed" (day precedes the word closed)
    for m in re.finditer(r"\b(" + "|".join(_WEEKDAYS) + r")s?\b\s*:?\s*closed", low):
        closed.add(m.group(1))
    return [d for d in _WEEKDAYS if d in closed]


def _extract_open_range(hours_text: str) -> str:
    """An explicit open day-RANGE phrase if the source states one — 'Tuesday to
    Sunday', 'Monday–Friday'. Returns a natural 'X to Y' string or ''. Never a
    day LIST (D633)."""
    if not hours_text:
        return ""
    low = hours_text.lower()
    m = re.search(
        r"\b(" + "|".join(_WEEKDAYS) + r")\b\s*(?:to|–|-|through|thru)\s*\b("
        + "|".join(_WEEKDAYS) + r")\b", low)
    if m:
        a, b = m.group(1), m.group(2)
        # Guard against a range that is really the open window of a single line
        # ("Monday, Wednesday to Saturday") — only trust it when the two ends are
        # not the same day.
        if a != b:
            return f"{_WEEKDAY_TITLE[a]} to {_WEEKDAY_TITLE[b]}"
    return ""


def _open_phrase_from_closed(closed: "List[str]") -> str:
    """Turn the CLOSED day set into an open phrase as a RANGE, never a list.
      * no closed day               → 'daily'
      * one closed day              → 'daily except <Day>'
      * two closed days             → 'daily except <Day> and <Day>'
      * three or more closed days   → '' (too many to phrase as 'daily except …';
                                      the caller lets an explicit open range speak)
    """
    if not closed:
        return "daily"
    names = [_WEEKDAY_TITLE[d] for d in closed]
    if len(names) == 1:
        return f"daily except {names[0]}"
    if len(names) == 2:
        return f"daily except {names[0]} and {names[1]}"
    return ""


def _mentioned_open_days(hours_text: str) -> "List[str]":
    """Weekdays the source NAMES with an opening time (an open-day list such as
    'Monday, Thursday, Friday: 12:00 – 6:00; Saturday, Sunday: 10:00 – 6:00').
    Days that appear only inside a 'closed …' clause are excluded. Week-ordered."""
    if not hours_text:
        return []
    low = hours_text.lower()
    # Remove closed clauses so a closed day is not counted as open.
    low_open = re.sub(r"closed[^.;]*", " ", low)
    mentioned = {d for d in _WEEKDAYS if re.search(rf"\b{d}s?\b", low_open)}
    return [d for d in _WEEKDAYS if d in mentioned]


def _closed_from_open_complement(hours_text: str) -> "List[str]":
    """When the source lists OPEN days (no 'to' range, no explicit 'closed' day),
    the closed days are the complement of the named open days. Only trusted when
    the source names a plausible open-day LIST (3–6 distinct weekdays) so a single
    stray weekday does not imply six closed days. Week-ordered."""
    open_days = _mentioned_open_days(hours_text)
    if not (3 <= len(open_days) <= 6):
        return []
    return [d for d in _WEEKDAYS if d not in open_days]


def _extract_open_time_span(hours_text: str) -> str:
    """A SINGLE simplified open→close span, e.g. '8:15 to 6:30', '10 to 5' — the
    FIRST clock span in the source, with am/pm/'h' suffixes and the ticket-office
    parenthetical dropped so the sentence stays short (the task example keeps the
    span: 'open Tuesday to Sunday from 8:15 to 6:30'). Returns '' when the source
    carries no clock time. Only one span is ever kept — a venue's many day-group
    time rows are not read aloud (that is the long dump D633 removes)."""
    if not hours_text:
        return ""
    # Drop parentheticals (ticket-office / hall-closing detail) before scanning.
    txt = re.sub(r"\([^)]*\)", " ", hours_text)
    # Normalise the word times to a spoken form the span regex can carry.
    txt = re.sub(r"(?i)\bnoon\b", "12", txt)
    txt = re.sub(r"(?i)\bmidnight\b", "12", txt)
    m = re.search(
        r"(\d{1,2})(?::(\d{2}))?\s*(?:am|pm)?\s*(?:to|–|-|until|till)\s*"
        r"(\d{1,2})(?::(\d{2}))?\s*(?:am|pm)?", txt, re.I)
    if not m:
        return ""

    def _fmt(h, mm):
        return f"{h}:{mm}" if mm else f"{h}"

    start = _fmt(m.group(1), m.group(2))
    end = _fmt(m.group(3), m.group(4))
    return f"{start} to {end}"


def _compose_hours_phrase(hours_text: str, venue_short: str) -> str:
    """One short spoken hours sentence from the structured hours string.

    Prefers an explicit open day-RANGE ('Tuesday to Sunday'); otherwise derives
    'daily except <Day>' from a single closed day. A single simplified time span
    ('from 8:15 to 6:30') rides along when the source gives one — the task example
    keeps it, and one short span cannot trip long_practical_sentence (which needs a
    clock time AND >30 words). Parentheticals, ticket-office / hall-closing detail,
    and multi-row time tables are never read aloud. Returns '' when no weekday
    structure can be found."""
    hours_text = (hours_text or "").strip()
    if not hours_text:
        return ""
    hours_text = _expand_weekday_abbr(hours_text)
    closed = _extract_closed_days(hours_text)
    open_range = _extract_open_range(hours_text)
    time_span = _extract_open_time_span(hours_text)
    # When the source lists OPEN days with no explicit closed day and no 'to'
    # range, the closed days are the complement of the named open days — so a
    # 5-day list ("Monday, Thursday, Friday … Saturday, Sunday") becomes an honest
    # "daily except Tuesday and Wednesday", never a false "daily".
    if not closed:
        closed = _closed_from_open_complement(hours_text)

    # [LEAD 2026-10-08] Trust a stated range only when it covers EXACTLY the non-closed days.
    # The Met source "Sun–Tue, Thu…Sat; closed Wednesday" yielded "open Sunday to Tuesday",
    # a false statement that drops Thursday to Saturday. Otherwise phrase from the closed days.
    if open_range and closed:
        _a, _b = [d.lower() for d in open_range.split(" to ")]
        _i, _j = _WEEKDAYS.index(_a), _WEEKDAYS.index(_b)
        _span = {_WEEKDAYS[(_i + k) % 7] for k in range(((_j - _i) % 7) + 1)}
        if _span != set(_WEEKDAYS) - set(closed):
            open_range = ""
    if open_range:
        body = f"open {open_range}"
        if time_span:
            body += f" from {time_span}"
        if len(closed) == 1:
            body += f", and closed on {_WEEKDAY_TITLE[closed[0]]}s"
    else:
        phrase = _open_phrase_from_closed(closed)
        if not phrase:
            return ""
        body = f"open {phrase}"
        if time_span:
            # "open daily from 10 to 5" / "open daily except Monday, 10 to 5"
            sep = ", " if "except" in phrase else " from "
            body += f"{sep}{time_span}"
    return f"{venue_short} is {body}."


def _compose_admission_phrase(admission_text: str) -> str:
    """One short spoken admission sentence: ONE adult price plus AT MOST one free
    group. The currency is a WORD. No parentheses, no discount schemes, no price
    tables (D633). Returns '' when neither a price nor a general/concession-free
    fact is present."""
    admission_text = (admission_text or "").strip()
    if not admission_text:
        return ""
    # Strip any parenthetical aside outright — those are the discount/ticket-office
    # details the composer must never speak.
    cleaned = re.sub(r"\([^)]*\)", " ", admission_text)

    # The FIRST currency amount is taken as the adult/general price (sources lead
    # with the general ticket). Symbol-led ("€12", "$30") or amount-led ("12 EUR").
    price = ""
    m = re.search(r"([$€£¥])\s?(\d{1,4}(?:\.\d{2})?)", cleaned)
    if m:
        price = _spoken_price(m.group(1), m.group(2))
    else:
        m2 = re.search(r"\b(\d{1,4})\s?(?:eur|euros?|usd|dollars?|gbp|pounds?)\b",
                       cleaned, re.I)
        if m2:
            # Normalise the trailing currency word.
            word = re.search(r"(eur|euros?|usd|dollars?|gbp|pounds?)",
                             cleaned[m2.start():], re.I)
            w = (word.group(1).lower() if word else "")
            spoken_w = ("euros" if w.startswith("eur") else
                        "dollars" if w.startswith(("usd", "dollar")) else
                        "pounds" if w.startswith(("gbp", "pound")) else w)
            price = f"{m2.group(1)} {spoken_w}".strip()

    # Is there a FREE group we may name (at most one)? Only a group the source
    # explicitly ties to FREE entry — never a PRICED concession ("$8 for seniors,
    # students" means they PAY $8, not that they go free). Isolate the clause(s)
    # that actually carry a "free" marker and look for a group ONLY there.
    low = cleaned.lower()
    general_free = bool(re.search(
        r"\b(?:admission|entry)\s+is\s+free\b|\bfree\s+admission\b|"
        r"\balways\s+free\b|\bfree\s+to\s+(?:the\s+public|all|enter|visit)\b", low))

    # The spans of text that are about FREE entry: a "free … <groups>" lead
    # ("free for children 12 and under", "Free Admission: … under 18, over 65"),
    # or a "<group> … free" trailer.
    free_context = " ".join(re.findall(r"free[^.;]*", low))
    free_context += " " + " ".join(re.findall(r"[^.;]*?\bfree\b", low))

    free_group = ""
    # [LEAD 2026-10-08] Speak the source's OWN age: "children 12 and under" stays 12. The
    # previous code mapped any child mention to "under-18s" (Met tour 512 was false).
    _age = re.search(r"\b(?:children|kids|visitors|youth)?\s*(?:aged\s+)?(\d{1,2})\s+(?:and|&)\s+(?:under|younger)\b"
                     r"|\bunder[-\s]?(\d{1,2})s?\b", free_context)
    if _age:
        _n = _age.group(1) or _age.group(2)
        free_group = (f"children {_n} and under" if _age.group(1) else f"under-{_n}s")
    elif re.search(r"\bchildren\b|\bchild\b", free_context):
        free_group = "children"
    elif re.search(r"\bstudents?\b", free_context):
        free_group = "students"
    elif re.search(r"\bover[-\s]?65s?\b|\bseniors?\b|\b65\+\b", free_context):
        free_group = "seniors"

    if price and free_group:
        return f"Admission is {price} for adults; {free_group} go free."
    if price:
        return f"Admission is {price} for adults."
    if general_free:
        return "Admission is free."
    return ""


def compose_practical_facts(preflight: "Optional[Dict]") -> str:
    """[LOCAL-633] Compose ONE short spoken practical-facts sentence pair from the
    STRUCTURED preflight.

    ``preflight`` is the venue preflight dict (keys ``hours``, ``admission`` are
    free-text strings grounded by the preflight; ``name``/``venue``/``museum_name``
    optionally carry the venue's name for the spoken subject). Returns at most two
    short sentences (hours, then admission), about 30 words total, spoken naturally
    and faithful to D633's rules. Returns '' when the preflight carries neither a
    usable hours structure nor an admission fact.

    Pure and deterministic. Only facts present in the preflight are spoken — the
    composer never invents a day, a price or a free group.
    """
    if not preflight or not isinstance(preflight, dict):
        return ""
    if preflight.get("error") or preflight.get("skipped"):
        return ""
    hours_text = (preflight.get("hours") or "").strip()
    admission_text = (preflight.get("admission") or "").strip()
    if not hours_text and not admission_text:
        return ""

    # Spoken subject: a natural short venue name, else "The museum".
    venue_name = (preflight.get("name") or preflight.get("venue")
                  or preflight.get("museum_name") or "").strip()
    venue_short = _compose_subject(venue_name)

    # Never speak "open daily" when a closed weekday is named (reuse the preflight's
    # own reconciliation when available).
    if hours_text:
        try:
            import venue_preflight as _vpf
            hours_text = _vpf.reconcile_daily_with_closed_days(hours_text)
        except Exception:
            pass

    parts: List[str] = []
    hours_sentence = _compose_hours_phrase(hours_text, venue_short)
    if hours_sentence:
        parts.append(hours_sentence)
    adm_sentence = _compose_admission_phrase(admission_text)
    if adm_sentence:
        parts.append(adm_sentence)
    return " ".join(parts).strip()


def _compose_subject(venue_name: str) -> str:
    """A natural spoken subject for the hours sentence: 'The Uffizi', 'The Met',
    else 'The museum'. Strips a trailing ', City, ST' tail and a generic descriptor
    so the sentence reads aloud, and ensures a leading 'The'."""
    vn = (venue_name or "").split(",")[0].strip()
    if not vn:
        return "The museum"
    # Known natural short names people say aloud.
    low = vn.lower()
    if "uffizi" in low:
        return "The Uffizi"
    if "metropolitan museum" in low or low == "the met":
        return "The Met"
    if "reina sof" in low:
        return "The Reina Sofía"
    # Prefix "The" when the name is not already article-led.
    if low.startswith(("the ", "a ", "an ")):
        return vn[:1].upper() + vn[1:]
    return f"The {vn}"


# ---------------------------------------------------------------------------
# CLI: run gate on a tour file
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python practical_facts_gate.py <tour_file.txt> [source_url] [source_file]")
        print("  tour_file.txt — the generated tour to check")
        print("  source_url    — optional: URL the visitor info was fetched from")
        print("  source_file   — optional: file containing the fetched source content")
        sys.exit(1)

    tour_path = sys.argv[1]
    _source_url = sys.argv[2] if len(sys.argv) > 2 else ""
    _source_file = sys.argv[3] if len(sys.argv) > 3 else ""

    with open(tour_path, 'r', encoding='utf-8') as f:
        _tour_text = f.read()

    _source_text = ""
    if _source_file:
        with open(_source_file, 'r', encoding='utf-8') as f:
            _source_text = f.read()

    fixed, result = gate_and_fix(_tour_text, _source_url, _source_text)

    # Exit code: 0 = all verified, 1 = claims dropped
    if result.passed:
        print("\n  GATE: PASSED — all practical claims verified")
        sys.exit(0)
    else:
        print(f"\n  GATE: CLAIMS DROPPED — {len(result.dropped_claims)} unverifiable claim(s)")
        sys.exit(1)
