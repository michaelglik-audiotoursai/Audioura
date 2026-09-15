#!/usr/bin/env python3
"""
test_gcs5e_polly_auth_and_fail.py — GCS-5E red->green guard.
============================================================
polly-tts is a PRIVATE Cloud Run service. tour_editing_phase2 called it with a
bare requests.post and NO identity token, so it got a 403; the caller ignored
the return value and the save reported success with a MISSING audio_1.mp3
(LEAD live verification, 2026-09-15). This guard proves both halves of the fix:

  1. Auth path is really exercised: an auth-requiring Polly stub that returns
     403 unless `Authorization: Bearer <token>` is present, plus an INJECTED
     token function (the production seam _identity_token_fn) so the token is
     actually attached — no real metadata server needed.

Two-part (project pattern D35/D36 — exercise, don't just inspect):

  RED  : reconstruct the pre-fix generator (bare requests.post, no token; on a
         non-200 return ("error", []) and let the caller ignore it) and prove
         that against the auth-requiring stub it produces a save that "succeeds"
         with NO audio_1.mp3 in the built tour. That is the shipped bug.

  GREEN: drive the REAL tour_editing_phase2 app via POST /tour/<id>/bulk-save,
         with _identity_token_fn injected so the token path runs:
           a) Polly reachable + token accepted -> save 200, ZIP has audio_1.mp3
              (> 0 bytes) for the edited stop.
           b) Polly returns 403 (e.g. token missing/denied) -> save 4xx/5xx
              AUDIO_GENERATION_FAILED, and NEITHER an R2 object NOR a
              tour_edit_blobs row is created.

Heavy deps (boto3, psycopg2, blobstorage) are mocked so the app imports without
a DB/R2. The Polly stub runs in a background Flask thread on localhost — the
harness never touches r2.cloudflarestorage.com or a real Cloud Run service.
Windows-safe: utf-8 on every read/write.

Usage:  python tests/test_gcs5e_polly_auth_and_fail.py
"""
import os
import sys
import json
import time
import zipfile
import shutil
import tempfile
import threading
import importlib.util
from unittest.mock import MagicMock

SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE_FILE = os.path.join(SERVICE_DIR, "tour_editing_phase2.py")

PASS_COUNT = 0
FAIL_COUNT = 0

INJECTED_TOKEN = "test-identity-token-abc123"


def check(name, condition, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        print(f"  PASS: {name}")
        PASS_COUNT += 1
    else:
        print(f"  FAIL: {name} — {detail}")
        FAIL_COUNT += 1


# ── Auth-requiring Polly stub (returns 403 unless Bearer token present) ───────
def _make_polly_stub_app(require_token=True, deny_all=False):
    """A minimal /synthesize stub.

    require_token=True : 403 unless Authorization: Bearer <INJECTED_TOKEN>.
    deny_all=True      : always 403 (simulates Polly down / IAM denial).
    On success returns ID3-prefixed bytes so downstream mp3 sniffing is happy.
    """
    from flask import Flask, request, Response
    app = Flask(__name__)

    @app.route('/synthesize', methods=['POST'])
    def synthesize():
        if deny_all:
            return Response('{"error":"forbidden"}', status=403, mimetype='application/json')
        auth = request.headers.get('Authorization', '')
        if require_token and auth != f"Bearer {INJECTED_TOKEN}":
            return Response('{"error":"missing or bad identity token"}',
                            status=403, mimetype='application/json')
        data = request.get_json(silent=True) or {}
        text = (data.get('text') or '')
        body = b'ID3\x03\x00\x00\x00\x00\x00\x00' + text[:64].encode('utf-8', 'replace')
        return Response(body, mimetype='audio/mpeg')

    @app.route('/health')
    def health():
        auth = request.headers.get('Authorization', '')
        if require_token and auth != f"Bearer {INJECTED_TOKEN}":
            return Response('forbidden', status=403)
        return {'status': 'ok'}

    return app


def _start_stub(app):
    """Start a Flask stub on an ephemeral localhost port; return (base_url, shutdown)."""
    from werkzeug.serving import make_server
    srv = make_server('127.0.0.1', 0, app)
    port = srv.server_port
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    # NOTE: http:// (not https://). The real POLLY_TTS_URL in cloud is https://,
    # which is what triggers the token path; here we force the token path via the
    # injected _identity_token_fn regardless of scheme (see _load_module).
    return f"http://127.0.0.1:{port}", srv.shutdown


def _mock_missing_modules():
    mocks = {}
    for mod_name in ["boto3", "psycopg2", "psycopg2.errors", "psycopg2.extras",
                     "flask_cors", "blobstorage"]:
        if mod_name not in sys.modules:
            m = MagicMock()
            if mod_name == "flask_cors":
                m.CORS = lambda app, **kw: None
            if mod_name == "psycopg2":
                m.errors = MagicMock()
            sys.modules[mod_name] = m
            mocks[mod_name] = m
    return mocks


def _cleanup_mocks(mocks):
    for mod_name in mocks:
        if sys.modules.get(mod_name) is mocks[mod_name]:
            del sys.modules[mod_name]


def _load_module(polly_url, tours_dir):
    """Import a fresh copy of the real service with env pointed at the stub.

    NOTE: `requests` is NOT mocked — the app makes a real localhost HTTP call to
    the stub. boto3/psycopg2/blobstorage are mocked (no DB/R2)."""
    os.environ["POLLY_TTS_URL"] = polly_url
    os.environ["TOUR_STORAGE_MODE"] = "cloud"       # exercise the R2 branch guard
    os.environ["BLOB_STORAGE_TYPE"] = "database"     # sentinel; we monkeypatch anyway
    os.environ.setdefault("DATABASE_URL", "postgresql://x:y@localhost:5433/audiotours")
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
    if SERVICE_DIR not in sys.path:
        sys.path.insert(0, SERVICE_DIR)
    mocks = _mock_missing_modules()
    try:
        mod_name = "tour_editing_phase2_gcs5e_under_test"
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        spec = importlib.util.spec_from_file_location(mod_name, SERVICE_FILE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        _cleanup_mocks(mocks)

    mod.TOURS_DIR = tours_dir
    return mod


def _seed_source_tour(tours_dir, tour_id):
    """Create a minimal on-disk source tour with one stop that has audio."""
    tour_path = os.path.join(tours_dir, tour_id)
    os.makedirs(tour_path, exist_ok=True)
    with open(os.path.join(tour_path, "audio_1.txt"), "w", encoding="utf-8") as f:
        f.write("Original stop text.")
    with open(os.path.join(tour_path, "audio_1.mp3"), "wb") as f:
        f.write(b"ID3\x03\x00\x00original-audio")
    with open(os.path.join(tour_path, "tour_content.txt"), "w", encoding="utf-8") as f:
        f.write("Tour content.")
    return tour_path


# ── RED: pre-fix generator (bare post, no token) yields a missing MP3 ─────────
def test_red_prefix_generator():
    print("\n[RED] Pre-fix generator (no identity token) -> missing audio_1.mp3")
    import requests
    from pathlib import Path

    polly_app = _make_polly_stub_app(require_token=True)
    base, shutdown = _start_stub(polly_app)
    try:
        # Reconstruct the shipped (pre-fix) behaviour: bare requests.post with no
        # Authorization header; on a non-200 return ("error", []) and let the
        # caller ignore it (so no MP3 is written but the build "succeeds").
        def prefix_generate(tour_path, stop_number, text):
            try:
                r = requests.post(f"{base}/synthesize",
                                  json={"text": text, "voice_id": "Tatyana", "format": "mp3"},
                                  timeout=10)
                if r.status_code == 200:
                    with open(tour_path / f"audio_{stop_number}.mp3", "wb") as f:
                        f.write(r.content)
                    return "tts_generated"
                return "error"   # <- ignored by caller in the shipped bug
            except Exception:
                return "error"

        build = Path(tempfile.mkdtemp())
        with open(build / "audio_1.txt", "w", encoding="utf-8") as f:
            f.write("Edited Russian stop.")
        result = prefix_generate(build, 1, "Отредактированная остановка.")
        mp3 = build / "audio_1.mp3"
        print(f"  pre-fix generator returned {result!r}; audio_1.mp3 exists={mp3.exists()}")
        check("RED: pre-fix generator gets 403 (no token) and writes NO audio_1.mp3",
              result == "error" and not mp3.exists(),
              f"result={result!r} mp3_exists={mp3.exists()}")
        shutil.rmtree(build, ignore_errors=True)
    finally:
        shutdown()


# ── GREEN: real app, token injected, auth-requiring stub ──────────────────────
def test_green_real_app():
    print("\n[GREEN] Real bulk-save with injected identity token")
    tours_dir = tempfile.mkdtemp()
    # (a) success case: stub requires token, app injects it.
    polly_app = _make_polly_stub_app(require_token=True)
    base, shutdown = _start_stub(polly_app)
    mod = None
    try:
        mod = _load_module(base, tours_dir)

        # Inject the production token seam so the token path is really exercised
        # regardless of http/https scheme, and force auth headers onto the call.
        called_audiences = []

        def fake_token(audience):
            called_audiences.append(audience)
            return INJECTED_TOKEN

        mod._identity_token_fn = fake_token
        # The stub is http://; make the auth wrapper attach the header anyway so
        # the token path runs against the local stub (production POLLY_TTS_URL is
        # https:// and would attach it without this).
        _orig_auth_headers_for = mod._auth_headers_for
        mod._auth_headers_for = lambda url: (
            {"Authorization": f"Bearer {mod._get_identity_token(url)}"}
            if mod._get_identity_token(url) else {}
        )

        # Record R2 activity: neither should fire on the success path either
        # (source stop is regenerated, but this is volume-independent); we mainly
        # assert on the FAILURE path below. Use a recording blob storage.
        uploaded = []
        recorded_rows = []

        class RecordingStorage:
            def upload(self, key, data):
                uploaded.append((key, len(data)))

        mod._get_blob_storage = lambda: RecordingStorage()
        mod._record_edit_blob = lambda new_id, src_id, uri: recorded_rows.append((new_id, src_id, uri))
        mod._get_source_content_language = lambda tid: "ru"
        mod.has_custom_audio = lambda *a, **k: None
        mod.cleanup_tmp_tour_path = lambda p: None
        # comprehend is mocked; skip language detection (fail-open) so the save
        # is not blocked by a bogus MagicMock language code.
        mod._detect_text_language = lambda text: None
        tour_id = "src-tour-ru"
        src_dir = _seed_source_tour(tours_dir, tour_id)
        # Cloud mode's resolver reads from the DB; point it at our seeded dir so
        # the test needs no Postgres. The R2 UPLOAD branch still runs for real.
        from pathlib import Path as _P
        mod.resolve_tour_to_directory = lambda tid: _P(src_dir)

        client = mod.app.test_client()
        body = {"stops": [{"stop_number": 1, "text": "Отредактированная остановка музея.",
                           "action": "modify", "generate_audio_from_text": True}]}
        r = client.post(f"/tour/{tour_id}/bulk-save", json=body)
        js = r.get_json() or {}
        print(f"  success-case save -> {r.status_code} status={js.get('status')} "
              f"token_audiences={called_audiences} r2_uploads={len(uploaded)}")

        check("GREEN(a): save returns 200", r.status_code == 200, f"got {r.status_code} {js}")
        check("GREEN(a): token path exercised (identity token requested)",
              len(called_audiences) >= 1, f"audiences={called_audiences}")

        # Prove the edited stop has audio in the persisted ZIP (the ZIP is
        # created on disk before the R2 upload; find it under tours_dir).
        mp3_ok = False
        zip_found = None
        for root, _dirs, files in os.walk(tours_dir):
            for fn in files:
                if fn.endswith(".zip"):
                    zip_found = os.path.join(root, fn)
        if zip_found:
            with zipfile.ZipFile(zip_found) as zf:
                names = zf.namelist()
                if "audio_1.mp3" in names:
                    mp3_ok = zf.getinfo("audio_1.mp3").file_size > 0
                print(f"  built ZIP {os.path.basename(zip_found)} names={names}")
        check("GREEN(a): edited stop audio_1.mp3 present and > 0 bytes in built tour",
              mp3_ok, f"zip={zip_found}")
        check("GREEN(a): R2 upload + mapping row happened on success (cloud mode)",
              len(uploaded) == 1 and len(recorded_rows) == 1,
              f"uploads={uploaded} rows={recorded_rows}")
    finally:
        shutdown()

    # (b) failure case: Polly denies all (403) -> AUDIO_GENERATION_FAILED, no R2.
    tours_dir2 = tempfile.mkdtemp()
    polly_deny = _make_polly_stub_app(require_token=True, deny_all=True)
    base2, shutdown2 = _start_stub(polly_deny)
    try:
        mod2 = _load_module(base2, tours_dir2)
        mod2._identity_token_fn = lambda audience: INJECTED_TOKEN
        mod2._auth_headers_for = lambda url: {"Authorization": f"Bearer {INJECTED_TOKEN}"}

        uploaded2 = []
        recorded_rows2 = []

        class RecordingStorage2:
            def upload(self, key, data):
                uploaded2.append((key, len(data)))

        mod2._get_blob_storage = lambda: RecordingStorage2()
        mod2._record_edit_blob = lambda new_id, src_id, uri: recorded_rows2.append((new_id, src_id, uri))
        mod2._get_source_content_language = lambda tid: "ru"
        mod2.has_custom_audio = lambda *a, **k: None
        mod2.cleanup_tmp_tour_path = lambda p: None
        mod2._detect_text_language = lambda text: None

        tour_id2 = "src-tour-ru-2"
        src_dir2 = _seed_source_tour(tours_dir2, tour_id2)
        from pathlib import Path as _P2
        mod2.resolve_tour_to_directory = lambda tid: _P2(src_dir2)

        client2 = mod2.app.test_client()
        body2 = {"stops": [{"stop_number": 1, "text": "Новый текст остановки, который нужно озвучить.",
                            "action": "modify", "generate_audio_from_text": True}]}
        r2 = client2.post(f"/tour/{tour_id2}/bulk-save", json=body2)
        js2 = r2.get_json() or {}
        print(f"  polly-down save -> {r2.status_code} code={js2.get('error_code')} "
              f"stop={js2.get('stop_number')} r2_uploads={len(uploaded2)} rows={len(recorded_rows2)}")

        check("GREEN(b): Polly 403 -> save is 4xx/5xx (not 200)",
              r2.status_code >= 400, f"got {r2.status_code} {js2}")
        check("GREEN(b): error_code == AUDIO_GENERATION_FAILED",
              js2.get("error_code") == "AUDIO_GENERATION_FAILED", f"got {js2}")
        check("GREEN(b): NO R2 object created on failure",
              len(uploaded2) == 0, f"uploads={uploaded2}")
        check("GREEN(b): NO tour_edit_blobs row created on failure",
              len(recorded_rows2) == 0, f"rows={recorded_rows2}")
    finally:
        shutdown2()


def main():
    print("\n" + "=" * 70)
    print("test_gcs5e_polly_auth_and_fail.py")
    print("GCS-5E: authenticate Polly + never report success on TTS failure")
    print("=" * 70)

    test_red_prefix_generator()
    test_green_real_app()

    print(f"\n{'=' * 70}")
    print(f"Results: {PASS_COUNT} passed, {FAIL_COUNT} failed")
    print("=" * 70)
    sys.exit(1 if FAIL_COUNT > 0 else 0)


if __name__ == "__main__":
    main()
