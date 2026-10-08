"""external_lookup_budget.py — LOCAL-622: a per-tour budget for external lookups.

Why this exists
---------------
D635 measured a tour that FINISHED but was thrown away. The generator spent
663.4s in the `external_lookups` phase, most of it waiting on per-stop
Overpass/OSM queries that returned HTTP 504 ("[OSM-VENUE] Overpass HTTP 504 for
'Toter Uhu'"). Each stop's doomed query stacked up to an 11-minute stall; the
orchestrator's own 20-minute ceiling then abandoned a tour the generator was
still successfully producing. The listener paid $0.60 for a discarded tour.

External lookups — OSM/Overpass venue facts, Wikidata enrichment, venue site
fetches — are OPTIONAL enrichments. A tour must never stall waiting on them.
This module gives one tour a shared time budget. Once the budget is spent,
further optional lookups are skipped (and the skip is logged), so the tour
proceeds on what it already has instead of waiting on an API that cannot answer.

Design
------
* Per-call hard timeout: callers use a short timeout (e.g. 10s) so no single
  request can hang the phase.
* At most one retry with backoff: the caller decides; the budget just tracks
  the wall time spent so retries also count against it.
* Per-tour budget (default 120s): a single :class:`LookupBudget` is created at
  the start of the external-lookups phase and shared by every optional lookup.
  When :meth:`remaining` reaches zero, :meth:`should_skip` returns True and the
  caller skips the lookup entirely.

The budget is deliberately simple and has NO network dependency, so it can be
unit-tested against stubbed slow endpoints with no live traffic.
"""

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Default per-tour budget for ALL optional external lookups combined.
# D635 target: external_lookups at or under ~150s on the same venue; a 120s
# budget leaves headroom for the one in-flight call that was already started
# when the budget ran out.
DEFAULT_LOOKUP_BUDGET_SECONDS = 120.0

# Default per-call hard timeout for a single optional external request.
DEFAULT_CALL_TIMEOUT_SECONDS = 10.0

# Default number of retries (in ADDITION to the first attempt) for a single
# optional external request. "At most one retry" per the LOCAL-622 contract.
DEFAULT_MAX_RETRIES = 1


class LookupBudget:
    """A shared, tour-scoped time budget for optional external lookups.

    Create ONE per tour at the start of the external-lookups phase and pass it
    to every optional lookup. The budget is thread-safe: the generator fans
    some lookups out across threads, and they must all draw from the same pool.

    Example::

        budget = LookupBudget(total_seconds=120)
        for stop in stops:
            if budget.should_skip("osm", context=stop.name):
                continue
            with budget.track("osm", context=stop.name):
                facts = fetch_osm_venue_facts(stop.name, city, budget=budget)
    """

    def __init__(
        self,
        total_seconds: float = DEFAULT_LOOKUP_BUDGET_SECONDS,
        call_timeout: float = DEFAULT_CALL_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        self.total_seconds = float(total_seconds)
        self.call_timeout = float(call_timeout)
        self.max_retries = int(max_retries)
        self._spent = 0.0
        self._lock = threading.Lock()
        self._skipped_count = 0
        self._exhausted_logged = False

    # -- accounting ---------------------------------------------------------

    def record(self, seconds: float) -> None:
        """Record wall-clock seconds spent on an external lookup."""
        if seconds <= 0:
            return
        with self._lock:
            self._spent += float(seconds)

    @property
    def spent(self) -> float:
        with self._lock:
            return self._spent

    def remaining(self) -> float:
        """Seconds left in the budget (never negative)."""
        with self._lock:
            return max(0.0, self.total_seconds - self._spent)

    @property
    def skipped_count(self) -> int:
        with self._lock:
            return self._skipped_count

    def is_exhausted(self) -> bool:
        return self.remaining() <= 0.0

    # -- decisions ----------------------------------------------------------

    def should_skip(self, kind: str = "lookup", context: str = "") -> bool:
        """Return True if the budget is spent and this lookup must be skipped.

        Logs the FIRST exhaustion once at WARNING, then counts subsequent skips
        so a 50-stop tour does not produce 50 identical warnings.
        """
        if not self.is_exhausted():
            return False
        with self._lock:
            self._skipped_count += 1
            first = not self._exhausted_logged
            self._exhausted_logged = True
            skipped = self._skipped_count
            spent = self._spent
        if first:
            logger.warning(
                "[LOOKUP-BUDGET] External-lookup budget exhausted after "
                "%.1fs (limit %.0fs). Skipping optional %s lookup for %r and "
                "any further optional lookups this tour.",
                spent, self.total_seconds, kind, context,
            )
        else:
            logger.info(
                "[LOOKUP-BUDGET] Skipped optional %s lookup for %r "
                "(budget exhausted; %d skipped so far).",
                kind, context, skipped,
            )
        return True

    def effective_timeout(self) -> float:
        """Per-call timeout, clamped so one call cannot overrun the budget.

        Never larger than the configured ``call_timeout`` and never larger than
        the time still remaining in the budget.
        """
        return max(0.0, min(self.call_timeout, self.remaining()))

    # -- context manager ----------------------------------------------------

    def track(self, kind: str = "lookup", context: str = ""):
        """Context manager that records the wall time of the enclosed lookup.

        Time is recorded even if the enclosed block raises, so a request that
        times out or errors still counts against the budget.
        """
        return _BudgetTracker(self, kind, context)

    def summary(self) -> str:
        with self._lock:
            return (
                f"spent={self._spent:.1f}s / limit={self.total_seconds:.0f}s, "
                f"skipped={self._skipped_count}"
            )


class _BudgetTracker:
    """Context manager returned by :meth:`LookupBudget.track`."""

    def __init__(self, budget: LookupBudget, kind: str, context: str):
        self._budget = budget
        self._kind = kind
        self._context = context
        self._start = 0.0

    def __enter__(self):
        self._start = time.monotonic()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.monotonic() - self._start
        self._budget.record(elapsed)
        # Never suppress exceptions — the caller handles its own errors.
        return False


def run_with_budget(
    budget: Optional[LookupBudget],
    func,
    *args,
    kind: str = "lookup",
    context: str = "",
    **kwargs,
):
    """Run ``func`` under the budget, returning ``(ran, result)``.

    * If ``budget`` is None, the function always runs (no budget enforcement).
    * If the budget is exhausted, the function is NOT run and ``(False, None)``
      is returned.
    * Otherwise the function runs, its wall time is charged to the budget, and
      ``(True, result)`` is returned.

    This is a convenience wrapper for the common call shape; callers that need
    finer control can use :meth:`LookupBudget.should_skip` and
    :meth:`LookupBudget.track` directly.
    """
    if budget is None:
        return True, func(*args, **kwargs)
    if budget.should_skip(kind, context):
        return False, None
    with budget.track(kind, context):
        return True, func(*args, **kwargs)
