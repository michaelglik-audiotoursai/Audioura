import json, glob, os, collections, sys
REC = "/tmp/local566/local560/tests/fixtures/local560/recordings"
WRITER = "generate_tour_text.py:14129"
summ={s["slug"]:s for s in json.load(open(os.path.join(REC,"_run_summary.json")))}

# For palais (39 writer calls), look at sequence of pt/cached to see caching warmup
for target in ["palais_lascaris_nice","logan_airport"]:
    print(f"\n=== {target} ({summ[target]['tour_type']}) writer call sequence ===")
    seq=[]
    with open(os.path.join(REC,target+".jsonl")) as fh:
        for line in fh:
            r=json.loads(line)
            if (r.get("site") or r.get("caller"))==WRITER:
                u=r.get("usage") or {}
                usr=next((m["content"] for m in r["messages"] if m["role"]=="user"),"")
                seq.append((u.get("prompt_tokens",0),(u.get("prompt_tokens_details") or {}).get("cached_tokens",0),len(usr)))
    print(f"{'#':>3}{'in_tok':>8}{'cached':>8}{'cache%':>8}{'usr_chars':>10}")
    for i,(pt,c,uc) in enumerate(seq):
        print(f"{i:>3}{pt:>8}{c:>8}{(100*c/pt if pt else 0):>7.0f}%{uc:>10}")
