#!/usr/bin/env python3
"""
test_gcs5r2_update_stop_empty_text.py — GCS-5R2 item 2 red->green guard.
=========================================================================
GCS-5R removed the old `if not new_text` validation from update-stop. As a
result POST /tour/<id>/update-stop with an empty or whitespace-only new_text is
accepted and synthesises an empty stop, which risks a zero-length audio file
(Michael saw "0 length" audio in the editor). This guard proves the 400
VALIDATION_FAILED response is restored.

Two-part (project pattern, D35/D36 — exercise, don't just inspect):

  RED  : reconstruct the pre-fix handler body (no new_text check) as its own
         Flask app and prove empty new_text is NOT rejected with 400 — i.e. the
         guard would have caught the regression.
  GREEN: import the real tour_editing_phase2 app, stub the persistence path
         (_bulk_save_core) so a valid save does not touch a DB/R2, and prove:
           - empty new_text        -> 400 VALIDATION_FAILED
           - whitespace new_text   -> 400 VALIDATION_FAILED
           - missing new_text      -> 400 VALIDATION_FAILED
           - non-empty new_text    -> NOT 400 (passes validation, reaches save)
           - missing stop_number   -> 400 VALIDATION_FAILED (pre-existing rule
                                       still holds)

Heavy deps (boto3, psycopg2, ...) are mocked so the app imports for route
exercise only. Windows-safe: utf-8 on every read.

Usage:  python tests/test_gcs5r2_update_stop_empty_text.py
"""
import os
import sys
import importlib.util
from unittest.mock import MagicMock

from flask import Flask, request, jsonify

SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE_FILE = os.path.join(SERVICE_DIR, "tour_editing_phase2.py")

PASS_COUNT = 0
FAIL_COUNT = 0


def check(name, condition, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        print(f"  PASS: {name}")
        PASS_COUNT += 1
    else:
        print(f"  FAIL: {name} — {detail}")
        FAIL_COUNT += 1


def _mock_missing_modules():
    mocks = {}
    for mod_name in [
        "boto3", "psycopg2", "psycopg2.errors", "psycopg2.extras",
        "flask_cors", "requests", "blobstorage",
    ]:
        if mod_name not in sys.modules:
            mock = MagicMock()
            if mod_name == "flask_cors":
                mock.CORS = lambda app, **kw: None
            if mod_name == "psycopg2":
                mock.errors = MagicMock()
            sys.modules[mod_name] = mock
            mocks[mod_name] = mock
    return mocks


def _cleanup_mocks(mocks):
    for mod_name in mocks:
        if mod_name in sys.modules and sys.modules[mod_name] is mocks[mod_name]:
            del sys.modules[mod_name]


def load_module_from_file(filepath):
    os.environ.setdefault("DATABASE_URL", "postgresql://admin:password123@localhost:5433/audiotours")
    os.environ.setdefault("POLLY_TTS_URL", "http://localhost:5018")
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
    if SERVICE_DIR not in sys.path:
        sys.path.insert(0, SERVICE_DIR)

    mocks = _mock_missing_modules()
    try:
        mod_name = "tour_editing_phase2_gcs5r2_under_test"
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        spec = importlib.util.spec_from_file_location(mod_name, filepath)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        _cleanup_mocks(mocks)


# ── RED: pre-fix handler (no new_text validation) must NOT reject empty text ──
def _build_prefix_app():
    """Reconstruct the GCS-5R (pre-fix) update-stop handler: validates only
    stop_number, folds any new_text (including empty) into a bulk save."""
    app = Flask(__name__)

    @app.route('/tour/<tour_id>/update-stop', methods=['POST'])
    def update_single_stop(tour_id):
        data = request.json or {}
        stop_number = data.get('stop_number')
        new_text = data.get('new_text', data.get('text', ''))
        if stop_number is None:
            return jsonify({
                "status": "error", "message": "stop_number is required",
                "error_code": "VALIDATION_FAILED", "recoverable": True,
            }), 400
        # No new_text check (the regression) — pretend the save succeeds.
        return jsonify({"status": "success", "new_tour_id": "synth", "echo_text": new_text}), 200

    return app


def test_red_probe():
    print("\n[RED PROBE] Pre-fix handler accepts empty new_text (regression present)")
    app = _build_prefix_app()
    client = app.test_client()
    r = client.post('/tour/123/update-stop', json={"stop_number": 1, "new_text": ""})
    print(f"  pre-fix empty new_text -> {r.status_code}")
    check("RED: pre-fix handler does NOT return 400 on empty new_text "
          "(so the GREEN guard is meaningful)",
          r.status_code != 400,
          f"pre-fix handler returned {r.status_code}; probe is not evidence")


# ── GREEN: real handler rejects empty/whitespace/missing new_text ─────────────
def test_green_real_handler():
    print("\n[GREEN] Real update-stop handler validates new_text")
    mod = load_module_from_file(SERVICE_FILE)

    # Stub the persistence core so a VALID save doesn't touch DB/R2/Polly.
    mod._bulk_save_core = lambda tour_id, data: (
        mod.jsonify({"status": "success", "new_tour_id": "stub", "stubbed": True})
    )

    client = mod.app.test_client()

    def body(status, data):
        r = client.post(f'/tour/123/update-stop', json=data)
        return r.status_code, (r.get_json() or {})

    # empty string
    sc, js = body(None, {"stop_number": 1, "new_text": ""})
    print(f"  empty new_text -> {sc} {js.get('error_code')}")
    check("empty new_text -> 400 VALIDATION_FAILED",
          sc == 400 and js.get("error_code") == "VALIDATION_FAILED",
          f"got {sc} {js}")

    # whitespace only
    sc, js = body(None, {"stop_number": 1, "new_text": "   \n\t  "})
    print(f"  whitespace new_text -> {sc} {js.get('error_code')}")
    check("whitespace-only new_text -> 400 VALIDATION_FAILED",
          sc == 400 and js.get("error_code") == "VALIDATION_FAILED",
          f"got {sc} {js}")

    # missing new_text entirely
    sc, js = body(None, {"stop_number": 1})
    print(f"  missing new_text -> {sc} {js.get('error_code')}")
    check("missing new_text -> 400 VALIDATION_FAILED",
          sc == 400 and js.get("error_code") == "VALIDATION_FAILED",
          f"got {sc} {js}")

    # valid new_text passes validation and reaches the (stubbed) save
    sc, js = body(None, {"stop_number": 1, "new_text": "A real edit."})
    print(f"  valid new_text -> {sc} stubbed={js.get('stubbed')}")
    check("non-empty new_text -> NOT 400 (reaches save path)",
          sc != 400 and js.get("stubbed") is True,
          f"got {sc} {js}")

    # pre-existing rule: missing stop_number still 400
    sc, js = body(None, {"new_text": "text but no stop number"})
    print(f"  missing stop_number -> {sc} {js.get('error_code')}")
    check("missing stop_number -> 400 VALIDATION_FAILED (unchanged)",
          sc == 400 and js.get("error_code") == "VALIDATION_FAILED",
          f"got {sc} {js}")


def main():
    print("\n" + "=" * 70)
    print("test_gcs5r2_update_stop_empty_text.py")
    print("GCS-5R2 item 2: restore 400 VALIDATION_FAILED for empty new_text")
    print("=" * 70)

    test_red_probe()
    test_green_real_handler()

    print(f"\n{'=' * 70}")
    print(f"Results: {PASS_COUNT} passed, {FAIL_COUNT} failed")
    print("=" * 70)
    sys.exit(1 if FAIL_COUNT > 0 else 0)


if __name__ == "__main__":
    main()
