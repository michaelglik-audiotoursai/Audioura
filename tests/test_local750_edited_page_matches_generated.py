"""
test_local750_edited_page_matches_generated.py — LOCAL-750 (B) red->green.
===========================================================================
Michael's retest (community 10, tour 716, 2026-10-23): after LOCAL-747 the
edited page HAD map buttons, but it still did not look like a generated tour —
"the map sign ... not at the beginning of the title of the stop as it should
and does for tours, but in the end of the title, and 'Audio N' is not in the
stop names like in other tours."

Cause: the generator (tour_generation_modernized.generate_html_with_external_audio)
and the editor (tour_editing_phase2.create_clean_html) each wrote their OWN
per-stop markup, page header and CSS, so the two drifted.

Fix (B): the per-stop block, the page header and the CSS live once in
tour_html_map and BOTH services call it. The red assertions below pin the three
things Michael called out and prove the two pages agree stop-for-stop:

  * every stop name carries ": Audio N",
  * the map button comes right AFTER the stop <h3> (before the <audio>),
  * the page <h1> is the tour name (not the generic "Audio Tour"),
  * the edited and generated stop blocks are identical for the same 3 stops.

Heavy deps are mocked so the edit service imports (reusing the LOCAL-747 test
harness helpers). Windows-safe: utf-8 on every read/write.

Usage:  python tests/test_local750_edited_page_matches_generated.py
"""
import os
import re
import sys
import tempfile
from pathlib import Path

SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SERVICE_DIR not in sys.path:
    sys.path.insert(0, SERVICE_DIR)

# Reuse the LOCAL-747 harness: module loader, mocks, 3-stop writer, STOP_TEXT.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_local747_edit_save_html_and_download import (  # noqa: E402
    load_module_from_file, _write_three_stop_tour, STOP_TEXT,
    EDIT_SERVICE_FILE, GEN_SERVICE_FILE, check,
)

import test_local747_edit_save_html_and_download as _h  # for PASS/FAIL counters


def _extract_stop_blocks(html):
    """Return the list of per-stop <div class="audio-item">...</div> blocks."""
    return re.findall(r'<div class="audio-item">.*?</div>', html, re.DOTALL)


def _generated_html(tour_name):
    gen = load_module_from_file(GEN_SERVICE_FILE,
                                "tour_generation_modernized_l750")
    tour_data = {
        "tour_name": tour_name,
        "tour_category": "biking",
        "text_content": [STOP_TEXT.format(n=1), STOP_TEXT.format(n=2),
                         STOP_TEXT.format(n=3)],
    }
    return gen.generate_html_with_external_audio(tour_data)


def _edited_html(tour_name):
    edit = load_module_from_file(EDIT_SERVICE_FILE,
                                 "tour_editing_phase2_l750")
    with tempfile.TemporaryDirectory() as td:
        tour_dir = Path(td) / "edited_tour"
        _write_three_stop_tour(tour_dir, category_line="Tour-Category: biking")
        # Pass the same display name so the page <h1> matches the generator.
        edit.create_clean_html(tour_dir, {1, 2, 3}, tour_name=tour_name)
        return (tour_dir / "index.html").read_text(encoding="utf-8")


def test_audio_n_suffix_and_button_position():
    print("\n[1] Edited stop names carry ': Audio N' and the button is after "
          "the <h3>")
    html = _edited_html("Harbor Bike Loop")

    # ": Audio 1/2/3" present in the stop names.
    for n in (1, 2, 3):
        check(f"edited page has ': Audio {n}' in a stop <h3>",
              re.search(rf'<h3>[^<]*: Audio {n}</h3>', html) is not None,
              f"missing ': Audio {n}' heading")

    # Button right after the <h3> (before the <audio>): the first thing after
    # </h3> in each audio-item is the map-btn.
    blocks = _extract_stop_blocks(html)
    check("edited page renders 3 stop blocks", len(blocks) == 3,
          f"got {len(blocks)}")
    for i, blk in enumerate(blocks, 1):
        after_h3 = blk.split("</h3>", 1)[1] if "</h3>" in blk else ""
        btn_pos = after_h3.find('class="map-btn"')
        audio_pos = after_h3.find("<audio")
        check(f"stop {i}: map button comes before the <audio>",
              btn_pos != -1 and (audio_pos == -1 or btn_pos < audio_pos),
              f"btn_pos={btn_pos}, audio_pos={audio_pos}")


def test_header_is_tour_name():
    print("\n[2] The edited page <h1> is the tour name, not 'Audio Tour'")
    html = _edited_html("Harbor Bike Loop")
    h1 = re.search(r"<h1>(.*?)</h1>", html, re.DOTALL)
    check("edited page has an <h1>", h1 is not None, "no <h1>")
    if h1:
        text = h1.group(1).strip()
        check("edited <h1> is the tour name (title-cased)",
              text == "Harbor Bike Loop", f"got {text!r}")
        check("edited <h1> is NOT the generic 'Audio Tour'",
              text != "Audio Tour", "still the generic header")


def test_edited_matches_generated_stop_blocks():
    print("\n[3] Edited and generated stop blocks are identical for the same "
          "3 stops")
    name = "Harbor Bike Loop"
    gen_blocks = _extract_stop_blocks(_generated_html(name))
    edit_blocks = _extract_stop_blocks(_edited_html(name))
    check("both pages have 3 stop blocks",
          len(gen_blocks) == 3 and len(edit_blocks) == 3,
          f"gen={len(gen_blocks)}, edit={len(edit_blocks)}")
    for i, (g, e) in enumerate(zip(gen_blocks, edit_blocks), 1):
        check(f"stop {i} block is byte-for-byte identical", g == e,
              f"\n  GEN : {g!r}\n  EDIT: {e!r}")


def test_voice_control_survives():
    print("\n[4] The edited page keeps a working voice-control player")
    html = _edited_html("Harbor Bike Loop")
    check("edited page keeps playAudio handler", "playAudio" in html,
          "voice control lost")
    check("edited page keeps openMap bridge", "openMap(" in html,
          "openMap lost")


def main():
    print("\n" + "=" * 70)
    print("test_local750_edited_page_matches_generated.py")
    print("LOCAL-750 (B): edited page looks exactly like a generated one")
    print("=" * 70)

    test_audio_n_suffix_and_button_position()
    test_header_is_tour_name()
    test_edited_matches_generated_stop_blocks()
    test_voice_control_survives()

    print(f"\n{'=' * 70}")
    print(f"Results: {_h.PASS_COUNT} passed, {_h.FAIL_COUNT} failed")
    print("=" * 70)
    sys.exit(1 if _h.FAIL_COUNT > 0 else 0)


if __name__ == "__main__":
    main()
