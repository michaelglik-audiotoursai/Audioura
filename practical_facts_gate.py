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

    # Split by sentence-like boundaries
    sentences = re.split(r'[.;]\s*', info_text)

    for sentence in sentences:
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

    if not _times and not _times_24h:
        # Try "open daily" type claims
        if 'daily' in claim_lower or 'tous les jours' in claim_lower:
            return ('daily' in source_lower or 'tous les jours' in source_lower
                    or 'every day' in source_lower or 'chaque jour' in source_lower)
        return False

    # At least one time value from the claim must appear in the source
    verified_count = 0

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
        # Source must say free/gratuit/libre...
        _has_free = bool(re.search(r'gratuit|libre|free', source_lower))
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
