#!/usr/bin/env python3
"""LOCAL-894 -- a described request with a user stop LIST (Michael's Phan Thiet driving
tour, cloud 549). Offline: the network is blocked and OpenAI is faked.

Generic: the unit tests use the request from the field report as a FIXTURE only; nothing
in the code under test names a place (D769)."""
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import user_list_integrity as uli  # noqa: E402

REQUEST = (
    "Create a half-day driving tour from Caty Mui Ne Resort in Ham Tien, Mui Ne, to Ta Cu "
    "Mountain in Binh Thuan province and back, for an English-speaking family visiting "
    "Vietnam for the first time. The drive takes about one hour each way through Phan Thiet "
    "and past dragon fruit plantations. Include the history of Phan Thiet and the Cham "
    "heritage of the region, how dragon fruit is grown and why Binh Thuan is famous for it, "
    "the story of Ta Cu Mountain and the Linh Son Truong Tho Pagoda, the cable car ascent, "
    "and the 49-meter Reclining Buddha \u2014 its construction, meaning in Buddhism, and the "
    "pilgrimage tradition. Keep the tone warm and unhurried, with the longer stories timed "
    "for the drive and short segments at each stop on the mountain. End with the return "
    "drive to Mui Ne.")
STOPS = [
    "Leaving Mui Ne \u2013 the fishing coast and Ham Tien strip",
    "Phan Thiet and the Ca Ty River",
    "Dragon fruit country \u2013 the plantations along the road",
    "Arriving at Ta Cu \u2013 the mountain and its legends (for the base / electric car)",
    "The cable car ascent",
    "Linh Son Truong Tho Pagoda",
    "The Reclining Buddha",
    "The summit views and the drive home",
]
EXPECTED_TITLES = [uli.strip_qualifier(s) for s in STOPS]


# ── 1. location from a long description ─────────────────────────────────────
class TestLocationFromDescription:
    def test_request_is_a_description(self):
        assert uli.looks_like_description(REQUEST)
        assert not uli.looks_like_description("Ham Tien, Mui Ne")
        assert not uli.looks_like_description("Boston, MA")

    def test_place_scope_and_title(self):
        d = uli.derive_request_place(REQUEST, "driving")
        assert d["is_description"]
        assert "Mui Ne" in d["location"] or "Ham Tien" in d["location"]
        assert len(d["location"]) <= 80
        assert d["origin"] == "Caty Mui Ne Resort"
        assert d["destination"] == "Ta Cu Mountain"
        # the scope is the REGION that holds both end-points
        assert "Binh Thuan" in d["scope"]
        assert "Phan Thiet" in d["through"]
        assert len(d["title"]) <= 60
        assert d["title"].endswith("Driving Tour")
        assert "." not in d["title"] and "Include" not in d["title"]

    def test_scope_box_covers_origin_and_destination(self):
        # coordinates are test inputs (the live run resolves them); the box helper is generic
        mui_ne, ta_cu = (10.9433, 108.2870), (10.7480, 107.9490)
        box = uli.bbox_covering([mui_ne, ta_cu])
        assert uli.bbox_contains(box, *mui_ne) and uli.bbox_contains(box, *ta_cu)

    def test_never_truncated_mid_word(self):
        import tour_orchestrator_service as orch
        out = orch.sanitize_input("word " * 100, max_len=47)
        assert not out.endswith("wor") and out == out.strip()
        assert all(w == "word" for w in out.split())
        full = orch.sanitize_input(REQUEST, max_len=uli.DESCRIPTION_INPUT_MAX)
        assert full.endswith("return drive to Mui Ne.")

    def test_title_has_no_description_fragment(self):
        t = uli.short_title("A very long origin venue name that goes on and on",
                            "an equally long destination mountain name", "driving")
        assert len(t) <= 60 and t.endswith("Driving Tour")
        assert not re.search(r"\b(to|and|the|of)\s+-", t)


# ── 2. the user list is the tour ────────────────────────────────────────────
class TestNamedPlaceHygiene:
    @pytest.mark.parametrize("bad", [
        "the", "a", "past dragon fruit plantations. Include the history of Phan Thiet",
        "Vietnam for the first time. The drive takes about one hour each way through Phan Thiet",
        "dragon", "and the"])
    def test_rejected(self, bad):
        assert uli.reject_named_place_candidate(bad)

    @pytest.mark.parametrize("good", ["Linh Son Truong Tho Pagoda", "Ta Cu Mountain", "Mui Ne"])
    def test_real_names_kept(self, good):
        assert not uli.reject_named_place_candidate(good)

    def test_announcement_never_names_a_fragment(self):
        from area_resolver import build_named_place_intro_sentence
        assert build_named_place_intro_sentence(["the"]) == ""
        assert "the," not in build_named_place_intro_sentence(["the", "Ta Cu Mountain"])

    def test_extractor_candidates_filtered_end_to_end(self):
        from area_resolver import extract_named_places_from_clause
        got = [n for n in extract_named_places_from_clause(REQUEST[:200])
               if not uli.reject_named_place_candidate(n)]
        assert all(not uli.reject_named_place_candidate(n) for n in got)


class TestTitles:
    def test_only_parenthetical_qualifier_is_stripped(self):
        assert uli.strip_qualifier(STOPS[3]) == "Arriving at Ta Cu \u2013 the mountain and its legends"
        assert uli.strip_qualifier("Phan Thiet and the Ca Ty River") == "Phan Thiet and the Ca Ty River"

    def test_lookup_core_for_pins(self):
        assert uli.lookup_core(STOPS[3]) == "Ta Cu Mountain"
        assert uli.lookup_core(STOPS[0]) == "Mui Ne"
        assert uli.lookup_core(STOPS[1]) == "Phan Thiet and the Ca Ty River"
        assert uli.lookup_core(STOPS[5]) == "Linh Son Truong Tho Pagoda"
        assert uli.lookup_core(STOPS[4]) == ""      # no proper noun: nothing to look up
        assert uli.lookup_core(STOPS[7]) == ""

    def test_pins_use_core_but_keep_titles(self):
        import itinerary_import as ii
        seen = {}

        def preview(text, city):
            seen["q"], seen["city"] = text.split("\n"), city
            return {"ok": True, "city": {"name": city}, "stops": [
                {"name": q, "stop_name": q, "lat": 10.9 - i * 0.01, "lng": 108.2 - i * 0.01}
                for i, q in enumerate(seen["q"])]}
        logs = []
        out, n = ii.resolve_user_stop_pins(STOPS, "Binh Thuan province", log=logs.append,
                                           preview_fn=preview, core_fn=uli.lookup_core)
        assert "Ta Cu Mountain" in seen["q"] and "Arriving at Ta Cu" not in " ".join(seen["q"])
        assert seen["city"] == "Binh Thuan province"
        assert len(seen["q"]) == 6 and n == 6            # 2 stops name no place
        assert any("pins resolved 6/6" in l for l in logs)
        # display titles keep the listener's words, in order, for all 8
        assert [re.split(r"\s+https?://", s)[0].strip() for s in out][3].startswith(
            "Arriving at Ta Cu")
        assert out[4] == STOPS[4] and out[7] == STOPS[7]


class TestTopics:
    def test_request_topics_are_extracted_generically(self):
        t = uli.request_topics(REQUEST)
        assert "how dragon fruit is grown" in t
        assert "the Cham heritage of the region" in t
        assert any("pilgrimage" in x for x in t) and any("construction" in x for x in t)

    def test_topics_route_to_matching_stops(self):
        t = uli.request_topics(REQUEST)
        assert any("pilgrimage" in x for x in uli.topics_for_stop(t, "The Reclining Buddha"))
        assert any("Phan Thiet" in x for x in
                   uli.topics_for_stop(t, "Phan Thiet and the Ca Ty River"))
        assert uli.topics_for_stop(t, "The cable car ascent") != []

    def test_support_is_reported_never_invented(self):
        sup = uli.topic_support(["the pilgrimage tradition", "its construction"],
                                ["Pilgrims climb the mountain each lunar new year."])
        assert sup["the pilgrimage tradition"] is False     # "Pilgrims" is not "pilgrimage"
        assert sup["its construction"] is False
        sup2 = uli.topic_support(["how dragon fruit is grown"], ["Dragon fruit is grown on concrete posts."])
        assert sup2["how dragon fruit is grown"] is True
        assert uli.topic_support(["the history of Phan Thiet"], ["unrelated text"]) == {
            "the history of Phan Thiet": False}

    def test_thin_stop_queries_carry_the_topics(self):
        import thin_stop_search as ts
        q = ts.name_variant_queries("Reclining Buddha", "Binh Thuan",
                                    topics=["the pilgrimage tradition", "its construction"])
        assert any("pilgrimage tradition" in x for x in q)


class TestDrivingRegister:
    def test_sensory_padding_never_says_street_or_pavement(self):
        import strict_grounding_gate as sgg
        body = sgg.sensory_body("The Reclining Buddha", [], 4, register="driving")
        txt = " ".join(body).lower()
        assert body and not re.search(r"look around you|pavement|the street|walk", txt)
        walking = " ".join(sgg.sensory_body("X", [], 4)).lower()
        assert "pavement" in walking                       # the walking default is unchanged

    def test_driving_prompt_block(self):
        blk = uli.driving_register_block("Leaving Mui Ne \u2013 the coast", [])
        assert "DRIVE SEGMENT" in blk
        stop = uli.driving_register_block("Linh Son Truong Tho Pagoda", ["the story of X"])
        assert "This is a STOP" in stop and "never invent" in stop.lower()


# ── end to end through generate_tour_text, network mocked ───────────────────
@pytest.fixture(scope="module")
def tour(tmp_path_factory):
    import socket
    import time
    import requests
    mp = pytest.MonkeyPatch()
    for k, v in dict(OPENAI_API_KEY="sk-test", DISABLE_TOUR_CACHE="1", GEMINI_API_KEY="",
                     SERPER_API_KEY="", SERP_API_KEY="",
                     DATABASE_URL="postgresql://x:y@127.0.0.1:1/z").items():
        mp.setenv(k, v)
    mp.setattr(time, "sleep", lambda *_a, **_k: None)

    def _blocked_connect(self, *a, **k):
        raise OSError("LOCAL-894 test: network blocked")
    mp.setattr(socket.socket, "connect", _blocked_connect)

    class _R:
        def __init__(s, code=200, js=None):
            s.status_code, s._js, s.headers = code, js, {}
            s.text = json.dumps(js or {})
            s.content = s.text.encode()
            s.ok = code < 400

        def json(s):
            return s._js

        def raise_for_status(s):
            if s.status_code >= 400:
                raise requests.HTTPError(str(s.status_code))

    def _chat(content):
        return _R(200, {"choices": [{"message": {"content": content}}],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})

    def fake_post(url, *a, **k):
        if "openai.com" in url:
            body = k.get("data") or json.dumps(k.get("json") or {})
            if "Analyze this tour request" in body:
                # the intent model reads the (now short) request; hand back what a model
                # would for a driving route, INCLUDING a junk named place the old code trusted
                return _chat(json.dumps({
                    "poi_type": "landmarks", "location": "Vietnam", "theme_type": "STANDARD",
                    "venue_name": None, "geographic_scope": "Phan Thiet",
                    "named_places": ["the", "past dragon fruit plantations. Include the history"],
                    "scope_precision": "CITY", "transport_mode": "vehicle"}))
            return _chat("The road runs on ahead. Fishing boats line the shore at dawn. "
                         "The hills rise slowly. Take your time.")
        raise requests.ConnectionError("blocked " + url)

    def fake_get(url, *a, **k):
        raise requests.ConnectionError("blocked " + url)
    mp.setattr(requests, "post", fake_post)
    mp.setattr(requests, "get", fake_get)
    mp.setattr(requests.Session, "request",
               lambda self, m, u, *a, **k: (_ for _ in ()).throw(requests.ConnectionError(u)))
    import generate_tour_text as g
    out = str(tmp_path_factory.mktemp("t894") / "tour.txt")
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        res = g.generate_tour_text(REQUEST, "driving", out, 8, forced_stops=list(STOPS),
                                   job_id="t894")
    mp.undo()
    return {"text": res[0] or "", "log": buf.getvalue(), "g": g}


def _titles(text):
    return [m.group(1).strip() for m in re.finditer(r"(?m)^Stop \d+:\s*(.+)$", text)]


class TestEndToEnd:
    def test_eight_stops_in_the_users_order_with_the_users_titles(self, tour):
        got = _titles(tour["text"])
        assert len(got) == 8, got
        assert got == EXPECTED_TITLES, got

    def test_no_ghost_stop_and_no_announcement(self, tour):
        low = tour["text"].lower()
        assert "could not be confirmed" not in low
        assert "one place you asked for" not in low
        for frag in ("past dragon fruit plantations.", "vietnam for the first time"):
            assert frag not in " ".join(_titles(tour["text"])).lower()

    def test_coverage_selection_did_not_run_or_reorder(self, tour):
        assert "[LOCAL-894] coverage selection skipped" in tour["log"]
        assert "[LOCAL-212] Dropped" not in tour["log"]

    def test_location_and_scope_cover_the_route(self, tour):
        m = re.search(r"\[LOCAL-894\] location is a description .*?location='([^']+)' "
                      r"scope='([^']+)'", tour["log"])
        assert m, "description was not recognised"
        assert "Mui Ne" in m.group(1) or "Ham Tien" in m.group(1)
        assert "Binh Thuan" in m.group(2)

    def test_driving_register(self, tour):
        low = tour["text"].lower()
        assert not re.search(r"look around you at the street|the pavement", low)
        assert "force-enforce not applied to a driving tour" in tour["log"].lower()

    def test_user_list_blocks_description_named_places(self, tour):
        assert "named-place insertion from the request text is OFF" in tour["log"]
        assert "verified against discovered landmark" not in tour["log"]
