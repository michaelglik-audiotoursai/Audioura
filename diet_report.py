#!/usr/bin/env python3
"""diet_report.py — LOCAL-647 prompt-diet experiment report.

Compares the FULL production-shape prompt against a TRIMMED (diet) variant on
arm A (gpt-4.1) and arm B (gpt-4.1-mini, the best cheap arm within 0.3 of A),
and reports the OpenAI automatic-prompt-caching result (fixed-instructions-first).

Metrics per (arm, variant):
  * mean prompt tokens (from the API usage) — full vs diet
  * mean Kiro score — score delta vs full
  * mean $/stop priced with the network meter's own rate table (cost_rates /
    paid_api_meter) from prompt+completion tokens, so the $ delta is apples-to-apples
  * cached_tokens from the fixed-first run (prompt caching) and the $ it saves

The authoritative TOTAL spend is still the paid_api_calls ledger (reported
separately); this per-variant pricing just lets us isolate the diet's input-token
saving, which the ledger cannot (all variants used the same model string).

usage: python3 diet_report.py --dir bench_out
"""
import json
import os
import statistics
import sys

# meter rate table (USD per 1M tokens): (input, output, cached_input)
RATES = {
    "A": (2.00, 8.00, 0.50),   # gpt-4.1
    "B": (0.40, 1.60, 0.10),   # gpt-4.1-mini
}


def price(arm, prompt_tok, completion_tok, cached_tok=0):
    i, o, c = RATES[arm]
    return ((prompt_tok - cached_tok) * i + cached_tok * c + completion_tok * o) / 1e6


def load(path):
    return json.load(open(path, encoding="utf-8"))


def mean_scores(kiro_path, arm):
    if not os.path.exists(kiro_path):
        return None
    d = load(kiro_path)
    sc = [s["score"] for s in d.get(arm, []) if s.get("score") is not None]
    return round(statistics.mean(sc), 3) if sc else None


def variant_stats(base_dir, variant, arm):
    """variant in {'', 'diet', 'fixedfirst'} -> subdir."""
    sub = base_dir if variant == "full" else os.path.join(base_dir, variant)
    recs = load(os.path.join(sub, arm, f"arm_{arm}_results.json"))
    pts = [r["usage"].get("prompt_tokens", 0) for r in recs]
    cts = [r["usage"].get("completion_tokens", 0) for r in recs]
    cds = [(r["usage"].get("prompt_tokens_details") or {}).get("cached_tokens", 0)
           for r in recs]
    per_stop_usd = [price(arm, p, c, cd) for p, c, cd in zip(pts, cts, cds)]
    kiro_path = os.path.join(sub, "kiro_scores.json")
    return {
        "mean_prompt_tok": round(statistics.mean(pts)),
        "mean_completion_tok": round(statistics.mean(cts)),
        "mean_cached_tok": round(statistics.mean(cds)),
        "mean_usd_per_stop": round(statistics.mean(per_stop_usd), 6),
        "mean_score": mean_scores(kiro_path, arm),
        "n": len(recs),
    }


def build(base_dir):
    report = {}
    md = []
    md.append("### Prompt-diet experiment (arm A gpt-4.1, arm B gpt-4.1-mini)\n")
    md.append("| Arm | Variant | Mean prompt tok | Mean cached tok | Mean out tok | Mean score | $/stop |")
    md.append("|-----|---------|-----------------|-----------------|--------------|-----------|--------|")
    for arm in ["A", "B"]:
        report[arm] = {}
        for variant in ["full", "diet", "fixedfirst"]:
            try:
                st = variant_stats(base_dir, variant, arm)
            except FileNotFoundError:
                continue
            report[arm][variant] = st
            md.append(f"| {arm} | {variant} | {st['mean_prompt_tok']} | "
                      f"{st['mean_cached_tok']} | {st['mean_completion_tok']} | "
                      f"{st['mean_score']} | ${st['mean_usd_per_stop']:.6f} |")
    # deltas
    md.append("")
    md.append("**Deltas (diet vs full):**")
    for arm in ["A", "B"]:
        f = report[arm].get("full")
        d = report[arm].get("diet")
        if f and d:
            tok_cut = f["mean_prompt_tok"] - d["mean_prompt_tok"]
            tok_pct = 100 * tok_cut / f["mean_prompt_tok"]
            usd_delta = d["mean_usd_per_stop"] - f["mean_usd_per_stop"]
            score_delta = ((d["mean_score"] - f["mean_score"])
                           if (d["mean_score"] and f["mean_score"]) else None)
            md.append(f"- Arm {arm}: prompt tokens {f['mean_prompt_tok']}→"
                      f"{d['mean_prompt_tok']} (−{tok_cut}, −{tok_pct:.1f}%); "
                      f"score {f['mean_score']}→{d['mean_score']} "
                      f"(Δ{score_delta:+.3f}); $/stop ${f['mean_usd_per_stop']:.6f}→"
                      f"${d['mean_usd_per_stop']:.6f} (Δ${usd_delta:+.6f})")
    md.append("")
    md.append("**OpenAI automatic prompt caching (fixed-instructions-first):**")
    for arm in ["A", "B"]:
        ff = report[arm].get("fixedfirst")
        full = report[arm].get("full")
        if ff:
            pct = 100 * ff["mean_cached_tok"] / max(ff["mean_prompt_tok"], 1)
            # saving vs same prompt with no caching
            i, o, c = RATES[arm]
            saved = ff["mean_cached_tok"] * (i - c) / 1e6
            md.append(f"- Arm {arm}: mean cached_tokens={ff['mean_cached_tok']} of "
                      f"{ff['mean_prompt_tok']} prompt tok ({pct:.0f}% cached); "
                      f"caching saves ≈${saved:.6f}/stop on input "
                      f"(cached billed at ${c}/1M vs ${i}/1M).")
    table = "\n".join(md)
    print(table)
    with open(os.path.join(base_dir, "diet_report.md"), "w", encoding="utf-8") as f:
        f.write(table + "\n")
    with open(os.path.join(base_dir, "diet_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report


def _main():
    args = sys.argv[1:]
    base = args[args.index("--dir") + 1] if "--dir" in args else "bench_out"
    build(base)


if __name__ == "__main__":
    _main()
