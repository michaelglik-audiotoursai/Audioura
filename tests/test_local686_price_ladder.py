"""
LOCAL-686 — price-ladder config + snapping unit tests (pure, no DB).

[LOCAL-734] Release plan L4 NARROWS the picker to the tour products that exist on
the stores now ($3/$5/$10/$20/$50). LOCAL-686 originally opened the whole 34-step
ladder; this file was updated so it asserts the L4 policy instead:
  * all 34 ladder tiers + 7 legacy tiers still EXIST and are VALID (so a tour
    already priced at any of them keeps its price — no DB rewrite);
  * the picker offers ONLY the 5 Apple-live steps (price_tiers.in_picker, capped
    by price_tiers.APPLE_LIVE_TOUR_PRODUCTS);
  * snapping snaps to the NEAREST OFFERED (Apple-live) step, ties round DOWN.

Pure functions over the code-default config (no cursor) — no DB needed.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import price_tiers as pt  # noqa: E402


# The Apple-live tour products the picker offers after L4 (LOCAL-734).
APPLE_LIVE_TIERS = {9: 3.0, 11: 5.0, 16: 10.0, 26: 20.0, 32: 50.0}


# ─── 1. The ladder config still exists in full (tiers stay VALID) ─────────────

def test_ladder_tiers_8_to_41_round_dollars():
    tiers = pt.load_price_tiers()  # no cursor → code defaults
    # 7 legacy + 34 ladder = 41 tiers, all present and valid.
    assert set(tiers.keys()) == set(range(1, 42))
    expected = (list(range(2, 21)) + [25, 30, 35, 40, 45, 50,
                                      60, 70, 80, 90, 100, 125, 150, 175, 200])
    assert len(expected) == 34
    for tier, dollars in zip(range(8, 42), expected):
        info = tiers[tier]
        assert info["price_usd"] == float(dollars)
        assert info["label"] == f"${dollars}"
        assert info["product_id"] == f"audioura.tour.usd{dollars}"


# ─── 2. [LOCAL-734] The picker is capped to the Apple-live steps ──────────────

def test_picker_offers_only_apple_live_steps():
    picker = pt.picker_tiers()
    assert set(picker.keys()) == set(APPLE_LIVE_TIERS.keys())
    assert len(picker) == 5
    for tier, dollars in APPLE_LIVE_TIERS.items():
        assert picker[tier]["price_usd"] == dollars
        assert picker[tier]["in_picker"] is True
    # Every offered product is on the Apple-live allowlist, and nothing else is.
    offered_products = {info["product_id"] for info in picker.values()}
    assert offered_products == set(pt.APPLE_LIVE_TOUR_PRODUCTS)


def test_non_live_tiers_valid_but_hidden_from_picker():
    tiers = pt.load_price_tiers()
    # Legacy .99 tiers stay valid…
    assert tiers[3]["label"] == "$4.99"
    assert pt.is_valid_tier(3) is True
    assert pt.is_valid_tier(7) is True
    # …and so do the non-live ladder steps (e.g. $7, $35) — a tour priced there
    # keeps its price.
    assert pt.is_valid_tier(13) is True   # $7
    assert pt.is_valid_tier(29) is True   # $35
    # But none of them appear in the picker.
    for t in list(range(1, 9)) + [13, 29, 41]:
        assert tiers[t]["in_picker"] is False


def test_tier_range_widened_to_41():
    assert pt.is_valid_tier(41) is True
    assert pt.is_valid_tier(42) is False
    assert pt.is_valid_tier(8) is True
    assert pt.is_valid_tier(0) is False
    assert pt.is_valid_tier(None) is False
    assert pt.is_valid_tier(2.5) is False


def test_product_to_tier_roundtrips_ladder():
    assert pt.tier_for_product("audioura.tour.usd35") == 29
    assert pt.tier_for_product("audioura.tour.usd2") == 8
    assert pt.tier_for_product("audioura.tour.usd200") == 41
    # Legacy ids still resolve.
    assert pt.tier_for_product("audioura.tour.tier3") == 3
    # A non-tour product is None.
    assert pt.tier_for_product("l3_pack_10") is None


# ─── 3. Snapping — to the NEAREST OFFERED (Apple-live) step, ties round DOWN ──

def test_snap_to_nearest_offered_step():
    # Offered steps are $3, $5, $10, $20, $50.
    cases = {
        1: 3,         # below the floor → lowest offered ($3)
        3: 3,
        3.9: 3,       # nearer $3 than $5
        4: 3,         # tie between $3 and $5 → round DOWN
        4.5: 5,
        7: 5,         # nearer $5 than $10 (|7-5|=2 < |7-10|=3)
        7.5: 5,       # tie between $5 and $10 → round DOWN
        8: 10,
        14: 10,       # nearer $10 than $20
        15: 10,       # tie between $10 and $20 → round DOWN
        16: 20,
        34: 20,       # nearer $20 than $50 (|34-20|=14 < |34-50|=16)
        35: 20,       # tie → round DOWN
        36: 50,
        500: 50,      # above the ceiling → highest offered ($50)
    }
    for amount, expected in cases.items():
        tier, price = pt.snap_to_ladder(amount)
        assert price == float(expected), f"{amount} → ${price}, expected ${expected}"
        assert pt.tier_info(tier)["price_usd"] == float(expected)


def test_snap_label_matches_step():
    assert pt.snap_label(7) == "$5"
    assert pt.snap_label(1) == "$3"
    assert pt.snap_label(500) == "$50"


def test_snap_garbage_input_defaults_to_lowest():
    tier, price = pt.snap_to_ladder("not a number")
    assert price == 3.0 and tier == 9
    tier, price = pt.snap_to_ladder(None)
    assert price == 3.0 and tier == 9


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
