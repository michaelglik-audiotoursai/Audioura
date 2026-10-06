"""
l2_by_reference.py — LOCAL-597: the L2 "by reference" tour path (D613).
========================================================================

An L2 (free) tour may only **reuse researched stops that already exist** — the
LOCAL-590 stop pool and the stops of existing non-test tours of the same venue
(or within an outdoor tour's radius). It re-sequences and re-narrates them
through the existing pool assembly (stop_pool_assembly), regenerating only the
orientation / adjacent transitions and folding the D611 opening section in from
STORED material. It must issue **zero grounded Gemini requests and zero Serper
queries** (SUBSCRIPTION_LEVELS.md §"L2 by reference"). If there is no reusable
material, the listener gets an actionable refusal — never a fresh generation.

This module has two public pieces:

  1. THE GUARD. `grounding_forbidden()` is a context manager that, for its
     duration, makes any grounded `story_leads` call and any `work_story_searcher`
     Serper query RAISE `GroundingForbiddenError` instead of hitting the network.
     The two choke points (story_leads._gemini / gemini_with_sources with
     grounded=True, and work_story_searcher._serp_search) consult
     `grounding_is_forbidden()` at call time and raise. This is the belt-and-braces
     proof that an L2 build cannot spend a cent on grounding or SERP: not only does
     the by-reference path never call them, but if some future refactor wired a
     grounded call into it, the build would fail loudly rather than silently bill.

  2. THE PATH. `build_by_reference_tour(...)` resolves reusable material, and
     either returns an assembled tour (reusing >= N stops, zero grounding) or a
     structured refusal (`by_reference_no_material`) carrying up to three nearby
     existing tours. `check_zero_grounding()` reads the LOCAL-594 counters so a
     caller/test can assert the build spent nothing on grounding.

The guard is a process-global toggle guarded by a lock and implemented as a depth
counter so nested `with` blocks compose. It is deliberately conservative: when
the flag is on, EVERY grounded request raises, no matter who issues it.
"""
import logging
import os
import threading
from contextlib import contextmanager
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# THE GUARD
# ─────────────────────────────────────────────────────────────────────────────
class GroundingForbiddenError(RuntimeError):
    """Raised when a grounded Gemini request or a Serper query is attempted while
    an L2 by-reference build is active. An L2 tour reuses already-researched
    material only; reaching the network for fresh grounding/SERP is a bug, and
    this error turns that bug into a hard, visible failure instead of a silent
    charge."""


# Depth counter (not a bool) so nested guard blocks compose correctly: the guard
# only lifts when the outermost block exits. Guarded by a lock because grounded
# calls fan out across worker threads (story pass / gates), and the by-reference
# path must forbid grounding on every one of them.
_guard_lock = threading.RLock()
_guard_depth = 0


def grounding_is_forbidden() -> bool:
    """True while any L2 by-reference build is active. The two grounding/SERP
    choke points consult this and raise GroundingForbiddenError when it is True."""
    with _guard_lock:
        return _guard_depth > 0


def _enter_guard() -> None:
    global _guard_depth
    with _guard_lock:
        _guard_depth += 1


def _exit_guard() -> None:
    global _guard_depth
    with _guard_lock:
        if _guard_depth > 0:
            _guard_depth -= 1


@contextmanager
def grounding_forbidden():
    """Context manager: forbid grounded Gemini + Serper for its duration.

    Also resets the LOCAL-594 grounding counters on entry so a caller/test can
    read them afterwards and assert they stayed at 0. Resetting is best-effort
    (story_leads may be unavailable in an isolated unit test); the raise-on-call
    guard does not depend on it.
    """
    _enter_guard()
    try:
        try:
            import story_leads
            story_leads.reset_grounding_requests()
        except Exception as e:  # pragma: no cover - counter reset is best-effort
            logger.info(f"[LOCAL-597] grounding counter reset skipped: {e}")
        yield
    finally:
        _exit_guard()


def _raise_if_forbidden(what: str) -> None:
    """Raise GroundingForbiddenError if a grounding/SERP guard is active.

    Called from the grounded-Gemini and Serper choke points. `what` names the
    attempted operation for the error message and the log line.
    """
    if grounding_is_forbidden():
        logger.error(f"[LOCAL-597] GUARD TRIPPED: {what} attempted during an L2 "
                     f"by-reference build — raising GroundingForbiddenError")
        raise GroundingForbiddenError(
            f"{what} is forbidden during an L2 by-reference build "
            f"(zero grounding, zero SERP)."
        )


def check_zero_grounding() -> Dict[str, int]:
    """Return the LOCAL-594 grounding meter: {requests, queries}. A by-reference
    build must leave both at 0. Best-effort: if story_leads is unavailable the
    meter is reported as 0 (nothing could have been counted)."""
    try:
        import story_leads
        return {
            "requests": int(story_leads.get_grounding_requests()),
            "queries": int(story_leads.get_grounding_queries()),
        }
    except Exception as e:  # pragma: no cover
        logger.info(f"[LOCAL-597] grounding meter read skipped: {e}")
        return {"requests": 0, "queries": 0}
