"""job_cancellation.py — LOCAL-622: cooperative cancellation for generator jobs.

Why this exists
---------------
D635: the orchestrator abandoned a live generation after its 20-minute ceiling,
returned an error to the listener, and the generator kept working — finishing a
tour nobody would receive and metering $0.60 of spend for it.

LOCAL-622 part 2 requires: when the orchestrator DOES give up (only after a real
5-minute no-progress stall, with a 40-minute absolute cap), it must tell the
generator job to stop, "so no further spend happens on a tour nobody will
receive."

This module is the generator-side half of that contract. It is a tiny,
thread-safe registry of cancelled job ids. The generator's async worker checks
``is_cancelled(job_id)`` at points that precede spend (external lookups, and —
critically — the billing/charge step) and aborts cleanly instead of continuing.

The registry is intentionally process-local and dependency-free: the orchestrator
reaches it over HTTP (POST /cancel/<job_id> on the generator), which flips the
flag in the generator process that is actually running the job. That keeps the
mechanism simple and unit-testable with no network and no database.
"""

import threading

_lock = threading.Lock()
_cancelled = set()


class JobCancelledError(Exception):
    """Raised when a job has been asked to stop by the orchestrator."""


def request_cancel(job_id: str) -> None:
    """Mark a job as cancelled. Idempotent."""
    if not job_id:
        return
    with _lock:
        _cancelled.add(job_id)


def is_cancelled(job_id: str) -> bool:
    """Return True if the job has been asked to stop."""
    if not job_id:
        return False
    with _lock:
        return job_id in _cancelled


def clear(job_id: str) -> None:
    """Forget a job id (call when a job finishes, to bound the set)."""
    if not job_id:
        return
    with _lock:
        _cancelled.discard(job_id)


def check(job_id: str) -> None:
    """Raise :class:`JobCancelledError` if the job has been cancelled.

    Convenience for inserting a cancellation checkpoint before an expensive or
    spend-incurring step.
    """
    if is_cancelled(job_id):
        raise JobCancelledError(f"Job {job_id} was cancelled by the orchestrator")
