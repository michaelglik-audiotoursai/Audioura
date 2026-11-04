"""LOCAL-864: replay the FINAL claim gate over live run 2's delivered Asian Art text.
No network, no LLM. Catalog records = the museum's own label blocks (test fixtures,
copied from collections.asianart.org). The run-2 gate had already removed the Miro
attribution sentence; it is re-inserted so stop 3 is gated as the run saw it.
Run from the repo root:  python3 submission_artifacts/local864/replay_final_gate.py"""
import os, re, sys
sys.path[:0] = ['.', 'tests']
import museum_claim_gate as g
from test_local864_museum_claim_gate import B338_HTML, CROWNED_HTML
D = 'submission_artifacts/local864/'
t=open(D+'asian_run2_delivered.txt').read()
# re-insert the sentences the in-run gate dropped (log lines), so stops 3/4 look as the gate saw them
B=B338_HTML; C=CROWNED_HTML
cache=['https://collections.asianart.org/collection/seated-buddha-dated-338/','https://collections.asianart.org/collection/crowned-and-bejeweled-buddha-image-and-throne/']
pages={cache[0]:B,cache[1]:C}
titles=dict((int(n),x.strip()) for n,x in re.findall(r'(?m)^Stop (\d+): (.+)$',t))
cats={}
for n,ti in titles.items():
    for u in g.catalog_urls_from_snippets(ti,[{'url':u} for u in cache],'http://www.asianart.org'):
        r=g.parse_label_block(pages[u],ti)
        if r: cats[n]=r; break
pre=t.replace("This piece distills","Joan Miró painted Head of a Catalan Peasant between 1924 and 1925. This piece distills",1); assert pre!=t
snips={3:[{'title':'Head of a Catalan Peasant | Tate','snippet':'Joan Miró 1925'}],
       4:[{'title':'Bacchante in a Landscape | The Met','snippet':'Camille Corot 1865-70'}]}
new,rep=g.filter_tour_text_claims(pre,{n:[] for n in titles},stop_catalogs=cats,stop_titles=titles,
   stop_own_evidence={n:[str(c)] for n,c in cats.items()},venue_name='Asian Art Museum',stop_snippets=snips)
for r in rep['removed']: print(' -',r['stop'],r['reason'][:70],'|',r['sentence'][:90])
open(D+'asian_run2_final_gate_replay.txt','w').write(new)
for k in ('Miró','Catalan','Corot','Bacchante','Byodo','blue stone','Ly Dynasty','Vietnam','treasure','two statues','pairing'): print(k, k in new)
