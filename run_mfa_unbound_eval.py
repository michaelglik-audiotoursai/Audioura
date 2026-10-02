"""Generate the CORRECT evaluation tour: the Unbound exhibition, 3 stops.

Michael's evaluation case is:
    "Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA", 3 stops

Every live run from LOCAL-413 onward used
    "Museum of Fine Arts, Boston, Massachusetts", 4 stops
which is a generic whole-museum highlights tour, not the exhibition.

This runner pins the real case so it cannot drift again.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

LOCATION = "Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA"
STOPS = 3

from generate_tour_text import generate_tour_text as gen_tour

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "TOUR_MFA_UNBOUND_EVAL.txt")

print("=" * 72)
print("  MFA UNBOUND EXHIBITION — evaluation tour")
print(f"  location : {LOCATION}")
print(f"  stops    : {STOPS}")
print("=" * 72)

tour_text, output_file, coords = gen_tour(
    LOCATION,
    "contained",
    out,
    total_stops=STOPS,
    persona=None,
    user_id="mfa_unbound_eval",
    job_id="mfa_unbound_eval",
)

if not tour_text:
    print("FAILED: no text generated")
    sys.exit(1)

print(f"\nCHARS: {len(tour_text)}  WORDS: {len(tour_text.split())}")
print(f"SAVED: {out}")
