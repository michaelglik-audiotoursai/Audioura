#!/usr/bin/env python3
"""test_local805b_places_count.py — LOCAL-805B.

"Massage and spa near Ben Thanh Market, District 1, Ho Chi Minh City" (3) was
delivered on the PLACES path as only 2 of 3 real spas while Google/Serper Places
lists ten within ~0.6 km of Ben Thanh Market. The LOCAL-805 note blamed "the LLM
spa pool was thin", but on the places path the stops come from Serper Places — so
the shortfall was a FILTER dropping real, open, in-scope spas, not a thin pool.

ROOT CAUSE (traced offline against the recorded Serper payload):
``places_search._bind_in_scope``'s TOWN-NAME MISMATCH guard. The landmark geocode
of "Ben Thanh Market, District 1, Ho Chi Minh City" returns NO bounding box
(Nominatim gives a point, or nothing), so the guard — not a bbox — decides scope.
``_address_town`` read the SECOND comma-part of the Serper address as the town;
two of the ten spas have a noise segment there:

  * "AN's spa 2 - DTC Branch …"  →  "12 Đặng Trần Côn, P, Bến Thành, …"   → "p"
  * "Norah Spa"                   →  "114 Lê Thị Hồng Gấm, Street, Bến Thành, …"→ "street"

so their "town" read as "p"/"street" ≠ the scope town "ben thanh market", and with
no bbox the guard DROPPED them — real, open, in-scope spas. US addresses
("…, Norwood, MA 02062") parse cleanly, which is why "coffee near Boston Common"
delivered 3/3 while the Ben Thanh spa tour delivered 2/3.

THE FIX (places_search.py): ``_address_town`` / ``_parse_address_components`` now
skip a noise comma-part (street-type words, a bare "P"/"Q" admin-unit prefix, a
pure number/postcode) and take the first GENUINE locality part — "Bến Thành" in
both cases — so the two spas bind in scope and N stops are delivered.

This test uses the RECORDED Serper Places payload (captured once, 2026-10-29, for
the query/ll in the ticket; raw JSON in scratch/benthanh_spa_serper.json). Pure,
offline, deterministic — no network, no paid API.

    python3 -m pytest tests/test_local805b_places_count.py -q
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import places_search as ps
import stop_existence_gate as gate


SCOPE = "Ben Thanh Market, District 1, Ho Chi Minh City"
# Ben Thanh Market centre (the geocoded landmark the live places path centres on).
BEN_THANH_CENTER = (10.7726, 106.6983)

# ── RECORDED Serper Places payload (captured live once, 2026-10-29) ──────────
# "massage and spa in Ben Thanh Market, District 1, Ho Chi Minh City" — the exact
# body Serper returned (10 real spas, all in Bến Thành / District 1, within
# ~0.6 km of the market). Two carry the noise second comma-part that the old
# town-parse mis-read as the town ("P" ward prefix; a literal "Street" tail).
_SERPER_BENTHANH_SPA = {
    "places": [
        {"position": 1, "title": ".Haisalon The Spa",
         "address": "165 Lý Tự Trọng, Bến Thành, Hồ Chí Minh 700000, Vietnam",
         "latitude": 10.773316, "longitude": 106.69644, "rating": 4.9,
         "ratingCount": 5400, "category": "Massage spa",
         "website": "https://haithespa.com/", "cid": "18249158308092313642"},
        {"position": 2,
         "title": "AN\u2019s spa 2 - DTC Branch - Traditional Massage & Skincare",
         "address": "12 \u0110\u1eb7ng Tr\u1ea7n C\u00f4n, P, B\u1ebfn Th\u00e0nh, "
                    "H\u1ed3 Ch\u00ed Minh 700000, Vietnam",
         "latitude": 10.772513, "longitude": 106.6942, "rating": 4.9,
         "ratingCount": 3500, "category": "Massage spa",
         "website": "https://an-spa.vn/", "cid": "4339414946822109064"},
        {"position": 3, "title": "Norah Spa",
         "address": "114 L\u00ea Th\u1ecb H\u1ed3ng G\u1ea5m, Street, B\u1ebfn Th\u00e0nh, "
                    "H\u1ed3 Ch\u00ed Minh 700000, Vietnam",
         "latitude": 10.769055, "longitude": 106.69752, "rating": 4.9,
         "ratingCount": 4900, "category": "Massage spa",
         "website": "http://www.norahspa.com/", "cid": "5986186213544795615"},
        {"position": 4, "title": "AnNam Spa - Thu Khoa Huan, Ben Thanh Market",
         "address": "25 - 27 Th\u1ee7 Khoa Hu\u00e2n, B\u1ebfn Th\u00e0nh, H\u1ed3 Ch\u00ed Minh, Vietnam",
         "latitude": 10.773548, "longitude": 106.697235, "rating": 4.9,
         "ratingCount": 1900, "category": "Tourist attraction",
         "website": "http://annamspa.vn/", "cid": "12316010368314683690"},
        {"position": 5, "title": "CiCi International Spa",
         "address": "154 L\u00fd T\u1ef1 Tr\u1ecdng, B\u1ebfn Th\u00e0nh, H\u1ed3 Ch\u00ed Minh, Vietnam",
         "latitude": 10.773473, "longitude": 106.69609, "rating": 4.9,
         "ratingCount": 3400, "category": "Massage spa",
         "website": "https://cicispa154.com/", "cid": "14964970808182746401"},
        {"position": 6,
         "title": "The Spa by SOL\u00c9A - Head Spa & Massage | District 1 Branch",
         "address": "35/5 Nguy\u1ec5n Trung Tr\u1ef1c, B\u1ebfn Th\u00e0nh, H\u1ed3 Ch\u00ed Minh, Vietnam",
         "latitude": 10.77496, "longitude": 106.69764, "rating": 5,
         "ratingCount": 194, "category": "Massage spa",
         "website": "https://booking.thespa.vn/", "cid": "6067727422402794790"},
        {"position": 7, "title": "La Maison Spa Saigon",
         "address": "40 - 42 Phan B\u1ed9i Ch\u00e2u, B\u1ebfn Th\u00e0nh, H\u1ed3 Ch\u00ed Minh 700000, Vietnam",
         "latitude": 10.773273, "longitude": 106.698555, "rating": 5,
         "ratingCount": 814, "category": "Health spa",
         "website": "https://lamaisonspa.com.vn/saigon.html", "cid": "196895226153177672"},
        {"position": 8,
         "title": "AN\u2019s spa 3 - NTB Branch - Traditional Massage & Skincare",
         "address": "130 Nguy\u1ec5n Th\u00e1i B\u00ecnh, B\u1ebfn Th\u00e0nh, H\u1ed3 Ch\u00ed Minh, Vietnam",
         "latitude": 10.768211, "longitude": 106.69847, "rating": 4.9,
         "ratingCount": 3100, "category": "Spa",
         "website": "https://an-spa.vn/", "cid": "11559849738639647804"},
        {"position": 9,
         "title": "M\u1ed9c Kim Spa 2 - Ben Thanh Branch - Massage Near Me, Head Spa & Facial District 1",
         "address": "143 L\u00ea Th\u1ecb H\u1ed3ng G\u1ea5m, B\u1ebfn Th\u00e0nh, H\u1ed3 Ch\u00ed Minh 00700, Vietnam",
         "latitude": 10.767604, "longitude": 106.69628, "rating": 4.8,
         "ratingCount": 772, "category": "Massage spa",
         "website": "https://duongsinhspa.vn/en/ben-thanh-branch/", "cid": "14433527728175362007"},
        {"position": 10, "title": "Laboho Spa",
         "address": "17 \u0110\u1eb7ng Th\u1ecb Nhu, B\u1ebfn Th\u00e0nh, H\u1ed3 Ch\u00ed Minh 700000, Vietnam",
         "latitude": 10.76944, "longitude": 106.69745, "rating": 4.9,
         "ratingCount": 3000, "category": "Massage spa",
         "website": "https://www.laboho.vn/", "cid": "8612662696653497119"},
    ]
}

# The two spas the old town-parse dropped (noise second comma-part).
_PREV_DROPPED = {
    "AN\u2019s spa 2 - DTC Branch - Traditional Massage & Skincare",
    "Norah Spa",
}


def _install_serper(monkeypatch, body):
    """Enable Serper Places and serve the recorded body for any query. The scope
    geocode is faked (center, NO bbox) to the live condition that triggered the
    defect: the landmark geocode gives a point but no bounding box."""
    monkeypatch.setenv("SERP_API_KEY", "test-key")
    monkeypatch.setenv("SERP_PROVIDER", "serper")
    ps.clear_cache()

    def _fake_post(url, payload, api_key=None, timeout=15, extra_headers=None):
        return 200, json.dumps(body).encode("utf-8")
    monkeypatch.setattr(ps, "_serper_post", _fake_post)
    # The places path geocodes the scope CENTRE but gets NO bbox for a landmark.
    monkeypatch.setattr(gate, "_geocode_scope_center", lambda s: BEN_THANH_CENTER)
    monkeypatch.setattr(gate, "_geocode_scope_bbox", lambda s: None)


# ───────────────────── 1. address-town parse (the fix) ───────────────────────
class TestAddressTownParse:
    """``_address_town`` reads the real locality, skipping a noise comma-part."""

    def test_vietnamese_ward_prefix_noise_skipped(self):
        # "12 Đặng Trần Côn, P, Bến Thành, …" — the "P" is noise, town is Bến Thành.
        rec = {"_serper_address":
               "12 \u0110\u1eb7ng Tr\u1ea7n C\u00f4n, P, B\u1ebfn Th\u00e0nh, "
               "H\u1ed3 Ch\u00ed Minh 700000, Vietnam", "address": {}}
        assert ps._address_town(rec) == "ben thanh"

    def test_vietnamese_literal_street_tail_skipped(self):
        rec = {"_serper_address":
               "114 L\u00ea Th\u1ecb H\u1ed3ng G\u1ea5m, Street, B\u1ebfn Th\u00e0nh, "
               "H\u1ed3 Ch\u00ed Minh 700000, Vietnam", "address": {}}
        assert ps._address_town(rec) == "ben thanh"

    def test_clean_vietnamese_address_unchanged(self):
        rec = {"_serper_address":
               "165 L\u00fd T\u1ef1 Tr\u1ecdng, B\u1ebfn Th\u00e0nh, H\u1ed3 Ch\u00ed Minh 700000, Vietnam",
               "address": {}}
        assert ps._address_town(rec) == "ben thanh"

    def test_us_address_town_unchanged(self):
        # LOCAL-786: a clean US address still reads "norwood" as the town.
        rec = {"_serper_address": "678 Washington St, Norwood, MA 02062", "address": {}}
        assert ps._address_town(rec) == "norwood"

    def test_structured_city_from_noise_is_ignored(self):
        # A record whose address.city was set from a noise segment is not read as
        # the town (the structured read now skips noise too).
        rec = {"address": {"city": "P"},
               "_serper_address": "12 X, P, B\u1ebfn Th\u00e0nh, H\u1ed3 Ch\u00ed Minh, Vietnam"}
        assert ps._address_town(rec) == "ben thanh"

    def test_parse_components_city_is_locality_not_noise(self):
        comp = ps._parse_address_components(
            "12 \u0110\u1eb7ng Tr\u1ea7n C\u00f4n, P, B\u1ebfn Th\u00e0nh, H\u1ed3 Ch\u00ed Minh 700000, Vietnam")
        assert ps._strip_accents(comp["city"]).lower() == "ben thanh"
        # US address still gives Norwood.
        comp2 = ps._parse_address_components("678 Washington St, Norwood, MA 02062")
        assert comp2["city"] == "Norwood"


# ─────────── 2. scope-bind keeps ALL ten real spas (no bbox, radius) ──────────
class TestScopeBindKeepsAllRealSpas:
    def test_all_ten_spas_bind_in_scope(self, monkeypatch):
        _install_serper(monkeypatch, _SERPER_BENTHANH_SPA)
        out = ps.places_search(
            "massage and spa in " + SCOPE, SCOPE,
            scope_center=BEN_THANH_CENTER, scope_bbox=None, limit=25)
        names = {r["name"] for r in out}
        # Every recorded spa (cleaned title) survives — 10/10.
        assert len(out) == 10
        # The two the old parse dropped are now kept.
        for dropped in _PREV_DROPPED:
            cleaned = ps.clean_place_title(dropped)
            assert cleaned in names, f"{cleaned!r} must bind in scope now"

    def test_prev_dropped_spas_were_the_regression(self, monkeypatch):
        # Prove the SPECIFIC records recover: AN's spa 2 and Norah Spa.
        _install_serper(monkeypatch, _SERPER_BENTHANH_SPA)
        out = ps.places_search(
            "massage and spa in " + SCOPE, SCOPE,
            scope_center=BEN_THANH_CENTER, scope_bbox=None, limit=25)
        names = {r["name"] for r in out}
        assert any("AN" in n and "spa 2" in n for n in names)
        assert "Norah Spa" in names


# ─────────── 3. N stops delivered: replenish yields >= requested ─────────────
class TestReplenishDeliversN:
    def test_business_replenish_returns_at_least_three(self, monkeypatch):
        _install_serper(monkeypatch, _SERPER_BENTHANH_SPA)
        cands = gate.business_replenish_candidates(
            "massage and spa", SCOPE, needed=3, exclude=set())
        assert len(cands) == 3, "N=3 real in-scope spas must be delivered"
        for c in cands:
            assert c["verified"] is True
            assert c["lat"] and c["lng"]

    def test_replenish_can_supply_the_whole_pool(self, monkeypatch):
        # With needed high, every real spa is available (>= 8, ticket's "dozens").
        _install_serper(monkeypatch, _SERPER_BENTHANH_SPA)
        cands = gate.business_replenish_candidates(
            "massage and spa", SCOPE, needed=10, exclude=set())
        assert len(cands) >= 8
        names = {c["name"] for c in cands}
        # The two previously-dropped spas are in the pool.
        assert any("AN" in n and "spa 2" in n for n in names)
        assert "Norah Spa" in names

    def test_escalation_ladder_delivers_three(self, monkeypatch):
        # Through the full ladder used by the generator's maps-first top-up.
        _install_serper(monkeypatch, _SERPER_BENTHANH_SPA)
        cands = gate.replenish_with_escalation(
            "business", "massage and spa", SCOPE, 3, exclude=set(),
            allow_grounding=False)
        assert len(cands) == 3


# ─────────── 4. LOCAL-786 preserved: a true out-of-town place is dropped ──────
class TestLocal786Preserved:
    def test_norwood_place_still_rejected_on_west_roxbury_scope(self):
        rec = {"name": "Byblos", "lat": "42.1900", "lon": "-71.1990",
               "_serper_address": "678 Washington St, Norwood, MA 02062",
               "address": {}}
        kept = ps._bind_in_scope([rec], "West Roxbury, MA",
                                 (42.2843, -71.1627),
                                 ps._zoom_for_scope("West Roxbury, MA"), bbox=None)
        assert kept == [], "a genuine Norwood place is still out of scope for WR"

    def test_west_roxbury_street_only_place_kept(self):
        rec = {"name": "Al Wadi", "lat": "42.2772", "lon": "-71.1726",
               "_serper_address": "1249 VFW Pkwy", "address": {}}
        kept = ps._bind_in_scope([rec], "West Roxbury, MA",
                                 (42.2843, -71.1627),
                                 ps._zoom_for_scope("West Roxbury, MA"), bbox=None)
        assert [k["name"] for k in kept] == ["Al Wadi"]


# ─────────── 5. recorded fixture integrity (the payload is real) ─────────────
class TestRecordedFixture:
    def test_ten_real_spas_near_ben_thanh(self):
        places = _SERPER_BENTHANH_SPA["places"]
        assert len(places) == 10
        # Every recorded spa is within ~0.7 km of the landmark centre.
        for p in places:
            d = ps._haversine_km(BEN_THANH_CENTER, (p["latitude"], p["longitude"]))
            assert d <= 0.7, f"{p['title']!r} is {d:.2f} km from Ben Thanh"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
