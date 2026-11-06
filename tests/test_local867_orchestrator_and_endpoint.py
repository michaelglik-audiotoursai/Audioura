"""LOCAL-867 — /preview-stops endpoint (generator) and user_stops intake (orchestrator).
Offline: no network, no DB, no paid calls."""
import json
import os
import re
import sys
import importlib

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import itinerary_import as ii  # noqa: E402

MICHAEL = ("Cathedral → Post Office → Book Street → Independence Palace → "
           "War Remnants Museum → Opera House/Đồng Khởi → City Hall & Nguyễn Huệ → "
           "Café Apartments 42 → Bạch Đằng Pier (tour-bus + waterbus) → Thi Bar")


@pytest.fixture
def gen_client(monkeypatch):
    import generate_tour_text_service as svc
    svc.app.testing = True
    return svc, svc.app.test_client()


def _stub_preview(monkeypatch, captured):
    def fake(text, city, **kw):
        captured.update(text=text, city=city, kw=kw)
        return {"ok": True, "city": {"name": "Ho Chi Minh City", "lat": 1, "lng": 2},
                "count": 1, "unresolved_count": 0, "stops": [{"name": "A"}],
                "cost": {"usd": 0.0}}
    monkeypatch.setattr(ii, "preview_stops", fake)


def test_endpoint_off_by_default_is_404(gen_client, monkeypatch):
    _, c = gen_client
    monkeypatch.delenv("USER_STOPS_ENABLED", raising=False)
    r = c.post("/preview-stops", json={"text": "A → B", "city": "Ho Chi Minh City"})
    assert r.status_code == 404


def test_endpoint_validation(gen_client, monkeypatch):
    _, c = gen_client
    monkeypatch.setenv("USER_STOPS_ENABLED", "true")
    assert c.post("/preview-stops", json={}).status_code == 400
    assert c.post("/preview-stops", json={"text": "   "}).status_code == 400
    assert c.post("/preview-stops", json={"text": "x" * 9000}).status_code == 400
    assert c.post("/preview-stops", json={"text": "A", "city": 5}).status_code == 400


def test_endpoint_passes_text_and_city_and_returns_json(gen_client, monkeypatch):
    _, c = gen_client
    monkeypatch.setenv("USER_STOPS_ENABLED", "true")
    cap = {}
    _stub_preview(monkeypatch, cap)
    r = c.post("/preview-stops", json={"text": MICHAEL, "city": " Ho Chi Minh City "})
    assert r.status_code == 200
    assert cap["text"] == MICHAEL and cap["city"] == "Ho Chi Minh City"
    assert r.get_json()["count"] == 1


def test_endpoint_no_city_is_400(gen_client, monkeypatch):
    _, c = gen_client
    monkeypatch.setenv("USER_STOPS_ENABLED", "true")
    r = c.post("/preview-stops", json={"text": "Cathedral → Post Office"})
    assert r.status_code == 400 and "city" in r.get_json()["error"]


def test_endpoint_makes_no_llm_import_path():
    """The module must not reach an LLM client."""
    src = open(os.path.join(ROOT, "itinerary_import.py"), encoding="utf-8").read()
    for bad in ("gemini", "openai", "anthropic", "genai", "grounded"):
        assert bad not in src.lower().replace("llm_calls", "")


# ── orchestrator ────────────────────────────────────────────────────────────

def _load_orch(monkeypatch):
    monkeypatch.setenv("USER_STOPS_ENABLED", "true")
    import tour_orchestrator_service as orch
    importlib.reload(orch)
    import entitlements
    allow = lambda *a, **k: {"allowed": True, "error_code": None, "level": "L1",  # noqa
                             "clamped_stops": k.get("requested_stops") or 10,
                             "mode": None}
    monkeypatch.setattr(entitlements, "check_operation", allow, raising=False)
    monkeypatch.setattr(orch, "check_operation", allow, raising=False)
    monkeypatch.setattr(orch, "check_tour_quota",
                        lambda uid, stops=10: {"allowed": True, "clamped_stops": stops,
                                               "used": 0, "remaining": 100},
                        raising=False)
    monkeypatch.setattr(orch, "track_user_tour", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(orch, "log_job_update", lambda *a, **k: None, raising=False)
    import psycopg2
    monkeypatch.setattr(psycopg2, "connect",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no DB")))
    return orch


def _post(orch, monkeypatch, user_stops):
    got = {"stops": "<<uncalled>>"}

    def thread(job_id, location, tour_type, total_stops, user_id=None,
               request_string=None, language='en', persona=None, is_test=None,
               stops=None, mode=None):
        got["stops"], got["total"] = stops, total_stops
    monkeypatch.setattr(orch, "orchestrate_tour_async", thread)
    orch.app.testing = True
    r = orch.app.test_client().post(
        "/generate-complete-tour", content_type="application/json",
        data=json.dumps({"location": "Ho Chi Minh City, Vietnam",
                         "tour_type": "walking", "user_id": "tester",
                         "request_string": "a walking tour of my itinerary",
                         "user_stops": user_stops}))
    return r, got


def test_orchestrator_accepts_reviewed_preview_objects_in_order(monkeypatch, capsys):
    orch = _load_orch(monkeypatch)
    items = [{"name": "Cathedral", "stop_name": "Notre-Dame Cathedral Basilica of Saigon",
              "lat": 10.779798, "lng": 106.699018},
             {"name": "Zzyzx", "lat": None, "lng": None, "unresolved": True},
             "Opera House"]
    r, got = _post(orch, monkeypatch, items)
    assert r.status_code in (200, 202), r.get_data(as_text=True)
    st = got["stops"]
    assert len(st) == 3 and got["total"] == 3
    assert st[0].startswith("Notre-Dame Cathedral Basilica of Saigon https___www.google.com_maps_@10.779798,106.699018")
    assert st[1] == "Zzyzx" and st[2] == "Opera House"
    assert "[LOCAL-867] imported 3 stops" in capsys.readouterr().out


def test_orchestrator_strings_only_unchanged_and_no_import_log(monkeypatch, capsys):
    orch = _load_orch(monkeypatch)
    r, got = _post(orch, monkeypatch, ["Bell Tower", "Crypt"])
    assert r.status_code in (200, 202)
    assert got["stops"] == ["Bell Tower", "Crypt"]
    assert "[LOCAL-867]" not in capsys.readouterr().out


def test_orchestrator_bad_object_is_400_not_dropped(monkeypatch):
    orch = _load_orch(monkeypatch)
    r, got = _post(orch, monkeypatch, [{"lat": 1, "lng": 2}, "B"])
    assert r.status_code == 400
    assert got["stops"] == "<<uncalled>>"


def test_orchestrator_pin_round_trips_through_the_852_parser(monkeypatch):
    import user_stop_input as usi
    orch = _load_orch(monkeypatch)
    r, got = _post(orch, monkeypatch,
                   [{"name": "Thi Bar", "stop_name": "Thi Bar Saigon",
                     "lat": 10.76766, "lng": 106.69396}])
    assert r.status_code in (200, 202)
    p = usi.parse_user_stop(got["stops"][0])
    assert p["name"] == "Thi Bar Saigon"
    assert (p["lat"], p["lng"]) == (10.76766, 106.69396)
    assert p["needs_geocode"] is False


def test_forced_stops_keep_the_given_order_in_route_ordering():
    """[LOCAL-867] A user-chosen stop list is never re-sequenced by LOCAL-7."""
    import generate_tour_text as g
    pois = [{"name": n, "coordinates": c} for n, c in [
        ("Far West", "10.7700, 106.6800"), ("Far East", "10.7700, 106.7200"),
        ("Middle", "10.7700, 106.7000"), ("Near West", "10.7700, 106.6900")]]
    g._J._KEEP_GIVEN_ORDER = False
    try:
        assert [p["name"] for p in g._compute_route_order(pois)] != \
            [p["name"] for p in pois]                    # normally re-sequenced
        g._J._KEEP_GIVEN_ORDER = True
        assert [p["name"] for p in g._compute_route_order(pois)] == \
            [p["name"] for p in pois]                    # forced: kept
    finally:
        g._J._KEEP_GIVEN_ORDER = False


def test_forced_stops_block_sets_and_resets_keep_order_flag():
    src = open(os.path.join(ROOT, "generate_tour_text.py"), encoding="utf-8").read()
    i = src.index("    _forced_stops_active = False\n    try:\n        _J._KEEP_GIVEN_ORDER = False")
    j = src.index("_J._KEEP_GIVEN_ORDER = True", i)
    assert j - i < 1200


def test_long_title_and_alias_never_lose_the_coordinate_to_the_200_char_cut(monkeypatch):
    """[LOCAL-867, live run 2] City Hall's title + Vietnamese alias exceeded the
    orchestrator's 200-char sanitize cut; the cut landed inside @lat,lng."""
    import user_stop_input as usi
    orch = _load_orch(monkeypatch)
    items = [{"stop_name": "Ho Chi Minh City Hall (People's Committee Building)",
              "matched_name": "Trụ sở Ủy ban Nhân dân Thành phố Hồ Chí Minh",
              "lat": 10.77647, "lng": 106.70097},
             {"stop_name": "A" * 260, "lat": 10.7, "lng": 106.6}]
    r, got = _post(orch, monkeypatch, items)
    assert r.status_code in (200, 202)
    for raw, it in zip(got["stops"], items):
        assert len(raw) <= 200
        p = usi.parse_user_stop(raw)
        assert (p["lat"], p["lng"]) == (it["lat"], it["lng"]), raw
        assert p["needs_geocode"] is False
    assert usi.parse_user_stop(got["stops"][0])["name"] == \
        "Ho Chi Minh City Hall (People's Committee Building)"


def test_saved_live_preview_replays_through_intake_with_every_pin_verbatim(monkeypatch):
    """Offline replay of the REAL live preview (if present): all 10 stops reach
    the generator with their reviewed coordinate, in order."""
    path = os.path.join(ROOT, "submission_artifacts", "local867", "preview_michael_hcmc.json")
    if not os.path.exists(path):
        pytest.skip("live preview artefact not present")
    import user_stop_input as usi
    stops = json.load(open(path, encoding="utf-8"))["stops"]
    orch = _load_orch(monkeypatch)
    r, got = _post(orch, monkeypatch, stops)
    assert r.status_code in (200, 202) and len(got["stops"]) == len(stops)
    for raw, s in zip(got["stops"], stops):
        p = usi.parse_user_stop(raw)
        assert p["name"] == s["stop_name"]
        assert (p["lat"], p["lng"]) == (s["lat"], s["lng"]), raw


def test_kill_switch_off_drops_preview_objects_without_import_log(monkeypatch, capsys):
    orch = _load_orch(monkeypatch)
    monkeypatch.setenv("USER_STOPS_ENABLED", "false")
    r, got = _post(orch, monkeypatch, [{"name": "Cathedral", "lat": 10.78, "lng": 106.7}])
    out = capsys.readouterr().out
    assert "[LOCAL-867] imported" not in out
    assert got["stops"] in (None, "<<uncalled>>") or r.status_code >= 400
