import json,glob,os,collections,sys
sys.path.insert(0,"/Users/micha/audioura-worktrees/LOCAL-566")
from cost_rates import llm_cost
REC="/tmp/local566/local560/tests/fixtures/local560/recordings"
summ={s["slug"]:s for s in json.load(open(os.path.join(REC,"_run_summary.json")))}
# per tour_type, per site cost
by=collections.defaultdict(lambda:collections.defaultdict(lambda:{"calls":0,"cost":0.0,"pt":0,"ct":0,"model":""}))
for f in sorted(glob.glob(os.path.join(REC,"*.jsonl"))):
    slug=os.path.basename(f).replace(".jsonl","")
    tt=summ[slug]["tour_type"]
    with open(f) as fh:
        for line in fh:
            r=json.loads(line); u=r.get("usage") or {}
            site=r.get("site") or r.get("caller")
            a=by[tt][site]; a["calls"]+=1; a["pt"]+=u.get("prompt_tokens",0); a["ct"]+=u.get("completion_tokens",0)
            a["cost"]+=llm_cost(input_tokens=u.get("prompt_tokens",0),output_tokens=u.get("completion_tokens",0),model=r.get("model") or "gpt-3.5-turbo")
            a["model"]=r.get("model")
# museum: palais + our_lady. show top sites for museum
for tt in ["museum"]:
    print(f"=== tour_type={tt} top sites by cost (2 tours: palais+our_lady) ===")
    sites=by[tt]
    for site,a in sorted(sites.items(),key=lambda x:-x[1]["cost"])[:12]:
        print(f"  {site:<40}{a['calls']:>4} calls {a['model']:<14} in={a['pt']:>7} out={a['ct']:>6} ${a['cost']:.4f}")
