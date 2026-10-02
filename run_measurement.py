"""
LOCAL-446 — Run the measurement: LLM vs Wikimedia.

Loads ground truth fixture, probes each model, compares, and produces
the results table and verdict.

Three measurement axes:
  1. Speed (latency per call, LLM vs Wikimedia healthy)
  2. Accuracy per field (correct / wrong / abstained)
  3. Confident-and-wrong rate (the headline number)
"""

import json
import os
import sys
import time
import logging
import statistics
import unicodedata
from typing import Optional

from llm_wikimedia_probe import (
    probe_llm_for_entity,
    probe_llm_for_entity_strict,
    estimate_cost,
)
from harvest_ground_truth import fetch_wikipedia_summary_latency, FIXTURE_PATH

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

RESULTS_PATH = os.path.join(os.path.dirname(__file__), "measurement_results.json")
REPORT_PATH = os.path.join(os.path.dirname(__file__), "SUBMISSION_LOCAL-446.md")

MODELS = ["gpt-4o-mini", "gpt-4o"]
FIELDS_TO_COMPARE = ["qid", "label", "wikipedia_extract", "official_website", "instance_of", "country", "city"]


def _normalize(s: Optional[str]) -> Optional[str]:
    """Normalize a string for comparison: lowercase, accent-fold, strip."""
    if s is None:
        return None
    # NFD decomposition + strip combining marks (accent folding per D243)
    nfkd = unicodedata.normalize("NFKD", s)
    folded = "".join(c for c in nfkd if not unicodedata.combining(c))
    return folded.lower().strip()


def _extract_domain(url: Optional[str]) -> Optional[str]:
    """Extract registrable domain from a URL for comparison."""
    if not url:
        return None
    url = url.lower().strip().rstrip("/")
    for prefix in ["https://www.", "http://www.", "https://", "http://"]:
        if url.startswith(prefix):
            url = url[len(prefix):]
            break
    # Strip leading www. even without protocol
    if url.startswith("www."):
        url = url[4:]
    # Take just the domain part
    return url.split("/")[0].split("?")[0]


def _compare_field(field: str, ground_truth_value, llm_value) -> str:
    """Compare a single field. Returns 'correct', 'wrong', or 'abstained'."""
    # LLM abstained
    if llm_value is None or (isinstance(llm_value, str) and llm_value.strip() == ""):
        return "abstained"

    # Ground truth is None — we can't judge, treat as abstained-correct
    # (if we don't have GT, we can't say the LLM is wrong)
    if ground_truth_value is None:
        return "abstained"  # Can't verify → not counted

    # Special handling per field type
    if field == "qid":
        # Exact match required for QIDs
        return "correct" if str(llm_value).upper() == str(ground_truth_value).upper() else "wrong"

    elif field == "official_website":
        # Compare domains
        gt_domain = _extract_domain(str(ground_truth_value))
        llm_domain = _extract_domain(str(llm_value))
        if gt_domain and llm_domain:
            return "correct" if gt_domain == llm_domain else "wrong"
        return "abstained"

    elif field == "wikipedia_extract":
        # For extracts: check if the LLM's version substantially overlaps
        # We use a simple heuristic: the first 50 chars of GT should appear in LLM
        # (normalized), OR vice versa. This is generous — we're testing recall, not
        # verbatim reproduction.
        gt_norm = _normalize(ground_truth_value)
        llm_norm = _normalize(str(llm_value))
        if not gt_norm or not llm_norm:
            return "abstained"
        # Check first-sentence overlap (first 100 chars)
        gt_start = gt_norm[:100]
        # If >40% of GT start words appear in LLM, call it correct
        gt_words = set(gt_start.split())
        llm_words = set(llm_norm[:500].split())
        if not gt_words:
            return "abstained"
        overlap = len(gt_words & llm_words) / len(gt_words)
        return "correct" if overlap > 0.4 else "wrong"

    else:
        # Generic comparison: normalized substring match
        gt_norm = _normalize(str(ground_truth_value))
        llm_norm = _normalize(str(llm_value))
        if not gt_norm or not llm_norm:
            return "abstained"
        # Either one contains the other
        if gt_norm in llm_norm or llm_norm in gt_norm:
            return "correct"
        # Word overlap check
        gt_words = set(gt_norm.split())
        llm_words = set(llm_norm.split())
        if gt_words and len(gt_words & llm_words) / len(gt_words) > 0.5:
            return "correct"
        return "wrong"


def _is_confident(result: dict) -> bool:
    """Check if the model expressed high confidence (didn't hedge)."""
    resp = result.get("response", {})
    if not resp:
        return False
    confidence = resp.get("confidence", "").lower()
    return confidence in ("high", "medium")


def run_measurement():
    """Run the full measurement suite."""
    # Load ground truth
    if not os.path.exists(FIXTURE_PATH):
        print(f"ERROR: Ground truth fixture not found at {FIXTURE_PATH}")
        print("Run harvest_ground_truth.py first.")
        sys.exit(1)

    with open(FIXTURE_PATH, "r") as f:
        ground_truth = json.load(f)

    print(f"Loaded {len(ground_truth)} ground truth entities.")
    print(f"Models to test: {MODELS}")
    print()

    all_results = {}

    for model in MODELS:
        print(f"\n{'='*60}")
        print(f"TESTING MODEL: {model}")
        print(f"{'='*60}\n")

        model_results = []
        for i, gt_entity in enumerate(ground_truth):
            entity_name = gt_entity["entity_name"]
            print(f"  [{i+1}/{len(ground_truth)}] {entity_name}...", end=" ", flush=True)

            # Normal probe
            result = probe_llm_for_entity(entity_name, model=model)
            result["ground_truth"] = gt_entity

            # Compare each field
            comparisons = {}
            if result["response"]:
                for field in FIELDS_TO_COMPARE:
                    gt_val = gt_entity.get(field)
                    llm_val = result["response"].get(field)
                    comparisons[field] = _compare_field(field, gt_val, llm_val)
            result["comparisons"] = comparisons
            result["cost_usd"] = estimate_cost(result)

            # Check confident-and-wrong
            confident_wrong = []
            if result["response"] and _is_confident(result):
                for field, verdict in comparisons.items():
                    if verdict == "wrong":
                        confident_wrong.append({
                            "field": field,
                            "ground_truth": gt_entity.get(field),
                            "llm_said": result["response"].get(field),
                        })
            result["confident_wrong"] = confident_wrong

            model_results.append(result)
            status = "✓" if not result["error"] else "✗"
            print(f"{status} ({result['latency_ms']:.0f}ms, ${result['cost_usd']:.5f})")

            # Small delay between API calls
            time.sleep(0.5)

        all_results[model] = model_results

        # Also run strict mode on a subset (first 20)
        print(f"\n  Running strict mode on first 20 entities...")
        strict_results = []
        for i, gt_entity in enumerate(ground_truth[:20]):
            entity_name = gt_entity["entity_name"]
            result = probe_llm_for_entity_strict(entity_name, model=model)
            result["ground_truth"] = gt_entity
            if result["response"]:
                comparisons = {}
                for field in FIELDS_TO_COMPARE:
                    gt_val = gt_entity.get(field)
                    llm_val = result["response"].get(field)
                    comparisons[field] = _compare_field(field, gt_val, llm_val)
                result["comparisons"] = comparisons
            strict_results.append(result)
            time.sleep(0.5)

        all_results[f"{model}_strict"] = strict_results

    # Measure Wikimedia latency for comparison
    print(f"\n{'='*60}")
    print("MEASURING WIKIMEDIA HEALTHY LATENCY")
    print(f"{'='*60}\n")

    wiki_latencies = []
    for i, gt_entity in enumerate(ground_truth):
        entity_name = gt_entity["entity_name"]
        lat = fetch_wikipedia_summary_latency(entity_name)
        wiki_latencies.append(lat)
        print(f"  [{i+1}/{len(ground_truth)}] {entity_name}: {lat['latency_ms']:.0f}ms ({'ok' if lat['success'] else 'fail'})")
        time.sleep(1.0)  # Rate limit

    all_results["wikimedia_latency"] = wiki_latencies

    # Save raw results
    _save_results(all_results)

    # Generate report
    _generate_report(all_results, ground_truth)

    print(f"\nResults saved to: {RESULTS_PATH}")
    print(f"Report saved to: {REPORT_PATH}")


def _save_results(data: dict):
    """Save results (without large extracts to keep file manageable)."""
    # Strip wikipedia_extract from ground_truth in results to keep file small
    save_data = {}
    for key, val in data.items():
        if isinstance(val, list):
            cleaned = []
            for item in val:
                if isinstance(item, dict):
                    item_copy = dict(item)
                    # Truncate long fields
                    if "raw_text" in item_copy and item_copy["raw_text"]:
                        item_copy["raw_text"] = item_copy["raw_text"][:500]
                    gt = item_copy.get("ground_truth")
                    if gt and "wikipedia_extract" in gt:
                        gt_copy = dict(gt)
                        if gt_copy["wikipedia_extract"]:
                            gt_copy["wikipedia_extract"] = gt_copy["wikipedia_extract"][:200] + "..."
                        item_copy["ground_truth"] = gt_copy
                    cleaned.append(item_copy)
                else:
                    cleaned.append(item)
            save_data[key] = cleaned
        else:
            save_data[key] = val

    with open(RESULTS_PATH, "w") as f:
        json.dump(save_data, f, indent=2, ensure_ascii=False)


def _generate_report(all_results: dict, ground_truth: list):
    """Generate the markdown submission report."""
    lines = []
    lines.append("# LOCAL-446: LLM as Wikimedia Substitute — Measurement Report")
    lines.append("")
    lines.append(f"**Date:** {time.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Entities tested:** {len(ground_truth)}")
    lines.append(f"**Models tested:** {', '.join(MODELS)}")
    lines.append("")

    # Ground truth summary
    gt_with_qid = sum(1 for g in ground_truth if g.get("qid"))
    gt_with_wiki = sum(1 for g in ground_truth if g.get("wikipedia_extract"))
    gt_with_p856 = sum(1 for g in ground_truth if g.get("official_website"))
    lines.append("## Ground Truth Coverage")
    lines.append("")
    lines.append(f"- Entities with Wikidata QID: {gt_with_qid}/40")
    lines.append(f"- Entities with Wikipedia extract: {gt_with_wiki}/40")
    lines.append(f"- Entities with P856 website: {gt_with_p856}/40")
    lines.append("")

    # Per-model results
    for model in MODELS:
        results = all_results.get(model, [])
        if not results:
            continue

        lines.append(f"## Model: {model}")
        lines.append("")

        # Latency
        latencies = [r["latency_ms"] for r in results if r["latency_ms"]]
        if latencies:
            lines.append("### Speed")
            lines.append("")
            lines.append(f"- Median latency: **{statistics.median(latencies):.0f}ms**")
            lines.append(f"- P90 latency: **{sorted(latencies)[int(len(latencies)*0.9)]:.0f}ms**")
            lines.append(f"- Min/Max: {min(latencies):.0f}ms / {max(latencies):.0f}ms")
            lines.append("")

        # Accuracy per field
        lines.append("### Accuracy (per field)")
        lines.append("")
        lines.append("| Field | Correct | Wrong | Abstained | Accuracy (excl. abstain) |")
        lines.append("|-------|---------|-------|-----------|--------------------------|")

        total_confident_wrong = []
        for field in FIELDS_TO_COMPARE:
            correct = sum(1 for r in results if r.get("comparisons", {}).get(field) == "correct")
            wrong = sum(1 for r in results if r.get("comparisons", {}).get(field) == "wrong")
            abstained = sum(1 for r in results if r.get("comparisons", {}).get(field) == "abstained")
            answered = correct + wrong
            acc = f"{correct/answered*100:.0f}%" if answered > 0 else "N/A"
            lines.append(f"| {field} | {correct} | {wrong} | {abstained} | {acc} |")

        lines.append("")

        # Confident-and-wrong
        all_cw = []
        for r in results:
            for cw in r.get("confident_wrong", []):
                all_cw.append({
                    "entity": r["entity_name"],
                    "field": cw["field"],
                    "ground_truth": cw["ground_truth"],
                    "llm_said": cw["llm_said"],
                })
        total_confident_wrong = all_cw

        lines.append("### Confident-and-Wrong (HEADLINE NUMBER)")
        lines.append("")
        lines.append(f"**Total confident-and-wrong answers: {len(all_cw)}**")
        lines.append("")

        if all_cw:
            lines.append("Verbatim examples (up to 5):")
            lines.append("")
            for ex in all_cw[:5]:
                lines.append(f"- **{ex['entity']}** → field `{ex['field']}`")
                lines.append(f"  - Ground truth: `{ex['ground_truth']}`")
                lines.append(f"  - LLM said: `{ex['llm_said']}`")
                lines.append("")
        else:
            lines.append("*No confident-and-wrong answers found. This is a strong and surprising result.*")
            lines.append("")

        # Cost
        costs = [r.get("cost_usd", 0) for r in results]
        total_cost = sum(costs)
        avg_cost = total_cost / len(costs) if costs else 0
        lines.append("### Cost")
        lines.append("")
        lines.append(f"- Average cost per call: **${avg_cost:.5f}**")
        lines.append(f"- Total measurement cost: ${total_cost:.4f}")
        lines.append("")

        # Strict mode delta
        strict_key = f"{model}_strict"
        strict_results = all_results.get(strict_key, [])
        if strict_results:
            lines.append("### Strict Mode Delta (first 20 entities)")
            lines.append("")
            # Count abstentions in strict vs normal
            normal_subset = results[:20]
            normal_abstain = sum(
                1 for r in normal_subset
                for f in FIELDS_TO_COMPARE
                if r.get("comparisons", {}).get(f) == "abstained"
            )
            strict_abstain = sum(
                1 for r in strict_results
                for f in FIELDS_TO_COMPARE
                if r.get("comparisons", {}).get(f) == "abstained"
            )
            lines.append(f"- Normal mode abstentions: {normal_abstain}/{20*len(FIELDS_TO_COMPARE)}")
            lines.append(f"- Strict mode abstentions: {strict_abstain}/{20*len(FIELDS_TO_COMPARE)}")
            lines.append(f"- Delta: +{strict_abstain - normal_abstain} abstentions in strict mode")
            lines.append("")

    # Wikimedia latency comparison
    wiki_lats = all_results.get("wikimedia_latency", [])
    if wiki_lats:
        successful = [w["latency_ms"] for w in wiki_lats if w.get("success")]
        lines.append("## Wikimedia Healthy Latency (Baseline)")
        lines.append("")
        if successful:
            lines.append(f"- Median: **{statistics.median(successful):.0f}ms**")
            lines.append(f"- P90: **{sorted(successful)[int(len(successful)*0.9)]:.0f}ms**")
            lines.append(f"- Min/Max: {min(successful):.0f}ms / {max(successful):.0f}ms")
            lines.append(f"- Success rate: {len(successful)}/{len(wiki_lats)}")
        else:
            lines.append("- All Wikimedia calls failed (possibly rate-limited)")
        lines.append("")

    # Verdict
    lines.append("## Verdict")
    lines.append("")
    lines.append("### 1. Is it faster than healthy Wikimedia?")
    lines.append("")

    # Compare latencies
    for model in MODELS:
        results = all_results.get(model, [])
        llm_lats = [r["latency_ms"] for r in results if r.get("latency_ms")]
        wiki_successful = [w["latency_ms"] for w in wiki_lats if w.get("success")]
        if llm_lats and wiki_successful:
            llm_med = statistics.median(llm_lats)
            wiki_med = statistics.median(wiki_successful)
            faster = "YES" if llm_med < wiki_med else "NO"
            lines.append(f"- **{model}**: {faster} (LLM {llm_med:.0f}ms vs Wiki {wiki_med:.0f}ms)")

    lines.append("")
    lines.append("### 2. Is it accurate enough on the long tail to substitute?")
    lines.append("")

    for model in MODELS:
        results = all_results.get(model, [])
        # Look at long-tail entities specifically (indices 15-29)
        long_tail = results[15:30] if len(results) >= 30 else results
        lt_wrong = sum(
            1 for r in long_tail
            for f in FIELDS_TO_COMPARE
            if r.get("comparisons", {}).get(f) == "wrong"
        )
        lt_total = sum(
            1 for r in long_tail
            for f in FIELDS_TO_COMPARE
            if r.get("comparisons", {}).get(f) in ("correct", "wrong")
        )
        if lt_total > 0:
            error_rate = lt_wrong / lt_total * 100
            lines.append(f"- **{model}** long-tail error rate: {error_rate:.1f}% ({lt_wrong}/{lt_total} answered fields wrong)")
        else:
            lines.append(f"- **{model}**: insufficient data to judge long tail")

    lines.append("")
    lines.append("### 3. Under what guard, if any, would it be safe?")
    lines.append("")

    # Assess based on confident-wrong count
    for model in MODELS:
        results = all_results.get(model, [])
        cw_count = sum(len(r.get("confident_wrong", [])) for r in results)
        total_answered = sum(
            1 for r in results
            for f in FIELDS_TO_COMPARE
            if r.get("comparisons", {}).get(f) in ("correct", "wrong")
        )
        if total_answered > 0:
            cw_rate = cw_count / total_answered * 100
            if cw_rate < 2:
                lines.append(f"- **{model}**: Confident-wrong rate {cw_rate:.1f}% — potentially usable at web_search tier with corroboration requirement (D373).")
            elif cw_rate < 10:
                lines.append(f"- **{model}**: Confident-wrong rate {cw_rate:.1f}% — marginal. Would require strict corroboration for every field.")
            else:
                lines.append(f"- **{model}**: Confident-wrong rate {cw_rate:.1f}% — **UNUSABLE as a substitute.** The model asserts falsehoods too frequently.")

    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    lines.append("- 40 entities is enough to reject a bad option, not enough to certify a good one.")
    lines.append("- The measurement reflects model behavior as of today; model updates may change results.")
    lines.append("- Wikipedia extract comparison uses word-overlap heuristic, not semantic similarity.")
    lines.append("- Cost estimates use published per-token pricing; actual billed amounts may differ slightly.")
    lines.append("")

    report_text = "\n".join(lines)
    with open(REPORT_PATH, "w") as f:
        f.write(report_text)

    return report_text


if __name__ == "__main__":
    run_measurement()
