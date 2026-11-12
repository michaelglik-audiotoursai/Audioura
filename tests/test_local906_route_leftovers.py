"""LOCAL-906 -- wave 51 leftovers on the route (551) and single-place (552) tours. Offline, $0, generic fixtures.

1  exclusivity claim / year + builder / out-of-scope comparative (single-place path too)
2  an AREA stop's pin lies between its neighbours
3  Directions keep wayfinding, never scenery (route and single-place)
4  Orientation "at the foot of X" after earlier stops went up X
5  a sentence already delivered in an earlier stop
6  negative first-stop tone
7  template closing filler
8  job-scoped module state (two interleaved jobs)
9  fetch selection (social hosts, off-scope pages)
+  full replay of both fixtures
"""
import os
import re
import sys
import threading

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import delivery_bodies_905 as db905  # noqa: E402
import route_content_896 as rc  # noqa: E402
import route_leftovers_906 as l906  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")
INFO = {"is_description": True, "origin": "<Resort>", "destination": "<Mountain>", "through": ["<Town>"],
        "region": "<Region>", "origin_locality": ""}


def _fx(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def _block(text, n):
    for s, e, num, _t in rc._stop_blocks(text):
        if num == n:
            return text[s:e]
    raise AssertionError(f"no stop {n}")


def _coord(text, n):
    m = re.search(r"(?m)^Coordinates:\s*(-?[\d.]+),\s*(-?[\d.]+)", _block(text, n))
    return float(m.group(1)), float(m.group(2))


@pytest.fixture
def route():
    with rc.job_scope("t906-route"):
        rc.set_route(INFO)
        l906.set_verified_stops(set())
        yield
    rc.clear_route()


@pytest.fixture
def plain():
    with rc.job_scope("t906-plain"):
        rc.clear_route()
        yield


# ── 1. unsupported claims ────────────────────────────────────────────────────
def test_exclusivity_claim_dropped_unless_in_evidence(route):
    t = _fx("local906_route_w51.txt")
    out = l906.drop_unsupported_claims(t, {}, None)
    assert "the only country" not in out
    assert "thousands of local farmers" in out                       # neighbouring sentences stay
    ev = {"<Province>, the <fruit> plantations along the road":
          "<Country> is the only country in <Region> that grows <fruit> on a commercial scale."}
    assert "the only country" in l906.drop_unsupported_claims(t, ev, None)


def test_exclusivity_cue_needs_a_geographic_noun(route):
    assert not l906.is_exclusivity_claim("It is the only road up the hill.")
    assert l906.is_exclusivity_claim("<Country> is the only country in <Region> that grows <fruit>.")
    assert l906.is_exclusivity_claim("There is no other region like it in the country.")
    assert l906.is_exclusivity_claim("<City> was the first city in <Region> to have electric light.")


def test_year_and_builder_need_the_stops_evidence(plain):
    t = _fx("local906_single_w51.txt")
    logs = []
    out = l906.drop_unsupported_claims(t, {}, logs.append)
    assert "1958" not in out and "<Person>" not in out
    assert any("year 1958 + builder not in the stop's evidence" in x for x in logs)
    ev = {"<Statue>": "Construction began in 1958 by <Person>, who also built three smaller statues."}
    kept = l906.drop_unsupported_claims(t, ev, None)
    assert "began in 1958 by <Person>" in kept
    only_year = {"<Statue>": "Construction began in 1958 by a team of monks."}
    assert "1958 by <Person>" not in l906.drop_unsupported_claims(t, only_year, None)


def test_out_of_scope_comparative_dropped_on_the_single_place_path(plain):
    """902 item 5 only ran on a described route (``active()``) and only with an evidence map; the single-place
    delivery pass had neither, so the sentence survived. ``force`` runs it there."""
    t = _fx("local906_single_w51.txt")
    assert rc.drop_unsupported_comparatives(t, {}, None) == t                    # the old behaviour: skipped
    out = rc.drop_unsupported_comparatives(t, {}, None, force=True)
    assert "larger than those at" not in out and "bigger reclining" not in out
    assert "49 meters long" in out
    logs = []
    out2 = rc.apply_single_place_guards(t, logs.append)
    assert "larger than those at" not in out2
    assert any("comparison with other places" in x for x in logs)


# ── 2. area-stop pin ─────────────────────────────────────────────────────────
def test_area_stop_pin_between_neighbours(route):
    t = _fx("local906_route_w51.txt")
    a, p, b = _coord(t, 2), _coord(t, 3), _coord(t, 4)
    tt, off, _al = l906.segment_position(p, a, b)
    assert tt < 0, "the fixture's Stop 3 pin is behind Stop 2 (east of it on a west-going route)"
    logs = []
    out = l906.repin_area_stops_in_text(t, set(), logs.append)
    p2 = _coord(out, 3)
    t2, off2, _ = l906.segment_position(p2, a, b)
    assert 0 < t2 < 1 and off2 <= l906.MAX_OFF_SEGMENT_KM
    assert _coord(out, 2) == a and _coord(out, 4) == b                           # neighbours untouched
    assert any(re.match(r"\s*\[LOCAL-906\] route area stop=3 re-pinned between neighbours \(was [\d.]+ km "
                        r"(behind|off the segment)\)", x) for x in logs), logs


def test_area_stop_already_between_is_left_and_verified_is_never_moved(route):
    t = _fx("local906_route_w51.txt")
    a, b = _coord(t, 2), _coord(t, 4)
    mid = l906._lerp(a, b, 0.4)
    ok = re.sub(r"(?m)^(Coordinates:) 10\.9150, 108\.1290", f"\\1 {mid[0]:.6f}, {mid[1]:.6f}", t)
    assert l906.repin_area_stops_in_text(ok, set(), None) == ok
    assert l906.repin_area_stops_in_text(t, {3}, None) == t                      # verified pin: untouched
    l906.set_verified_stops(None)
    assert l906.repin_area_stops_in_text(t, None, None) == t                     # no pin information: untouched


def test_off_segment_more_than_10km_is_repinned(route):
    t = _fx("local906_route_w51.txt")
    a, b = _coord(t, 2), _coord(t, 4)
    mid = l906._lerp(a, b, 0.5)
    far = re.sub(r"(?m)^(Coordinates:) 10\.9150, 108\.1290", f"\\1 {mid[0] + 0.15:.6f}, {mid[1]:.6f}", t)
    logs = []
    out = l906.repin_area_stops_in_text(far, set(), logs.append)
    _t, off, _ = l906.segment_position(_coord(out, 3), a, b)
    assert off < 0.5 and any("off the segment" in x for x in logs)


def test_area_detection_and_poi_level_repin(route):
    assert l906.is_area_stop("<Province>, the <fruit> plantations", "Agricultural area")
    assert not l906.is_area_stop("<Pagoda A>", "Buddhist temple")
    assert not l906.is_area_stop("The cable car ascent", "Cable car experience")
    pois = [{"name": "A", "coordinates": "10.9281, 108.1002", "type_specialty": "City"},
            {"name": "<Province> farmland", "coordinates": "10.9150, 108.1290", "type_specialty": "Agricultural area"},
            {"name": "B", "coordinates": "10.813277, 107.894085", "type_specialty": "Mountain"}]
    logs = []
    assert l906.repin_area_stops(pois, set(), logs.append) == 1
    assert pois[1]["coordinates_approximate"] is True
    assert any("route area stop=2 re-pinned between neighbours" in x for x in logs)
    pois2 = [dict(p) for p in pois]
    pois2[1]["coordinates"] = "10.9150, 108.1290"
    pois2[1]["wikidata_lat"], pois2[1]["wikidata_lng"] = 10.915, 108.129    # verified: never moved
    assert l906.repin_area_stops(pois2, set(), None) == 0


# ── 3. Directions without scenery ────────────────────────────────────────────
def test_directions_drop_scenery_on_the_route(route):
    t = _fx("local906_route_w51.txt")
    out = rc.normalize_directions(t, None)
    d2 = re.search(r"(?m)^Directions:.*$", _block(out, 2)).group(0)
    assert d2.startswith("Directions: Continue to ") and "km away." in d2
    assert "hues" not in d2 and "landscape" not in d2
    d6 = re.search(r"(?m)^Directions:.*$", _block(out, 6)).group(0)
    assert d6.startswith("Directions: Walk on to") and "landscape" not in d6 and "stretches" not in d6


def test_directions_keep_one_wayfinding_sentence():
    assert rc._wayfinding_clause("Turn left at the junction. The view is lovely.") == "Turn left at the junction."
    assert rc._wayfinding_clause("Take the stairs beside the bridge.") == "Take the stairs beside the bridge."
    assert rc._wayfinding_clause("The bright pink hues are striking against the landscape.") is None
    assert rc._wayfinding_clause("The expansive landscape stretches out before you.") is None
    assert rc._wayfinding_clause("Look for the gate. The views are great!") == "Look for the gate."
    assert rc._wayfinding_clause("Head north for 5 km.") is None


def test_directions_without_scenery_on_the_single_place_path(plain):
    t = _fx("local906_single_w51.txt").replace(
        "Directions: Walk on to <Statue>.",
        "Directions: Walk on to <Statue>. The expansive landscape stretches out before you.")
    out = rc.apply_single_place_guards(t, None)
    d1 = re.search(r"(?m)^Directions:.*$", _block(out, 1)).group(0)
    assert d1 == "Directions: Walk on to <Statue>."


# ── 4. orientation vs. stop order ────────────────────────────────────────────
def test_orientation_at_the_foot_after_an_ascent_is_dropped(route):
    t = _fx("local906_route_w51.txt")
    logs = []
    out = l906.drop_contradicting_orientation(t, logs.append)
    assert "foot of" not in out and "Orientation:" not in _block(out, 7)
    assert "49 meters long" in _block(out, 7)
    assert any("Stop 7" in x and "foot / base" in x for x in logs)


def test_orientation_kept_when_nothing_went_up_first(route):
    t = _fx("local906_route_w51.txt")
    t = re.sub(r"(?m)^Orientation:.*\n\n", "", t)                     # Stop 7's own contradicting Orientation
    # the same sentence on Stop 2: no earlier stop ascended anything named <Mountain>
    moved = t.replace("Type/Specialty: City and river\n",
                      "Type/Specialty: City and river\n\nOrientation: Arrive at the foot of <Mountain> here.\n", 1)
    assert l906.drop_contradicting_orientation(moved, None) == moved


# ── 5. repeated sentence ─────────────────────────────────────────────────────
def test_repeated_sentence_dropped_from_the_later_stop(route):
    t = _fx("local906_route_w51.txt")
    sent = "You can reach the top of <Mountain> by two ways, including a modern cable car ride."
    assert _block(t, 4).count(sent) == 1 and _block(t, 5).count(sent) == 1
    logs = []
    out = l906.drop_repeated_sentences(t, logs.append)
    assert sent in _block(out, 4) and sent not in _block(out, 5)
    assert "The cable car climbs through the forest" in _block(out, 5)
    assert any("Stop 5" in x and "already delivered" in x for x in logs)


def test_near_duplicate_counts_and_a_stop_is_never_emptied(route):
    t = _fx("local906_route_w51.txt")
    near = t.replace("You can reach the top of <Mountain> by two ways, including a modern cable car ride. The cable car"
                     " climbs", "You can reach the top of <Mountain> by two ways, including a modern cable car ride!"
                     " The cable car climbs")
    o_near = l906.drop_repeated_sentences(near, None)
    assert "modern cable car ride!" not in o_near and "The cable car climbs through the forest" in o_near
    single = ("X\nTour-Category: driving\n\nStop 1: A\n\nCoordinates: 1, 1\n\nThe river runs past the old mill "
              "and under the bridge.\n\nStop 2: B\n\nCoordinates: 1, 2\n\nThe river runs past the old mill and "
              "under the bridge.\n\nThat's 2 stops in all.\n")
    out = l906.drop_repeated_sentences(single, None)
    assert out.count("The river runs past the old mill") == 2          # would empty Stop 2: left for 905's floor
    assert l906.is_repeat("The river runs past the old mill and under the bridge!",
                          [l906._tok("The river runs past the old mill and under the bridge.")])


# ── 6. negative opening tone ─────────────────────────────────────────────────
def test_pollution_sentence_dropped_from_the_first_stop_of_a_leisure_tour(route):
    t = _fx("local906_route_w51.txt")
    logs = []
    out = l906.tone_first_stop(t, None, logs.append)
    assert "pollution" not in out and "trash" not in out
    assert "known for its <Ward> Market" in _block(out, 1) and "officially established in 1999" in _block(out, 1)
    assert any("Stop 1" in x and "leisure tour" in x for x in logs)


def test_negative_sentence_kept_when_it_is_the_stops_story(route):
    t = _fx("local906_route_w51.txt")
    hist = t.replace("The beach here has faced pollution challenges, with trash sometimes washing ashore.",
                     "The great flood disaster of 1952 destroyed the old market.")
    assert l906.tone_first_stop(hist, None, None) == hist                         # a historic event
    sig = {"<Ward> and the <Beach> strip": "Fishermen recall how trash and pollution washing ashore each spring "
                                           "forced the beach cleanup that now defines the ward."}
    assert "pollution" in l906.tone_first_stop(t, sig, None)                      # part of the signature story


def test_negative_opening_moved_after_the_first_positive_sentence_off_a_leisure_tour():
    txt = ("X\nTour-Category: museum\n\nStop 1: A\n\nCoordinates: 1, 1\n\nThe beach here has faced pollution "
           "challenges, with trash washing ashore. The square is known for its market and its fountain.\n\n"
           "Stop 2: B\n\nCoordinates: 1, 2\n\nA quiet lane.\n\nThat's 2 stops in all.\n")
    out = l906.tone_first_stop(txt, None, None)
    body = _block(out, 1).strip().split("\n\n")[-1]
    assert body.startswith("The square is known") and body.rstrip().endswith("washing ashore.")


# ── 7. template closing ──────────────────────────────────────────────────────
def test_template_closing_filler_dropped_keeps_count_and_offer(plain):
    t = _fx("local906_single_w51.txt")
    out = l906.drop_template_closing(t, None)
    assert "one thread runs through" not in out and "add up to more than" not in out
    assert out.rstrip().endswith("That's 2 stops in all.")
    t2 = t.replace("That's 2 stops in all.", "That's 2 stops in all. If you would like to eat nearby, just ask.")
    o2 = l906.drop_template_closing(t2, None)
    assert "That's 2 stops in all." in o2 and "If you would like to eat nearby" in o2


# ── 8. job-scoped module state ───────────────────────────────────────────────
def test_two_interleaved_jobs_do_not_share_route_or_evidence_state():
    a_set, b_set, a_read, b_read = threading.Event(), threading.Event(), threading.Event(), threading.Event()
    seen = {}

    def job_a():
        with rc.job_scope("job-A"):
            rc.set_route({"is_description": True, "origin": "Alpha Lodge", "destination": "Gamma Peak",
                          "through": [], "region": "", "origin_locality": ""})
            rc.set_evidence_904({"Stop A": "evidence of A"})
            rc._HONEST_DONE.add("honest-a")
            a_set.set()
            b_set.wait(5)                                 # B has now written ITS state
            seen["a"] = (rc.endpoints(), dict(rc._EVIDENCE_904), "honest-a" in rc._HONEST_DONE,
                         "honest-b" in rc._HONEST_DONE)
            a_read.set()
            b_read.wait(5)

    def job_b():
        a_set.wait(5)
        with rc.job_scope("job-B"):
            assert not rc.active() and dict(rc._EVIDENCE_904) == {}           # A's state is invisible here
            rc.set_route({"is_description": True, "origin": "Beta Inn", "destination": "Delta Cape",
                          "through": [], "region": "", "origin_locality": ""})
            rc.set_evidence_904({"Stop B": "evidence of B"})
            rc._HONEST_DONE.add("honest-b")
            b_set.set()
            a_read.wait(5)
            seen["b"] = (rc.endpoints(), dict(rc._EVIDENCE_904), "honest-b" in rc._HONEST_DONE,
                         "honest-a" in rc._HONEST_DONE)
            b_read.set()

    ta, tb = threading.Thread(target=job_a), threading.Thread(target=job_b)
    ta.start(); tb.start(); ta.join(10); tb.join(10)
    assert seen["a"] == (("Alpha Lodge", "Gamma Peak"), {"Stop A": "evidence of A"}, True, False)
    assert seen["b"] == (("Beta Inn", "Delta Cape"), {"Stop B": "evidence of B"}, True, False)
    # cleared at job end: nothing of either job is left in the default slot or under their ids
    assert not rc.active() and dict(rc._EVIDENCE_904) == {}
    with rc.job_scope("job-A"):
        assert not rc.active() and dict(rc._EVIDENCE_904) == {}


def test_ensure_bodies_reads_the_evidence_of_its_own_job():
    txt = ("X\n\nStop 1: Alpha Hall\n\nCoordinates: 1, 1\n\nType/Specialty: Hall\n\nDirections: Walk on to the next.\n\n"
           "Stop 2: Beta Hall\n\nCoordinates: 1, 2\n\nA quiet lane runs past it today.\n\nThat's 2 stops in all.\n")
    sent = "Alpha Hall was opened to visitors in the nineteenth century and still holds its original floor."
    with rc.job_scope("ev-A"):
        rc.set_evidence_904({"Alpha Hall": sent})
        with rc.job_scope("ev-B"):
            rc.set_evidence_904({"Alpha Hall": "Something else entirely about another hall far away from here."})
            out_b = db905.ensure_bodies(txt, None, None)
        out_a = db905.ensure_bodies(txt, None, None)
    assert sent in out_a and sent not in out_b


def test_nested_scope_of_the_same_job_keeps_the_state():
    with rc.job_scope("nest"):
        rc.set_evidence_904({"A": "x"})
        with rc.job_scope("nest"):
            assert dict(rc._EVIDENCE_904) == {"A": "x"}
        assert dict(rc._EVIDENCE_904) == {"A": "x"}                 # the inner exit did not clear the outer job
    with rc.job_scope("nest"):
        assert dict(rc._EVIDENCE_904) == {}


def test_job_scoped_decorator_binds_the_jobs_id():
    @rc.job_scoped
    def gen(location, job_id=None):
        rc.set_evidence_904({"k": str(job_id)})
        return rc._current_job(), dict(rc._EVIDENCE_904)

    assert gen("x", job_id="J1") == ("J1", {"k": "J1"})
    with rc.job_scope("J1"):
        assert dict(rc._EVIDENCE_904) == {}                         # cleared when the call ended


# ── 9. fetch selection ───────────────────────────────────────────────────────
def test_fetch_skips_social_hosts_and_off_scope_pages(monkeypatch, capsys):
    import story_first
    fetched = []
    pages = {
        "https://example.org/a": "<Mountain> cable car guide. The mountain has two pagodas and a statue on top.",
        "https://blog.example.net/b": "Best pizza recipes of the year. Flour, water and yeast for a great dough.",
    }

    def fake(url, timeout=None):
        fetched.append(url)
        return {"url": url, "text": pages[url], "success": True, "elapsed_ms": 1.0}
    monkeypatch.setattr(story_first, "_fetch_single_page", fake)
    urls = ["https://www.facebook.com/p/1", "https://youtube.com/watch?v=1", "https://x.com/a/1",
            "https://m.tiktok.com/v", "https://www.instagram.com/p/2", "https://twitter.com/a",
            "https://example.org/a", "https://blog.example.net/b"]
    scope = story_first._scope_tokens_906("<Mountain> cable car", "<City>")
    out = story_first.fetch_full_pages(urls, budget_seconds=10, scope_tokens=scope)
    log = capsys.readouterr().out
    assert sorted(fetched) == ["https://blog.example.net/b", "https://example.org/a"]          # social never fetched
    for host in ("facebook.com", "youtube.com", "x.com", "m.tiktok.com", "instagram.com", "twitter.com"):
        assert f"[LOCAL-906] fetch skipped {host}: social/video host" in log
    assert "[LOCAL-906] fetch skipped blog.example.net: title/first paragraph shares no token" in log
    ok = [r for r in out if r["success"]]
    assert [r["url"] for r in ok] == ["https://example.org/a"]
    assert not story_first.is_social_host_906("https://box.com/x") and story_first.is_social_host_906("https://x.com/y")


# ── full replay ──────────────────────────────────────────────────────────────
def _count(text):
    return len(re.findall(r"(?m)^Stop \d+:", text))


def _no_empty_stop(text):
    last = _count(text)
    for s, e, num, _t in rc._stop_blocks(text):
        blk = text[s:e].split("\n")
        prose = [x for i, x in enumerate(blk) if i > 0 and x.strip() and not rc._KEYED.match(x)
                 and not rc._CLOSING_LINE.match(x.strip())]
        assert prose, f"stop {num} has no body"


def test_replay_route_fixture(route):
    t = _fx("local906_route_w51.txt")
    logs = []
    out = rc.finalize_898(t, None, logs.append)
    out = rc.apply_single_place_guards(out, logs.append)
    out = db905.ensure_bodies(out, None, logs.append)
    assert "the only country" not in out                                                      # 1
    a, b = _coord(out, 2), _coord(out, 4)
    tt, off, _ = l906.segment_position(_coord(out, 3), a, b)                                  # 2
    assert 0 < tt < 1 and off <= 10
    for n in range(1, 8):                                                                     # 3
        d = re.search(r"(?m)^Directions:.*$", _block(out, n)).group(0)
        assert not re.search(r"hues|landscape|stretches|striking", d), d
    assert "foot of" not in out                                                               # 4
    sent = "You can reach the top of <Mountain> by two ways"                                  # 5
    assert out.count(sent) == 1
    assert "pollution" not in _block(out, 1) and "trash" not in out                           # 6
    assert re.search(r"That's 8 stops in all\.", out) and _count(out) == 8
    _no_empty_stop(out)
    assert len(rc._stop_blocks(out)) == 8
    assert any("route area stop=3 re-pinned" in x for x in logs)
    # the Directions distances are measured from the FINAL pins (Stop 3 moved before they were built)
    d2 = re.search(r"(?m)^Directions:.*$", _block(out, 2)).group(0)
    d3 = re.search(r"(?m)^Directions:.*$", _block(out, 3)).group(0)
    assert "3.5 km" not in d2 and "28.0 km" not in d3
    km23 = rc._km(_coord(out, 2), _coord(out, 3))
    assert f"{km23:.1f} km away" in d2


def test_replay_single_fixture(plain):
    t = _fx("local906_single_w51.txt")
    logs = []
    out = rc.finalize_898(t, None, logs.append)
    out = rc.apply_single_place_guards(out, logs.append)
    out = db905.ensure_bodies(out, None, logs.append)
    assert "larger than those at" not in out and "bigger reclining" not in out                # 1c
    assert "1958" not in out and "<Person>" not in out                                        # 1b
    assert "one thread runs through" not in out and "add up to more than" not in out          # 7
    assert re.search(r"That's 2 stops in all\.", out) and _count(out) == 2
    assert "49 meters long" in _block(out, 2)
    assert re.search(r"(?m)^Directions: Walk on to <Statue>\.$", _block(out, 1))              # 3
    _no_empty_stop(out)
