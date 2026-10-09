"""conftest.py — repo-root pytest fixtures.

[LOCAL-656] The per-tour memoization in ``fast_pipeline`` (resolve_venue /
fetch_venue_works) is keyed by call arguments and scoped to one tour generation.
In production the tour wrapper calls ``fast_pipeline.reset_tour_memo()`` at the
start of every tour, so each tour sees an empty memo. Pytest runs many tests in
ONE process/thread (one ``contextvars`` Context), so without a reset a test that
calls ``fetch_venue_works("Q160112", …)`` with one monkeypatched SPARQL backend
would, when ``FAST_PIPELINE=1``, serve a later test calling the SAME key from the
earlier test's cached value.

This autouse fixture resets the memo before each test, exactly mirroring the
per-tour boundary. It is a no-op when ``fast_pipeline`` is absent and never
changes any test's intent — it only guarantees the clean-slate the real pipeline
already guarantees per tour. It does nothing when the flag is OFF (the memo is
never consulted) beyond clearing an empty store.
"""
import pytest


@pytest.fixture(autouse=True)
def _reset_fast_pipeline_tour_memo():
    try:
        import fast_pipeline
        fast_pipeline.reset_tour_memo()
    except Exception:
        pass
    yield
    try:
        import fast_pipeline
        fast_pipeline.reset_tour_memo()
    except Exception:
        pass
