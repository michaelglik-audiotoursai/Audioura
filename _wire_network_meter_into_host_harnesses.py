#!/usr/bin/env python3
"""_wire_network_meter_into_host_harnesses.py — one-off editor (LOCAL-678).

Host-run harnesses (measure_*.py, replay_harness.py, and the run_*_live /
*massart / mcmullen runners that import story_leads / serper_* and call paid APIs
DIRECTLY on the Mac, not inside a container) have no sitecustomize, so the
network paid-API meter (_meter/paid_api_meter.py) is never installed for them and
their OpenAI/Gemini/Serper calls never reach paid_api_calls. That is a large part
of the Oct 11 ~6.6k unmetered OpenAI requests.

This tool inserts, right after each listed file's module docstring, a tiny block
that puts the repo's _meter dir on sys.path and installs the meter. Idempotent:
it skips any file that already references meter_bootstrap. It is a dev tool kept
in the tree for provenance; it does not run at tour time.

    python3 _wire_network_meter_into_host_harnesses.py
"""
import os
import re

# Host-run harnesses that make paid calls directly (NOT *_container.py, which run
# inside the generator image where sitecustomize already installs the meter).
HARNESSES = [
    "measure_local645_overlap.py",
    "measure_local648_overlap.py",
    "measure_local674_walking.py",
    "measure_local674_pervenue.py",
    "replay_harness.py",
    "run_local585_live.py",
    "run_local590_live.py",
    "run_local591_live.py",
    "run_local592_live.py",
    "run_local584_live.py",
    "run_local607_live.py",
    "run_local614_live.py",
    "run_local543_live.py",
    "run_local540_logan.py",
    "run_local594_mcmullen.py",
    "run_local599_massart.py",
    "run_local599b_massart.py",
    "run_local599c_massart.py",
    "run_local600_massart.py",
    "run_local602b_moic.py",
    "run_local533_one_tour.py",
    "run_matrix_queries.py",
    "run_credit_line_queries.py",
    "run_credit_line_gemini_sources.py",
    "run_seed_queries.py",
    "run_seed_queries_v2.py",
    "run_adjudicated_stories.py",
]

MARKER = "meter_bootstrap"

BLOCK = '''
# [LOCAL-678] Install the network paid-API meter for this HOST-run process. In a
# container sitecustomize (PYTHONPATH=/opt/meter) does this; on the host nothing
# does, so without this line every OpenAI/Gemini/Serper call this harness makes
# would be invisible to paid_api_calls. Must be the first thing we do, before any
# paid-call module is imported. Never breaks a run (install_meter fails open).
import os as _os678  # noqa: E402
import sys as _sys678  # noqa: E402
_sys678.path.insert(0, _os678.path.join(
    _os678.path.dirname(_os678.path.abspath(__file__)), "_meter"))
try:
    import meter_bootstrap as _meter_bootstrap  # noqa: F401,E402  (installs the meter)
except Exception as _meter_err:  # metering must never break a run
    print("[LOCAL-678] network meter unavailable (%s): "
          "paid calls from this host run will not be metered" % (_meter_err,))
'''


def _docstring_end_offset(src):
    """Char offset just after the module docstring (and its newline), or 0."""
    m = re.match(r'^(#![^\n]*\n)?(\s*)("""|\'\'\')', src)
    if not m:
        return 0
    quote = m.group(3)
    start = m.end()
    end = src.find(quote, start)
    if end == -1:
        return 0
    end += len(quote)
    nl = src.find("\n", end)
    return nl + 1 if nl != -1 else end


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    wired, skipped, missing = [], [], []
    for fname in HARNESSES:
        path = os.path.join(here, fname)
        if not os.path.exists(path):
            missing.append(fname)
            continue
        src = open(path, encoding="utf-8").read()
        if MARKER in src:
            skipped.append(fname)
            continue
        off = _docstring_end_offset(src)
        new = src[:off] + BLOCK + src[off:]
        open(path, "w", encoding="utf-8").write(new)
        wired.append(fname)
    print("WIRED (%d): %s" % (len(wired), ", ".join(wired) or "-"))
    print("SKIPPED already-wired (%d): %s" % (len(skipped), ", ".join(skipped) or "-"))
    print("MISSING (%d): %s" % (len(missing), ", ".join(missing) or "-"))


if __name__ == "__main__":
    main()
