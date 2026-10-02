#!/usr/bin/env python3
"""
gcs5r_b1_import_guard.py — GCS-5R Blocker B1: single handler per editing rule.
=============================================================================
storied's tour_editing_phase2.py already had LOCAL-153 shims (update_single_stop,
get_job_status). The naive GCS-5 port ADDED a second def on those same rules,
which makes Flask raise at import:

    AssertionError: View function mapping is overwriting an existing endpoint
    function: update_single_stop

so the container never starts.

This guard does BOTH halves of the red/green:

  RED  : synthesize the naive port (append a duplicate update_single_stop and a
         job_status handler onto a copy of the CURRENT file) and prove it fails
         to import with the endpoint-overwrite AssertionError.
  GREEN: import the real current file and prove app.url_map has each editing
         rule exactly once.

Exit 0 = both halves passed. Windows-safe (utf-8 everywhere).

Usage:  python tests/gcs5r_b1_import_guard.py
"""
import os
import sys
import types
import importlib.util
from unittest.mock import MagicMock

SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE_FILE = os.path.join(SERVICE_DIR, "tour_editing_phase2.py")

EDITING_RULES = {
    "/tour/<tour_id>/bulk-save",
    "/tour/<tour_id>/update-multiple-stops",
    "/tour/<tour_id>/update-stop",
    "/tour/<tour_id>/job-status/<job_id>",
    "/tour/<tour_id>/download",
    "/tour/<tour_id>/edit-info",
}

FAILS = 0


def check(name, cond, detail=""):
    global FAILS
    if cond:
        print(f"  PASS: {name}")
    else:
        print(f"  FAIL: {name} — {detail}")
        FAILS += 1


def _install_mocks():
    mocks = {}
    for mod in ["boto3", "psycopg2", "psycopg2.errors", "psycopg2.extras",
                "flask_cors", "requests", "blobstorage"]:
        if mod not in sys.modules:
            m = MagicMock()
            if mod == "flask_cors":
                m.CORS = lambda app, **kw: None
            if mod == "psycopg2":
                m.errors = MagicMock()
            sys.modules[mod] = m
            mocks[mod] = m
    return mocks


def _uninstall_mocks(mocks):
    for mod in mocks:
        if sys.modules.get(mod) is mocks[mod]:
            del sys.modules[mod]


def _load_from_source(src, module_name):
    """Exec source text as a fresh module; return the module or raise."""
    mod = types.ModuleType(module_name)
    mod.__file__ = os.path.join(SERVICE_DIR, module_name + ".py")
    sys.modules[module_name] = mod
    try:
        code = compile(src, mod.__file__, "exec")
        exec(code, mod.__dict__)
        return mod
    finally:
        pass


def main():
    with open(SERVICE_FILE, "r", encoding="utf-8") as f:
        current_src = f.read()

    mocks = _install_mocks()
    try:
        # ---- RED: naive port = current file + a DUPLICATE handler on an
        # existing rule (exactly the defect GCS-5 introduced). Must fail import.
        naive_src = current_src + (
            "\n\n"
            "@app.route('/tour/<tour_id>/update-stop', methods=['POST'])\n"
            "def update_single_stop_naive_dup(tour_id):\n"
            "    return jsonify({'dup': True})\n"
        )
        # Flask keys the overwrite check on the function name, so reproduce the
        # real collision: a second def named exactly update_single_stop.
        naive_src = current_src + (
            "\n\n"
            "@app.route('/tour/<tour_id>/update-stop', methods=['POST'])\n"
            "def update_single_stop(tour_id):\n"
            "    return jsonify({'dup': True})\n"
            "\n"
            "@app.route('/tour/<tour_id>/job-status/<job_id>', methods=['GET'])\n"
            "def job_status(tour_id, job_id):\n"
            "    return jsonify({'dup': True})\n"
        )
        red_error = None
        try:
            _load_from_source(naive_src, "tour_editing_phase2_naive")
        except Exception as e:
            red_error = e
        finally:
            sys.modules.pop("tour_editing_phase2_naive", None)
        print("[RED] naive port import error:")
        print(f"      {type(red_error).__name__}: {red_error}")
        check("naive port fails to import (endpoint overwrite)",
              red_error is not None and "overwriting an existing endpoint function"
              in str(red_error),
              f"expected AssertionError about overwriting endpoint, got {red_error!r}")

        # ---- GREEN: real current file imports and each rule appears once.
        green_mod = None
        green_error = None
        try:
            green_mod = _load_from_source(current_src, "tour_editing_phase2_green")
        except Exception as e:
            green_error = e
        check("current file imports cleanly", green_error is None,
              f"import raised {green_error!r}")

        if green_mod is not None:
            rules = {}
            for rule in green_mod.app.url_map.iter_rules():
                rules.setdefault(str(rule.rule), 0)
                rules[str(rule.rule)] += 1
            for r in sorted(EDITING_RULES):
                count = rules.get(r, 0)
                check(f"rule registered exactly once: {r}", count == 1,
                      f"found {count} registrations")
        sys.modules.pop("tour_editing_phase2_green", None)
    finally:
        _uninstall_mocks(mocks)

    print()
    if FAILS == 0:
        print("RESULT: PASS — B1 red->green verified (naive dup fails, current single-handler imports).")
        return 0
    print(f"RESULT: FAIL — {FAILS} check(s) failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
