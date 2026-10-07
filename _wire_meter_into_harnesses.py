#!/usr/bin/env python3
"""_wire_meter_into_harnesses.py — one-off editor (LOCAL-613).

Insert the shared live_run_meter cap+meter block into each listed isolated
live-run harness, right after its module docstring. Idempotent: skips a file that
already references live_run_meter. Prints what it changed. This script is a dev
tool kept in the tree for provenance; it does not run at tour time.
"""
import io
import os
import re
import tokenize

HARNESSES = {
    "run_local583_container.py": "LOCAL-583",
    "run_local585_live.py": "LOCAL-585",
    "run_local587_container.py": "LOCAL-587",
    "run_local590_live.py": "LOCAL-590",
    "run_local592_live.py": "LOCAL-592",
    "run_local593_container.py": "LOCAL-593",
    "run_local593b_container.py": "LOCAL-593B",
    "run_local594_mcmullen.py": "LOCAL-594",
    "run_local599_massart.py": "LOCAL-599",
    "run_local599b_massart.py": "LOCAL-599B",
    "run_local599c_massart.py": "LOCAL-599C",
    "run_local600_massart.py": "LOCAL-600",
    "run_local602b_moic.py": "LOCAL-602B",
    "run_local603_preflight.py": "LOCAL-603",
    "run_local607_live.py": "LOCAL-607",
}

BLOCK = '''
# [LOCAL-613] Meter + cap this isolated run. auto_meter installs the per-task
# TEST_GEMINI_MAX_USD cap (default $1.00, ALL providers combined) at the grounding
# counter and writes ONE cost_ledger row (user_id='{uid}', description='test run')
# at process exit — even if the cap or any error stops the run. One line; every
# future harness should do the same.
import os as _os613  # noqa: E402
import sys as _sys613  # noqa: E402
_sys613.path.insert(0, _os613.path.join(
    _os613.path.dirname(_os613.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter  # noqa: E402
    _live_run_meter.auto_meter('{uid}')
except Exception as _meter_err:  # metering must never break a run
    print(f"[LOCAL-613] live_run_meter unavailable ({{_meter_err}}): "
          f"run will not be metered/capped")
'''


def _docstring_end_offset(src):
    """Return the character offset just after the module docstring (and its
    newline), or 0 if there is no module docstring."""
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readlines().__iter__().__next__))
    except Exception:
        toks = None
    # Simpler: find the first triple-quoted string at module start.
    m = re.match(r'^(#![^\n]*\n)?(\s*)("""|\'\'\')', src)
    if not m:
        return 0
    quote = m.group(3)
    start = m.end()
    end = src.find(quote, start)
    if end == -1:
        return 0
    end += len(quote)
    # advance past the end-of-line
    nl = src.find("\n", end)
    return nl + 1 if nl != -1 else end


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    for fname, uid in HARNESSES.items():
        path = os.path.join(here, fname)
        if not os.path.exists(path):
            print(f"SKIP (missing): {fname}")
            continue
        src = open(path, encoding="utf-8").read()
        if "live_run_meter" in src:
            print(f"SKIP (already wired): {fname}")
            continue
        off = _docstring_end_offset(src)
        block = BLOCK.format(uid=uid)
        new = src[:off] + block + src[off:]
        open(path, "w", encoding="utf-8").write(new)
        print(f"WIRED: {fname}  -> {uid}")


if __name__ == "__main__":
    main()
