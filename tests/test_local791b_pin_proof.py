"""test_local791b_pin_proof.py — LOCAL-791B item 3.

Pin proof: for each stop, the distance from the shipped coordinate to an
independent geocode (Serper Places first, else Nominatim) of the same name, with a
100 m target. Pure/offline — the geocoders are injected.

Run:
    python3 -m pytest tests/test_local791b_pin_proof.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestParseCoordinate:
    def test_parse_comma_pair(self):
        from pin_proof import parse_coordinate
        assert parse_coordinate("10.776900, 106.703000") == (10.7769, 106.703)

    def test_reject_out_of_range(self):
        from pin_proof import parse_coordinate
        assert parse_coordinate("not a coord") is None
        assert parse_coordinate("200.0, 500.0") is None


class TestParseTourStops:
    def test_pairs_header_with_coordinates(self):
        from pin_proof import parse_tour_stops
        text = (
            "Stop 1: Jade Emperor Pagoda (Chùa Ngọc Hoàng)\n"
            "Address: 73 Mai Thi Luu, District 1\n"
            "Coordinates: 10.788300, 106.695600\n"
            "Some narration.\n\n"
            "Stop 2: Thien Hau Temple\n"
            "Coordinates: 10.753000, 106.661000\n")
        stops = parse_tour_stops(text)
        assert len(stops) == 2
        assert stops[0]["title"] == "Jade Emperor Pagoda (Chùa Ngọc Hoàng)"
        assert stops[0]["coordinate"] == (10.7883, 106.6956)
        assert stops[1]["coordinate"] == (10.753, 106.661)

    def test_missing_coordinate_is_none(self):
        from pin_proof import parse_tour_stops
        stops = parse_tour_stops("Stop 1: No Pin Place\nAddress: somewhere\n")
        assert stops == [{"title": "No Pin Place", "coordinate": None}]


class TestReferenceForName:
    def test_prefers_serper(self):
        from pin_proof import reference_for_name
        ref = reference_for_name(
            "Jade Emperor Pagoda",
            serper_fn=lambda n: (10.7883, 106.6956),
            nominatim_fn=lambda n: (10.0, 106.0))
        assert ref == (10.7883, 106.6956, "serper")

    def test_falls_back_to_nominatim(self):
        from pin_proof import reference_for_name
        ref = reference_for_name(
            "Obscure Pagoda",
            serper_fn=lambda n: None,
            nominatim_fn=lambda n: (10.75, 106.66))
        assert ref == (10.75, 106.66, "nominatim")

    def test_none_when_neither_resolves(self):
        from pin_proof import reference_for_name
        assert reference_for_name(
            "Nowhere", serper_fn=lambda n: None,
            nominatim_fn=lambda n: None) is None


class TestPinReport:
    def test_within_and_outside_target(self):
        from pin_proof import pin_report
        stops = [
            {"title": "Jade Emperor Pagoda", "coordinate": (10.7883, 106.6956)},
            {"title": "War Remnants Museum", "coordinate": (10.7772, 106.7028)},
        ]
        # Serper returns the SAME point for stop 1 (0 m) and a point ~1.2 km away
        # for stop 2 (the inherited-pin defect pattern).
        refs = {
            "Jade Emperor Pagoda": (10.7883, 106.6956),
            "War Remnants Museum": (10.7795, 106.6921),
        }
        rep = pin_report(stops, serper_fn=lambda n: refs.get(n))
        assert rep["total"] == 2
        assert rep["measured"] == 2
        assert rep["rows"][0]["within_target"] is True
        assert rep["rows"][0]["distance_m"] == 0.0
        assert rep["rows"][0]["source"] == "serper"
        assert rep["rows"][1]["within_target"] is False
        assert rep["rows"][1]["distance_m"] > 100
        assert rep["proven"] == 1
        assert rep["all_within_target"] is False

    def test_all_within_target(self):
        from pin_proof import pin_report
        stops = [
            {"title": "A", "coordinate": (10.0000, 106.0000)},
            {"title": "B", "coordinate": (10.0005, 106.0000)},  # ~55 m
        ]
        refs = {"A": (10.0000, 106.0000), "B": (10.0005, 106.0001)}
        rep = pin_report(stops, serper_fn=lambda n: refs.get(n))
        assert rep["all_within_target"] is True
        assert rep["proven"] == 2

    def test_unresolved_name_not_counted_as_measured(self):
        from pin_proof import pin_report
        stops = [{"title": "Ghost Place", "coordinate": (10.0, 106.0)}]
        rep = pin_report(stops, serper_fn=lambda n: None, nominatim_fn=lambda n: None)
        assert rep["measured"] == 0
        assert rep["rows"][0]["distance_m"] is None
        assert rep["all_within_target"] is False


class TestFormatPinTable:
    def test_table_has_rows_and_summary(self):
        from pin_proof import pin_report, format_pin_table
        stops = [{"title": "Jade Emperor Pagoda", "coordinate": (10.7883, 106.6956)}]
        rep = pin_report(stops, serper_fn=lambda n: (10.7883, 106.6956))
        table = format_pin_table(rep)
        assert "Jade Emperor Pagoda" in table
        assert "serper" in table
        assert "within" in table


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
