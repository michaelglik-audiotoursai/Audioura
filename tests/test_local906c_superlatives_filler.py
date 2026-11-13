"""LOCAL-906C -- wave 52 leftovers. Offline, $0, generic fixtures (D769), no network, no key (stubbed everywhere).

1  an exclusivity claim the stop's evidence lacks is dropped on EVERY path (route, single-place, any other tour)
2  a regional superlative needs evidence for the SAME or a WIDER scope; the narrower supported sentence is used
3  the within-stop duplicate keeps the supported claim (route and single-place)
4  no two stops share a filler body: (a) neighbour evidence, (b) kind variant, (c) merge + recount
5  the salvage ignores HTML markers (neither kept nor counted nor logged)
6  "You see the X here is ..." (cause: the clause splitter ate the connector) is fixed
+  full replay of both wave-52 shapes
"""
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("OPENAI_API_KEY", None)
os.environ["THIN_STOP_SEARCH"] = "0"

import delivery_bodies_905 as db905  # noqa: E402
import leftovers_906c as c906c  # noqa: E402
import route_content_896 as rc  # noqa: E402
import route_leftovers_906 as l906  # noqa: E402
import tour_conclusion as tc  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")
INFO = {"is_description": True, "origin": "<Resort>", "destination": "<Mountain>", "through": ["<Town>"],
        "region": "<Region>", "origin_locality": ""}
MARKER = "<!-- LOCAL-628:stop-editor:v1 -->"
T_PROV = "<Province>, the <fruit> plantations along the road"
CLAIM = "<Country> is the only country in <Region> to grow <fruit> on a commercial scale."
LONGEST = "This statue is also the longest reclining Buddha in <Region>."
LARGEST = "It is the largest reclining Buddha statue in <Country>."
EV_STATUE = {"<Statue>": "The statue is the largest reclining Buddha statue in <Country>. "
                         "It measures 49 meters in length and 7 meters in height."}
NO_LLM = lambda *a, **k: None  # noqa: E731


def _fx(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def _bodies(text):
    out = {}
    for s, e, num, _t in rc._stop_blocks(text):
        lines = text[s:e].split("\n")
        out[num] = " ".join(ln for i, ln in enumerate(lines) if i > 0 and ln.strip() and not rc._KEYED.match(ln)
                            and not ln.startswith("<!--") and not rc._CLOSING_LINE.match(ln.strip())
                            and not ln.startswith("From <Resort>"))
    return out


@pytest.fixture
def route():
    with rc.job_scope("t906c-route"):
        rc.set_route(INFO)
        l906.set_verified_stops(set())
        rc.set_evidence_904({})
        yield
    rc.clear_route()


@pytest.fixture
def plain():
    with rc.job_scope("t906c-plain"):
        rc.clear_route()
        rc.set_evidence_904({})
        yield


def _route_tour():
    return _fx("local906c_route_w52.txt")


def _single_tour():
    return _fx("local906c_single_w52.txt")


# ── 1. why item 1 survived, and the fix ──────────────────────────────────────────────────────────────────
def test_item1_route_path_calls_the_claim_guard_with_the_stops_evidence(route):
    """finalize_898 -> content_pass -> drop_unsupported_claims reads the evidence stash (the generator hands it over
    with set_evidence_904): evidence that lacks the claim -> dropped; evidence that holds it -> kept."""
    t = _route_tour()
    for ev, kept in (({T_PROV: "The orchards grow in a dry climate."}, False), ({}, False),
                     ({T_PROV: CLAIM.replace(" to grow", " that grows")}, True)):
        rc.set_evidence_904(ev)
        out = rc.finalize_898(t, None, None)                    # the delivery call passes None: the stash decides
        assert ("only country" in out) is kept, (ev, out)
    rc.set_evidence_904({})
    logs = []
    out = rc.finalize_898(t, {T_PROV: "The orchards grow in a dry climate."}, logs.append)   # the post-pass call
    assert "only country" not in out
    assert any(x.startswith("  [LOCAL-906C] Stop 2: superlative scope unsupported:") for x in logs), logs


def test_item1_the_claim_is_dropped_on_every_path_when_the_evidence_lacks_it(route):
    ev = {T_PROV: "The orchards grow in a dry climate.", "<Mountain>": "A volcano near the coast."}
    t = _route_tour()
    # route delivery text pass, and the 905 final pass (runs on every path, scope-gate free)
    rc.set_evidence_904(ev)
    assert "only country" not in l906.content_pass(t, None, None)
    assert "only country" not in db905.ensure_bodies(t, log=None)
    assert "only country" not in c906c.final_pass(t, ev, None)
    # a plain multi-stop walking tour (not a route, > 2 stops): the old 906 gate skipped it
    rc.clear_route()
    assert "only country" not in c906c.final_pass(t, ev, None)
    assert "only country" not in db905.ensure_bodies(t, log=None)


def test_item1_single_place_path(plain):
    s = ("Alpha - Walking Tour\n\nStop 1: <Statue>\n\nCoordinates: 1.0, 2.0\n\nType/Specialty: Statue\n\n"
         "The statue stands on a hill. " + CLAIM + " Visitors come all year.\n\nThat's 1 stop in all.\n")
    assert CLAIM not in rc.apply_single_place_guards(s, None, evidence_by_title={"<Statue>": "A statue on a hill."})
    keep = rc.apply_single_place_guards(s, None, evidence_by_title={"<Statue>": CLAIM.replace(" to grow", " that grows")})
    assert CLAIM in keep


def test_item1_evidence_with_a_different_scope_does_not_back_the_claim(route):
    other = "<Country B> is the only country in <Region B> that grows <fruit> on a commercial scale."
    out = l906.drop_unsupported_claims(_route_tour(), {T_PROV: other}, None)
    assert "only country" not in out and "thousands of local farmers" in out        # neighbours stay


def test_item1_no_evidence_map_on_an_ordinary_tour_is_left_alone(plain):
    """Nothing to judge by (no evidence handed in) on a non-route multi-stop tour: unchanged, not a blanket drop."""
    t = _route_tour()
    assert c906c.drop_unsupported_scope_claims(t, None, None) == t


# ── 2. scope-matched superlatives ────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("claim,ev,verdict", [
    (LONGEST, "It is the largest reclining Buddha statue in <Country>.", "bad"),            # wider scope AND other measure
    ("It is the longest reclining Buddha in <Region>.", "It is the longest reclining Buddha in <Country>.", "bad"),
    ("It is the longest reclining Buddha in <Country>.", "It is the longest reclining Buddha in <Region>.", "ok"),
    ("It is the longest reclining Buddha in <Region>.", "It is the longest reclining Buddha in <Region>.", "ok"),
    ("It is the longest reclining Buddha in <Region>.", "It is the longest reclining Buddha in the world.", "ok"),
    ("It is the tallest tower in Alpha Land.", "It is the tallest tower in Beta Land.", "bad"),     # unknown names: exact
    ("It is the tallest tower in Alpha Land.", "It is the tallest tower in Alpha Land.", "ok"),
    ("It is the oldest temple in <Province>.", "", "bad"),                                          # no evidence
    ("It is one of the largest statues in <Region>.", "", "na"),                                    # hedged
    ("It is the largest statue in <Statue Park>.", "", "na"),                                       # the stop's own place
    ("Wood is the first material mentioned here.", "", "na"),                                        # no area
    ("<Country> is the sole producer of <fruit> in <Region>.", "", "bad"),
    ("There is no other temple in <City> like it.", "", "bad"),
])
def test_item2_scope_verdicts(claim, ev, verdict):
    assert c906c.check_claim(claim, ev, "<Statue Park>")[0] == verdict


def test_item2_unsupported_claim_is_dropped_and_logged_on_route_and_single_place(route, plain):
    for mode in ("route", "single"):
        with rc.job_scope("t906c-" + mode):
            if mode == "route":
                rc.set_route(INFO)
            else:
                rc.clear_route()
            logs = []
            t = _single_tour().replace(LARGEST + " ", "")
            out = c906c.drop_unsupported_scope_claims(t, {"<Statue>": "The statue lies on a terrace."}, logs.append)
            assert LONGEST not in out and "49 meters long" in out
            assert logs == [f'  [LOCAL-906C] Stop 2: superlative scope unsupported: "{LONGEST[:80]}"'], logs


def test_item2_a_supported_narrower_version_replaces_the_unsupported_claim(plain):
    t = _single_tour().replace(LARGEST + " ", "")           # only the wide, false claim is in the text
    logs = []
    out = c906c.drop_unsupported_scope_claims(t, EV_STATUE, logs.append)
    assert LONGEST not in out
    assert "The statue is the largest reclining Buddha statue in <Country>." in out
    assert any("narrower supported version used" in x for x in logs)
    # the narrower sentence is already there: the false one is just dropped, nothing is added twice
    out2 = c906c.drop_unsupported_scope_claims(_single_tour(), EV_STATUE, None)
    assert LONGEST not in out2 and out2.count("largest reclining Buddha statue in <Country>") == 1


# ── 3. the within-stop duplicate keeps the supported claim ───────────────────────────────────────────────
def _dup_block(first, second):
    return ("Stop 1: <Statue>\n\nCoordinates: 1.0, 2.0\n\nType/Specialty: Statue\n\n"
            f"The statue lies on a terrace. {first} {second} Visitors come all year.\n\nThat's 1 stop in all.\n")


@pytest.mark.parametrize("order", ["wide-first", "narrow-first"])
def test_item3_dedup_keeps_the_supported_narrower_claim(plain, order):
    a, b = (LONGEST, LARGEST) if order == "wide-first" else (LARGEST, LONGEST)
    assert rc.same_fact(a, b, "<Statue>")                    # the premise: the 906B guard treats them as one fact
    logs = []
    out = rc.drop_within_stop_duplicates(_dup_block(a, b), logs.append, EV_STATUE)
    assert LARGEST in out and LONGEST not in out
    assert any('dropped "' + LONGEST[:60] in x for x in logs), logs
    # with the stop's evidence stashed (the delivery call) it is the same
    rc.set_evidence_904(EV_STATUE)
    assert LONGEST not in rc.drop_within_stop_duplicates(_dup_block(a, b), None)


def test_item3_dedup_on_the_route_path(route):
    rc.set_evidence_904(EV_STATUE)
    t = _dup_block(LONGEST, LARGEST).replace("<Statue>", "<Statue>", 1)
    out = rc.drop_within_stop_duplicates(t, None)
    assert LARGEST in out and LONGEST not in out


def test_item3_both_wide_the_narrower_scope_stays_and_specificity_decides_otherwise(plain):
    a, b = "It is the largest reclining Buddha statue in <Region>.", "It is the largest reclining Buddha statue in <Country>."
    out = rc.drop_within_stop_duplicates(_dup_block(a, b), None, {})
    assert b in out and a not in out
    # no scoped claim at all: 906B specificity as before
    x, y = "The statue is 49 meters long.", "The statue is about 49 meters long and 7 meters high in 1958."
    out2 = rc.drop_within_stop_duplicates(_dup_block(x, y), None, {})
    assert y in out2 and x not in out2


def test_item3_a_ranking_claim_and_a_measurement_are_two_facts(plain):
    plain_s = "You see the reclining Buddha statue here, a statue of 49 meters long and 7 meters high."
    out = rc.drop_within_stop_duplicates(_dup_block(plain_s, LARGEST), None, EV_STATUE)
    assert LARGEST in out and plain_s in out


# ── 4. no two stops share a filler body ──────────────────────────────────────────────────────────────────
DISC = "We could not confirm verified historical details for this stop"
STUB_EV = {"The cable car ascent": "A short path from the upper station leads to the lookout, where a small shrine stands."}


def _same_bodies(text):
    b = [c906c._toks_of(i["sents"], i["title"]) for i in c906c._stops_info(text)]
    return [(i + 1, j + 1) for i in range(len(b)) for j in range(i + 1, len(b)) if c906c._same_body(b[i], b[j])]


def test_item4_premise_stops_5_and_7_have_the_same_filler_body():
    assert _same_bodies(_route_tour()) == [(5, 7)]


def test_item4_branch_a_unused_neighbour_evidence_that_fits_the_title(route):
    logs = []
    out = c906c.distinct_filler_bodies(_route_tour(), STUB_EV, logs.append)
    assert _same_bodies(out) == []
    assert "short path from the upper station leads to the lookout" in _bodies(out)[7] and "short path from the upper station leads to the lookout" not in _bodies(out)[5]
    assert any("branch (a)" in x and "Stop 7" in x for x in logs), logs
    assert out.count("That's 7 stops in all.") == 1 and out.count(MARKER) == 1       # marker untouched, count kept


def test_item4_branch_b_a_variant_keyed_to_the_kind(route):
    logs = []
    out = c906c.distinct_filler_bodies(_route_tour(), {}, logs.append)
    assert _same_bodies(out) == []
    assert any("branch (b)" in x and "'view'" in x for x in logs), logs
    assert _bodies(out)[7].startswith("From the lookout, let your eyes travel")


def test_item4_branch_b_no_two_stops_get_the_same_variant(route):
    """Four view-like stops with filler bodies: each gets a different variant."""
    stops = []
    for i, t in enumerate(["The summit views", "The overlook", "The lookout", "The panorama point"], 1):
        stops.append(f"Stop {i}: {t}\n\nCoordinates: 1.0, 2.0\n\nType/Specialty: Viewpoint\n\n"
                     f"At the place, look out at the view and notice how far the land opens below you. "
                     f"Feel the height and the cooler, thinner air, and listen for the wind. {DISC}, so this part of the "
                     f"tour focuses on what you can see and sense here rather than on dates or events.\n\n"
                     + (f"Directions: Walk on.\n\n" if i < 4 else "That's 4 stops in all.\n"))
    out = c906c.distinct_filler_bodies("Tour\n\n" + "".join(stops), {}, None)
    assert _same_bodies(out) == []
    bodies = list(_bodies(out).values())
    assert len(set(bodies)) == 4


def test_item4_branch_c_merge_into_the_previous_stop_and_recount(route, monkeypatch):
    monkeypatch.setattr(c906c, "FILLER_VARIANTS", {})
    logs = []
    out = c906c.distinct_filler_bodies(_route_tour(), {}, logs.append)
    heads = re.findall(r"(?m)^Stop (\d+): (.+)$", out)
    assert [h[0] for h in heads] == ["1", "2", "3", "4", "5", "6"], heads         # renumbered
    assert "The lookout" not in out.split("Stop 6:")[0]                            # header dropped
    assert any("branch (c)" in x and "merged into Stop 6" in x for x in logs), logs
    assert "That's 6 stops in all." in out and "That's 7" not in out               # recount = delivered stops
    assert out.count(MARKER) == 1
    # the merged (last) stop's closing survives, and the previous stop's Directions to the removed stop is gone
    assert "this route is the one you chose" in out and "Walk on to the lookout" not in out


def test_item4_branch_c_middle_stop_keeps_its_directions(route, monkeypatch):
    monkeypatch.setattr(c906c, "FILLER_VARIANTS", {})
    t = _route_tour()
    # make Stops 4 and 5 share the filler body instead (Stop 5 is a middle stop with Directions)
    b = _bodies(t)
    t = t.replace(b[7], "The lookout has a railing, a bench and a small shrine.")      # Stop 7 is no filler now
    t = t.replace(b[4], b[5])                                                      # Stop 4 repeats Stop 5's body
    out = c906c.distinct_filler_bodies(t, {}, None)
    assert _same_bodies(out) == []
    assert out.count("Directions: Walk on to the terrace.") == 1 and out.count("Walk on to the summit views.") == 0
    assert len(re.findall(r"(?m)^Stop \d+:", out)) == 6 and "That's 6 stops in all." in out and "Stop 5: The summit views" not in out and "Stop 4: The cable car ascent" in out


def test_item4_the_905_floor_does_not_leave_an_identical_body_twice(route):
    logs = []
    out = db905.ensure_bodies(_route_tour(), log=logs.append)
    assert _same_bodies(out) == [], out


def test_item4_a_non_filler_repeat_is_not_touched(route):
    t = _route_tour().replace(_bodies(_route_tour())[7], "The lookout has a railing, a bench and a small shrine.")
    assert c906c.distinct_filler_bodies(t, {}, None) == t


# ── 5. the salvage ignores markers ───────────────────────────────────────────────────────────────────────
FACTS = ["The reclining Buddha statue measures 49 meters in length and 7 meters in height.",
         "Construction of the statue began in 1958 under a monk."]


def test_item5_salvage_after_count_skips_markers():
    cut = ("That's 2 stops in all.\n\nIf you would like to eat nearby we can build you a restaurant tour. "
           + " ".join(FACTS) + "\n" + MARKER + "\n")
    keep, gone = tc._salvage_after_count(cut, ["Alpha Mountain"])
    assert keep == FACTS and not any("<!--" in x or "LOCAL-628" in x for x in keep + gone), (keep, gone)
    k2, g2 = tc._salvage_after_count("That's 2 stops in all. " + MARKER + "\n", [])
    assert k2 == [] and not any("LOCAL-628" in x for x in g2)


def test_item5_rebuild_conclusion_no_marker_in_the_logs_and_the_marker_stays_last():
    t = ("Alpha - Walking Tour\n\nStop 1: Alpha Mountain\n\nCoordinates: 1.0, 2.0\n\nType/Specialty: Mountain\n\n"
         "The mountain rises above the plain and is reached by a cable car.\n\nDirections: Walk on to Beta Statue.\n\n"
         "Stop 2: Beta Statue\n\nCoordinates: 1.0, 2.0\n\nType/Specialty: Statue\n\n"
         "The statue lies on a terrace.\n\nThat's 2 stops in all.\n\n"
         "If you would like to eat nearby we can build you a restaurant tour. " + FACTS[0] + "\n" + MARKER + "\n")
    logs = []
    out = tc.rebuild_conclusion(t, venue_name="V", log=logs.append)
    assert not any("<!--" in x or "LOCAL-628" in x or "stop-editor" in x for x in logs), logs
    assert FACTS[0] in out and out.index(FACTS[0]) < out.index("That's 2 stops in all.")
    assert out.count(MARKER) == 1 and out.rstrip().endswith(MARKER)                 # where it was: the end
    assert not any(MARKER in x for x in re.findall(r"[^.!?]*[.!?]", out.split(MARKER)[0]))   # in no sentence
    assert any('[LOCAL-906B] Stop 2: kept "' + FACTS[0][:60] in x for x in logs)
    # idempotent and no marker in a body
    assert tc.rebuild_conclusion(out, venue_name="V").count(MARKER) == 1


# ── 6. "You see the X here is ..." ────────────────────────────────────────────────────────────────────
def test_item6_cause_the_clause_cut_ate_the_connector(route):
    """cap_unsupported_numbers split at ", which" / ", and" and re-joined the good parts with a bare space."""
    s = ("Stop 1: <Statue>\n\nCoordinates: 1.0, 2.0\n\nType/Specialty: Statue\n\n"
         "You see the reclining Buddha statue here, which is 49 meters long and 7 meters high, and stands 11 meters wide "
         "on the terrace. The statue lies near the summit.\n\nThat's 1 stop in all.\n")
    logs = []
    out = rc.cap_unsupported_numbers(s, {"<Statue>": "The statue is 49 meters long and 7 meters high."}, logs.append)
    assert "You see the reclining Buddha statue here, which is 49 meters long and 7 meters high." in out
    assert "here is" not in out
    # the old shape: each kept clause keeps its own connector; a cut clause takes only itself with it
    rx = re.compile(r"(?i),\s*(?:and|but|which)\s+|;\s*")
    parts, seps = rc._split_clauses("A thing, which is big, and is red; blue", rx)
    assert rc._join_kept_clauses(parts, seps, lambda p: "red" in p or p == "blue") == "A thing, which is big"
    # a clause after a cut one stays only when it can stand alone (a subject, joined by "and")
    parts, seps = rc._split_clauses("The pagoda sits 475 meters up, and you can reach it by cable car", rx)
    assert rc._join_kept_clauses(parts, seps, lambda p: "475" in p) == "you can reach it by cable car"
    parts, seps = rc._split_clauses("The statue sits here, which is 49 meters long", rx)
    assert rc._join_kept_clauses(parts, seps, lambda p: "statue" in p) == ""


def test_item6_cause_the_fact_cap_too(route):
    s = ("Stop 1: <Statue>\n\nCoordinates: 1.0, 2.0\n\nType/Specialty: Statue\n\n"
         "You see the reclining Buddha statue here, which is a famous landmark, and was built in 1963 by sculptor Tau Upsilon. "
         "The statue lies near the summit.\n\nThat's 1 stop in all.\n")
    out = rc.cap_unsupported_facts(s, {"<Statue>": "A famous landmark."}, None)
    assert "You see the reclining Buddha statue here, which is a famous landmark." in out and "here is" not in out


@pytest.mark.parametrize("bad,good", [
    ("You see the reclining Buddha statue here is 49 meters long and 7 meters high.",
     "You see the reclining Buddha statue here. It is 49 meters long and 7 meters high."),
    ("You can see the twin towers here are 80 meters tall.", "You can see the twin towers here. They are 80 meters tall."),
    ("You see the statue here at <Pagoda> is 49 meters long.", "You see the statue here at <Pagoda>. It is 49 meters long."),
    ("You see the reclining Buddha statue here.", None),
    ("You see the statue here, which is 49 meters long.", None),
    ("Here is the entrance you see on your right.", None),
])
def test_item6_repair_net(bad, good):
    s = f"Stop 1: <Statue>\n\nCoordinates: 1.0, 2.0\n\nType/Specialty: Statue\n\n{bad} It stands on a hill.\n\nThat's 1 stop in all.\n"
    out = c906c.repair_you_see_here(s, None)
    assert (good in out) if good else (out == s)


# ── full replays of both wave-52 shapes ─────────────────────────────────────────────────────────────────
def _deliver(text, ev, logs):
    t = rc.finalize_898(text, ev, logs.append) if rc.active() else text
    t = rc.apply_single_place_guards(t, logs.append, evidence_by_title=ev)
    return db905.ensure_bodies(t, evidence_by_title=ev, log=logs.append)


def test_replay_551_route_shape(route):
    ev = {T_PROV: "The orchards grow in a dry climate.", "The cable car ascent": STUB_EV["The cable car ascent"]}
    rc.set_evidence_904(ev)
    logs = []
    out = _deliver(_route_tour(), ev, logs)
    assert "only country" not in out and "the only" not in out
    assert _same_bodies(out) == []
    n = len(re.findall(r"(?m)^Stop \d+:", out))
    assert n == 7 and f"That's {n} stops in all." in out
    assert "You see the" not in out or " here is " not in out
    assert not any("<!--" in x or "LOCAL-628" in x for x in logs), logs
    assert out.count(DISC) <= 1                                                       # said once, not once per stop


def test_replay_551_route_shape_when_nothing_borrowable_merges(route, monkeypatch):
    monkeypatch.setattr(c906c, "FILLER_VARIANTS", {})
    logs = []
    out = _deliver(_route_tour(), {}, logs)
    assert _same_bodies(out) == []
    n = len(re.findall(r"(?m)^Stop \d+:", out))
    assert n == 6 and f"That's {n} stops in all." in out and "That's 7" not in out
    assert any("branch (c)" in x for x in logs)


def test_replay_552_single_place_shape(plain):
    rc.set_evidence_904(EV_STATUE)
    logs = []
    out = _deliver(_single_tour(), EV_STATUE, logs)
    b2 = _bodies(out)[2]
    assert LONGEST not in out                                                         # no regional superlative w/o scope evidence
    assert LARGEST in b2                                                              # the narrower true claim is kept
    assert "You see the reclining Buddha statue here. It is 49 meters long and 7 meters high." in b2
    assert not re.search(r"You see the [^.]*? here is\b", out)
    assert len(re.findall(r"(?m)^Stop \d+:", out)) == 2 and "That's 2 stops in all." in out
    assert not any("<!--" in x or "LOCAL-628" in x for x in logs), logs
    assert any("superlative scope unsupported" in x for x in logs)


def test_replay_552_when_the_evidence_holds_only_the_wide_claim(plain):
    ev = {"<Statue>": "The statue is the longest reclining Buddha in <Region>. It measures 49 meters in length."}
    rc.set_evidence_904(ev)
    out = _deliver(_single_tour(), ev, [])
    assert LONGEST in out                                                             # evidence states it: kept


def test_a_plain_superlative_with_no_evidence_at_all_cannot_be_judged_but_exclusivity_still_goes(plain):
    """Nothing handed in anywhere: "the longest in <Country>" is left to the other guards (902 keeps it), "the only
    country in <Region>" has always gone (906)."""
    t = ("Alpha - Walking Tour\n\nStop 1: <Statue>\n\nCoordinates: 1.0, 2.0\n\nType/Specialty: Statue\n\n"
         "This reclining Buddha is the longest in <Country>. " + CLAIM + " It stands on a hill.\n\nThat's 1 stop in all.\n")
    out = c906c.drop_unsupported_scope_claims(t, None, None)
    assert "the longest in <Country>" in out and CLAIM not in out
