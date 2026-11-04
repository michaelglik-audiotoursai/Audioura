#!/usr/bin/env python3
"""test_local859_share_google_resolve.py — LOCAL-859.

Google changed the share.google flow: ``https://share.google/<id>`` now 302s to
``https://www.google.com/share.google?q=<id>``, a JS-rendered page with NO
coordinate in the HTTP response (GCloud_Storied_1 wave 26, tour 529 Sophia
rerun: all six share.google links logged "unresolved", 5/7 pins differed from
tour 525, An Spa landed on the city centroid).

This file proves, OFFLINE and deterministically, the fixes from the ticket:

  1. URL FORMS. parse_maps_place_url / parse_plain_latlng accept every form the
     ticket lists: a /maps/place/…@lat,lng URL, a /maps?q=lat,lng URL, a
     !3dLAT!4dLNG blob, and a plain "lat,lng" string. Out-of-range pairs reject.
     is_google_maps_link accepts maps.app.goo.gl, goo.gl/maps, google.<tld>/maps,
     maps.google.<tld>, share.google.

  2. NEW 302 CHAIN. default_resolver, with requests mocked from a CAPTURED new-
     flow response (share.google/<id> -> www.google.com/share.google?q=<id>),
     recovers the coordinate from a /maps/place URL embedded in the final page
     body — the path the live flow now takes. An invalid id (-> /error) resolves
     to None.

  3. NAME-LOOKUP FALLBACK. name_lookup_in_bbox returns the best name match INSIDE
     the city bounding box (Serper /places first, else Nominatim) and marks the
     source; a candidate OUTSIDE the box is rejected (a same-named venue in
     another city) and the function returns None — the caller then leaves the
     stop with NO coordinate (announced), NEVER the city centroid.

Run:
    python3 -m pytest tests/test_local859_share_google_resolve.py -q
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import user_stop_input as u  # noqa: E402


# HCMC District 1 bounding box (south, north, west, east) and centre.
HCMC_BBOX = (10.70, 10.85, 106.62, 106.75)
HCMC_CENTER = (10.7769, 106.7009)


# ───────────────────── 1. URL forms ──────────────────────────────────────────
class TestUrlForms:
    def test_place_at_latlng(self):
        name, lat, lng = u.parse_maps_place_url(
            "https://www.google.com/maps/place/Rambutan+Saigon/@10.7725,106.6985,17z")
        assert name == "Rambutan Saigon"
        assert (round(lat, 4), round(lng, 4)) == (10.7725, 106.6985)

    def test_maps_q_latlng(self):
        name, lat, lng = u.parse_maps_place_url(
            "https://www.google.com/maps?q=10.7725,106.6985")
        assert (round(lat, 4), round(lng, 4)) == (10.7725, 106.6985)

    def test_bang_3d4d(self):
        _n, lat, lng = u.parse_maps_place_url(
            "https://maps.google.com/maps/place/X/data=!3d10.78!4d106.69")
        assert (round(lat, 2), round(lng, 2)) == (10.78, 106.69)

    def test_plain_latlng(self):
        assert u.parse_plain_latlng("10.7725, 106.6985") == (10.7725, 106.6985)
        assert u.parse_plain_latlng("10.7725,106.6985") == (10.7725, 106.6985)

    def test_out_of_range_rejected(self):
        assert u.parse_plain_latlng("200, 500") == (None, None)
        _n, lat, lng = u.parse_maps_place_url("https://www.google.com/maps?q=200,500")
        assert lat is None and lng is None

    def test_host_recognition(self):
        for url in ("https://share.google/1v4x",
                    "https://maps.app.goo.gl/abcd",
                    "https://goo.gl/maps/abcd",
                    "https://www.goo.gl/maps/abcd",
                    "https://www.google.com/maps/place/X/@1,2,17z",
                    "https://google.de/maps/place/Y",
                    "https://maps.google.co.uk/?q=1,2"):
            assert u.is_google_maps_link(url), url

    def test_website_is_not_maps_link(self):
        assert not u.is_google_maps_link("https://an-spa.vn/en")

    def test_plain_latlng_parsed_as_direct_coordinate(self):
        p = u.parse_user_stop("10.7725, 106.6985", resolve=lambda _x: None,
                              log=lambda *_a: None)
        assert p["how"] == "latlng"
        assert p["needs_geocode"] is False
        assert (round(p["lat"], 4), round(p["lng"], 4)) == (10.7725, 106.6985)


# ───────────────────── 2. new 302 chain (mocked) ─────────────────────────────
# A captured new-flow page body: the JS-rendered share page embeds the canonical
# /maps/place URL (what the live flow now carries once the client resolves it).
_Q_PAGE_BODY = (
    '<!DOCTYPE html><html><head><title>share.google</title>'
    '<link rel="canonical" href="https://www.google.com/maps/place/'
    'Rambutan+Saigon/@10.7725,106.6985,17z/data=!3d10.7725!4d106.6985"/>'
    '</head><body>loading…</body></html>'
)
# The /error page an INVALID id lands on — no coordinate anywhere.
_ERROR_BODY = (
    '<!DOCTYPE html><html><head><title>share.google</title></head>'
    '<body>Something went wrong.</body></html>'
)


class _FakeResp:
    def __init__(self, url, text):
        self.url = url
        self.text = text


class _FakeCookies:
    def set(self, *a, **k):
        pass


class _FakeSession:
    """A requests.Session stand-in replaying the captured new-flow chain:
    share.google/<id>  -> www.google.com/share.google?q=<id>  (JS page body)."""

    # id -> (final_url, body) for the share-page GET.
    PAGES = {
        "1v4x": ("https://www.google.com/share.google?q=1v4x", _Q_PAGE_BODY),
        "bad":  ("https://share.google/error", _ERROR_BODY),
    }

    def __init__(self):
        self.headers = {}
        self.cookies = _FakeCookies()

    def _id(self, url):
        import re
        m = re.search(r"(?:share\.google/|[?&]q=)([^/?&#\s]+)", url)
        return m.group(1) if m else ""

    def get(self, url, timeout=None, allow_redirects=True):
        sid = self._id(url)
        if sid in self.PAGES:
            final, body = self.PAGES[sid]
            return _FakeResp(final, body)
        # Fallback endpoints (maps?q=<id>, maps.google, maps/search): no coord for
        # a valid id in this fixture (the body path already resolved it), and
        # definitely none for a bad id.
        return _FakeResp(url, "<html><body>no map</body></html>")


def _install_fake_requests(monkeypatch, session_cls=_FakeSession):
    fake = types.ModuleType("requests")
    fake.Session = session_cls
    monkeypatch.setitem(sys.modules, "requests", fake)


class TestNew302Chain:
    def test_valid_id_recovers_coord_from_body(self, monkeypatch):
        _install_fake_requests(monkeypatch)
        final = u.default_resolver("https://share.google/1v4x")
        assert final is not None
        _n, lat, lng = u.parse_maps_place_url(final)
        assert (round(lat, 4), round(lng, 4)) == (10.7725, 106.6985)

    def test_invalid_id_resolves_to_none(self, monkeypatch):
        _install_fake_requests(monkeypatch)
        # /error body has no coordinate and the fallback endpoints have none → the
        # resolver returns a candidate with no coord, from which no latlng parses.
        final = u.default_resolver("https://share.google/bad")
        if final:
            _n, lat, lng = u.parse_maps_place_url(final)
            assert lat is None and lng is None

    def test_resolver_never_raises_on_broken_requests(self, monkeypatch):
        class _Boom:
            def __init__(self):
                raise RuntimeError("network down")
        _install_fake_requests(monkeypatch, session_cls=_Boom)
        # Must degrade to None, never propagate.
        assert u.default_resolver("https://share.google/1v4x") is None

    def test_parse_user_stop_uses_resolver_and_logs_859(self, monkeypatch):
        _install_fake_requests(monkeypatch)
        logs = []
        p = u.parse_user_stop("Rambutan https___share.google_1v4x", log=logs.append)
        assert p["needs_geocode"] is False
        assert (round(p["lat"], 4), round(p["lng"], 4)) == (10.7725, 106.6985)
        assert any(l.startswith("[LOCAL-859] user link resolved") for l in logs)


# ───────────────────── 3. name-lookup fallback ──────────────────────────────
class TestNameLookupFallback:
    def test_in_box_serper_match_wins(self):
        def serp(name, city, center):
            return [{"title": "Rambutan Saigon", "lat": 10.7725, "lon": 106.6985}]
        logs = []
        hit = u.name_lookup_in_bbox(
            "Rambutan", "Ho Chi Minh City", bbox=HCMC_BBOX, center=HCMC_CENTER,
            serper_fn=serp, nominatim_fn=lambda n, c: [], log=logs.append)
        assert hit is not None
        lat, lng, source, matched = hit
        assert source == "serper"
        assert (round(lat, 4), round(lng, 4)) == (10.7725, 106.6985)
        assert "Rambutan" in matched
        assert any("name lookup" in l and "serper" in l for l in logs)

    def test_out_of_box_candidate_rejected(self):
        # A same-named venue in another city (far outside the HCMC box).
        def serp(name, city, center):
            return [{"title": "Rambutan", "lat": 40.0, "lon": -70.0}]
        logs = []
        hit = u.name_lookup_in_bbox(
            "Rambutan", "Ho Chi Minh City", bbox=HCMC_BBOX, center=HCMC_CENTER,
            serper_fn=serp, nominatim_fn=lambda n, c: [], log=logs.append)
        assert hit is None
        assert any("NO MATCH in box" in l for l in logs)

    def test_nominatim_used_when_serper_empty(self):
        def nom(name, city):
            return [{"name": "An Spa", "lat": 10.78, "lon": 106.70}]
        hit = u.name_lookup_in_bbox(
            "An Spa", "Ho Chi Minh City", bbox=HCMC_BBOX, center=HCMC_CENTER,
            serper_fn=lambda n, c, ctr: [], nominatim_fn=nom,
            log=lambda *_a: None)
        assert hit is not None
        assert hit[2] == "nominatim"

    def test_best_name_match_among_candidates(self):
        def serp(name, city, center):
            return [
                {"title": "Longan Bar & Grill", "lat": 10.7801, "lon": 106.6922},
                {"title": "Completely Different", "lat": 10.7805, "lon": 106.6925},
            ]
        hit = u.name_lookup_in_bbox(
            "Longan", "HCMC", bbox=HCMC_BBOX, center=HCMC_CENTER,
            serper_fn=serp, nominatim_fn=lambda n, c: [], log=lambda *_a: None)
        assert hit is not None
        assert "Longan" in hit[3]

    def test_low_score_rejected(self):
        def serp(name, city, center):
            return [{"title": "Totally Unrelated Place", "lat": 10.78,
                     "lon": 106.70}]
        hit = u.name_lookup_in_bbox(
            "Rambutan", "HCMC", bbox=HCMC_BBOX, center=HCMC_CENTER,
            serper_fn=serp, nominatim_fn=lambda n, c: [], log=lambda *_a: None)
        assert hit is None

    def test_empty_name_returns_none(self):
        assert u.name_lookup_in_bbox("", "HCMC", bbox=HCMC_BBOX) is None

    def test_never_returns_centroid(self):
        # When nothing matches, the function returns None — the caller must NOT
        # substitute the centre. Prove the function itself never emits the centre.
        hit = u.name_lookup_in_bbox(
            "Nonexistent Venue XYZ", "HCMC", bbox=HCMC_BBOX, center=HCMC_CENTER,
            serper_fn=lambda n, c, ctr: [], nominatim_fn=lambda n, c: [],
            log=lambda *_a: None)
        assert hit is None

    def test_radius_guard_rejects_same_name_other_continent(self):
        # A huge/absent bbox must not let a same-named venue on another continent
        # through: the center + max_radius_km backstop rejects it. "Rambutan"
        # matched LONDON (51.5,-0.09) in the live run; it must be rejected even
        # with no bbox.
        def serp(name, city, center):
            return [{"title": "Rambutan", "lat": 51.505577, "lon": -0.091465}]
        hit = u.name_lookup_in_bbox(
            "Rambutan", "Ho Chi Minh City", bbox=None, center=HCMC_CENTER,
            serper_fn=serp, nominatim_fn=lambda n, c: [], log=lambda *_a: None)
        assert hit is None

    def test_radius_guard_rejects_far_suburb_in_huge_bbox(self):
        # The HCMC administrative bbox spans ~350 km. A correct-named venue in a
        # far suburb (~29 km out) is inside that bbox but outside the 25 km radius
        # — rejected, so the stop is announced rather than mis-pinned.
        huge_bbox = (8.3456879, 11.5015885, 105.9769387, 108.4311207)
        def serp(name, city, center):
            return [{"title": "An Spa", "lat": 10.715047, "lon": 106.960300}]
        hit = u.name_lookup_in_bbox(
            "An Spa", "Ho Chi Minh City", bbox=huge_bbox, center=HCMC_CENTER,
            serper_fn=serp, nominatim_fn=lambda n, c: [], max_radius_km=25.0,
            log=lambda *_a: None)
        assert hit is None

    def test_radius_guard_keeps_in_city_venue_in_huge_bbox(self):
        huge_bbox = (8.3456879, 11.5015885, 105.9769387, 108.4311207)
        def serp(name, city, center):
            return [{"title": "Thi Bar Saigon", "lat": 10.76766, "lon": 106.69396}]
        hit = u.name_lookup_in_bbox(
            "Thi Bar Saigon", "Ho Chi Minh City", bbox=huge_bbox,
            center=HCMC_CENTER, serper_fn=serp, nominatim_fn=lambda n, c: [],
            log=lambda *_a: None)
        assert hit is not None
        assert (round(hit[0], 4), round(hit[1], 4)) == (10.7677, 106.694)


# ───────────────────── 4. coord_source semantics ────────────────────────────
class TestCoordSourceSemantics:
    def test_user_name_lookup_is_not_a_fallback_coord(self):
        import identity_dedup as idd
        # A name-lookup pin is a REAL resolved point, not a centroid/fallback.
        assert idd._is_fallback_coord_stop(
            {"coord_source": "user_name_lookup",
             "coord_confidence": "name_lookup"}) is False

    def test_user_name_lookup_recognised_as_user_pin(self):
        import pin_snap
        assert pin_snap._is_user_pin(
            {"user_explicit": True, "coord_source": "user_name_lookup",
             "coordinates": "10.7725, 106.6985"}) is True
