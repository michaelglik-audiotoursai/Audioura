import json,glob,os,collections
REC="/tmp/local566/local560/tests/fixtures/local560/recordings"
summ={s["slug"]:s for s in json.load(open(os.path.join(REC,"_run_summary.json")))}
WRITER="generate_tour_text.py:14129"
for f in sorted(glob.glob(os.path.join(REC,"*.jsonl"))):
    slug=os.path.basename(f).replace(".jsonl","")
    n=0
    with open(f) as fh:
        for line in fh:
            r=json.loads(line)
            if (r.get("site") or r.get("caller"))==WRITER: n+=1
    stops=summ[slug]["stops"]; ttype=summ[slug]["tour_type"]
    rm=summ[slug]["phase517"]["retry_markers"]
    print(f"{slug:<24}{ttype:<11} stops={stops} writer_calls={n:>3}  calls/stop={n/stops:>4.1f}  phase517_retry_markers={rm}")
