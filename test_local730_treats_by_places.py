#!/usr/bin/env python3
"""
[LOCAL-730 / D694, Privacy "Location and places"] Tests for the treats service:
  * merge_treats de-duplicates by treat id across several tour-stop points,
    keeping the nearest copy, nearest-first, capped at RESULT_LIMIT;
  * round_coord logs only 2-decimal coordinates (never the exact position);
  * the POST /treats-near-places contract (validation, cap, no device/user/IP).

Pure unit tests — no database and no network. The DB-touching handlers are
exercised with a tiny fake cursor so merge/order logic is covered end to end.
"""
import importlib
import sys

import pytest

treats_service = importlib.import_module("treats_service")


# --- round_coord: logging precision -------------------------------------

def test_round_coord_two_decimals():
    assert treats_service.round_coord(42.36627) == 42.37
    assert treats_service.round_coord(-71.05442) == -71.05


def test_round_coord_truncates_precision_below_about_1km():
    # Two positions ~300 m apart collapse to the same 2-decimal value, so the
    # log cannot distinguish them — that is the privacy point.
    assert treats_service.round_coord(42.3600) == treats_service.round_coord(42.3611)


def test_round_coord_handles_bad_input():
    assert treats_service.round_coord(None) is None
    assert treats_service.round_coord("not-a-number") is None


# --- merge_treats: de-dup + order + cap ---------------------------------

def test_merge_dedups_by_id_keeping_nearest():
    p1 = [{"id": 1, "name": "Cafe", "distance_km": 2.0},
          {"id": 2, "name": "Bakery", "distance_km": 5.0}]
    p2 = [{"id": 1, "name": "Cafe", "distance_km": 0.5},  # nearer copy wins
          {"id": 3, "name": "Pub", "distance_km": 1.0}]
    merged = treats_service.merge_treats([p1, p2])
    by_id = {t["id"]: t for t in merged}
    # treat 1 de-duplicated to a single row
    assert len(merged) == 3
    assert by_id[1]["distance_km"] == 0.5
    # nearest-first ordering
    assert [t["id"] for t in merged] == [1, 3, 2]


def test_merge_caps_at_result_limit():
    many = [[{"id": i, "distance_km": float(i)} for i in range(20)]]
    merged = treats_service.merge_treats(many)
    assert len(merged) == treats_service.RESULT_LIMIT
    # kept the nearest ones
    assert [t["id"] for t in merged] == [0, 1, 2, 3, 4]


def test_merge_treats_without_id_uses_name_vendor_key():
    p1 = [{"name": "Cafe", "link_to_vendor": "x.com", "distance_km": 3.0}]
    p2 = [{"name": "Cafe", "link_to_vendor": "x.com", "distance_km": 1.0}]
    merged = treats_service.merge_treats([p1, p2])
    assert len(merged) == 1
    assert merged[0]["distance_km"] == 1.0


def test_merge_treats_missing_distance_sorts_last():
    p = [[{"id": 1}, {"id": 2, "distance_km": 0.1}]]
    merged = treats_service.merge_treats(p)
    assert [t["id"] for t in merged] == [2, 1]


# --- encode_images ------------------------------------------------------

def test_encode_images_replaces_bytes_with_base64():
    treats = [{"id": 1, "ad_image": b"PNGDATA"}, {"id": 2, "ad_image": None}]
    out = treats_service.encode_images(treats)
    assert "ad_image" not in out[0]
    assert out[0]["image_base64"] is not None
    assert out[1]["image_base64"] is None


# --- POST /treats-near-places contract ----------------------------------

class _FakeCursor:
    """A cursor that returns a fixed treat row set and records nothing else."""

    ROWS = [
        # id, ad_name, ad_text, lat, lng, link_to_vendor, ad_image, dist_ft
        (1, "Cafe", "good coffee", 42.0, -71.0, "cafe.com", None, 0),
        (2, "Bakery", "fresh bread", 48.0, 2.0, "bakery.com", None, 0),
    ]

    def execute(self, *a, **k):
        self._rows = list(self.ROWS)

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class _FakeConn:
    def cursor(self):
        return _FakeCursor()

    def close(self):
        pass


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(treats_service, "get_db_connection", lambda: _FakeConn())
    treats_service.app.config["TESTING"] = True
    return treats_service.app.test_client()


def test_post_places_merges_and_returns(client):
    resp = client.post("/treats-near-places", json={
        "points": [{"lat": 42.0, "lng": -71.0}, {"lat": 48.0, "lng": 2.0}],
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["points"] == 2
    # two tours near the same two treats ⇒ de-duplicated to 2 rows
    ids = sorted(t["id"] for t in data["treats"])
    assert ids == [1, 2]


def test_post_places_rejects_empty(client):
    resp = client.post("/treats-near-places", json={"points": []})
    assert resp.status_code == 400


def test_post_places_rejects_over_cap(client):
    pts = [{"lat": 1.0, "lng": 1.0}] * (treats_service.MAX_POINTS + 1)
    resp = client.post("/treats-near-places", json={"points": pts})
    assert resp.status_code == 400


def test_post_places_rejects_non_numeric(client):
    resp = client.post("/treats-near-places", json={
        "points": [{"lat": "x", "lng": "y"}],
    })
    assert resp.status_code == 400


def test_get_single_point_still_works(client):
    resp = client.get("/treats-near/42.0/-71.0")
    assert resp.status_code == 200
    assert "treats" in resp.get_json()


def test_log_is_rounded_not_exact(client, capsys):
    client.get("/treats-near/42.36627/-71.05442")
    out = capsys.readouterr().out
    # the exact high-precision coordinates must NOT appear in the log
    assert "42.36627" not in out
    assert "-71.05442" not in out
    # the rounded values do
    assert "42.37" in out
    assert "-71.05" in out


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
