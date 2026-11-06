#!/usr/bin/env python3
"""LOCAL-872C: apply the FINAL landmark_claim_gate (with Wikipedia authority) to a live
run's delivered text + its saved evidence, then score the ticket's PASS criteria.
usage: replay_check.py <meterlog_dir> <run_tag> <out_dir>"""
import json, os, re, sys, unicodedata
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import landmark_claim_gate as lg  # noqa: E402

fold = lambda x: "".join(c for c in unicodedata.normalize("NFD", x)
                         if not unicodedata.combining(c)).replace("đ", "d").replace("Đ", "d").lower()


def blocks(t):
    ts = re.findall(r"(?mi)^Stop\s+(\d+):\s*(.+)$", t)
    bs = re.split(r"(?mi)^Stop\s+\d+:\s*.+$", t)[1:]
    return [(x.strip(), b) for (_, x), b in zip(ts, bs)]


def prose(b):
    return " ".join(l for l in b.split("\n") if l.strip() and not re.match(
        r"(?i)^(Coordinates|Type/Specialty|Specific Examples|Directions|Address):", l.strip()))


def main(d, run, out_dir):
    p = lambda s: os.path.join(d, f"{run}_{s}")
    ev = {int(k): v for k, v in json.load(open(p("evidence.json"))).items()}
    ti = {int(k): v for k, v in json.load(open(p("titles.json"))).items()}
    kn = json.load(open(p("known.json")))
    auth = {k: [x for x in v if " - Wikipedia (" in x[:200]] for k, v in ev.items()}
    kw = dict(stop_evidence=ev, stop_titles=ti, skip_stops=kn["skip"],
              stop_known={int(k): v for k, v in kn["known"].items()}, location="Ho Chi Minh City, Vietnam")
    live = open(p("delivered.txt"), encoding="utf-8").read()
    # the stop's D759 grounded body, from the same fields the live run had (name, kind, examples)
    import user_stop_narration as usn
    fb = {k: usn.grounded_user_stop_body({"name": v[0], "address": v[1], "type_specialty": v[2],
                                          "specific_examples": v[3]}, kw["location"])
          for k, v in kw["stop_known"].items()}
    out, rep = lg.filter_tour_text(live, stop_authority=auth, stop_fallback=fb, **kw)
    out, filled = lg.fill_empty_stops(out, ti, auth, fb, kw["location"])   # the last pass
    _, rep2 = lg.filter_tour_text(out, **kw)
    open(os.path.join(out_dir, f"{run}_final_code_replay.txt"), "w", encoding="utf-8").write(out)
    B = blocks(out)
    g = lambda k: next(b for t, b in B if k in t.lower())
    op, ip, nd = fold(prose(g("opera"))), fold(prose(g("independence"))), prose(g("notre"))
    res = {
        "opera_architect_and_1900": any(n in op for n in ("olivier", "guichard", "ferret")) and "1900" in op,
        "independence_ngo_viet_thu_1960s_no_1885": "ngo viet thu" in ip and bool(re.search(r"196[2-6]", ip)) and "1885" not in ip,
        "notre_dame_1863_and_1880": "1863" in nd and "1880" in nd,
        "no_empty_body": all(lg._has_real_sentence(b) for _, b in B),
        "no_miss_saigon": "miss saigon" not in out.lower(),
        "recheck_drops_0": rep2["dropped"] == 0,
        "stops": len(B), "gate_drops_on_live_text": rep["dropped"],
        "filled_empty": filled,
        "added": [m.strip() for m in re.findall(r"[^.\n]*According to Wikipedia[^.\n]*\.", out)],
    }
    print(run, json.dumps(res, ensure_ascii=False, indent=1))
    return all(v for k, v in res.items() if k not in ("stops", "gate_drops_on_live_text", "added", "filled_empty"))


if __name__ == "__main__":
    sys.exit(0 if main(*sys.argv[1:4]) else 1)
