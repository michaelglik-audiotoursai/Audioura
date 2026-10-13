"""meter_bootstrap.py — install the network paid-API meter from a HOST process.

[LOCAL-678] Containers load the meter through sitecustomize (PYTHONPATH=/opt/meter).
Scripts run directly on the HOST (Kiro harnesses, critique.sh helpers, measure_*.py,
replay_harness.py, run_*_live.py) have NO sitecustomize, so every paid call they
make — OpenAI/Gemini via the SDK (httpx), Serper, raw requests — was never written
to paid_api_calls. That is a large part of the Oct 11 ~6.6k unmetered OpenAI
requests (~$19).

Any host-run script that can make a paid call should, as its FIRST import, do:

    import _meter.meter_bootstrap  # noqa: F401  (installs the paid-API meter)

or, when _meter is not already importable:

    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_meter"))
    import meter_bootstrap  # noqa: F401

Importing this module installs the meter exactly once (idempotent). It never
raises into the caller: a meter failure must never break a run.
"""
import os
import sys

_installed = False


def install_meter():
    """Idempotently install the paid-API network meter. Returns True if the meter
    is active after the call, False if it could not be installed. Never raises."""
    global _installed
    if _installed:
        return True
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        import paid_api_meter
        paid_api_meter.install()
        _installed = True
        return True
    except Exception as e:
        try:
            sys.stderr.write(
                "[meter_bootstrap] could not install paid-API meter: %s\n"
                % (str(e)[:200],))
        except Exception:
            pass
        return False


# Install on import so a bare `import _meter.meter_bootstrap` is enough.
install_meter()
