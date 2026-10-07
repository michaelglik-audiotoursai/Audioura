#!/usr/bin/env python3
"""tests/live_run_meter.py — meter + cap for ISOLATED test runs (LOCAL-613).

Why this exists
===============
On 2026-10-06 Gemini's prepaid balance went from $14.06 (~17:00) to $0 (00:28,
402) in about 11 hours. The shared ``cost_ledger`` showed only 14 ``tour_generate``
rows from the LIVE stack in that window, costing $1.05. The other ~$13 was burned
by about 20 Kiro tasks' ISOLATED live runs (``docker run --rm --name localNNN-gen
…``) — runs that wrote NO ledger rows and left NO Gemini totals, so when Michael
asked "how many tours did we run during testing to burn $14?" nobody could answer.

This module is the fix. Every isolated live-run harness (``run_local*_live.sh`` /
``run_local*_container.py`` and every future one) uses it to do two things:

  1. **Meter.** Accumulate the run's spend per provider and, at the end, write ONE
     ``cost_ledger`` row with ``user_id = 'TEST-<LOCAL-NNN>'``, ``description =
     'test run'`` and the LOCAL-609 breakdown fields:

         openai            — OpenAI (gpt-4o / gpt-4o-mini) dollars
         gemini_grounding  — grounded Gemini search-query dollars, carrying the
                             request and query COUNTS behind the figure
         gemini_tokens     — Gemini token dollars (ungrounded model usage)
         serper            — Serper search dollars
         preflight         — venue-preflight grounding dollars (a subset of the
                             grounding spend, surfaced on its own so a run that
                             spends only on preflight is still legible)

     A ``TEST-*`` user_id is how ``cost_report_window.py`` separates test spend
     from live users when it answers "where did the money go?".

  2. **Cap.** Enforce a hard per-task spend cap, ``TEST_GEMINI_MAX_USD`` (default
     **$1.00**), AT THE GROUNDING COUNTER (story_leads). The cap applies to ALL
     PROVIDERS COMBINED — the moment the run's combined running spend (openai +
     gemini grounding + gemini tokens + serper + preflight) reaches the cap, the
     next grounded Gemini step raises ``story_leads.TestRunCapExceeded`` and the
     run stops. A task file sets its own, lower cap by exporting the env var.

Usage (container-side python harness)
=====================================
    from live_run_meter import LiveRunMeter   # tests/ is on sys.path

    meter = LiveRunMeter("LOCAL-613")   # reads TEST_GEMINI_MAX_USD; installs cap
    try:
        import generate_tour_text as g
        text, _out, _coords = g.generate_tour_text(location, kind, out, stops)
        meter.add_generation(g)         # read _LAST_GENERATION_COST + counters
    finally:
        row_id = meter.record()         # ONE ledger row, description='test run'
        meter.uninstall()
    print(meter.summary())

The meter never raises on a DB problem (metering must not break a run); it logs
and returns None from ``record()``. The CAP, by contrast, is a hard stop and does
raise — that is the whole point.
"""
import logging
import os
import sys

logger = logging.getLogger(__name__)

# tests/ lives one level under the repo root; make repo-root modules importable
# whether this is imported as ``live_run_meter`` (tests/ on sys.path) or
# ``tests.live_run_meter``.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_HERE, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from cost_rates import (  # noqa: E402
    GROUNDING_COST_PER_QUERY,
    SERPER_COST_PER_QUERY,
    grounding_query_cost,
)

DEFAULT_TEST_GEMINI_MAX_USD = 1.00
TEST_RUN_DESCRIPTION = "test run"

# The LOCAL-609 breakdown fields, in the order they are reported. Kept as a
# module constant so the helper, the tests and the report all agree.
BREAKDOWN_FIELDS = (
    "openai",
    "gemini_grounding",
    "gemini_tokens",
    "serper",
    "preflight",
)


def resolve_cap_usd(explicit=None):
    """Resolve the per-task combined-spend cap in USD.

    Precedence: an explicit argument wins; else ``TEST_GEMINI_MAX_USD`` from the
    environment; else the $1.00 default. A malformed env value falls back to the
    default rather than disabling the cap (fail safe, not fail open)."""
    if explicit is not None:
        return float(explicit)
    raw = os.environ.get("TEST_GEMINI_MAX_USD")
    if raw is None or str(raw).strip() == "":
        return DEFAULT_TEST_GEMINI_MAX_USD
    try:
        return float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "[LIVE_RUN_METER] TEST_GEMINI_MAX_USD=%r is not a number — "
            "falling back to default $%.2f", raw, DEFAULT_TEST_GEMINI_MAX_USD)
        return DEFAULT_TEST_GEMINI_MAX_USD


def _normalise_task_id(task_id):
    """Turn ``LOCAL-613`` / ``local613`` / ``613`` into the ledger user_id
    ``TEST-LOCAL-613``. Idempotent if already ``TEST-…`` prefixed."""
    t = str(task_id).strip()
    if t.upper().startswith("TEST-"):
        return "TEST-" + t[5:]
    t = t.upper()
    if t.isdigit():
        t = "LOCAL-" + t
    elif t.startswith("LOCAL") and not t.startswith("LOCAL-"):
        t = "LOCAL-" + t[len("LOCAL"):]
    return "TEST-" + t


class LiveRunMeter:
    """Accumulate an isolated run's spend, enforce the per-task cap at the
    grounding counter, and write ONE ``cost_ledger`` row at the end.

    Parameters
    ----------
    task_id:
        The task, e.g. ``"LOCAL-613"``. Stored as ``user_id='TEST-LOCAL-613'``.
    cap_usd:
        Optional explicit cap override. Normally omitted so ``TEST_GEMINI_MAX_USD``
        (default $1.00) is used.
    job_id:
        Optional correlation id written to the ledger row.
    install_cap:
        When True (default), register the cap guard in ``story_leads`` on
        construction, so a grounded call raises the instant combined spend reaches
        the cap. Set False only in a unit test that drives the accumulators by hand.
    """

    def __init__(self, task_id, cap_usd=None, job_id=None, install_cap=True):
        self.task_id = task_id
        self.user_id = _normalise_task_id(task_id)
        self.cap_usd = resolve_cap_usd(cap_usd)
        self.job_id = job_id

        # Per-provider dollar accumulators (the LOCAL-609 breakdown).
        self.openai_usd = 0.0
        self.gemini_grounding_usd = 0.0
        self.gemini_tokens_usd = 0.0
        self.serper_usd = 0.0
        self.preflight_usd = 0.0

        # Counts behind the grounding dollar figure.
        self.gemini_grounding_requests = 0
        self.gemini_grounding_queries = 0

        self._capped = False       # True once the cap guard has fired
        self._recorded = False     # guards against a double ledger write
        self._installed = False

        if install_cap:
            self.install_cap()

    # ── cap enforcement ──────────────────────────────────────────────────────
    def combined_spend_usd(self):
        """The run's spend across ALL providers combined — the figure the cap is
        measured against. Includes the live grounding spend counted in
        story_leads since the last reset, so the guard sees the query that is
        about to push the run over the line.

        preflight is NOT added here: a venue preflight is itself a grounded Gemini
        call, so its queries are already inside the grounding counter. The
        ``preflight`` field is a labelled SUBSET of gemini_grounding surfaced for
        visibility — adding it again would double-count."""
        live_grounding = self._live_grounding_usd()
        # Use the larger of the live counter and the amount already folded into
        # our accumulator, so neither double-counts nor under-counts across a
        # mid-run add_generation().
        grounding = max(self.gemini_grounding_usd, live_grounding)
        return (self.openai_usd + grounding + self.gemini_tokens_usd
                + self.serper_usd)

    def _live_grounding_usd(self):
        """Dollar value of grounded queries counted in story_leads right now."""
        try:
            import story_leads
            return grounding_query_cost(story_leads.get_grounding_queries())
        except Exception:
            return 0.0

    def _cap_guard(self):
        """Installed into story_leads: raise TestRunCapExceeded when the combined
        running spend has reached the cap. Called by the grounding counter right
        before a grounded request is issued and right after a response's queries
        are counted."""
        spend = self.combined_spend_usd()
        if spend >= self.cap_usd:
            self._capped = True
            import story_leads
            raise story_leads.TestRunCapExceeded(
                f"[LOCAL-613] {self.user_id}: isolated-run spend "
                f"${spend:.4f} >= cap ${self.cap_usd:.2f} "
                f"(TEST_GEMINI_MAX_USD, all providers combined) — stopping run "
                f"before the next grounded Gemini query is issued.")

    def install_cap(self):
        """Register the cap guard in story_leads. Idempotent."""
        import story_leads
        story_leads.set_grounding_cap_callback(self._cap_guard)
        self._installed = True

    def uninstall(self):
        """Remove the cap guard so later, unrelated work in the same process is
        not affected. Always call in a finally block."""
        try:
            import story_leads
            story_leads.set_grounding_cap_callback(None)
        except Exception:
            pass
        self._installed = False

    @property
    def capped(self):
        return self._capped

    # ── accumulation ─────────────────────────────────────────────────────────
    def add_openai(self, usd):
        self.openai_usd += max(0.0, float(usd or 0.0))

    def add_gemini_tokens(self, usd):
        self.gemini_tokens_usd += max(0.0, float(usd or 0.0))

    def add_serper(self, usd=None, queries=None):
        """Add Serper spend, either as dollars or as a query count priced here."""
        if usd is not None:
            self.serper_usd += max(0.0, float(usd))
        if queries is not None:
            self.serper_usd += max(0, int(queries)) * SERPER_COST_PER_QUERY

    def add_grounding(self, requests=0, queries=0, preflight_queries=0):
        """Add grounded-Gemini spend from measured counts.

        requests / queries   — grounded request and search-query counts for the
                               whole run (queries drive the dollar figure).
        preflight_queries    — of those queries, how many were the venue
                               preflight; surfaced in the ``preflight`` field too.
        """
        self.gemini_grounding_requests += max(0, int(requests))
        q = max(0, int(queries))
        self.gemini_grounding_queries += q
        self.gemini_grounding_usd += grounding_query_cost(q)
        if preflight_queries:
            self.preflight_usd += grounding_query_cost(max(0, int(preflight_queries)))

    def add_preflight_usd(self, usd):
        self.preflight_usd += max(0.0, float(usd or 0.0))

    def add_generation(self, gen_module=None, preflight_queries=0):
        """Fold in the LAST generation's cost from generate_tour_text.

        Reads ``gen_module._LAST_GENERATION_COST`` (``breakdown`` → llm/tts/search)
        for the OpenAI and Serper figures, and the live story_leads grounding
        counters (requests + queries) for the Gemini grounding figure. TTS is not
        a Gemini/OpenAI provider line in the LOCAL-609 breakdown, so it is left
        out of the capped total; the dollar lines reported are exactly the
        provider lines the ticket names.

        ``preflight_queries`` lets a harness that measured the preflight in
        isolation attribute that share to the ``preflight`` field.
        """
        if gen_module is None:
            import generate_tour_text as gen_module  # noqa: F811

        cost = dict(getattr(gen_module, "_LAST_GENERATION_COST", {}) or {})
        breakdown = dict(cost.get("breakdown", {}) or {})
        # llm == OpenAI dollars; search == Serper dollars (both named by LOCAL-60).
        self.add_openai(breakdown.get("llm", 0.0))
        self.serper_usd += max(0.0, float(breakdown.get("search", 0.0) or 0.0))

        # Grounded Gemini spend from the live counters (the invoice unit).
        try:
            import story_leads
            self.gemini_grounding_requests = max(
                self.gemini_grounding_requests, story_leads.get_grounding_requests())
            q = story_leads.get_grounding_queries()
            self.gemini_grounding_queries = max(self.gemini_grounding_queries, q)
            self.gemini_grounding_usd = max(
                self.gemini_grounding_usd, grounding_query_cost(q))
        except Exception as e:
            logger.warning("[LIVE_RUN_METER] could not read grounding counters: %s", e)

        if preflight_queries:
            self.preflight_usd += grounding_query_cost(max(0, int(preflight_queries)))
        return self

    # ── reporting / recording ────────────────────────────────────────────────
    def breakdown(self):
        """The LOCAL-609 breakdown dict written to the ledger row."""
        return {
            "openai": round(self.openai_usd, 6),
            "gemini_grounding": {
                "usd": round(self.gemini_grounding_usd, 6),
                "requests": self.gemini_grounding_requests,
                "queries": self.gemini_grounding_queries,
            },
            "gemini_tokens": round(self.gemini_tokens_usd, 6),
            "serper": round(self.serper_usd, 6),
            "preflight": round(self.preflight_usd, 6),
            "capped": self._capped,
            "cap_usd": round(self.cap_usd, 6),
        }

    def total_usd(self):
        """Total our-cost for the ledger row. Equals the combined provider spend
        (the capped figure) — grounding counted once, preflight NOT re-added
        (it is a subset of grounding)."""
        grounding = max(self.gemini_grounding_usd, self._live_grounding_usd())
        return round(self.openai_usd + grounding + self.gemini_tokens_usd
                     + self.serper_usd, 6)

    def record(self, operation_type="tour_generate", cache_hit=False):
        """Write ONE cost_ledger row for this run and return its id (or None).

        user_id = 'TEST-<LOCAL-NNN>', description = 'test run', breakdown = the
        LOCAL-609 fields. Never raises: a metering failure must not break the run
        (the whole bug was runs that produced no row — a crash here would recreate
        it). Idempotent: a second call is a no-op returning None."""
        if self._recorded:
            logger.info("[LIVE_RUN_METER] record() already called for %s", self.user_id)
            return None
        self._recorded = True
        try:
            from cost_meter import record_operation
            return record_operation(
                operation_type=operation_type,
                our_cost_usd=self.total_usd(),
                cache_hit=cache_hit,
                user_id=self.user_id,
                job_id=self.job_id,
                breakdown=self.breakdown(),
                description=TEST_RUN_DESCRIPTION,
            )
        except Exception as e:  # pragma: no cover - defensive
            logger.error("[LIVE_RUN_METER] failed to record ledger row: %s", e)
            print(f"[LIVE_RUN_METER] WARNING: could not record ledger row: {e}")
            return None

    def summary(self):
        b = self.breakdown()
        g = b["gemini_grounding"]
        lines = [
            f"[LIVE_RUN_METER] {self.user_id}  (cap ${self.cap_usd:.2f}, "
            f"all providers combined){'  CAP HIT' if self._capped else ''}",
            f"  openai            ${b['openai']:.4f}",
            f"  gemini_grounding  ${g['usd']:.4f}  "
            f"(requests={g['requests']}, queries={g['queries']})",
            f"  gemini_tokens     ${b['gemini_tokens']:.4f}",
            f"  serper            ${b['serper']:.4f}",
            f"  preflight         ${b['preflight']:.4f}",
            f"  TOTAL             ${self.total_usd():.4f}   description='{TEST_RUN_DESCRIPTION}'",
        ]
        return "\n".join(lines)

    # Context-manager sugar: `with LiveRunMeter("LOCAL-613") as m: ...` records
    # and uninstalls on exit, even on exception (incl. the cap raise).
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.record()
        finally:
            self.uninstall()
        return False  # never suppress — a cap raise must propagate


def install_grounding_cap(task_id, cap_usd=None, job_id=None):
    """Convenience: build a LiveRunMeter with the cap installed and return it.

    Equivalent to ``LiveRunMeter(task_id, cap_usd, job_id)`` — named so a harness
    reads intent at the call site: 'install the grounding cap for this task'."""
    return LiveRunMeter(task_id, cap_usd=cap_usd, job_id=job_id, install_cap=True)


def auto_meter(task_id, cap_usd=None, job_id=None):
    """One-line opt-in for a harness: install the cap now AND register an atexit
    hook that reads the LAST generation's cost and writes the ``TEST-*`` ledger
    row when the process ends — even if the run is stopped by the cap or any other
    exception.

    This is the whole integration a harness needs:

        import live_run_meter
        live_run_meter.auto_meter("LOCAL-613")   # cap installed; row on exit
        ...call generate_tour_text as usual...

    The atexit hook calls ``add_generation()`` (reading
    ``generate_tour_text._LAST_GENERATION_COST`` and the live grounding counters)
    unless the harness already recorded by hand. Returns the LiveRunMeter so a
    caller that wants the richer API (per-provider adds, summary()) still can."""
    import atexit

    meter = LiveRunMeter(task_id, cap_usd=cap_usd, job_id=job_id, install_cap=True)

    def _finalize():
        if meter._recorded:
            meter.uninstall()
            return
        try:
            import generate_tour_text  # noqa: F401
            meter.add_generation(generate_tour_text)
        except Exception:
            pass  # no generation happened (or module unavailable) — still record
        try:
            row_id = meter.record()
            print(meter.summary())
            if row_id:
                print(f"[LIVE_RUN_METER] cost_ledger row {row_id} "
                      f"(user_id={meter.user_id}, description='{TEST_RUN_DESCRIPTION}')")
        finally:
            meter.uninstall()

    atexit.register(_finalize)
    return meter
