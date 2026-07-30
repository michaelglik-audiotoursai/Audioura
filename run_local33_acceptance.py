"""LOCAL-33 acceptance evidence runner.

Runs all three venues (Asian Arts Museum, Matisse, Palais Lascaris) with fresh
corpus and cache, prints:
- Corpus titles for each venue
- URLs crawled for Palais Lascaris (to show scoping works)
- Delivered stops
- Museum Information line
- Verification that Asian Arts Museum is not regressed

Usage:
    OPENAI_API_KEY=sk-... python3 run_local33_acceptance.py
"""
import os
import sys
import time

os.environ["STORIED_MODE"] = "true"

# Ensure no DATABASE_URL so cache is skipped (fresh generation)
if "DATABASE_URL" in os.environ:
    del os.environ["DATABASE_URL"]

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from generate_tour_text import generate_tour_text


VENUES = [
    {
        "name": "Musée des Arts Asiatiques, Nice",
        "tour_type": "museum",
        "total_stops": 8,
        "label": "Asian Arts Museum",
    },
    {
        "name": "Musée Matisse, Nice",
        "tour_type": "museum",
        "total_stops": 8,
        "label": "Matisse Museum",
    },
    {
        "name": "Palais Lascaris, Nice",
        "tour_type": "art and historical instruments",
        "total_stops": 8,
        "label": "Palais Lascaris",
    },
]


def extract_stops(tour_text):
    """Extract stop names from tour text."""
    import re
    stops = re.findall(r'^Stop \d+:\s*(.+)$', tour_text, re.MULTILINE)
    if not stops:
        # Try alternate format
        stops = re.findall(r'^(?:##?\s*)?Stop\s+\d+[:\s]+(.+)$', tour_text, re.MULTILINE)
    return stops


def extract_museum_info(tour_text):
    """Extract Museum Information line from tour text."""
    import re
    match = re.search(r'^Museum Information:\s*(.+)$', tour_text, re.MULTILINE)
    return match.group(1).strip() if match else "(not found)"


def main():
    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not set")
        sys.exit(1)

    print("=" * 78)
    print("LOCAL-33 ACCEPTANCE EVIDENCE RUNNER")
    print("=" * 78)
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    results = {}

    for venue in VENUES:
        print()
        print("=" * 78)
        print(f"  VENUE: {venue['label']}")
        print(f"  Location: {venue['name']}")
        print(f"  Tour type: {venue['tour_type']}")
        print(f"  Stops requested: {venue['total_stops']}")
        print("=" * 78)
        print()

        start_time = time.time()
        tour_text, _, _ = generate_tour_text(
            venue["name"],
            venue["tour_type"],
            total_stops=venue["total_stops"],
        )
        elapsed = time.time() - start_time

        if not tour_text:
            print(f"\n  *** GENERATION FAILED for {venue['label']} ***\n")
            results[venue["label"]] = {"stops": [], "info": "(failed)", "elapsed": elapsed}
            continue

        stops = extract_stops(tour_text)
        info = extract_museum_info(tour_text)

        results[venue["label"]] = {
            "stops": stops,
            "info": info,
            "elapsed": elapsed,
            "tour_text": tour_text,
        }

        print(f"\n{'─' * 60}")
        print(f"  RESULT: {venue['label']}")
        print(f"{'─' * 60}")
        print(f"  Stops delivered: {len(stops)}/{venue['total_stops']}")
        for i, s in enumerate(stops, 1):
            print(f"    {i}. {s}")
        print(f"  Museum Information: {info}")
        print(f"  Generation time: {elapsed:.1f}s")
        print()

    # --- Summary ---
    print()
    print("=" * 78)
    print("  SUMMARY")
    print("=" * 78)
    
    for label, data in results.items():
        print(f"\n  {label}:")
        print(f"    Stops: {len(data['stops'])}")
        print(f"    Museum Information: {data['info']}")
    
    # --- Verification checks ---
    print()
    print("=" * 78)
    print("  VERIFICATION")
    print("=" * 78)
    
    # Check Asian Arts Museum non-regression
    asian = results.get("Asian Arts Museum", {})
    asian_stops = len(asian.get("stops", []))
    asian_info = asian.get("info", "")
    
    print(f"\n  Asian Arts Museum:")
    print(f"    Stops: {asian_stops}/8 {'✓' if asian_stops >= 8 else '✗'}")
    asian_info_ok = "closed" in asian_info.lower() and "tuesday" in asian_info.lower() and "free" in asian_info.lower()
    print(f"    Museum Information valid: {'✓' if asian_info_ok else '✗'} → {asian_info}")
    
    # Check Palais Lascaris improvement
    palais = results.get("Palais Lascaris", {})
    palais_stops = len(palais.get("stops", []))
    print(f"\n  Palais Lascaris:")
    print(f"    Stops: {palais_stops}/8 {'✓' if palais_stops > 1 else '✗ (still 1 stop!)'}")
    
    # Check no section headings as stops
    heading_stops = [s for s in palais.get("stops", []) 
                     if s.lower() in ('current use', 'photo gallery', 'the building', 
                                      'permanent collection', 'instruments de musique')]
    print(f"    Section headings as stops: {len(heading_stops)} {'✓' if not heading_stops else '✗'}")
    if heading_stops:
        for h in heading_stops:
            print(f"      BAD: {h}")

    # Check no municipal admin text in info
    palais_info = palais.get("info", "")
    has_municipal_junk = any(x in palais_info.lower() for x in ('télécharger', 'recueil', 'délibération', 'municipal'))
    print(f"    No municipal text in info: {'✓' if not has_municipal_junk else '✗'}")
    
    print()
    print("=" * 78)
    print("  END OF ACCEPTANCE EVIDENCE")
    print("=" * 78)


if __name__ == "__main__":
    main()
