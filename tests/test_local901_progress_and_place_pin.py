"""LOCAL-901 -- wave 48 cloud failures. Generic fixtures, offline, $0, no network (Wikidata/Nominatim mocked).

A0  durable heartbeat: worker on instance A, /status served by instance B -> heartbeat present and fresh;
    the orchestrator watchdog does not fire while the DB heartbeat advances and does when it stops > 5 min.
A1  a heartbeat call at every phase / every stop / each post pass (source-level, plus runtime sink checks).
A2  finalize_898 + apply_single_place_guards + drop_fragments on the 551 fixtures take < 1 s (and no
    catastrophic backtracking on a 5 KB body / a 50-sentence body).
A4  the OSM venue facts NameError (`venue_name`) is gone.   A5  the fetch loop logs its social-host count.
B   single-place request: first named place -> place-level reference, bounded to the province.
C   791E dedupe never merges a distinct structure into the mountain / park that contains it.
D   mood filler (and the closing paragraph) capped on the single-place path.
"""
import io
import contextlib
import os
import sys
import threading
import time
from datetime import datetime, timedelta

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import job_heartbeat as hb  # noqa: E402
import job_store  # noqa: E402
import route_content_896 as rc  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")


def _fx(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def _src(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


# ── A0. two fake instances sharing one fake store ───────────────────────────
class _FakeDB:
    """Stands in for GeneratorJobsStore: one shared 'table', merge semantics of the real upsert."""

    def __init__(self):
        self.rows = {}
        self.lock = threading.Lock()
        self.writes = 0

    def upsert(self, job_id, **fields):
        columns, result_extra, error_extra = job_store._split_fields(fields)
        with self.lock:
            row = self.rows.setdefault(job_id, {"job_id": job_id, "result": {}, "error": {}})
            row.update(columns)
            row["result"].update(result_extra)
            row["error"].update(error_extra)
            row["updated_at"] = datetime.now().isoformat()
            self.writes += 1

    create = upsert
    update = upsert

    def get(self, job_id):
        with self.lock:
            row = self.rows.get(job_id)
            if not row:
                return None
            out = {k: v for k, v in row.items() if k not in ("result", "error")}
            out.update(row["result"])
            out.update(row["error"])
            return out

    def delete(self, job_id):
        return None


def _two_instances():
    db = _FakeDB()
    a = job_store.LayeredJobStore(service_name="t")
    b = job_store.LayeredJobStore(service_name="t")
    a._db = b._db = db
    return a, b, db


def _age(ts):
    return (datetime.now() - datetime.fromisoformat(ts)).total_seconds()


def test_heartbeat_written_by_A_is_served_fresh_by_B():
    import generate_tour_text_service as gen
    a, b, db = _two_instances()
    jid = "job-901-a"
    a.update(jid, status="processing", progress="Starting tour text generation...",
             location="Gamma Mountain", tour_type="", total_stops=2)
    ticker = hb.HeartbeatTicker(a, jid, interval=0.05, min_gap=0.0).start()
    try:
        gen.app.config["TESTING"] = True
        client = gen.app.test_client()
        orig, orig_threads = gen.ACTIVE_JOBS, dict(gen.JOB_THREADS)
        gen.ACTIVE_JOBS = b                       # B serves /status
        gen.JOB_THREADS.pop(jid, None)            # the worker thread lives only on A
        try:
            r1 = client.get(f"/status/{jid}").get_json()
            assert r1["status"] == "processing"
            assert r1.get("heartbeat_at"), "the DB fallback must carry the durable heartbeat"
            assert _age(r1["heartbeat_at"]) < 5
            assert r1.get("updated_at") and _age(r1["updated_at"]) < 5
            time.sleep(0.3)
            r2 = client.get(f"/status/{jid}").get_json()
            assert r2["heartbeat_at"] > r1["heartbeat_at"], "the ticker keeps advancing it"
            assert r2["updated_at"] >= r1["updated_at"]
        finally:
            gen.ACTIVE_JOBS = orig
            gen.JOB_THREADS.clear()
            gen.JOB_THREADS.update(orig_threads)
    finally:
        ticker.stop()


def test_ticker_stops_with_the_job_and_does_not_touch_status():
    a, b, db = _two_instances()
    jid = "job-901-stop"
    a.update(jid, status="processing", progress="p")
    t = hb.HeartbeatTicker(a, jid, interval=0.02, min_gap=0.0).start()
    time.sleep(0.1)
    t.stop()
    n = db.writes
    time.sleep(0.15)
    assert db.writes == n, "no write after stop()"
    row = db.get(jid)
    assert row["status"] == "processing" and row["progress"] == "p", "ticker never rewrites status/progress"
    hb.beat(jid, "late")                                     # sink unregistered: no-op
    assert db.writes == n


def test_terminal_job_does_not_advertise_a_heartbeat():
    import generate_tour_text_service as gen
    a, b, db = _two_instances()
    a.update("j-done", status="processing", progress="p", location="x", tour_type="", total_stops=1)
    a.update("j-done", heartbeat_at=datetime.now().isoformat())
    a.update("j-done", status="completed", progress="done", output_file="f.txt", tour_content="t")
    gen.app.config["TESTING"] = True
    orig = gen.ACTIVE_JOBS
    gen.ACTIVE_JOBS = b
    try:
        body = gen.app.test_client().get("/status/j-done").get_json()
    finally:
        gen.ACTIVE_JOBS = orig
    assert body["status"] == "completed" and "heartbeat_at" not in body


def test_beat_is_routed_throttled_and_thread_safe():
    calls = []
    hb.register_sink("j", calls.append)
    try:
        threads = [threading.Thread(target=hb.beat, args=("j", f"stop {i}")) for i in range(8)]
        [t.start() for t in threads]
        [t.join() for t in threads]
    finally:
        hb.unregister_sink("j")
    assert sorted(calls) == sorted(f"stop {i}" for i in range(8))
    hb.beat("unknown-job", "x")                              # no sink -> no-op, never raises
    hb.beat(None, "x")

    class _Boom:
        def update(self, *a, **k):
            raise RuntimeError("db down")
    t = hb.HeartbeatTicker(_Boom(), "jj", interval=60, min_gap=0.0)
    assert t.write("x", force=True) is False                 # swallowed

    a, _, db = _two_instances()
    tt = hb.HeartbeatTicker(a, "jt", interval=60, min_gap=60.0, clock=lambda: 1000.0)
    assert tt.write("a") is True and tt.write("b") is False and tt.write("c", force=True) is True


# ── A0. the orchestrator watchdog ────────────────────────────────────────────
def _wd():
    import tour_orchestrator_service as orch
    t0 = datetime(2026, 11, 12, 16, 21, 0)
    return orch, orch.StallWatchdog(t0), t0


def _drive(wd, t0, until_s, reply_at, step=10, limit_s=300):
    """Poll every `step` s; reply_at(now) -> status dict. Return the second the watchdog would fire, or None."""
    for s in range(0, until_s, step):
        now = t0 + timedelta(seconds=s)
        wd.observe(reply_at(now), now)
        if wd.stalled_for(now) > timedelta(seconds=limit_s):
            return s
    return None


def test_watchdog_does_not_fire_while_the_db_heartbeat_advances():
    orch, wd, t0 = _wd()

    def reply(now):
        beat = t0 + timedelta(seconds=int((now - t0).total_seconds()) // 30 * 30)
        return {"status": "processing", "progress": "Starting tour text generation...",
                "updated_at": beat.isoformat(), "heartbeat_at": beat.isoformat()}
    # progress text frozen for 12 minutes (wave 48); heartbeat from the DB advancing every 30 s
    assert _drive(wd, t0, 720, reply) is None


def test_watchdog_fires_when_the_heartbeat_stops_for_over_five_minutes():
    orch, wd, t0 = _wd()
    last = t0 + timedelta(seconds=120)

    def reply(now):
        beat = min(now, last)                                  # the worker dies at +120 s
        return {"status": "processing", "progress": "Starting tour text generation...",
                "updated_at": beat.isoformat(), "heartbeat_at": beat.isoformat()}
    fired = _drive(wd, t0, 900, reply)
    assert fired is not None
    # last heartbeat +120 s; the 90 s freshness window can extend the last credit to +210 s; then 5 min
    assert 120 + 300 <= fired <= 120 + 90 + 300 + 20, f"fired at +{fired}s, expected ~5 min after the last heartbeat"


def test_watchdog_belt_and_braces_fresh_timestamp_counts_as_alive():
    orch, wd, t0 = _wd()
    ts = t0.isoformat()       # identical marker every poll (a frozen reply)
    reply = {"status": "processing", "progress": "p", "updated_at": ts, "heartbeat_at": ts}
    wd.observe(reply, t0)
    wd.observe(reply, t0 + timedelta(seconds=60))
    assert wd.last_progress_at == t0 + timedelta(seconds=60), "age 60 s < 90 s: still alive"
    wd.observe(reply, t0 + timedelta(seconds=200))
    assert wd.last_progress_at == t0 + timedelta(seconds=60), "age 200 s: no credit"
    assert wd.stalled_for(t0 + timedelta(seconds=200)) == timedelta(seconds=140)


def test_watchdog_freshness_only_counts_for_processing_and_ignores_future_or_bad_timestamps():
    orch, wd, t0 = _wd()
    fresh = t0.isoformat()
    base = {"progress": "p", "updated_at": fresh, "heartbeat_at": fresh}
    wd.observe({**base, "status": "processing"}, t0)
    now = t0 + timedelta(seconds=30)
    wd.observe({**base, "status": "queued"}, now)
    assert wd.last_progress_at == t0, "queued is not alive on freshness alone"
    wd.observe({**base, "status": "processing", "updated_at": "garbage", "heartbeat_at": None}, now)
    assert wd.last_progress_at == now                          # marker changed -> alive (old rule intact)
    wd2 = orch.StallWatchdog(t0)
    future = (t0 + timedelta(hours=5)).isoformat()             # a tz-skewed DB clock must not pin 'alive' forever
    r = {"status": "processing", "progress": "p", "updated_at": future, "heartbeat_at": None}
    wd2.observe(r, t0)
    wd2.observe(r, t0 + timedelta(seconds=200))
    assert wd2.last_progress_at == t0


def test_watchdog_old_marker_rule_still_resets():
    orch, wd, t0 = _wd()
    wd.observe({"status": "processing", "progress": "a"}, t0)
    wd.observe({"status": "processing", "progress": "b"}, t0 + timedelta(seconds=250))
    assert wd.last_progress_at == t0 + timedelta(seconds=250)


# ── A1. a heartbeat at every phase / stop / post pass ────────────────────────
_PHASE_PRINTS = ["PHASE 1:", "PHASE 3A: Fetching", "PHASE 4: Verifying POIs", "OK PHASE 3B:", "PHASE 5: Generating",
                 "PHASE 6: Assembling", "STORY GATE: checking", "STORY VERIFICATION: checking"]


def test_every_phase_print_is_followed_by_a_heartbeat():
    lines = _src("generate_tour_text.py").split("\n")
    for marker in _PHASE_PRINTS:
        idx = [i for i, ln in enumerate(lines) if marker in ln and "print(" in ln
               and "SKIPPED" not in ln and "skipped" not in ln]
        assert idx, marker
        for i in idx:
            window = "\n".join(lines[i:i + 4])
            assert "_hb_beat(job_id" in window, f"no heartbeat right after: {lines[i].strip()}"


def test_heartbeat_at_stop_level_d556_and_post_passes():
    s = _src("generate_tour_text.py")
    for needle in ('"phase 5 stop {idx + 1} start"', '"phase 5 stop {idx + 1} done"',   # parallel worker + as_completed
                   '"D556 replenish+lore"', 'D556 lore {_gn[:40]}', 'story units {_sg_name[:40]}',
                   'story verification {_sv_name[:40]}', '"finalize_898 (delivery)"',
                   '"single-place guards (delivery)"', '"key fact coverage / finalize_tour"',
                   '"route content (897/898) post pass"', '"route content pass start"'):
        assert needle in s, needle
    assert "_apply_delivery_hours_guard(result, job_id=job_id)" in s


def test_no_gap_covers_more_than_one_phase_in_a_simulated_run():
    """The heartbeat labels the source emits, in phase order, through a recording sink: every phase
    contributes a beat, so consecutive beats are never separated by a whole phase."""
    s = _src("generate_tour_text.py")
    order = ["phase 1", "phase 3A", "phase 4", "phase 3B done", "D556 replenish+lore", "phase 5 start",
             "phase 5 stop", "story gate start", "story verification start", "phase 6",
             "key fact coverage", "finalize_898", "single-place guards"]
    pos = []
    for lbl in order:
        i = s.find('f"phase 5 stop') if lbl == "phase 5 stop" else s.find(f'_hb_beat(job_id, "{lbl}')
        assert i > 0, lbl
        pos.append(i)
    assert pos[:6] == sorted(pos[:6])
    sink = []
    hb.register_sink("sim", sink.append)
    try:
        for lbl in order:
            hb.beat("sim", lbl)
    finally:
        hb.unregister_sink("sim")
    assert sink == order


# ── A2. timing of 900/900B on the 551 fixtures; no catastrophic backtracking ─
INFO = {"is_description": True, "origin": "Alpha Lodge", "destination": "Gamma Mountain",
        "through": ["Sigma Town"], "region": "Kappa province", "origin_locality": "Alpha Bay"}


@pytest.fixture
def route():
    rc.set_route(INFO)
    rc._POINTS.clear()
    rc._HONEST_DONE.clear()
    yield
    rc.clear_route()
    rc._POINTS.clear()


@pytest.mark.parametrize("name", ["local900b_tour551.txt", "local900b_tour551_input.txt"])
def test_900_900b_passes_take_under_a_second_on_551(route, name):
    t = _fx(name)
    t0 = time.perf_counter()
    rc.finalize_898(t, None)
    rc.drop_fragments(t, force=True)
    rc.apply_single_place_guards(t)
    assert time.perf_counter() - t0 < 1.0


def test_no_catastrophic_backtracking_on_long_bodies(route):
    sent = ("The old pagoda, which stands on the mountain, was built by the monk Alpha Beta in 1901 "
            "and is larger than the one at Delta, and ")
    bodies = {
        "5kb": "Ab " * 1700,
        "50sent": " ".join(f"Sentence number {i} about the pagoda and the mountain." for i in range(50)),
        "long_clauses": sent * 45,
        "no_punct": "The pagoda " * 600,
        "commas": ", ".join(["alpha"] * 1500) + ".",
    }
    for nm, body in bodies.items():
        text = f"Stop 1: Alpha Pagoda\nCoordinates: 10.0, 100.0\n{body}\n\nStop 2: Beta\n{body}\n"
        t0 = time.perf_counter()
        rc.finalize_898(text, {"Alpha Pagoda": "x", "Beta": "y"})
        rc.apply_single_place_guards(text)
        rc.cap_single_place_filler(text)
        assert time.perf_counter() - t0 < 1.0, nm


# ── A4. NameError / A5. fetch log ────────────────────────────────────────────
def test_osm_venue_facts_no_longer_references_an_undefined_venue_name():
    s = _src("generate_tour_text.py")
    assert "_museum_venue_name or venue_name\n" not in s
    assert "_venue_query_name = _museum_venue_name or location" in s


def test_fetch_loop_logs_social_host_count_and_skips_them(monkeypatch):
    # [LOCAL-906] 901 only logged the count; social / video hosts are now skipped (see test_local906_*)
    import story_first
    seen = []

    def fake(url, timeout=None):
        seen.append(url)
        return {"url": url, "text": "x" * 50, "success": True, "elapsed_ms": 1.0}
    monkeypatch.setattr(story_first, "_fetch_single_page", fake)
    urls = ["https://www.facebook.com/p/1", "https://youtube.com/watch?v=1", "https://example.org/a"]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out = story_first.fetch_full_pages(urls, budget_seconds=10)
    assert "[LOCAL-901] page fetch: 3 url(s), 2 social/video host(s)" in buf.getvalue()
    assert seen == ["https://example.org/a"] and len(out) == 1


# ── B. single-place tour: place-level pin reference ──────────────────────────
import area_resolver as ar  # noqa: E402
import place_names_900 as pn  # noqa: E402

LOC = "Gamma Mountain and the Reclining Buddha, Kappa Province"
SITE = (10.81, 107.89)
PROVINCE = (11.083333, 108.083333)      # ~35 km from the site
MODEL_PIN = (10.9191, 107.6461)         # ~29.5 km from the site (the 552 shape)


@pytest.fixture
def stubbed_resolver(monkeypatch):
    calls = []
    monkeypatch.setattr(ar, "_resolve_city", lambda c: ("Q-PROV", PROVINCE))
    monkeypatch.setattr(ar, "_is_country_type", lambda q: False)
    monkeypatch.setattr(ar, "_is_city_type", lambda q: True)
    monkeypatch.setattr(ar, "_resolve_neighborhood", lambda n, c, q: ("", (0.0, 0.0)))
    monkeypatch.setattr(ar, "_detect_language", lambda q: "en")
    monkeypatch.setattr(ar, "_get_country", lambda q: "Q-Z")
    monkeypatch.setattr(ar, "_nominatim_bbox", lambda q: [10.5, 11.7, 107.3, 108.7])
    monkeypatch.setattr(ar, "parse_districts", lambda n, c: [])

    def lookup_ok(name, city=""):
        calls.append((name, city))
        return {"qid": "Q9", "aliases": [name], "lat": SITE[0], "lng": SITE[1]}
    monkeypatch.setattr(ar, "_wikidata_name_lookup", lookup_ok)
    return calls


def test_first_named_place_splits_on_and_comma_dash():
    assert ar.first_named_place("Gamma Mountain and the Reclining Buddha") == "Gamma Mountain"
    assert ar.first_named_place("The Gamma Mountain, Kappa Province") == "Gamma Mountain"
    assert ar.first_named_place("Gamma Mountain \u2013 Kappa") == "Gamma Mountain"
    assert ar.first_named_place("Gamma Mountain & Delta") == "Gamma Mountain"
    assert ar.first_named_place("") == ""


def test_resolve_area_gives_a_place_level_reference_for_the_552_shape(stubbed_resolver, capsys):
    area = ar.resolve_area(LOC)
    assert area is not None and area.resolved
    assert area.place_ref_precision == "place" and area.place_ref_source == "first_named_place"
    assert (area.place_ref_lat, area.place_ref_lng) == SITE and area.place_ref_name == "Gamma Mountain"
    assert (area.center_lat, area.center_lng) == PROVINCE, "the scope centre itself is unchanged"
    assert stubbed_resolver[0][0] == "Gamma Mountain"
    out = capsys.readouterr().out
    assert "[LOCAL-901] place reference 'Gamma Mountain' \u2192 10.8100,107.8900 (first_named_place)" in out


def test_552_both_pins_replaced_by_the_place_reference(stubbed_resolver):
    area = ar.resolve_area(LOC)
    stops = [{"name": "Gamma Mountain", "coordinates": f"{MODEL_PIN[0]}, {MODEL_PIN[1]}"},
             {"name": "Gamma Mountain National Park", "coordinates": f"{MODEL_PIN[0]}, {MODEL_PIN[1]}"}]
    logs = []
    n = pn.check_pins_against_scope(
        stops, (area.place_ref_lat, area.place_ref_lng), "", log=logs.append,
        ref_precision=area.place_ref_precision, ref_source=area.place_ref_source)
    assert n == 2
    for s in stops:
        lat, lng = (float(x) for x in s["coordinates"].split(","))
        assert pn._hav((lat, lng), SITE) < 15 and s["coordinates_approximate"]
    assert any("action=replaced" in x for x in logs)


def test_lookup_result_abroad_is_refused(stubbed_resolver, monkeypatch, capsys):
    monkeypatch.setattr(ar, "_wikidata_name_lookup",
                        lambda name, city="": {"qid": "Q1", "aliases": [], "lat": 13.748, "lng": 100.491})
    area = ar.resolve_area(LOC)
    assert area.place_ref_precision == "" and area.place_ref_lat == 0.0
    assert "REFUSED" in capsys.readouterr().out
    stops = [{"name": "Gamma Mountain", "coordinates": f"{MODEL_PIN[0]}, {MODEL_PIN[1]}"}]
    logs = []
    n = pn.check_pins_against_scope(stops, PROVINCE, "", log=logs.append, ref_precision="region",
                                    ref_source="area_resolver('Kappa Province')")
    assert n == 0 and any("skipped_coarse_ref" in x for x in logs), "900B still refuses the coarse centre"


def test_far_result_inside_the_geocoder_bbox_is_accepted(stubbed_resolver, monkeypatch):
    # 130+ km from the coarse centre but inside the province bbox -> accepted
    monkeypatch.setattr(ar, "_nominatim_bbox", lambda q: [9.0, 12.5, 106.0, 109.0])
    monkeypatch.setattr(ar, "_wikidata_name_lookup",
                        lambda name, city="": {"qid": "Q1", "aliases": [], "lat": 9.6, "lng": 107.9})
    assert ar.resolve_area(LOC).place_ref_precision == "place"


def test_no_lookup_hit_or_single_name_location_gives_no_reference(stubbed_resolver, monkeypatch):
    monkeypatch.setattr(ar, "_wikidata_name_lookup", lambda name, city="": None)
    assert ar.resolve_area(LOC).place_ref_precision == ""
    assert ar.first_named_place_reference("Gamma Mountain", "Kappa", PROVINCE) is None


def test_pin_check_in_the_pipeline_prefers_the_place_reference():
    s = _src("generate_tour_text.py")
    assert "place_ref_precision" in s and "[LOCAL-901] pin check uses place reference" in s


# ── C. 791E dedupe keeps distinct structures ─────────────────────────────────
import walking_stop_title as wst  # noqa: E402
import local802_relevance_gate as g802  # noqa: E402


def _P(name, **k):
    return {"name": name, "coordinates": "10.0, 100.0", **k}


def test_distinct_structures_are_not_the_same_place_as_the_mountain():
    stops = [_P("Gamma Mountain"), _P("Delta Statue"), _P("Omega Pagoda"), _P("Lambda Pagoda"),
             _P("Gamma Cable Car Station"), _P("Epsilon Museum")]
    logs = []
    out = wst.dedupe_place_titles(stops, log=logs.append)
    assert [p["name"] for p in out] == [p["name"] for p in stops], logs
    assert not logs


def test_true_duplicates_still_merge():
    out = wst.dedupe_place_titles([_P("Notre-Dame Cathedral Basilica"), _P("Saigon Notre-Dame Basilica"),
                                   _P("Gamma Mountain"), _P("Gamma Mountain")])
    assert [p["name"] for p in out] == ["Notre-Dame Cathedral Basilica", "Gamma Mountain"]
    # same QID / alias merge even for structures
    out = wst.dedupe_place_titles([_P("Omega Pagoda", wikidata_qid="Q5"), _P("Lambda Temple", wikidata_qid="Q5")])
    assert len(out) == 1
    out = wst.dedupe_place_titles([_P("Omega Pagoda", aliases=["Lambda Temple"]), _P("Lambda Temple")])
    assert len(out) == 1


def test_same_building_gate_does_not_merge_a_structure_located_in_the_mountain():
    mtn = _P("Gamma Mountain", wikidata_qid="Q1")
    statue = _P("Delta Statue", wikidata_qid="Q2", located_in=["Q1"])
    assert not g802.same_building(mtn, statue)
    assert not g802.same_building(_P("Gamma Mountain"), _P("Omega Pagoda"))   # same pin (<= 60 m)
    kept, removed = g802.dedupe_same_building_stops([mtn, statue, _P("Lambda Pagoda", wikidata_qid="Q3")])
    assert len(kept) == 3 and not removed
    # a genuine same-QID duplicate still merges
    assert g802.same_building(_P("Omega Pagoda", wikidata_qid="Q7"), _P("Omega Temple", wikidata_qid="Q7"))


# ── D. mood filler on the single-place path ──────────────────────────────────
FILLERS = ["The pagoda's wooden beams creak gently in the mountain breeze",
           "This mountain and its pagoda stand at a crossroads of shifting administrative boundaries",
           "This tour explores the enduring connection between spirituality and the natural world",
           "This relationship highlights the significance of finding peace and tranquility"]


def test_552_filler_and_closing_paragraph_are_capped():
    t = _fx("local901_tour552_filler.txt")
    for f in FILLERS:
        assert f in t
    logs = []
    out = rc.apply_single_place_guards(t, logs.append)
    for f in FILLERS:
        assert f not in out
    # facts, numbers, the stop count and the restaurant offer survive
    for keep in ("constructed in 1861", "49 meters long", "That's 2 stops in all.", "restaurant tour",
                 "Visitors often reach this site by taking a cable car"):
        assert keep in out
    assert sum("mood filler dropped" in x for x in logs) == 4
    assert rc.apply_single_place_guards(out) == out, "idempotent"


def test_a_body_that_is_all_filler_is_left_as_it_was():
    t = ("Stop 1: Alpha Site\nType/Specialty: Landmark\n"
         "The gentle breeze whispers a timeless testament to peace.\n")
    assert rc.cap_single_place_filler(t) == t


def test_sentences_with_numbers_or_no_mood_terms_are_never_filler():
    assert not rc.is_mood_filler("It was built in 1861 in a gentle, peaceful valley.", set())
    assert not rc.is_mood_filler("Visitors reach the summit by cable car.", set())
    assert rc.is_mood_filler("The breeze echoes a timeless serenity.", set())
    assert rc.is_mood_filler("A gentle path leads to the pagoda.", {"statue"})     # 1 hit, unsupported
    assert not rc.is_mood_filler("A gentle path leads to the Statue.", {"statue"})  # 1 hit, supported


def test_filler_cap_leaves_a_route_tour_to_the_897_pass(route):
    t = _fx("local901_tour552_filler.txt")
    assert rc.active()
    assert "creak gently" in rc.apply_single_place_guards(t)


def test_two_structures_at_one_street_address_still_collapse_but_not_at_a_shared_area_address():
    street = "73 Alpha Street, Beta, District 1"
    out = wst.dedupe_place_titles([_P("Jade Pagoda", address=street, _anchor=True), _P("Ngoc Pagoda", address=street)])
    assert [p["name"] for p in out] == ["Jade Pagoda"]
    area = "Gamma Mountain, Zeta, Kappa, Zedland"
    out = wst.dedupe_place_titles([_P("Omega Pagoda", address=area), _P("Lambda Pagoda", address=area),
                                   _P("Gamma Mountain", address=area)])
    assert len(out) == 3
