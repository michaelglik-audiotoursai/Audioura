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

[LOCAL-686] A fine round-dollar LADDER (migration 026) is added as tiers 8..41:
$2..$20 /$1, $25..$50 /$5, $60..$100 /$10, $125..$200 /$25 = 34 steps, product
ids 'audioura.tour.usd<N>', labels "$N". The guide's picker shows ONLY the
ladder (price_tiers.in_picker TRUE); the seven legacy .99 tiers (1..7) stay
ACTIVE for already-priced tours but in_picker is FALSE. A typed price snaps to
the nearest ladder step (snap_to_ladder; ties round DOWN, clamp $2..$200).

Nothing here handles payouts, the store fee or Audioura's 10% split — that is a
later task (D624 §4). This is only what the buyer pays and which product unlocks
a tour.
"""

# The default tiers. tier -> {product_id, price_usd, label, in_picker}. The store
# product ids are CONSUMABLES in App Store Connect / the StoreKit config file;
# the app sells exactly these. Keep in lock-step with the migration seed rows.
#
# in_picker (LOCAL-686): TRUE if the guide's price PICKER offers this tier. The
# seven legacy .99 tiers (1..7, migrations 022/024) are kept ACTIVE so tours
# already priced with them keep their price, but in_picker is FALSE — the picker
# offers only the LADDER (tiers 8..41, migration 026).
DEFAULT_PRICE_TIERS = {
    # ── Legacy .99 tiers 1..7 (022/024) — ACTIVE but hidden from the picker ──
    1: {"product_id": "audioura.tour.tier1", "price_usd": 1.99, "label": "$1.99", "in_picker": False},
    2: {"product_id": "audioura.tour.tier2", "price_usd": 2.99, "label": "$2.99", "in_picker": False},
    3: {"product_id": "audioura.tour.tier3", "price_usd": 4.99, "label": "$4.99", "in_picker": False},
    4: {"product_id": "audioura.tour.tier4", "price_usd": 7.99, "label": "$7.99", "in_picker": False},
    5: {"product_id": "audioura.tour.tier5", "price_usd": 9.99, "label": "$9.99", "in_picker": False},
    6: {"product_id": "audioura.tour.tier6", "price_usd": 19.99, "label": "$19.99", "in_picker": False},
    7: {"product_id": "audioura.tour.tier7", "price_usd": 49.99, "label": "$49.99", "in_picker": False},
    # ── [LOCAL-686] the round-dollar LADDER (migration 026), tiers 8..41 ──────
    # $2..$20 /$1, $25..$50 /$5, $60..$100 /$10, $125..$200 /$25 = 34 steps.
    8: {"product_id": "audioura.tour.usd2", "price_usd": 2.0, "label": "$2", "in_picker": True},
    9: {"product_id": "audioura.tour.usd3", "price_usd": 3.0, "label": "$3", "in_picker": True},
    10: {"product_id": "audioura.tour.usd4", "price_usd": 4.0, "label": "$4", "in_picker": True},
    11: {"product_id": "audioura.tour.usd5", "price_usd": 5.0, "label": "$5", "in_picker": True},
    12: {"product_id": "audioura.tour.usd6", "price_usd": 6.0, "label": "$6", "in_picker": True},
    13: {"product_id": "audioura.tour.usd7", "price_usd": 7.0, "label": "$7", "in_picker": True},
    14: {"product_id": "audioura.tour.usd8", "price_usd": 8.0, "label": "$8", "in_picker": True},
    15: {"product_id": "audioura.tour.usd9", "price_usd": 9.0, "label": "$9", "in_picker": True},
    16: {"product_id": "audioura.tour.usd10", "price_usd": 10.0, "label": "$10", "in_picker": True},
    17: {"product_id": "audioura.tour.usd11", "price_usd": 11.0, "label": "$11", "in_picker": True},
    18: {"product_id": "audioura.tour.usd12", "price_usd": 12.0, "label": "$12", "in_picker": True},
    19: {"product_id": "audioura.tour.usd13", "price_usd": 13.0, "label": "$13", "in_picker": True},
    20: {"product_id": "audioura.tour.usd14", "price_usd": 14.0, "label": "$14", "in_picker": True},
    21: {"product_id": "audioura.tour.usd15", "price_usd": 15.0, "label": "$15", "in_picker": True},
    22: {"product_id": "audioura.tour.usd16", "price_usd": 16.0, "label": "$16", "in_picker": True},
    23: {"product_id": "audioura.tour.usd17", "price_usd": 17.0, "label": "$17", "in_picker": True},
    24: {"product_id": "audioura.tour.usd18", "price_usd": 18.0, "label": "$18", "in_picker": True},
    25: {"product_id": "audioura.tour.usd19", "price_usd": 19.0, "label": "$19", "in_picker": True},
    26: {"product_id": "audioura.tour.usd20", "price_usd": 20.0, "label": "$20", "in_picker": True},
    27: {"product_id": "audioura.tour.usd25", "price_usd": 25.0, "label": "$25", "in_picker": True},
    28: {"product_id": "audioura.tour.usd30", "price_usd": 30.0, "label": "$30", "in_picker": True},
    29: {"product_id": "audioura.tour.usd35", "price_usd": 35.0, "label": "$35", "in_picker": True},
    30: {"product_id": "audioura.tour.usd40", "price_usd": 40.0, "label": "$40", "in_picker": True},
    31: {"product_id": "audioura.tour.usd45", "price_usd": 45.0, "label": "$45", "in_picker": True},
    32: {"product_id": "audioura.tour.usd50", "price_usd": 50.0, "label": "$50", "in_picker": True},
    33: {"product_id": "audioura.tour.usd60", "price_usd": 60.0, "label": "$60", "in_picker": True},
    34: {"product_id": "audioura.tour.usd70", "price_usd": 70.0, "label": "$70", "in_picker": True},
    35: {"product_id": "audioura.tour.usd80", "price_usd": 80.0, "label": "$80", "in_picker": True},
    36: {"product_id": "audioura.tour.usd90", "price_usd": 90.0, "label": "$90", "in_picker": True},
    37: {"product_id": "audioura.tour.usd100", "price_usd": 100.0, "label": "$100", "in_picker": True},
    38: {"product_id": "audioura.tour.usd125", "price_usd": 125.0, "label": "$125", "in_picker": True},
    39: {"product_id": "audioura.tour.usd150", "price_usd": 150.0, "label": "$150", "in_picker": True},
    40: {"product_id": "audioura.tour.usd175", "price_usd": 175.0, "label": "$175", "in_picker": True},
    41: {"product_id": "audioura.tour.usd200", "price_usd": 200.0, "label": "$200", "in_picker": True},
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
                "SELECT tier, product_id, price_usd, label, "
                "       COALESCE(in_picker, TRUE) AS in_picker "
                "FROM price_tiers "
                "WHERE COALESCE(active, TRUE) = TRUE ORDER BY tier"
            )
            rows = cur.fetchall()
            if rows:
                return {
                    int(tier): {
                        "product_id": product_id,
                        "price_usd": float(price_usd),
                        "label": label or _format_label(price_usd),
                        "in_picker": bool(in_picker),
                    }
                    for tier, product_id, price_usd, label, in_picker in rows
                }
        except Exception:  # noqa: BLE001 — fall back to the constants on any error
            # A DB that predates the in_picker column (migration 026) still has
            # the price_tiers table; read it WITHOUT in_picker and default TRUE.
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
                            "in_picker": True,
                        }
                        for tier, product_id, price_usd, label in rows
                    }
            except Exception:  # noqa: BLE001
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


# ─── [LOCAL-686] The picker ladder + snapping ────────────────────────────────

# The ladder bounds (dollars). A typed price below $2 snaps to $2, above $200 to
# $200. These match the migration 026 ladder; the ladder itself is derived from
# the config (every in_picker tier), so there is one source of truth.
LADDER_MIN_USD = 2.0
LADDER_MAX_USD = 200.0


def picker_tiers(cur=None):
    """{tier: info} for only the tiers the guide's PICKER offers (in_picker TRUE).

    The 34 round-dollar ladder steps (migration 026). The seven legacy .99 tiers
    stay valid for already-priced tours but never appear here."""
    return {
        t: info
        for t, info in load_price_tiers(cur).items()
        if info.get("in_picker", True)
    }


def ladder_prices(cur=None):
    """The sorted list of (tier, price_usd) for the picker ladder — the snap
    targets. Sorted by price ascending (the ladder is monotonic in tier too)."""
    picks = picker_tiers(cur)
    return sorted(
        ((t, float(info["price_usd"])) for t, info in picks.items()),
        key=lambda tp: tp[1],
    )


def snap_to_ladder(amount, cur=None):
    """Snap a typed dollar [amount] to the NEAREST ladder step.

    Returns (tier, price_usd) of the chosen step, or (None, None) when the ladder
    is empty. Rules (D-pending, Michael's examples):
      * ties round DOWN (equidistant → the lower price): 2.5 → $2, 112.5 → $100;
      * below the ladder minimum snaps to the lowest step (1 → $2);
      * above the ladder maximum snaps to the highest step (250 → $200);
      * a non-numeric / None amount → the lowest step (a sane default).
    """
    ladder = ladder_prices(cur)
    if not ladder:
        return (None, None)
    try:
        amt = float(amount)
    except (TypeError, ValueError):
        return ladder[0]  # lowest step for garbage input

    # Clamp to the ladder's own range (below min → first, above max → last).
    if amt <= ladder[0][1]:
        return ladder[0]
    if amt >= ladder[-1][1]:
        return ladder[-1]

    # Nearest step; on an exact tie pick the LOWER price (round down).
    best = ladder[0]
    best_dist = abs(amt - best[1])
    for tier, price in ladder[1:]:
        dist = abs(amt - price)
        # Strictly closer wins; an equal distance does NOT replace the lower
        # price already held (ladder is ascending → first-seen is lower).
        if dist < best_dist:
            best, best_dist = (tier, price), dist
    return best


def snap_label(amount, cur=None):
    """The display label ('$35') of the nearest ladder step for a typed amount,
    or 'Free' when the ladder is empty."""
    tier, _price = snap_to_ladder(amount, cur)
    if tier is None:
        return "Free"
    return label_for_tier(tier, cur)
