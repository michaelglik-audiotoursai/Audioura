#!/usr/bin/env python3
"""report.py — LOCAL-647 bake-off report table.

Aggregates, per arm: mean score, min score, failures, $ per stop (from the
paid_api_calls ledger — the network meter, not an estimate), median seconds per
stop, and mean output tokens. Marks which arms are within 0.3 of arm A's mean.

$ per stop comes from the ledger: we read paid_api_calls for host=local647-gen,
status=200, grouped by model, and divide by the number of bake-off stops for
that arm (12). Latency and output tokens come from arm_X_results.json (the
harness recorded wall-time and usage per draft).

usage: python3 report.py --dir bench_out [--host local647-gen]
       (DB queried via docker exec on development-postgres-2-1)
"""
import json
import os
import statistics
import subprocess
import sys

ARMS = ["A", "B", "C", "D", "E"]
ARM_LABEL = {
    "A": ("gpt-4.1", "gpt-4.1 (today)"),
    "B": ("gpt-4.1-mini", "gpt-4.1-mini"),
    "C": ("gpt-4.1-nano", "gpt-4.1-nano"),
    "D": ("gemini-flash-lite-latest", "Gemini 2.5 Flash-Lite"),
    "E": ("gemini-flash-latest", "Gemini 2.5 Flash"),
}


def ledger_by_model(host):
    """Return {model_substring_match: (calls, usd)} from paid_api_calls."""
    sql = ("select model, count(*), coalesce(sum(usd),0) from paid_api_calls "
           f"where host='{host}' and status=200 group by model")
    out = subprocess.run(
        ["docker", "exec", "development-postgres-2-1", "psql", "-U", "admin",
         "-d", "audiotours", "-Atc", sql], capture_output=True, text=True).stdout
    rows = {}
    for line in out.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|")
        model, calls, usd = parts[0], int(parts[1]), float(parts[2])
        rows[model] = (calls, usd)
    return rows


def _model_matches(arm_key, ledger_model):
    """Exact-family match: 'gpt-4.1' must NOT match 'gpt-4.1-mini'/'-nano'.

    The ledger stores dated ids like 'gpt-4.1-2025-04-14' and
    'gpt-4.1-mini-2025-04-14'. We require the ledger model to start with the arm
    key and the next character (if any) to be a date digit boundary ('-' followed
    by a 4-digit year) rather than a longer family suffix like '-mini'.
    """
    import re as _re
    if not ledger_model.startswith(arm_key):
        return False
    rest = ledger_model[len(arm_key):]
    if rest == "":
        return True
    # OpenAI dated suffix: '-2025-04-14'; a family suffix would be '-mini'/'-nano'
    if _re.match(r"^-\d{4}", rest):
        return True
    # Gemini aliases have no dated suffix; arm_key already equals the full alias
    return False


def arm_ledger_cost(arm, ledger, n_stops):
    """$ per stop for an arm, from the ledger, matching the arm's model."""
    model_key = ARM_LABEL[arm][0]
    total_usd = 0.0
    total_calls = 0
    for model, (calls, usd) in ledger.items():
        if _model_matches(model_key, model):
            total_usd += usd
            total_calls += calls
    # per-stop cost = ledger per-CALL average (one narration call per stop).
    # Using per-call avoids skew from the extra nano smoke call in the ledger.
    per_stop = (total_usd / total_calls) if total_calls else 0.0
    return total_usd, total_calls, per_stop


def build(base_dir, host):
    kiro = json.load(open(os.path.join(base_dir, "kiro_scores.json"), encoding="utf-8"))
    detectors = json.load(open(os.path.join(base_dir, "detectors.json"), encoding="utf-8"))
    ledger = ledger_by_model(host)

    rows = []
    arm_a_mean = None
    for arm in ARMS:
        recs = json.load(open(os.path.join(base_dir, arm, f"arm_{arm}_results.json"),
                              encoding="utf-8"))
        scores = [s["score"] for s in kiro.get(arm, []) if s.get("score") is not None]
        n_stops = len(recs)
        mean_score = round(statistics.mean(scores), 2) if scores else None
        min_score = min(scores) if scores else None
        det_fails = sum(d["n_failures"] for d in detectors.get(arm, []))
        http_fails = sum(1 for r in recs if r["status"] != 200)
        secs = [r["seconds"] for r in recs]
        med_secs = round(statistics.median(secs), 2) if secs else None
        out_tokens = [r["usage"].get("completion_tokens", 0) for r in recs
                      if isinstance(r.get("usage"), dict)]
        mean_out_tok = round(statistics.mean(out_tokens)) if out_tokens else None
        total_usd, calls, per_stop = arm_ledger_cost(arm, ledger, n_stops)
        usd_total_12 = round(per_stop * n_stops, 5)  # clean 12-stop total (smoke-free)
        if arm == "A":
            arm_a_mean = mean_score
        rows.append({
            "arm": arm, "model": ARM_LABEL[arm][1],
            "mean_score": mean_score, "min_score": min_score,
            "detector_failures": det_fails, "http_failures": http_fails,
            "usd_total": usd_total_12, "usd_ledger_raw": round(total_usd, 5),
            "ledger_calls": calls,
            "usd_per_stop": round(per_stop, 5),
            "median_seconds": med_secs, "mean_output_tokens": mean_out_tok,
            "n_stops": n_stops,
        })

    for r in rows:
        if arm_a_mean is not None and r["mean_score"] is not None:
            r["within_0_3_of_A"] = abs(r["mean_score"] - arm_a_mean) <= 0.3
        else:
            r["within_0_3_of_A"] = None

    report = {"host": host, "arm_a_mean": arm_a_mean, "rows": rows}
    with open(os.path.join(base_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # markdown table
    md = []
    md.append("| Arm | Model | Mean | Min | Det.fails | HTTP fails | $/stop | $ total | Median s | Mean out-tok | Within 0.3 of A |")
    md.append("|-----|-------|------|-----|-----------|-----------|--------|---------|----------|--------------|-----------------|")
    for r in rows:
        md.append(
            f"| {r['arm']} | {r['model']} | {r['mean_score']} | {r['min_score']} | "
            f"{r['detector_failures']} | {r['http_failures']} | ${r['usd_per_stop']:.5f} | "
            f"${r['usd_total']:.5f} | {r['median_seconds']} | {r['mean_output_tokens']} | "
            f"{'yes' if r['within_0_3_of_A'] else 'no'} |")
    table = "\n".join(md)
    print(table)
    with open(os.path.join(base_dir, "report_table.md"), "w", encoding="utf-8") as f:
        f.write(table + "\n")
    # within-0.3 summary
    within = [r["arm"] for r in rows if r["within_0_3_of_A"] and r["arm"] != "A"]
    print(f"\nArms within 0.3 of arm A ({arm_a_mean}): {within or 'none'}")
    return report


def _main():
    args = sys.argv[1:]

    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args else default

    base = opt("--dir", "bench_out")
    host = opt("--host", "local647-gen")
    build(base, host)


if __name__ == "__main__":
    _main()
