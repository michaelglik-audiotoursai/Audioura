#!/usr/bin/env python3
"""
price_tiers.py — the price-tier config of record (LOCAL-677, D624 / D652).

Curator paid tours sell at one of a FIXED set of tiers. Per-tour products cannot
be created on the fly, so the app ships a fixed set of consumable store products
(audioura.tour.tier1 … tier5) and the server records which tour a given verified
transaction unlocked (tour_unlocks). This module is the single place the tier
NUMBER (1..7) maps to a store product id, a dollar price and a display label.

D652 (LEAD defaults, Michael owns the numbers): $1.99 / $2.99 / $4.99 / $7.99 /
$9.99. These live as ROWS in the price_tiers table (migration 022) so Michael
changes a price with one UPDATE and no redeploy. The constants here are the
FALLBACK used only when that table is absent (a DB that predates migration 022),
mirroring how the other services keep self-healing DDL + code defaults in step.

Nothing here handles payouts, the store fee or Audioura's 10% split — that is a
later task (D624 §4). This is only what the buyer pays and which product unlocks
a tour.
"""

# The default tiers (D652). tier -> {product_id, price_usd, label}. The store
# product ids are CONSUMABLES in App Store Connect / the StoreKit config file;
# the app sells exactly these. Keep in lock-step with migration 022's seed rows.
DEFAULT_PRICE_TIERS = {
    1: {"product_id": "audioura.tour.tier1", "price_usd": 1.99, "label": "$1.99"},
    2: {"product_id": "audioura.tour.tier2", "price_usd": 2.99, "label": "$2.99"},
    3: {"product_id": "audioura.tour.tier3", "price_usd": 4.99, "label": "$4.99"},
    4: {"product_id": "audioura.tour.tier4", "price_usd": 7.99, "label": "$7.99"},
    5: {"product_id": "audioura.tour.tier5", "price_usd": 9.99, "label": "$9.99"},
    # [LOCAL-684] migration 024 (Michael, 2026-10-14: "add $20 and $50").
    6: {"product_id": "audioura.tour.tier6", "price_usd": 19.99, "label": "$19.99"},
    7: {"product_id": "audioura.tour.tier7", "price_usd": 49.99, "label": "$49.99"},
}

# The valid tier numbers, in order.
TIER_NUMBERS = tuple(sorted(DEFAULT_PRICE_TIERS.keys()))

# Reverse map: store product id -> tier number (for the purchase-verify path,
# which receives a store product id and must find the tier/price it unlocked).
DEFAULT_PRODUCT_TO_TIER = {
    v["product_id"]: t for t, v in DEFAULT_PRICE_TIERS.items()
}


def _format_label(price_usd):
    """Render a dollar label like '$4.99' from a numeric price."""
    try:
        return f"${float(price_usd):.2f}"
    except (TypeError, ValueError):
        return ""


def _has_price_tiers_table(cur):
    """True if the price_tiers config table exists. Cheap probe; the caller
    falls back to DEFAULT_PRICE_TIERS when it does not (pre-022 DB)."""
    try:
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'price_tiers'"
        )
        return cur.fetchone() is not None
    except Exception:  # noqa: BLE001 — a probe must never raise
        return False


def load_price_tiers(cur=None):
    """Return {tier: {product_id, price_usd, label}} for all ACTIVE tiers.

    Reads the price_tiers table when a cursor is given and the table exists;
    otherwise returns the DEFAULT_PRICE_TIERS constants (pre-022 DB, or a pure
    unit test with no DB). The DB is authoritative when present so Michael's SQL
    edits take effect with no redeploy.
    """
    if cur is not None and _has_price_tiers_table(cur):
        try:
            cur.execute(
                "SELECT tier, product_id, price_usd, label FROM price_tiers "
                "WHERE COALESCE(active, TRUE) = TRUE ORDER BY tier"
            )
            rows = cur.fetchall()
            if rows:
                return {
                    int(tier): {
                        "product_id": product_id,
                        "price_usd": float(price_usd),
                        "label": label or _format_label(price_usd),
                    }
                    for tier, product_id, price_usd, label in rows
                }
        except Exception:  # noqa: BLE001 — fall back to the constants on any error
            pass
    # Fallback: the code defaults (deep-ish copy so a caller cannot mutate ours).
    return {t: dict(v) for t, v in DEFAULT_PRICE_TIERS.items()}


def valid_tiers(cur=None):
    """The set of valid tier numbers (keys of the active config)."""
    return set(load_price_tiers(cur).keys())


def is_valid_tier(tier, cur=None):
    """True if `tier` is a valid, active tier number. None (free) is NOT a tier
    — callers treat None as 'clear the price' explicitly, not as a tier."""
    if tier is None:
        return False
    try:
        tier_int = int(tier)
    except (TypeError, ValueError):
        return False
    if tier_int != float(tier):  # reject 2.5, "2.0" etc.
        return False
    return tier_int in valid_tiers(cur)


def tier_info(tier, cur=None):
    """{product_id, price_usd, label} for one tier, or None if not a valid tier."""
    if not is_valid_tier(tier, cur):
        return None
    return load_price_tiers(cur).get(int(tier))


def price_for_tier(tier, cur=None):
    """The dollar price for a tier, or None (free / unknown tier)."""
    info = tier_info(tier, cur)
    return info["price_usd"] if info else None


def label_for_tier(tier, cur=None):
    """The display label ('$4.99') for a tier, or 'Free' for a NULL/invalid tier."""
    if tier is None:
        return "Free"
    info = tier_info(tier, cur)
    return info["label"] if info else "Free"


def product_to_tier(cur=None):
    """{store product id -> tier number} from the active config."""
    return {v["product_id"]: t for t, v in load_price_tiers(cur).items()}


def tier_for_product(product_id, cur=None):
    """The tier number a store product id unlocks, or None if it is not a
    tour-tier product (so the purchase-verify path can tell a tour purchase from
    a level pack like 'l3_pack_10')."""
    if not product_id:
        return None
    return product_to_tier(cur).get(product_id)
