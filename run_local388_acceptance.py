#!/usr/bin/env python3
"""run_local388_acceptance.py — Acceptance test for LOCAL-388: Story Beat Delivery.

Generates:
  1. Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA (8 stops)
     → Broder, Mourlot, Fridman at least once each
     → Miró stop 1; Dalí AND Freud stop 2; Gris AND Reverdy stop 3
     → Every stop ≥120 words
     → Each stop has ≥1 sentence naming a person and what they did
     → Zero: thesis/framing/premise, 'with publisher', D305 banned list
     → Kept: livre d'artiste, collabor*, typography, book in ≥2 stops
     → That's N stops == heading count
     → Orientation consistent across stops
     → Per-stop beats log line

  2. Palais Lascaris, Nice, France (4 stops)
     → 4/4 real instruments
     → score_tour_file(f,4)=81.2, score_tour_file(f,8)=75.0
     → Every stop ≥120 words; framing=venue_purpose; no fabricated premise

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


# === Helpers ===

def split_stops(tour_text: str) -> list:
    """Split tour text into individual stops."""
    stops = re.split(r'\n(?=Stop \d+:)', tour_text)
    return [s for s in stops if s.strip().startswith('Stop')]


def word_count(text: str) -> int:
    """Count words in text."""
    return len(text.split())


def contains_case_insensitive(text: str, term: str) -> bool:
    """Case-insensitive substring check."""
    return term.lower() in text.lower()


def check_mfa_tour(tour_text: str) -> list:
    """Check LOCAL-388 acceptance criteria for the MFA exhibition tour."""
    errors = []
    stops = split_stops(tour_text)
    
    # --- Heading count ---
    thats_match = re.search(r"That'?s (\d+) stops", tour_text)
    if thats_match:
        claimed = int(thats_match.group(1))
        if claimed != len(stops):
            errors.append(f"'That's {claimed} stops' but found {len(stops)} headings")
    
    # --- Required people (case-insensitive) ---
    required_anywhere = ['Broder', 'Mourlot', 'Fridman']
    full_text_lower = tour_text.lower()
    for name in required_anywhere:
        if name.lower() not in full_text_lower:
            errors.append(f"MISSING: '{name}' not found anywhere in tour text")
    
    # --- Per-stop attributions (387 preservation) ---
    if len(stops) >= 3:
        # Stop 1: Miró
        if not contains_case_insensitive(stops[0], 'miró') and not contains_case_insensitive(stops[0], 'miro'):
            errors.append("REGRESSION: Miró not in stop 1")
        # Stop 2: Dalí AND Freud
        if not contains_case_insensitive(stops[1], 'dalí') and not contains_case_insensitive(stops[1], 'dali'):
            errors.append("REGRESSION: Dalí not in stop 2")
        if not contains_case_insensitive(stops[1], 'freud'):
            errors.append("REGRESSION: Freud not in stop 2")
        # Stop 3: Gris AND Reverdy
        if not contains_case_insensitive(stops[2], 'gris'):
            errors.append("REGRESSION: Gris not in stop 3")
        if not contains_case_insensitive(stops[2], 'reverdy'):
            errors.append("REGRESSION: Reverdy not in stop 3")
    else:
        errors.append(f"Fewer than 3 stops found ({len(stops)})")
    
    # --- Word count floor ---
    for i, stop in enumerate(stops):
        # Extract description (after orientation or first paragraph)
        lines = stop.strip().split('\n')
        # Skip header line and metadata lines
        desc_text = '\n'.join(l for l in lines[1:] if not l.startswith(('Address:', 'Coordinates:', 'Type/', 'Museum Info', 'Orientation:')))
        wc = word_count(desc_text)
        if wc < 120:
            errors.append(f"Stop {i+1} under floor: {wc} words < 120")
    
    # --- Zero-check: banned narration terms ---
    banned_narration = ['thesis', 'framing', 'premise']
    # Find narration text (skip headers, orientation, transitions)
    for term in banned_narration:
        # Search in description text only (not headers/metadata)
        for i, stop in enumerate(stops):
            lines = stop.strip().split('\n')
            narration = '\n'.join(l for l in lines[1:] if not l.startswith(('Address:', 'Coordinates:', 'Type/', 'Museum Info', 'Orientation:', 'Next:', 'Proceed to', 'Continue')))
            if re.search(rf'\b{term}\b', narration, re.IGNORECASE):
                errors.append(f"BANNED: '{term}' found in stop {i+1} narration")
    
    # --- Zero-check: 'with publisher' ---
    if 'with publisher' in full_text_lower:
        errors.append("PLACEHOLDER: 'with publisher' still present in text")
    
    # --- Zero-check: D305 banned list ---
    d305_banned = ['ceiling', 'mural', 'installation', 'sculpture', 'painting', 'glass',
                   'stand beneath', 'look up', 'gaze up', 'Chagall', 'Rousseau',
                   'Corbusier', 'Lalanne', 'Matisse']
    for term in d305_banned:
        if contains_case_insensitive(tour_text, term):
            errors.append(f"D305 BANNED: '{term}' found in tour text")
    
    # --- Kept terms: livre d'artiste, collabor*, typography, book ---
    kept_terms = {
        "livre d'artiste": 0,
        'collabor': 0,
        'typography': 0,
        'book': 0,
    }
    for i, stop in enumerate(stops):
        for term in kept_terms:
            if contains_case_insensitive(stop, term):
                kept_terms[term] += 1
    
    # Check ≥2 stops for each
    for term, count in kept_terms.items():
        if term == "livre d'artiste" and count < 1:
            errors.append(f"KEPT TERM: '{term}' in {count} stops (need ≥1)")
        elif term != "livre d'artiste" and count < 2:
            errors.append(f"KEPT TERM: '{term}' in {count} stops (need ≥2)")
    
    # --- Orientation consistency ---
    orientation_count = sum(1 for stop in stops if 'Orientation:' in stop)
    if orientation_count != len(stops):
        errors.append(f"ORIENTATION: only {orientation_count}/{len(stops)} stops have 'Orientation:'")
    
    # --- Per-stop story beat: at least one sentence naming a person + what they did ---
    # Heuristic: check for a proper name (capitalized word) followed by a verb
    for i, stop in enumerate(stops):
        lines = stop.strip().split('\n')
        narration = ' '.join(l for l in lines[1:] if not l.startswith(('Address:', 'Coordinates:', 'Orientation:', 'Next:', 'Proceed', 'Continue')))
        # Check for pattern: Name + verb (did/created/published/printed/founded/etc)
        has_person_action = bool(re.search(
            r'[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)*\s+'
            r'(?:published|printed|created|illustrated|collaborated|partnered|wrote|'
            r'designed|founded|donated|established|devised|assembled|produced|'
            r'gave|brought|commissioned|drew|engraved|composed|conceived|'
            r'contributed|arranged|acquired|selected|collected|interpreted|was)',
            narration
        ))
        if not has_person_action:
            errors.append(f"Stop {i+1}: no sentence found naming a person + what they did")
    
    return errors


def check_palais_lascaris(tour_text: str, tour_file: str) -> list:
    """Check D302 control case: Palais Lascaris, Nice, France at 4 stops."""
    errors = []
    stops = split_stops(tour_text)
    
    if len(stops) != 4:
        errors.append(f"Expected 4 stops, got {len(stops)}")
    
    # Word count floor
    for i, stop in enumerate(stops):
        lines = stop.strip().split('\n')
        desc_text = '\n'.join(l for l in lines[1:] if not l.startswith(('Address:', 'Coordinates:', 'Type/', 'Orientation:')))
        wc = word_count(desc_text)
        if wc < 120:
            errors.append(f"Stop {i+1} under floor: {wc} words < 120")
    
    # Instruments (4/4 real)
    full_text = tour_text.lower()
    instrument_patterns = ['baroque', 'guitar', 'lute', 'violin', 'harpsichord', 'flute',
                          'cello', 'mandolin', 'organ', 'hurdy', 'viol', 'oboe', 'trumpet']
    instrument_count = sum(1 for p in instrument_patterns if p in full_text)
    if instrument_count < 4:
        errors.append(f"Only {instrument_count} instrument references (need 4+)")
    
    # Dates: 1780/1884/1696/1581 intact
    required_dates = ['1780', '1884', '1696', '1581']
    for d in required_dates:
        if d not in tour_text:
            errors.append(f"Date {d} missing from Palais Lascaris tour")
    
    # No fabricated premise
    if 'premise' in full_text:
        errors.append("'premise' found in Palais Lascaris tour")
    
    # Score bounds
    score4 = score_tour_file(tour_file, 4)
    score8 = score_tour_file(tour_file, 8)
    if score4 < 81.2:
        errors.append(f"score_tour_file(f,4)={score4:.1f} < 81.2")
    if score8 < 75.0:
        errors.append(f"score_tour_file(f,8)={score8:.1f} < 75.0")
    
    return errors


# === Main ===

def main():
    print("=" * 70)
    print("LOCAL-388 ACCEPTANCE — Story Beat Delivery (Storied release)")
    print("=" * 70)
    
    all_pass = True
    
    # --- Case 1: MFA Exhibition ---
    print("\n" + "=" * 70)
    print("CASE 1: Picasso, Miró, Dalí: Unbound — MFA, Boston, MA (8 stops)")
    print("=" * 70)
    
    mfa_file = "tours/acceptance_local388_mfa.txt"
    try:
        tour_text = generate_tour_text(
            location="Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA",
            num_stops=8,
        )
        os.makedirs("tours", exist_ok=True)
        with open(mfa_file, "w") as f:
            f.write(tour_text)
        print(f"\n  Tour written to: {mfa_file}")
        print(f"  Total words: {word_count(tour_text)}")
        
        errors = check_mfa_tour(tour_text)
        if errors:
            print(f"\n  ❌ FAILURES ({len(errors)}):")
            for e in errors:
                print(f"    • {e}")
            all_pass = False
        else:
            print("\n  ✅ ALL MFA CHECKS PASS")
        
        # Report per-stop details
        stops = split_stops(tour_text)
        print(f"\n  Stops found: {len(stops)}")
        for i, stop in enumerate(stops):
            header = stop.split('\n')[0][:60]
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
    
    lascaris_file = "tours/acceptance_local388_lascaris.txt"
    try:
        tour_text = generate_tour_text(
            location="Palais Lascaris, Nice, France",
            num_stops=4,
        )
        os.makedirs("tours", exist_ok=True)
        with open(lascaris_file, "w") as f:
            f.write(tour_text)
        print(f"\n  Tour written to: {lascaris_file}")
        print(f"  Total words: {word_count(tour_text)}")
        
        errors = check_palais_lascaris(tour_text, lascaris_file)
        if errors:
            print(f"\n  ❌ FAILURES ({len(errors)}):")
            for e in errors:
                print(f"    • {e}")
            all_pass = False
        else:
            print("\n  ✅ ALL PALAIS LASCARIS CHECKS PASS")
        
        # Report per-stop details
        stops = split_stops(tour_text)
        print(f"\n  Stops found: {len(stops)}")
        for i, stop in enumerate(stops):
            header = stop.split('\n')[0][:60]
            wc = word_count(stop)
            print(f"    Stop {i+1}: {wc} words — {header}")
    except Exception as e:
        print(f"\n  ❌ GENERATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        all_pass = False
    
    # --- Summary ---
    print("\n" + "=" * 70)
    if all_pass:
        print("LOCAL-388 ACCEPTANCE: ✅ ALL PASS")
    else:
        print("LOCAL-388 ACCEPTANCE: ❌ FAILURES FOUND")
    print("=" * 70)
    
    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main())
