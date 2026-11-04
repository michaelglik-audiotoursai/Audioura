"""LOCAL-864: every UNSOURCED claim in a run log vs the delivered text.
Usage (repo root): python3 submission_artifacts/local864/check_unsourced_vs_text.py <run.log> <delivered.txt>
A hit is a flagged claim (or a person named in it) present in a sentence that is not
disclosed (D760). Venue names are not people."""
import re,sys
sys.path.insert(0,'.')
import museum_claim_gate as g
log=open(sys.argv[1]).read(); txt=open(sys.argv[2]).read()
VEN={"asian art museum","musee d'orsay","orsay"}
claims=sorted(set(re.findall(r"UNSOURCED: '([^']+)'",log)))
low=g._fold(txt); bad=[]
for c in claims:
    names=[m.group(1) for m in g._NAME_RE.finditer(c) if g._fold(m.group(1)) not in VEN]
    keys=[c]+names
    for k in keys:
        kf=g._fold(k)
        for m in re.finditer(re.escape(kf),low):
            # the sentence holding it
            a=low.rfind('.',0,m.start())+1; b=low.find('.',m.end()); sent=txt[a:b+1].strip()
            if not g.is_disclosed(sent): bad.append((c,k,sent[:160]))
print(f"{len(claims)} UNSOURCED claims in log; undisclosed in delivered text: {len(bad)}")
for c in claims: print('  -',c)
for x in bad: print('  !!',x)
