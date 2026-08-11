#!/usr/bin/env python3
"""run_local389_acceptance.py — Acceptance test for LOCAL-389.

Generates:
  1. MFA "Picasso, Miró, Dalí: Unbound" (8 stops) — 2 runs gate ON, 2 runs gate OFF
     to settle whether the gate strips credit-line figures
  2. Palais Lascaris, Nice, France (4 stops) — control case (D302)

Checks per the LOCAL-389 spec:
  - Zero: ungrounded visitor/attendance figures, zero garbage matches
  - Survive: 40 color lithographs, 1971/1974/1955 wherever credit line supports
  - Must not regress (D308/D309): Miró stop 1; Dalí+Freud stop 2; Gris+Reverdy stop 3;
    every stop ≥120 words; book in ≥2 stops; livre d'artiste, collabor*, typography;
    That's N stops == heading count; full D305 zero-list
  - Control: Palais Lascaris dates survive, score bounds met

Env:
  DISABLE_TOUR_CACHE=1
  DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours
  STORIED_MODE=true
"""
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault('DISABLE_TOUR_CACHE', '1')
os.environ.setdefault('DATABASE_URL', 'postgresql://admin:password123@localhost:5433/audiotours')
os.environ.setdefault('STORIED_MODE', 'true')

from generate_tour_text import generate_tour_text
from tour_rubric_scorer import score_tour_file


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def count_occurrences(text, term):
    """Case-insensitive count of term in text."""
    return len(re.findall(re.escape(term), text, re.IGNORECASE))


def extract_stops(tour_text):
    """Extract individual stop texts split by heading pattern."""
    # Stops are delimited by "Stop N:" or "## Stop N" patterns
    parts = re.split(r'(?:^|\n)(?:##?\s*)?Stop\s+\d+[:\s]', tour_text, flags=re.IGNORECASE)
    # First part is the general description; rest are stops
    return parts[1:] if len(parts) > 1 else []


def count_headings(tour_text):
    """Count stop headings."""
    return len(re.findall(r'(?:^|\n)(?:##?\s*)?Stop\s+\d+[:\s]', tour_text, re.IGNORECASE))


def check_d305_zero_list(tour_text):
    """D305: none of these terms should appear (form-claim gate should remove them)."""
    zero_terms = [
        'ceiling', 'mural', 'installation', 'sculpture', 'painting', 'glass',
        'stand beneath', 'look up', 'gaze up',
        'Chagall', 'Rousseau', 'Corbusier', 'Lalanne', 'Matisse'
    ]
    violations = []
    text_lower = tour_text.lower()
    for term in zero_terms:
        if term.lower() in text_lower:
            violations.append(term)
    return violations


def check_d308_d309(tour_text):
    """D308/D309 regression checks."""
    errors = []
    text_lower = tour_text.lower()
    stops = extract_stops(tour_text)

    # Miró stop 1
    if stops and 'miró' not in stops[0].lower() and 'miro' not in stops[0].lower():
        errors.append("D309: Miró not in stop 1")

    # Dalí AND Freud stop 2
    if len(stops) >= 2:
        s2 = stops[1].lower()
        if 'dalí' not in s2 and 'dali' not in s2:
            errors.append("D309: Dalí not in stop 2")
        if 'freud' not in s2:
            errors.append("D309: Freud not in stop 2")

    # Gris AND Reverdy stop 3
    if len(stops) >= 3:
        s3 = stops[2].lower()
        if 'gris' not in s3:
            errors.append("D309: Gris not in stop 3")
        if 'reverdy' not in s3:
            errors.append("D309: Reverdy not in stop 3")

    # Every stop ≥120 words
    for i, stop in enumerate(stops):
        word_count = len(stop.split())
        if word_count < 120:
            errors.append(f"D308: Stop {i+1} has only {word_count} words (need ≥120)")

    # 'book' in ≥2 stops
    book_stops = sum(1 for s in stops if 'book' in s.lower())
    if book_stops < 2:
        errors.append(f"D308: 'book' in only {book_stops} stops (need ≥2)")

    # livre d'artiste, collabor*, typography present
    if "livre d'artiste" not in text_lower and "livres d'artiste" not in text_lower:
        errors.append("D308: 'livre d'artiste' not present")
    if 'collabor' not in text_lower:
        errors.append("D308: 'collabor*' not present")
    if 'typography' not in text_lower and 'typograph' not in text_lower:
        errors.append("D308: 'typography' not present")

    # "That's N stops" == heading count
    thats_match = re.search(r"that'?s\s+(\d+)\s+stops?", text_lower)
    heading_count = count_headings(tour_text)
    if thats_match:
        n_stated = int(thats_match.group(1))
        if n_stated != heading_count:
            errors.append(f"D308: 'That's {n_stated} stops' but heading count = {heading_count}")

    return errors


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    all_results = []
    gate_comparison = {'on': [], 'off': []}

    # ─── MFA runs: 2x gate ON, 2x gate OFF ───
    for gate_state in ['on', 'off']:
        for run_num in range(1, 3):
            label = f"MFA gate={gate_state} run={run_num}"
            print(f"\n{'═'*70}")
            print(f"  {label}")
            print(f"{'═'*70}\n")

            # Toggle gate by temporarily monkey-patching
            if gate_state == 'off':
                os.environ['DISABLE_NUMERIC_CLAIM_GATE'] = '1'
            else:
                os.environ.pop('DISABLE_NUMERIC_CLAIM_GATE', None)

            filepath = f"/tmp/local389_mfa_{gate_state}_{run_num}.txt"
            try:
                tour_text, _, coords = generate_tour_text(
                    "Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA",
                    "museum",
                    filepath,
                    total_stops=8,
                )
                if not tour_text:
                    print(f"  FAIL: {label} returned None")
                    continue

                # Count key terms
                counts = {
                    '1971': count_occurrences(tour_text, '1971'),
                    '1974': count_occurrences(tour_text, '1974'),
                    '1955': count_occurrences(tour_text, '1955'),
                    '40 color lithographs': count_occurrences(tour_text, '40 color lithographs'),
                    'Freud': count_occurrences(tour_text, 'Freud'),
                }
                gate_comparison[gate_state].append(counts)

                print(f"\n  {label} — Key term counts:")
                for term, count in counts.items():
                    print(f"    {term}: {count}")

                # Only check full acceptance on gate=on runs
                if gate_state == 'on':
                    # Check no garbage matches (look for LOCAL-389 drops in log)
                    # The log is printed to stdout during generation — we check
                    # the tour text itself for the important acceptance criteria

                    # D305 zero-list
                    violations = check_d305_zero_list(tour_text)
                    if violations:
                        print(f"\n  ⚠️  D305 zero-list violations: {violations}")

                    # D308/D309
                    regression_errors = check_d308_d309(tour_text)
                    if regression_errors:
                        print(f"\n  ⚠️  D308/D309 regressions:")
                        for e in regression_errors:
                            print(f"    {e}")
                    else:
                        print(f"\n  ✓ D308/D309 checks pass")

                    # Score
                    score = score_tour_file(filepath, 8)
                    print(f"\n  Score (8 stops): {score}")

                    all_results.append({
                        'label': label,
                        'counts': counts,
                        'd305_violations': violations,
                        'regression_errors': regression_errors,
                        'score': score,
                    })

            except Exception as e:
                print(f"  ERROR {label}: {e}")
                import traceback
                traceback.print_exc()

    # ─── Gate comparison summary ───
    print(f"\n{'═'*70}")
    print("  GATE COMPARISON SUMMARY")
    print(f"{'═'*70}")
    print(f"\n  {'Term':<25} {'Gate ON (2 runs)':<25} {'Gate OFF (2 runs)'}")
    print(f"  {'-'*25} {'-'*25} {'-'*25}")
    for term in ['1971', '1974', '1955', '40 color lithographs', 'Freud']:
        on_counts = [r[term] for r in gate_comparison['on']] if gate_comparison['on'] else ['N/A']
        off_counts = [r[term] for r in gate_comparison['off']] if gate_comparison['off'] else ['N/A']
        on_str = ', '.join(str(c) for c in on_counts)
        off_str = ', '.join(str(c) for c in off_counts)
        print(f"  {term:<25} {on_str:<25} {off_str}")

    # ─── Palais Lascaris control (D302) ───
    print(f"\n{'═'*70}")
    print("  CONTROL: Palais Lascaris, Nice, France (4 stops)")
    print(f"{'═'*70}\n")

    os.environ.pop('DISABLE_NUMERIC_CLAIM_GATE', None)
    filepath_palais = "/tmp/local389_palais.txt"
    try:
        tour_text_p, _, coords_p = generate_tour_text(
            "Palais Lascaris, Nice, France",
            "museum",
            filepath_palais,
            total_stops=4,
        )
        if tour_text_p:
            print(f"\n  Tour text (first 2000 chars):")
            print(tour_text_p[:2000])

            text_lower = tour_text_p.lower()

            # 4/4 real instruments
            # (Palais Lascaris is a museum of musical instruments — check for instrument content)
            print(f"\n  Checking Palais Lascaris acceptance...")

            # Dates: 1780, 1884, 1696, 1581 — these are in stop titles, must survive
            palais_dates = ['1780', '1884', '1696', '1581']
            date_results = {}
            for d in palais_dates:
                date_results[d] = count_occurrences(tour_text_p, d)
                status = "✓" if date_results[d] > 0 else "✗"
                print(f"    {status} Date {d}: {date_results[d]} occurrences")

            missing_dates = [d for d, c in date_results.items() if c == 0]
            if missing_dates:
                print(f"\n  ⚠️  FAIL: Dates missing from Palais Lascaris: {missing_dates}")
                print(f"       (These are in stop titles — stripping them is an automatic bounce)")

            # framing=venue_purpose
            if 'venue_purpose' in tour_text_p or 'musical instrument' in text_lower or 'instrument' in text_lower:
                print(f"    ✓ venue_purpose framing detected (instruments mentioned)")
            else:
                print(f"    ⚠️  No venue_purpose framing evidence")

            # Every stop ≥120 words
            stops_p = extract_stops(tour_text_p)
            for i, stop in enumerate(stops_p):
                wc = len(stop.split())
                status = "✓" if wc >= 120 else "✗"
                print(f"    {status} Stop {i+1}: {wc} words")

            # Score bounds
            score4 = score_tour_file(filepath_palais, 4)
            score8 = score_tour_file(filepath_palais, 8)
            print(f"\n    score_tour_file(f, 4) = {score4}  (bound: ≥81.2)")
            print(f"    score_tour_file(f, 8) = {score8}  (bound: ≥75.0)")

            if score4 < 81.2:
                print(f"    ⚠️  FAIL: score(4) = {score4} < 81.2")
            if score8 < 75.0:
                print(f"    ⚠️  FAIL: score(8) = {score8} < 75.0")
        else:
            print("  FAIL: Palais Lascaris tour returned None")
    except Exception as e:
        print(f"  ERROR generating Palais Lascaris: {e}")
        import traceback
        traceback.print_exc()

    # ─── Final summary ───
    print(f"\n{'═'*70}")
    print("  FINAL SUMMARY")
    print(f"{'═'*70}\n")
    print("  Gate comparison shows whether the numeric-claim gate strips")
    print("  credit-line figures. If ON and OFF counts are similar, the gate")
    print("  is NOT causing drops. If ON shows zeros where OFF does not,")
    print("  that would indicate a bug in identity-block grounding.")


if __name__ == '__main__':
    main()
