#!/usr/bin/env python3
"""run_local607_live.py — LOCAL-607 isolated live delivery check.

Runs INSIDE a disposable container (docker run --rm --name local607-gen …),
never against the audioura-* stack. Requests ONE McMullen tour, 7 stops, with the
stop POOL ON (the reuse path). Hard cost cap $1.50.

Prints, from the ONE delivered tour, exactly what Michael asked to see:
  * Stop 1's opening section, with the hours spoken
  * Grace Hoops in full
  * the last stop's ending through the conclusion
  * the cross-stop dedupe log lines
  * the BLOCKER 3 factual-integrity QA lines (incl. 'No repeated story across stops')
  * Tour total:
"""
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_envfile = os.path.join(HERE, ".env")
if os.path.exists(_envfile):
    for line in open(_envfile):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

os.environ["STORIED_MODE"] = "true"
# Pool ON — this is the whole point of the run (the reuse path).
os.environ.pop("DISABLE_STOP_POOL", None)
# Hard LLM spend ceiling for this single run.
os.environ.setdefault("COST_HARD_LIMIT_USD", "1.50")

LOCATION = os.environ.get("LOCAL607_LOCATION",
                          "McMullen Museum of Art, Boston College, Boston, MA")
TOUR_TYPE = os.environ.get("LOCAL607_TYPE", "museum")
STOPS = int(os.environ.get("LOCAL607_STOPS", "7"))
_OUTDIR = os.path.join(HERE, "tours") if os.path.isdir(os.path.join(HERE, "tours")) else HERE
OUT = os.path.join(_OUTDIR, "LOCAL607_mcmullen_pool.txt")

import generate_tour_text as g  # noqa: E402

print("=" * 78)
print(f"LOCAL-607 live (pool ON): {LOCATION} / {TOUR_TYPE} / {STOPS} stops  cap=$1.50")
print("=" * 78, flush=True)

t0 = time.time()
text, _out, _coords = g.generate_tour_text(LOCATION, TOUR_TYPE, OUT, STOPS)
wall = time.time() - t0

cost = dict(getattr(g, "_LAST_GENERATION_COST", {}) or {})
path = getattr(g, "_LAST_DELIVERY_PATH", "?")
n_stops = len(re.findall(r'^Stop\s+\d+:', text or "", re.M))

print("\n" + "=" * 78)
print(f"DELIVERY: path={path}  stops={n_stops}  wall={wall:.0f}s")
print("=" * 78, flush=True)


def _stop_block(num):
    m = re.search(rf'(^Stop\s+{num}:.*?)(?=\nStop\s+\d+:|\nFrom\s+.+?you have followed|\Z)',
                  text or "", re.S | re.M)
    return m.group(1).strip() if m else ""


# ── Stop 1 opening section (with hours) ──────────────────────────────────────
print("\n----- STOP 1 (opening section, hours spoken) -----")
s1 = _stop_block(1)
print(s1[:1600])

# ── Grace Hoops in full ──────────────────────────────────────────────────────
print("\n----- GRACE HOOPS (full) -----")
m = re.search(r'(^Stop\s+\d+:\s*Grace Hoops.*?)(?=\nStop\s+\d+:|\Z)',
              text or "", re.S | re.M)
print(m.group(1).strip() if m else "(Grace Hoops stop not found)")

# ── Last stop ending through the conclusion ──────────────────────────────────
print("\n----- LAST STOP ENDING → CONCLUSION -----")
_last = list(re.finditer(r'^Stop\s+\d+:', text or "", re.M))
if _last:
    tail = (text or "")[_last[-1].start():]
    # print the last ~900 chars so the stop end + full conclusion are visible
    print(tail[-1100:])

# ── Dedupe log + BLOCKER 3 QA lines ──────────────────────────────────────────
print("\n----- CONTENT QA (BLOCKER 3 factual integrity) -----")
try:
    import content_qa_runner as qa
    qa.run_qa(text or "", tour_file=OUT)
    print(f"\nFACTUAL_FAIL_COUNT={getattr(qa, 'FACTUAL_FAIL_COUNT', '?')}")
except Exception as e:
    print(f"QA run error: {e}")

print("\n" + "=" * 78)
print(f"Tour total:           ${cost.get('tour_total_cost', cost.get('total_cost', 0.0)):.4f}")
print(f"  (LLM ${cost.get('total_cost', 0.0):.4f}  "
      f"grounding ${cost.get('grounding_cost', 0.0):.4f}  "
      f"pool_reuse={cost.get('pool_reuse', False)})")
print("=" * 78, flush=True)
