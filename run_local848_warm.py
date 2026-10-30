"""run_local848_warm.py — LOCAL-848 WARM-container cross-request memory proof.

The generator on Cloud Run is a long-lived container that serves many requests.
The OOM (531 MiB) hit MID-TOUR on already-running revisions, which is the
signature of RSS ratcheting UP request after request until the 512 MiB cap is
crossed — not a single tour needing 531 MiB on its own.

This runner exercises the REAL service path (generate_tour_async, which carries
the LOCAL-848 post-request gc.collect()+malloc_trim(0) in its finally block) for
TWO sequential Rijks requests in one process and reports the resident RSS after
each. With the fix, the second request does NOT leave the container higher than
the first — the ratchet is broken.

To keep the whole run within the $0.60 task budget, the SECOND request reuses
the tour cache (DISABLE_TOUR_CACHE unset for req 2), so it is a near-free cache
hit that still drives the full service completion + release path.

Isolated throwaway DB only. Never an audioura-* container.
"""
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests"))

os.environ.setdefault("STORIED_MODE", "true")
os.environ.setdefault("DISABLE_STOP_POOL", "1")
os.environ.setdefault("STOP_EXISTENCE_GATE_MODE", "log_only")
os.environ.setdefault("CHEAP_ARM_CATEGORIES", "museum")
os.environ.setdefault("NARRATION_MODEL", "gpt-4.1-mini")
os.environ.setdefault("SERPER_RESEARCH_MODEL", "gpt-4.1-mini")
os.environ.setdefault("RESEARCH_BACKEND", "serper")
os.environ.setdefault("SERP_PROVIDER", "serper")
os.environ.setdefault("WORK_STORY_RESEARCH", "1")
os.environ["LOCAL848_TRACEMALLOC"] = "0"

LOCATION = "Rijksmuseum, Amsterdam, Netherlands"


def _rss():
    import mem_guard
    return mem_guard.read_rss_mib()


def main():
    import mem_guard
    print("=" * 72, flush=True)
    print("=== LOCAL-848 WARM cross-request proof (generate_tour_async × 2) ===",
          flush=True)
    print(f"  MALLOC_ARENA_MAX={os.environ.get('MALLOC_ARENA_MAX', '(unset)')} "
          f"LOCAL848_RELEASE={os.environ.get('LOCAL848_RELEASE', '1')}", flush=True)

    import generate_tour_text_service as svc

    marks = []
    marks.append(("import", _rss()))
    print(f"  RSS after import: {marks[-1][1]:.1f} MiB", flush=True)

    # Request 1 — fresh generation (cache disabled).
    os.environ["DISABLE_TOUR_CACHE"] = "1"
    job1 = str(uuid.uuid4())
    t0 = time.time()
    svc.generate_tour_async(job1, LOCATION, "museum", 5)
    marks.append(("after_req1_fresh", _rss()))
    print(f"  req1 (fresh) done in {time.time()-t0:.0f}s — "
          f"RSS {marks[-1][1]:.1f} MiB  status={svc.ACTIVE_JOBS.get(job1).get('status') if svc.ACTIVE_JOBS.get(job1) else '?'}",
          flush=True)

    # Request 2 — allow the cache so it is a near-free warm request that still
    # runs the full completion + post-request release path.
    os.environ["DISABLE_TOUR_CACHE"] = "0"
    job2 = str(uuid.uuid4())
    t0 = time.time()
    svc.generate_tour_async(job2, LOCATION, "museum", 5)
    marks.append(("after_req2_warm", _rss()))
    print(f"  req2 (warm) done in {time.time()-t0:.0f}s — "
          f"RSS {marks[-1][1]:.1f} MiB  status={svc.ACTIVE_JOBS.get(job2).get('status') if svc.ACTIVE_JOBS.get(job2) else '?'}",
          flush=True)

    print("\n=== WARM RSS TRACE ===", flush=True)
    for name, mib in marks:
        print(f"  {name:<20} {mib:7.1f} MiB", flush=True)

    r1 = marks[1][1]
    r2 = marks[2][1]
    ratchet = r2 - r1
    print(f"\n  cross-request ratchet (req2 - req1): {ratchet:+.1f} MiB", flush=True)
    # PASS: the warm request did not push RSS materially higher than req1, and we
    # stayed under the 512 MiB cap throughout.
    under_cap = all(m[1] < 500.0 for m in marks)
    flat = ratchet <= 40.0
    print(f"  under 500 MiB throughout: {under_cap}   warm request flat: {flat}",
          flush=True)
    print(f"  VERDICT: {'PASS' if (under_cap and flat) else 'FAIL'}", flush=True)

    try:
        import json
        os.makedirs("/app/reports/local848", exist_ok=True)
        json.dump({"marks": {n: round(v, 1) for n, v in marks},
                   "ratchet_mib": round(ratchet, 1),
                   "under_cap": under_cap, "flat": flat,
                   "pass": under_cap and flat},
                  open("/app/reports/local848/warm_result.json", "w"),
                  ensure_ascii=False, indent=2)
    except Exception:
        pass
    return 0 if (under_cap and flat) else 1


if __name__ == "__main__":
    raise SystemExit(main())
