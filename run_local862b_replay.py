#!/usr/bin/env python3
"""run_local862_replay.py — LOCAL-862 cheap iteration harness.

Replays ONLY the enrichment + verification stage (no tour generation) on a saved
tour text, with the same budget contract (TASK_BUDGET_ID=LOCAL-862) and its OWN
meter dir. Used to tune the material filters without re-paying for generation.

  python3 run_local862_replay.py <tour.txt> <out.txt> [report.json]
"""
import json, os, sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "_meter"))
for line in open(os.path.join(_HERE, ".env"), errors="ignore"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
os.environ["TASK_BUDGET_ID"] = "LOCAL-862B"
os.environ.setdefault("TASK_BUDGET_USD", "0.50")
os.environ.setdefault("SERP_PROVIDER", "serper")
_M = os.path.join(_HERE, "_local862b_meterlogs")
os.makedirs(_M, exist_ok=True)
os.environ["PAID_API_LOG"] = os.path.join(_M, "paid_api_calls.jsonl")
os.environ["METER_MOUNT_GUARD"] = "0"
os.environ["METER_SERVICE"] = "LOCAL-862B"
os.environ.setdefault("AUDIOURA_TASK_BUDGET_DIR", _M)

import re
import user_stop_enrichment as use
import user_stop_verify as usv


def main(src, dst, rep_path=None):
    text = open(src, encoding="utf-8").read()
    titles = [t.strip() for t in re.findall(r"(?mi)^Stop\s+\d+:\s*(.+)$", text)]
    loc = "Ho Chi Minh City, Vietnam"
    import user_stop_input as usi
    from run_local862b_live import USER_STOP_INPUTS
    aliases = {}
    for raw in USER_STOP_INPUTS:
        p = usi.parse_user_stop(raw, resolve=lambda u: None)
        if p.get("resolved_name"):
            aliases[p["name"]] = p["resolved_name"]
    new, rep = use.enrich_user_stops_in_text(text, titles, loc, log=print,
                                             aliases_by_title=aliases)
    new, vrep = usv.verify_user_stops_in_text(
        new, titles, loc, log=print,
        material_by_title=rep["material_by_title"],
        precomposed_titles=rep["precomposed"])
    rep["verify"] = {k: vrep.get(k) for k in
                     ("ran", "dropped_total", "cost_usd", "stops", "serper_queries")}
    open(dst, "w", encoding="utf-8").write(new)
    if rep_path:
        json.dump(rep, open(rep_path, "w"), indent=2, ensure_ascii=False, default=str)
    print(f"enrich ${rep['total_cost_usd']:.4f} + verify ${vrep.get('cost_usd',0):.5f}"
          f" dropped={vrep.get('dropped_total')}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
