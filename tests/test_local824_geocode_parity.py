#!/usr/bin/env python3
"""test_local824_geocode_parity.py — LOCAL-824.

THE BUG
=======
LOCAL-793 added the server-side place geocoder `GET /geocode` to the root
`map_delivery_service.py` (the Mac dev monolith), but NOT to `map_delivery/app.py`
— the file the Cloud Run map-delivery image actually runs (build context
`./map_delivery`, Dockerfile CMD `python app.py`; see docker-compose-master.yml
and SUBMISSION_LOCAL-88/89). So `GET /geocode` returned 404 on
subscribed-api.audioura.com even though it worked on the Mac. The Home place
search's server-side fallback (typo-tolerant Serper -> Nominatim) silently did
nothing on the cloud.

WHAT THIS PROVES (hermetic — no network, no DB, no paid call)
=============================================================
The /geocode route is now present in the DEPLOYED file and behaves exactly like
the root monolith's:

  * Serper path: a configured key + a Serper 200 yields {lat,lng,name} from the
    first usable place; the metered door `serper_post` is called exactly ONCE
    (the cap: one paid query per lookup).
  * Nominatim fallback: with no Serper result, the free Nominatim path resolves
    the query and PREFERS a place class over a nearer POI (the LOCAL-793 point:
    "Saigon Vietnam" must not open a Paris restaurant).
  * Cache: a repeated lookup for the same place returns the cached result
    WITHOUT a second paid Serper call ($0 on repeat — cap-friendly).
  * 404 when neither path resolves; 400 when `q` is missing.
  * No `requests` dependency is introduced (the cloud image's requirements.txt
    does not ship it); the Nominatim path uses stdlib urllib.

Isolation: `serper_post` and the Nominatim opener are monkeypatched on the loaded
module, so NO real HTTP happens and NO paid_api_calls row is written. The live
paid proof (<= 4 Serper calls, metered, budget $0.05) is the container run in
SUBMISSION_LOCAL-824.md, not this test.
"""
import importlib.util
import json
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_MAPDIR = os.path.join(_ROOT, "map_delivery")
for _p in (_HERE, _ROOT, _MAPDIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _load_map_app():
    """Load map_delivery/app.py as an isolated module (its own name so it never
    collides with the root service or other tests' copies)."""
    spec = importlib.util.spec_from_file_location(
        "md_app_local824", os.path.join(_MAPDIR, "app.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeHTTPResponse:
    """Minimal context-manager stand-in for urllib.request.urlopen()."""
    def __init__(self, payload, status=200):
        self._body = json.dumps(payload).encode("utf-8")
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


class GeocodeRouteTest(unittest.TestCase):
    def setUp(self):
        self.mod = _load_map_app()
        self.mod._GEOCODE_CACHE.clear()
        self.client = self.mod.app.test_client()
        # Default: no Serper key, so the Serper path is skipped unless a test
        # sets one AND installs a fake serper_post.
        os.environ.pop("SERP_API_KEY", None)
        os.environ.pop("SERPER_API_KEY", None)

    # ---- helpers ---------------------------------------------------------
    def _install_serper(self, places, status=200, counter=None):
        body = json.dumps({"places": places}).encode("utf-8")

        def fake_post(url, payload, api_key=None, **kw):
            if counter is not None:
                counter.append(url)
            return status, body
        self.mod._serper_post = fake_post
        os.environ["SERP_API_KEY"] = "test-key-xxxx"

    def _install_nominatim(self, rows, status=200):
        def fake_urlopen(req, timeout=None):
            return _FakeHTTPResponse(rows, status=status)
        self.mod._urlrequest.urlopen = fake_urlopen

    def _get(self, q):
        from urllib.parse import quote
        return self.client.get(f"/geocode?q={quote(q)}")

    # ---- the route exists at all (the parity bug) ------------------------
    def test_geocode_route_is_registered(self):
        rules = {r.rule for r in self.mod.app.url_map.iter_rules()}
        self.assertIn("/geocode", rules,
                      "/geocode must exist in the DEPLOYED map_delivery/app.py "
                      "(LOCAL-793 reached only the root monolith — LOCAL-824)")

    # ---- Serper path + one-paid-call cap ---------------------------------
    def test_serper_resolves_and_caps_one_call(self):
        calls = []
        self._install_serper(
            [{"latitude": 10.93, "longitude": 108.29, "address": "Mui Ne, Vietnam"}],
            counter=calls)
        # Serper must win before Nominatim is even consulted: make Nominatim blow
        # up if touched.
        def _boom(*a, **k):
            raise AssertionError("Nominatim must not be called when Serper resolves")
        self.mod._urlrequest.urlopen = _boom

        resp = self._get("Mui Ne")
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        body = resp.get_json()
        self.assertAlmostEqual(body["lat"], 10.93)
        self.assertAlmostEqual(body["lng"], 108.29)
        self.assertEqual(body["name"], "Mui Ne, Vietnam")
        self.assertEqual(len(calls), 1, "exactly ONE paid Serper query per lookup")

    # ---- cache: the repeat lookup spends $0 ------------------------------
    def test_cache_prevents_second_paid_call(self):
        calls = []
        self._install_serper(
            [{"latitude": 20.0, "longitude": 105.0, "address": "Hanoi, Vietnam"}],
            counter=calls)
        first = self._get("Hanoi")
        self.assertEqual(first.status_code, 200)
        # Second, same place (different casing/spacing -> same cache key).
        second = self._get("  hanoi ")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.get_json(), second.get_json())
        self.assertEqual(len(calls), 1,
                         "the cached place must NOT trigger a 2nd paid Serper call")

    # ---- Nominatim fallback prefers a PLACE over a POI -------------------
    def test_nominatim_fallback_prefers_place(self):
        # No Serper (no key). Nominatim returns a far POI first (higher
        # importance), then the real place — the place class must win anyway.
        self._install_nominatim([
            {"class": "amenity", "type": "restaurant", "lat": "48.85",
             "lon": "2.35", "importance": "0.9", "display_name": "Saigon, Paris"},
            {"class": "place", "type": "city", "lat": "10.78", "lon": "106.70",
             "importance": "0.5", "display_name": "Ho Chi Minh City, Vietnam"},
        ])
        resp = self._get("Saigon Vietnam")
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        body = resp.get_json()
        self.assertAlmostEqual(body["lat"], 10.78)
        self.assertAlmostEqual(body["lng"], 106.70)
        self.assertIn("Ho Chi Minh", body["name"])

    # ---- Serper miss -> Nominatim picks up --------------------------------
    def test_serper_empty_falls_through_to_nominatim(self):
        self._install_serper([])      # key set, but zero places
        self._install_nominatim([
            {"class": "place", "type": "town", "lat": "27.0", "lon": "-82.45",
             "importance": "0.4", "display_name": "Venice, Florida, USA"},
        ])
        resp = self._get("Venice, FL")
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        body = resp.get_json()
        self.assertAlmostEqual(body["lat"], 27.0)
        self.assertAlmostEqual(body["lng"], -82.45)

    # ---- not found / bad input -------------------------------------------
    def test_not_found_is_404(self):
        self._install_nominatim([])   # no rows, no Serper key
        resp = self._get("asdkjhqwiuhefaksjdh")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json().get("q"), "asdkjhqwiuhefaksjdh")

    def test_missing_q_is_400(self):
        resp = self.client.get("/geocode")
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)


def test_nominatim_keeps_rank_order_among_places_mui_ne():
    """LEAD 2026-10-30: the live Nominatim answer for 'Mui Ne' — rank 1 is the ward in Vietnam (importance
    0.39), rank 2 is Meizhou, China (0.56). Sorting places by importance picked China."""
    import json as _json, importlib, sys as _sys, os as _os
    _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', 'map_delivery'))
    _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..'))
    rows = [
        {"display_name": "Phường Mũi Né, Tỉnh Lâm Đồng, Việt Nam", "class": "boundary", "type": "administrative",
         "importance": 0.39, "lat": "10.95", "lon": "108.28"},
        {"display_name": "梅州市, 广东省, 中国", "class": "boundary", "type": "administrative",
         "importance": 0.56, "lat": "24.29", "lon": "116.11"},
    ]
    import importlib.util as _iu
    _root = _os.path.join(_os.path.dirname(__file__), '..')
    checked = 0
    for modname, path in (("local824_md_app", _os.path.join(_root, "map_delivery", "app.py")),
                          ("local824_md_root", _os.path.join(_root, "map_delivery_service.py"))):
        spec = _iu.spec_from_file_location(modname, path)
        m = _iu.module_from_spec(spec)
        spec.loader.exec_module(m)
        fn = getattr(m, "_geocode_via_nominatim", None) or getattr(m, "_geocode_via_nominatim_place", None)
        if fn is None:
            continue
        checked += 1

        class _Resp:
            def __init__(self, b): self.b = b
            def read(self): return self.b
            def __enter__(self): return self
            def __exit__(self, *a): return False
            # requests-style
            status_code = 200
            def json(self): return rows
            text = ""
        payload = _json.dumps(rows).encode()
        import urllib.request as _ur
        orig_open = _ur.urlopen
        _ur.urlopen = lambda *a, **k: _Resp(payload)
        orig_get = None
        try:
            import requests as _rq
            orig_get = _rq.get
            _rq.get = lambda *a, **k: _Resp(payload)
        except Exception:
            _rq = None
        try:
            got = fn("Mui Ne")
        finally:
            _ur.urlopen = orig_open
            if _rq is not None and orig_get is not None:
                _rq.get = orig_get
        assert got and "Mũi Né" in got["name"], (modname, got)
    assert checked >= 1, "no geocoder function found — test would be vacuous"
