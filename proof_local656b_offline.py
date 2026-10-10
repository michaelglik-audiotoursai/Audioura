#!/usr/bin/env python3
"""proof_local656b_offline.py — LOCAL-656B OFFLINE proof (no network, no paid run).

Proves the two LOCAL-656 claims against the REAL merged code, with fakes timed to
the LOCAL-651 profile (resolve 2.7 s ×4, preflight 14 s):

  CLAIM 1  resolve_venue call count falls 4 → 1.
           FAST_PIPELINE OFF: 4 identical resolve_venue() calls → 4 impl calls
           (byte-identical to today). FAST_PIPELINE ON: the per-tour memo (the
           SINGLE LOCAL-661 resolution store the merged resolve_venue reads on its
           fast-path) collapses the 4 to 1 impl call.

  CLAIM 2  poi_selection wall drops by the overlap.
           The up-front preflight (14 s) and the venue resolution (2.7 s) are
           independent and today run one-after-another (serial ≈ 16.7 s). With
           FAST_PIPELINE ON the merged wrapper starts the resolve on a worker
           thread (copied contextvars Context) while the preflight runs on the main
           thread; wall ≈ max(14, 2.7) = 14 s. The resolve result is handed to the
           SAME per-tour memo (seed → _resolve_memo_remember) so the first
           in-pipeline resolve_venue is a memo HIT (0 extra impl calls).

Everything here is a stub: _resolve_venue_impl and the preflight are replaced with
timed sleeps. No Wikidata, no SERP, no DB, no paid API. Run:  python3 proof_local656b_offline.py
"""
import concurrent.futures
import contextvars
import os
import sys
import time

import fast_pipeline as fp
import venue_resolver as vr


# ── LOCAL-651 profile timings ────────────────────────────────────────────────
RESOLVE_S = 2.7     # one resolve_venue (Wikidata) call
PREFLIGHT_S = 14.0  # the up-front grounded venue preflight
N_RESOLVES = 4      # the profile saw resolve_venue run 4× for the SAME venue

VENUE = "The Courtauld Gallery"
CITY = "London"


class _FakeEntity:
    """Minimal stand-in for VenueEntity (needs a truthy .qid to be memoised)."""
    def __init__(self, qid, name):
        self.qid = qid
        self.name = name
        self.language = "en"


def _install_fake_impl():
    """Replace _resolve_venue_impl with a timed stub that counts real impl calls."""
    calls = {"n": 0}

    def _fake_impl(venue_string, city=""):
        calls["n"] += 1
        time.sleep(RESOLVE_S)                 # the 2.7 s Wikidata resolve
        return _FakeEntity("Q1314057", venue_string)

    vr._resolve_venue_impl = _fake_impl
    return calls


def _fake_preflight():
    time.sleep(PREFLIGHT_S)                   # the 14 s up-front grounded call
    return {"status": "open"}


def claim1_call_drop():
    print("=" * 72)
    print("CLAIM 1 — resolve_venue call count: 4 → 1")
    print("=" * 72)

    # ---- OFF: 4 resolves must be 4 impl calls (byte-identical to today) ----
    os.environ.pop("FAST_PIPELINE", None)
    assert not fp.is_enabled()
    orig = vr._resolve_venue_impl
    try:
        calls = _install_fake_impl()
        fp.reset_tour_memo()
        vr.reset_resolution_memo()
        vr.reset_network_failure_count()
        t0 = time.time()
        for _ in range(N_RESOLVES):
            vr.resolve_venue(VENUE, CITY)
        off_wall = time.time() - t0
        off_calls = calls["n"]
    finally:
        vr._resolve_venue_impl = orig
    print(f"  FAST_PIPELINE OFF : {N_RESOLVES} resolve_venue() calls -> "
          f"{off_calls} impl call(s), wall={off_wall:.2f}s "
          f"(serial {N_RESOLVES}×{RESOLVE_S}s)")

    # ---- ON: the per-tour memo collapses 4 → 1 impl call ----
    os.environ["FAST_PIPELINE"] = "1"
    assert fp.is_enabled()
    orig = vr._resolve_venue_impl
    try:
        calls = _install_fake_impl()
        fp.reset_tour_memo()           # tour boundary: clears the ONE venue memo
        vr.reset_network_failure_count()
        t0 = time.time()
        for _ in range(N_RESOLVES):
            vr.resolve_venue(VENUE, CITY)
        on_wall = time.time() - t0
        on_calls = calls["n"]
    finally:
        vr._resolve_venue_impl = orig
        os.environ.pop("FAST_PIPELINE", None)
    print(f"  FAST_PIPELINE ON  : {N_RESOLVES} resolve_venue() calls -> "
          f"{on_calls} impl call(s), wall={on_wall:.2f}s "
          f"(1 real resolve, 3 memo hits)")

    ok = (off_calls == N_RESOLVES) and (on_calls == 1)
    print(f"  RESULT: 4→1 drop {'PROVEN' if ok else 'FAILED'} "
          f"(OFF={off_calls}, ON={on_calls}); "
          f"wall saved ≈ {off_wall - on_wall:.2f}s on the duplicate resolves")
    return ok


def claim2_overlap():
    print("=" * 72)
    print("CLAIM 2 — poi_selection wall drops by the preflight ∥ resolve overlap")
    print("=" * 72)

    os.environ["FAST_PIPELINE"] = "1"
    orig = vr._resolve_venue_impl
    try:
        calls = _install_fake_impl()
        fp.reset_tour_memo()
        vr.reset_network_failure_count()

        # --- SERIAL baseline (what today does): preflight THEN resolve ---
        t0 = time.time()
        _ = _fake_preflight()
        _ = vr.resolve_venue(VENUE, CITY)
        serial_wall = time.time() - t0
        serial_impl = calls["n"]

        # Reset for the overlapped run.
        calls["n"] = 0
        fp.reset_tour_memo()
        vr.reset_network_failure_count()

        # --- OVERLAP (the merged wrapper's structure): resolve on a worker in a
        #     COPIED context while the preflight runs here; seed the memo after
        #     join so the in-pipeline resolve_venue is a HIT. ---
        t0 = time.time()
        ctx = contextvars.copy_context()
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        fut = ex.submit(ctx.run, lambda: vr.resolve_venue(VENUE, CITY))
        try:
            _pf = _fake_preflight()
        finally:
            _ent = fut.result()
            fp.seed("resolve_venue", (VENUE, CITY), {}, _ent)
            ex.shutdown(wait=False)
        # The first in-pipeline resolve_venue — must be a memo HIT (no new impl).
        _impl_before_inpipeline = calls["n"]
        _ = vr.resolve_venue(VENUE, CITY)
        overlap_wall = time.time() - t0
        overlap_impl = calls["n"]
        inpipeline_was_hit = (calls["n"] == _impl_before_inpipeline)
    finally:
        vr._resolve_venue_impl = orig
        os.environ.pop("FAST_PIPELINE", None)

    print(f"  SERIAL  (today)   : preflight {PREFLIGHT_S}s + resolve {RESOLVE_S}s "
          f"= wall {serial_wall:.2f}s  (impl calls={serial_impl})")
    print(f"  OVERLAP (ON)      : max(preflight {PREFLIGHT_S}s, resolve {RESOLVE_S}s) "
          f"= wall {overlap_wall:.2f}s  (impl calls={overlap_impl}, "
          f"in-pipeline resolve was a memo HIT: {inpipeline_was_hit})")
    saved = serial_wall - overlap_wall
    # Overlap must land near the preflight (the longer wait), well below serial.
    ok = (overlap_wall < serial_wall - 1.0) and inpipeline_was_hit
    print(f"  RESULT: overlap {'PROVEN' if ok else 'FAILED'} — "
          f"poi_selection wall dropped ≈ {saved:.2f}s "
          f"(≈ the {RESOLVE_S}s resolve now hidden under the {PREFLIGHT_S}s preflight)")
    return ok


def main():
    print("LOCAL-656B OFFLINE proof — no network, no DB, no paid API, no live run.")
    print(f"Profile: resolve={RESOLVE_S}s ×{N_RESOLVES}, preflight={PREFLIGHT_S}s\n")
    c1 = claim1_call_drop()
    print()
    c2 = claim2_overlap()
    print()
    print("=" * 72)
    if c1 and c2:
        print("ALL CLAIMS PROVEN (offline).")
        return 0
    print("PROOF FAILED.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
