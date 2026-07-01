"""
regression_all_tour_types.py — Beta parity across all 4 categories.
Task [S65]: Run STORIED_MODE=false regression for museum, walking, restaurant, specialized.
Requires OPENAI_API_KEY.
"""
import os
import sys
import re

os.environ["STORIED_MODE"] = "false"

TOUR_CONFIGS = [
    {"name": "Museum", "location": "Musée National Marc Chagall, Nice", "tour_type": "art and paintings", "total_stops": 10},
    {"name": "Walking", "location": "Beacon Hill, Boston", "tour_type": "walking", "total_stops": 8},
    {"name": "Restaurant", "location": "North End, Boston", "tour_type": "restaurant", "total_stops": 8},
    {"name": "Specialized", "location": "Harry Potter filming locations, London", "tour_type": "movie locations", "total_stops": 8},
]

PASS_COUNT = 0
FAIL_COUNT = 0

def check(name, condition, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        print(f"    PASS: {name}")
        PASS_COUNT += 1
    else:
        print(f"    FAIL: {name} — {detail}")
        FAIL_COUNT += 1

def run_assertions(tour_text, config):
    """Run 6 assertions on generated tour."""
    # 1. Stop count matches requested
    stops = re.findall(r"Stop\s+\d+[:\.]", tour_text)
    check("Stop count matches", len(stops) >= config["total_stops"] - 2,
          f"expected ~{config['total_stops']}, got {len(stops)}")
    
    # 2. Stop names present (at least half are non-generic)
    names = re.findall(r"Stop\s+\d+[:\.]?\s*(.+?)(?:\n|$)", tour_text)
    real_names = [n for n in names if not re.match(r"^(Location|Stop|Place)\s*\d", n)]
    check("Real stop names", len(real_names) >= len(names) // 2,
          f"{len(real_names)}/{len(names)} real names")
    
    # 3. No Introduction block
    check("No Introduction block", "Introduction:" not in tour_text)
    
    # 4. No Artist's View labels
    check("No Artist's View labels", "\U0001f3a8 Artist's View:" not in tour_text)
    
    # 5. No STORIED/SPINE in output
    has_storied = bool(re.search(r"\bSTORIED\b", tour_text))
    has_spine = bool(re.search(r"\bSPINE\b", tour_text))
    check("No STORIED/SPINE text", not has_storied and not has_spine)
    
    # 6. Tour completed without error (non-empty)
    check("Tour non-empty", len(tour_text) > 500, f"length={len(tour_text)}")

def main():
    print("=" * 70)
    print("REGRESSION: Beta Parity — All 4 Tour Types (STORIED_MODE=false)")
    print("=" * 70)
    
    if not os.environ.get("OPENAI_API_KEY"):
        print("FAIL: OPENAI_API_KEY not set.")
        sys.exit(1)
    
    from generate_tour_text import generate_tour_text
    
    for config in TOUR_CONFIGS:
        print(f"\n{'─' * 50}")
        print(f"  {config['name']} Tour: {config['location']}")
        print(f"{'─' * 50}")
        
        tour_text, _, _ = generate_tour_text(
            location=config["location"],
            tour_type=config["tour_type"],
            total_stops=config["total_stops"],
            persona=None,
        )
        
        if tour_text is None:
            print(f"    FAIL: Generation returned None")
            FAIL_COUNT += 6
            continue
        
        run_assertions(tour_text, config)
    
    print(f"\n{'=' * 70}")
    print(f"Results: {PASS_COUNT} PASS, {FAIL_COUNT} FAIL (24 total assertions)")
    if FAIL_COUNT == 0:
        print("ALL TOUR TYPES PASS — Beta parity confirmed across all categories")
    else:
        print(f"{FAIL_COUNT} assertion(s) FAILED")
    print("=" * 70)
    sys.exit(0 if FAIL_COUNT == 0 else 1)

if __name__ == "__main__":
    main()
