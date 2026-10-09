"""
Per-tour cost accumulator — the single place every billable API call lands.
=============================================================================
[LOCAL-562]

Why this exists
---------------
Before LOCAL-562 the per-tour `total_cost` was summed by hand at ~5 call sites
inside ``generate_tour_text.generate_tour_text`` (``total_cost += _tour_llm_cost(...)``).
But the recordings from LOCAL-560 show that a single Chart House tour makes 137
OpenAI calls across 18 call sites in 7 modules (gates, extractors, writers). The
other ~130 calls — story_gate, stop_specificity_gate, unglossed_reference_gate,
fact_extractor, restaurant_practicals, spine_generator, stop_knowledge_fallback,
and the openai-client path in story_element_extractor — never touched
``total_cost``. The ledger therefore undercounted OpenAI by ~3x, and Michael's
per-tour price formula rested on that understated number.

The fix is to count at ONE choke point (the HTTP call itself, see
``openai_cost_wrapper.py``) and add every call's ``usage × rate`` into *this*
accumulator. The ledger then reads the accumulator instead of a hand-summed total.

Why per-tour (not a process global)
-----------------------------------
The generator runs tours concurrently (ThreadPoolExecutor, and the service runs
multiple jobs). A process-global counter cross-contaminates: the LOCAL-550
grounding numbers rose monotonically across parallel runs for exactly this
reason (D-note). So the accumulator is scoped with a ``contextvars.ContextVar``:
each tour opens its own accumulator with ``tour_scope()`` (a context manager),
and every call made *within that dynamic scope* — including inside worker threads
that inherit the context — lands in that tour's accumulator and no other.

ContextVar + threads
--------------------
``contextvars`` are copied into a thread only when the thread is started via
``contextvars.Context.run`` (which ``ThreadPoolExecutor`` does NOT do by default).
To make the common ``ThreadPoolExecutor`` case correct we expose
``current_accumulator()`` which falls back to a thread-inherited reference set by
``tour_scope`` when a child thread was spawned under a scope. For the robust path,
threads that must share a parent tour's accumulator should be submitted via
``run_in_tour_context`` (a thin wrapper that re-binds the ContextVar inside the
child). Tests cover both.

Keys
----
Breakdown keys are fixed by the ledger contract: ``llm``, ``grounding``,
``search``, ``tts``. Each is a running USD total plus a small amount of metadata
(call counts, tokens, characters) for debugging.

This module performs NO network I/O and imports no heavy deps. It only knows how
to hold numbers. Pricing lives in ``cost_rates.py``; the wrapper that calls into
here lives in ``openai_cost_wrapper.py``.
"""

from __future__ import annotations

import contextlib
import contextvars
import threading
from typing import Optional

import cost_rates

__all__ = [
    "CostAccumulator",
    "tour_scope",
    "preflight_scope",
    "current_accumulator",
    "add_llm_usage",
    "add_grounding_requests",
    "add_gemini_tokens",
    "add_gemini_call",
    "add_preflight",
    "add_search_queries",
    "add_tts_characters",
    "run_in_tour_context",
    "install_executor_context_propagation",
    "uninstall_executor_context_propagation",
]


class CostAccumulator:
    """A thread-safe running total of one tour's billable API cost.

    Instances are cheap and isolated: one per tour. All mutation is guarded by a
    lock because a single tour fans work out across worker threads (per-stop
    description calls, gate calls) that all share the one accumulator.
    """

    __slots__ = (
        "_lock", "job_id", "llm", "grounding", "search", "tts",
        # [LOCAL-609] new provider-split buckets
        "llm_by_model", "gemini_tokens", "preflight",
    )

    def __init__(self, job_id: Optional[str] = None):
        self._lock = threading.Lock()
        self.job_id = job_id
        # Each bucket: usd plus type-appropriate counters.
        self.llm = {"usd": 0.0, "calls": 0, "input_tokens": 0, "output_tokens": 0}
        self.grounding = {"usd": 0.0, "requests": 0, "queries": 0}
        self.search = {"usd": 0.0, "queries": 0}
        self.tts = {"usd": 0.0, "characters": 0, "calls": 0}
        # [LOCAL-609] OpenAI usage split per model, so a tour_generate row can show
        # gpt-4o vs gpt-4o-mini separately. Keyed by model string on the wire.
        self.llm_by_model: dict = {}
        # [LOCAL-609] Gemini Flash TOKEN channel (separate from the grounding
        # search-query channel). usageMetadata prompt/candidates token counts.
        self.gemini_tokens = {"usd": 0.0, "calls": 0, "input_tokens": 0, "output_tokens": 0}
        # [LOCAL-609] LOCAL-603 venue preflight — reported on its own line. Holds
        # the preflight call's grounding queries and Flash tokens and their $.
        self.preflight = {"usd": 0.0, "calls": 0, "queries": 0,
                          "input_tokens": 0, "output_tokens": 0}

    # ---- mutation ---------------------------------------------------------
    def add_llm(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Price one OpenAI chat-completion call and add it. Returns the call's USD cost.

        Priced with cost_rates.llm_cost (the one rate table). ``model`` should be
        the model string actually on the wire — the recorder's ``actual_model``
        when available, else the requested ``model`` — so a gpt-4o call is never
        priced at mini rates and vice versa.
        """
        input_tokens = int(input_tokens or 0)
        output_tokens = int(output_tokens or 0)
        cost = cost_rates.llm_cost(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model or "gpt-3.5-turbo",
        )
        with self._lock:
            self.llm["usd"] += cost
            self.llm["calls"] += 1
            self.llm["input_tokens"] += input_tokens
            self.llm["output_tokens"] += output_tokens
            # [LOCAL-609] per-model split
            _mkey = model or "gpt-3.5-turbo"
            _m = self.llm_by_model.get(_mkey)
            if _m is None:
                _m = {"usd": 0.0, "calls": 0, "input_tokens": 0, "output_tokens": 0}
                self.llm_by_model[_mkey] = _m
            _m["usd"] += cost
            _m["calls"] += 1
            _m["input_tokens"] += input_tokens
            _m["output_tokens"] += output_tokens
        return cost

    def add_grounding(self, num_requests: int = 1, num_queries: int = 0) -> float:
        """Add grounded Google-Search Gemini usage.

        [LOCAL-609] The dollar figure follows the SEARCH QUERIES (the unit Google
        invoices — "Generate content search query gemini 3 paid"), priced via
        cost_rates.grounding_query_cost. ``num_requests`` is tracked only to
        enforce the LOCAL-594 "<= 1 grounded request per stop" cap; it does not
        drive the dollars. When ``num_queries`` is 0 the request searched nothing
        and costs $0.00 on this channel — exactly what Google bills.

        Backwards-compat: callers that pass only ``num_requests`` (the pre-609
        signature) still work; with no query count they add 0 dollars (which is
        correct — a request that reported no webSearchQueries is free here).
        """
        num_requests = int(num_requests or 0)
        num_queries = int(num_queries or 0)
        # [LEAD 2026-10-09] bill per search-enabled request (price card r4); queries only as a floor
        cost = max(num_requests * getattr(cost_rates, 'GROUNDED_REQUEST_COST', 0.035),
                   cost_rates.grounding_query_cost(num_queries))
        with self._lock:
            self.grounding["usd"] += cost
            self.grounding["requests"] += num_requests
            self.grounding["queries"] += num_queries
        return cost

    def add_gemini_tokens(self, input_tokens: int = 0, output_tokens: int = 0) -> float:
        """[LOCAL-609] Add one Gemini Flash call's TOKEN usage (the token channel,
        separate from the grounding search-query channel). Priced with
        cost_rates.gemini_tokens_cost. Before LOCAL-609 this spend was metered
        nowhere, so the ledger silently omitted it."""
        input_tokens = int(input_tokens or 0)
        output_tokens = int(output_tokens or 0)
        cost = cost_rates.gemini_tokens_cost(input_tokens, output_tokens)
        with self._lock:
            self.gemini_tokens["usd"] += cost
            self.gemini_tokens["calls"] += 1
            self.gemini_tokens["input_tokens"] += input_tokens
            self.gemini_tokens["output_tokens"] += output_tokens
        return cost

    def add_preflight(self, num_queries: int = 0, input_tokens: int = 0,
                      output_tokens: int = 0) -> float:
        """[LOCAL-609] Add the LOCAL-603 venue preflight call, reported on its own
        ledger line. Its dollars are grounding search queries + Flash tokens
        (cost_rates.preflight_cost); no new rate. On a cache hit the preflight
        does not run, so this stays $0.00 / 0 calls and the report says so."""
        num_queries = int(num_queries or 0)
        input_tokens = int(input_tokens or 0)
        output_tokens = int(output_tokens or 0)
        cost = cost_rates.preflight_cost(num_queries, input_tokens, output_tokens)
        with self._lock:
            self.preflight["usd"] += cost
            self.preflight["calls"] += 1
            self.preflight["queries"] += num_queries
            self.preflight["input_tokens"] += input_tokens
            self.preflight["output_tokens"] += output_tokens
        return cost

    def add_search(self, num_queries: int = 1) -> float:
        """Add ``num_queries`` Serper search queries."""
        num_queries = int(num_queries or 0)
        cost = cost_rates.search_cost(num_queries)
        with self._lock:
            self.search["usd"] += cost
            self.search["queries"] += num_queries
        return cost

    def add_tts(self, char_count: int, engine: str = "neural") -> float:
        """Add one Polly synthesis call of ``char_count`` characters.

        Default engine is 'neural' — the voices the pipeline actually uses
        (Joanna, Matthew, Amy, Brian) are neural (see polly_tts_service.py). TTS
        showed $0.00 in every ledger row before LOCAL-562 because nothing fed it.
        """
        char_count = int(char_count or 0)
        cost = cost_rates.tts_cost(char_count, engine=engine)
        with self._lock:
            self.tts["usd"] += cost
            self.tts["characters"] += char_count
            self.tts["calls"] += 1
            # [LOCAL-609] remember the engine for the breakdown's engine field.
            self.tts["engine"] = engine
        return cost

    # ---- read-out ---------------------------------------------------------
    def total_usd(self) -> float:
        with self._lock:
            return self._total_usd_locked()

    def _total_usd_locked(self) -> float:
        """Sum of every billable channel. Caller must hold the lock.
        [LOCAL-609] includes gemini_tokens and preflight alongside the original
        llm/grounding/search/tts channels."""
        return (
            self.llm["usd"] + self.grounding["usd"] + self.search["usd"]
            + self.tts["usd"] + self.gemini_tokens["usd"] + self.preflight["usd"]
        )

    def breakdown(self) -> dict:
        """The original four-key breakdown (kept for backwards compatibility with
        pre-LOCAL-609 callers/tests that read llm/grounding/search/tts)."""
        with self._lock:
            return {
                "llm": self.llm["usd"],
                "grounding": self.grounding["usd"],
                "search": self.search["usd"],
                "tts": self.tts["usd"],
            }

    def provider_breakdown(self) -> dict:
        """[LOCAL-609] The per-provider breakdown Michael asked for — every channel
        with its dollars AND its unit counts, counted (not estimated). This is the
        dict written into the tour_generate ledger row's `breakdown`.

        Keys (ticket LOCAL-609):
          openai            — $ and tokens, split per model under `by_model`
          gemini_grounding  — $, grounded requests, search queries
          gemini_tokens     — $, Flash input/output tokens
          serper            — $, queries
          preflight         — $, queries + Flash tokens (0 on a cache hit)
          tts               — engine, chars, $ (Kokoro is $0 by rate)
        A translation row carries its own `translation` key (added by the
        translation service), not here.
        """
        with self._lock:
            return {
                "openai": {
                    "usd": self.llm["usd"],
                    "calls": self.llm["calls"],
                    "input_tokens": self.llm["input_tokens"],
                    "output_tokens": self.llm["output_tokens"],
                    "by_model": {
                        m: dict(v) for m, v in self.llm_by_model.items()
                    },
                },
                "gemini_grounding": {
                    "usd": self.grounding["usd"],
                    "requests": self.grounding["requests"],
                    "queries": self.grounding["queries"],
                },
                "gemini_tokens": {
                    "usd": self.gemini_tokens["usd"],
                    "calls": self.gemini_tokens["calls"],
                    "input_tokens": self.gemini_tokens["input_tokens"],
                    "output_tokens": self.gemini_tokens["output_tokens"],
                },
                "serper": {
                    "usd": self.search["usd"],
                    "queries": self.search["queries"],
                },
                "preflight": {
                    "usd": self.preflight["usd"],
                    "calls": self.preflight["calls"],
                    "queries": self.preflight["queries"],
                    "input_tokens": self.preflight["input_tokens"],
                    "output_tokens": self.preflight["output_tokens"],
                },
                "tts": {
                    "usd": self.tts["usd"],
                    "engine": self.tts.get("engine", ""),
                    "characters": self.tts["characters"],
                    "calls": self.tts["calls"],
                },
            }

    def snapshot(self) -> dict:
        """A full debug snapshot: breakdown plus per-bucket counters and total.

        [LOCAL-609] carries both the legacy four-key ``breakdown`` and the new
        seven-key ``provider_breakdown`` so old readers and the new report both
        work, and the total now includes gemini_tokens and preflight.
        """
        with self._lock:
            total = self._total_usd_locked()
            provider = {
                "openai": {
                    "usd": self.llm["usd"], "calls": self.llm["calls"],
                    "input_tokens": self.llm["input_tokens"],
                    "output_tokens": self.llm["output_tokens"],
                    "by_model": {m: dict(v) for m, v in self.llm_by_model.items()},
                },
                "gemini_grounding": {
                    "usd": self.grounding["usd"],
                    "requests": self.grounding["requests"],
                    "queries": self.grounding["queries"],
                },
                "gemini_tokens": {
                    "usd": self.gemini_tokens["usd"], "calls": self.gemini_tokens["calls"],
                    "input_tokens": self.gemini_tokens["input_tokens"],
                    "output_tokens": self.gemini_tokens["output_tokens"],
                },
                "serper": {"usd": self.search["usd"], "queries": self.search["queries"]},
                "preflight": {
                    "usd": self.preflight["usd"], "calls": self.preflight["calls"],
                    "queries": self.preflight["queries"],
                    "input_tokens": self.preflight["input_tokens"],
                    "output_tokens": self.preflight["output_tokens"],
                },
                "tts": {
                    "usd": self.tts["usd"], "engine": self.tts.get("engine", ""),
                    "characters": self.tts["characters"], "calls": self.tts["calls"],
                },
            }
            return {
                "job_id": self.job_id,
                "total_usd": total,
                "breakdown": {
                    "llm": self.llm["usd"],
                    "grounding": self.grounding["usd"],
                    "search": self.search["usd"],
                    "tts": self.tts["usd"],
                },
                "provider_breakdown": provider,
                "llm": dict(self.llm),
                "llm_by_model": {m: dict(v) for m, v in self.llm_by_model.items()},
                "grounding": dict(self.grounding),
                "gemini_tokens": dict(self.gemini_tokens),
                "preflight": dict(self.preflight),
                "search": dict(self.search),
                "tts": dict(self.tts),
            }


# ─── ContextVar plumbing ─────────────────────────────────────────────────────
# The current tour's accumulator. Default None = "no tour scope active"; calls
# made outside any scope are simply not attributed (and the wrapper falls back to
# passing straight through), which is the correct behaviour for ad-hoc scripts.
_current: "contextvars.ContextVar[Optional[CostAccumulator]]" = contextvars.ContextVar(
    "cost_accumulator_current", default=None
)

# [LOCAL-609] When True in the current context, Gemini usage made inside this
# dynamic scope is attributed to the PREFLIGHT bucket (the LOCAL-603 venue
# preflight call) instead of the ordinary gemini_tokens + gemini_grounding
# channels — so the ledger can show preflight on its own line (ticket LOCAL-609).
# The preflight is a grounded Gemini call that would otherwise be indistinguishable
# from any other grounded call in the token/grounding totals.
_preflight_active: "contextvars.ContextVar[bool]" = contextvars.ContextVar(
    "cost_accumulator_preflight_active", default=False
)


@contextlib.contextmanager
def preflight_scope():
    """[LOCAL-609] Mark the dynamic scope of the LOCAL-603 venue preflight call.

    Gemini usage (tokens + grounding queries) metered via ``add_gemini_call``
    inside this ``with`` block lands in the accumulator's PREFLIGHT bucket, so the
    tour_generate ledger row can report preflight separately. Nests cleanly and
    is a no-op for attribution outside a tour scope.
    """
    token = _preflight_active.set(True)
    try:
        yield
    finally:
        _preflight_active.reset(token)


def add_gemini_call(input_tokens: int = 0, output_tokens: int = 0,
                    num_queries: int = 0, grounded: bool = False,
                    num_requests: int = 1) -> float:
    """[LOCAL-609] Attribute ONE Gemini call to the current tour scope, routing by
    whether we are inside a ``preflight_scope``.

    This is the single entry point the two Gemini HTTP sites (story_leads._gemini
    and story_leads.gemini_with_sources) call after they parse a response. It:

      * adds the Flash input/output TOKENS (always — every Gemini call burns
        tokens), and
      * adds the grounding SEARCH QUERIES when ``grounded`` (the dollar unit Google
        invoices), tracking the request for the LOCAL-594 cap.

    When a ``preflight_scope`` is active, BOTH the tokens and the queries land in
    the preflight bucket instead, so preflight shows on its own ledger line and is
    not double-counted in gemini_tokens/gemini_grounding. No-op outside a tour
    scope. Returns the dollars added.
    """
    acc = _current.get()
    if acc is None:
        return 0.0
    if _preflight_active.get():
        return acc.add_preflight(
            num_queries=(num_queries if grounded else 0),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    cost = acc.add_gemini_tokens(input_tokens, output_tokens)
    if grounded:
        cost += acc.add_grounding(num_requests=num_requests, num_queries=num_queries)
    return cost


def current_accumulator() -> Optional[CostAccumulator]:
    """Return the accumulator for the tour in whose scope we are running, or None."""
    return _current.get()


@contextlib.contextmanager
def tour_scope(job_id: Optional[str] = None, accumulator: Optional[CostAccumulator] = None):
    """Open a per-tour cost scope.

    All billable calls made dynamically within the ``with`` block — including in
    worker threads submitted via ``run_in_tour_context`` — are attributed to the
    one accumulator yielded here. Nesting is supported (inner scope shadows outer
    for its duration, then restores).

    Usage::

        with cost_accumulator.tour_scope(job_id=job_id) as acc:
            ... run generation ...
            record = acc.snapshot()
    """
    acc = accumulator or CostAccumulator(job_id=job_id)
    token = _current.set(acc)
    try:
        yield acc
    finally:
        _current.reset(token)


def run_in_tour_context(accumulator: CostAccumulator, fn, *args, **kwargs):
    """Run ``fn(*args, **kwargs)`` with ``accumulator`` bound as the current scope.

    Use this to submit work to a ``ThreadPoolExecutor`` so the child thread
    attributes its calls to the parent tour's accumulator. ThreadPoolExecutor
    does not copy contextvars into workers, so each worker must re-bind.
    """
    def _runner():
        token = _current.set(accumulator)
        try:
            return fn(*args, **kwargs)
        finally:
            _current.reset(token)

    return _runner


# ─── ThreadPoolExecutor context propagation ─────────────────────────────────
# The pipeline fans per-stop work out across ~12 ThreadPoolExecutor sites (the
# per-stop story pass at generate_tour_text.py:15076 is the single most
# expensive LLM call of a tour). ``ThreadPoolExecutor`` does NOT copy the
# submitting thread's contextvars into its workers, so an OpenAI call made inside
# a worker sees ``current_accumulator() is None`` and goes uncounted — which is
# exactly why a live Chart House run first attributed only 46 of 56 calls.
#
# ``install_executor_context_propagation`` patches ``ThreadPoolExecutor.submit``
# so each submitted callable runs inside a *copy* of the submitting thread's
# context (``contextvars.copy_context()``). Each tour's main thread holds its own
# scope, so its workers inherit that tour's accumulator and no other — concurrent
# tours stay isolated (the copy is taken per-submit, per-thread). Idempotent.
_executor_patch_lock = threading.Lock()
_executor_patch = {"installed": False, "orig_submit": None}


def install_executor_context_propagation() -> bool:
    """Make ThreadPoolExecutor workers inherit the submitting thread's cost scope.

    Patches ``concurrent.futures.ThreadPoolExecutor.submit`` once. Safe to call
    repeatedly. Returns True when active.
    """
    with _executor_patch_lock:
        if _executor_patch["installed"]:
            return True
        from concurrent.futures import ThreadPoolExecutor

        orig_submit = ThreadPoolExecutor.submit
        _executor_patch["orig_submit"] = orig_submit

        def _submit(self, fn, /, *args, **kwargs):
            ctx = contextvars.copy_context()

            def _in_ctx(*a, **k):
                return ctx.run(fn, *a, **k)

            return orig_submit(self, _in_ctx, *args, **kwargs)

        ThreadPoolExecutor.submit = _submit
        _executor_patch["installed"] = True
        return True


def uninstall_executor_context_propagation() -> None:
    with _executor_patch_lock:
        if not _executor_patch["installed"]:
            return
        from concurrent.futures import ThreadPoolExecutor
        if _executor_patch["orig_submit"] is not None:
            ThreadPoolExecutor.submit = _executor_patch["orig_submit"]
        _executor_patch["orig_submit"] = None
        _executor_patch["installed"] = False



# ─── module-level convenience: attribute to the current scope ────────────────
# These are what the HTTP wrapper and the grounding/TTS sites call. Each is a
# no-op (returns 0.0) when there is no active tour scope, so importing and
# calling them is always safe.

def add_llm_usage(input_tokens: int, output_tokens: int, model: str) -> float:
    acc = _current.get()
    if acc is None:
        return 0.0
    return acc.add_llm(input_tokens, output_tokens, model)


def add_grounding_requests(num_requests: int = 1, num_queries: int = 0) -> float:
    """[LOCAL-609] Attribute grounded Gemini usage to the current scope. ``num_queries``
    (the webSearchQueries count) drives the dollars; ``num_requests`` is tracked
    for the LOCAL-594 per-stop cap. No-op outside a tour scope."""
    acc = _current.get()
    if acc is None:
        return 0.0
    return acc.add_grounding(num_requests, num_queries)


def add_gemini_tokens(input_tokens: int = 0, output_tokens: int = 0) -> float:
    """[LOCAL-609] Attribute one Gemini Flash call's token usage to the current
    scope (the token channel, separate from grounding). No-op outside a scope."""
    acc = _current.get()
    if acc is None:
        return 0.0
    return acc.add_gemini_tokens(input_tokens, output_tokens)


def add_preflight(num_queries: int = 0, input_tokens: int = 0,
                  output_tokens: int = 0) -> float:
    """[LOCAL-609] Attribute the LOCAL-603 venue preflight call to the current
    scope, on its own ledger line. No-op outside a scope."""
    acc = _current.get()
    if acc is None:
        return 0.0
    return acc.add_preflight(num_queries, input_tokens, output_tokens)


def add_search_queries(num_queries: int = 1) -> float:
    acc = _current.get()
    if acc is None:
        return 0.0
    return acc.add_search(num_queries)


def add_tts_characters(char_count: int, engine: str = "neural") -> float:
    acc = _current.get()
    if acc is None:
        return 0.0
    return acc.add_tts(char_count, engine=engine)
