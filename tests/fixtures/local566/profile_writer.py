import json, glob, os, collections, sys
sys.path.insert(0, "/Users/micha/audioura-worktrees/LOCAL-566")
from cost_rates import llm_cost

REC = "/tmp/local566/local560/tests/fixtures/local560/recordings"
WRITER = "generate_tour_text.py:14129"

# Load summary for tour_type mapping
summ = {s["slug"]: s for s in json.load(open(os.path.join(REC,"_run_summary.json")))}

writer_calls = []
for f in sorted(glob.glob(os.path.join(REC, "*.jsonl"))):
    slug = os.path.basename(f).replace(".jsonl","")
    with open(f) as fh:
        for line in fh:
            line=line.strip()
            if not line: continue
            r = json.loads(line)
            site = r.get("site") or r.get("caller")
            if site != WRITER: continue
            u = r.get("usage") or {}
            msgs = r.get("messages",[])
            writer_calls.append({
                "slug": slug, "ttype": summ[slug]["tour_type"],
                "pt": u.get("prompt_tokens",0), "ct": u.get("completion_tokens",0),
                "cached": (u.get("prompt_tokens_details") or {}).get("cached_tokens",0),
                "roles":[m.get("role") for m in msgs],
                "sys": next((m["content"] for m in msgs if m.get("role")=="system"), ""),
                "usr": next((m["content"] for m in msgs if m.get("role")=="user"), ""),
                "max_tokens": r.get("max_tokens"),
            })

print(f"=== WRITER {WRITER}: {len(writer_calls)} calls across tours ===")
# per-tour counts
byt = collections.defaultdict(lambda:{"calls":0,"pt":0,"ct":0,"cached":0,"cost":0.0,"ttype":""})
for c in writer_calls:
    a=byt[c["slug"]]; a["calls"]+=1; a["pt"]+=c["pt"]; a["ct"]+=c["ct"]; a["cached"]+=c["cached"]; a["ttype"]=c["ttype"]
    a["cost"]+=llm_cost(input_tokens=c["pt"],output_tokens=c["ct"],model="gpt-4o")
print(f"{'slug':<24}{'type':<11}{'calls':>6}{'in_tok':>9}{'out_tok':>8}{'cached':>8}{'cost$':>8}")
for slug,a in sorted(byt.items()):
    print(f"{slug:<24}{a['ttype']:<11}{a['calls']:>6}{a['pt']:>9}{a['ct']:>8}{a['cached']:>8}{a['cost']:>8.3f}")

TOT_pt=sum(c["pt"] for c in writer_calls); TOT_ct=sum(c["ct"] for c in writer_calls)
TOT_cached=sum(c["cached"] for c in writer_calls)
in_cost=sum(llm_cost(input_tokens=c["pt"],output_tokens=0,model="gpt-4o") for c in writer_calls)
out_cost=sum(llm_cost(input_tokens=0,output_tokens=c["ct"],model="gpt-4o") for c in writer_calls)
print()
print(f"Q1 INPUT vs OUTPUT share of WRITER cost:")
print(f"  input tokens {TOT_pt:,} -> ${in_cost:.4f} ({100*in_cost/(in_cost+out_cost):.1f}%)")
print(f"  output tokens {TOT_ct:,} -> ${out_cost:.4f} ({100*out_cost/(in_cost+out_cost):.1f}%)")
print(f"  cached tokens already: {TOT_cached:,} ({100*TOT_cached/TOT_pt:.1f}% of input)")

# Q2: static prefix. Compare system prompts across calls.
sys_prompts = [c["sys"] for c in writer_calls]
from collections import Counter
sysc = Counter(sys_prompts)
print(f"\nQ2 SYSTEM prompt uniqueness: {len(sysc)} distinct system prompts over {len(writer_calls)} calls")
for i,(sp,n) in enumerate(sysc.most_common(5)):
    print(f"  sys#{i}: {n} calls, {len(sp)} chars, starts: {sp[:80]!r}")

# longest common prefix of USER messages within each tour and across all
def lcp(strs):
    if not strs: return ""
    s1=min(strs); s2=max(strs)
    for i,ch in enumerate(s1):
        if ch!=s2[i]: return s1[:i]
    return s1
# approx tokens = chars/4
all_usr=[c["usr"] for c in writer_calls]
pref_all = lcp(all_usr)
print(f"\nQ2 USER message common prefix across ALL writer calls: {len(pref_all)} chars (~{len(pref_all)//4} tok)")
print(f"   prefix sample: {pref_all[:200]!r}")
# within-tour prefix
print("\nQ2 within-tour USER prefix:")
for slug in sorted(set(c['slug'] for c in writer_calls)):
    us=[c['usr'] for c in writer_calls if c['slug']==slug]
    p=lcp(us)
    print(f"  {slug:<24} {len(us)} calls, common USER prefix {len(p)} chars (~{len(p)//4} tok)")

# system prefix across all
pref_sys = lcp(sys_prompts)
print(f"\nQ2 SYSTEM common prefix across ALL: {len(pref_sys)} chars (~{len(pref_sys)//4} tok)")
