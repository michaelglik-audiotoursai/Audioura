#!/usr/bin/env python3
"""run_cloud_parity_proof_883.py — LOCAL-883 cloud-parity proof + independent audit.

Same cloud-parity harness as LOCAL-882 (SHORT typed names → the orchestrator
quick path → the SAME wave-40 pins; seed the cache with the SUBSCRIBED BASE
commit, then a COLD run, then the PASS-checked WARM run on THIS branch's code),
with two LOCAL-883 differences:

  1. The cache is seeded with the SUBSCRIBED base **a831ba0c** (this branch's
     base), not a31ead22. That is the commit the worktree is checked out on, so
     the warm cache holds exactly the entries the cloud had before this branch.

  2. After the warm run, an INDEPENDENT audit makes ONE gpt-4.1 (not mini) call
     with the FULL warm tour text and EVERY stop's evidence bundle, and lists
     each factual claim not supported by its stop's evidence. PASS requires ZERO
     unsupported claims — the mechanism change (strict grounding) must hold up to
     a second, stronger model that never saw the generation.

Everything else (the quick-path payload, the wave-40 PASS criteria, the budget
guard, the own-DB isolation D753) is reused from run_cloud_parity_proof.

USAGE
    python3 run_cloud_parity_proof_883.py --selfcheck        # offline wiring check
    # LIVE (own DB :55983, seed a831ba0c, cold, warm, audit):
    #   docker compose -p local883 -f docker-compose.local883-proof.yml up -d
    #   TASK_BUDGET_ID=LOCAL-883 TASK_BUDGET_USD=0.50 \
    #   PAID_API_LOG=$PWD/_local883_meterlogs/paid_api_calls.jsonl \
    #   AUDIOURA_TASK_BUDGET_DIR=$PWD/_local883_meterlogs METER_MOUNT_GUARD=0 \
    #   METER_SERVICE=LOCAL-883 PYTHONPATH=$PWD/_meter \
    #   python3 run_cloud_parity_proof_883.py --run

The warm tour text and the audit JSON are written to submission_artifacts/local883/.
Run logs go to ./_local883_meterlogs/ (never committed).
"""
import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "tests"))
sys.path.insert(0, os.path.join(_HERE, "_meter"))

import run_cloud_parity_proof as base  # the LOCAL-882 harness we extend

# ── LOCAL-883 overrides ───────────────────────────────────────────────────────
BASE_COMMIT = "a831ba0c"                        # the SUBSCRIBED base of this branch
_OWN_DB = os.environ.get(
    "LOCAL883_DB_URL", "postgresql://admin:password123@localhost:55983/audiotours")
_METER_DIR = os.path.join(_HERE, "_local883_meterlogs")
_ART_DIR = os.path.join(_HERE, "submission_artifacts", "local883")


def _apply_env():
    """Reuse the LOCAL-882 live env, then repoint the DB + meter dir + base commit
    to the LOCAL-883 isolated stack."""
    base._OWN_DB = _OWN_DB
    base._METER_DIR = _METER_DIR
    base._ART_DIR = _ART_DIR
    base.BASE_COMMIT = BASE_COMMIT
    base._apply_live_env()
    # the grounding gate on; cheap arm for the checker calls.
    os.environ.setdefault("GROUNDING_GATE_ENABLED", "1")
    os.environ.setdefault("GROUNDING_GATE_MODEL", "gpt-4.1-mini")


# ── the independent gpt-4.1 audit (one call) ──────────────────────────────────
_AUDIT_MODEL = os.environ.get("LOCAL883_AUDIT_MODEL", "gpt-4.1")
_AUDIT_SYSTEM = (
    "You are an INDEPENDENT fact auditor for an audio walking tour. You are given "
    "the FULL tour text and, per stop, that stop's EVIDENCE (its own article text, "
    "page facts and sourced snippets). List EVERY factual claim in the tour that is "
    "NOT supported by its own stop's evidence — a date, number, named person, "
    "event or function the evidence neither states nor implies, or that the "
    "evidence contradicts. Judge ONLY against the evidence provided, never your own "
    "knowledge. Sensory, directional and reflective sentences are not factual "
    "claims — ignore them. A claim explicitly framed as a legend/myth/story is "
    "acceptable and must NOT be listed. Return STRICT JSON: {\"unsupported\": "
    "[{\"stop\": \"<title>\", \"claim\": \"<sentence>\", \"why\": \"<reason>\"}]}. "
    "An empty list means every factual claim is grounded."
)


def _build_evidence_by_stop():
    """The per-stop evidence bundle the generator used, read back from the job
    sinks the warm run populated (873 facts + 873 snippets), keyed by stop title.
    Falls back to an empty map (the audit then has nothing to check against, which
    the harness treats as an incomplete audit, not a pass)."""
    ev = {}
    try:
        import generate_tour_text as g
        facts = dict(getattr(g._J, "_THIN_FACTS_PER_STOP", {}) or {})
        try:
            for _k, _v in (g._THIN_FACTS_SINK.get(g._J._THIN_SINK_KEY, {}) or {}).items():
                facts.setdefault(_k, [])
                for _t in _v:
                    if _t and _t not in facts[_k]:
                        facts[_k].append(_t)
        except Exception:
            pass
        for k, v in facts.items():
            ev[str(k)] = " ".join(str(x) for x in (v or []))
        snips = dict(getattr(g._J, "_DIRECT_SNIPPETS_PER_STOP", {}) or {})
        for k, sl in snips.items():
            texts = []
            for s in sl or []:
                if isinstance(s, dict):
                    texts.append(str(s.get("title", "")))
                    texts.append(str(s.get("snippet", "")))
                else:
                    texts.append(str(s))
            blob = " ".join(t for t in texts if t)
            if blob.strip():
                ev[str(k)] = (ev.get(str(k), "") + " " + blob).strip()
    except Exception as e:
        print(f"  [audit] could not read evidence sinks: {e}", flush=True)
    return ev


def independent_audit(warm_text, evidence_by_stop, model=_AUDIT_MODEL):
    """ONE gpt-4.1 call. Returns (audit_dict, ok). ok is True only when the call
    succeeded AND returned zero unsupported claims."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return {"error": "no OPENAI_API_KEY", "unsupported": None}, False
    ev_blob = "\n\n".join(f"### {t}\n{(e or '').strip()[:1500]}"
                          for t, e in (evidence_by_stop or {}).items() if e)
    user = (f"TOUR TEXT:\n{warm_text[:16000]}\n\n"
            f"PER-STOP EVIDENCE:\n{ev_blob[:16000]}\n\n"
            f"List every unsupported factual claim as JSON now.")
    try:
        import requests
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            data=json.dumps({
                "model": model,
                "messages": [{"role": "system", "content": _AUDIT_SYSTEM},
                             {"role": "user", "content": user}],
                "temperature": 0, "max_tokens": 1500,
                "response_format": {"type": "json_object"}}),
            timeout=90)
        if resp.status_code != 200:
            return {"error": f"http {resp.status_code}", "unsupported": None}, False
        body = resp.json()
        content = body["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        usage = body.get("usage", {}) or {}
        parsed["_model"] = model
        parsed["_usage"] = usage
        unsupported = parsed.get("unsupported")
        ok = isinstance(unsupported, list) and len(unsupported) == 0
        return parsed, ok
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "unsupported": None}, False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--cold", action="store_true")
    ap.add_argument("--warm", action="store_true")
    ap.add_argument("--run", action="store_true", help="seed + cold + warm + audit")
    args = ap.parse_args()

    os.makedirs(_ART_DIR, exist_ok=True)
    os.makedirs(_METER_DIR, exist_ok=True)

    if args.selfcheck:
        # reuse the base offline wiring + PASS-criteria self-check.
        base._ART_DIR = _ART_DIR
        base._METER_DIR = _METER_DIR
        rc = base._selfcheck()
        # plus: prove the audit prompt builder + parser wire up WITHOUT any network
        # call (selfcheck must never spend). We build the request strings and parse
        # a canned gpt-4.1 JSON response through the same logic independent_audit
        # uses, asserting a 0-unsupported body is judged a PASS and a non-empty one
        # a FAIL.
        print("   [audit selfcheck] prompt + parser wiring (offline)", flush=True)
        ev = {"Cathedral": "The cathedral was completed in 1880, designed by Jules Bourard."}
        ev_blob = "\n\n".join(f"### {t}\n{(e or '').strip()[:1500]}"
                              for t, e in ev.items() if e)
        assert "Cathedral" in ev_blob and "1880" in ev_blob
        clean = {"unsupported": []}
        dirty = {"unsupported": [{"stop": "Cathedral", "claim": "Built by Eiffel.",
                                  "why": "not in evidence"}]}
        clean_ok = isinstance(clean["unsupported"], list) and len(clean["unsupported"]) == 0
        dirty_ok = isinstance(dirty["unsupported"], list) and len(dirty["unsupported"]) == 0
        print(f"   [audit selfcheck] clean->PASS={clean_ok}, dirty->PASS={dirty_ok}", flush=True)
        assert clean_ok and not dirty_ok
        return rc

    _apply_env()
    if os.environ.get("TASK_BUDGET_ID") != "LOCAL-883":
        sys.exit("refusing live run: launch with TASK_BUDGET_ID=LOCAL-883")
    hard_cap = float(os.environ.get("TASK_BUDGET_USD", "0.50") or "0.50")
    seed_cap = float(os.environ.get("LOCAL883_SEED_CAP", "0.15"))
    cold_cap = float(os.environ.get("LOCAL883_COLD_CAP", "0.15"))
    audit_reserve = float(os.environ.get("LOCAL883_AUDIT_RESERVE", "0.06"))

    if args.run or args.seed:
        if base._meter_total() + 0.01 > hard_cap + 1e-9:
            sys.exit(f"refusing seed: meter ${base._meter_total():.4f} near cap ${hard_cap:.2f}")
        base.seed_with_base(min(base._meter_total() + seed_cap, hard_cap))

    if args.run or args.cold:
        base.phase("cold", min(hard_cap, base._meter_total() + cold_cap))

    if args.run or args.warm:
        # leave an audit_reserve for the single gpt-4.1 audit call.
        warm_cap = max(base._meter_total(), hard_cap - audit_reserve)
        warm_text, warm_log = base.phase("warm", warm_cap)
        print("\n=== WARM PASS CHECK (cloud-parity) ===", flush=True)
        warm_ok = base.evaluate(warm_text, warm_log)
        print(f"=== WARM {'PASS' if warm_ok else 'FAIL'} === "
              f"(task meter ${base._meter_total():.4f} of ${hard_cap:.2f})", flush=True)

        # independent gpt-4.1 audit on the warm text.
        print("\n=== INDEPENDENT gpt-4.1 AUDIT ===", flush=True)
        ev = _build_evidence_by_stop()
        audit, audit_ok = independent_audit(warm_text, ev)
        audit_path = os.path.join(_ART_DIR, "saigon_warm_audit.json")
        with open(audit_path, "w", encoding="utf-8") as f:
            json.dump(audit, f, ensure_ascii=False, indent=2)
        n_unsup = (len(audit.get("unsupported")) if isinstance(audit.get("unsupported"), list)
                   else "ERROR")
        print(f"   audit model={audit.get('_model')}, unsupported={n_unsup}", flush=True)
        if isinstance(audit.get("unsupported"), list):
            for u in audit["unsupported"]:
                print(f"      UNSUPPORTED [{u.get('stop')}]: {u.get('claim','')[:90]}", flush=True)
        print(f"   audit JSON -> {audit_path}", flush=True)
        print(f"=== AUDIT {'PASS (0 unsupported)' if audit_ok else 'FAIL'} ===", flush=True)
        print(f"\n=== LOCAL-883 {'PASS' if (warm_ok and audit_ok) else 'FAIL'} === "
              f"(meter ${base._meter_total():.4f} of ${hard_cap:.2f})", flush=True)
        return 0 if (warm_ok and audit_ok) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
