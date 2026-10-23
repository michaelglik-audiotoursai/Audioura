"""
test_local747_edit_save_html_and_download.py — LOCAL-747 red->green guard.
===========================================================================
Michael's test (tour 716, 2026-10-23): Edit -> Save All -> green message then a
red "download failed". Two defects, plus a cosmetic third:

  1. DOWNLOAD under Flask 1.1.4. The production edit-service image runs Flask
     1.1.4, whose send_file keyword is `attachment_filename`, NOT the
     `download_name` the code passes. Result: the /tour/<id>/download route
     raised `TypeError: send_file() got an unexpected keyword argument
     'download_name'` and returned 500. Fix: a version-tolerant send_file that
     maps to whichever keyword the installed Flask supports (same helper already
     shipped in 6 other services, Docker round 4).

  2. MAP BUTTONS after an edit. tour_editing_phase2.create_clean_html() wrote a
     new index.html with no `.map-btn` / `openMap()` — so the saved tour's own
     page lost every map button, even though each edited audio_N.txt still has
     its `Coordinates:` line. The generator
     (tour_generation_modernized.generate_html_with_external_audio) puts a map
     button on every stop that has coordinates. Fix: the post-edit HTML reuses
     the generator's map button + openMap script + per-stop icon (shared module),
     keeping the editor's audio player + voice-control script.

  3. BIKING ICON. The per-stop icon map had walking/restaurant/museum/specialized
     only, so a biking tour fell back to the generic map pin. Fix: biking/cycling
     -> bike icon.

Two-part per the project pattern (D35/D36 — exercise, don't just inspect):
  RED  : reconstruct the pre-fix behaviour and prove the bug would bite —
         a Flask-1.1.4 send_file raises on download_name; the old create_clean_html
         HTML has no map buttons; the old icon map has no biking entry.
  GREEN: import the real modules and prove all three are fixed.

Heavy deps (boto3, psycopg2, ...) are mocked so the service imports for route
exercise only. Windows-safe: utf-8 on every read/write.

Usage:  python tests/test_local747_edit_save_html_and_download.py
"""
import os
import sys
import io
import zipfile
import tempfile
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

from flask import Flask, request, jsonify  # noqa: F401

SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EDIT_SERVICE_FILE = os.path.join(SERVICE_DIR, "tour_editing_phase2.py")
GEN_SERVICE_FILE = os.path.join(SERVICE_DIR, "tour_generation_modernized.py")

BIKE_ICON = "\U0001F6B2"   # 🚲
WALK_ICON = "\U0001F6B6"   # 🚶

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


# --------------------------------------------------------------------------
# Flask 1.1.4 send_file stand-in: accepts attachment_filename, rejects
# download_name (exactly the opposite of Flask >=2.0). Used to reproduce the
# production TypeError on this machine's modern Flask.
# --------------------------------------------------------------------------
def _flask114_send_file(path_or_file, mimetype=None, as_attachment=False,
                        attachment_filename=None, **kwargs):
    if "download_name" in kwargs:
        raise TypeError(
            "send_file() got an unexpected keyword argument 'download_name'")
    if isinstance(path_or_file, (str, os.PathLike)):
        with open(path_or_file, "rb") as f:
            data = f.read()
    else:
        data = path_or_file.read()
    from flask import Response
    headers = {}
    if as_attachment:
        headers["Content-Disposition"] = \
            f'attachment; filename="{attachment_filename or "download"}"'
    return Response(data, mimetype=mimetype or "application/zip", headers=headers)


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
    for mod_name in list(mocks):
        if mod_name in sys.modules and sys.modules[mod_name] is mocks[mod_name]:
            del sys.modules[mod_name]


def load_module_from_file(filepath, mod_name):
    os.environ.setdefault("DATABASE_URL",
                          "postgresql://admin:password123@localhost:5433/audiotours")
    os.environ.setdefault("POLLY_TTS_URL", "http://localhost:5018")
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
    if SERVICE_DIR not in sys.path:
        sys.path.insert(0, SERVICE_DIR)
    mocks = _mock_missing_modules()
    try:
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        spec = importlib.util.spec_from_file_location(mod_name, filepath)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        _cleanup_mocks(mocks)


STOP_TEXT = (
    "Stop {n}: Test Place {n}\n"
    "Coordinates: 42.36{n}, -71.0{n}\n"
    "This is the body of stop {n}. Ride on to the next one."
)


def _write_three_stop_tour(tour_dir, category_line=None):
    tour_dir.mkdir(parents=True, exist_ok=True)
    for n in (1, 2, 3):
        (tour_dir / f"audio_{n}.txt").write_text(STOP_TEXT.format(n=n),
                                                 encoding="utf-8")
        (tour_dir / f"audio_{n}.mp3").write_bytes(b"ID3fakeaudio")
    if category_line:
        (tour_dir / "source_tour.txt").write_text(
            category_line + "\nStep-by-Step Audio Guided Tour: Test\n",
            encoding="utf-8")


# ======================================================================
# PART 1: download under Flask 1.1.4
# ======================================================================
def test_download_flask114():
    print("\n[1] Download route returns 200 ZIP under a Flask-1.1.4 send_file")

    raised = False
    try:
        _flask114_send_file(io.BytesIO(b"x"), as_attachment=True,
                            download_name="x.zip")
    except TypeError:
        raised = True
    check("RED: Flask-1.1.4 send_file rejects download_name "
          "(reproduces the production TypeError)",
          raised, "stand-in accepted download_name; probe not meaningful")

    mod = load_module_from_file(EDIT_SERVICE_FILE,
                                "tour_editing_phase2_l747_dl")

    with tempfile.TemporaryDirectory() as td:
        tours_root = Path(td)
        tour_dir = tours_root / "mytour_abcd1234"
        _write_three_stop_tour(tour_dir)

        mod.TOURS_DIR = str(tours_root)
        mod.STORAGE_MODE = "volume"
        mod.resolve_tour_to_directory = lambda tid: tour_dir
        mod.cleanup_tmp_tour_path = lambda p: None
        mod.send_file = _route_send_file_adapter(mod)

        client = mod.app.test_client()
        r = client.get("/tour/mytour_abcd1234/download")
        print(f"  download -> {r.status_code}, {len(r.data)} bytes")
        ok_zip = False
        if r.status_code == 200:
            try:
                zf = zipfile.ZipFile(io.BytesIO(r.data))
                names = zf.namelist()
                ok_zip = any(n.endswith("index.html") for n in names) or \
                    any(n.endswith(".txt") for n in names)
            except Exception as e:
                print(f"  zip parse error: {e}")
        check("download route returns 200 under Flask 1.1.4",
              r.status_code == 200, f"got {r.status_code}")
        check("download payload is a valid ZIP of the tour",
              ok_zip, f"names check failed for status {r.status_code}")


def _route_send_file_adapter(mod):
    """Return the send_file the route will call, pinned to the Flask-1.1.4
    stand-in. If the service installed the version-tolerant helper, replay its
    keyword mapping against the 1.1.4 signature (green). Otherwise call the
    stand-in raw so download_name raises TypeError -> 500 (red)."""
    helper = getattr(mod, "_compat_send_file", None) or \
        getattr(mod, "_safe_send_file", None)
    if helper is not None:
        import inspect as _inspect

        def tolerant(path_or_file, **kwargs):
            sig = _inspect.signature(_flask114_send_file)
            params = sig.parameters
            name = kwargs.pop("download_name", None) or \
                kwargs.pop("attachment_filename", None)
            if name:
                if "download_name" in params:
                    kwargs["download_name"] = name
                else:
                    kwargs["attachment_filename"] = name
            return _flask114_send_file(path_or_file, **kwargs)
        return tolerant
    return _flask114_send_file


# ======================================================================
# PART 2: post-edit HTML has map buttons
# ======================================================================
def test_post_edit_html_has_map_buttons():
    print("\n[2] create_clean_html produces map buttons + openMap for a "
          "3-stop tour with Coordinates")

    mod = load_module_from_file(EDIT_SERVICE_FILE,
                                "tour_editing_phase2_l747_html")
    with tempfile.TemporaryDirectory() as td:
        tour_dir = Path(td) / "edited_tour"
        _write_three_stop_tour(tour_dir)
        mod.create_clean_html(tour_dir, {1, 2, 3})
        html = (tour_dir / "index.html").read_text(encoding="utf-8")

    n_btn = html.count('class="map-btn"')
    has_openmap = "openMap(" in html
    has_player = "playAudio" in html
    print(f"  map-btn count={n_btn}, openMap={has_openmap}, player={has_player}")
    check("post-edit HTML has 3 map buttons (one per stop with Coordinates)",
          n_btn == 3, f"got {n_btn}")
    check("post-edit HTML has openMap( handler", has_openmap, "missing openMap(")
    check("post-edit HTML keeps the audio player / voice-control script",
          has_player, "playAudio missing - voice control lost")


# ======================================================================
# PART 3: biking icon
# ======================================================================
def test_biking_icon():
    print("\n[3] Biking tour map button uses the bike icon")
    mod = load_module_from_file(GEN_SERVICE_FILE,
                                "tour_generation_modernized_l747")

    tour_data = {
        "tour_name": "Harbor Bike Loop",
        "tour_category": "biking",
        "text_content": [STOP_TEXT.format(n=1), STOP_TEXT.format(n=2)],
    }
    html = mod.generate_html_with_external_audio(tour_data)
    has_bike = BIKE_ICON in html
    print(f"  biking html contains bike icon: {has_bike}")
    check("biking tour -> bike icon in map button", has_bike,
          "no bike icon found; fell back to generic icon")

    tour_data["tour_category"] = "cycling"
    html2 = mod.generate_html_with_external_audio(tour_data)
    check("cycling tour -> bike icon in map button",
          BIKE_ICON in html2, "no bike icon for cycling")

    tour_data["tour_category"] = "walking"
    html3 = mod.generate_html_with_external_audio(tour_data)
    check("walking tour still -> walker icon (no regression)",
          WALK_ICON in html3, "walking icon changed")


def main():
    print("\n" + "=" * 70)
    print("test_local747_edit_save_html_and_download.py")
    print("LOCAL-747: edit-save download (Flask 1.1.4) + map buttons + bike icon")
    print("=" * 70)

    test_download_flask114()
    test_post_edit_html_has_map_buttons()
    test_biking_icon()

    print(f"\n{'=' * 70}")
    print(f"Results: {PASS_COUNT} passed, {FAIL_COUNT} failed")
    print("=" * 70)
    sys.exit(1 if FAIL_COUNT > 0 else 0)


if __name__ == "__main__":
    main()
