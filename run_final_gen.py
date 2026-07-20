"""Final Story Mining generation for the Chagall museum."""
import sys, os
sys.path.insert(0, '/app')
os.environ['STORIED_MODE'] = 'true'
if 'DATABASE_URL' in os.environ:
    del os.environ['DATABASE_URL']

from generate_tour_text import generate_tour_text
result = generate_tour_text(
    'Musee National Marc Chagall, Nice', 
    'museum', 
    output_file='/app/tours/story_mining_chagall_final.txt', 
    total_stops=10, 
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
    print("FAILED")
    print(f"{'='*60}")
