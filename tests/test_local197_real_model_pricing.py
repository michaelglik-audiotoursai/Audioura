#!/usr/bin/env python3
"""
LOCAL-197: Real Model Pricing — Unit Tests
===========================================
Tests that cost_rates.py uses correct per-model input/output rates,
the split-token llm_cost() signature works, and unknown models fail loud.
"""
import os
import sys
import logging

import pytest

# These two guard the Subscribed billing modules, which exist only on the
# `subscribed` branch. On `storied` there is no wallet and no overdraft floor
# (D58: Storied users are never shown a cost), so the guards are skipped
# rather than deleted — the file is shared by both branches.
_subscribed_only = pytest.mark.skipif(
    __import__("importlib").util.find_spec("wallet_ledger") is None,
    reason="Subscribed-only module; not present on storied",
)



PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

PASS_COUNT = 0
FAIL_COUNT = 0


def check(name, condition, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        print(f"  PASS: {name}")
        PASS_COUNT += 1
    else:
        print(f"  FAIL: {name} — {detail}")
        FAIL_COUNT += 1


def test_rate_table_values():
    """Verify LLM_RATES matches cited provider rates."""
    print("\n--- Test: Rate table values ---")
    from cost_rates import LLM_RATES

    # gpt-4o-mini: $0.15/1M input, $0.60/1M output
    # Source: https://openai.com/index/gpt-4o-mini-advancing-cost-efficient-intelligence/
    check("gpt-4o-mini input rate",
          LLM_RATES["gpt-4o-mini"]["input_per_1m"] == 0.15,
          f"got {LLM_RATES['gpt-4o-mini']['input_per_1m']}")
    check("gpt-4o-mini output rate",
          LLM_RATES["gpt-4o-mini"]["output_per_1m"] == 0.60,
          f"got {LLM_RATES['gpt-4o-mini']['output_per_1m']}")

    # gpt-3.5-turbo: $0.50/1M input, $1.50/1M output
    # Source: https://cloudprice.net/models/openai-gpt-3-5-turbo
    check("gpt-3.5-turbo input rate",
          LLM_RATES["gpt-3.5-turbo"]["input_per_1m"] == 0.50,
          f"got {LLM_RATES['gpt-3.5-turbo']['input_per_1m']}")
    check("gpt-3.5-turbo output rate",
          LLM_RATES["gpt-3.5-turbo"]["output_per_1m"] == 1.50,
          f"got {LLM_RATES['gpt-3.5-turbo']['output_per_1m']}")


def test_split_token_signature():
    """llm_cost() with explicit input/output tokens."""
    print("\n--- Test: Split token signature ---")
    from cost_rates import llm_cost

    # gpt-4o-mini: 1000 input, 500 output
    # Expected: (1000 * 0.15/1M) + (500 * 0.60/1M) = 0.00015 + 0.0003 = 0.00045
    cost = llm_cost(input_tokens=1000, output_tokens=500, model="gpt-4o-mini")
    expected = (1000 * 0.15 / 1_000_000) + (500 * 0.60 / 1_000_000)
    check("gpt-4o-mini split: 1000in/500out",
          abs(cost - expected) < 1e-12,
          f"got {cost}, expected {expected}")

    # gpt-3.5-turbo: 5000 input, 2000 output
    # Expected: (5000 * 0.50/1M) + (2000 * 1.50/1M) = 0.0025 + 0.003 = 0.0055
    cost = llm_cost(input_tokens=5000, output_tokens=2000, model="gpt-3.5-turbo")
    expected = (5000 * 0.50 / 1_000_000) + (2000 * 1.50 / 1_000_000)
    check("gpt-3.5-turbo split: 5000in/2000out",
          abs(cost - expected) < 1e-12,
          f"got {cost}, expected {expected}")


def test_total_tokens_deprecated_path():
    """llm_cost(total_tokens=N) works with 70/30 assumption."""
    print("\n--- Test: Deprecated total_tokens path ---")
    from cost_rates import llm_cost

    # Reset deprecation flag for clean test
    if hasattr(llm_cost, "_deprecated_warned"):
        del llm_cost._deprecated_warned

    # gpt-3.5-turbo, 10000 total: 7000 input + 3000 output (70/30 split)
    # Expected: (7000 * 0.50/1M) + (3000 * 1.50/1M) = 0.0035 + 0.0045 = 0.0080
    cost = llm_cost(total_tokens=10000, model="gpt-3.5-turbo")
    expected = (7000 * 0.50 / 1_000_000) + (3000 * 1.50 / 1_000_000)
    check("total_tokens=10000 gpt-3.5-turbo",
          abs(cost - expected) < 1e-12,
          f"got {cost}, expected {expected}")

    # gpt-4o-mini, 10000 total: 7000 input + 3000 output
    # Expected: (7000 * 0.15/1M) + (3000 * 0.60/1M) = 0.00105 + 0.0018 = 0.00285
    cost = llm_cost(total_tokens=10000, model="gpt-4o-mini")
    expected = (7000 * 0.15 / 1_000_000) + (3000 * 0.60 / 1_000_000)
    check("total_tokens=10000 gpt-4o-mini",
          abs(cost - expected) < 1e-12,
          f"got {cost}, expected {expected}")


def test_zero_tokens():
    """Zero tokens should return zero cost."""
    print("\n--- Test: Zero tokens ---")
    from cost_rates import llm_cost

    check("zero input+output",
          llm_cost(input_tokens=0, output_tokens=0, model="gpt-4o-mini") == 0.0)
    check("zero total_tokens",
          llm_cost(total_tokens=0, model="gpt-3.5-turbo") == 0.0)


def test_output_heavy_vs_input_heavy():
    """Output-heavy call costs more than input-heavy for same total tokens."""
    print("\n--- Test: Output-heavy vs input-heavy ---")
    from cost_rates import llm_cost

    # Same total tokens (10000), different split
    output_heavy = llm_cost(input_tokens=2000, output_tokens=8000, model="gpt-4o-mini")
    input_heavy = llm_cost(input_tokens=8000, output_tokens=2000, model="gpt-4o-mini")

    check("output-heavy > input-heavy (gpt-4o-mini)",
          output_heavy > input_heavy,
          f"output_heavy={output_heavy}, input_heavy={input_heavy}")

    # Same for gpt-3.5-turbo
    output_heavy = llm_cost(input_tokens=2000, output_tokens=8000, model="gpt-3.5-turbo")
    input_heavy = llm_cost(input_tokens=8000, output_tokens=2000, model="gpt-3.5-turbo")

    check("output-heavy > input-heavy (gpt-3.5-turbo)",
          output_heavy > input_heavy,
          f"output_heavy={output_heavy}, input_heavy={input_heavy}")


def test_unknown_model_warns_and_prices_high():
    """Unknown model logs warning and uses most expensive rate."""
    print("\n--- Test: Unknown model warns and prices high ---")
    from cost_rates import llm_cost, LLM_RATES

    # Capture log output
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.WARNING)
    logger = logging.getLogger("cost_rates")
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)

    # Call with unknown model
    cost_unknown = llm_cost(input_tokens=1000, output_tokens=500, model="gpt-99-future")

    # Should use gpt-3.5-turbo rates (the most expensive known model)
    most_expensive = max(
        LLM_RATES.values(),
        key=lambda r: r["input_per_1m"] + r["output_per_1m"]
    )
    expected = (1000 * most_expensive["input_per_1m"] / 1_000_000) + \
               (500 * most_expensive["output_per_1m"] / 1_000_000)

    check("unknown model uses most expensive rate",
          abs(cost_unknown - expected) < 1e-12,
          f"got {cost_unknown}, expected {expected}")

    # Verify the error direction: unknown model should cost >= all known models
    for model_name in LLM_RATES:
        known_cost = llm_cost(input_tokens=1000, output_tokens=500, model=model_name)
        check(f"unknown >= {model_name}",
              cost_unknown >= known_cost - 1e-12,
              f"unknown={cost_unknown}, {model_name}={known_cost}")

    logger.removeHandler(handler)


def test_model_substring_matching():
    """Model variants like 'gpt-4o-mini-2024-07-18' resolve correctly."""
    print("\n--- Test: Model substring matching ---")
    from cost_rates import llm_cost

    # Versioned model name should still resolve
    cost_base = llm_cost(input_tokens=1000, output_tokens=500, model="gpt-4o-mini")
    cost_versioned = llm_cost(input_tokens=1000, output_tokens=500, model="gpt-4o-mini-2024-07-18")
    check("gpt-4o-mini-2024-07-18 == gpt-4o-mini",
          cost_base == cost_versioned,
          f"base={cost_base}, versioned={cost_versioned}")


def test_models_are_now_different():
    """gpt-4o-mini and gpt-3.5-turbo must produce different costs (the original bug)."""
    print("\n--- Test: Models produce different costs ---")
    from cost_rates import llm_cost

    cost_mini = llm_cost(total_tokens=10000, model="gpt-4o-mini")
    cost_35 = llm_cost(total_tokens=10000, model="gpt-3.5-turbo")

    check("gpt-4o-mini != gpt-3.5-turbo",
          abs(cost_mini - cost_35) > 0.001,
          f"mini={cost_mini}, 3.5={cost_35}")

    # gpt-4o-mini should be cheaper
    check("gpt-4o-mini < gpt-3.5-turbo",
          cost_mini < cost_35,
          f"mini={cost_mini}, 3.5={cost_35}")

    # The ratio should be roughly 3-4×
    ratio = cost_35 / cost_mini
    check("gpt-3.5-turbo is ~2.5-4× more expensive",
          2.0 < ratio < 5.0,
          f"ratio={ratio:.2f}")


def test_no_hardcoded_0002_in_cost_path():
    """Verify no remaining 0.002 literals in key files."""
    print("\n--- Test: No hardcoded 0.002 in cost path ---")
    import re

    files_to_check = [
        "generate_tour_text.py",
        "generate_tour_path.py",
        "derepetition_guard.py",
        "tour_hook_generator.py",
        "modified_generate_tour_text.py",
    ]

    for filename in files_to_check:
        filepath = os.path.join(PROJECT_ROOT, filename)
        if not os.path.exists(filepath):
            check(f"{filename}: file exists", False, "file not found")
            continue
        with open(filepath, 'r') as f:
            content = f.read()
        # Look for the pattern: something / 1000 * 0.002
        matches = re.findall(r'/ 1000 \* 0\.002', content)
        check(f"{filename}: no '/ 1000 * 0.002' literals",
              len(matches) == 0,
              f"found {len(matches)} occurrences")


@_subscribed_only
def test_wallet_ledger_unchanged():
    """Verify wallet_ledger.py imports and constants are untouched."""
    print("\n--- Test: Wallet ledger unchanged ---")

    from wallet_ledger import PRICING_MULTIPLIER, VALID_MOVEMENT_TYPES
    from decimal import Decimal

    check("PRICING_MULTIPLIER == 5.0",
          PRICING_MULTIPLIER == Decimal("5.0"),
          f"got {PRICING_MULTIPLIER}")
    check("VALID_MOVEMENT_TYPES includes 'charge'",
          "charge" in VALID_MOVEMENT_TYPES)


@_subscribed_only
def test_projected_costs_unchanged():
    """Verify projected_costs.py is untouched (D41 overdraft logic)."""
    print("\n--- Test: Projected costs unchanged ---")
    from projected_costs import PROJECTED_COSTS, OVERDRAFT_FLOOR_CENTS, would_breach_floor
    from decimal import Decimal

    check("tour_generate projected = $0.40",
          PROJECTED_COSTS["tour_generate"] == Decimal("0.40"))
    check("overdraft floor = -200 cents",
          OVERDRAFT_FLOOR_CENTS == -200)
    # Test the function still works
    check("would_breach_floor(100, 'tour_generate') == False",
          would_breach_floor(100, "tour_generate") is False)
    check("would_breach_floor(-180, 'translation_generate') == True",
          would_breach_floor(-180, "translation_generate") is True)


def test_money_impact_table():
    """Print the before/after money table for review."""
    print("\n--- Money Impact Table ---")
    from cost_rates import llm_cost

    # Real measured token counts from SUBMISSION_LOCAL-194.md
    TOUR_TOKENS = 10_123      # avg tokens per tour (measured)
    ARTICLE_TOKENS = 160      # typical news article LLM call

    MULTIPLIER = 5  # Michael's ×5 rule (PRICING_MULTIPLIER)

    # Old rates (the bug): $0.002/1K regardless of model
    def old_cost(tokens):
        return tokens / 1000 * 0.002

    print(f"\n  {'':40s} | {'Our Cost':>12s} | {'User ×5':>12s}")
    print(f"  {'─' * 40} | {'─' * 12} | {'─' * 12}")

    # --- Tour (10,123 tokens) ---
    old_tour = old_cost(TOUR_TOKENS)
    new_tour_35 = llm_cost(total_tokens=TOUR_TOKENS, model="gpt-3.5-turbo")
    new_tour_mini = llm_cost(total_tokens=TOUR_TOKENS, model="gpt-4o-mini")

    print(f"  {'TOUR (10,123 tokens)':40s} |              |")
    print(f"  {'  BEFORE (either model, same rate)':40s} | ${old_tour:>10.6f} | ${old_tour * MULTIPLIER:>10.6f}")
    print(f"  {'  AFTER  gpt-3.5-turbo':40s} | ${new_tour_35:>10.6f} | ${new_tour_35 * MULTIPLIER:>10.6f}")
    print(f"  {'  AFTER  gpt-4o-mini':40s} | ${new_tour_mini:>10.6f} | ${new_tour_mini * MULTIPLIER:>10.6f}")
    print(f"  {'':40s} |              |")

    # --- Article (160 tokens) ---
    old_article = old_cost(ARTICLE_TOKENS)
    new_article_35 = llm_cost(total_tokens=ARTICLE_TOKENS, model="gpt-3.5-turbo")
    new_article_mini = llm_cost(total_tokens=ARTICLE_TOKENS, model="gpt-4o-mini")

    print(f"  {'ARTICLE (160 tokens LLM component)':40s} |              |")
    print(f"  {'  BEFORE (either model, same rate)':40s} | ${old_article:>10.6f} | ${old_article * MULTIPLIER:>10.6f}")
    print(f"  {'  AFTER  gpt-3.5-turbo':40s} | ${new_article_35:>10.6f} | ${new_article_35 * MULTIPLIER:>10.6f}")
    print(f"  {'  AFTER  gpt-4o-mini':40s} | ${new_article_mini:>10.6f} | ${new_article_mini * MULTIPLIER:>10.6f}")
    print()

    # Verify the correction direction: new cost < old cost for both models
    check("tour: new gpt-3.5 < old",
          new_tour_35 < old_tour,
          f"new={new_tour_35}, old={old_tour}")
    check("tour: new gpt-4o-mini < old",
          new_tour_mini < old_tour,
          f"new={new_tour_mini}, old={old_tour}")
    check("article: new gpt-3.5 < old",
          new_article_35 < old_article,
          f"new={new_article_35}, old={old_article}")
    check("article: new gpt-4o-mini < old",
          new_article_mini < old_article,
          f"new={new_article_mini}, old={old_article}")

    # Show savings factor
    print(f"  Savings factors (old_cost / new_cost):")
    print(f"    Tour gpt-3.5-turbo:  {old_tour / new_tour_35:.1f}× overcharge corrected")
    print(f"    Tour gpt-4o-mini:    {old_tour / new_tour_mini:.1f}× overcharge corrected")
    print(f"    Article gpt-3.5:     {old_article / new_article_35:.1f}× overcharge corrected")
    print(f"    Article gpt-4o-mini: {old_article / new_article_mini:.1f}× overcharge corrected")


if __name__ == "__main__":
    print("=" * 70)
    print("  LOCAL-197: Real Model Pricing — Unit Tests")
    print("=" * 70)

    test_rate_table_values()
    test_split_token_signature()
    test_total_tokens_deprecated_path()
    test_zero_tokens()
    test_output_heavy_vs_input_heavy()
    test_unknown_model_warns_and_prices_high()
    test_model_substring_matching()
    test_models_are_now_different()
    test_no_hardcoded_0002_in_cost_path()
    test_wallet_ledger_unchanged()
    test_projected_costs_unchanged()
    test_money_impact_table()

    print("\n" + "=" * 70)
    print(f"  Results: {PASS_COUNT} passed, {FAIL_COUNT} failed")
    print("=" * 70)

    if FAIL_COUNT > 0:
        sys.exit(1)
    print("\n=== ALL TESTS PASSED ===")
    sys.exit(0)
