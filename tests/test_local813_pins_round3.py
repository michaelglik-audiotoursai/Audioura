"""test_local813_pins_round3.py — LOCAL-813.

Walking/museum tours 854/855/857/860/861/862 still shipped pins 250–1379 m off
after 791E/803. The diagnosis (SUBMISSION_LOCAL-813.md) found three GENERAL
causes; these tests assert each fix with the EXACT failing stop titles, fully
OFFLINE (recorded Wikidata responses / injected references — no network):

  CAUSE A — the geocoded neighbourhood bbox was razor-tight and rejected a correct
            landmark just outside its edge. "Eikan-do Zenrin-ji" (a real
            Higashiyama temple, Wikidata Q2380134 at 35.01452,135.79529) sits
            ~380 m north of the Nominatim box for "Higashiyama, Kyoto" and was
            rejected -> shipped 35.0175 (343 m off). FIX: pad the bbox by ~2 km
            before the in-scope test; the metro radius stays the cross-city guard.

  CAUSE B — a cross-language name-match was too strict. "Museu de Fado" (the
            Portuguese stop title) vs the geocoder's English "Fado Museum" shared
            no distinctive core (museu vs museum stayed distinct), so the snap was
            refused and the pin stayed 230 m off. FIX: fold place-class words
            across languages (museu/museum/musee/museo -> museum, ...) and drop the
            Romance articles (de/do/da/...), so the cores match.

  CAUSE C — a museum tour's stops are ARTWORK titles with no place identity; they
            share the ONE building-level pin. "Judith I" etc. had no own P625 and
            the geocoder returned a WRONG same-name building ("Lower Belvedere"),
            so all five shipped 1,379 m off the palace. FIX: resolve the museum
            building's P625 once (Upper Belvedere, the painting galleries) and use
            it as the snap's venue fallback for any artwork stop with no reference.

Run:
    python3 -m pytest tests/test_local813_pins_round3.py -q
"""
import math
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _hav_m(a, b):
    R = 6371000.0
    la1, lo1 = math.radians(a[0]), math.radians(a[1])
    la2, lo2 = math.radians(b[0]), math.radians(b[1])
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


def _fold(s):
    nf = unicodedata.normalize("NFKD", str(s or "").lower())
    s = "".join(c for c in nf if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


# ───────────────────── recorded Wikidata responses ──────────────────────────
_SEARCH = {
    # Eikan-do Zenrin-ji — the real temple (used by Cause A).
    "eikan do zenrin ji": [("Q2380134", "Eikan-do Zenrin-ji Temple",
                            "Buddhist temple in Kyoto Prefecture, Japan")],
    # Museu do Fado resolves in PT; "Museu de Fado" (the de/do variant the title
    # carries) does NOT surface it — proves the generic-geocoder cross-language
    # name-match (Cause B) is what rescues it.
    "museu de fado": [],
    "museu do fado": [("Q1954395", "Museu do Fado", "museum in Lisbon")],
    "fado museum": [("Q1954395", "Fado Museum", "museum in Lisbon")],
    # The museum building for Cause C.
    "belvedere museum": [("Q303139", "Belvedere", "museum in Vienna, Austria")],
    "belvedere": [("Q303139", "Belvedere", "museum in Vienna, Austria")],
    "upper belvedere": [("Q87193291", "Upper Belvedere", "palace in Vienna")],
    # Artwork titles: no place entity with a P625.
    "judith i": [],
    "the evil mothers": [],
}

_ENTITIES = {
    "Q2380134": (35.014525, 135.79529167),   # Eikan-do Zenrin-ji
    "Q1954395": (38.71108627, -9.12761974),  # Museu do Fado / Fado Museum
    "Q303139": (48.19138889, 16.38083333),   # Belvedere (museum building)
    "Q87193291": (48.19154, 16.3809),        # Upper Belvedere
}


def _search_resp(hits):
    return {"search": [{"id": q, "label": lbl, "description": desc}
                       for (q, lbl, desc) in hits]}


def recorded_fetch(action, params):
    if params.get("action") == "wbsearchentities":
        return _search_resp(_SEARCH.get(_fold(params.get("search", "")), []))
    if params.get("action") == "wbgetentities":
        qid = params.get("ids")
        pt = _ENTITIES.get(qid, (None, None))
        if pt[0] is None:
            return {"entities": {qid: {"claims": {}}}}
        return {"entities": {qid: {"claims": {"P625": [{"mainsnak": {
            "datavalue": {"value": {"latitude": pt[0], "longitude": pt[1]}}}}]}}}}
    return None


# ═══════════════════════ CAUSE A — bbox padding ═════════════════════════════
class TestCauseA_BboxPadEdgeLandmark:
    # Nominatim's box for "Higashiyama, Kyoto, Japan"; north edge 35.0108540.
    TIGHT_BBOX = [34.9699550, 35.0108540, 135.7646440, 135.7911370]
    CENTER = (35.0030, 135.7820)
    EIKANDO = (35.014525, 135.79529167)  # ~380 m N of the box north edge
    SHIPPED = (35.0175, 135.7943)        # 343 m off

    def test_edge_landmark_admitted_with_pad(self):
        import wikidata_landmark_lookup as wll
        hit = wll.lookup("Eikan-do Zenrin-ji",
                         scope="Higashiyama, Kyoto, Japan",
                         scope_center=self.CENTER, scope_bbox=self.TIGHT_BBOX,
                         tour_language="en", fetch_fn=recorded_fetch,
                         use_cache=False)
        assert hit is not None
        assert hit[3] == "Q2380134"
        assert _hav_m((hit[0], hit[1]), self.EIKANDO) < 5

    def test_pad_can_be_disabled_to_show_the_old_reject(self):
        import importlib
        import wikidata_landmark_lookup as wll
        old = os.environ.get("LANDMARK_BBOX_PAD_DEG")
        os.environ["LANDMARK_BBOX_PAD_DEG"] = "0"
        try:
            importlib.reload(wll)
            hit = wll.lookup("Eikan-do Zenrin-ji",
                             scope="Higashiyama, Kyoto, Japan",
                             scope_center=None, scope_bbox=self.TIGHT_BBOX,
                             tour_language="en", fetch_fn=recorded_fetch,
                             use_cache=False)
            assert hit is None
        finally:
            if old is None:
                os.environ.pop("LANDMARK_BBOX_PAD_DEG", None)
            else:
                os.environ["LANDMARK_BBOX_PAD_DEG"] = old
            importlib.reload(wll)

    def test_pad_does_not_admit_a_far_same_name_place(self):
        import wikidata_landmark_lookup as wll
        far = {"eikan do zenrin ji": [("QFAR", "Eikan-do", "temple")]}

        def far_fetch(action, params):
            if params.get("action") == "wbsearchentities":
                return _search_resp(far.get(_fold(params.get("search", "")), []))
            return {"entities": {"QFAR": {"claims": {"P625": [{"mainsnak": {
                "datavalue": {"value": {"latitude": 35.45,
                                        "longitude": 135.80}}}}]}}}}
        hit = wll.lookup("Eikan-do Zenrin-ji",
                         scope="Higashiyama, Kyoto, Japan",
                         scope_center=self.CENTER, scope_bbox=self.TIGHT_BBOX,
                         tour_language="en", fetch_fn=far_fetch, use_cache=False)
        assert hit is None  # ~50 km N: outside padded box AND metro radius


# ═══════════════════════ CAUSE B — cross-language name-match ═════════════════
class TestCauseB_CrossLanguageNameMatch:
    def test_museu_de_fado_matches_fado_museum(self):
        from pin_snap import _name_matches_reference
        assert _name_matches_reference("Museu de Fado", "Fado Museum") is True
        assert _name_matches_reference("Museu do Fado", "Fado Museum") is True

    def test_museu_de_fado_snaps_to_generic_geocoder_ref(self):
        from pin_snap import snap_pin
        fado = (38.71108627, -9.12761974)
        row = snap_pin("Museu de Fado", (38.7131, -9.1265),
                       scope="Alfama, Lisbon, Portugal",
                       scope_center=(38.712, -9.130),
                       reference_fn=lambda n: (fado[0], fado[1], "serper",
                                               "Fado Museum"),
                       require_name_match=True)
        assert row["snapped"] is True
        assert _hav_m(row["new_coordinate"], fado) < 5
        assert row["distance_m"] > 150  # ~230 m shipped error

    def test_unrelated_museum_still_refused(self):
        from pin_snap import snap_pin
        row = snap_pin("Museu de Fado", (38.7131, -9.1265),
                       scope="Lisbon", scope_center=(38.712, -9.130),
                       reference_fn=lambda n: (38.70, -9.20, "serper",
                                               "Museum of Art"),
                       require_name_match=True)
        assert row["snapped"] is False
        assert "refused" in row["reason"]


# ═══════════════════════ CAUSE C — museum building fallback ══════════════════
class TestCauseC_MuseumBuildingFallback:
    UPPER = (48.19154, 16.3809)
    SHIPPED = (48.2031, 16.3747)  # ~1379 m off the palace

    def test_artwork_stop_with_no_reference_snaps_to_building(self):
        from pin_snap import snap_pin
        row = snap_pin("Judith I", self.SHIPPED,
                       scope="Belvedere Museum, Vienna, Austria",
                       scope_center=(48.1914, 16.3808),
                       reference_fn=lambda n: None,
                       venue_fallback_coordinate=self.UPPER)
        assert row["snapped"] is True
        assert row["source"] == "venue_building"
        assert _hav_m(row["new_coordinate"], self.UPPER) < 5
        assert row["distance_m"] > 150

    def test_wrong_same_name_building_falls_back_to_the_museum(self):
        from pin_snap import snap_pin
        row = snap_pin("The Plain of Auvers", self.SHIPPED,
                       scope="Belvedere Museum, Vienna, Austria",
                       scope_center=(48.1914, 16.3808),
                       reference_fn=lambda n: (48.19102, 16.38013, "serper",
                                               "Lower Belvedere"),
                       require_name_match=True,
                       venue_fallback_coordinate=self.UPPER)
        assert row["snapped"] is True
        assert row["source"] == "venue_building"
        assert _hav_m(row["new_coordinate"], self.UPPER) < 5

    def test_no_building_pin_leaves_stop_unsnapped(self):
        from pin_snap import snap_pin
        row = snap_pin("Judith I", self.SHIPPED,
                       scope="Belvedere Museum, Vienna, Austria",
                       scope_center=(48.1914, 16.3808),
                       reference_fn=lambda n: None)
        assert row["snapped"] is False
        assert row["reference"] is None

    def test_museum_lookup_resolves_building_via_recorded_wikidata(self):
        import wikidata_landmark_lookup as wll
        hit = wll.lookup("Belvedere Museum",
                         scope="Belvedere Museum, Vienna, Austria",
                         scope_center=(48.1914, 16.3808), scope_bbox=None,
                         tour_language="en", fetch_fn=recorded_fetch,
                         use_cache=False)
        assert hit is not None
        assert _hav_m((hit[0], hit[1]), self.UPPER) < 50  # Q303139 ≈ Upper


# ═══════════════════ full-tour snap over a stored stop ═══════════════════════
class TestSnapOverStoredStops:
    def test_kyoto_eikando_snaps(self):
        import wikidata_landmark_lookup as wll
        from pin_snap import snap_poi_coordinates
        bbox = [34.9699550, 35.0108540, 135.7646440, 135.7911370]
        pois = [{"name": "Eikan-do Zenrin-ji", "coordinates": "35.0175, 135.7943"}]

        def lf(name):
            return wll.lookup(name, scope="Higashiyama, Kyoto, Japan",
                              scope_center=(35.003, 135.782), scope_bbox=bbox,
                              tour_language="en", fetch_fn=recorded_fetch,
                              use_cache=False)
        _, rows = snap_poi_coordinates(
            pois, scope="Higashiyama, Kyoto, Japan",
            scope_center=(35.003, 135.782), scope_bbox=bbox,
            tour_language="en", landmark_fn=lf, log=lambda m: None)
        assert rows[0]["snapped"] is True
        assert rows[0]["source"] == "wikidata_p625"
        assert _hav_m(rows[0]["new_coordinate"], (35.014525, 135.79529167)) < 5
