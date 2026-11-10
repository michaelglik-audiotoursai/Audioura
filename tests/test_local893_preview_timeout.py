"""LOCAL-893 — the orchestrator's D762 /preview-stops call timed out (20 s) on the
cloud because LOCAL-882's canonical lookups made the preview ~18 s, so the
generator silently got RAW strings. Offline: no network, no DB, no paid calls.

Covers: (1) preview speed (concurrent canonical lookups, timing log),
(2) timeout 60 s + one retry + ERROR log, never silent, (3) a SLOW preview
(longer than the old 20 s timeout) still yields pins and clean titles, and a
FAILED preview still yields clean titles, (4) the generator-side title cleaning.
"""
import importlib
import json
import os
import sys
import time

import pytest
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import itinerary_import as ii  # noqa: E402

CITY = "Ho Chi Minh City"
RAW = [
    "Cathedral", "Post Office", "Book Street", "Independence Palace",
    "War Remnants Museum", "Opera House_Đồng Khởi", "City Hall & Nguyễn Huệ",
    "Café Apartments 42", "Bạch Đằng Pier (tour-bus + waterbus)", "Thi Bar",
]
CLEAN = [
    "Cathedral", "Post Office", "Book Street", "Independence Palace",
    "War Remnants Museum", "Opera House", "City Hall", "Café Apartments 42",
    "Bạch Đằng Pier", "Thi Bar",
]


# ── helpers ──────────────────────────────────────────────────────────────────
def _stub_resolvers(canon_delay=0.0):
    pts = {n: (10.77 + i * 0.001, 106.69 + i * 0.001) for i, n in enumerate(CLEAN)}

    def link(raw):
        return {"lat": None, "lng": None}

    def wikidata(name, scope, center, bbox):
        p = pts.get(name)
        return (p[0], p[1], "Q1") if p else None

    def canonical(user_name, pin, city="", local_lang="", user_link=""):
        time.sleep(canon_delay)
        return {"canonical_en": user_name + " (canonical)", "aliases": [],
                "source": "stub", "distance_m": 1, "match_tier": 1}

    return ii.Resolvers(wikidata=wikidata, nominatim=lambda p: [], serper=lambda *a: [],
                        link=link, city_fetch=lambda p: [], canonical=canonical)


def _fake_preview_payload():
    """What /preview-stops returns for RAW: clean `name`, a pin per stop."""
    stops = []
    for i, (raw, clean) in enumerate(zip(RAW, CLEAN)):
        stops.append({"index": i, "name": clean, "stop_name": clean, "alt_names": [],
                      "note": "", "url": None, "lat": 10.77 + i * 0.001,
                      "lng": 106.69 + i * 0.001, "source": "stub",
                      "confidence": "high", "unresolved": False})
    return {"ok": True, "city": {"name": CITY}, "count": len(stops), "stops": stops}


class _Resp:
    status_code = 200

    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


def _load_orch(monkeypatch):
    monkeypatch.setenv("USER_STOPS_ENABLED", "true")
    import tour_orchestrator_service as orch
    importlib.reload(orch)
    return orch


# ── 1. preview speed ─────────────────────────────────────────────────────────
def test_canonical_lookups_run_concurrently_and_keep_order(monkeypatch):
    monkeypatch.setenv("PREVIEW_CANON_WORKERS", "5")
    lines = []
    t0 = time.time()
    out = ii.preview_stops("\n".join(CLEAN), CITY, resolvers=_stub_resolvers(0.4),
                           log=lines.append)
    dt = time.time() - t0
    assert out["ok"] and out["count"] == 10
    n_res = out["count"] - out["unresolved_count"]
    assert n_res >= 5
    # n_res x 0.4 s sequentially (>= 2 s); on 5 workers ~0.4-0.8 s
    assert dt < 0.4 * n_res * 0.7, f"canonical lookups were not concurrent ({dt:.2f}s)"
    assert [s["name"] for s in out["stops"]] == CLEAN        # order preserved
    assert all(s["matched_name"].endswith("(canonical)")
               for s in out["stops"] if not s["unresolved"])
    assert any("[LOCAL-893] preview timing: 10 stops" in x for x in lines)
    assert sum("pin " in x and "canonical " in x and "[LOCAL-867] preview" in x
               for x in lines) == 10                          # per-stop timing


def test_one_failing_canonical_does_not_sink_the_preview():
    res = _stub_resolvers()

    def boom(*a, **k):
        raise RuntimeError("x")
    res.canonical = boom
    out = ii.preview_stops("\n".join(CLEAN), CITY, resolvers=res, log=lambda *_: None)
    assert out["ok"] and out["count"] == 10   # still resolved, canonical just absent


# ── 2. timeout / retry / ERROR ───────────────────────────────────────────────
def test_timeout_is_60s_and_one_retry_on_timeout(monkeypatch, capsys):
    orch = _load_orch(monkeypatch)
    calls = []

    def fake(method, url, **kw):
        calls.append(kw["timeout"])
        if len(calls) == 1:
            raise requests.exceptions.ReadTimeout("Read timed out. (read timeout=60)")
        return _Resp(_fake_preview_payload())
    monkeypatch.setattr(orch, "_authenticated_request", fake)
    r = orch._d762_gen_preview("\n".join(RAW), CITY)
    assert r["ok"] and calls == [60.0, 60.0]
    assert "retrying once" in capsys.readouterr().out


def test_failure_logs_error_never_silent(monkeypatch, capsys, caplog):
    orch = _load_orch(monkeypatch)
    n = []

    def fake(method, url, **kw):
        n.append(1)
        raise requests.exceptions.ReadTimeout("Read timed out.")
    monkeypatch.setattr(orch, "_authenticated_request", fake)
    with caplog.at_level("ERROR"):
        r = orch._d762_gen_preview("x", CITY)
    assert r["ok"] is False and len(n) == 2            # exactly one retry
    assert "[D762] PREVIEW FAILED — generating from raw strings" in capsys.readouterr().out
    assert any("PREVIEW FAILED" in rec.message and rec.levelname == "ERROR"
               for rec in caplog.records)


def test_http_500_is_not_retried_but_is_reported(monkeypatch, capsys):
    orch = _load_orch(monkeypatch)
    n = []

    class R500(_Resp):
        status_code = 500
    monkeypatch.setattr(orch, "_authenticated_request",
                        lambda *a, **k: (n.append(1), R500({}))[1])
    r = orch._d762_gen_preview("x", CITY)
    assert r["ok"] is False and len(n) == 1
    assert "PREVIEW FAILED" in capsys.readouterr().out


# ── 3. slow preview: clean titles + pins survive (through the real intake) ───
def _post_raw(orch, monkeypatch):
    got = {}

    def thread(job_id, location, tour_type, total_stops, user_id=None,
               request_string=None, language='en', persona=None, is_test=None,
               stops=None, mode=None):
        got["stops"] = stops
    monkeypatch.setattr(orch, "orchestrate_tour_async", thread)
    import entitlements
    allow = lambda *a, **k: {"allowed": True, "error_code": None, "level": "L1",  # noqa
                             "clamped_stops": 10, "mode": None}
    monkeypatch.setattr(entitlements, "check_operation", allow, raising=False)
    monkeypatch.setattr(orch, "check_operation", allow, raising=False)
    monkeypatch.setattr(orch, "check_tour_quota",
                        lambda uid, stops=10: {"allowed": True, "clamped_stops": stops,
                                               "used": 0, "remaining": 100}, raising=False)
    monkeypatch.setattr(orch, "track_user_tour", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(orch, "log_job_update", lambda *a, **k: None, raising=False)
    import psycopg2
    monkeypatch.setattr(psycopg2, "connect",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no DB")))
    orch.app.testing = True
    r = orch.app.test_client().post(
        "/generate-complete-tour", content_type="application/json",
        data=json.dumps({"location": CITY, "tour_type": "walking", "total_stops": 10,
                         "user_id": "tester", "stops": RAW, "is_test": True}))
    assert r.status_code in (200, 202), r.get_data(as_text=True)
    return got["stops"]


def test_slow_preview_longer_than_old_timeout_keeps_clean_titles_and_pins(
        monkeypatch, capsys):
    """Preview answers after a (virtual) 22 s — 2 s past the OLD 20 s timeout."""
    orch = _load_orch(monkeypatch)
    seen = []

    def slow(method, url, **kw):
        seen.append(kw["timeout"])
        if 22.0 > kw["timeout"]:          # would have timed out at the old 20 s
            raise requests.exceptions.ReadTimeout("Read timed out.")
        return _Resp(_fake_preview_payload())
    monkeypatch.setattr(orch, "_authenticated_request", slow)
    stops = _post_raw(orch, monkeypatch)
    out = capsys.readouterr().out
    assert seen[0] >= 60
    assert "user-stop pins resolved 10/10" in out
    assert "PREVIEW FAILED" not in out
    assert len(stops) == 10 and all("_@10." in s for s in stops)       # pins carried
    assert [s.split(" https")[0] for s in stops] == CLEAN           # clean titles
    assert not any(("_" in s.split(" https")[0]) or "(" in s.split(" https")[0]
                   or "&" in s.split(" https")[0] for s in stops)


def test_failed_preview_still_hands_the_generator_clean_titles(monkeypatch, capsys):
    orch = _load_orch(monkeypatch)

    def dead(method, url, **kw):
        raise requests.exceptions.ReadTimeout("Read timed out.")
    monkeypatch.setattr(orch, "_authenticated_request", dead)
    stops = _post_raw(orch, monkeypatch)
    out = capsys.readouterr().out
    assert "[D762] PREVIEW FAILED — generating from raw strings" in out
    assert stops == CLEAN                      # degraded, but never raw titles
    for raw_marker in ("_Đồng", "& Nguyễn", "(tour-bus"):
        assert not any(raw_marker in s for s in stops)


# ── 4. the cleaner itself ────────────────────────────────────────────────────
def test_clean_raw_stop_titles_cases():
    assert ii.clean_raw_stop_titles(RAW, CITY) == CLEAN


def test_clean_leaves_links_pins_objects_and_odd_items_alone():
    items = ["Opera House https://www.google.com/maps/place/x/@10.77,106.70,17z",
             {"name": "A"}, "", "   ", None, "A → B", "Thi Bar"]
    out = ii.clean_raw_stop_titles(items, CITY)
    assert out[:6] == items[:6] and out[6] == "Thi Bar"


def test_generator_cleaning_hook_is_wired():
    src = open(os.path.join(ROOT, "generate_tour_text.py"), encoding="utf-8").read()
    assert "clean_raw_stop_titles as _crst893" in src


# ── 5. the real-path harness's own assertions ────────────────────────────────
def test_harness_log_assertions():
    import run_local893_real_path as h
    ok = h.assess_orch_log("[D762] /preview-stops OK in 5.2s (try 1)\n"
                           "[D762] user-stop pins resolved 10/10 (city X)\n")
    assert all(p for _, p, _ in ok)
    wave43 = h.assess_orch_log("[D762] user-stop pin resolve error: Read timed out "
                               "(read timeout=20)\n")
    assert not any(p for _, p, _ in wave43)
    g = h.assess_gen_log("[LOCAL-852] user stop resolved 'Opera House_Đồng Khởi' "
                         "(no coord — geocode by name) via name_only\n")
    assert not g[0][1] and not g[1][1]


# ── 6. underscore qualifier + preview deadline ───────────────────────────────
def test_parser_treats_underscore_street_qualifier_like_slash():
    got = ii.parse_itinerary("Opera House_Đồng Khởi", CITY)
    assert got[0]["name"] == "Opera House" and got[0]["alt_names"] == ["Đồng Khởi"]


def test_underscore_inside_a_protected_url_is_untouched():
    got = ii.parse_itinerary(
        "Thi Bar https://www.google.com/maps/place/Thi_Bar/@10.7,106.6,17z", CITY)
    assert got[0]["name"] == "Thi Bar" and "Thi_Bar" in got[0]["url"]


def test_slow_canonical_is_abandoned_at_the_deadline_loudly(monkeypatch):
    monkeypatch.setenv("PREVIEW_CANON_DEADLINE_S", "0.6")
    monkeypatch.setenv("PREVIEW_CANON_MIN_GRACE_S", "0.5")
    lines = []
    t0 = time.time()
    out = ii.preview_stops("\n".join(CLEAN), CITY, resolvers=_stub_resolvers(5.0),
                           log=lines.append)
    dt = time.time() - t0
    assert dt < 3.0, f"preview waited for the slow canonical lookups ({dt:.1f}s)"
    assert out["ok"] and out["count"] == 10
    resolved = [s for s in out["stops"] if not s["unresolved"]]
    assert resolved and all(s["canonical_aliases"] == [] for s in resolved)
    assert any("abandoned at the 0.6s preview deadline" in x for x in lines)
    assert any("[LOCAL-893] preview timing" in x and "abandoned" in x for x in lines)


def test_last_stop_after_a_slow_pin_phase_still_gets_its_grace(monkeypatch):
    """Live finding: pins took > the deadline, so the LAST stop's canonical lookup
    got ~0.05 s and was always abandoned. It now gets a minimum grace."""
    monkeypatch.setenv("PREVIEW_CANON_DEADLINE_S", "0.3")
    monkeypatch.setenv("PREVIEW_CANON_MIN_GRACE_S", "1.6")
    monkeypatch.setenv("PREVIEW_CANON_WORKERS", "10")   # isolate grace from pool queueing
    res = _stub_resolvers(1.0)               # each canonical lookup takes 1.0 s
    _wd = res.wikidata

    def slow_pin(name, scope, center, bbox):
        time.sleep(0.15)                     # pins alone exceed the 0.3 s deadline
        return _wd(name, scope, center, bbox)
    res.wikidata = slow_pin
    lines = []
    out = ii.preview_stops("\n".join(CLEAN), CITY, resolvers=res, log=lines.append)
    last = [s for s in out["stops"] if not s["unresolved"]][-1]
    assert last["matched_name"].endswith("(canonical)"), lines
    # and without the grace the same stop IS abandoned (the bug this pins down)
    monkeypatch.setenv("PREVIEW_CANON_MIN_GRACE_S", "0")
    out0 = ii.preview_stops("\n".join(CLEAN), CITY, resolvers=res, log=lambda *_: None)
    last0 = [s for s in out0["stops"] if not s["unresolved"]][-1]
    assert not (last0["matched_name"] or "").endswith("(canonical)")
