"""
LOCAL-686 — price-ladder config + snapping unit tests (pure, no DB).

Covers the ticket's test list for the server-side ladder:
  * the 34-step ladder exists as tiers 8..41 with round-dollar labels ("$35");
  * the seven legacy .99 tiers (1..7) are still valid but hidden from the picker
    (in_picker FALSE); the picker offers only the 34 ladder steps;
  * snapping: 37→35, 1→2, 2.4→2, 2.5→2 (tie down), 22→20, 23→25, 199→200,
    250→200, 112.5→100 (tie down), 113→125.

Pure functions over the code-default config (no cursor) — no DB needed.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import price_tiers as pt  # noqa: E402


# ─── 1. The ladder config ─────────────────────────────────────────────────────

def test_ladder_tiers_8_to_41_round_dollars():
    tiers = pt.load_price_tiers()  # no cursor → code defaults
    # 7 legacy + 34 ladder = 41 tiers.
    assert set(tiers.keys()) == set(range(1, 42))
    # The ladder tiers 8..41 are round-dollar, labelled "$N", product usd<N>.
    expected = (list(range(2, 21)) + [25, 30, 35, 40, 45, 50,
                                      60, 70, 80, 90, 100, 125, 150, 175, 200])
    assert len(expected) == 34
    for tier, dollars in zip(range(8, 42), expected):
        info = tiers[tier]
        assert info["price_usd"] == float(dollars)
        assert info["label"] == f"${dollars}"
        assert info["product_id"] == f"audioura.tour.usd{dollars}"
        assert info["in_picker"] is True


def test_legacy_tiers_valid_but_hidden_from_picker():
    tiers = pt.load_price_tiers()
    # The legacy .99 tiers stay as before and remain VALID…
    assert tiers[3]["label"] == "$4.99"
    assert tiers[6]["label"] == "$19.99"
    assert tiers[7]["label"] == "$49.99"
    assert pt.is_valid_tier(3) is True
    assert pt.is_valid_tier(7) is True
    # …but are NOT offered in the picker.
    for t in range(1, 8):
        assert tiers[t]["in_picker"] is False
    picker = pt.picker_tiers()
    assert set(picker.keys()) == set(range(8, 42))  # ladder only
    assert len(picker) == 34


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


# ─── 2. Snapping (the ticket's exact cases) ───────────────────────────────────

def test_snap_to_nearest_ladder_step():
    cases = {
        37: 35,       # Michael's headline example
        1: 2,         # below the floor → $2
        2.4: 2,
        2.5: 2,       # tie → round DOWN
        22: 20,
        23: 25,
        199: 200,
        250: 200,     # above the ceiling → $200
        112.5: 100,   # tie → round DOWN
        113: 125,
    }
    for amount, expected in cases.items():
        tier, price = pt.snap_to_ladder(amount)
        assert price == float(expected), f"{amount} → ${price}, expected ${expected}"
        # The chosen tier's own price matches the snapped price.
        assert pt.tier_info(tier)["price_usd"] == float(expected)


def test_snap_label_matches_step():
    assert pt.snap_label(37) == "$35"
    assert pt.snap_label(1) == "$2"
    assert pt.snap_label(250) == "$200"


def test_snap_garbage_input_defaults_to_lowest():
    tier, price = pt.snap_to_ladder("not a number")
    assert price == 2.0 and tier == 8
    tier, price = pt.snap_to_ladder(None)
    assert price == 2.0 and tier == 8


if __name__ == "__main__":
    # Allow a bare `python3 tests/test_local686_price_ladder.py` smoke run.
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
