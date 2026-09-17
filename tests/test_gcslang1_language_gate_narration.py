#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_gcslang1_language_gate_narration.py — GCS-LANG1 red->green guard.
======================================================================
The DEPLOYED editing service (tour_editing_phase2.py, image tour-editing:v3)
runs the language gate over the ENTIRE stop blob:

    detected = _detect_text_language(stop_data['text_content'])

The blob carries a Latin metadata header (Coordinates:/Address:/...) and often
Latin place names, plus (here) one English `Orientation:` line. Comprehend sees
mixed scripts and returns a neighbouring language — a Russian narration was
reported as 'cv' (Chuvash, which shares Cyrillic with ru) — so the save is
falsely rejected with LANGUAGE_MISMATCH. An all-Russian body with the same
header passed.

The fix (GCS-LANG1) judges the narration, not the scaffolding:
_narration_for_language_detection() strips the nav header (reusing the GCS-SAN1
_strip_nav_fields_for_tts helper) AND a single leading stop-name line, then
feeds only that to _detect_text_language.

We chose to ALSO drop the leading stop-name line: stop names are frequently
Latin place names even inside a ru/zh/... tour and are exactly the cross-script
noise that misleads the detector. The Orientation: line and every narrative
paragraph are kept; the saved .txt and the TTS input are untouched.

Coverage (acceptance criteria 1 & 2):
  1. RED->GREEN on the exact reported blob (ru narration + Latin header + one
     English Orientation: line). Comprehend is mocked DETERMINISTICALLY (no AWS):
     the mock returns 'cv' for the whole blob (reproducing the bug) and 'ru' for
     the stripped narration. We assert the OLD path (detect on blob) rejects and
     the NEW path (detect on narration) accepts — proven both at the helper
     level AND end-to-end through the real /update-multiple-stops route.
  2. A genuinely wrong-language edit (all-English narration on a ru tour) is
     STILL rejected 400 LANGUAGE_MISMATCH — through the real route. A break-probe
     shows the guard is real: remove the check and the mismatch is NOT rejected.
  Plus: empty / too-short stripped body is NOT rejected (today's fail-open kept).

Heavy deps (boto3, psycopg2, blobstorage, flask_cors) are mocked; Comprehend is
mocked on the loaded module. The harness touches no AWS and no R2. Windows-safe:
utf-8 everywhere; the Cyrillic bodies are built in-process from \\u escapes, so
the source file stays ASCII and no shell handles raw Cyrillic.

Usage:  python tests/test_gcslang1_language_gate_narration.py
"""
import os
import sys
import importlib.util
from unittest.mock import MagicMock

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
        print(f"  FAIL: {name} - {detail}")
        FAIL_COUNT += 1


# ---------------------------------------------------------------------------
# The exact reported blob (built from \u escapes so this file stays ASCII).
#   Line 1: stop name          -> "Кладбище Рикье"      (Cyrillic)
#   Coordinates:/Address:      -> Latin nav header (place name incl. accents)
#   Orientation:               -> English/French, in a ru tour
#   then a multi-paragraph Russian narration
# ---------------------------------------------------------------------------
_STOP_NAME = "\u041a\u043b\u0430\u0434\u0431\u0438\u0449\u0435 \u0420\u0438\u043a\u044c\u0435"
_RU_NARRATION = (
    "\u042d\u0442\u043e \u0441\u0442\u0430\u0440\u0435\u0439\u0448\u0435\u0435 "
    "\u043a\u043b\u0430\u0434\u0431\u0438\u0449\u0435 \u041d\u0438\u0446\u0446\u044b, "
    "\u0433\u0434\u0435 \u043f\u043e\u0445\u043e\u0440\u043e\u043d\u0435\u043d\u044b "
    "\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u044b\u0435 \u0433\u043e\u0440\u043e"
    "\u0436\u0430\u043d\u0435 \u0438 \u043c\u0435\u0446\u0435\u043d\u0430\u0442\u044b.\n"
    "\u0417\u0434\u0435\u0441\u044c \u0446\u0430\u0440\u0438\u0442 \u0442\u0438"
    "\u0448\u0438\u043d\u0430, \u0430 \u0441 \u0445\u043e\u043b\u043c\u0430 "
    "\u043e\u0442\u043a\u0440\u044b\u0432\u0430\u0435\u0442\u0441\u044f \u0432\u0438\u0434 "
    "\u043d\u0430 \u0437\u0430\u043b\u0438\u0432 \u0410\u043d\u0433\u0435\u043b\u043e\u0432."
)
RED_BLOB = (
    _STOP_NAME + "\n"
    "Coordinates: 43.7066, 7.2831\n"
    "Address: Avenue Auguste V\u00e9rola, 06300 Nice, France\n"
    "Orientation: Face l'Imp\u00e9ratrice gate.\n"
    "\n"
    + _RU_NARRATION
)

# A genuine mismatch: all-English narration under the same header, on a ru tour.
ENGLISH_BLOB = (
    "Rimiez Cemetery\n"
    "Coordinates: 43.7066, 7.2831\n"
    "Address: Avenue Auguste V\u00e9rola, 06300 Nice, France\n"
    "Orientation: Face the Empress gate.\n"
    "\n"
    "This is the oldest cemetery in Nice, where notable citizens and patrons "
    "are buried. Silence reigns here, and from the hill a view opens onto the "
    "Bay of Angels below the old town."
)


def _mock_missing_modules():
    mocks = {}
    for mod_name in ["boto3", "psycopg2", "psycopg2.errors", "psycopg2.extras",
                     "flask_cors", "requests", "blobstorage"]:
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


def _load_module():
    os.environ.setdefault("DATABASE_URL", "postgresql://x:y@localhost:5433/audiotours")
    os.environ.setdefault("POLLY_TTS_URL", "http://localhost:5018")
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
    if SERVICE_DIR not in sys.path:
        sys.path.insert(0, SERVICE_DIR)
    mocks = _mock_missing_modules()
    try:
        mod_name = "tour_editing_phase2_gcslang1_under_test"
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        spec = importlib.util.spec_from_file_location(mod_name, SERVICE_FILE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        _cleanup_mocks(mocks)


def _make_comprehend(mapping, default):
    """A deterministic Comprehend stub.

    Classifies the text it is GIVEN by counting Cyrillic vs Latin letters,
    then maps that verdict through `mapping`. This reproduces the reported
    real-world behaviour without AWS:
      - whole blob (Latin header + place name + English Orientation dilute the
        Cyrillic body) -> classified 'mixed-cyrillic' -> mapping returns 'cv'
      - stripped narration (dominantly Cyrillic)        -> 'cyrillic' -> 'ru'
      - all-English narration                            -> 'latin'    -> 'en'
    """
    def _detect(Text=None, **kw):
        t = Text or ""
        cyr = sum(1 for ch in t if '\u0400' <= ch <= '\u04FF')
        lat = sum(1 for ch in t if ('a' <= ch.lower() <= 'z'))
        if cyr == 0:
            verdict = 'latin'
        elif lat == 0:
            verdict = 'cyrillic'
        else:
            # Mixed scripts. If Latin is a large fraction of the letters, the
            # detector wanders to a neighbouring Cyrillic language (the bug).
            ratio = lat / float(cyr + lat)
            verdict = 'mixed-cyrillic' if ratio >= 0.25 else 'cyrillic'
        code = mapping.get(verdict, default)
        return {'Languages': [{'LanguageCode': code, 'Score': 0.99}]}
    stub = MagicMock()
    stub.detect_dominant_language.side_effect = _detect
    return stub


COMPREHEND_MAP = {'mixed-cyrillic': 'cv', 'cyrillic': 'ru', 'latin': 'en'}


# ---------------------------------------------------------------------------
# Criterion 1 (helper level): the detector wanders on the blob, is right on
# the stripped narration.
# ---------------------------------------------------------------------------
def test_helper_red_green():
    print("\n[HELPER red->green] detect on blob -> 'cv' (reject); on narration -> 'ru' (accept)")
    mod = _load_module()
    mod.comprehend_client = _make_comprehend(COMPREHEND_MAP, default='en')

    # RED: current deployed behaviour detected on the whole blob.
    detected_blob = mod._detect_text_language(RED_BLOB)
    print(f"  detect(blob)      -> {detected_blob!r}")
    check("RED: whole-blob detection returns a NON-ru language (the bug)",
          detected_blob is not None and detected_blob != 'ru',
          f"got {detected_blob!r} (expected the mixed-script wander, e.g. 'cv')")

    # GREEN: the fix detects on the stripped narration body.
    narration = mod._narration_for_language_detection(RED_BLOB)
    print(f"  narration fed to detector -> {narration!r}")
    detected_narr = mod._detect_text_language(narration)
    print(f"  detect(narration) -> {detected_narr!r}")
    check("GREEN: narration-only detection returns 'ru' (accept)",
          detected_narr == 'ru', f"got {detected_narr!r}")

    # The stripping removed the nav header AND the leading stop-name line, but
    # kept the Orientation line and the narrative paragraphs.
    check("stripped narration DROPS the leading stop-name line",
          _STOP_NAME not in narration, f"narration={narration!r}")
    check("stripped narration DROPS the Coordinates:/Address: header",
          "Coordinates:" not in narration and "Address:" not in narration,
          f"narration={narration!r}")
    check("stripped narration KEEPS the Orientation: line",
          "Orientation: Face l'Imp\u00e9ratrice gate." in narration,
          f"narration={narration!r}")
    check("stripped narration KEEPS the narrative body",
          "\u0417\u0430\u043b\u0438\u0432 \u0410\u043d\u0433\u0435\u043b\u043e\u0432."[-6:] in narration
          or "\u0410\u043d\u0433\u0435\u043b\u043e\u0432." in narration,
          f"narration={narration!r}")


# ---------------------------------------------------------------------------
# Route-level harness: exercise the REAL /update-multiple-stops through the
# real _bulk_save_core, stopping right after the language gate. We stub only
# the source-directory read, the source language and the persistence core, so
# a save that PASSES the gate returns a stubbed success instead of touching
# any DB / R2 / Polly.
# ---------------------------------------------------------------------------
def _wire_route_harness(mod, save_sentinel):
    from pathlib import Path

    class _FakePath:
        def glob(self, _pat):
            return []  # no existing stops -> original_stops_dict = {}

    mod.resolve_tour_to_directory = lambda tid: _FakePath()
    mod._get_source_content_language = lambda tid: "ru"
    mod.has_custom_audio = lambda *a, **k: False

    def _stub_create(*a, **k):
        save_sentinel.append(True)
        # Shape the success path expects (STORAGE_MODE is local here, so the R2
        # persistence block is skipped and this yields a clean 200).
        return {"new_tour_id": "stub-new-uuid", "tour_path": None}

    mod.create_complete_tour_with_preservation = _stub_create


def _post_blob(mod, blob):
    client = mod.app.test_client()
    body = {"stops": [{"stop_number": 1, "text": blob,
                       "action": "modify", "generate_audio_from_text": True}]}
    r = client.post("/tour/421/update-multiple-stops", json=body)
    return r.status_code, (r.get_json() or {})


def test_route_red_green_and_mismatch():
    print("\n[ROUTE] real /update-multiple-stops through _bulk_save_core (gate only)")
    mod = _load_module()
    mod.comprehend_client = _make_comprehend(COMPREHEND_MAP, default='en')
    saved = []
    _wire_route_harness(mod, saved)

    # Criterion 1 GREEN end-to-end: the reported blob is ACCEPTED (reaches save).
    saved.clear()
    sc, js = _post_blob(mod, RED_BLOB)
    print(f"  RED_BLOB (ru narration + Latin header + EN Orientation) -> {sc} "
          f"{js.get('error_code') or js.get('status')}")
    check("GREEN: reported blob is ACCEPTED after fix (not 400 LANGUAGE_MISMATCH)",
          sc != 400 and js.get('error_code') != 'LANGUAGE_MISMATCH',
          f"got {sc} {js}")
    check("GREEN: accepted save reached the persistence path (gate passed)",
          len(saved) == 1, f"save_sentinel={saved}")

    # Criterion 1 RED proof: with the OLD behaviour (detect on the raw blob) the
    # SAME request is rejected. We reproduce the pre-fix line exactly.
    saved.clear()
    orig_narr = mod._narration_for_language_detection
    try:
        mod._narration_for_language_detection = lambda text: text  # pre-fix: raw blob
        sc_red, js_red = _post_blob(mod, RED_BLOB)
    finally:
        mod._narration_for_language_detection = orig_narr
    print(f"  RED_BLOB under PRE-FIX (detect on raw blob) -> {sc_red} "
          f"{js_red.get('error_code')} detected={js_red.get('detected_language')}")
    check("RED: pre-fix (detect on whole blob) REJECTS the same blob "
          "(so the green result is meaningful)",
          sc_red == 400 and js_red.get('error_code') == 'LANGUAGE_MISMATCH',
          f"got {sc_red} {js_red}")

    # Criterion 2: a genuine mismatch (English narration on a ru tour) is STILL
    # rejected, through the real route with the fix in place.
    saved.clear()
    sc_m, js_m = _post_blob(mod, ENGLISH_BLOB)
    print(f"  ENGLISH_BLOB on ru tour -> {sc_m} {js_m.get('error_code')} "
          f"detected={js_m.get('detected_language')}")
    check("STILL REJECTS: English narration on a ru tour -> 400 LANGUAGE_MISMATCH",
          sc_m == 400 and js_m.get('error_code') == 'LANGUAGE_MISMATCH'
          and js_m.get('detected_language') == 'en',
          f"got {sc_m} {js_m}")
    check("mismatch rejected BEFORE the save (no persistence)",
          len(saved) == 0, f"save_sentinel={saved}")

    # Break-probe: if the language check were removed, the mismatch would NOT be
    # rejected. Prove the guard is real by neutralising the detector and showing
    # the same English blob then sails through to the save.
    saved.clear()
    orig_detect = mod._detect_text_language
    try:
        mod._detect_text_language = lambda text: None  # check disabled
        sc_p, js_p = _post_blob(mod, ENGLISH_BLOB)
    finally:
        mod._detect_text_language = orig_detect
    print(f"  BREAK-PROBE English blob with check disabled -> {sc_p} "
          f"{js_p.get('error_code') or js_p.get('status')}")
    check("BREAK-PROBE: with the check removed the mismatch is NOT rejected "
          "(the guard above is real)",
          sc_p != 400 and js_p.get('error_code') != 'LANGUAGE_MISMATCH'
          and len(saved) == 1,
          f"got {sc_p} {js_p} save_sentinel={saved}")


# ---------------------------------------------------------------------------
# Fail-open: an empty / too-short stripped body must NOT be rejected (keep
# today's behaviour — do not invent a new rejection).
# ---------------------------------------------------------------------------
def test_empty_body_not_rejected():
    print("\n[FAIL-OPEN] header-only / too-short body is NOT rejected")
    mod = _load_module()
    # A real Comprehend would never be asked here (too short), but wire the stub
    # anyway so any call is deterministic.
    mod.comprehend_client = _make_comprehend(COMPREHEND_MAP, default='en')
    saved = []
    _wire_route_harness(mod, saved)

    header_only = (
        _STOP_NAME + "\n"
        "Coordinates: 43.7066, 7.2831\n"
        "Address: Avenue Auguste V\u00e9rola, 06300 Nice, France\n"
    )
    narration = mod._narration_for_language_detection(header_only)
    print(f"  stripped narration -> {narration!r} (len={len(narration)})")
    check("stripped body from a header-only blob is empty/too-short",
          len(narration) < 25, f"narration={narration!r}")

    saved.clear()
    sc, js = _post_blob(mod, header_only)
    print(f"  header-only blob -> {sc} {js.get('error_code') or js.get('status')}")
    check("header-only blob is NOT rejected on language (fail-open kept)",
          sc != 400 or js.get('error_code') != 'LANGUAGE_MISMATCH',
          f"got {sc} {js}")


def main():
    print("\n" + "=" * 70)
    print("test_gcslang1_language_gate_narration.py")
    print("GCS-LANG1: run the language gate on the narration, not the stop blob")
    print("=" * 70)

    test_helper_red_green()
    test_route_red_green_and_mismatch()
    test_empty_body_not_rejected()

    print(f"\n{'=' * 70}")
    print(f"Results: {PASS_COUNT} passed, {FAIL_COUNT} failed")
    print("=" * 70)
    sys.exit(1 if FAIL_COUNT > 0 else 0)


if __name__ == "__main__":
    main()
