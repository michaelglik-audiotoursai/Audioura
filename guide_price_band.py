"""guide_price_band.py — LOCAL-354: Source price band from dining guides.

OSM carries opening_hours and payment but no price in Nice's dining district.
Michael's requirement: state "you can eat here for under X" — a cheapest-
realistic-meal threshold from a published guide, not a prediction of spend.

Supported guides (priority order):
  1. Le Fooding — publishes "À la carte €A-B" price range per listed venue
  2. Gault&Millau — publishes "Indicative price per person (excl. drinks) A to B"

Threshold derivation:
  Given a guide range [low, high], the threshold is the NEXT round €10 above
  the high end. If high ≤ 43, threshold = 50. If high ≤ 55, threshold = 60.
  This produces "under €50" which is falsifiable only if you CANNOT eat there
  for that. Conservative by design — never states the average, always the cap.

Combination rule (Michael's format):
  "An average dinner or lunch would cost under €50 but credit cards are not accepted."
  ONE sentence. Band plus the practical gotcha. Nothing else.

Where no guide lists the venue: silence. Never infer from cuisine or neighbourhood.
"""

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from math import ceil

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class GuidePriceBand:
    """Price band sourced from a dining guide for one venue."""
    venue_name: str
    guide_name: str = ""           # "Le Fooding" or "Gault&Millau"
    guide_url: str = ""            # URL of the guide page for provenance
    low_eur: Optional[float] = None   # Lower bound of guide's price range
    high_eur: Optional[float] = None  # Upper bound of guide's price range
    raw_text: str = ""             # Verbatim price text from the guide page
    threshold_eur: Optional[int] = None  # Derived "under €X" value
    currency: str = "EUR"          # Always EUR for Nice venues

    @property
    def has_price(self) -> bool:
        """True if a guide-sourced price band exists."""
        return self.high_eur is not None and self.guide_name != ""

    @property
    def source_text_for_gate(self) -> str:
        """Source text the practical facts gate can verify against.

        Contains the guide name, URL, and the verbatim price text.
        """
        if not self.has_price:
            return ""
        lines = [
            f"Guide: {self.guide_name}",
            f"URL: {self.guide_url}",
            f"Price text: {self.raw_text}",
            f"Range: €{self.low_eur}-{self.high_eur}",
            f"Threshold: under €{self.threshold_eur}",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Threshold derivation
# ---------------------------------------------------------------------------

def derive_threshold(high_eur: float) -> int:
    """Derive the conservative "under €X" threshold from the guide's high-end.

    Rules:
      - Round UP to the next €10 boundary.
      - "Under €50" means: you CAN eat there for less than 50.
      - The high end of a guide range is what the most expensive à la carte
        items cost; the threshold must sit ABOVE it.

    Examples:
      high=43 → threshold=50  (next 10 above 43)
      high=50 → threshold=60  (50 itself is the high, so cap must be above)
      high=55 → threshold=60
      high=32 → threshold=40
    """
    # Next €10 boundary strictly above high_eur
    return int(ceil((high_eur + 1) / 10.0)) * 10


# ---------------------------------------------------------------------------
# Guide price registry — known listings from published guides
# ---------------------------------------------------------------------------

# These are sourced from publicly-accessible guide pages.
# Each entry: venue_name → (guide_name, guide_url, raw_price_text, low_eur, high_eur)
#
# Le Fooding for La Merenda:
#   Page: https://lefooding.com/en/restaurants/restaurant-la-merenda-nice-6
#   Price tag: "€36 to €50"
#   Detail text: "À la carte €31-43"
#   (We use the à la carte range which is the more specific claim)
#
# Gault&Millau for Le Safari:
#   Page: https://fr.gaultmillau.com/en/restaurants/le-safari
#   "Indicative price per person (excl. drinks) 32 to 55"
#
# Fenocchio: Listed on Gault&Millau as "Artisan" (glacier/ice cream parlour),
#   NOT as a restaurant. No per-person meal budget published. Omit.
#
# Acchiardo: NOT listed on Le Fooding, Gault&Millau, or Michelin Guide. Omit.

_GUIDE_PRICE_REGISTRY: Dict[str, Dict] = {
    "La Merenda": {
        "guide_name": "Le Fooding",
        "guide_url": "https://lefooding.com/en/restaurants/restaurant-la-merenda-nice-6",
        "raw_text": "À la carte €31-43",
        "low_eur": 31.0,
        "high_eur": 43.0,
    },
    "Le Safari": {
        "guide_name": "Gault&Millau",
        "guide_url": "https://fr.gaultmillau.com/en/restaurants/le-safari",
        "raw_text": "Indicative price per person (excl. drinks) 32 to 55",
        "low_eur": 32.0,
        "high_eur": 55.0,
    },
}

# Venues assessed but NOT listed on any guide with price data:
_GUIDE_NO_LISTING: Dict[str, str] = {
    "Fenocchio": "Gault&Millau lists as Artisan (glacier), no meal budget published",
    "Acchiardo": "Not listed on Le Fooding, Gault&Millau, or Michelin Guide",
}


def lookup_guide_price(venue_name: str) -> GuidePriceBand:
    """Look up guide price band for a venue.

    Returns a GuidePriceBand. If the venue has no guide listing, returns
    an empty band (has_price == False).
    """
    result = GuidePriceBand(venue_name=venue_name)

    entry = _GUIDE_PRICE_REGISTRY.get(venue_name)
    if entry:
        result.guide_name = entry["guide_name"]
        result.guide_url = entry["guide_url"]
        result.raw_text = entry["raw_text"]
        result.low_eur = entry["low_eur"]
        result.high_eur = entry["high_eur"]
        result.threshold_eur = derive_threshold(entry["high_eur"])
        logger.debug(f"[LOCAL-354] {venue_name}: guide price found → under €{result.threshold_eur}")
    else:
        reason = _GUIDE_NO_LISTING.get(venue_name, "Not found in any dining guide")
        logger.debug(f"[LOCAL-354] {venue_name}: no guide price — {reason}")

    return result


# ---------------------------------------------------------------------------
# Sentence combination: price band + payment fact → one sentence
# ---------------------------------------------------------------------------

def combine_price_and_payment(
    price_band: GuidePriceBand,
    payment_info: str,
) -> str:
    """Combine guide price band with OSM payment info into one sentence.

    Michael's format:
      "An average dinner or lunch would cost under €50 but credit cards are not accepted."

    Rules:
      - Price band present + payment gotcha → combined sentence
      - Price band present, no payment gotcha → price-only sentence
      - No price band + payment gotcha → payment-only sentence
      - Neither → empty string (silence)
    """
    if not price_band.has_price and not payment_info:
        return ""

    # Build the price part
    price_part = ""
    if price_band.has_price:
        price_part = f"an average dinner or lunch would cost under €{price_band.threshold_eur}"

    # Build the payment gotcha part
    payment_part = ""
    if payment_info:
        # Normalize: "Cash only" → "credit cards are not accepted"
        if payment_info.lower() in ("cash only",):
            payment_part = "credit cards are not accepted"
        elif payment_info.lower() in ("card payments only",):
            payment_part = "cash is not accepted"
        else:
            payment_part = payment_info.lower()

    # Combine
    if price_part and payment_part:
        # Michael's format: "An average ... under €50 but credit cards are not accepted"
        sentence = f"{price_part} but {payment_part}"
    elif price_part:
        sentence = price_part
    elif payment_part:
        # Payment-only: reformat as standalone
        if "credit cards are not accepted" in payment_part:
            sentence = "credit cards are not accepted"
        else:
            sentence = payment_part
    else:
        return ""

    # Capitalize first letter
    sentence = sentence[0].upper() + sentence[1:]

    return sentence


# ---------------------------------------------------------------------------
# Gate integration: generate source text for the practical facts gate
# ---------------------------------------------------------------------------

def build_price_source_text(price_band: GuidePriceBand) -> str:
    """Build the source text that the practical facts gate verifies against.

    This is appended to the OSM source text so the gate has both:
    - OSM tags (for payment/hours claims)
    - Guide price text (for the "under €X" claim)
    """
    if not price_band.has_price:
        return ""

    return price_band.source_text_for_gate


# ---------------------------------------------------------------------------
# Public API: Get combined operational sentence for a dining stop
# ---------------------------------------------------------------------------

def get_dining_sentence(
    venue_name: str,
    osm_payment_info: str = "",
) -> Tuple[str, str, str]:
    """Get the combined price+payment sentence for a dining stop.

    Args:
        venue_name: Restaurant name (e.g. "La Merenda")
        osm_payment_info: Payment info from OSM (e.g. "Cash only")

    Returns:
        Tuple of (sentence, source_url, source_text):
          - sentence: The combined operational sentence for the listener
          - source_url: Guide URL for provenance
          - source_text: Source text for gate verification
    """
    price_band = lookup_guide_price(venue_name)
    sentence = combine_price_and_payment(price_band, osm_payment_info)
    source_url = price_band.guide_url
    source_text = build_price_source_text(price_band)

    if sentence:
        print(f"  [LOCAL-354] {venue_name}: {sentence}")
        print(f"  [LOCAL-354]   source: {price_band.guide_name} ({source_url})")

    return sentence, source_url, source_text
