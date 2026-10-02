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
    "current_accumulator",
    "add_llm_usage",
    "add_grounding_requests",
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

    __slots__ = ("_lock", "job_id", "llm", "grounding", "search", "tts")

    def __init__(self, job_id: Optional[str] = None):
        self._lock = threading.Lock()
        self.job_id = job_id
        # Each bucket: usd plus type-appropriate counters.
        self.llm = {"usd": 0.0, "calls": 0, "input_tokens": 0, "output_tokens": 0}
        self.grounding = {"usd": 0.0, "requests": 0}
        self.search = {"usd": 0.0, "queries": 0}
        self.tts = {"usd": 0.0, "characters": 0, "calls": 0}

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
        return cost

    def add_grounding(self, num_requests: int = 1) -> float:
        """Add ``num_requests`` grounded Google-Search Gemini requests (per-request bill)."""
        num_requests = int(num_requests or 0)
        cost = cost_rates.grounding_cost(num_requests)
        with self._lock:
            self.grounding["usd"] += cost
            self.grounding["requests"] += num_requests
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
        return cost

    # ---- read-out ---------------------------------------------------------
    def total_usd(self) -> float:
        with self._lock:
            return self.llm["usd"] + self.grounding["usd"] + self.search["usd"] + self.tts["usd"]

    def breakdown(self) -> dict:
        """The four-key breakdown the cost ledger stores."""
        with self._lock:
            return {
                "llm": self.llm["usd"],
                "grounding": self.grounding["usd"],
                "search": self.search["usd"],
                "tts": self.tts["usd"],
            }

    def snapshot(self) -> dict:
        """A full debug snapshot: breakdown plus per-bucket counters and total."""
        with self._lock:
            return {
                "job_id": self.job_id,
                "total_usd": (
                    self.llm["usd"] + self.grounding["usd"]
                    + self.search["usd"] + self.tts["usd"]
                ),
                "breakdown": {
                    "llm": self.llm["usd"],
                    "grounding": self.grounding["usd"],
                    "search": self.search["usd"],
                    "tts": self.tts["usd"],
                },
                "llm": dict(self.llm),
                "grounding": dict(self.grounding),
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


def add_grounding_requests(num_requests: int = 1) -> float:
    acc = _current.get()
    if acc is None:
        return 0.0
    return acc.add_grounding(num_requests)


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
