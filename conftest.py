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


@pytest.fixture(autouse=True)
def _disable_live_serper_places(monkeypatch):
    """[LOCAL-783] Keep the test suite OFFLINE.

    places_search routes business/restaurant lookups to Serper's Places endpoint
    whenever SERP_API_KEY is set and SERP_PROVIDER=serper. The developer `.env`
    sets both, so without this the many fixture-only suites that monkeypatch
    stop_existence_gate._nominatim_request would be bypassed and would attempt
    LIVE Serper calls. We force the provider OFF for every test by default, so the
    Nominatim seam the suites already patch stays the seam under test.

    A test that specifically exercises the Serper Places path opts back in by
    monkeypatching places_search._serper_post with a recorded fixture (which does
    not need the env), so this never blocks the LOCAL-783 Serper tests — they set
    their own fake transport rather than relying on the real key.
    """
    monkeypatch.delenv("SERP_API_KEY", raising=False)
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.setenv("SERP_PROVIDER", "nominatim")
    yield
