#!/usr/bin/env python3
"""LOCAL-884 §4 — itinerary import must reproduce the WAVE-40 titles and pins.

Wave 42 (gen 00044-w2d) regressed the import path introduced for 882/883: the
delivered stop titles were the RAW pasted labels ("Opera House_Đồng Khởi",
"City Hall & Nguyễn Huệ", "Bạch Đằng Pier (tour-bus + waterbus)"), stops 1 and 6
lost their Coordinates, the Café was pinned next to the Palace, and the tour start
moved. Wave 40 had clean titles ("Opera House", "City Hall", "Bạch Đằng Pier") and
a correct pin on every stop.

This test runs Michael's EXACT raw pasted list through the real import path —
``expand_pasted_lists`` then ``resolve_user_stop_pins`` — with a stubbed preview
that mimics ``preview_stops`` (it parses the joined names with the real parser and
pins each to its WAVE-40 coordinate). It asserts, for all ten stops:

  * the spoken title is the clean wave-40 title — no '_', '&', '/', or parenthesis,
    and no alt/note bled into it;
  * every stop carries a pin (/@lat,lng), with NO stop left coordinate-less;
  * every pin is the wave-40 pin within 50 m (the Café is at 10.774089,106.704056,
    never the Palace 10.7761,106.6959);
  * the order is unchanged (Cathedral first, Thi Bar last) — the start did not move.

It is fully offline (no network, no LLM): the preview is injected.
"""
import math
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import itinerary_import as ii  # noqa: E402

# Michael's EXACT raw pasted list (one field), as it reached the orchestrator.
MICHAEL = ("Cathedral → Post Office → Book Street → Independence Palace → "
           "War Remnants Museum → Opera House/Đồng Khởi → City Hall & Nguyễn Huệ → "
           "Café Apartments 42 → Bạch Đằng Pier (tour-bus + waterbus) → Thi Bar")

CITY = "Ho Chi Minh City"

# The WAVE-40 Coordinates lines (the pins the cloud shipped before the regression),
# keyed by the clean parsed name. The Café's wave-40 pin is on Nguyễn Huệ, NOT at
# the Palace.
WAVE40 = {
    "Cathedral":            (10.779722, 106.699167),
    "Post Office":          (10.780000, 106.700000),
    "Book Street":          (10.780573, 106.699695),
    "Independence Palace":  (10.777050, 106.695370),
    "War Remnants Museum":  (10.779500, 106.692000),
    "Opera House":          (10.776390, 106.702780),
    "City Hall":            (10.776470, 106.700970),
    "Café Apartments 42":   (10.774089, 106.704056),
    "Bạch Đằng Pier":       (10.775240, 106.707002),
    "Thi Bar":              (10.767660, 106.693960),
}
EXPECTED_ORDER = list(WAVE40.keys())


def _km(a, b):
    R = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(h)))


def _wave40_preview(text, city, **_kw):
    """Stub of preview_stops: parse the joined text with the REAL parser (so the
    title cleaning is exercised exactly as live) and pin each parsed stop to its
    wave-40 coordinate by its clean name. Unknown names come back unresolved."""
    parsed = ii.parse_itinerary(text, city)
    stops = []
    for p in parsed:
        nm = p["name"]
        pin = None
        for k, v in WAVE40.items():
            if ii._fold(k) == ii._fold(nm):
                pin = v
                break
        if pin:
            stops.append({"name": nm, "stop_name": nm, "lat": pin[0], "lng": pin[1],
                          "matched_name": None})
        else:
            stops.append({"name": nm, "unresolved": True, "lat": None, "lng": None})
    return {"ok": True, "city": {"name": CITY}, "stops": stops}


def _split_name(s):
    return s.split(" http")[0].strip()


def _pin_of(s):
    m = re.search(r"/@(-?\d+\.\d+),(-?\d+\.\d+)", s)
    return (float(m.group(1)), float(m.group(2))) if m else None


class ItineraryWave40(unittest.TestCase):
    def _run(self):
        # 1) one pasted field -> ten name-only stops, order kept (clean names).
        expanded, n_exp = ii.expand_pasted_lists([MICHAEL], CITY)
        self.assertEqual(n_exp, 1)
        self.assertEqual(len(expanded), 10)
        # 2) resolve each name-only stop to a pin via the stubbed wave-40 preview,
        #    exactly as the orchestrator does live.
        out, n_pin = ii.resolve_user_stop_pins(
            expanded, CITY, log=lambda *a: None, preview_fn=_wave40_preview)
        return out, n_exp, n_pin

    def test_titles_are_the_clean_wave40_labels(self):
        out, _, _ = self._run()
        self.assertEqual(len(out), 10)
        for i, s in enumerate(out):
            title = _split_name(s)
            self.assertEqual(title, EXPECTED_ORDER[i],
                             f"stop {i+1} title {title!r} != {EXPECTED_ORDER[i]!r}")
            # no raw-label artefacts in any title
            for bad in ("_", "&", "/", "(", ")", "Đồng Khởi", "Nguyễn Huệ",
                        "tour-bus", "waterbus"):
                self.assertNotIn(bad, title, f"raw label artefact {bad!r} in {title!r}")

    def test_every_stop_has_a_pin(self):
        out, _, n_pin = self._run()
        self.assertEqual(n_pin, 10, "every stop must carry a reviewed pin")
        for i, s in enumerate(out):
            self.assertIn("/@", s, f"stop {i+1} lost its Coordinates: {s!r}")

    def test_pins_match_wave40_within_50m(self):
        out, _, _ = self._run()
        for i, s in enumerate(out):
            pin = _pin_of(s)
            self.assertIsNotNone(pin, f"stop {i+1} has no pin")
            want = WAVE40[EXPECTED_ORDER[i]]
            d_m = _km(pin, want) * 1000.0
            self.assertLessEqual(d_m, 50.0,
                                 f"stop {i+1} {EXPECTED_ORDER[i]} pin {pin} is "
                                 f"{d_m:.0f} m from the wave-40 pin {want}")

    def test_cafe_is_not_at_the_palace(self):
        out, _, _ = self._run()
        cafe = _pin_of(out[7])                      # stop 8: Café Apartments 42
        self.assertIsNotNone(cafe)
        palace_wrong = (10.7761, 106.6959)          # the wave-42 wrong café pin
        self.assertGreater(_km(cafe, palace_wrong) * 1000.0, 50.0,
                           "Café must not be pinned next to the Palace")
        self.assertLessEqual(_km(cafe, WAVE40["Café Apartments 42"]) * 1000.0, 50.0)

    def test_start_did_not_move(self):
        out, _, _ = self._run()
        self.assertEqual(_split_name(out[0]), "Cathedral")
        self.assertEqual(_split_name(out[-1]), "Thi Bar")


if __name__ == "__main__":
    unittest.main()
