"""
test_local24_live_regeneration.py — LOCAL-24 live 8-stop tour regeneration.

Runs a fresh tour generation for Asian Arts Museum Nice in an isolated container,
verifies no stop is a program/workshop/gallery-meta/section heading, and no
invented artist appears.
"""
import os
import sys
import re
import json

os.environ["STORIED_MODE"] = "true"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_live_regeneration():
    """Generate a fresh 8-stop tour and analyze it."""
    from generate_tour_text import generate_tour_text
    
    location = "Asian arts museum, nice, France"
    tour_type = "museum"
    total_stops = 8
    
    print("=" * 70)
    print(f"LOCAL-24 LIVE REGENERATION: {location}")
    print(f"  tour_type={tour_type}, total_stops={total_stops}")
    print("=" * 70)
    
    tour_text, tour_title, extras = generate_tour_text(
        location, tour_type, total_stops=total_stops
    )
    
    if not tour_text:
        print("\n  FAIL: Tour generation returned empty text")
        return None
    
    print(f"\n{'=' * 70}")
    print("FULL TOUR TEXT")
    print("=" * 70)
    print(tour_text)
    print("=" * 70)
    
    # --- Analysis ---
    print(f"\n{'=' * 70}")
    print("ANALYSIS")
    print("=" * 70)
    
    # Extract stops
    stop_pattern = re.compile(r'(?:Stop|Arrêt)\s+(\d+)(?:\s*[-:–]|\s*\.)\s*(.*?)(?:\n|$)', re.IGNORECASE)
    stops = stop_pattern.findall(tour_text)
    
    # Also try "## Stop N" markdown pattern
    if not stops:
        stop_pattern2 = re.compile(r'#{1,3}\s*(?:Stop|Arrêt)\s+(\d+)[:\s.-]*(.*?)(?:\n|$)', re.IGNORECASE)
        stops = stop_pattern2.findall(tour_text)
    
    # Also try numbered sections
    if not stops:
        stop_pattern3 = re.compile(r'(\d+)\.\s+\*\*([^*]+)\*\*', re.MULTILINE)
        stops = stop_pattern3.findall(tour_text)
    
    print(f"\n  Stop count: {len(stops)}")
    
    # Known problematic titles that MUST NOT appear as stops
    _EXCLUDED_TITLES_LOWER = {
        'promenade des anglais',
        "origin of the museum's pieces",
        "the museum's collections",
        'monstre de poche', 'monstres de poche', 'monstres et cie',
        'super-héros, super-pouvoirs', 'super-heros super-pouvoirs',
        'voyage en asie',
        'en harmonie avec la nature',
        'pour ne pas perdre la mémoire', 'pour ne pas perdre la memoire',
    }
    
    _GALLERY_TITLES_LOWER = {
        "l'asie du sud-est", 'asie du sud-est',
        'le japon, pays du soleil levant', 'japon pays du soleil levant',
        'les quatre grands courants religieux', 'quatre grands courants',
        'rites et cérémonies en asie', 'rites et ceremonies en asie',
    }
    
    issues = []
    for stop_num, stop_name in stops:
        _lower = stop_name.strip().lower()
        print(f"  Stop {stop_num}: {stop_name.strip()}")
        
        if any(excl in _lower for excl in _EXCLUDED_TITLES_LOWER):
            issues.append(f"Stop {stop_num} is an excluded non-work: '{stop_name.strip()}'")
        
        if any(gal in _lower for gal in _GALLERY_TITLES_LOWER):
            # Gallery names are allowed but should be noted
            print(f"    [NOTE: gallery-name stop — allowed but flagged]")
    
    # Check for invented artists
    # Look for "created by" or "by the" + proper name patterns
    _KNOWN_REAL_ARTISTS = {'kenzo tange', 'hokusai', 'katsushika hokusai'}
    _artist_pattern = re.compile(
        r'(?:created|designed|crafted|made|painted|sculpted)\s+by\s+(?:the\s+)?(?:esteemed|renowned|famous|celebrated)?\s*(?:artist|sculptor|painter|craftsman)?\s*\*?\*?([A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)+)',
        re.MULTILINE
    )
    artist_mentions = _artist_pattern.findall(tour_text)
    for artist in artist_mentions:
        if artist.lower().strip() not in _KNOWN_REAL_ARTISTS:
            # Check if this might be fabricated
            issues.append(f"Potential fabricated artist attribution: '{artist}'")
            print(f"  WARNING: Artist attribution '{artist}' — verify this is real")
    
    # Check for "Hiroshi Yoshida" specifically (the known fabrication from task)
    if 'hiroshi yoshida' in tour_text.lower():
        issues.append("FABRICATION: 'Hiroshi Yoshida' appears in tour (known fabricated attribution)")
    
    print(f"\n  Issues found: {len(issues)}")
    for issue in issues:
        print(f"    ⚠ {issue}")
    
    if not issues:
        print("    ✓ No programs, workshops, or fabricated artists detected")
    
    return {
        'tour_text': tour_text,
        'stop_count': len(stops),
        'stops': stops,
        'issues': issues,
    }


if __name__ == "__main__":
    result = run_live_regeneration()
    if result:
        print(f"\n{'=' * 70}")
        print(f"SUMMARY: {result['stop_count']} stops, {len(result['issues'])} issues")
        if result['stop_count'] >= 7:
            print("  ✓ Stop count preserved (≥7)")
        else:
            print(f"  ⚠ Stop count dropped to {result['stop_count']} (was 7 in LOCAL-23)")
        print("=" * 70)
