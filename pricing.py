"""
Pricing Engine — turn metered cost into user-facing charge.
============================================================
Implements the Subscribed pricing rule:

    user_charge = our_cost × PRICING_MULTIPLIER

All values use `decimal.Decimal` internally. Rounding happens ONCE at the
charge boundary (never per component). Banker's rounding (ROUND_HALF_EVEN)
is used — it eliminates systematic bias over large transaction volumes and
is the IEEE 754 default. A float balance would accumulate drift; Decimal
with explicit quantize does not.

Cache-hit charging (LOCAL-200, extends D45):
  Michael Q&A-2: "we should take the same amount in order not to confuse the
  user" — reason: "why only the first user is paying?"
  Michael Q&A-3, answer 3: tour reuse also charges.

  All cache hits (translation, tour, news) charge the user the same as a
  fresh generation. Our cost remains $0.00 — that is accounting truth. The
  user charge is fairness between users, not margin.

  The fresh_cost_usd basis comes from the original generation's cost_ledger
  row. If no row exists (pre-metering tours) or the row is implausible
  (pre-LOCAL-197 inflated rates), charge $0.00 for safety.

This module does NOT mutate balances, write to a wallet, or touch any
ledger. It computes a price from a cost and returns it. LOCAL-66 owns the
wallet.
"""

import os
from decimal import Decimal, ROUND_HALF_EVEN, InvalidOperation
from typing import Optional

from cost_rates import CACHE_HIT_COST_USD

# ---------------------------------------------------------------------------
# Configuration — all runtime-tunable via environment variables.
# A code change is never required to adjust pricing.
# ---------------------------------------------------------------------------

def _env_decimal(key: str, default: str) -> Decimal:
    """Read a Decimal config value from environment, with fallback."""
    raw = os.environ.get(key, default)
    try:
        return Decimal(raw)
    except InvalidOperation:
        # Bad env value — fall back to default rather than crash the service.
        return Decimal(default)


def get_pricing_multiplier() -> Decimal:
    """Current pricing multiplier (reads env each call — runtime-tunable)."""
    return _env_decimal("PRICING_MULTIPLIER", "5.0")


def get_cache_hit_cost() -> Decimal:
    """Cost to charge for a cache hit (always 0 per design)."""
    return _env_decimal("CACHE_HIT_COST_USD", "0.00")


# The quantum for USD: $0.01 (one cent)
_CENT = Decimal("0.01")

# Operation types that charge on cache hit when fresh_cost_usd is provided.
# LOCAL-200: extends D45 (translation-only) to tours and news.
_CACHE_HIT_CHARGE_TYPES = frozenset([
    "translation_cache_hit",
    "tour_cache_hit",
    "news_cache_hit",
])


# ---------------------------------------------------------------------------
# Core pricing function
# ---------------------------------------------------------------------------

def compute_user_charge(
    our_cost_usd: "Decimal | float | str",
    cache_hit: bool,
    operation_type: str,
    description: Optional[str] = None,
    fresh_cost_usd: "Decimal | float | str | None" = None,
) -> dict:
    """Compute the user-facing charge for a single metered operation.

    Args:
        our_cost_usd: Our actual cost in USD (from cost_meter / cost_ledger).
                      Accepts Decimal, float, or numeric string.
        cache_hit: True if this was served from cache.
        operation_type: e.g. "tour_generate", "translation_cache_hit".
                        Used for the human-readable description.
        description: Optional human-readable label for the transaction list,
                     e.g. "Tour: French Riviera biking". If not provided,
                     a default is generated from operation_type.
        fresh_cost_usd: For cache hits (D45/LOCAL-200): the cost of the
                        original fresh generation. The user is charged as if
                        it were fresh, even though our_cost is $0.00. Required
                        when operation_type is in _CACHE_HIT_CHARGE_TYPES and
                        a charge should be levied. If None, cache hit charges
                        $0.00 (safe fallback for pre-metering content).

    Returns:
        dict with:
            - user_charge_usd: Decimal — the charge to the user, rounded to
              the cent using banker's rounding.
            - user_charge_cents: int — same value as integer cents (for
              storage in integer-cent ledger columns).
            - our_cost_usd: Decimal — the input cost as Decimal.
            - multiplier: Decimal — the multiplier applied.
            - cache_hit: bool
            - operation_type: str
            - description: str — human-readable label for the wallet
              transaction list.
    """
    # Normalise input to Decimal — never float internally.
    if isinstance(our_cost_usd, float):
        # Convert float via string to preserve the displayed value.
        # Decimal(0.0633) gives 0.0632999... ; Decimal("0.0633") is exact.
        cost = Decimal(str(our_cost_usd))
    elif isinstance(our_cost_usd, Decimal):
        cost = our_cost_usd
    else:
        cost = Decimal(str(our_cost_usd))

    multiplier = get_pricing_multiplier()

    # --- Cache hit with fresh_cost_usd basis (D45, LOCAL-200) ---
    # Michael Q&A-2: "we should take the same amount" — fairness between users.
    # our_cost stays $0.00 (accounting truth). User charge = fresh_cost × multiplier.
    # Applies to: translation_cache_hit (D45), tour_cache_hit, news_cache_hit (LOCAL-200).
    if cache_hit and fresh_cost_usd is not None and operation_type in _CACHE_HIT_CHARGE_TYPES:
        if isinstance(fresh_cost_usd, float):
            basis = Decimal(str(fresh_cost_usd))
        elif isinstance(fresh_cost_usd, Decimal):
            basis = fresh_cost_usd
        else:
            basis = Decimal(str(fresh_cost_usd))
        raw_charge = basis * multiplier
        charge = raw_charge.quantize(_CENT, rounding=ROUND_HALF_EVEN)
    # --- Cache hit without basis: charge $0.00 (no ledger row / implausible) ---
    elif cache_hit:
        charge = Decimal("0.00")
    else:
        # Fresh operation: charge = our_cost × multiplier
        raw_charge = cost * multiplier
        # Quantize to $0.01 using banker's rounding.
        charge = raw_charge.quantize(_CENT, rounding=ROUND_HALF_EVEN)

    # Integer cents — multiply by 100, convert to int.
    charge_cents = int(charge * 100)

    # Human-readable description for the Wallet transaction list.
    if description is None:
        description = _default_description(operation_type)

    return {
        "user_charge_usd": charge,
        "user_charge_cents": charge_cents,
        "our_cost_usd": cost,
        "multiplier": multiplier,
        "cache_hit": cache_hit,
        "operation_type": operation_type,
        "description": description,
    }


# ---------------------------------------------------------------------------
# Batch pricing (for ledger round-trip verification)
# ---------------------------------------------------------------------------

def compute_charges_for_ledger_rows(rows: list[dict]) -> list[dict]:
    """Given a list of cost_ledger row dicts, compute the user charge for each.

    Each row dict must have at minimum:
        - our_cost_usd (float or Decimal)
        - cache_hit (bool)
        - operation_type (str)

    Optionally:
        - description (str)

    Returns a list of result dicts from compute_user_charge, one per row,
    in the same order.
    """
    results = []
    for row in rows:
        result = compute_user_charge(
            our_cost_usd=row["our_cost_usd"],
            cache_hit=row["cache_hit"],
            operation_type=row["operation_type"],
            description=row.get("description"),
        )
        # Carry through any extra fields from the row (e.g. id, user_id).
        result["ledger_id"] = row.get("id")
        result["user_id"] = row.get("user_id")
        result["job_id"] = row.get("job_id")
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# Description generator
# ---------------------------------------------------------------------------

_OPERATION_LABELS = {
    "tour_generate": "Tour generation",
    "tour_cache_hit": "Tour (cached — same charge)",
    "translation_generate": "Translation",
    "translation_cache_hit": "Translation (cached — same charge)",
    "news_generate": "News article",
    "news_cache_hit": "News article (cached — same charge)",
    "photo_extension": "Photo tour extension",
}


def _default_description(operation_type: str) -> str:
    """Generate a human-readable default description for a charge."""
    label = _OPERATION_LABELS.get(operation_type, operation_type.replace("_", " ").title())
    return label
