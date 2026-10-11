"""LOCAL-675 item 1 — bilingual stop headers must render as "<local> (<English>)".

Fixture: ~/Audioura/.continuous_dev/bench/AB17/run_OFF-1.log — the LOCAL-669C
final gate logged `bilingual titles: set 4 '<local> (<English>)' header(s)`, yet
HCMC tours 678/679 delivered "Stop 3: Bác Hồ với thiếu nhi" with no English.

Root cause (offline-provable): PHASE 3B rebuilds every stop with a fresh
`_new_poi()` dict and only carried `verified` across. The `display_title` set by
the gate was dropped, so the PHASE 6 header fell back to the bare `name`. A
second, defensive hole: the LOCAL-22 final sanitizer built its "real header" set
from `name` only, so a correctly-rendered bilingual header could be treated as
injected text and stripped.

These tests reproduce BOTH pieces of logic verbatim (the Phase-3B merge-carry and
the sanitizer predicate) with no network and no paid call.
"""
import os
import re
import unittest

# Real fixture strings from run_OFF-1.log (HCMC, Ho Chi Minh City Museum of Fine Arts).
_VN = "Bác Hồ với thiếu nhi"
_EN = "Uncle Ho with Children"
_BILINGUAL = f"{_VN} ({_EN})"


def _new_poi(name, address=""):
    """Mirror of generate_tour_text._new_poi — note: NO display_title key."""
    return {
        "stop_number": 0,
        "name": (name or "").strip(),
        "address": (address or "").strip(),
        "artist": "",
        "year": "",
        "directions": "",
        "coordinates": "",
        "type_specialty": "",
        "specific_examples": "",
        "operational_details": "",
        "description": "",
        "page_sourced": False,
        "confirmation": "",
    }


def _phase3b_merge_carry(orig, merged):
    """The exact carry-over block from _run_phase_3b after the LOCAL-675 fix."""
    if orig and "verified" in orig:
        merged["verified"] = orig["verified"]
    if orig and (orig.get("display_title") or "").strip():
        merged["display_title"] = orig["display_title"]
    return merged


class TestPhase3BCarriesDisplayTitle(unittest.TestCase):
    """The gate's bilingual display_title must survive the Phase 3B rebuild."""

    def test_display_title_survives_rebuild(self):
        # Gate output: candidate carries the bilingual header on display_title.
        orig = _new_poi(_VN)
        orig["verified"] = True
        orig["display_title"] = _BILINGUAL

        # Phase 3B builds a FRESH dict (no display_title) then carries fields over.
        merged = _new_poi(_VN)
        merged = _phase3b_merge_carry(orig, merged)

        self.assertEqual(merged.get("display_title"), _BILINGUAL,
                         "bilingual header dropped by the Phase 3B rebuild")
        self.assertTrue(merged.get("verified"), "verified must also survive")

    def test_header_build_prefers_display_title(self):
        # Mirror of the PHASE 6 header line: display_title first, else bare name.
        poi = _phase3b_merge_carry(
            {"verified": True, "display_title": _BILINGUAL}, _new_poi(_VN))
        _header_title = (poi.get("display_title") or "").strip() or poi["name"]
        self.assertEqual(f"Stop 3: {_header_title}", f"Stop 3: {_BILINGUAL}")
        self.assertIn(_EN, _header_title, "English gloss must be present")

    def test_monolingual_stop_unaffected(self):
        # A stop with no gate-set display_title falls back to bare name, as before.
        poi = _phase3b_merge_carry({"verified": True}, _new_poi("Em Thúy"))
        _header_title = (poi.get("display_title") or "").strip() or poi["name"]
        self.assertEqual(_header_title, "Em Thúy")


# ── LOCAL-22 sanitizer predicate, reproduced verbatim (post LOCAL-675) ──────────
def _hdr_norm(_x):
    _x = re.sub(r"^Stop\s+\d+:\s*", "", _x or "")
    _x = (_x.replace("\u2019", "'").replace("\u2018", "'")
            .replace("\u201c", '"').replace("\u201d", '"'))
    _x = re.sub(r"\s+by\s+.+$", "", _x)
    _x = re.sub(r",\s*\d{3,4}.*$", "", _x)
    return re.sub(r"\s+", " ", _x).strip().lower()


def _build_sanitizer(poi_list):
    _real_header_set = set()
    for i, poi in enumerate(poi_list):
        _title_variants = {(poi.get("name") or "").strip()}
        _disp = (poi.get("display_title") or "").strip()
        if _disp:
            _title_variants.add(_disp)
        for _tv in _title_variants:
            if not _tv:
                continue
            _h = f"Stop {i + 1}: {_tv}"
            if poi["artist"] and poi["artist"].lower() != "unknown artist":
                _h += f" by {poi['artist']}"
            if poi["year"]:
                _h += f", {poi['year']}"
            _real_header_set.add(_h)
    _real_by_num = {
        i + 1: _hdr_norm((poi.get("display_title") or "").strip() or (poi.get("name") or ""))
        for i, poi in enumerate(poi_list)
    }

    def _is_real_header(_line):
        if _line.strip() in _real_header_set:
            return True
        _m = re.match(r"^Stop\s+(\d+):", _line)
        if not _m:
            return False
        _want = _real_by_num.get(int(_m.group(1)))
        _got = _hdr_norm(_line)
        return bool(_want) and (_got == _want or _got.startswith(_want) or _want.startswith(_got))

    return _is_real_header


class TestLocal22SanitizerKeepsBilingual(unittest.TestCase):
    """The sanitizer must recognise the delivered bilingual header as real."""

    def _poi(self, name, display_title="", artist="", year=""):
        return {"name": name, "display_title": display_title,
                "artist": artist, "year": year}

    def test_bilingual_header_is_real(self):
        pois = [self._poi(_VN, display_title=_BILINGUAL)]
        is_real = _build_sanitizer(pois)
        self.assertTrue(is_real(f"Stop 1: {_BILINGUAL}"),
                        "delivered bilingual header wrongly flagged as fake")

    def test_bare_name_still_real(self):
        # Backwards compatibility: a stop that never got a bilingual title.
        pois = [self._poi("Em Thúy")]
        is_real = _build_sanitizer(pois)
        self.assertTrue(is_real("Stop 1: Em Thúy"))

    def test_injected_header_still_stripped(self):
        # A genuinely fake "Stop N:" line inside prose must still be caught.
        pois = [self._poi(_VN, display_title=_BILINGUAL)]
        is_real = _build_sanitizer(pois)
        self.assertFalse(is_real("Stop 2: and then we walked onward to the next"))

    def test_bilingual_header_survives_full_sanitize_pass(self):
        # End-to-end over a mini "complete_tour": the English gloss stays put.
        pois = [self._poi(_VN, display_title=_BILINGUAL)]
        is_real = _build_sanitizer(pois)
        complete_tour = (
            f"Stop 1: {_BILINGUAL}\n\n"
            "This sculpture by Diệp Minh Châu stands in the garden.\n"
            "Stop 2: a stray line GPT echoed mid-paragraph\n"
        )
        out_lines = []
        for _line in complete_tour.split("\n"):
            if re.match(r"^Stop\s+\d+:", _line) and not is_real(_line):
                out_lines.append(re.sub(r"^Stop\s+\d+:\s*", "", _line))
            else:
                out_lines.append(_line)
        out = "\n".join(out_lines)
        self.assertIn(f"Stop 1: {_BILINGUAL}", out,
                      "bilingual header (with English) must survive sanitize")
        self.assertNotIn("Stop 2: a stray line", out,
                         "injected mid-prose header must still be stripped")


class TestFixtureIsPresent(unittest.TestCase):
    """Soft check that the cited offline fixture exists (skipped if absent)."""

    def test_fixture_log_shows_the_symptom(self):
        path = os.path.expanduser(
            "~/Audioura/.continuous_dev/bench/AB17/run_OFF-1.log")
        if not os.path.exists(path):
            self.skipTest("fixture log not present on this machine")
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        self.assertIn("bilingual titles: set 4", text,
                      "fixture should show the gate claiming it set headers")
        # The pre-fix symptom: the delivered stop line had no English gloss.
        self.assertIn("3. Bác Hồ với thiếu nhi", text)


if __name__ == "__main__":
    unittest.main()
