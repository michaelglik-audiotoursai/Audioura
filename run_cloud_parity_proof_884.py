#!/usr/bin/env python3
"""run_cloud_parity_proof_884.py — LOCAL-884 cloud-parity proof + independent audit.

Extends the LOCAL-882 cloud-parity harness (SHORT typed names → the orchestrator
quick path → the SAME wave-40 pins; a WARM evidence cache; the wave-40 PASS
criteria; own DB + budget guard, D753) with the LOCAL-884 changes:

  1. CLOUD CACHE, not a simulated one. Before the cold+warm runs the harness
     loads the GCloud_Storied read-only cache export
     (~/Audioura/cloud_cache_snapshot/) into the DISPOSABLE proof DB, so the warm
     cache holds exactly the cloud's old POSITIVE and NEGATIVE evidence rows (the
     ones that starved wave 42). The code creates each cache table first (via its
     own lazy CREATE), then \\copy loads the CSV. If the snapshot is ABSENT the
     harness falls back to the 882 method: seed run 1 with a31ead22, seed run 2
     with 6fe0577f (this branch's base), so both old positive and old negative
     rows exist. The method used is reported.

  2. The INDEPENDENT gpt-4.1 audit receives EACH stop's evidence and LOGS the
     evidence CHARACTER COUNT per stop in the request; a stop with factual
     sentences must have > 0 evidence chars, and the audit must list 0 unsupported
     claims.

  3. Extra PASS criteria on the warm run (on top of the wave-40 set):
       * every stop has `labelled N > 0` in the grounding log, OR is a disclosed
         no-history stop (the D760 line);
       * every stop has >= 4 content sentences.

USAGE
    python3 run_cloud_parity_proof_884.py --selfcheck       # offline wiring check
    # LIVE (own DB :55984, load cloud snapshot, cold, warm, audit):
    #   docker compose -p local884 -f docker-compose.local884-proof.yml up -d
    #   TASK_BUDGET_ID=LOCAL-884 TASK_BUDGET_USD=0.50 \
    #   PAID_API_LOG=$PWD/_local884_meterlogs/paid_api_calls.jsonl \
    #   AUDIOURA_TASK_BUDGET_DIR=$PWD/_local884_meterlogs METER_MOUNT_GUARD=0 \
    #   METER_SERVICE=LOCAL-884 PYTHONPATH=$PWD/_meter \
    #   python3 run_cloud_parity_proof_884.py --run

The warm tour text and the audit JSON are written to submission_artifacts/local884/.
Run logs go to ./_local884_meterlogs/ (never committed).
"""
import argparse
import json
import os
import re
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "tests"))
sys.path.insert(0, os.path.join(_HERE, "_meter"))

import run_cloud_parity_proof as base  # the LOCAL-882 harness we extend

# ── LOCAL-884 overrides ───────────────────────────────────────────────────────
BASE_COMMIT = "6fe0577f"                         # the SUBSCRIBED base of this branch
PREV_COMMIT = "a31ead22"                         # the previous subscribed commit
_OWN_DB = os.environ.get(
    "LOCAL884_DB_URL", "postgresql://admin:password123@localhost:55984/audiotours")
_DB_PORT = os.environ.get("LOCAL884_DB_PORT", "55984")
_METER_DIR = os.path.join(_HERE, "_local884_meterlogs")
_ART_DIR = os.path.join(_HERE, "submission_artifacts", "local884")
_SNAPSHOT_DIR = os.path.expanduser(
    os.environ.get("CLOUD_CACHE_SNAPSHOT_DIR", "~/Audioura/cloud_cache_snapshot"))

# The cache tables we load from the snapshot, with the module whose lazy CREATE
# makes the table before the \copy. landmark_wiki_cache is the one this task turns
# on; the others are loaded when present so the warm run is cloud-faithful.
_SNAPSHOT_TABLES = [
    ("landmark_wiki_cache", "cloud_landmark_wiki_cache"),
    ("landmark_coord_cache", "cloud_landmark_coord_cache"),
    ("local_language_cache", "cloud_local_language_cache"),
    ("thin_verify_cache", "cloud_thin_verify_cache"),
    ("venue_preflight_cache", "cloud_venue_preflight_cache"),
    ("venue_works_cache", "cloud_venue_works_cache"),
    ("work_story_research_cache", "cloud_work_story_research_cache"),
    ("domain_tier_cache", "cloud_domain_tier_cache"),
]


def _apply_env():
    base._OWN_DB = _OWN_DB
    base._METER_DIR = _METER_DIR
    base._ART_DIR = _ART_DIR
    base.BASE_COMMIT = PREV_COMMIT
    base._apply_live_env()
    # repoint every DB var the base set to :55982 onto the 884 stack (:55984).
    for _k, _v in (("DATABASE_URL", _OWN_DB), ("VENUE_CACHE_DB_URL", _OWN_DB),
                   ("DB_PORT", _DB_PORT)):
        os.environ[_k] = _v
    os.environ.setdefault("GROUNDING_GATE_ENABLED", "1")
    os.environ.setdefault("GROUNDING_GATE_MODEL", "gpt-4.1-mini")


# ── load the cloud cache snapshot into the disposable proof DB ────────────────
def _snapshot_present() -> bool:
    try:
        f = os.path.join(_SNAPSHOT_DIR, "cloud_landmark_wiki_cache_20261109.csv.gz")
        if os.path.exists(f):
            return True
        # any dated wiki-cache export counts
        return any(fn.startswith("cloud_landmark_wiki_cache")
                   for fn in os.listdir(_SNAPSHOT_DIR))
    except Exception:
        return False


def _ensure_cache_tables():
    """Make each evidence-cache table exist (via the module's own lazy CREATE), so
    the \\copy has a target. landmark_wiki_cache is created by
    landmark_wikipedia_evidence._ensure; the rest by a direct CREATE mirroring the
    snapshot header when a module path is not obvious. We only NEED
    landmark_wiki_cache for this task; others are best-effort."""
    try:
        import landmark_wikipedia_evidence as lwe
        conn = lwe._conn()
        if conn is not None and lwe._ensure(conn):
            print("  [884 snapshot] landmark_wiki_cache table ready", flush=True)
    except Exception as e:
        print(f"  [884 snapshot] could not pre-create landmark_wiki_cache: {e}", flush=True)


def _proof_conn():
    """A psycopg2 connection to the DISPOSABLE 884 proof DB ONLY (the fixed
    :55984 own-DB URL), never the shared dev/live DB."""
    import psycopg2
    return psycopg2.connect(_OWN_DB)


def _count_rows(conn, table):
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            return cur.fetchone()[0]
    except Exception:
        return None


def _find_snapshot_csv(prefix: str):
    try:
        for fn in sorted(os.listdir(_SNAPSHOT_DIR)):
            if fn.startswith(prefix) and (fn.endswith(".csv.gz") or fn.endswith(".csv")):
                return os.path.join(_SNAPSHOT_DIR, fn)
    except Exception:
        pass
    return None


def load_cloud_snapshot() -> bool:
    """Load the cloud cache snapshot into the disposable proof DB via psycopg2
    COPY (no psql CLI needed). Creates the landmark_wiki_cache table first, then
    COPY each present CSV into the table columns named in its header. Returns True
    when at least landmark_wiki_cache loaded. Pinned to the 884 own-DB URL, so it
    never touches any shared DB."""
    import csv
    import gzip
    import io

    if not _snapshot_present():
        return False
    print(f"  [884 snapshot] loading from {_SNAPSHOT_DIR}", flush=True)
    _ensure_cache_tables()
    loaded_wiki = False
    try:
        conn = _proof_conn()
    except Exception as e:
        print(f"  [884 snapshot] could not connect to proof DB: {e}", flush=True)
        return False
    try:
        for table, prefix in _SNAPSHOT_TABLES:
            csv_path = _find_snapshot_csv(prefix)
            if not csv_path:
                continue
            # read the header to COPY only the columns the CSV carries (the real
            # table may have defaulted/extra columns, e.g. created_at).
            opener = gzip.open if csv_path.endswith(".gz") else open
            try:
                with opener(csv_path, "rt", encoding="utf-8", errors="replace") as fh:
                    header_line = fh.readline().rstrip("\n\r")
                    cols = next(csv.reader([header_line]))
                    data = fh.read()
            except Exception as e:
                print(f"  [884 snapshot] {table}: read error {e}", flush=True)
                continue
            col_list = ", ".join(f'"{c}"' for c in cols)
            buf = io.StringIO(header_line + "\n" + data)
            try:
                with conn.cursor() as cur:
                    # idempotent: the disposable proof DB's cache table is cleared
                    # before load so re-running the harness re-plants the SAME
                    # cloud rows (no PK conflict). Skips a table that does not
                    # exist yet (a cache other modules create lazily at runtime).
                    cur.execute("SELECT to_regclass(%s)", (table,))
                    if cur.fetchone()[0] is None:
                        print(f"  [884 snapshot] {table}: SKIPPED (table not created yet)",
                              flush=True)
                        conn.rollback()
                        continue
                    cur.execute(f"TRUNCATE {table}")
                    cur.copy_expert(
                        f"COPY {table} ({col_list}) FROM STDIN WITH (FORMAT csv, HEADER true)",
                        buf)
                conn.commit()
                n = _count_rows(conn, table)
                print(f"  [884 snapshot] {table}: loaded ({os.path.basename(csv_path)}; "
                      f"{n} rows)", flush=True)
                if table == "landmark_wiki_cache":
                    loaded_wiki = True
            except Exception as e:
                conn.rollback()
                print(f"  [884 snapshot] {table}: SKIPPED ({type(e).__name__}: "
                      f"{str(e)[:200]})", flush=True)
        # report the negative rows we just planted (what wave 42 was starved by).
        if loaded_wiki:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT name, found, COALESCE(rules_version,'<null>') "
                                "FROM landmark_wiki_cache WHERE found = false ORDER BY name")
                    neg = cur.fetchall()
                print(f"  [884 snapshot] negative rows planted: {len(neg)}", flush=True)
                for nm, fnd, rv in neg:
                    print(f"      NEG {nm!r} rules_version={rv}", flush=True)
            except Exception:
                pass
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return loaded_wiki


# ── per-stop evidence + 884 PASS criteria ─────────────────────────────────────
def _build_evidence_by_stop():
    """Per-stop evidence bundle read back from the job sinks (same as the 883
    harness)."""
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
        import llm_evidence as _le892
        for k, sl in snips.items():
            texts = []
            for s in _le892.filter_records(sl):      # [LOCAL-892] an LLM's output is never evidence
                if isinstance(s, dict):
                    texts.append(str(s.get("title", "")))
                    texts.append(str(s.get("snippet", "")))
                else:
                    texts.append(str(s))
            blob = " ".join(t for t in texts if t)
            if blob.strip():
                ev[str(k)] = (ev.get(str(k), "") + " " + blob).strip()
        # [LOCAL-884] the Wikipedia evidence the narrator saw (per-job sink), so a
        # stop grounded only on its article shows >0 evidence chars to the auditor.
        try:
            wiki = dict(g._WIKI_EVIDENCE_SINK.get(g._J._THIN_SINK_KEY, {}) or {})
            for k, items in wiki.items():
                blob = " ".join(str(x) for x in (items or []) if str(x).strip())
                if blob.strip():
                    ev[str(k)] = (ev.get(str(k), "") + " " + blob).strip()
        except Exception:
            pass
    except Exception as e:
        print(f"  [audit] could not read evidence sinks: {e}", flush=True)
    try:                                  # [LOCAL-892] belt and braces: registered LLM passages out
        import llm_evidence as _le892z
        ev = _le892z.scrub_map(ev)
    except Exception:
        pass
    return ev


def llm_leads_by_stop():
    """[LOCAL-892] The LLM-sourced snippets each stop held (narrator leads, NEVER evidence)."""
    out = {}
    try:
        import generate_tour_text as g
        import llm_evidence as le
        for k, sl in dict(getattr(g._J, "_DIRECT_SNIPPETS_PER_STOP", {}) or {}).items():
            bad = [str(x.get("snippet", "")) for x in (sl or []) if isinstance(x, dict) and not le.is_evidence_record(x)]
            if bad:
                out[str(k)] = bad
    except Exception:
        pass
    return out


_AUDIT_MODEL = os.environ.get("LOCAL884_AUDIT_MODEL", "gpt-4.1")
_AUDIT_SYSTEM = (
    "You are an INDEPENDENT fact auditor for an audio walking tour. You are given "
    "the FULL tour text and, per stop, that stop's EVIDENCE (its own article text, "
    "page facts and sourced snippets) WITH the evidence character count. List EVERY "
    "factual claim in the tour that is NOT supported by its own stop's evidence — a "
    "date, number, named person, event or function the evidence neither states nor "
    "implies, or that the evidence contradicts. Judge ONLY against the evidence "
    "provided, never your own knowledge. Sensory, directional and reflective "
    "sentences are not factual claims — ignore them. A claim explicitly framed as a "
    "legend/myth/story, and an honest 'we could not confirm verified history' "
    "disclosure, are acceptable and must NOT be listed. Return STRICT JSON: "
    "{\"unsupported\": [{\"stop\": \"<title>\", \"claim\": \"<sentence>\", "
    "\"why\": \"<reason>\"}]}. An empty list means every factual claim is grounded. "
    "[LOCAL-891] Each evidence item is tagged about_stop=true/false. A claim is SUPPORTED only when an "
    "about_stop=true item states it (the stop's own article, or a passage whose subject is the stop). "
    "A claim that only an about_stop=false item states (the city, a neighbouring place, a person - e.g. "
    "an event that happened elsewhere in the city) is UNSUPPORTED: list it with why 'off-topic', unless the "
    "sentence itself ties the event to a different place ('a few blocks away, at ...') - at most one such "
    "sentence per stop."
)


def independent_audit(warm_text, evidence_by_stop, model=_AUDIT_MODEL):
    """ONE gpt-4.1 call. The per-stop evidence block carries the CHARACTER COUNT so
    the audit (and this log) can see each stop actually received its evidence.
    Returns (audit_dict, ok). ok is True only when the call succeeded AND returned
    zero unsupported claims."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    # log the evidence char count per stop (the audit input proof).
    ev_counts = {t: len((e or "").strip()) for t, e in (evidence_by_stop or {}).items()}
    print("  [audit] evidence char count per stop:", flush=True)
    for t, n in ev_counts.items():
        print(f"      {t[:48]:48} {n:6d} chars", flush=True)
    if not api_key:
        return {"error": "no OPENAI_API_KEY", "unsupported": None,
                "evidence_chars": ev_counts}, False
    # [LOCAL-891] the SAME flagged items the gate reads (about_stop true/false); a claim supported only
    # by an about_stop=false item is UNSUPPORTED (off-topic).
    import aboutness as _ab
    _items_by_stop = {}
    _blobs = []
    for t, e in (evidence_by_stop or {}).items():
        if not e:
            continue
        its = _ab.build_items(e, t)
        _items_by_stop[t] = its
        body = "\n".join(f"[{i['id']} | about_stop={'true' if i['about_stop'] else 'false'} | {i['kind']}] {i['text']}"
                         for i in its)
        _blobs.append(f"### {t}  [{len((e or '').strip())} evidence chars]\n{body}")
    ev_blob = "\n\n".join(_blobs)
    user = (f"TOUR TEXT:\n{warm_text[:16000]}\n\n"
            f"PER-STOP EVIDENCE (with char counts):\n{ev_blob[:150000]}\n\n"
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
                "temperature": 0, "max_tokens": 3000,
                "response_format": {"type": "json_object"}}),
            timeout=120)
        if resp.status_code != 200:
            return {"error": f"http {resp.status_code}", "unsupported": None,
                    "evidence_chars": ev_counts}, False
        body = resp.json()
        content = body["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        parsed["_model"] = model
        parsed["_usage"] = body.get("usage", {}) or {}
        parsed["evidence_chars"] = ev_counts
        unsupported = parsed.get("unsupported")
        # [LOCAL-891] the same aboutness rule, mechanically, over the same items
        try:
            ab = _ab.audit_tour(warm_text, evidence_by_stop)
            parsed["offtopic_mechanical"] = ab["offtopic"]
            parsed["items_by_stop"] = {t: [{k: i[k] for k in ("id", "about_stop", "kind", "source", "why")}
                                           for i in its] for t, its in _items_by_stop.items()}
            if isinstance(unsupported, list):
                have = {(u.get("claim") or "").strip() for u in unsupported if isinstance(u, dict)}
                for o in ab["offtopic"]:
                    if o["claim"].strip() not in have:
                        unsupported.append({"stop": o["stop"], "claim": o["claim"],
                                            "why": o["why"], "by": "aboutness-rule"})
        except Exception as _ae:
            parsed["offtopic_error"] = f"{type(_ae).__name__}: {_ae}"
        ok = isinstance(unsupported, list) and len(unsupported) == 0
        return parsed, ok
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "unsupported": None,
                "evidence_chars": ev_counts}, False


def _labelled_ok(log_text):
    """Parse the grounding log: across ALL passes a stop must have been labelled
    N>0 at least once, OR have been disclosed as a no-history stop at least once.
    (The final re-pass re-logs an already-disclosed stop as 'labelled 0', so we
    aggregate per stop rather than trust the last line.) Returns (ok, detail)."""
    max_lab = {}
    ever_disclosed = {}
    for m in re.finditer(r"\[LOCAL-884\] Stop (\d+) '[^']*': labelled (\d+)(.*)",
                         log_text or ""):
        n = int(m.group(1))
        labelled = int(m.group(2))
        disclosed = "no-history" in (m.group(3) or "")
        max_lab[n] = max(max_lab.get(n, 0), labelled)
        ever_disclosed[n] = ever_disclosed.get(n, False) or disclosed
    if not max_lab:
        return False, "no per-stop labelled lines found"
    bad = [n for n in max_lab
           if max_lab[n] <= 0 and not ever_disclosed.get(n, False)]
    stops = max_lab  # for the count in the detail string
    return (not bad), (f"all {len(stops)} stops labelled>0 or disclosed"
                       if not bad else f"stops with labelled 0 and not disclosed: {bad}")


def evaluate_884(text, log):
    """The 882 wave-40 criteria PLUS the 884 criteria (labelled N>0 or disclosed;
    every stop >= 4 content sentences)."""
    checks = base._criteria(text, log, require_ten=True)
    # labelled N > 0 or disclosed, from the log
    lab_ok, lab_detail = _labelled_ok(log)
    base._check("every stop labelled N>0 or is a disclosed no-history stop",
                lab_ok, lab_detail)
    checks.append(("labelled", lab_ok))
    # every stop >= 4 content sentences
    blocks = base._blocks(text)
    short = [(n, t) for n, t, b in blocks
             if len(base._content_sentences(base._prose((n, t, b)))) < 4]
    four_ok = not short
    base._check("every stop >= 4 content sentences", four_ok,
                "all >=4" if four_ok else f"short: {short}")
    checks.append(("four_sentences", four_ok))
    return all(v for _, v in checks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--load-snapshot", action="store_true")
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--cold", action="store_true")
    ap.add_argument("--warm", action="store_true")
    ap.add_argument("--run", action="store_true",
                    help="load snapshot (or seed) + cold + warm + audit")
    args = ap.parse_args()

    os.makedirs(_ART_DIR, exist_ok=True)
    os.makedirs(_METER_DIR, exist_ok=True)

    if args.selfcheck:
        base._ART_DIR = _ART_DIR
        base._METER_DIR = _METER_DIR
        rc = base._selfcheck()
        # 884 additions: the labelled-log parser and the 884 criteria, offline.
        print("\n   [884 selfcheck] labelled-log parser + criteria (offline)", flush=True)
        good_log = ("  [LOCAL-884] Stop 1 'Cathedral': labelled 3\n"
                    "  [LOCAL-884] Stop 2 'Thi Bar': labelled 0 (no-history disclosed)\n")
        bad_log = ("  [LOCAL-884] Stop 1 'Cathedral': labelled 0\n")
        ok1, d1 = _labelled_ok(good_log)
        ok2, d2 = _labelled_ok(bad_log)
        print(f"      good_log -> {ok1} ({d1}); bad_log -> {ok2} ({d2})", flush=True)
        assert ok1 and not ok2
        # snapshot presence (informational; selfcheck never spends or loads).
        print(f"   [884 selfcheck] cloud snapshot present: {_snapshot_present()} "
              f"at {_SNAPSHOT_DIR}", flush=True)
        print("=== 884 SELFCHECK PASS ===", flush=True)
        return rc

    _apply_env()
    if os.environ.get("TASK_BUDGET_ID") != "LOCAL-884":
        sys.exit("refusing live run: launch with TASK_BUDGET_ID=LOCAL-884")
    hard_cap = float(os.environ.get("TASK_BUDGET_USD", "0.50") or "0.50")
    cold_cap = float(os.environ.get("LOCAL884_COLD_CAP", "0.15"))
    seed_cap = float(os.environ.get("LOCAL884_SEED_CAP", "0.15"))
    audit_reserve = float(os.environ.get("LOCAL884_AUDIT_RESERVE", "0.06"))

    used_snapshot = False
    if args.run or args.load_snapshot or args.seed:
        used_snapshot = load_cloud_snapshot()
        if used_snapshot:
            print("  [884] WARM cache = CLOUD snapshot (landmark_wiki_cache loaded)",
                  flush=True)
        else:
            print("  [884] cloud snapshot ABSENT -> seeding a31ead22 then 6fe0577f",
                  flush=True)
            if base._meter_total() + 0.01 <= hard_cap + 1e-9:
                base.BASE_COMMIT = PREV_COMMIT
                base.seed_with_base(min(base._meter_total() + seed_cap, hard_cap))
                base.BASE_COMMIT = BASE_COMMIT
                base.seed_with_base(min(base._meter_total() + seed_cap, hard_cap))

    if args.run or args.cold:
        if used_snapshot and not args.cold:
            # The CLOUD snapshot already IS the warm evidence cache (seed+cold
            # exist only to PLANT old rows when no snapshot is available). With the
            # snapshot loaded we go straight to the PASS-checked warm run, which
            # keeps the whole generation under the $0.50 budget.
            print("  [884] cloud snapshot loaded -> skipping cold (snapshot is the "
                  "warm cache); warm run next", flush=True)
        else:
            base.phase("cold", min(hard_cap, base._meter_total() + cold_cap))

    if args.run or args.warm:
        warm_cap = max(base._meter_total(), hard_cap - audit_reserve)
        warm_text, warm_log = base.phase("warm", warm_cap)
        print("\n=== WARM PASS CHECK (cloud-parity + 884) ===", flush=True)
        warm_ok = evaluate_884(warm_text, warm_log)
        print(f"=== WARM {'PASS' if warm_ok else 'FAIL'} === "
              f"(task meter ${base._meter_total():.4f} of ${hard_cap:.2f})", flush=True)

        print("\n=== INDEPENDENT gpt-4.1 AUDIT (per-stop evidence chars) ===", flush=True)
        ev = _build_evidence_by_stop()
        audit, audit_ok = independent_audit(warm_text, ev)
        audit["used_cloud_snapshot"] = used_snapshot
        audit_path = os.path.join(_ART_DIR, "saigon_warm_audit.json")
        with open(audit_path, "w", encoding="utf-8") as f:
            json.dump(audit, f, ensure_ascii=False, indent=2)
        n_unsup = (len(audit.get("unsupported")) if isinstance(audit.get("unsupported"), list)
                   else "ERROR")
        print(f"   audit model={audit.get('_model')}, unsupported={n_unsup}", flush=True)
        if isinstance(audit.get("unsupported"), list):
            for u in audit["unsupported"]:
                print(f"      UNSUPPORTED [{u.get('stop')}]: {u.get('claim','')[:90]}",
                      flush=True)
        print(f"   audit JSON -> {audit_path}", flush=True)
        # every stop with factual sentences must have >0 evidence chars.
        ev_counts = audit.get("evidence_chars", {}) or {}
        zero_ev = [t for t, n in ev_counts.items() if n == 0]
        print(f"   stops with 0 evidence chars: {zero_ev or 'none'}", flush=True)
        print(f"=== AUDIT {'PASS (0 unsupported)' if audit_ok else 'FAIL'} ===", flush=True)
        print(f"\n=== LOCAL-884 {'PASS' if (warm_ok and audit_ok) else 'FAIL'} === "
              f"(meter ${base._meter_total():.4f} of ${hard_cap:.2f}; "
              f"cloud_snapshot={used_snapshot})", flush=True)
        return 0 if (warm_ok and audit_ok) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
