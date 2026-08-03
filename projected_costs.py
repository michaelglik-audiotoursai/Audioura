"""
Projected Costs — pre-flight cost estimates for overdraft floor enforcement.
============================================================================
LOCAL-163: Michael's overdraft rule requires checking BEFORE work begins
whether completing an operation would breach the −$2.00 floor.

D15 records the limitation: the existing ceiling fires AFTER generation,
so it cannot abort work. The pre-flight check here runs BEFORE spend and
uses conservative estimates derived from measured production data.

These are PROJECTIONS — estimates with bounded error. The $2.00 floor is
generous relative to maximum observed costs:
  - Tour:        ~$0.068 our cost → ~$0.34 user charge (max observed ~$0.08 → $0.40)
  - Translation: ~$0.31–$0.54 → $1.55–$2.70 user charge (varies by text length)
  - Article:     ~$0.006–$0.011 → $0.03–$0.06 user charge

Error analysis:
  - Tour estimate $0.34 has a max observed error of ~$0.06 (18%)
  - Translation estimate $2.70 is the UPPER bound — most are ~$1.55
  - Article estimate $0.06 has negligible error (<$0.03)

The $2.00 floor absorbs worst-case estimate error for tours and articles.
Translation is the only operation that could theoretically breach the floor
from a single operation, but even at the upper bound ($2.70), the pre-flight
check correctly refuses when balance − $2.70 < −$2.00 (i.e. balance < $0.70).

All values are in USD (user-facing charge, i.e. our_cost × 5).
"""

from decimal import Decimal

# ─── Projected user charges per operation type ────────────────────────────────
# These are the USER-FACING charge (our_cost × PRICING_MULTIPLIER).
# Source: cost_rates.py measured figures + PRICING_MULTIPLIER=5.0.
#
# Conservative: use the UPPER end of observed range to avoid under-predicting
# (which would allow work that then breaches the floor).

PROJECTED_COSTS = {
    # Tour: measured ~$0.068 our cost → $0.34 user charge
    # Max observed: ~$0.08 → $0.40. Use $0.40 for safety.
    "tour_generate": Decimal("0.40"),

    # Translation: measured $0.31–$0.54 our cost → $1.55–$2.70 user charge
    # Use upper bound $2.70 (long text, two-pass mode).
    "translation_generate": Decimal("2.70"),

    # News article: measured ~$0.006–$0.011 our cost → $0.03–$0.06 user charge
    # Use $0.06 for safety.
    "news_generate": Decimal("0.06"),

    # Photo extension: not yet measured; estimate similar to article.
    "photo_extension": Decimal("0.10"),

    # Cache hits always $0.00 — no projection needed, but include for completeness.
    "tour_cache_hit": Decimal("0.00"),
    "translation_cache_hit": Decimal("0.00"),
    "news_cache_hit": Decimal("0.00"),
}

# The overdraft floor: balance may not go below this after a projected spend.
# Michael's rule (D41): floor at −$2.00.
OVERDRAFT_FLOOR_CENTS = -200  # −$2.00 in integer cents


def get_projected_cost_cents(operation_type: str) -> int:
    """Get the projected user-facing charge in cents for an operation type.

    Returns the projected cost in integer cents. If the operation type is
    unknown, returns 0 (fail-open on projection — the charge() function
    still enforces the floor at write time).
    """
    cost_usd = PROJECTED_COSTS.get(operation_type, Decimal("0.00"))
    return int(cost_usd * 100)


def would_breach_floor(balance_cents: int, operation_type: str) -> bool:
    """Return True if performing this operation would breach the −$2.00 floor.

    The check: balance − projected_cost < OVERDRAFT_FLOOR_CENTS

    If True, the operation must be REFUSED before any work begins.
    If False, the operation may proceed and the balance may go negative
    (but not below the floor based on the projection).
    """
    projected = get_projected_cost_cents(operation_type)
    return (balance_cents - projected) < OVERDRAFT_FLOOR_CENTS
