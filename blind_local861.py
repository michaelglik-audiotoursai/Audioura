#!/usr/bin/env python3
"""blind_local861.py — build the blind scoring set for the LOCAL-861 museum A/B.

Reads ./_local861_raw/<museum>_<A|B>.{txt,log,meta.json} (arm-labelled, NOT
committed), assigns each text a random id, and writes:

  submission_artifacts/local861/blind/<id>.txt      text only (committed)
  submission_artifacts/local861/BLIND_KEY.json      {id: {museum, arm, usd, secs}}  (committed, separate file)
  _local861_blindlogs/<id>.log                      research log with model names
                                                    and museum arm hints redacted (NOT committed)

No paid API calls.  Deterministic seed, so the blinding is auditable.
The scorer must not open BLIND_KEY.json until every score is written.
"""
import json
import os
import random
import re

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "_local861_raw")
OUT = os.path.join(HERE, "submission_artifacts", "local861")
BLIND = os.path.join(OUT, "blind")
LOGS = os.path.join(HERE, "_local861_blindlogs")

random.seed(20261104)
_REDACT = re.compile(r"gpt-4\.1(-mini)?|gpt-4o(-mini)?|NARRATION_MODEL\S*|narrat\w+ model\S*", re.I)


def main():
    os.makedirs(BLIND, exist_ok=True)
    os.makedirs(LOGS, exist_ok=True)
    runs = sorted(f[:-10] for f in os.listdir(RAW) if f.endswith(".meta.json"))
    ids = random.sample(range(1000, 9999), len(runs))
    key = {}
    for tag, n in zip(runs, ids):
        meta = json.load(open(os.path.join(RAW, tag + ".meta.json"), encoding="utf-8"))
        bid = f"t{n}"
        text = open(os.path.join(RAW, tag + ".txt"), encoding="utf-8").read()
        open(os.path.join(BLIND, bid + ".txt"), "w", encoding="utf-8").write(text)
        log = open(os.path.join(RAW, tag + ".log"), encoding="utf-8", errors="ignore").read()
        open(os.path.join(LOGS, bid + ".log"), "w", encoding="utf-8").write(_REDACT.sub("[model]", log))
        key[bid] = {"museum": meta["museum"], "location": meta["location"], "arm": meta["arm"],
                    "narration_model": meta["narration_model"], "usd": meta["usd_meter"],
                    "seconds": meta["seconds"], "error": meta["error"]}
    json.dump(key, open(os.path.join(OUT, "BLIND_KEY.json"), "w", encoding="utf-8"),
              indent=2, sort_keys=True)
    print(f"blinded {len(key)} runs -> {BLIND}")
    print("ids:", " ".join(sorted(key)))


if __name__ == "__main__":
    main()
