"""LOCAL-865 diagnosis: why do 27 R4 candidates fail canonical match for Palais Lascaris?
Runs only the D1v2 verification (Wikidata/Wikipedia/nice.fr fetch) and prints tier + canonical set."""
import os, sys
os.environ.setdefault('STORIED_MODE', 'true')
import generate_tour_text as g
r = g._verify_works_v2([], "Palais Lascaris, Nice, France")
print("TIER", r.tier, "sparql", r.sparql_count, "qid", r.qid)
cr = r.corpus_result or {}
ct = sorted(cr.get('canonical_titles', []))
print("CANON", len(ct))
for t in ct: print("  C:", t)
print("PAGES", [(p.get('url'), len(p.get('text',''))) for p in cr.get('pages', [])])
try:
    from venue_resolver import resolve_venue
    e = resolve_venue("Palais Lascaris", "Nice"); print("ENTITY", e.qid, e.name, e.lat, e.lng)
except Exception as ex: print("entity err", ex)
