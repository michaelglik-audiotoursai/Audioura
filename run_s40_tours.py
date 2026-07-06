"""Generate 3 additional Storied tours for S40 content QA."""
import os
os.environ['STORIED_MODE'] = 'true'

from generate_tour_text import generate_tour_text

configs = [
    ("Beacon Hill, Boston", "walking", "storied_walking.txt", 8, "history_buff"),
    ("North End, Boston", "restaurant", "storied_restaurant.txt", 8, "first_time_visitor"),
    ("Harry Potter filming locations, London", "movie locations", "storied_book.txt", 8, "family"),
]

for loc, tt, out, stops, persona in configs:
    print(f"\n{'='*60}\nGenerating: {loc} ({tt})\n{'='*60}")
    tour, _, _ = generate_tour_text(loc, tt, output_file=out, total_stops=stops, persona=persona)
    status = "OK" if tour else "FAIL"
    length = len(tour) if tour else 0
    print(f"\nRESULT: {status} — {length} chars saved to {out}")
