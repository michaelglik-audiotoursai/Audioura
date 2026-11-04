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


def truth_report(tour_path, rep_path):
    """Offline truth checks on a delivered tour: sentences per stop, every layer-3
    sentence with its marker, and any year / 'first' in the prose that no gathered
    fact for that stop contains."""
    import user_stop_context as usc
    text = open(tour_path, encoding="utf-8").read()
    rep = json.load(open(rep_path))
    facts_by = {s["stop"]: s.get("facts", []) for s in rep.get("stops", [])}
    blocks = re.split(r"(?mi)^Stop\s+\d+:\s*", text)[1:]
    ok = True
    print("\n== TRUTH CHECKS ==")
    for blk in blocks:
        title = blk.split("\n", 1)[0].strip()
        prose = []
        for ln in blk.split("\n")[1:]:
            t = ln.strip()
            if not t or re.match(r"(?i)^(Coordinates|Type/Specialty|Directions|Address|Specific Examples):", t):
                continue
            if re.match(r"(?i)^(across these stops|if you would like to eat)", t):
                break
            prose.append(re.sub(r"(?i)^Orientation:\s*", "", t))
        sents = usc._split_sentences(" ".join(prose))
        corpus = " ".join(f[2] for f in facts_by.get(title, [])) + " " + title
        bad = []
        for sn in sents:
            for y in re.findall(r"\b(1[0-9]{3}|20[0-2][0-9])\b", sn):
                if y not in corpus:
                    bad.append(f"year {y} in: {sn[:90]}")
            if re.search(r"(?i)\b(first[- ]ever|the first|oldest|pioneer)", sn) and not re.search(
                    r"(?i)\b(first[- ]ever|the first|oldest|pioneer)", corpus):
                bad.append(f"'first' claim in: {sn[:90]}")
        l3 = [(sn, usc.DISCLOSURE_RE.search(sn)) for sn in sents
              if usc.has_disclosure(sn) or re.search(
                  r"(?i)\b(legends?|myths?|folk\s*tales?|fables?|fairy|folklore|once\s+upon)\b", sn)]
        print(f"- {title}: {len(sents)} sentence(s); layer-3 sentences: {len(l3)}; "
              f"invented-specific hits: {len(bad)}")
        if len(sents) < 4:
            ok = False
            print("    FAIL: under 4 sentences")
        for sn, m in l3:
            mark = m.group(0) if m else None
            flag = "" if (mark or usc.is_name_meaning_sentence(sn, title)) else "   <-- NO MARKER"
            if flag:
                ok = False
            print(f"    L3 marker={mark!r}: {sn}{flag}")
        for b in bad:
            ok = False
            print("    INVENTED:", b)
    print("TRUTH CHECKS:", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    main(*sys.argv[1:4])
    if len(sys.argv) > 3:
        truth_report(sys.argv[2], sys.argv[3])
