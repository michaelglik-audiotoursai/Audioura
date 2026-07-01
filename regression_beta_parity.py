"""
Regression: Beta Parity Test
==============================
Verifies that when STORIED_MODE=false, tour generation output is identical
in structure to the Beta baseline (chagall_current_tour.txt).

Requires OPENAI_API_KEY to be set for live generation.

Usage:
    python regression_beta_parity.py

Exits 0 if all assertions pass, 1 otherwise.
"""
import os
import sys
import re

# Force STORIED_MODE off for this test
os.environ["STORIED_MODE"] = "false"


def load_baseline(path="chagall_current_tour.txt"):
    """Load the Beta baseline tour file."""
    if not os.path.exists(path):
        print(f"FAIL: Baseline file '{path}' not found.")
        print(f"      Place chagall_current_tour.txt in the working directory.")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def count_stops(tour_text):
    """Count the number of stops in a tour text."""
    # Match patterns like "Stop 1:", "Stop 2:", etc.
    return len(re.findall(r"Stop\s+\d+[:\.]", tour_text))


def extract_stop_names(tour_text):
    """Extract ordered list of stop names from tour text."""
    # Pattern: "Stop N: <name>" or "Stop N. <name>"
    matches = re.findall(r"Stop\s+\d+[:\.]?\s*(.+?)(?:\n|$)", tour_text)
    # Clean up — take just the name part (before " by " or end of line)
    names = []
    for m in matches:
        name = m.strip().split(" by ")[0].strip()
        # Remove trailing punctuation
        name = re.sub(r"[,;:]+$", "", name).strip()
        names.append(name)
    return names


def estimate_cost_from_text(tour_text):
    """Extract total cost if reported in the tour text, else estimate from length."""
    # Look for cost line like "Total estimated cost: $X.XX"
    cost_match = re.search(r"[Tt]otal\s+(?:estimated\s+)?cost[:\s]*\$?([\d.]+)", tour_text)
    if cost_match:
        return float(cost_match.group(1))
    # Fallback: estimate from word count (rough proxy)
    return len(tour_text.split()) * 0.001  # arbitrary per-word proxy


def run_assertions(baseline_text, generated_text):
    """Run all parity assertions. Returns list of (name, passed, detail)."""
    results = []

    # 1. Same number of stops
    baseline_stops = count_stops(baseline_text)
    generated_stops = count_stops(generated_text)
    passed = baseline_stops == generated_stops
    results.append((
        "Same number of stops",
        passed,
        f"baseline={baseline_stops}, generated={generated_stops}"
    ))

    # 2. Same stop names in same order
    baseline_names = extract_stop_names(baseline_text)
    generated_names = extract_stop_names(generated_text)
    passed = baseline_names == generated_names
    detail = ""
    if not passed:
        detail = f"baseline={baseline_names[:5]}... generated={generated_names[:5]}..."
    else:
        detail = f"{len(baseline_names)} stops match"
    results.append(("Same stop names in same order", passed, detail))

    # 3. No "Introduction:" block present
    has_intro = bool(re.search(r"^Introduction:", generated_text, re.MULTILINE))
    results.append((
        "No 'Introduction:' block present",
        not has_intro,
        "found 'Introduction:' block" if has_intro else "clean"
    ))

    # 4. No Artist's View labels
    has_artist_view = "\U0001f3a8 Artist's View:" in generated_text
    results.append((
        "No '\U0001f3a8 Artist\\'s View:' labels present",
        not has_artist_view,
        "found Artist's View label" if has_artist_view else "clean"
    ))

    # 5. No STORIED or SPINE in output text
    has_storied = bool(re.search(r"\bSTORIED\b", generated_text))
    has_spine = bool(re.search(r"\bSPINE\b", generated_text))
    passed = not has_storied and not has_spine
    detail_parts = []
    if has_storied:
        detail_parts.append("found 'STORIED'")
    if has_spine:
        detail_parts.append("found 'SPINE'")
    results.append((
        "No 'STORIED' or 'SPINE' in output text",
        passed,
        ", ".join(detail_parts) if detail_parts else "clean"
    ))

    # 6. Total cost within 20% of baseline cost
    baseline_cost = estimate_cost_from_text(baseline_text)
    generated_cost = estimate_cost_from_text(generated_text)
    if baseline_cost > 0:
        ratio = abs(generated_cost - baseline_cost) / baseline_cost
        passed = ratio <= 0.20
        detail = f"baseline=${baseline_cost:.4f}, generated=${generated_cost:.4f}, diff={ratio*100:.1f}%"
    else:
        passed = True
        detail = "baseline cost=0 (skipped cost comparison)"
    results.append(("Total cost within 20% of baseline cost", passed, detail))

    return results


def main():
    print("=" * 70)
    print("REGRESSION TEST: Beta Parity (STORIED_MODE=false)")
    print("=" * 70)

    # Verify OPENAI_API_KEY is set
    if not os.environ.get("OPENAI_API_KEY"):
        print("\nFAIL: OPENAI_API_KEY not set. This test requires live API access.")
        sys.exit(1)

    # Load baseline
    print("\nLoading baseline: chagall_current_tour.txt ...")
    baseline_text = load_baseline()
    print(f"  Baseline loaded: {len(baseline_text)} chars, {count_stops(baseline_text)} stops")

    # Generate a fresh tour with Chagall inputs
    print("\nGenerating fresh tour (STORIED_MODE=false) ...")
    print(f"  STORIED_MODE = {os.environ.get('STORIED_MODE')}")

    from generate_tour_text import generate_tour_text

    # Use Chagall museum inputs
    location = "Musée National Marc Chagall, Nice"
    tour_type = "art and paintings"
    total_stops = count_stops(baseline_text) or 10

    tour_text, output_file, coordinates = generate_tour_text(
        location=location,
        tour_type=tour_type,
        output_file=None,
        total_stops=total_stops,
        persona=None,
    )

    if tour_text is None:
        print("\nFAIL: Tour generation returned None (generation failed).")
        sys.exit(1)

    print(f"  Generated: {len(tour_text)} chars, {count_stops(tour_text)} stops")

    # Run assertions
    print("\n" + "-" * 70)
    print("ASSERTIONS:")
    print("-" * 70)

    results = run_assertions(baseline_text, tour_text)

    all_passed = True
    for name, passed, detail in results:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_passed = False
        print(f"  [{status}] {name}")
        if detail:
            print(f"         {detail}")

    print("\n" + "=" * 70)
    if all_passed:
        print("RESULT: ALL ASSERTIONS PASSED — Beta parity confirmed.")
        sys.exit(0)
    else:
        failed_count = sum(1 for _, p, _ in results if not p)
        print(f"RESULT: {failed_count} ASSERTION(S) FAILED — Beta parity broken.")
        sys.exit(1)


if __name__ == "__main__":
    main()
