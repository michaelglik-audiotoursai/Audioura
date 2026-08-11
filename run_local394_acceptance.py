#!/usr/bin/env python3
"""run_local394_acceptance.py — Acceptance test for LOCAL-394: Never drop a stop.

Generates:
  1. Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA (8 stops)
     → 3 stops delivered, Le Lézard aux plumes d'or among them
     → That's N stops == heading count
     → Broder, Mourlot, Fridman all present and ALL in the Lézard stop
     → Miró in that stop; Freud in the Moses stop; Gris and Reverdy in Soleil
     → Every stop ≥120 words OR a [LOCAL-394] below_floor … kept log line
     → with publisher = 0; book in ≥2 stops; livre d'artiste, collabor*, typography present
     → ZERO thesis/framing/premise as narration; full D305 zero-list

  2. Palais Lascaris, Nice, France (4 stops) — must stay as good as 393 made it
     → No BEAT RETRY naming a place; 4/4 instruments; dates intact
     → framing=venue_purpose; every stop ≥120 words
     → Bounds: score_tour_file(f,4)=81.2, score_tour_file(f,8)=75.0

Env:
  DISABLE_TOUR_CACHE=1
  DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours
  STORIED_MODE=true
"""
import os
import sys
import re
import io
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault('DISABLE_TOUR_CACHE', '1')
os.environ.setdefault('DATABASE_URL', 'postgresql://admin:password123@localhost:5433/audiotours')
os.environ.setdefault('STORIED_MODE', 'true')

from generate_tour_text import generate_tour_text
from tour_rubric_scorer import score_tour_file


# === Helpers ===

def split_stops(tour_text: str) -> list:
    """Split tour text into individual stops."""
    stops = re.split(r'\n(?=Stop \d+:)', tour_text)
    return [s for s in stops if s.strip().startswith('Stop')]


def word_count(text: str) -> int:
    return len(text.split())


def contains_ci(text: str, term: str) -> bool:
    return term.lower() in text.lower()


def check_mfa_tour(tour_text: str, generation_log: str) -> list:
    """Check LOCAL-394 acceptance criteria for the MFA exhibition tour."""
    errors = []
    stops = split_stops(tour_text)
    full_lower = tour_text.lower()

    # --- 3 stops delivered ---
    if len(stops) < 3:
        errors.append(f"CRITICAL: Only {len(stops)} stops delivered (need ≥3)")
        return errors  # can't check stop-specific criteria with <3 stops

    # --- Le Lézard aux plumes d'or must be among stops ---
    lezard_stop_idx = None
    for i, stop in enumerate(stops):
        if contains_ci(stop, "lézard") or contains_ci(stop, "lezard"):
            lezard_stop_idx = i
            break
    if lezard_stop_idx is None:
        errors.append("CRITICAL: 'Le Lézard aux plumes d'or' stop is MISSING — "
                      "the regression this ticket fixes")

    # --- Heading count ---
    thats_match = re.search(r"That'?s (\d+) stops?", tour_text)
    if thats_match:
        claimed = int(thats_match.group(1))
        if claimed != len(stops):
            errors.append(f"'That's {claimed} stops' but found {len(stops)} headings")

    # --- Broder, Mourlot, Fridman: all present AND all in the Lézard stop ---
    for name in ['Broder', 'Mourlot', 'Fridman']:
        if name.lower() not in full_lower:
            errors.append(f"MISSING: '{name}' not found anywhere in tour text")
        if lezard_stop_idx is not None and not contains_ci(stops[lezard_stop_idx], name):
            errors.append(f"LÉZARD STOP MISSING: '{name}' must be in the Lézard stop")

    # --- Miró in the Lézard stop ---
    if lezard_stop_idx is not None:
        if not contains_ci(stops[lezard_stop_idx], 'miró') and not contains_ci(stops[lezard_stop_idx], 'miro'):
            errors.append("Miró not in the Lézard stop")

    # --- Find Moses and Soleil stops ---
    moses_idx = None
    soleil_idx = None
    for i, stop in enumerate(stops):
        if contains_ci(stop, 'moses') or contains_ci(stop, 'monotheism'):
            moses_idx = i
        if contains_ci(stop, 'soleil') or contains_ci(stop, 'plafond'):
            soleil_idx = i

    # --- Freud in the Moses stop ---
    if moses_idx is not None:
        if not contains_ci(stops[moses_idx], 'freud'):
            errors.append("Freud not in the Moses stop")
    else:
        errors.append("Moses and Monotheism stop not found")

    # --- Gris and Reverdy in the Soleil stop ---
    if soleil_idx is not None:
        if not contains_ci(stops[soleil_idx], 'gris'):
            errors.append("Gris not in the Soleil stop")
        if not contains_ci(stops[soleil_idx], 'reverdy'):
            errors.append("Reverdy not in the Soleil stop")
    else:
        errors.append("Au Soleil du Plafond stop not found")

    # --- Word count floor: every stop ≥120 words OR below_floor log line ---
    below_floor_logged = re.findall(
        r"\[LOCAL-394\] stop='([^']+)' below_floor words=(\d+)", generation_log
    )
    below_floor_stops = {name.lower() for name, _ in below_floor_logged}

    for i, stop in enumerate(stops):
        lines = stop.strip().split('\n')
        # Extract stop name from header
        header = lines[0] if lines else ''
        stop_name_match = re.search(r'Stop \d+:\s*(.+)', header)
        stop_name = stop_name_match.group(1).strip() if stop_name_match else f'Stop {i+1}'

        desc_text = '\n'.join(l for l in lines[1:] if not l.startswith(
            ('Address:', 'Coordinates:', 'Type/', 'Museum Info', 'Orientation:')))
        wc = word_count(desc_text)
        if wc < 120:
            # Acceptable if there's a below_floor log line for this stop
            if stop_name.lower() not in below_floor_stops:
                errors.append(f"Stop {i+1} ({stop_name}): {wc} words < 120 "
                              f"and NO below_floor log line")

    # --- with publisher = 0 ---
    if 'with publisher' in full_lower:
        errors.append("PLACEHOLDER: 'with publisher' still present")

    # --- book in ≥2 stops ---
    book_stops = sum(1 for s in stops if contains_ci(s, 'book'))
    if book_stops < 2:
        errors.append(f"'book' in {book_stops} stops (need ≥2)")

    # --- Kept terms ---
    if not contains_ci(tour_text, "livre d'artiste"):
        errors.append("MISSING: \"livre d'artiste\" not found")
    if not re.search(r'collabor', tour_text, re.IGNORECASE):
        errors.append("MISSING: 'collabor*' not found")
    if not contains_ci(tour_text, 'typography'):
        errors.append("MISSING: 'typography' not found")

    # --- ZERO: banned narration ---
    banned_narration = ['thesis', 'framing', 'premise']
    for term in banned_narration:
        for i, stop in enumerate(stops):
            lines = stop.strip().split('\n')
            narration = '\n'.join(l for l in lines[1:] if not l.startswith(
                ('Address:', 'Coordinates:', 'Orientation:', 'Next:', 'Proceed', 'Continue')))
            if re.search(rf'\b{term}\b', narration, re.IGNORECASE):
                errors.append(f"BANNED: '{term}' found in stop {i+1} narration")

    # --- D305 banned list ---
    d305_banned = ['ceiling', 'mural', 'installation', 'sculpture', 'painting', 'glass',
                   'stand beneath', 'look up', 'gaze up', 'Chagall', 'Rousseau',
                   'Corbusier', 'Lalanne', 'Matisse']
    for term in d305_banned:
        if contains_ci(tour_text, term):
            errors.append(f"D305 BANNED: '{term}' found in tour text")

    return errors


def check_palais_lascaris(tour_text: str, tour_file: str, generation_log: str) -> list:
    """Check D302 control case — must stay as good as 393 made it."""
    errors = []
    stops = split_stops(tour_text)

    if len(stops) != 4:
        errors.append(f"Expected 4 stops, got {len(stops)}")

    # No BEAT RETRY naming a place
    beat_retry_lines = [l for l in generation_log.split('\n') if 'BEAT RETRY' in l]
    places = ['france', 'nice', 'paris', 'lascaris', 'palais']
    for line in beat_retry_lines:
        line_lower = line.lower()
        for place in places:
            if place in line_lower:
                errors.append(f"BEAT RETRY names a place: '{place}' in: {line.strip()}")

    # 4/4 instruments
    full_lower = tour_text.lower()
    instrument_patterns = ['baroque', 'guitar', 'lute', 'violin', 'harpsichord', 'flute',
                          'cello', 'mandolin', 'organ', 'hurdy', 'viol', 'oboe', 'trumpet']
    inst_count = sum(1 for p in instrument_patterns if p in full_lower)
    if inst_count < 4:
        errors.append(f"Only {inst_count} instrument references (need 4+)")

    # Dates
    for d in ['1780', '1884', '1696', '1581']:
        if d not in tour_text:
            errors.append(f"Date {d} missing")

    # framing=venue_purpose
    if 'venue_purpose' not in generation_log:
        errors.append("framing=venue_purpose not detected in log")

    # Word floor
    for i, stop in enumerate(stops):
        lines = stop.strip().split('\n')
        desc_text = '\n'.join(l for l in lines[1:] if not l.startswith(
            ('Address:', 'Coordinates:', 'Type/', 'Orientation:')))
        wc = word_count(desc_text)
        if wc < 120:
            errors.append(f"Stop {i+1} under floor: {wc} words < 120")

    # No fabricated premise
    if 'premise' in full_lower:
        errors.append("'premise' found")

    # Score bounds
    try:
        score4 = score_tour_file(tour_file, 4)
        score8 = score_tour_file(tour_file, 8)
        if score4 < 81.2:
            errors.append(f"score_tour_file(f,4)={score4:.1f} < 81.2")
        if score8 < 75.0:
            errors.append(f"score_tour_file(f,8)={score8:.1f} < 75.0")
    except Exception as e:
        errors.append(f"Scoring failed: {e}")

    return errors


# === Main ===

def main():
    print("=" * 70)
    print("LOCAL-394 ACCEPTANCE — Never drop a stop to satisfy a length rule")
    print("=" * 70)

    all_pass = True

    # --- Case 1: MFA Exhibition ---
    print("\n" + "=" * 70)
    print("CASE 1: Picasso, Miró, Dalí: Unbound — MFA, Boston, MA (8 stops)")
    print("=" * 70)

    mfa_file = "tours/acceptance_local394_mfa.txt"
    try:
        log_capture = io.StringIO()
        import contextlib
        with contextlib.redirect_stdout(log_capture):
            tour_text = generate_tour_text(
                location="Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA",
                num_stops=8,
            )
        generation_log = log_capture.getvalue()

        os.makedirs("tours", exist_ok=True)
        with open(mfa_file, "w") as f:
            f.write(tour_text)

        print(f"\n  Tour written to: {mfa_file}")
        print(f"  Total words: {word_count(tour_text)}")

        # --- Print key log lines ---
        # Stop count invariant
        invariant_lines = [l for l in generation_log.split('\n') if 'STOP COUNT INVARIANT' in l or 'Stop count invariant' in l]
        for il in invariant_lines:
            print(f"  {il.strip()}")

        # Below-floor log lines
        below_floor_lines = [l for l in generation_log.split('\n') if 'below_floor' in l]
        for bf in below_floor_lines:
            print(f"  {bf.strip()}")

        # Best description safety net activations
        safety_lines = [l for l in generation_log.split('\n') if 'prior valid description exists' in l]
        for sl in safety_lines:
            print(f"  {sl.strip()}")

        # Beat unrecoverable (should happen for some beats — that's OK)
        unrec_lines = [l for l in generation_log.split('\n') if 'beat_unrecoverable' in l]
        if unrec_lines:
            print(f"\n  Beat unrecoverables ({len(unrec_lines)}):")
            for ul in unrec_lines[:5]:
                print(f"    {ul.strip()}")

        # --- Run checks ---
        errors = check_mfa_tour(tour_text, generation_log)
        if errors:
            print(f"\n  ❌ FAILURES ({len(errors)}):")
            for e in errors:
                print(f"    • {e}")
            all_pass = False
        else:
            print("\n  ✅ ALL MFA CHECKS PASS")

        # Per-stop detail
        stops = split_stops(tour_text)
        print(f"\n  Stops found: {len(stops)}")
        for i, stop in enumerate(stops):
            header = stop.split('\n')[0][:80]
            wc = word_count(stop)
            print(f"    Stop {i+1}: {wc} words — {header}")

    except Exception as e:
        print(f"\n  ❌ GENERATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        all_pass = False

    # --- Case 2: Palais Lascaris ---
    print("\n" + "=" * 70)
    print("CASE 2: Palais Lascaris, Nice, France (4 stops) — D302 control")
    print("=" * 70)

    lascaris_file = "tours/acceptance_local394_lascaris.txt"
    try:
        log_capture = io.StringIO()
        import contextlib
        with contextlib.redirect_stdout(log_capture):
            tour_text = generate_tour_text(
                location="Palais Lascaris, Nice, France",
                num_stops=4,
            )
        generation_log = log_capture.getvalue()

        os.makedirs("tours", exist_ok=True)
        with open(lascaris_file, "w") as f:
            f.write(tour_text)
        print(f"\n  Tour written to: {lascaris_file}")
        print(f"  Total words: {word_count(tour_text)}")

        # Key logs
        invariant_lines = [l for l in generation_log.split('\n') if 'Stop count invariant' in l]
        for il in invariant_lines:
            print(f"  {il.strip()}")

        errors = check_palais_lascaris(tour_text, lascaris_file, generation_log)
        if errors:
            print(f"\n  ❌ FAILURES ({len(errors)}):")
            for e in errors:
                print(f"    • {e}")
            all_pass = False
        else:
            print("\n  ✅ ALL PALAIS LASCARIS CHECKS PASS")

        stops = split_stops(tour_text)
        print(f"\n  Stops found: {len(stops)}")
        for i, stop in enumerate(stops):
            header = stop.split('\n')[0][:80]
            wc = word_count(stop)
            print(f"    Stop {i+1}: {wc} words — {header}")

    except Exception as e:
        print(f"\n  ❌ GENERATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        all_pass = False

    # --- Final verdict ---
    print("\n" + "=" * 70)
    if all_pass:
        print("✅ LOCAL-394 ACCEPTANCE: ALL PASS")
    else:
        print("❌ LOCAL-394 ACCEPTANCE: FAILED")
    print("=" * 70)
    sys.exit(0 if all_pass else 1)


if __name__ == '__main__':
    main()
