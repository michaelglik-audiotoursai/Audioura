#!/usr/bin/env python3
"""LOCAL-560 Step 3 — replay every recorded CHECKER call with gpt-4o-mini.

For each CHECKER call in the recordings (same messages, same temperature, same
response_format), re-issue it against gpt-4o-mini and record the new response.
WRITER sites are not replayed (their models are out of scope for the switch).

Bounded thread pool (<= 8). Output appended as JSON lines to replay_mini.jsonl:
  {site, tour, record_index, orig_model, new_model, temperature,
   response_text, usage, status}

Idempotent: on re-run, calls already present in replay_mini.jsonl (keyed by
tour+record_index) are skipped, so a timeout mid-replay loses nothing.

Run from repo root:
  python3 tests/fixtures/local560/replay_mini.py
"""
import json, glob, os, sys, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
REC = os.path.join(HERE, "recordings")
OUT = os.path.join(HERE, "replay_mini.jsonl")
NEW_MODEL = "gpt-4o-mini"
MAX_WORKERS = 8

# Load .env for OPENAI_API_KEY
_envfile = os.path.join(REPO, ".env")
if os.path.exists(_envfile):
    for _line in open(_envfile):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

API_KEY = os.environ.get("OPENAI_API_KEY")

# The CHECKER sites (same set as mark_discrepancies.py). Replay all of them.
CHECKER_SITES = {
    "stop_specificity_gate.py:433", "story_gate.py:201",
    "unglossed_reference_gate.py:690", "unsupported_claim_gate.py:452",
    "generate_tour_text.py:1083", "generate_tour_text.py:1577",
    "story_element_extractor.py:419", "fact_extractor.py:76",
    "generate_tour_text.py:1008", "generate_tour_text.py:9580",
    "generate_tour_text.py:18583", "generate_tour_text.py:9983",
    "generate_tour_text.py:7770", "generate_tour_text.py:8781",
    "generate_tour_text.py:10105", "theme_thread_discoverer.py:260",
}

_write_lock = threading.Lock()


def _load_done():
    done = set()
    if os.path.exists(OUT):
        for line in open(OUT, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                done.add((r["tour"], r["record_index"]))
            except Exception:
                pass
    return done


def _collect_jobs(done):
    jobs = []
    for f in sorted(glob.glob(os.path.join(REC, "*.jsonl"))):
        tour = os.path.basename(f).replace(".jsonl", "")
        idx = 0
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            idx += 1
            if r.get("site") not in CHECKER_SITES:
                continue
            if (tour, idx) in done:
                continue
            jobs.append({
                "tour": tour, "record_index": idx, "site": r.get("site"),
                "orig_model": r.get("model"), "temperature": r.get("temperature"),
                "max_tokens": r.get("max_tokens"), "messages": r.get("messages"),
                "response_format": r.get("response_format"),
            })
    return jobs


def _replay_one(job):
    import requests
    body = {
        "model": NEW_MODEL,
        "messages": job["messages"],
    }
    if job.get("temperature") is not None:
        body["temperature"] = job["temperature"]
    if job.get("max_tokens") is not None:
        body["max_tokens"] = job["max_tokens"]
    if job.get("response_format") is not None:
        body["response_format"] = job["response_format"]

    rec = {
        "site": job["site"], "tour": job["tour"],
        "record_index": job["record_index"],
        "orig_model": job["orig_model"], "new_model": NEW_MODEL,
        "temperature": job["temperature"],
    }
    for attempt in range(4):
        try:
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {API_KEY}",
                         "Content-Type": "application/json"},
                data=json.dumps(body), timeout=90,
            )
            if resp.status_code == 200:
                j = resp.json()
                rec["response_text"] = j.get("choices", [{}])[0].get("message", {}).get("content")
                rec["usage"] = j.get("usage")
                rec["status"] = 200
                return rec
            if resp.status_code in (429, 500, 502, 503):
                time.sleep([2, 5, 15, 30][attempt])
                continue
            rec["status"] = resp.status_code
            rec["response_text"] = None
            rec["error"] = resp.text[:200]
            return rec
        except Exception as e:
            if attempt == 3:
                rec["status"] = -1
                rec["response_text"] = None
                rec["error"] = f"{type(e).__name__}: {e}"
                return rec
            time.sleep([2, 5, 15, 30][attempt])
    return rec


def _append(rec):
    with _write_lock:
        with open(OUT, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()


def main():
    if not API_KEY:
        print("ERROR: OPENAI_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    done = _load_done()
    jobs = _collect_jobs(done)
    print(f"checker calls to replay: {len(jobs)} (already done: {len(done)})", flush=True)
    if not jobs:
        print("nothing to do", flush=True)
        return
    ok = err = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_replay_one, j): j for j in jobs}
        for i, fut in enumerate(as_completed(futs), 1):
            rec = fut.result()
            _append(rec)
            if rec.get("status") == 200:
                ok += 1
            else:
                err += 1
            if i % 25 == 0:
                print(f"  {i}/{len(jobs)} done  ok={ok} err={err}  "
                      f"{time.time()-t0:.0f}s", flush=True)
    print(f"DONE: ok={ok} err={err} total={len(jobs)}  {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
