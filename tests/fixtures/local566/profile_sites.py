import json, glob, os, collections
import sys
sys.path.insert(0, "/Users/micha/audioura-worktrees/LOCAL-566")
from cost_rates import llm_cost

REC = "/tmp/local566/local560/tests/fixtures/local560/recordings"
rows = []
for f in sorted(glob.glob(os.path.join(REC, "*.jsonl"))):
    slug = os.path.basename(f).replace(".jsonl","")
    with open(f) as fh:
        for line in fh:
            line=line.strip()
            if not line: continue
            r = json.loads(line)
            u = r.get("usage") or {}
            rows.append({
                "slug": slug,
                "site": r.get("site") or r.get("caller") or "?",
                "model": r.get("model"),
                "pt": u.get("prompt_tokens",0),
                "ct": u.get("completion_tokens",0),
                "cached": (u.get("prompt_tokens_details") or {}).get("cached_tokens",0),
                "max_tokens": r.get("max_tokens"),
                "status": r.get("status"),
            })

print(f"TOTAL records: {len(rows)}")
# aggregate by site
agg = collections.defaultdict(lambda: {"calls":0,"pt":0,"ct":0,"cached":0,"cost":0.0,"models":collections.Counter()})
for r in rows:
    k = r["site"]
    a = agg[k]
    a["calls"]+=1; a["pt"]+=r["pt"]; a["ct"]+=r["ct"]; a["cached"]+=r["cached"]
    a["cost"] += llm_cost(input_tokens=r["pt"], output_tokens=r["ct"], model=r["model"] or "gpt-3.5-turbo")
    a["models"][r["model"]]+=1

total_cost = sum(a["cost"] for a in agg.values())
print(f"TOTAL llm cost across 8 tours: ${total_cost:.4f}")
print()
print(f"{'SITE':<45}{'calls':>6}{'in_tok':>9}{'out_tok':>9}{'cost$':>9}{'%':>6}  models")
for site,a in sorted(agg.items(), key=lambda x:-x[1]["cost"]):
    models = ",".join(f"{m}:{c}" for m,c in a["models"].most_common())
    print(f"{site[:44]:<45}{a['calls']:>6}{a['pt']:>9}{a['ct']:>9}{a['cost']:>9.4f}{100*a['cost']/total_cost:>6.1f}  {models}")
