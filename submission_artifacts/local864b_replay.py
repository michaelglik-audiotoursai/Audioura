"""LOCAL-864B: replay the post-editor gate + artist scrub over a delivered live text.
Catalog records are fetched from the museum's site by the new search binding (HTTP only,
no LLM, no DB). Usage (repo root): python3 submission_artifacts/local864b_replay.py <delivered.txt> [out.txt]"""
import re, sys
sys.path[:0] = ['.']
import museum_claim_gate as g
from object_record import _fetch
t = open(sys.argv[1]).read()
V = 'http://www.asianart.org'
titles = {int(n): x.strip() for n, x in re.findall(r'(?m)^Stop (\d+): (.+)$', t)}
cats, own = {}, {}
for n, ti in titles.items():
    urls, why = g.catalog_urls_by_search(ti, V, _fetch)
    rec = {}
    for u in urls:
        rec = g.parse_label_block(_fetch(u), ti)
        if rec:
            rec['url'] = u
            break
    print(f"stop {n} {ti[:40]!r}: " + (f"catalog bound <- {rec.get('accession_number')} {rec['url']}" if rec else f"catalog miss: {why}"))
    if rec:
        cats[n] = rec
    own[n] = [str(rec)] if rec else []
kw = dict(stop_evidence={n: [] for n in titles}, stop_known={n: [] for n in titles}, stop_flagged={},
          stop_catalogs=cats, stop_titles=titles, stop_own_evidence=own, stop_artists={}, stop_makers={},
          stop_snippets={n: [] for n in titles}, venue_name='Asian Art Museum')
new, rep = g.filter_tour_text_claims_keep_tail(t, **kw)
for r in rep['removed']:
    print(' - gate stop', r['stop'], r['reason'][:70], '|', r['sentence'][:100])
new, sc = g.scrub_artists_tour(new, stop_allow={n: ' '.join(own[n]) for n in titles}, stop_titles=titles, venue_name='Asian Art Museum')
for r in sc['removed']:
    print(' - scrub', r['where'], r['stop'], r['artist'], '|', r['sentence'][:100])
open(sys.argv[2] if len(sys.argv) > 2 else '/tmp/replay_out.txt', 'w').write(new)
for k in ('blue stone', 'Amitabha', 'Amida', 'Ly Dynasty', 'Corot', 'Miró', 'Miro', 'Catalan', 'Burmese', '1860', 'Chinese', '338'):
    print(f"{k!r}: {k in new}")
