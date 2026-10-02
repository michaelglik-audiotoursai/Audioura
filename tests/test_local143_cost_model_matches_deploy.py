#!/usr/bin/env python3
"""
LOCAL-143: Enforce that cost_rates.DEPLOYED_TRANSLATION_PASSES matches reality.

The cost model must not silently drift from the deployed service. This test
inspects the running translation container to determine which code path is
active, then asserts the constant matches.

Detection method:
  - If the container has LOCAL-142 code (grep for "LOCAL-142" in
    /app/translation_service.py returns > 0), it runs single-pass (passes=1).
  - Otherwise it runs two-pass (passes=2).

If no container is running (CI, dev machine without Docker), the test
verifies internal consistency: translation_cost(N, passes=DEPLOYED) produces
the value the orchestrator would book.

This test FAILS if:
  1. The container is rebuilt with LOCAL-142 but the constant is still 2, or
  2. The constant is flipped to 1 but the container still runs old code.

Either failure means the booked cost does not match reality.
"""
import os
import sys
import subprocess

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


def detect_container_pass_mode():
    """Inspect the running translation container.

    Returns:
        (int, str): (pass_count, evidence) or (None, reason) if undetectable.
    """
    container_name = "translation-service-1"

    # Check container is running
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={container_name}", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=5
        )
        if container_name not in result.stdout:
            return None, f"Container '{container_name}' not running"
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return None, f"Docker not available: {e}"

    # Grep for LOCAL-142 marker in the deployed code
    try:
        result = subprocess.run(
            ["docker", "exec", container_name, "grep", "-c", "LOCAL-142", "/app/translation_service.py"],
            capture_output=True, text=True, timeout=10
        )
        match_count = int(result.stdout.strip()) if result.returncode == 0 else 0
    except (subprocess.TimeoutExpired, ValueError) as e:
        return None, f"Grep failed: {e}"

    if match_count > 0:
        # LOCAL-142 code present → single-pass
        return 1, f"grep 'LOCAL-142' returned {match_count} matches → single-pass active"
    else:
        # No LOCAL-142 code → two-pass (old behaviour)
        # Double-check by looking for the two translate_text calls per stop
        try:
            result = subprocess.run(
                ["docker", "exec", container_name, "grep", "-n",
                 "self.translate_text(self._strip_nav_fields_for_tts", "/app/translation_service.py"],
                capture_output=True, text=True, timeout=10
            )
            has_second_pass = (result.returncode == 0 and "translate_text" in result.stdout)
        except (subprocess.TimeoutExpired, ValueError):
            has_second_pass = True  # Conservative: assume two-pass if check fails

        evidence = (
            f"grep 'LOCAL-142' returned 0 matches, "
            f"second translate_text call {'found' if has_second_pass else 'NOT found'} "
            f"→ two-pass active"
        )
        return 2, evidence


def test_constant_matches_container():
    """CRITICAL: The DEPLOYED_TRANSLATION_PASSES constant must match the running container."""
    print("\n--- Test: Constant matches running container ---")

    from cost_rates import DEPLOYED_TRANSLATION_PASSES

    detected_passes, evidence = detect_container_pass_mode()
    print(f"  Container inspection: {evidence}")
    print(f"  DEPLOYED_TRANSLATION_PASSES = {DEPLOYED_TRANSLATION_PASSES}")

    if detected_passes is None:
        # Can't inspect container — skip enforcement but log clearly
        print(f"  SKIP (container not available): {evidence}")
        print(f"  Falling back to internal consistency checks only.")
        check("constant is 1 or 2", DEPLOYED_TRANSLATION_PASSES in (1, 2),
              f"got {DEPLOYED_TRANSLATION_PASSES}")
        return

    check(
        f"DEPLOYED_TRANSLATION_PASSES == detected ({detected_passes})",
        DEPLOYED_TRANSLATION_PASSES == detected_passes,
        f"constant={DEPLOYED_TRANSLATION_PASSES}, container={detected_passes}. "
        f"The cost model is {'over' if DEPLOYED_TRANSLATION_PASSES > detected_passes else 'under'}stating "
        f"translation cost! Update DEPLOYED_TRANSLATION_PASSES in cost_rates.py."
    )


def test_cost_model_arithmetic():
    """Verify both modes produce the expected dollar amounts."""
    print("\n--- Test: Cost model arithmetic ---")

    from cost_rates import translation_cost, AWS_TRANSLATE_COST_PER_CHAR, POLLY_COST_PER_CHAR

    # Two-pass mode
    two_pass = translation_cost(1_000_000, passes=2)
    expected_two_pass = (1_000_000 * 1.95 * AWS_TRANSLATE_COST_PER_CHAR) + \
                        (1_000_000 * 0.95 * 1.06 * POLLY_COST_PER_CHAR)
    check("two-pass(1M) correct", abs(two_pass - expected_two_pass) < 0.001,
          f"got {two_pass}, expected {expected_two_pass}")

    # Single-pass mode
    one_pass = translation_cost(1_000_000, passes=1)
    expected_one_pass = (1_000_000 * 1.0 * AWS_TRANSLATE_COST_PER_CHAR) + \
                        (1_000_000 * 0.95 * 1.06 * POLLY_COST_PER_CHAR)
    check("single-pass(1M) correct", abs(one_pass - expected_one_pass) < 0.001,
          f"got {one_pass}, expected {expected_one_pass}")

    # The ratio should be ~1.74× (two-pass costs more)
    ratio = two_pass / one_pass
    check("two-pass is ~1.75× single-pass", 1.5 < ratio < 2.0,
          f"ratio={ratio:.3f}")

    # Verify the difference is the second pass cost
    diff = two_pass - one_pass
    second_pass_chars = 1_000_000 * 0.95  # nav-stripped ≈ 95% of source
    second_pass_cost = second_pass_chars * AWS_TRANSLATE_COST_PER_CHAR
    check("difference == second-pass translate cost",
          abs(diff - second_pass_cost) < 0.001,
          f"diff={diff:.4f}, expected_second_pass={second_pass_cost:.4f}")


def test_invalid_passes_rejected():
    """translation_cost() rejects invalid pass values."""
    print("\n--- Test: Invalid passes rejected ---")

    from cost_rates import translation_cost

    for bad_val in (0, 3, -1):
        try:
            translation_cost(1000, passes=bad_val)
            check(f"passes={bad_val} raises ValueError", False, "no exception raised")
        except ValueError:
            check(f"passes={bad_val} raises ValueError", True)


def test_orchestrator_uses_constant():
    """Verify the orchestrator imports and uses DEPLOYED_TRANSLATION_PASSES."""
    print("\n--- Test: Orchestrator uses constant ---")

    import ast
    orch_path = os.path.join(PROJECT_ROOT, "tour_orchestrator_service.py")
    with open(orch_path, 'r') as f:
        source = f.read()

    # Check that DEPLOYED_TRANSLATION_PASSES is imported
    check("orchestrator imports DEPLOYED_TRANSLATION_PASSES",
          "DEPLOYED_TRANSLATION_PASSES" in source,
          "constant not found in tour_orchestrator_service.py")

    # Check it's passed to translation_cost
    check("orchestrator passes constant to translation_cost()",
          "passes=DEPLOYED_TRANSLATION_PASSES" in source,
          "passes= argument not found in translation_cost call")

    # Check breakdown records the pass count (audit trail)
    check("breakdown records translation_passes",
          '"translation_passes"' in source or "'translation_passes'" in source,
          "translation_passes not in breakdown dict")


def test_default_matches_deployed_constant():
    """translation_cost(N) == translation_cost(N, passes=DEPLOYED_TRANSLATION_PASSES)."""
    print("\n--- Test: Default matches DEPLOYED constant ---")

    from cost_rates import translation_cost, DEPLOYED_TRANSLATION_PASSES

    for chars in (1000, 17765, 100000, 1_000_000):
        default_cost = translation_cost(chars)
        explicit_cost = translation_cost(chars, passes=DEPLOYED_TRANSLATION_PASSES)
        check(f"default({chars}) == explicit(passes={DEPLOYED_TRANSLATION_PASSES})",
              default_cost == explicit_cost,
              f"default={default_cost}, explicit={explicit_cost}")


def test_real_tour_cost_matches_expected(tours=None):
    """For real tours in the DB, verify cost matches pass count."""
    print("\n--- Test: Real tour costs match pass count ---")

    sys.path.insert(0, os.path.join(PROJECT_ROOT, "tests"))
    try:
        from db_connection import check_db_available, get_connection
    except ImportError:
        print("  SKIP: db_connection not importable")
        return

    if not check_db_available():
        print("  SKIP: Database not available")
        return

    from cost_rates import (
        translation_cost, DEPLOYED_TRANSLATION_PASSES,
        AWS_TRANSLATE_COST_PER_CHAR, POLLY_COST_PER_CHAR,
    )

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, tour_content FROM audio_tours WHERE id IN (14, 21, 27) AND tour_content IS NOT NULL")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        print("  SKIP: No tours found in DB")
        return

    for tour_id, content in rows:
        char_count = len(content)
        cost_2pass = translation_cost(char_count, passes=2)
        cost_1pass = translation_cost(char_count, passes=1)
        cost_default = translation_cost(char_count)

        # The booked cost must equal the mode-specific cost
        check(f"tour {tour_id} ({char_count} chars): default == {DEPLOYED_TRANSLATION_PASSES}-pass",
              cost_default == (cost_2pass if DEPLOYED_TRANSLATION_PASSES == 2 else cost_1pass),
              f"default={cost_default:.4f}, 2-pass={cost_2pass:.4f}, 1-pass={cost_1pass:.4f}")

        # Sanity: switching from 2-pass to 1-pass saves ~43% (not "2-pass is 43% more")
        # 2-pass/1-pass ratio = (1.95*15 + polly) / (1.0*15 + polly) ≈ 1.75
        # Saving = 1 - (1-pass / 2-pass) ≈ 43%
        saving_pct = (cost_2pass - cost_1pass) / cost_2pass * 100
        check(f"tour {tour_id}: 2→1 pass saves ~40-50%",
              35 < saving_pct < 55,
              f"got {saving_pct:.1f}%")


if __name__ == "__main__":
    print("=" * 70)
    print("  LOCAL-143: Cost Model Matches Deploy — Enforcement Test")
    print("=" * 70)

    test_constant_matches_container()
    test_cost_model_arithmetic()
    test_invalid_passes_rejected()
    test_orchestrator_uses_constant()
    test_default_matches_deployed_constant()
    test_real_tour_cost_matches_expected()

    print("\n" + "=" * 70)
    print(f"  Results: {PASS_COUNT} passed, {FAIL_COUNT} failed")
    print("=" * 70)

    if FAIL_COUNT > 0:
        sys.exit(1)
    print("\n=== ALL TESTS PASSED ===")
    sys.exit(0)
