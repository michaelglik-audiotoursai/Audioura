"""Generate a tour for Musée Eugène Boudin, Honfleur — expected medium tier (4 SPARQL works)."""
import sys, os
sys.path.insert(0, '/app')
os.environ['STORIED_MODE'] = 'true'
if 'DATABASE_URL' in os.environ:
    del os.environ['DATABASE_URL']

from generate_tour_text import generate_tour_text
result = generate_tour_text(
    'Musee Eugene Boudin, Honfleur, France', 
    'museum', 
    output_file='/app/tours/phase2_medium_boudin.txt', 
    total_stops=8, 
    persona='art_lover'
)
if result and result[0]:
    text = result[0]
    import re
    stops = re.findall(r'^Stop \d+:', text, re.MULTILINE)
    print(f"\n{'='*60}")
    print(f"SUCCESS: {len(text)} chars, {len(text.split())} words, {len(stops)} stops")
    print(f"{'='*60}")
else:
    print(f"\n{'='*60}")
    print("FAILED: Tour generation returned None")
    print(f"{'='*60}")
