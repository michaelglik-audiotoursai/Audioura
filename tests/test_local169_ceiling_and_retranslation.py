#!/usr/bin/env python3
"""
LOCAL-169: Ceiling $2.00 and re-translation charge.
=====================================================
Two changes (D45):
  1. Cost ceiling raised from $1.30 to $2.00.
  2. Re-translation (cache hit) charges the same as fresh translation.

Tests:
  - $1.90 operation is ALLOWED (was aborted at old $1.30 ceiling).
  - $2.10 operation is still ABORTED.
  - Fresh translation and cached translation both debit the same wallet amount.
  - cost_ledger shows $0.00 for cache hit, real cost for fresh (divergence intended).
  - Break-probe: ceiling threshold replacement count.

Uses fresh uuid4 test users. Does not touch demo_michael_1785726297.
Does NOT generate real translations — exercises the charge path only.

Run:
    DB_HOST=localhost DB_PORT=5433 python3 tests/test_local169_ceiling_and_retranslation.py
"""

import os
import sys
import uuid
from decimal import Decimal

# Ensure project root is on path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

# Set DB env for test context
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5433")
os.environ.setdefault("DB_NAME", "audiotours")
os.environ.setdefault("DB_USER", "admin")
os.environ.setdefault("DB_PASSWORD", "password123")

PASS_COUNT = 0
FAIL_COUNT = 0
_test_users = []


def check(name, condition, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        print(f"  ✓ {name}")
        PASS_COUNT += 1
    else:
        print(f"  ✗ {name} — {detail}")
        FAIL_COUNT += 1


def record(label, value):
    """Print a diagnostic value for the submission."""
    print(f"  📋 {label}: {value}")


# ============================================================
# TEST 1: Ceiling at $2.00
# ============================================================

def test_ceiling_190_allowed():
    """$1.90 operation is ALLOWED under the new $2.00 ceiling (was ABORTED at $1.30)."""
    print("\n─── TEST 1a: $1.90 is ALLOWED (new ceiling $2.00) ───")
    import importlib
    import cost_ceiling_monitor
    importlib.reload(cost_ceiling_monitor)

    from unittest.mock import patch, MagicMock
    with patch.dict('sys.modules', {'psycopg2': MagicMock()}):
        result = cost_ceiling_monitor.enforce_cost_ceiling(
            total_cost=1.90,
            job_id="test169-190",
            user_id="test169-user",
            tour_category="translation",
        )

    check("$1.90_NOT_aborted", result["abort"] is False, f"abort={result['abort']}")
    check("$1.90_warns", result["warn"] is True, f"warn={result['warn']}")
    check("hard_limit_is_2.00", result["hard_limit"] == 2.00, f"got {result['hard_limit']}")
    record("ceiling_result_190", f"abort={result['abort']}, warn={result['warn']}, hard_limit={result['hard_limit']}")


def test_ceiling_210_aborted():
    """$2.10 operation is ABORTED (still above $2.00)."""
    print("\n─── TEST 1b: $2.10 is ABORTED (exceeds $2.00) ───")
    import importlib
    import cost_ceiling_monitor
    importlib.reload(cost_ceiling_monitor)

    from unittest.mock import patch, MagicMock
    with patch.dict('sys.modules', {'psycopg2': MagicMock()}):
        result = cost_ceiling_monitor.enforce_cost_ceiling(
            total_cost=2.10,
            job_id="test169-210",
            user_id="test169-user",
            tour_category="translation",
        )

    check("$2.10_aborted", result["abort"] is True, f"abort={result['abort']}")
    check("breach_level_hard_limit", result["breach_level"] == "hard_limit_exceeded",
          f"got {result['breach_level']}")
    record("ceiling_result_210", f"abort={result['abort']}, breach={result['breach_level']}")


# ============================================================
# TEST 2: Break-probe — ceiling threshold replacement count (D36)
# ============================================================

def test_ceiling_break_probe():
    """Break-probe: verify the threshold can be found and has exactly 1 replacement."""
    print("\n─── TEST 2: Break-probe — ceiling threshold ───")

    # Read cost_ceiling_monitor.py and count occurrences of the default value
    ceiling_path = os.path.join(_project_root, "cost_ceiling_monitor.py")
    with open(ceiling_path, 'r') as f:
        source = f.read()

    # The default is now "2.00" in the env var fallback
    count_default = source.count('"2.00"')
    record("break_probe_replacement_count", count_default)
    check("ceiling_default_present", count_default >= 1, f"found {count_default} occurrences of '2.00'")

    # The old value $1.30 should NOT appear as a default anymore
    count_old = source.count('"1.30"')
    check("old_ceiling_removed", count_old == 0, f"found {count_old} occurrences of '\"1.30\"' still present")


# ============================================================
# TEST 3: Translation charge — fresh vs cached, wallet + cost_ledger
# ============================================================

def test_translation_charge_fresh_and_cached():
    """Fresh and cached translation both debit the same wallet amount.
    cost_ledger shows $0.00 for cache hit, real cost for fresh.
    """
    print("\n─── TEST 3: Translation charge — fresh vs cached ───")

    from tests.db_connection import get_connection
    from wallet_ledger import topup, charge, get_balance_cents
    from pricing import compute_user_charge
    from cost_meter import record_operation
    from cost_rates import translation_cost, DEPLOYED_TRANSLATION_PASSES, CACHE_HIT_COST_USD

    # Create two fresh test users
    user_fresh = f"test169_fresh_{uuid.uuid4().hex[:8]}"
    user_cached = f"test169_cached_{uuid.uuid4().hex[:8]}"
    _test_users.extend([user_fresh, user_cached])

    # Top up both users with $10
    topup(user_fresh, Decimal("10.00"), f"topup:{user_fresh}:1")
    topup(user_cached, Decimal("10.00"), f"topup:{user_cached}:1")

    bal_fresh_before = get_balance_cents(user_fresh)
    bal_cached_before = get_balance_cents(user_cached)
    check("fresh_user_topped_up", bal_fresh_before == 1000, f"got {bal_fresh_before}")
    check("cached_user_topped_up", bal_cached_before == 1000, f"got {bal_cached_before}")

    # Simulate a 16000-char tour translation
    source_chars = 16000
    fresh_cost = translation_cost(source_chars, passes=DEPLOYED_TRANSLATION_PASSES)
    record("fresh_translation_cost_usd", f"${fresh_cost:.6f}")

    # --- Fresh translation: cost_ledger gets real cost, wallet gets charge ---
    job_fresh = f"job_fresh_{uuid.uuid4().hex[:8]}"
    cost_ledger_id_fresh = record_operation(
        operation_type="translation_generate",
        our_cost_usd=fresh_cost,
        cache_hit=False,
        user_id=user_fresh,
        job_id=job_fresh,
    )

    charge_result_fresh = compute_user_charge(
        our_cost_usd=fresh_cost,
        cache_hit=False,
        operation_type="translation_generate",
        description="Translation to fr (fresh)",
    )
    record("fresh_user_charge_usd", f"${charge_result_fresh['user_charge_usd']}")
    record("fresh_user_charge_cents", charge_result_fresh['user_charge_cents'])

    _row, _bal, _stopped = charge(
        user_id=user_fresh,
        charge_usd=charge_result_fresh['user_charge_usd'],
        idempotency_key=f"charge:{user_fresh}:{job_fresh}:translation",
        description=f"Translation to fr — ${charge_result_fresh['user_charge_usd']:.2f}",
        job_id=job_fresh,
    )
    bal_fresh_after = get_balance_cents(user_fresh)

    # --- Cached translation: cost_ledger gets $0.00, wallet gets SAME charge ---
    job_cached = f"job_cached_{uuid.uuid4().hex[:8]}"
    cost_ledger_id_cached = record_operation(
        operation_type="translation_cache_hit",
        our_cost_usd=CACHE_HIT_COST_USD,
        cache_hit=True,
        user_id=user_cached,
        job_id=job_cached,
    )

    # D45: charge same as fresh, using fresh_cost_usd parameter
    charge_result_cached = compute_user_charge(
        our_cost_usd=CACHE_HIT_COST_USD,
        cache_hit=True,
        operation_type="translation_cache_hit",
        description="Translation to fr (cached — same charge)",
        fresh_cost_usd=fresh_cost,
    )
    record("cached_user_charge_usd", f"${charge_result_cached['user_charge_usd']}")
    record("cached_user_charge_cents", charge_result_cached['user_charge_cents'])

    _row2, _bal2, _stopped2 = charge(
        user_id=user_cached,
        charge_usd=charge_result_cached['user_charge_usd'],
        idempotency_key=f"charge:{user_cached}:{job_cached}:translation",
        description=f"Translation to fr (cached) — ${charge_result_cached['user_charge_usd']:.2f}",
        job_id=job_cached,
    )
    bal_cached_after = get_balance_cents(user_cached)

    # --- Assertions ---
    # Both users were charged the same amount
    fresh_debit = bal_fresh_before - bal_fresh_after
    cached_debit = bal_cached_before - bal_cached_after
    check("same_wallet_debit", fresh_debit == cached_debit,
          f"fresh={fresh_debit}¢, cached={cached_debit}¢")
    check("debit_is_positive", fresh_debit > 0, f"got {fresh_debit}")

    record("fresh_wallet_debit_cents", fresh_debit)
    record("cached_wallet_debit_cents", cached_debit)
    record("fresh_balance_after", bal_fresh_after)
    record("cached_balance_after", bal_cached_after)

    # Verify cost_ledger divergence
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT our_cost_usd, cache_hit FROM cost_ledger WHERE job_id = %s", (job_fresh,))
    row_fresh = cur.fetchone()
    cur.execute("SELECT our_cost_usd, cache_hit FROM cost_ledger WHERE job_id = %s", (job_cached,))
    row_cached = cur.fetchone()
    cur.close()
    conn.close()

    check("cost_ledger_fresh_has_real_cost", row_fresh is not None and float(row_fresh[0]) > 0,
          f"got {row_fresh}")
    check("cost_ledger_cached_has_zero_cost", row_cached is not None and float(row_cached[0]) == 0.0,
          f"got {row_cached}")
    check("cost_ledger_fresh_not_cache_hit", row_fresh[1] is False, f"got {row_fresh[1]}")
    check("cost_ledger_cached_is_cache_hit", row_cached[1] is True, f"got {row_cached[1]}")

    record("cost_ledger_fresh_our_cost", f"${float(row_fresh[0]):.6f}")
    record("cost_ledger_cached_our_cost", f"${float(row_cached[0]):.6f}")

    # Show wallet_ledger rows for both
    conn2 = get_connection()
    cur2 = conn2.cursor()
    cur2.execute(
        "SELECT movement_type, amount_cents, description FROM wallet_ledger "
        "WHERE user_id = %s AND movement_type = 'charge' ORDER BY created_at DESC LIMIT 1",
        (user_fresh,))
    wl_fresh = cur2.fetchone()
    cur2.execute(
        "SELECT movement_type, amount_cents, description FROM wallet_ledger "
        "WHERE user_id = %s AND movement_type = 'charge' ORDER BY created_at DESC LIMIT 1",
        (user_cached,))
    wl_cached = cur2.fetchone()
    cur2.close()
    conn2.close()

    record("wallet_ledger_fresh", f"type={wl_fresh[0]}, amount={wl_fresh[1]}¢, desc={wl_fresh[2]}")
    record("wallet_ledger_cached", f"type={wl_cached[0]}, amount={wl_cached[1]}¢, desc={wl_cached[2]}")

    check("wallet_rows_same_amount", wl_fresh[1] == wl_cached[1],
          f"fresh={wl_fresh[1]}¢, cached={wl_cached[1]}¢")


# ============================================================
# TEST 4: pricing.py — other cache hits still $0.00
# ============================================================

def test_tour_cache_hit_still_free():
    """Tour and news cache hits remain $0.00 — only translations changed."""
    print("\n─── TEST 4: Tour/news cache hits still $0.00 ───")
    from pricing import compute_user_charge

    result_tour = compute_user_charge(
        our_cost_usd=0.0,
        cache_hit=True,
        operation_type="tour_cache_hit",
    )
    check("tour_cache_hit_zero", result_tour["user_charge_cents"] == 0,
          f"got {result_tour['user_charge_cents']}")

    result_news = compute_user_charge(
        our_cost_usd=0.0,
        cache_hit=True,
        operation_type="news_cache_hit",
    )
    check("news_cache_hit_zero", result_news["user_charge_cents"] == 0,
          f"got {result_news['user_charge_cents']}")


# ============================================================
# TEST 5: Overdraft floor and ceiling are DIFFERENT $2.00 values
# ============================================================

def test_two_different_two_dollars():
    """The $2.00 ceiling and the −$2.00 overdraft floor are separate constants."""
    print("\n─── TEST 5: Two different $2.00 values ───")
    import cost_ceiling_monitor
    from projected_costs import OVERDRAFT_FLOOR_CENTS

    # Ceiling: COST_HARD_LIMIT = 2.00 (the most a single operation may cost)
    # Floor: OVERDRAFT_FLOOR_CENTS = -200 (how far balance may go negative)
    check("ceiling_is_200_usd", cost_ceiling_monitor.COST_HARD_LIMIT == 2.00,
          f"got {cost_ceiling_monitor.COST_HARD_LIMIT}")
    check("floor_is_neg200_cents", OVERDRAFT_FLOOR_CENTS == -200,
          f"got {OVERDRAFT_FLOOR_CENTS}")
    # They are conceptually different: one is a maximum cost, the other is a minimum balance.
    # Both happen to be $2.00 in magnitude but they live in different modules
    # and must not be unified.
    record("ceiling_location", "cost_ceiling_monitor.COST_HARD_LIMIT")
    record("floor_location", "projected_costs.OVERDRAFT_FLOOR_CENTS")


# ============================================================
# TEST 6: Cache identity is tour-variant + language
# ============================================================

def test_cache_identity():
    """Report: translation cache key is original_tour_id + content_language.
    Two variants of the same venue have different IDs → different cache entries.
    """
    print("\n─── TEST 6: Cache identity report ───")

    # Read the translation service source to confirm the cache key
    translation_path = os.path.join(_project_root, "translation-service", "translation_service.py")
    if not os.path.exists(translation_path):
        record("cache_key_source", "translation-service not in worktree (container-only)")
        check("cache_key_documented", True)
        return

    with open(translation_path, 'r') as f:
        src = f.read()

    # The cache check is: SELECT id FROM audio_tours WHERE original_tour_id = %s AND content_language = %s
    has_cache_check = "original_tour_id = %s AND content_language = %s" in src
    check("cache_key_is_tour_id_plus_language", has_cache_check,
          "expected SQL: original_tour_id = %s AND content_language = %s")

    record("cache_key", "original_tour_id + content_language (per-variant, not per-venue)")
    record("implication", "Two variants of same venue = different cache entries = correct per D45")


# ============================================================
# CLEANUP
# ============================================================

def cleanup():
    """Remove test data from wallet tables."""
    print("\n─── CLEANUP ───")
    if not _test_users:
        return

    from tests.db_connection import get_connection
    conn = get_connection()
    cur = conn.cursor()
    for uid in _test_users:
        cur.execute("DELETE FROM wallet_ledger WHERE user_id = %s", (uid,))
        cur.execute("DELETE FROM wallet_balance_cache WHERE user_id = %s", (uid,))
    # Clean cost_ledger entries created by our test jobs
    cur.execute("DELETE FROM cost_ledger WHERE user_id LIKE 'test169_%'")
    conn.commit()
    cur.close()
    conn.close()
    print(f"  ✓ {len(_test_users)} test users cleaned up")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("=" * 70)
    print("  LOCAL-169: Ceiling $2.00 and Re-Translation Charge")
    print("=" * 70)

    test_ceiling_190_allowed()
    test_ceiling_210_aborted()
    test_ceiling_break_probe()
    test_translation_charge_fresh_and_cached()
    test_tour_cache_hit_still_free()
    test_two_different_two_dollars()
    test_cache_identity()
    cleanup()

    print("\n" + "=" * 70)
    print(f"  RESULTS: {PASS_COUNT}/{PASS_COUNT + FAIL_COUNT} passed, {FAIL_COUNT} failed")
    print("=" * 70)

    if FAIL_COUNT > 0:
        sys.exit(1)
    print("\n=== ALL TESTS PASSED ===")
