import json,glob,os,collections,sys
sys.path.insert(0,"/Users/micha/audioura-worktrees/LOCAL-566")
from cost_rates import llm_cost
REC="/tmp/local566/local560/tests/fixtures/local560/recordings"
WRITER="generate_tour_text.py:14129"
summ={s["slug"]:s for s in json.load(open(os.path.join(REC,"_run_summary.json")))}
# writer calls per tour with per-call tokens
tours=collections.defaultdict(list)
for f in sorted(glob.glob(os.path.join(REC,"*.jsonl"))):
    slug=os.path.basename(f).replace(".jsonl","")
    for line in open(f):
        r=json.loads(line)
        if (r.get("site") or r.get("caller"))==WRITER:
            u=r.get("usage") or {}
            tours[slug].append((u.get("prompt_tokens",0),u.get("completion_tokens",0),(u.get("prompt_tokens_details") or {}).get("cached_tokens",0)))

print("=== Proposal 1: fewer regenerations ===")
print(f"{'tour':<22}{'type':<11}{'stops':>5}{'calls':>6}{'c/stop':>7}{'writer$':>9}{'$if<=2/stop':>12}{'save':>8}")
tot_cur=tot_cap=0
for slug,calls in sorted(tours.items()):
    stops=summ[slug]['stops']; tt=summ[slug]['tour_type']
    cur=sum(llm_cost(input_tokens=p,output_tokens=c,model='gpt-4o') for p,c,_ in calls)
    # model: cap at 2 writes/stop. Keep the cheapest-cold + warms. Approx: scale cost by min(1, 2*stops/calls)
    cap_calls=min(len(calls), 2*stops)
    # take first cap_calls calls' cost (they include the cold+first warms)
    capcost=sum(llm_cost(input_tokens=p,output_tokens=c,model='gpt-4o') for p,c,_ in calls[:cap_calls])
    tot_cur+=cur; tot_cap+=capcost
    print(f"{slug:<22}{tt:<11}{stops:>5}{len(calls):>6}{len(calls)/stops:>7.1f}{cur:>9.3f}{capcost:>12.3f}{cur-capcost:>8.3f}")
print(f"{'TOTAL':<22}{'':<11}{'':>5}{'':>6}{'':>7}{tot_cur:>9.3f}{tot_cap:>12.3f}{tot_cur-tot_cap:>8.3f}")
print(f"  -> capping writes at 2/stop saves ${tot_cur-tot_cap:.3f} of ${tot_cur:.3f} writer cost ({100*(tot_cur-tot_cap)/tot_cur:.0f}%) across 8 tours")
print(f"  -> per-tour avg writer cost: ${tot_cur/8:.3f} -> ${tot_cap/8:.3f}")

print("\n=== Proposal 2: cheaper writer model (same token volume, cache-discounted input) ===")
# total writer tokens
PT=sum(p for cs in tours.values() for p,_,_ in cs); CT=sum(c for cs in tours.values() for _,c,_ in cs)
CACHED=sum(cc for cs in tours.values() for _,_,cc in cs)
def disc_cost(model):
    # cached input billed 50% (gpt-4o/4.1/mini all support prompt caching @50%)
    inp=llm_cost(input_tokens=PT-CACHED,output_tokens=0,model=model)+llm_cost(input_tokens=CACHED,output_tokens=0,model=model)*0.5
    out=llm_cost(input_tokens=0,output_tokens=CT,model=model)
    return inp+out
for m in ['gpt-4o','gpt-4o-mini']:
    print(f"  {m:<14} total writer ${disc_cost(m):.3f}  (per tour ${disc_cost(m)/8:.3f})")
# gpt-4.1 pricing (not in table) — note separately
print("  gpt-4.1 (not in cost_rates): list ~$2.00/1M in, $8.00/1M out — ~20% under gpt-4o")
g41=( (PT-CACHED)*2.00/1e6 + CACHED*2.00/1e6*0.5 + CT*8.00/1e6 )
print(f"    -> est total writer ${g41:.3f} (per tour ${g41/8:.3f})")
