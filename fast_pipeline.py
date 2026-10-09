"""fast_pipeline.py — LOCAL-651: overlap the INDEPENDENT waits (flag FAST_PIPELINE).

Behind ``FAST_PIPELINE=1`` (default OFF). When OFF, ``is_enabled()`` returns False
and every call site keeps its existing serial code path, so behaviour is
byte-identical to today — nothing in this module runs.

The profile (SUBMISSION_LOCAL-651.md, Step 1) found the pipeline spends long
stretches issuing INDEPENDENT network/LLM calls one after another:

  * poi_selection deterministic fill: venue_preflight, resolve_venue (Wikidata),
    fetch_osm_venue_facts — independent inputs, run sequentially (~37s on
    Courtauld);
  * external_lookups: the per-stop lookups run in a serial loop.

This module provides ONE primitive — ``run_parallel`` — that runs a set of
*independent* zero-argument callables concurrently and returns their results IN
THE SAME ORDER as submitted, re-raising the first exception exactly as the serial
code would have raised it. It is deliberately tiny: the only behaviour change ON
vs OFF is WHEN the identical calls are issued, never WHICH calls or in what order
their results are consumed.

THREAD-SAFETY. The callables issue the same network/LLM calls the serial path
issues. Shared mutable state they touch:
  * the paid-API meter (``_meter/paid_api_meter.py``) — already guarded by its own
    ``threading.Lock`` around the log write and uses a short-lived DB connection
    per call; concurrent calls are safe.
  * the ``[TIMING-SUB]`` SubTimer — ``phase_timer.SubTimer`` accumulates under a
    lock (see test_local651_sub_timer).
  * venue/OSM caches — module-level dict caches guarded in their own modules.
``run_parallel`` adds no shared state of its own; each job owns its inputs and its
return value. Callers must not have two jobs write the same dict key (they don't:
each job returns its value and the caller assembles results after join).
"""
from __future__ import annotations

import concurrent.futures
import os
from typing import Callable, List, Optional, TypeVar

T = TypeVar("T")

FLAG_ENV = "FAST_PIPELINE"

# Pool ceiling for an overlap group. The groups we overlap are small (3-5
# independent calls, or one call per stop for a 3-8 stop tour); a modest cap keeps
# us well under the paid-API providers' concurrency and the box's resources.
DEFAULT_MAX_WORKERS = int(os.environ.get("FAST_PIPELINE_MAX_WORKERS", "6"))


def is_enabled() -> bool:
    """True only when FAST_PIPELINE=1 is explicitly set. Default OFF."""
    return os.environ.get(FLAG_ENV, "") == "1"


def run_parallel(jobs: List[Callable[[], T]],
                 max_workers: Optional[int] = None,
                 label: str = "") -> List[T]:
    """Run independent zero-arg callables concurrently; return results in order.

    * Results are returned in the SAME order as ``jobs`` (so the caller consumes
      them exactly as it would the serial results).
    * The FIRST exception raised by any job is re-raised to the caller after all
      jobs settle — matching "the same calls must happen"; a job that would have
      raised serially still raises here.
    * With 0 or 1 jobs, or when the flag is OFF, the jobs are simply run inline in
      order (no thread pool) so there is no behavioural difference.

    This function does NOT check the flag itself — call sites decide whether to use
    it, so the OFF path never touches a thread pool.
    """
    if not jobs:
        return []
    if len(jobs) == 1:
        return [jobs[0]()]

    workers = max_workers or min(DEFAULT_MAX_WORKERS, len(jobs))
    results: List[Optional[T]] = [None] * len(jobs)
    first_exc: List[Optional[BaseException]] = [None]

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        future_to_idx = {ex.submit(job): i for i, job in enumerate(jobs)}
        for fut in concurrent.futures.as_completed(future_to_idx):
            idx = future_to_idx[fut]
            try:
                results[idx] = fut.result()
            except BaseException as e:  # noqa: BLE001 - preserve + re-raise below
                if first_exc[0] is None:
                    first_exc[0] = e

    if first_exc[0] is not None:
        raise first_exc[0]
    return results  # type: ignore[return-value]
