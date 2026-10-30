#!/usr/bin/env python3
"""test_local824_route_parity.py — LOCAL-824 recurrence guard.

WHY
===
LOCAL-824's root cause is structural: there are TWO map-delivery Flask files that
have drifted apart —

  * map_delivery_service.py  (repo root)  — the Mac dev monolith; many LOCAL fixes
    land here first and are proven on the Mac against THIS file.
  * map_delivery/app.py                   — the file the Cloud Run map-delivery
    image actually runs (build context ./map_delivery, Dockerfile CMD
    `python app.py`; docker-compose-master.yml, SUBMISSION_LOCAL-88/89).

LOCAL-793 added `/geocode` to the root file only, so it 404'd on the cloud. The
same shape of bug can recur for ANY route. This test is the tripwire: it FAILS
when a route exists in one file but not the other, unless that difference is in
the explicit allowlist below WITH a reason.

WHAT IT DOES
============
Parse each file with `ast` (no import, no DB, no network), collect every
`@app.route('<path>')` path, normalise the path converter (`<int:x>` -> `<x>`)
so `/tour/<int:id>` and `/tour/<id>` compare equal, and compare the two sets.
Every route that is in exactly one file MUST appear in ROOT_ONLY_ALLOWLIST or
APP_ONLY_ALLOWLIST. A new unexplained divergence breaks the build.

LONG-TERM FIX (out of scope here, stated for the record)
========================================================
The real cure is ONE source of truth: either delete the root monolith and have
the Mac dev stack also run map_delivery/app.py (its compose already can —
docker-compose.yml would change `command: python map_delivery_service.py` to the
map_delivery image), or extract the shared route handlers into a module both
files import. Both are larger refactors touching the Mac dev workflow and every
LOCAL fix's muscle memory, so this guard holds the line until then.
"""
import ast
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_ROOT_FILE = os.path.join(_ROOT, "map_delivery_service.py")
_APP_FILE = os.path.join(_ROOT, "map_delivery", "app.py")

_CONVERTER = re.compile(r"<[a-z]+:([a-zA-Z_][a-zA-Z0-9_]*)>")


def _normalise(path):
    """`/tour/<int:tour_id>` -> `/tour/<tour_id>` so converter-type differences
    (int vs string) never count as a route difference."""
    return _CONVERTER.sub(r"<\1>", path)


def _routes(py_path):
    """Return the set of normalised route paths declared with @app.route('...')
    in a file, parsed statically (the first string-literal positional arg of each
    app.route decorator)."""
    with open(py_path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=py_path)
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            func = dec.func
            is_route = (
                (isinstance(func, ast.Attribute) and func.attr == "route") or
                (isinstance(func, ast.Name) and func.id == "route")
            )
            if not is_route or not dec.args:
                continue
            first = dec.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                found.add(_normalise(first.value))
    return found


# ── Intentional differences. Each entry MUST carry a reason. ─────────────────
# Routes that live ONLY in the root monolith because a DEDICATED cloud service
# owns them (the app calls those services directly, not map-delivery), or because
# they have no app consumer at all.
ROOT_ONLY_ALLOWLIST = {
    "/tour/<tour_id>/update-stop":
        "Served on the cloud by tour_editing_service.py (Service.tourEditing, "
        ":5022, path /tour-editing). The app routes stop edits there, not to "
        "map-delivery.",
    "/tour/<tour_id>/edit-info":
        "Served on the cloud by tour_editing_service.py (Service.tourEditing, "
        ":5022). Not a map-delivery endpoint.",
    "/tour/<tour_id>/create-custom":
        "Served on the cloud by tour_editing_service.py (Service.tourEditing, "
        ":5022). Not a map-delivery endpoint.",
    "/tour/<download_id>/resolve":
        "Served on the cloud by tour_id_resolution_service.py "
        "(Service.tourIdResolution, :5025, path /tour-id).",
    "/tour/<tour_id>/version":
        "Legacy update-check endpoint with no app consumer (grep of "
        "audio_tour_app/lib finds no caller); never wired on the cloud.",
    "/tours/check-versions":
        "Legacy batch update-check with no app consumer; dev-only.",
    "/version-test":
        "Dev smoke-test route; never exposed on the cloud.",
}

# Routes that live ONLY in the cloud app.py because they are cloud-era features
# (LOCAL-657+) that were never added back to the Mac dev monolith. They are
# served by map-delivery on the cloud and are not a parity GAP to port downward.
APP_ONLY_ALLOWLIST = {
    "/tour-by-code/<code>":
        "[ST-2] Share-code resolution, a cloud feature; not in the dev monolith.",
    "/report-tour":
        "Cloud content-report endpoint (LOCAL-724 family); cloud-only.",
    "/tour/<tour_id>/preview-audio":
        "Cloud audio-preview endpoint; cloud-only.",
    "/tour/<tour_id>/download-failed":
        "Cloud download-failure recorder (LOCAL-785/D723); cloud-only.",
    "/tour/<tour_id>/score-explanation":
        "'Why this score' (LOCAL-688); cloud-only scoring feature.",
    "/tour/<tour_id>/match":
        "Personal Match % (LOCAL-689); cloud-only.",
    "/tour/<tour_id>/rescore-request":
        "Guide one-free-rescore (LOCAL-688 family); cloud-only.",
    "/how-we-score":
        "Public scoring explainer page (LOCAL-688); cloud-only.",
}


class RouteParityTest(unittest.TestCase):
    def setUp(self):
        self.root = _routes(_ROOT_FILE)
        self.app = _routes(_APP_FILE)

    def test_geocode_is_in_both(self):
        """The specific LOCAL-824 regression: /geocode must be in BOTH files."""
        self.assertIn("/geocode", self.root, "root monolith lost /geocode")
        self.assertIn("/geocode", self.app,
                      "/geocode missing from the DEPLOYED map_delivery/app.py — "
                      "this is exactly the LOCAL-824 bug")

    def test_no_unexplained_root_only_routes(self):
        root_only = self.root - self.app
        unexplained = sorted(r for r in root_only if r not in ROOT_ONLY_ALLOWLIST)
        self.assertEqual(
            unexplained, [],
            "Route(s) exist in map_delivery_service.py but NOT in "
            "map_delivery/app.py (the file the cloud runs). Port them, or add "
            "each to ROOT_ONLY_ALLOWLIST with a reason:\n  " +
            "\n  ".join(unexplained))

    def test_no_unexplained_app_only_routes(self):
        app_only = self.app - self.root
        unexplained = sorted(r for r in app_only if r not in APP_ONLY_ALLOWLIST)
        self.assertEqual(
            unexplained, [],
            "Route(s) exist in map_delivery/app.py but NOT in "
            "map_delivery_service.py. Add each to APP_ONLY_ALLOWLIST with a "
            "reason (or port it to the dev monolith):\n  " +
            "\n  ".join(unexplained))

    def test_allowlists_are_not_stale(self):
        """An allowlisted route that is no longer one-file-only means the drift
        was resolved — remove the stale entry so the allowlist keeps meaning."""
        root_only = self.root - self.app
        app_only = self.app - self.root
        stale_root = sorted(r for r in ROOT_ONLY_ALLOWLIST if r not in root_only)
        stale_app = sorted(r for r in APP_ONLY_ALLOWLIST if r not in app_only)
        self.assertEqual(stale_root, [],
                         "Stale ROOT_ONLY_ALLOWLIST entries (now in both / in "
                         "neither): " + ", ".join(stale_root))
        self.assertEqual(stale_app, [],
                         "Stale APP_ONLY_ALLOWLIST entries (now in both / in "
                         "neither): " + ", ".join(stale_app))


if __name__ == "__main__":
    unittest.main(verbosity=2)
