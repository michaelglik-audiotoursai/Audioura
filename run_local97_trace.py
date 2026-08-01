#!/usr/bin/env python3
"""LOCAL-97 Trace: Where do catalogue facts get lost?

Single run of Asian Arts Museum, N=8. Captures:
1. The evidence_log content (what period/material/origin each stop has)
2. The fact_sheet content (what the GPT-3.5 extractor returned)
3. Whether the C5-1 binding block fired per stop
4. The final tour text for each stop

This is diagnostic — it does NOT generate via the HTTP service. It calls
generate_tour_text() directly to instrument the internals.
"""
import json
import os
import sys
import time

# Set STORIED_MODE so the full pipeline runs
os.environ['STORIED_MODE'] = 'true'
os.environ['TOUR_TEST_MODE'] = 'true'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from generate_tour_text import generate_audio_tour

LOCATION = "Musée des Arts Asiatiques, Nice"
TOUR_TYPE = "museum tour"
TOTAL_STOPS = 8
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tours")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def bust_cache():
    """Delete cached tour so generation is fresh."""
    import hashlib
    try:
        import psycopg2
        raw = f"{LOCATION.strip().lower()}|{TOUR_TYPE.strip().lower()}|{TOTAL_STOPS}"
        key = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        conn = psycopg2.connect("postgresql://admin:password123@localhost:5432/audiotours")
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tour_cache WHERE cache_key = %s", (key,))
            conn.commit()
        conn.close()
        print(f"[cache] Busted tour_cache for key={key[:16]}...")
    except Exception as e:
        print(f"[cache] Warning: {e}")


def main():
    print("=" * 70)
    print("LOCAL-97 TRACE: Where do catalogue facts get lost?")
    print("=" * 70)
    print(f"Venue: {LOCATION}")
    print(f"Stops: {TOTAL_STOPS}")
    print()

    # Get API key
    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        # Try to get from Docker env
        import subprocess
        try:
            result = subprocess.run(
                ['docker', 'exec', 'audioura-tour-generator-1', 'printenv', 'OPENAI_API_KEY'],
                capture_output=True, text=True, timeout=10
            )
            api_key = result.stdout.strip()
        except Exception:
            pass
    if not api_key:
        print("ERROR: No OPENAI_API_KEY found")
        sys.exit(1)
    
    os.environ['OPENAI_API_KEY'] = api_key
    print(f"[OK] API key: {api_key[:8]}...{api_key[-4:]}")

    bust_cache()
    
    output_file = os.path.join(OUTPUT_DIR, "local97_trace_asian_arts.txt")
    
    start = time.time()
    print(f"\n{'='*70}")
    print("Starting generation...")
    print(f"{'='*70}\n")
    
    result = generate_audio_tour(
        location=LOCATION,
        tour_type=TOUR_TYPE,
        total_stops=TOTAL_STOPS,
        api_key=api_key,
        output_file=output_file,
    )
    
    elapsed = time.time() - start
    print(f"\n{'='*70}")
    print(f"Generation complete in {elapsed:.1f}s")
    print(f"{'='*70}\n")
    
    if result is None or (isinstance(result, tuple) and result[0] is None):
        print("ERROR: Generation returned None")
        sys.exit(1)
    
    # Now read the evidence log that was written
    evidence_file = output_file.replace('.txt', '_evidence_log.json')
    if os.path.exists(evidence_file):
        with open(evidence_file, 'r', encoding='utf-8') as f:
            evidence_log = json.load(f)
        
        print("\n" + "=" * 70)
        print("EVIDENCE LOG — Catalogue metadata per stop")
        print("=" * 70)
        for title, ev in evidence_log.items():
            method = ev.get('method', '?')
            period = ev.get('period', '')
            material = ev.get('material', '')
            origin = ev.get('origin', '')
            status = ev.get('status', '?')
            print(f"\n  [{status}] {title}")
            print(f"    method: {method}")
            print(f"    period: '{period}' {'✓' if period else '✗ EMPTY'}")
            print(f"    material: '{material}' {'✓' if material else '✗ EMPTY'}")
            print(f"    origin: '{origin}' {'✓' if origin else '—'}")
    else:
        print(f"\nWARNING: No evidence log file at {evidence_file}")
    
    # Check the generated tour text for each stop
    if os.path.exists(output_file):
        with open(output_file, 'r', encoding='utf-8') as f:
            tour_text = f.read()
        
        print("\n" + "=" * 70)
        print("STOP CONTENT ANALYSIS — Do catalogue facts appear in the output?")
        print("=" * 70)
        
        # Expected facts from the catalogue
        EXPECTED = {
            "L'Armure d'Andô Naoyuki": {
                'period': 'milieu du XIXe siècle',
                'material': 'acier, cuivre, cuir, soie, laque, feuille d\'or',
            },
            "Statue de Bouddha": {
                'period': 'IIe siècle',
                'material': 'schiste gris',
            },
            "La danse cosmique de Ganesh": {
                'period': '2nde moitié du Xe siècle',
                'material': 'chlorite',
            },
            "Kannon, le bodhisattva de la compassion": {
                'period': 'seconde moitié du XIIe siècle',
                'material': 'bois de cyprès',
            },
            "Ulysses Grant au Japon": {
                'period': '1879',
                'material': 'polychrome sur papier',
            },
            "Robe de prêtre taoïste": {
                'period': 'XVe siècle',
                'material': 'soie',
            },
        }
        
        # Split by stops
        stops = tour_text.split("Stop ")
        for i, stop in enumerate(stops[1:], 1):
            # Get first line (stop title)
            first_line = stop.split('\n')[0].strip()
            title = first_line.split(': ', 1)[1] if ': ' in first_line else first_line
            
            # Check for expected facts
            expected = None
            for exp_title, exp_facts in EXPECTED.items():
                if exp_title.lower() in title.lower() or title.lower() in exp_title.lower():
                    expected = exp_facts
                    exp_title_match = exp_title
                    break
            
            print(f"\n  Stop {i}: {title}")
            if expected:
                period_found = expected['period'].lower() in stop.lower()
                material_found = any(m.strip().lower() in stop.lower() 
                                   for m in expected['material'].split(','))
                print(f"    Expected period: '{expected['period']}' → {'FOUND ✓' if period_found else 'MISSING ✗'}")
                print(f"    Expected material: '{expected['material']}' → {'FOUND ✓' if material_found else 'MISSING ✗'}")
                if not period_found or not material_found:
                    # Show what the stop actually says (first 200 chars of description)
                    desc_start = stop.find('\n\n')
                    if desc_start > 0:
                        desc = stop[desc_start:desc_start+300].strip()
                        print(f"    Actual text begins: {desc[:150]}...")
            else:
                print(f"    (No catalogue entry expected for this stop)")
    
    # Report cost
    print(f"\n{'='*70}")
    print(f"TRACE COMPLETE")
    print(f"Time: {elapsed:.1f}s")
    print(f"Output: {output_file}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
