"""tests/test_local707_serper_scan_guard.py — LOCAL-707 static-scan guard.

Fails if any repo module issues an HTTP request to google.serper.dev WITHOUT
routing through the one metered door, serper_meter.serper_post / serper_search.

WHY A STATIC SCAN (LOCAL-705-style). The Oct 13 regression was silent: a new HTTP
client (httpx) was metered while the urllib/requests Serper path quietly stopped
being recorded, and no test would have caught it because no test asserted Serper
coverage. A grep-level guard makes "every Serper call is metered" a property the
whole repo is held to, so a future module that POSTs to serper.dev directly —
bypassing the meter — fails CI instead of silently going unbilled.

HOW. For every *.py file that contains a serper.dev URL literal used as an HTTP
request target, the file must import the metered door (serper_meter). The door
itself and a small, explicit allowlist of out-of-tour-path diagnostic/measurement
scripts (which run ad-hoc on the host, not in the live generator) are exempt —
listed by name so the exemption is intentional and visible, never a default.

NO network, NO imports of the scanned modules — this is pure text/AST analysis.
"""
import ast
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The one metered door. A file that routes Serper through this is compliant.
_DOOR_MARKERS = ("serper_meter", "serper_post", "serper_search")

# The serper host. Any string literal containing this that is used as a request
# target must go through the door.
_SERPER_HOST = "serper.dev"

# ── explicit, documented allowlist ───────────────────────────────────────────
# These are NOT in the live tour-generation path. They are ad-hoc host-run
# diagnostics / measurement one-offs (and the door itself + the meter). Each is
# listed by name so the exemption is deliberate; adding a new production module
# that hits serper.dev directly will NOT be covered here and so will FAIL.
_ALLOWLIST = {
    # the metered door itself + its test
    "serper_meter.py",
    os.path.join("tests", "test_local707_serper_scan_guard.py"),
    os.path.join("tests", "test_local707_serper_metered.py"),
    # the network meter module (defines the host match, never calls serper)
    os.path.join("_meter", "paid_api_meter.py"),
    # ── out-of-tour-path diagnostics / measurement one-offs (host, ad-hoc) ──
    "test_serp_key.py",                       # standalone key probe
    "test_local409_serp_request_encoding.py",  # mocked urlopen, no real call
    "run_local242_retrieval_lift.py",          # read-only retrieval measurement
    os.path.join("tests", "fetch_baseline_stop_sources.py"),
    os.path.join("tests", "fetch_palais_lascaris_sources.py"),
    os.path.join("tests", "fetch_palais_lascaris_sources_r2.py"),
    os.path.join("tests", "fetch_riviera_outdoor_sources.py"),
}


def _iter_py_files():
    skip_dirs = {".git", "node_modules", "audio_tour_app", "__pycache__",
                 "migration", "tours", "store_assets", "scratch"}
    for dirpath, dirnames, filenames in os.walk(_ROOT):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fn in filenames:
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


def _rel(path):
    return os.path.relpath(path, _ROOT)


def _string_literals_with_host(src):
    """Return True if the source has a STRING LITERAL (not a comment) containing
    the serper host — i.e. a real URL the code could POST to. Comments and
    docstrings-as-prose are excluded by only looking at ast.Constant str nodes
    that are NOT the module/func/class docstring."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        # Unparseable file: fall back to a conservative text check.
        return _SERPER_HOST in src
    # Collect docstring node ids to exclude pure prose docstrings.
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and \
                    isinstance(getattr(body[0], "value", None), ast.Constant) and \
                    isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstrings:
                continue
            if _SERPER_HOST in node.value:
                return True
    return False


def test_every_serper_url_goes_through_the_metered_door():
    offenders = []
    for path in _iter_py_files():
        rel = _rel(path)
        if rel in _ALLOWLIST:
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
        except Exception:
            continue
        if _SERPER_HOST not in src:
            continue
        # The file mentions serper.dev. Does it use it as a request-target
        # string literal (code), and if so does it route through the door?
        if not _string_literals_with_host(src):
            continue  # only in comments/docstrings — not a call target
        if any(marker in src for marker in _DOOR_MARKERS):
            continue  # routes through serper_meter — compliant
        offenders.append(rel)

    assert not offenders, (
        "These modules POST to serper.dev without routing through the metered "
        "door (serper_meter.serper_post/serper_search), so their Serper spend "
        "would be invisible to the meter — exactly the LOCAL-707 blind spot:\n"
        + "\n".join("  - " + o for o in sorted(offenders))
        + "\n\nRoute the call through serper_meter, or (only for an ad-hoc "
          "out-of-tour-path script) add it to _ALLOWLIST with a one-line reason."
    )


def test_door_module_exists_and_exposes_entry_points():
    """The metered door must exist and expose serper_post + serper_search."""
    door = os.path.join(_ROOT, "serper_meter.py")
    assert os.path.exists(door), "serper_meter.py (the metered door) must exist"
    with open(door, encoding="utf-8") as fh:
        src = fh.read()
    tree = ast.parse(src)
    funcs = {n.name for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert "serper_post" in funcs, "serper_meter must define serper_post()"
    assert "serper_search" in funcs, "serper_meter must define serper_search()"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
