import sys, os, time, json
sys.path.insert(0, '/Users/micha/Audioura')
os.chdir('/Users/micha/Audioura')
loc = sys.argv[1]; ttype = sys.argv[2]; stops = int(sys.argv[3]); out = sys.argv[4]
t0 = time.time()
from generate_tour_text import generate_tour_text
res = generate_tour_text(loc, ttype, out, stops)
text = res[0] if isinstance(res, tuple) else res
el = time.time() - t0
print(f"\n=== RESULT: {'OK' if text else 'FAILED'} chars={len(text) if text else 0} elapsed={el:.1f}s")
