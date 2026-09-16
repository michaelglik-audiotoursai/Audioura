#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_gcssan1_narration_and_tts_strip.py — GCS-SAN1 red->green guard.
====================================================================
Two separate faults in the DEPLOYED editing service (tour_editing_phase2.py,
image tour-editing:v2). This guard proves both fixes, exercising the real code
(project pattern D35/D36 — exercise, don't just inspect).

FAULT 1 — a filename/SQL sanitiser ran over every saved stop's prose:
  sanitize_user_input() turned 'Coordinates:' into 'Coordinates_', collapsed all
  newlines into one line, and deleted apostrophes/quotes (l'Impératrice ->
  lImpératrice). The fix uses sanitize_narration_text(), which preserves
  newlines, colons and apostrophes while keeping the genuinely-useful cleanups.

FAULT 2 — the editing service posted the full text (incl. the metadata header)
  to Polly, so the voice read 'Coordinates: 43.7…' aloud. The generation
  pipeline strips those nav lines first (_strip_nav_fields_for_tts). The fix
  duplicates that helper here and applies it to the /synthesize payload ONLY;
  the .txt on disk keeps every line.

Coverage (acceptance criteria):
  1. Round-trip on a real tour (local seeded dir + MinIO/R2-free harness):
     edit one stop, save, read back audio_N.txt — keeps newlines, colons and
     apostrophes and matches the shape of an untouched stop.
  2. Red -> green on the sanitiser: the OLD sanitize_user_input mangles the
     prose; the NEW sanitize_narration_text does not. Both printed.
  3. TTS payload excludes nav lines and nothing else — asserted on the exact
     text captured by a Polly stub: no Coordinates:/Address: line, but the stop
     name, Orientation: and all narrative paragraphs still present.
  4. Safety still enforced, proven by a break-probe: <script>…</script>,
     javascript: and on*= are stripped, and text over 10,000 chars is capped.

Heavy deps (boto3, psycopg2, blobstorage) are mocked; the Polly stub runs on
localhost. The harness never touches r2.cloudflarestorage.com. Windows-safe:
utf-8 on every read/write; the request body is built in-process (no shell).

Usage:  python tests/test_gcssan1_narration_and_tts_strip.py
"""
import os
import sys
import zipfile
import shutil
import tempfile
import threading
import importlib.util
from unittest.mock import MagicMock

SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE_FILE = os.path.join(SERVICE_DIR, "tour_editing_phase2.py")

INJECTED_TOKEN = "test-identity-token-sansan1"

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


# A realistic edited RU stop: name line, nav header (Coordinates/Address/…),
# an Orientation line and narrative paragraphs. Contains a French apostrophe
# (l'Impératrice) and colons that MUST survive in the saved .txt.
EDITED_STOP_TEXT = (
    "Памятник Императрице\n"
    "Address: Promenade des Anglais, Nice\n"
    "Coordinates: 43.7066, 7.2831\n"
    "Type/Specialty: Monument\n"
    "Specific Examples: statue de l'Impératrice\n"
    "Operational Details: open daily\n"
    "Orientation: Смотрите на набережную.\n"
    "\n"
    "Здесь стояла статуя de l'Impératrice, символ эпохи.\n"
    "Второй абзац повествования продолжает историю."
)


# ── Polly stub that captures the exact synthesise payload ─────────────────────
def _make_capturing_polly_stub(captured):
    from flask import Flask, request, Response
    app = Flask(__name__)

    @app.route('/synthesize', methods=['POST'])
    def synthesize():
        data = request.get_json(silent=True) or {}
        captured.append(data.get('text') or '')
        text = data.get('text') or ''
        body = b'ID3\x03\x00\x00\x00\x00\x00\x00' + text[:64].encode('utf-8', 'replace')
        return Response(body, mimetype='audio/mpeg')

    @app.route('/health')
    def health():
        return {'status': 'ok'}

    return app


def _start_stub(app):
    from werkzeug.serving import make_server
    srv = make_server('127.0.0.1', 0, app)
    port = srv.server_port
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
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
    os.environ["POLLY_TTS_URL"] = polly_url
    os.environ["TOUR_STORAGE_MODE"] = "cloud"
    os.environ["BLOB_STORAGE_TYPE"] = "database"
    os.environ.setdefault("DATABASE_URL", "postgresql://x:y@localhost:5433/audiotours")
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
    if SERVICE_DIR not in sys.path:
        sys.path.insert(0, SERVICE_DIR)
    mocks = _mock_missing_modules()
    try:
        mod_name = "tour_editing_phase2_gcssan1_under_test"
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
    """Seed a source tour with one UNTOUCHED stop that has the same shape
    (name + nav header + Orientation + narrative) so we can compare shapes."""
    tour_path = os.path.join(tours_dir, tour_id)
    os.makedirs(tour_path, exist_ok=True)
    with open(os.path.join(tour_path, "audio_1.txt"), "w", encoding="utf-8") as f:
        f.write(
            "Исходная остановка\n"
            "Address: Quai des États-Unis, Nice\n"
            "Coordinates: 43.6951, 7.2758\n"
            "Orientation: Оригинальная ориентация.\n"
            "\n"
            "Оригинальный абзац повествования."
        )
    with open(os.path.join(tour_path, "audio_1.mp3"), "wb") as f:
        f.write(b"ID3\x03\x00\x00original-audio")
    with open(os.path.join(tour_path, "tour_content.txt"), "w", encoding="utf-8") as f:
        f.write("Tour content.")
    return tour_path


# ── Criterion 2: red -> green on the sanitiser itself ─────────────────────────
def test_sanitiser_red_green():
    print("\n[SANITISER red->green] old mangles prose, new preserves it")
    mod = _load_module("http://127.0.0.1:1", tempfile.mkdtemp())  # url unused here

    old = mod.sanitize_user_input(EDITED_STOP_TEXT)
    new = mod.sanitize_narration_text(EDITED_STOP_TEXT)

    print("  --- OLD sanitize_user_input output (RED) ---")
    print("  " + repr(old))
    print("  --- NEW sanitize_narration_text output (GREEN) ---")
    print("  " + repr(new))

    # RED: the old function demonstrably mangles the prose.
    check("RED: old collapses newlines (one unbroken line)",
          "\n" not in old, f"old still had newlines: {old!r}")
    check("RED: old turns 'Coordinates:' into 'Coordinates_'",
          "Coordinates_" in old and "Coordinates:" not in old,
          f"old={old!r}")
    check("RED: old deletes the apostrophe in l'Impératrice",
          "lImpératrice" in old and "l'Impératrice" not in old,
          f"old={old!r}")

    # GREEN: the new function preserves structure and characters.
    check("GREEN: new preserves newlines", "\n" in new, f"new={new!r}")
    check("GREEN: new preserves 'Coordinates: 43.7066, 7.2831'",
          "Coordinates: 43.7066, 7.2831" in new, f"new={new!r}")
    check("GREEN: new preserves the apostrophe in l'Impératrice",
          "l'Impératrice" in new, f"new={new!r}")
    check("GREEN: new preserves the stop name and Orientation line",
          "Памятник Императрице" in new and "Orientation:" in new, f"new={new!r}")


# ── Criterion 4: safety still enforced, proven by a break-probe ───────────────
def test_safety_enforced():
    print("\n[SAFETY] XSS stripped and 10k cap enforced (break-probe backs each)")
    mod = _load_module("http://127.0.0.1:1", tempfile.mkdtemp())

    xss = ("Стоп <script>alert('x')</script> тут "
           "<a href=\"javascript:evil()\">клик</a> "
           "<div onclick=\"steal()\">x</div>")
    cleaned = mod.sanitize_narration_text(xss)
    print("  cleaned XSS -> " + repr(cleaned))
    check("<script>…</script> removed",
          "<script" not in cleaned.lower() and "alert(" not in cleaned,
          f"cleaned={cleaned!r}")
    check("javascript: removed", "javascript:" not in cleaned.lower(), f"cleaned={cleaned!r}")
    check("on*= handler removed", "onclick=" not in cleaned.lower(), f"cleaned={cleaned!r}")

    # Break-probe: if the XSS stripping were removed, the assertion above would
    # fail — prove that by running the same input through a stripped-down cleaner.
    def _no_xss_strip(t):
        # everything EXCEPT the three XSS rules (control chars + cap only)
        import re as _re
        t = _re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', t)
        return t[:10000]
    probe = _no_xss_strip(xss)
    check("BREAK-PROBE: without XSS stripping, <script> survives (test is real)",
          "<script" in probe.lower(),
          "probe unexpectedly clean — the safety assertions would be hollow")

    # 10k cap
    long_text = "а" * 15000
    capped = mod.sanitize_narration_text(long_text)
    print(f"  len(input)=15000 -> len(output)={len(capped)}")
    check("text longer than 10,000 chars is capped to 10,000",
          len(capped) == 10000, f"got {len(capped)}")


# ── Criteria 1 & 3: real round-trip + exact TTS payload ───────────────────────
def test_roundtrip_and_tts_payload():
    print("\n[ROUND-TRIP] edit one stop, save, read back audio_1.txt; inspect Polly payload")
    tours_dir = tempfile.mkdtemp()
    captured = []
    polly_app = _make_capturing_polly_stub(captured)
    base, shutdown = _start_stub(polly_app)
    try:
        mod = _load_module(base, tours_dir)

        # Exercise the auth seam so the localhost stub receives the call.
        mod._identity_token_fn = lambda audience: INJECTED_TOKEN
        mod._auth_headers_for = lambda url: {"Authorization": f"Bearer {INJECTED_TOKEN}"}

        uploaded = []

        class RecordingStorage:
            def upload(self, key, data):
                uploaded.append((key, len(data)))

        mod._get_blob_storage = lambda: RecordingStorage()
        mod._record_edit_blob = lambda new_id, src_id, uri: None
        mod._get_source_content_language = lambda tid: "ru"
        mod.has_custom_audio = lambda *a, **k: None
        mod.cleanup_tmp_tour_path = lambda p: None
        mod._detect_text_language = lambda text: None

        tour_id = "src-tour-ru-sansan1"
        src_dir = _seed_source_tour(tours_dir, tour_id)
        from pathlib import Path as _P
        mod.resolve_tour_to_directory = lambda tid: _P(src_dir)

        client = mod.app.test_client()
        body = {"stops": [{"stop_number": 1, "text": EDITED_STOP_TEXT,
                           "action": "modify", "generate_audio_from_text": True}]}
        r = client.post(f"/tour/{tour_id}/bulk-save", json=body)
        js = r.get_json() or {}
        check("save returns 200", r.status_code == 200, f"got {r.status_code} {js}")

        # Locate and open the built ZIP; read back audio_1.txt.
        zip_found = None
        for root, _dirs, files in os.walk(tours_dir):
            for fn in files:
                if fn.endswith(".zip"):
                    zip_found = os.path.join(root, fn)
        saved_txt = None
        if zip_found:
            with zipfile.ZipFile(zip_found) as zf:
                if "audio_1.txt" in zf.namelist():
                    saved_txt = zf.read("audio_1.txt").decode("utf-8")
        print("  --- saved audio_1.txt (round-trip) ---")
        print("  " + repr(saved_txt))

        # Criterion 1: saved .txt keeps newlines, colons and apostrophes and
        # matches the shape of an untouched stop.
        check("saved .txt is not None", saved_txt is not None, f"zip={zip_found}")
        if saved_txt is not None:
            check("saved .txt keeps newlines (multi-line)",
                  "\n" in saved_txt and saved_txt.count("\n") >= 5, f"txt={saved_txt!r}")
            check("saved .txt keeps 'Coordinates: 43.7066, 7.2831'",
                  "Coordinates: 43.7066, 7.2831" in saved_txt, f"txt={saved_txt!r}")
            check("saved .txt keeps the apostrophe in l'Impératrice",
                  "l'Impératrice" in saved_txt, f"txt={saved_txt!r}")
            # shape: an untouched stop has name + Address:/Coordinates: header +
            # Orientation: + a narrative paragraph. Assert the same shape here.
            for label in ("Address:", "Coordinates:", "Orientation:"):
                check(f"saved .txt matches untouched shape (has '{label}')",
                      label in saved_txt, f"txt={saved_txt!r}")
            # Byte-identity, newline-agnostic. On Windows, Python's text-mode
            # open() translates '\n' -> '\r\n' on write; the deployed container
            # is Linux, where no translation happens. Normalising CRLF->LF here
            # asserts the deployed behaviour without touching the pipeline's
            # file-writing (out of scope for this task).
            check("saved .txt is content-identical to the submitted edit, "
                  "newline-agnostic (preservation-by-exact-text holds)",
                  saved_txt.replace("\r\n", "\n") == EDITED_STOP_TEXT,
                  f"txt={saved_txt!r}")

        # Criterion 3: exact Polly payload — nav lines gone, everything else in.
        check("Polly received exactly one synthesise call", len(captured) == 1,
              f"captured={captured}")
        if captured:
            tts = captured[0]
            print("  --- exact text sent to Polly ---")
            print("  " + repr(tts))
            check("TTS payload has NO 'Coordinates:' line",
                  not any(l.strip().lower().startswith("coordinates:")
                          for l in tts.split("\n")), f"tts={tts!r}")
            check("TTS payload has NO 'Address:' line",
                  not any(l.strip().lower().startswith("address:")
                          for l in tts.split("\n")), f"tts={tts!r}")
            check("TTS payload has NO 'Type/Specialty:'/'Specific Examples:'/"
                  "'Operational Details:' lines",
                  not any(l.strip().lower().startswith(p) for l in tts.split("\n")
                          for p in ("type/specialty:", "specific examples:",
                                    "operational details:")),
                  f"tts={tts!r}")
            check("TTS payload KEEPS the stop name", "Памятник Императрице" in tts,
                  f"tts={tts!r}")
            check("TTS payload KEEPS the Orientation line",
                  "Orientation: Смотрите на набережную." in tts, f"tts={tts!r}")
            check("TTS payload KEEPS both narrative paragraphs",
                  "символ эпохи." in tts and "продолжает историю." in tts,
                  f"tts={tts!r}")
            # nothing-else: the TTS text must equal the saved text minus exactly
            # the five nav lines (order + all other lines preserved). Compared
            # newline-agnostic (Windows text-mode write adds '\r'; Linux does not).
            if saved_txt is not None:
                saved_lf = saved_txt.replace("\r\n", "\n")
                expected_tts = "\n".join(
                    l for l in saved_lf.split("\n")
                    if not mod._NAV_LABEL_RE.match(l))
                check("TTS payload == saved .txt minus ONLY the nav lines "
                      "(nothing else changed)",
                      tts.replace("\r\n", "\n") == expected_tts,
                      f"tts={tts!r}\nexpected={expected_tts!r}")
    finally:
        shutdown()
        shutil.rmtree(tours_dir, ignore_errors=True)


def main():
    print("\n" + "=" * 70)
    print("test_gcssan1_narration_and_tts_strip.py")
    print("GCS-SAN1: stop mangling narration + stop speaking the metadata header")
    print("=" * 70)

    test_sanitiser_red_green()
    test_safety_enforced()
    test_roundtrip_and_tts_payload()

    print(f"\n{'=' * 70}")
    print(f"Results: {PASS_COUNT} passed, {FAIL_COUNT} failed")
    print("=" * 70)
    sys.exit(1 if FAIL_COUNT > 0 else 0)


if __name__ == "__main__":
    main()
