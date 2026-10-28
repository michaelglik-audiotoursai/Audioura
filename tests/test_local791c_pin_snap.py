"""test_local791c_pin_snap.py — LOCAL-791C item 2.

The 791B pin_proof table measured LLM-written walking-stop pins 0.5–6 km from the
real place. These assert the snap: for a stop with an in-scope reference, a shipped
pin > 150 m away is snapped TO the reference and logged; a stop with no reference
is left unsnapped; a Wikidata P625 coordinate on the stop is the reference without
a network call.

Numbers below are the EXACT 791B pin table (SUBMISSION_LOCAL-791B.md):
  Giac Lam Pagoda          10.77910,106.62810  vs ref 10.77871,106.64919  = 2304 m
  Xa Loi Pagoda            10.75750,106.63610  vs ref 10.77803,106.68646  = 5956 m
  Phuoc An Hoi Quan Pagoda 10.75930,106.64440  vs ref 10.75515,106.65885  = 1645 m

Run:
    python3 -m pytest tests/test_local791c_pin_snap.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CENTER = (10.7769, 106.7009)  # HCMC centre

REFS = {
    "Giac Lam Pagoda": (10.77871, 106.64919, "serper"),
    "Xa Loi Pagoda": (10.77803, 106.68646, "serper"),
    "Phuoc An Hoi Quan Pagoda": (10.75515, 106.65885, "serper"),
}


def _ref_fn(name):
    return REFS.get(name)


class TestSnapOneStop:
    def test_far_pin_is_snapped_to_reference(self):
        from pin_snap import snap_pin
        row = snap_pin("Giac Lam Pagoda", (10.77910, 106.62810),
                       scope="Ho Chi Minh City", scope_center=CENTER,
                       reference_fn=_ref_fn)
        assert row["snapped"] is True
        assert row["new_coordinate"] == (10.77871, 106.64919)
        assert row["distance_m"] > 150  # 2304 m measured
        assert row["source"] == "serper"

    def test_close_pin_is_kept(self):
        from pin_snap import snap_pin
        # A pin 16 m from the reference is already good — not snapped.
        row = snap_pin("Close Stop", (10.0000, 106.0000),
                       scope="x", scope_center=(10.0, 106.0),
                       reference_fn=lambda n: (10.0001, 106.0001, "serper"))
        assert row["snapped"] is False
        assert row["distance_m"] is not None and row["distance_m"] < 150

    def test_no_reference_left_unsnapped(self):
        from pin_snap import snap_pin
        row = snap_pin("Unknown Place", (10.5, 106.5),
                       scope="x", scope_center=CENTER,
                       reference_fn=lambda n: None)
        assert row["snapped"] is False
        assert row["reference"] is None
        assert "unsnapped" in row["reason"]

    def test_wikidata_p625_is_the_reference(self):
        from pin_snap import snap_pin
        row = snap_pin("WD Stop", (10.9, 106.9),
                       scope="x", scope_center=CENTER,
                       wikidata_coord=(10.776, 106.700),
                       reference_fn=lambda n: None)  # never consulted
        assert row["snapped"] is True
        assert row["source"] == "wikidata"
        assert row["new_coordinate"] == (10.776, 106.700)

    def test_off_scope_reference_is_refused(self):
        from pin_snap import snap_pin
        # A bare-name geocode that resolved to another city (~40 km from centre)
        # must NOT move the pin. Stop is left unsnapped with an off-scope reason.
        row = snap_pin("Chua Ba Chua Xu", (10.78, 106.70),
                       scope="Ho Chi Minh City", scope_center=CENTER,
                       reference_fn=lambda n: (11.0667, 106.4788, "nominatim"),
                       max_snap_km=25.0)
        assert row["snapped"] is False
        assert row["new_coordinate"] is None
        assert "off-scope" in row["reason"]

    def test_wikidata_not_subject_to_off_scope_guard(self):
        from pin_snap import snap_pin
        # Wikidata P625 is the place's own authority — trusted even if far.
        row = snap_pin("Far WD", (10.78, 106.70),
                       scope="x", scope_center=CENTER,
                       wikidata_coord=(11.5, 106.0), max_snap_km=25.0,
                       reference_fn=lambda n: None)
        assert row["snapped"] is True
        assert row["source"] == "wikidata"

    def test_good_in_scope_pin_not_snapped_to_far_reference(self):
        from pin_snap import snap_pin
        # LOCAL-791C live run (Thien Hau Temple): the shipped pin sat in District 5
        # (~2 km from the HCMC centre, correct), but Nominatim's bare-name match
        # returned a same-name shrine 23 km north. Snapping a good in-scope pin to a
        # far-from-centre reference makes it WORSE and blew the walking route to
        # 11 km — refuse. The shipped pin is kept.
        shipped = (10.7536, 106.6619)   # real Thien Hau Temple, District 5
        far_ref = (10.9808, 106.6548)   # wrong same-name place ~23 km N of centre
        row = snap_pin("Thien Hau Temple", shipped,
                       scope="Ho Chi Minh City", scope_center=CENTER,
                       reference_fn=lambda n: (far_ref[0], far_ref[1], "nominatim"))
        assert row["snapped"] is False
        assert row["new_coordinate"] is None
        assert "off-scope same-name" in row["reason"]

    def test_real_far_pagoda_still_snaps_when_shipped_pin_is_wrong(self):
        from pin_snap import snap_pin
        # The guard must NOT block a legitimate snap: a pagoda genuinely 6 km from
        # the centre with a BAD shipped pin far from centre still snaps to its
        # reference (shipped pin is not itself in-scope, so the guard is inert).
        row = snap_pin("Giac Lam Pagoda", (10.60, 106.50),  # shipped ~25 km SW, wrong
                       scope="Ho Chi Minh City", scope_center=CENTER,
                       reference_fn=lambda n: (10.77871, 106.64919, "serper"))
        assert row["snapped"] is True
        assert row["new_coordinate"] == (10.77871, 106.64919)


class TestSnapPoiList:
    def test_all_three_791b_pagodas_snapped(self):
        from pin_snap import snap_poi_coordinates
        pois = [
            {"name": "Giac Lam Pagoda", "coordinates": "10.77910, 106.62810"},
            {"name": "Xa Loi Pagoda", "coordinates": "10.75750, 106.63610"},
            {"name": "Phuoc An Hoi Quan Pagoda", "coordinates": "10.75930, 106.64440"},
        ]
        poi_list, rows = snap_poi_coordinates(
            pois, scope="Ho Chi Minh City", scope_center=CENTER,
            reference_fn=_ref_fn, log=lambda *_: None)
        assert all(r["snapped"] for r in rows)
        # Every snapped stop now sits ON its reference → re-proof distance is 0 m.
        for p, name in zip(poi_list, REFS):
            ref = REFS[p["name"]]
            lat, lng = (float(x) for x in p["coordinates"].split(","))
            assert abs(lat - ref[0]) < 1e-6 and abs(lng - ref[1]) < 1e-6
            assert p.get("_pin_snapped") is True

    def test_log_line_format(self):
        from pin_snap import snap_poi_coordinates
        logs = []
        pois = [{"name": "Giac Lam Pagoda", "coordinates": "10.77910, 106.62810"}]
        snap_poi_coordinates(pois, scope="Ho Chi Minh City", scope_center=CENTER,
                             reference_fn=_ref_fn, log=logs.append)
        assert any(l.startswith("[LOCAL-791C] pin snap Giac Lam Pagoda") for l in logs)

    def test_unsnapped_logged_when_no_reference(self):
        from pin_snap import snap_poi_coordinates
        logs = []
        pois = [{"name": "Mystery Spot", "coordinates": "10.5, 106.5"}]
        snap_poi_coordinates(pois, scope="x", scope_center=CENTER,
                             reference_fn=lambda n: None, log=logs.append)
        assert any("left unsnapped" in l and "no in-scope reference" in l
                   for l in logs)


class TestReProofTargetMet:
    def test_snapped_tour_passes_100m_pin_proof(self):
        """After snapping, pin_proof against the same references reports ≤ 100 m
        (0 m) for every stop — the ticket's target."""
        from pin_snap import snap_poi_coordinates
        from pin_proof import pin_report
        pois = [
            {"name": "Giac Lam Pagoda", "coordinates": "10.77910, 106.62810"},
            {"name": "Xa Loi Pagoda", "coordinates": "10.75750, 106.63610"},
            {"name": "Phuoc An Hoi Quan Pagoda", "coordinates": "10.75930, 106.64440"},
        ]
        snap_poi_coordinates(pois, scope="Ho Chi Minh City", scope_center=CENTER,
                             reference_fn=_ref_fn, log=lambda *_: None)
        stops = [{"title": p["name"],
                  "coordinate": tuple(float(x) for x in p["coordinates"].split(","))}
                 for p in pois]
        # pin_proof uses a serper_fn returning (lat,lng); adapt our (lat,lng,src).
        report = pin_report(
            stops, scope="Ho Chi Minh City", scope_center=CENTER,
            serper_fn=lambda n: (REFS[n][0], REFS[n][1]) if n in REFS else None,
            nominatim_fn=lambda n: None)
        assert report["all_within_target"] is True
        assert report["proven"] == report["measured"] == 3
