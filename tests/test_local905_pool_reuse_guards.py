"""LOCAL-905 -- the stop-pool reuse path runs the same guards as a fresh stop. Offline: fake pool, no DB, no network."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import delivery_bodies_905 as db
import identity_dedup as idd
import pool_guards_905 as pg
import required_places_902 as rp
import stop_pool_orchestrator as orch

CTX = {"scope_center": (10.83, 107.88), "scope_precision": "DISTRICT", "place_ref": (10.828, 107.8828)}
BODY = "This pagoda sits above the sea and has a long stairway. Pilgrims climb it every morning."
GOOD = {"title": "Good Pagoda", "narration": BODY, "coordinates": "10.8265, 107.8901"}
FAR = {"title": "Far Statue", "narration": BODY, "coordinates": "13.748056, 100.491111"}
NEAR_BAD = {"title": "Old Pagoda", "narration": BODY, "coordinates": "10.8265, 107.5901"}      # ~33 km off
EMPTY = {"title": "Empty Stop", "narration": "  ", "coordinates": "10.83, 107.88"}


def test_far_pin_and_empty_body_rejected_on_reuse(capsys):
    kept, n = pg.filter_rows([GOOD, FAR, NEAR_BAD, EMPTY], CTX, log=print)
    assert [r["title"] for r in kept] == ["Good Pagoda"] and n == 3
    out = capsys.readouterr().out
    assert "[LOCAL-905] pool row 'Far Statue' rejected:" in out
    assert "[LOCAL-905] pool row 'Empty Stop' rejected: empty body" in out
    assert "'Old Pagoda' rejected: pin 32 km" in out        # the ~33 km pagoda


def test_place_reference_rule_on_a_single_place_scope():
    ctx = {"scope_center": (10.83, 107.88), "scope_precision": "DISTRICT", "place_ref": (10.9, 107.88)}
    row = dict(GOOD, coordinates="10.70, 107.88")        # 14 km from the centre, 22 km from the reference
    assert "verified place reference" in pg.pin_reject(row, ctx)


def test_route_box_rejects_outside_pin():
    ctx = {"route_box": [10.7, 10.9, 107.8, 108.0]}
    assert pg.pin_reject(GOOD, ctx) == ""
    assert "route box" in pg.pin_reject(FAR, ctx)


def test_no_pin_or_no_context_is_not_rejected():
    assert pg.pin_reject({"coordinates": ""}, CTX) == ""
    assert pg.pin_reject(FAR, {}) == ""


def _patch_pool(monkeypatch, rows):
    import stop_pool_store as store
    monkeypatch.setattr(store, "get_pool_stops", lambda *a, **k: list(rows))
    monkeypatch.setattr(orch, "_auto_reject_junk_titles", lambda r, *a, **k: r)
    monkeypatch.setattr(orch, "_revalidate_pooled_scope", lambda r, *a, **k: (r, 0))
    monkeypatch.setattr(pg, "build_context", lambda *a, **k: CTX)
    import stop_pool_sources as prov
    monkeypatch.setattr(prov, "filter_protected_titles", lambda r, *a, **k: r)
    return store


def test_orchestrator_does_not_serve_bad_rows(monkeypatch, capsys):
    _patch_pool(monkeypatch, [GOOD, FAR, NEAR_BAD, EMPTY])
    seen = {}

    def gen(location, tour_type, out, n, user_id=None, job_id=None, exclude_titles=None):
        seen["n"], seen["ex"] = n, list(exclude_titles or [])
        return None, None, (None, None)        # new-stop generation fails -> normal fallback (None)

    orch.maybe_generate_with_pool("Some Mountain, Province, Country", "walking", 4, "postgres://fake", gen)
    assert seen["ex"] == ["Good Pagoda"] and seen["n"] == 3      # only the good row counted as reusable
    assert "[LOCAL-905] pool row 'Old Pagoda' rejected" in capsys.readouterr().out


@pytest.mark.parametrize("n", [1, 2])
def test_small_tour_skips_the_pool(monkeypatch, capsys, n):
    import stop_pool_store as store

    def boom(*a, **k):
        raise AssertionError("pool must not be read for a <= 2 stop tour")
    monkeypatch.setattr(store, "get_pool_stops", boom)
    assert orch.maybe_generate_with_pool("X", "walking", n, "postgres://fake", lambda *a, **k: None) is None
    assert "[LOCAL-905] pool skipped: <= 2 stops" in capsys.readouterr().out


def test_three_stops_still_reads_the_pool(monkeypatch):
    assert not pg.skip_pool_for_small_tour(3) and pg.skip_pool_for_small_tour(2)


TOUR = """Stop 1: Pagoda
Coordinates: 10.8265, 107.5901
Type/Specialty: Buddhist temple
Orientation:

Together, these experiences make the day. That's 2 stops in all.
"""

TWO = """Stop 1: Mountain
Coordinates: 10.8, 107.8
Orientation: Start at the gate.

The mountain rises above the bay and has a long history of pilgrims. People climb it at dawn.

Directions: Continue to Pagoda.

Stop 2: Pagoda
Coordinates: 10.8, 107.8
Orientation:

Together, these experiences make the day. That's 2 stops in all.
"""


def test_empty_last_stop_is_refilled_and_count_is_true(capsys):
    out = db.ensure_bodies(TWO, evidence_by_title={"Pagoda": "The pagoda was built in 1960 above the bay."},
                           log=print)
    assert "The pagoda was built in 1960 above the bay." in out
    assert "That's 2 stops in all." in out
    assert "empty body on delivery -> refilled (own evidence)" in capsys.readouterr().out


def test_empty_stop_without_any_refill_is_removed_and_count_corrected(monkeypatch, capsys):
    import strict_grounding_gate as sgg
    monkeypatch.setattr(sgg, "sensory_body", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no")))
    out = db.ensure_bodies(TWO, evidence_by_title={}, log=print)
    assert "Stop 2:" not in out and "Stop 1: Mountain" in out
    assert "That's 1 stop in all." in out
    assert "removed" in capsys.readouterr().out


def test_empty_stop_gets_honest_body_by_default():
    out = db.ensure_bodies(TWO, evidence_by_title={})
    assert "Stop 2: Pagoda" in out and "That's 2 stops in all." in out
    block = out.split("Stop 2: Pagoda")[1]
    assert len([ln for ln in block.split("\n") if ln.strip() and not ln.startswith(("Coordinates", "Orientation"))]) >= 2


def test_count_is_corrected_when_it_disagrees():
    t = TWO.replace("That's 2 stops in all.", "That's 5 stops in all.")
    assert "That's 2 stops in all." in db.ensure_bodies(t, evidence_by_title={"Pagoda": "The pagoda dates from 1960 and faces the bay."})


def test_stop_with_a_body_is_untouched():
    t = TWO.replace("Orientation:\n\n", "Orientation:\n\nA quiet pagoda stands here above the bay. It was rebuilt in 1960.\n\n")
    assert db.ensure_bodies(t) == t


def test_pool_path_tour_pin_is_the_first_delivered_stop():
    assert pg.first_stop_pin(TWO) == (10.8, 107.8)
    assert pg.first_stop_pin("no stops here") == (None, None)
    import generate_tour_text as g
    import inspect
    src = inspect.getsource(g)
    assert "first_stop_pin(_pool_out" in src and '(_pool_out["text"], output_file, (None, None))' not in src


# ---- item 5: required places survive ---------------------------------------------------------------------
def _poi(name, addr="", **kw):
    d = {"name": name, "address": addr, "coordinates": "10.0, 107.0"}
    d.update(kw)
    return d


def _new(n, a):
    return _poi(n, a)


def test_required_match_by_core_tokens():
    assert rp._matches("Lady Buddha", "Lady Buddha Statue")
    assert rp._matches("Mount Tao", "Tao Mountain", loose=True)
    assert not rp._matches("Lady Buddha", "Pagoda")


def test_selection_statue_plus_required_mountain_and_statue():
    out = rp.ensure_required_stops([_poi("Lady Buddha Statue")], ["Mountain Tao", "Lady Buddha"], _new, max_stops=2)
    assert [p["name"] for p in out] == ["Mountain Tao", "Lady Buddha Statue"]
    assert all(p["_required_902"] for p in out)


def test_cap_keeps_required_stops_in_the_inner_run():
    import generate_tour_text as g
    import inspect
    assert "_req_n905" in inspect.getsource(g)


def test_dedupe_keeps_two_colliding_required_stops():
    a = _poi("Mountain Tao", _required_902=True, user_explicit=True, coordinates="10.800000, 107.800000")
    b = _poi("Lady Buddha Statue", _required_902=True, user_explicit=True, coordinates="10.800010, 107.800010")
    kept, dropped = idd.dedupe_by_location_or_qid([a, b])
    assert len(kept) == 2 and not dropped


def test_dedupe_prefers_the_required_stop_over_an_ordinary_one():
    a = _poi("Ordinary Viewpoint", coordinates="10.800000, 107.800000")
    b = _poi("Lady Buddha Statue", _required_902=True, user_explicit=False, coordinates="10.800010, 107.800010")
    kept, _ = idd.dedupe_by_location_or_qid([a, b])
    assert [p["name"] for p in kept] == ["Lady Buddha Statue"]


def test_identity_dedup_never_merges_two_required_stops():
    a = _poi("Mountain Tao", _required_902=True, qid="Q1")
    b = _poi("Lady Buddha Statue", _required_902=True, qid="Q1")
    out, _ = idd.dedup_by_identity([a, b])
    assert len(out) == 2


def test_audit_lists_bad_rows_per_key():
    import local905_pool_audit as au
    rows = [dict(r, pool_key="k1", venue_identity="loc:x") for r in (GOOD, EMPTY, dict(GOOD, title="G2"))]
    rep = au.audit(rows, ctx_for=lambda r: CTX)
    assert rep == {"k1": [("Empty Stop", "empty body")]}
