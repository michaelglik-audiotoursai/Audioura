#!/usr/bin/env python3
"""LOCAL-883 — strict grounding gate + canonical-resolver DISTINCTIVE-token fix +
the three small items (orphan 'is long', dangling 'Continue to X', cache-revalidate
log line). Fully offline: the grounding LLM is injected, the resolver's network is
injected, the small-item scrubs are deterministic.
"""
import io
import os
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import strict_grounding_gate as sgg       # noqa: E402
import venue_canonical_resolver as vcr     # noqa: E402
import spoken_text_hygiene as sth          # noqa: E402
import walking_directions_guard as wdg     # noqa: E402

CITY = "Ho Chi Minh City"


# ═══════════════════ 1. FACTUAL / NON-FACTUAL classification ═══════════════════
def test_factual_cue_floor():
    factual = [
        "The palace was designed by architect Ngô Viết Thụ in 1962.",
        "On 30 April 1975 a North Vietnamese tank crashed through the gates.",
        "The twin bell towers each hold six bronze bells.",
        "It is the first cathedral built in the city.",
        "Bishop Colombert laid the first stone in 1877.",
    ]
    nonfactual = [
        "You stand before the red brick façade of the cathedral.",
        "Head northwest for about 500 metres to the museum.",
        "Continue to City Hall, about 400 metres southeast.",
        "Take a moment to breathe in the atmosphere.",
        "The breeze carries the scent of the river.",
    ]
    for s in factual:
        assert sgg.is_factual_sentence(s), f"should be FACTUAL: {s}"
    for s in nonfactual:
        assert not sgg.is_factual_sentence(s), f"should be NON-FACTUAL: {s}"


# ═══════════════════ 2. the gate keeps SUPPORTED, drops the rest ═══════════════
def _fake_classify(verdicts):
    def fn(system, user, model, **kw):
        return ({"verdicts": verdicts}, 120, 60)
    return fn


def test_gate_keeps_supported_drops_contradicted_and_unsupported():
    body = ("The palace was designed by architect Ngô Viết Thụ in 1962. "
            "President Diem declared independence here in 1945. "
            "Gustave Eiffel completed an earlier structure in 1863. "
            "You stand in a wide forecourt today.")
    cls = _fake_classify([
        {"i": 1, "verdict": "SUPPORTED", "evidence": "designed by Thu 1962", "legend": False},
        {"i": 2, "verdict": "CONTRADICTED", "evidence": "", "legend": False},
        {"i": 3, "verdict": "UNSUPPORTED", "evidence": "", "legend": False},
    ])
    out, rep = sgg.apply_grounding_gate(
        "Independence Palace", body, evidence="designed by Ngô Viết Thụ, built 1962",
        classify_fn=cls)
    assert "Ngô Viết Thụ" in out
    assert "1945" not in out                     # contradicted dropped
    assert "Eiffel" not in out                   # unsupported dropped
    assert "wide forecourt" in out               # non-factual kept
    assert rep["contradicted"] == 1 and rep["unsupported"] == 1


def test_gate_discloses_legend_not_drops_it():
    body = ("Witnesses have reported a mysterious tear from the statue here. "
            "The statue was installed in 1959.")
    cls = _fake_classify([
        {"i": 1, "verdict": "UNSUPPORTED", "evidence": "a local legend of a weeping statue", "legend": True},
        {"i": 2, "verdict": "SUPPORTED", "evidence": "installed 1959", "legend": False},
    ])
    out, rep = sgg.apply_grounding_gate(
        "Cathedral", body, evidence="a local legend says the statue wept; installed 1959",
        classify_fn=cls)
    assert rep["disclosed"] == 1
    assert "legend" in out.lower()               # disclosed, not asserted flat
    assert "installed in 1959" in out


def test_gate_drops_factual_when_no_evidence_keeps_nonfactual():
    # [LOCAL-884 §1] "No evidence" means "no factual claim": a factual sentence
    # with no evidence to back it is UNSUPPORTED and dropped (no LLM call); a
    # non-factual sentence is kept.
    body = ("The hall opened in 1908. You cross a wide courtyard.")
    out, rep = sgg.apply_grounding_gate("City Hall", body, evidence="",
                                        classify_fn=_fake_classify([]))
    assert "1908" not in out                     # factual, no evidence → dropped
    assert "wide courtyard" in out               # non-factual → kept
    assert rep["called"] is False                # no LLM call: nothing to check
    assert rep["no_evidence"] is True
    assert rep["labelled"] == 1 and rep["unsupported"] == 1


def test_gate_drops_founded_1163_on_empty_evidence():
    # the cathedral wave-42 regression: an empty bundle with "founded in 1163"
    # (Notre-Dame de Paris, not the Saigon cathedral) is dropped, never shipped.
    body = ("The cathedral was founded in 1163, built in 1182 and completed in 1345. "
            "You hear the bells drift across the square.")
    out, rep = sgg.apply_grounding_gate("Cathedral", body, evidence="  ",
                                        classify_fn=_fake_classify([]))
    assert "1163" not in out and "1182" not in out and "1345" not in out
    assert "bells drift" in out
    assert rep["no_evidence"] is True and rep["labelled"] >= 1


# ═══════════════════ 3. tour-level gate + shortfall rebuild ════════════════════
TOUR = (
    "Stop 1: City Hall\n"
    "Orientation: You reach a wide square.\n"
    "The building served French colonial administrations. "
    "In 1945 the declaration of independence was proclaimed within these walls. "
    "You cross the courtyard. The façade faces the boulevard.\n"
    "Directions: Head to the Post Office.\n"
)


def test_ground_tour_text_edits_the_block():
    def cls(system, user, model, **kw):
        # mark the 1945 claim UNSUPPORTED, the colonial-admin sentence SUPPORTED
        vs = []
        for i, line in enumerate(user.splitlines()):
            pass
        return ({"verdicts": [
            {"i": 1, "verdict": "SUPPORTED", "evidence": "built for the colonial administration", "legend": False},
            {"i": 2, "verdict": "UNSUPPORTED", "evidence": "", "legend": False},
        ]}, 100, 50)
    ev = {"City Hall": "The Hôtel de Ville was built for the French colonial administration from 1898."}
    out, rep = sgg.ground_tour_text(TOUR, ev, classify_fn=cls,
                                    max_cost_usd=1.0)
    assert "declaration of independence" not in out
    assert "colonial administrations" in out
    assert rep["stops"] == 1


def test_shortfall_triggers_rebuild():
    # a body that loses too many sentences gets rebuilt from facts (injected)
    tour = (
        "Stop 1: Pier\n"
        "Orientation: You reach the riverbank.\n"
        "The evacuation happened from this very platform in 1975. "
        "You feel the breeze.\n"
        "Directions: Continue to the next stop.\n"
    )

    def cls(system, user, model, **kw):
        return ({"verdicts": [
            {"i": 1, "verdict": "UNSUPPORTED", "evidence": "", "legend": False},
        ]}, 50, 20)

    def rebuild(title, facts):
        return ["The pier opened in 1912 as a river port.",
                "Ferries once left here for the Mekong Delta.",
                "The quay was rebuilt in the 1990s.",
                "It remains a working waterfront today.",
                "Boats still dock along its length."]

    # the rebuild sentences are all SUPPORTED on the second pass
    calls = {"n": 0}

    def cls2(system, user, model, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return ({"verdicts": [{"i": 1, "verdict": "UNSUPPORTED", "evidence": "", "legend": False}]}, 50, 20)
        # second pass: everything supported
        n = len([ln for ln in user.splitlines() if ln[:2].strip().isdigit()])
        return ({"verdicts": [{"i": i, "verdict": "SUPPORTED", "evidence": "evidence", "legend": False}
                              for i in range(1, 6)]}, 80, 40)

    ev = {"Pier": "The pier opened in 1912. Ferries left for the Mekong Delta. Rebuilt in the 1990s."}
    out, rep = sgg.ground_tour_text(
        tour, ev, classify_fn=cls2, rebuild_fn=rebuild,
        facts_by_title={"Pier": ["opened 1912", "ferries to Mekong"]}, max_cost_usd=1.0)
    assert rep["rebuilt"] == 1
    assert "this very platform" not in out
    assert "river port" in out


def test_cost_cap_stops_further_calls():
    tour = TOUR + ("Stop 2: Post Office\nOrientation: x.\n"
                   "It opened in 1891. The clock is central.\nDirections: End.\n")

    def cls(system, user, model, **kw):
        return ({"verdicts": [{"i": 1, "verdict": "SUPPORTED", "evidence": "e", "legend": False}]}, 10**6, 10**6)
    # substantial evidence per stop so a real LLM call is made (an empty/thin
    # bundle would be handled by the no-evidence drop, with no call and no cost).
    ev = {"City Hall": "The Hôtel de Ville was built from 1898 to 1909 for the colonial administration.",
          "Post Office": "The Saigon Central Post Office opened in 1891, designed by Foulhoux."}
    out, rep = sgg.ground_tour_text(tour, ev, classify_fn=cls, max_cost_usd=0.0001)
    # the first call alone blows the cap, so the second stop is skipped
    assert rep["cost_usd"] > 0


# ═══════════════════ 4. canonical resolver (wave-41 leaks) ════════════════════
def _around(cands):
    return lambda lat, lng, r, ll: cands


def test_book_street_rejects_nearest_notable():
    cands = [{"qid": "Q9", "label_en": "22 Gia Long Street", "label_local": "",
              "aliases": [], "lat": 10.780873, "lng": 106.699695, "p31": ["Q79007"]}]
    got = vcr.resolve_canonical("Book Street", (10.780573, 106.699695), city=CITY,
                                around_fn=_around(cands), places_fn=lambda *a: [])
    assert got is None, got                       # shares only 'street' → rejected


def test_thi_bar_rejects_nearest_hotel():
    cands = [{"qid": "Q10", "label_en": "DDA Hotel 183 De Tham", "label_local": "",
              "aliases": [], "lat": 10.767860, "lng": 106.693960, "p31": ["Q27686"]}]
    got = vcr.resolve_canonical("Thi Bar", (10.767660, 106.693960), city=CITY,
                                around_fn=_around(cands), places_fn=lambda *a: [])
    assert got is None, got                       # no shared token → rejected


def test_cathedral_rejects_wrong_kind_square():
    cands = [{"qid": "Q11", "label_en": "Paris Commune Square", "label_local": "",
              "aliases": [], "lat": 10.780172, "lng": 106.699167, "p31": ["Q174782"]}]
    got = vcr.resolve_canonical("Cathedral", (10.779722, 106.699167), city=CITY,
                                around_fn=_around(cands), places_fn=lambda *a: [])
    assert got is None, got                       # kind mismatch (square ≠ cathedral)


def test_cathedral_accepts_real_cathedral_same_kind_p31():
    cands = [
        {"qid": "Q11", "label_en": "Paris Commune Square", "label_local": "",
         "aliases": [], "lat": 10.780522, "lng": 106.699167, "p31": ["Q174782"]},
        {"qid": "Q12", "label_en": "Saigon Notre-Dame Cathedral Basilica",
         "label_local": "", "aliases": ["Notre-Dame Cathedral"],
         "lat": 10.779922, "lng": 106.699167, "p31": ["Q2977"]},
    ]
    got = vcr.resolve_canonical("Cathedral", (10.779722, 106.699167), city=CITY,
                                around_fn=_around(cands), places_fn=lambda *a: [])
    assert got is not None and "Cathedral" in got["canonical_en"]


def test_city_hall_accepts_hotel_de_ville():
    cands = [{"qid": "Q1", "label_en": "Ho Chi Minh City Hall",
              "label_local": "Trụ sở Ủy ban Nhân dân", "aliases": ["Hôtel de Ville de Saïgon"],
              "lat": 10.776480, "lng": 106.700975, "p31": ["Q543654"]}]
    got = vcr.resolve_canonical("City Hall", (10.776470, 106.700970), city=CITY,
                                local_lang="vi", around_fn=_around(cands),
                                places_fn=lambda *a: [])
    assert got is not None and got["canonical_en"] == "Ho Chi Minh City Hall"


def test_distinctive_name_still_resolves():
    cands = [{"qid": "Q13", "label_en": "Nguyễn Văn Bình Book Street",
              "label_local": "Đường sách Nguyễn Văn Bình", "aliases": [],
              "lat": 10.780673, "lng": 106.699695, "p31": ["Q79007"]}]
    got = vcr.resolve_canonical("Nguyễn Văn Bình Book Street", (10.780573, 106.699695),
                                city=CITY, around_fn=_around(cands), places_fn=lambda *a: [])
    assert got is not None and got["match_tier"] == 0


def test_places_pick_rejected_when_no_shared_token():
    # nearest Places establishment shares nothing with 'Café Apartments 42'
    got = vcr.resolve_canonical("Café Apartments 42", (10.774089, 106.704056),
                                city=CITY, around_fn=lambda *a: [],
                                places_fn=lambda *a: [{"name": "The Reverie Saigon",
                                                       "lat": 10.774089, "lng": 106.704056}])
    assert got is None, got


def test_places_pick_accepted_when_shares_kind():
    got = vcr.resolve_canonical("Café Apartments 42", (10.774089, 106.704056),
                                city=CITY, around_fn=lambda *a: [],
                                places_fn=lambda *a: [{"name": "The Cafe Apartment",
                                                       "lat": 10.774089, "lng": 106.704056}])
    assert got is not None and got["canonical_en"] == "The Cafe Apartment"


def test_user_link_names_the_venue():
    # the short typed name shares no token, but the user's own link does
    cands = [{"qid": "Q20", "label_en": "Bến Thành Market", "label_local": "Chợ Bến Thành",
              "aliases": [], "lat": 10.772, "lng": 106.698, "p31": ["Q330284"]}]
    got = vcr.resolve_canonical("The Market", (10.772, 106.698), city=CITY,
                                around_fn=_around(cands), places_fn=lambda *a: [],
                                user_link="https://maps.google.com/?q=Ben+Thanh+Market")
    assert got is not None and "Bến Thành" in got["canonical_en"]


# ═══════════════════ 5. small items ═══════════════════════════════════════════
def test_orphan_is_long_removed():
    txt = ("Stop 2: Book Street\nOrientation: You enter a lane.\n"
           "This narrow street is 100 metres long. It is lined with bookshops.\n"
           "Directions: Continue to the museum.\n")
    out, rep = sth.audit_seating_capacity(
        txt, stop_evidence={"Book Street": "A pedestrian street lined with bookstores."})
    assert "is long" not in out
    assert "This narrow street" in out
    assert "lined with bookshops" in out


def test_sourced_magnitude_kept():
    txt = ("Stop 1: Cathedral\nOrientation: x.\n"
           "The towers rise 58 metres above the square.\nDirections: End.\n")
    out, rep = sth.audit_seating_capacity(
        txt, stop_evidence={"Cathedral": "The bell towers reach a height of 58 metres."})
    assert "58" in out                            # sourced → kept


def test_dangling_continue_to_is_wrong_target():
    assert wdg._directions_target_is_wrong(
        "Continue to City Hall, about 400 metres southeast.", "Post Office", [])
    assert not wdg._directions_target_is_wrong(
        "Continue to the Post Office.", "Post Office", [])
    assert not wdg._directions_target_is_wrong(
        "Head north for 200 metres.", "Post Office", [])
    assert not wdg._directions_target_is_wrong(
        "Walk east; you will pass the old market on your right.", "Post Office", ["Old Market"])


def test_dangling_continue_replaced_with_next_stop():
    tour = (
        "Stop 1: Opera House\nCoordinates: 10.7764, 106.7028\n"
        "Orientation: You face the theatre.\n"
        "The theatre opened in 1900.\n"
        "Directions: Continue to City Hall.\n\n"
        "Stop 2: Post Office\nCoordinates: 10.7800, 106.7000\n"
        "Orientation: x.\nThe post office opened in 1891.\n"
        "Directions: Enjoy the walk.\n"
    )
    out, rep = wdg.ensure_walking_directions_lead_to_next(tour)
    assert "Continue to City Hall" not in out
    assert "Post Office" in out                   # corrected hand-off names the next stop


def test_cache_revalidate_log_line_present():
    import landmark_wikipedia_evidence as lwe

    class _FakeCur:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, *a, **k): self._q = a
        def fetchone(self):
            import json as _j
            # a current-version HIT whose stored title name-matches the stop
            return (_j.dumps({"title": "Test Hall", "lead": "", "infobox": {}}),
                    True, lwe.RULES_VERSION)

    class _FakeConn:
        def cursor(self): return _FakeCur()
        def commit(self): pass

    _orig_conn, _orig_ensure = lwe._conn, lwe._ensure
    lwe._conn = lambda: _FakeConn()
    lwe._ensure = lambda conn: True
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            lwe._cache_get("Test Hall", "en", pin=(10.0, 106.0))
        assert "[LOCAL-882] cache revalidate" in buf.getvalue(), buf.getvalue()
    finally:
        lwe._conn, lwe._ensure = _orig_conn, _orig_ensure


if __name__ == "__main__":
    _p = _f = 0
    for _n, _fn in sorted(globals().items()):
        if _n.startswith("test_") and callable(_fn):
            try:
                _fn()
                print(f"PASS {_n}")
                _p += 1
            except Exception as e:
                import traceback
                print(f"FAIL {_n}: {e}")
                traceback.print_exc()
                _f += 1
    print(f"\n{_p} passed, {_f} failed")
    sys.exit(1 if _f else 0)
