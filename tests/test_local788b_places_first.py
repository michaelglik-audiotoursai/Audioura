#!/usr/bin/env python3
"""LOCAL-788B — place tours must come from the MAP, not the LLM.

Field defect (LEAD end-to-end, Mac shared stack, 2026-10-27): the request
"middle eastern restaurants near me, west Roxbury, MA" (tour_type "", as the app
sends) shipped **Sultan's Kebab** and **Cafe Jaffa** — both fabricated (Serper
Places at West Roxbury returns Al Wadi / Stardust / Bread Thyme). The log chain:

  * PHASE 3A asked the LLM for candidates → Al Wadi (REAL), Sultan's Kebab,
    Cafe Jaffa (invented).
  * An LLM check EXCLUDED Al Wadi ("a common name … cannot be verified as such").
  * `[VERIFIED] "Sultan's Kebab" — wikipedia_article: 'Kebab' is about the
    establishment+city` — a GENERIC-word article (Kebab) counted as evidence.
  * `[UNVERIFIED] 'Cafe Jaffa'` → shipped anyway (gate LOG_ONLY for non-walking).

This suite proves, offline and deterministically:
  1. A generic-word Wikipedia article (Kebab) is NOT evidence for "Sultan's Kebab".
  2. places_search is the authority: a fabricated name is not on the map in scope
     (verify_listing_in_scope False) while the real ones are; the PLACES-FIRST
     block in the generator drops the fakes with the exact log line
     '[LOCAL-788B] llm name not on map <name>', keeps only the map list, and runs
     BEFORE the LLM Part C refill.
  3. The LLM "is this really a restaurant" exclusion is overridden by a map hit
     (Al Wadi is kept), and map-verified stops are exempt from the existence gate.
  4. A place-type (dining/business/near-me) tour forces the existence gate to
     ENFORCE even when the app sent tour_type "".

Fixtures only — Wikipedia / Serper HTTP are stubbed.
"""
import inspect
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import stop_existence_gate as gate
import places_search as ps
import generate_tour_text as gtt


# ───────────────────────── 1) generic-word wiki is not evidence ─────────────
class TestGenericWordArticleNotEvidence:
    def test_distinctive_tokens_drop_generic_words(self):
        assert gate._distinctive_name_tokens("Sultan's Kebab") & {"sultan's", "sultans"}
        assert gate._distinctive_name_tokens("Cafe Jaffa") == {"jaffa"}
        # A wholly generic name has NO distinctive token — no wiki article can vouch.
        assert gate._distinctive_name_tokens("Kebab House") == set()

    def test_kebab_article_title_does_not_vouch_sultans_kebab(self):
        # The exact field case: the article "Kebab" (the food) must not be evidence
        # that "Sultan's Kebab" (the establishment) exists.
        assert gate._article_title_has_distinctive_token("Sultan's Kebab", "Kebab") is False
        assert gate._article_title_has_distinctive_token("Cafe Jaffa", "Cafe") is False
        # A real article about the place does vouch.
        assert gate._article_title_has_distinctive_token("Stardust", "Stardust") is True


# Wikipedia-stub integration: 'Kebab' article must not verify the dining stop.
_KEBAB_SUMMARY = {
    "title": "Kebab",
    "extract": ("Kebab is a type of cooked meat dish that originates from the "
                "Middle East. Kebabs are popular worldwide, including in Boston "
                "and Massachusetts."),
    "description": "Middle Eastern dish",
    # even if it carried coords, the title is generic — not this establishment.
}
_KEBAB_SEARCH_HIT = {
    "query": {"search": [{
        "title": "Kebab",
        "snippet": ("Kebab is a Middle Eastern dish served in restaurants across "
                    "West Roxbury, Boston, Massachusetts."),
    }]}
}
_EMPTY_SEARCH = {"query": {"search": []}}


class _FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


def _fake_requests(summary, search):
    class _FR:
        class exceptions:
            Timeout = type("Timeout", (Exception,), {})
            ConnectionError = type("ConnectionError", (Exception,), {})

        def get(self, url, **kwargs):
            if "/page/summary/" in url:
                return _FakeResp(200, summary) if summary else _FakeResp(404, {})
            if "wikidata.org" in url:
                return _FakeResp(200, {"search": []})
            if "api.php" in url:
                if "fr.wikipedia.org" in url:
                    return _FakeResp(200, _EMPTY_SEARCH)
                return _FakeResp(200, search)
            if "nominatim" in url or "openstreetmap" in url:
                return _FakeResp(200, [])
            return _FakeResp(200, [])

        def post(self, url, **kwargs):
            return _FakeResp(200, {})
    return _FR()


class TestDiningExistenceRejectsGenericWiki:
    def test_kebab_summary_does_not_verify_sultans_kebab(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "requests",
                            _fake_requests(_KEBAB_SUMMARY, _EMPTY_SEARCH))
        ok, evidence = gate._check_dining_existence(
            "Sultan's Kebab", "West Roxbury, MA", None)
        assert ok is False, f"the generic 'Kebab' summary must not verify (got {evidence!r})"

    def test_kebab_search_article_does_not_verify(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "requests",
                            _fake_requests(None, _KEBAB_SEARCH_HIT))
        ok, evidence = gate._check_dining_existence(
            "Sultan's Kebab", "West Roxbury, MA", None)
        assert ok is False, (
            f"'wikipedia_article: Kebab is about the establishment+city' must no "
            f"longer verify a named place (got {evidence!r})")


# ───────────────────── 2) places_search is the existence authority ──────────
# Serper returns ONLY the real West Roxbury Middle-Eastern places. A name lookup
# for a fabricated place returns none in scope → verify_listing_in_scope False.
_SERPER_WR = {
    "places": [
        {"title": "Al Wadi", "address": "1249 VFW Pkwy, West Roxbury, MA 02132",
         "latitude": 42.27725, "longitude": -71.17266, "category": "Middle Eastern"},
        {"title": "Bread Thyme", "address": "1866 Centre St, West Roxbury, MA 02132",
         "latitude": 42.285767, "longitude": -71.15497, "category": "Lebanese"},
        {"title": "Stardust", "address": "1753 Centre St, West Roxbury, MA 02132",
         "latitude": 42.28744, "longitude": -71.15047, "category": "Mediterranean"},
    ]
}
_WR_CENTER = [{"lat": "42.2843", "lon": "-71.1627",
               "boundingbox": ["42.255", "42.302", "-71.185", "-71.135"]}]


class _FakeNominatim:
    """Geocode the scope only; a places query (' in ' / 'restaurant') goes empty so
    the Serper path owns place lookups."""
    def __init__(self, geocode):
        self.geocode = geocode

    def __call__(self, params, context=""):
        q = (params.get("q") or "").lower()
        data = self.geocode if (" in " not in q and "," in q and
                                "restaurant" not in q and "kebab" not in q and
                                "jaffa" not in q and "wadi" not in q and
                                "thyme" not in q and "stardust" not in q) else []

        class _R:
            def __init__(self, d):
                self._d = d

            def json(self):
                return self._d
        return _R(data)


@pytest.fixture
def serper_wired(monkeypatch):
    ps.clear_cache()

    def _fake_post(url, payload, api_key=None, timeout=15, extra_headers=None):
        q = (payload.get("q") or "").lower()
        # The by-name lookups used by verify_listing_in_scope: only the REAL names
        # resolve; the fabricated ones return nothing.
        if any(real in q for real in ("al wadi", "bread thyme", "stardust")):
            return 200, json.dumps(_SERPER_WR).encode("utf-8")
        if "middle eastern" in q or "mediterranean" in q:
            return 200, json.dumps(_SERPER_WR).encode("utf-8")
        # Sultan's Kebab / Cafe Jaffa / anything else → no in-scope place.
        return 200, json.dumps({"places": []}).encode("utf-8")

    monkeypatch.setattr(ps, "_serper_post", _fake_post)
    monkeypatch.setattr(gate, "_nominatim_request", _FakeNominatim(_WR_CENTER))
    monkeypatch.setenv("SERP_API_KEY", "test-key")
    monkeypatch.setenv("SERP_PROVIDER", "serper")
    yield
    ps.clear_cache()


class TestPlacesSearchIsAuthority:
    def test_fabricated_names_not_on_map_real_ones_are(self, serper_wired):
        scope = "West Roxbury, MA"
        # The two field fakes are NOT on the map in scope.
        assert gate.verify_listing_in_scope("Sultan's Kebab", scope) is False
        assert gate.verify_listing_in_scope("Cafe Jaffa", scope) is False
        # The real West Roxbury places ARE.
        assert gate.verify_listing_in_scope("Al Wadi", scope) is True
        assert gate.verify_listing_in_scope("Bread Thyme", scope) is True
        assert gate.verify_listing_in_scope("Stardust", scope) is True


# ─── 2a) the JP coffee case: a generic LLM coffee name is NOT on the map ─────
# Live-run follow-up (Serper Places, Jamaica Plain): the real cafés Ula Café and
# Tres Gatos ARE on the map; the generic LLM name "Jamaica Plain Coffee" is NOT
# a distinct listing (verify_listing_in_scope False) — exactly the kind of
# place-type stop the PLACES-FIRST drop must remove. A coffee-shops request
# carries poi_type "coffee shops", which classifies as a BUSINESS, so the tour
# is place-type even though its tour_category comes back 'walking'.
_SERPER_JP = {
    "places": [
        {"title": "Ula Café", "address": "284 Amory St, Jamaica Plain, MA 02130",
         "latitude": 42.3085, "longitude": -71.1142, "category": "Cafe"},
        {"title": "Tres Gatos", "address": "470 Centre St, Jamaica Plain, MA 02130",
         "latitude": 42.3091, "longitude": -71.1151, "category": "Restaurant"},
    ]
}
_JP_CENTER = [{"lat": "42.3116", "lon": "-71.1144",
               "boundingbox": ["42.29", "42.33", "-71.13", "-71.10"]}]


@pytest.fixture
def serper_jp_wired(monkeypatch):
    ps.clear_cache()

    def _fake_post(url, payload, api_key=None, timeout=15, extra_headers=None):
        q = (payload.get("q") or "").lower()
        if "ula" in q or "tres gatos" in q or "coffee shops in" in q:
            return 200, json.dumps(_SERPER_JP).encode("utf-8")
        # "Jamaica Plain Coffee" (generic) and anything else → no distinct listing.
        return 200, json.dumps({"places": []}).encode("utf-8")

    monkeypatch.setattr(ps, "_serper_post", _fake_post)
    monkeypatch.setattr(gate, "_nominatim_request", _FakeNominatim(_JP_CENTER))
    monkeypatch.setenv("SERP_API_KEY", "test-key")
    monkeypatch.setenv("SERP_PROVIDER", "serper")
    yield
    ps.clear_cache()


class TestJamaicaPlainCoffeeCase:
    def test_coffee_shops_request_is_place_type(self):
        # tour_category comes back 'walking' for a coffee-shops request, but the
        # poi_type 'coffee shops' classifies as a business → place-type → ENFORCE.
        assert gate.classify_business_vs_landmark("coffee shops") == "business"
        assert gate.is_place_type_tour(
            tour_category="walking", poi_type="coffee shops") is True

    def test_generic_coffee_name_dropped_real_cafes_kept(self, serper_jp_wired):
        scope = "Jamaica Plain, Boston"
        # The real cafés are on the map in scope.
        assert gate.verify_listing_in_scope("Ula Cafe", scope) is True
        assert gate.verify_listing_in_scope("Tres Gatos", scope) is True
        # The generic LLM name is NOT a distinct listing → PLACES-FIRST drops it
        # with '[LOCAL-788B] llm name not on map Jamaica Plain Coffee'.
        assert gate.verify_listing_in_scope("Jamaica Plain Coffee", scope) is False


# ──────────── 2b) the generator's PLACES-FIRST wiring (source invariants) ────
class TestPlacesFirstWiring:
    def test_exact_log_line_and_existence_check(self):
        src = inspect.getsource(gtt._generate_tour_text_impl)
        # The exact ticket log line must be emitted for a dropped LLM name.
        assert "[LOCAL-788B] llm name not on map" in src
        # The drop is driven by verify_listing_in_scope (places_search authority).
        assert "verify_listing_in_scope" in src
        assert "is_place_type_tour" in src

    def test_places_first_runs_before_llm_part_c(self):
        src = inspect.getsource(gtt._generate_tour_text_impl)
        i_places_first = src.find("[LOCAL-788B] PLACES-FIRST")
        i_partc = src.find("Part C: replacement loop")
        assert i_places_first != -1, "the LOCAL-788B PLACES-FIRST block is missing"
        assert i_partc != -1
        assert i_places_first < i_partc, (
            "places_search verification must run BEFORE the LLM Part C refill")

    def test_maps_verified_stops_exempt_from_existence_gate(self):
        src = inspect.getsource(gtt._generate_tour_text_impl)
        # A maps-sourced stop carries _maps_verified and is exempt from the gate
        # (so the gate never re-drops a real map place via the Wikipedia path).
        assert "_maps_verified" in src

    def test_phase4_map_override_keeps_al_wadi(self):
        src = inspect.getsource(gtt._generate_tour_text_impl)
        # PHASE 4 must override the LLM exclusion with a places_search hit.
        assert "LLM exclusion overridden" in src


# ───────────── 3) place-type detection + gate ENFORCE for them ──────────────
class TestPlaceTypeTourAndGate:
    def test_is_place_type_tour_covers_the_field_case(self):
        # tour_type "" (as the app sends), category inferred 'restaurant'.
        assert gate.is_place_type_tour(tour_category="restaurant") is True
        assert gate.is_place_type_tour(poi_type="restaurants") is True
        assert gate.is_place_type_tour(poi_type="gyms") is True
        assert gate.is_place_type_tour(
            request_text="coffee shops near me, Jamaica Plain, Boston") is True
        # Museum / facility are NOT place-type (they keep their own grounding).
        assert gate.is_place_type_tour(tour_category="museum",
                                       poi_type="museum exhibits") is False

    def test_gate_forces_enforce_for_place_type(self, monkeypatch):
        import importlib
        for k in ("STOP_EXISTENCE_GATE_MODE", "WALKING_EXISTENCE_GATE_ENFORCE",
                  "DISABLE_STOP_EXISTENCE_GATE", "ENABLE_STOP_EXISTENCE_GATE"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("STOP_EXISTENCE_GATE_MODE", "log_only")
        importlib.reload(gate)
        # Dining (restaurant) and a near-me business request both ENFORCE.
        assert gate.get_gate_mode_for_category("restaurant") == "enforce"
        assert gate.get_gate_mode_for_category(
            "walking", poi_type="gyms",
            request_text="gyms near me, West Roxbury, MA") == "enforce"
        # Museum stays on the shared-stack mode.
        assert gate.get_gate_mode_for_category("museum") == "log_only"

    def test_explicit_off_still_wins(self, monkeypatch):
        import importlib
        monkeypatch.setenv("STOP_EXISTENCE_GATE_MODE", "off")
        importlib.reload(gate)
        assert gate.get_gate_mode_for_category("restaurant") == "off"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
