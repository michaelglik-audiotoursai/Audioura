"""
LOCAL-562 live acceptance — generate one Chart House tour and prove the ledger
row equals the wire total.

Installs the LOCAL-560 OpenAI recorder (independent instrument), generates a
4-stop Chart House restaurant tour through the production path (which now routes
every OpenAI call through the choke point into the per-tour accumulator), then
compares:

  * ledger LLM  = generate_tour_text._LAST_GENERATION_COST['breakdown']['llm']
                  (populated from the accumulator by the LOCAL-562 reconcile)
  * wire LLM    = sum over every recorded call of usage x cost_rates rate

They must match within $0.0005.

Also prints the recorded call count, per-model split, grounding cost, and a note
on Polly TTS (metered separately by polly_tts_service.py as its own tts_generate
ledger row; the text-generation record's tts stays 0 by design).

Run:
    OPENAI_API_KEY=... python3 run_local562_live_chart_house.py
"""

import io
import json
import os
import sys
import time
import contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tests", "fixtures", "local560"))

from cost_rates import llm_cost

REC_PATH = os.path.join(HERE, "local562_live_chart_house.jsonl")


def _wire_cost(records):
    total = 0.0
    by_model = {}
    for r in records:
        u = r.get("usage") or {}
        c = llm_cost(
            input_tokens=u.get("prompt_tokens") or 0,
            output_tokens=u.get("completion_tokens") or 0,
            model=r.get("model"),
        )
        total += c
        m = r.get("model")
        by_model[m] = by_model.get(m, 0) + 1
    return total, by_model


def main():
    if not os.environ.get("OPENAI_API_KEY"):
        print("SKIP: OPENAI_API_KEY not set — live run requires a real key.")
        return 2

    if os.path.exists(REC_PATH):
        os.remove(REC_PATH)

    import openai_recorder
    rec = openai_recorder.install(REC_PATH)

    import generate_tour_text as gtt

    buf = io.StringIO()
    t0 = time.time()
    err = None
    text = None
    try:
        with contextlib.redirect_stdout(buf):
            text, _out, _coords = gtt.generate_tour_text(
                "restaurant tour of Chart House, Boston, MA",
                "restaurant",
                None,
                4,
                job_id="local562-live-chart-house",
            )
    except Exception as e:
        import traceback
        err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    wall = time.time() - t0
    rec.uninstall()

    log_text = buf.getvalue()
    with open(os.path.join(HERE, "local562_live_chart_house.log"), "w", encoding="utf-8") as fh:
        fh.write(log_text)

    if err:
        print("GENERATION ERROR:\n", err)
        print("\n(tail of generation log)\n", log_text[-2000:])
        return 1

    # Load the recording the recorder captured on the wire.
    records = []
    with open(REC_PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    wire, by_model = _wire_cost(records)
    cost = dict(getattr(gtt, "_LAST_GENERATION_COST", {}) or {})
    ledger_llm = (cost.get("breakdown") or {}).get("llm", 0.0)
    grounding = cost.get("grounding_cost", (cost.get("breakdown") or {}).get("grounding", 0.0))

    diff = abs(ledger_llm - wire)

    print("=" * 68)
    print("LOCAL-562 LIVE — Chart House, Boston, restaurant, 4 stops")
    print("=" * 68)
    print(f"wall: {wall:.0f}s   chars: {len(text) if text else 0}")
    print(f"OpenAI calls recorded on wire : {len(records)}")
    print(f"models on wire                : {by_model}")
    print(f"accumulator calls attributed  : {(cost.get('cost_accumulator') or {}).get('llm', {}).get('calls')}")
    print("-" * 68)
    print(f"LEDGER  breakdown.llm         : ${ledger_llm:.6f}")
    print(f"WIRE    recomputed from usage : ${wire:.6f}")
    print(f"abs diff                      : ${diff:.6f}  (tolerance $0.0005)")
    print(f"MATCH                         : {'YES' if diff < 0.0005 else 'NO'}")
    print("-" * 68)
    print(f"grounding (per-request chan.) : ${grounding:.6f} ({cost.get('grounding_requests')} requests)")
    print(f"tour_total_cost               : ${cost.get('tour_total_cost', 0.0):.6f}")
    print(f"breakdown.tts (text-gen row)  : ${(cost.get('breakdown') or {}).get('tts', 0.0):.6f} "
          f"(Polly metered separately as its own tts_generate ledger row)")
    print("=" * 68)
    print("FULL _LAST_GENERATION_COST:")
    print(json.dumps({k: v for k, v in cost.items() if k != "cost_accumulator"}, indent=2, default=str))

    return 0 if diff < 0.0005 else 1


if __name__ == "__main__":
    sys.exit(main())
