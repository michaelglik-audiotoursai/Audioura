"""LOCAL-906K -- refill quality bar, hedge per clause, self-anchored thing, exclusivity = record class, venue promo, mode words,
conflicting measures. Offline, $0, generic fixtures (D769), no network, no key."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("SERPER_API_KEY", None)
os.environ["THIN_STOP_SEARCH"] = "0"

import delivery_bodies_905 as db905  # noqa: E402
import delivery_evidence_906h as de  # noqa: E402
import leftovers_906c as c  # noqa: E402
import leftovers_906f as f906  # noqa: E402
import refill_quality_906k as k  # noqa: E402
import route_content_896 as rc  # noqa: E402


@pytest.fixture(autouse=True)
def _job():
    with rc.job_scope("t906k"):
        rc.set_evidence_904({})
        de.clear()
        yield


def tour(bodies, titles, cat="walking", types=None):
    head = f"<City> - {cat.title()} Tour\nTour-Category: {cat}\n\n"
    out = head
    for n, (b, t) in enumerate(zip(bodies, titles), 1):
        out += (f"Stop {n}: {t}\n\nCoordinates: 10.{n}, 100.{n}\n\nType/Specialty: {(types or ['Landmark'] * 9)[n - 1]}\n\n{b}\n\n"
                f"Directions: Continue to the next stop.\n\n")
    return out + f"That's {len(titles)} stops in all.\n"


def body_of(text, num):
    for s, e, n, _t in rc._stop_blocks(text):
        if n == num:
            return " ".join(ln for ln in text[s:e].split("\n")
                            if ln.strip() and not rc._KEYED.match(ln) and not ln.startswith(("Stop ", "Directions")))
    return ""


# ── 1. refill quality bar: replays of the 551 junk (generic names) ────────────────────────────────────────
JUNK5 = ("The video highlights the ascent to the summit at 3,842 meters, describing it as the world's highest cable car "
         "that reaches 13,000 feet in under ... Luxury from $150.00 per adult A surreal ascent into the clouds, revealing the "
         "<Other Village> and <Other Bridge> at the top2 … up to 1,500 passengers/hour Riding the world's highest-vertical-ascent "
         "cable car <Person>, highest-ver")
JUNK7 = ("Choose cable car or trekking, with or without a guide, and visit the Reclining Buddha, ... The Reclining Buddha on "
         "Mount <Mountain> is open all year round.")
CLEAN = "The cable car climbs the slope in about fifteen minutes and its cabins hold twenty people."


@pytest.mark.parametrize("junk,why", [
    ("The cable car ascent to the summit is described in a video that you can watch online today.", "video"),
    ("The cable car ascent costs $150 for each adult passenger on the upper line.", "price"),
    ("The cable car ascent carries up to 1,500 passengers/hour on the main line.", "capacity"),
    ("The cable car ascent was built to reach the summit station and then it continues...", "ellipsis"),
    ("The cable car ascent reveals the top2 station and the valley below it today.", "glued"),
    ("The cable car ascent is the world's highest cable car and reaches the summit station.", "world"),
    ("The cable car ascent is the only cable car in <Region> that reaches the summit station.", "exclusivity"),
    ("The cable car ascent shows the <Other Village> and the <Other Bridge> far below the cabins.", "other landmark"),
    ("Book a cable car ascent ticket online and enjoy the ride up to the summit.", "book"),
    ("The market sells fruit all morning to the people of the town.", "not about the stop"),
    (" ".join(["The cable car ascent passes"] + ["another quiet green ridge"] * 12) + ".", "run-on"),
])
def test_refill_bar_rejects_snippet_junk(junk, why):
    t = tour(["You ride up on the cable car."], ["The cable car ascent"])
    assert k.refill_reject(junk, "The cable car ascent", t, "article") is not None, why


def test_551_stop5_junk_is_never_a_refill():
    t = tour(["You ride the cabin. It is quiet. The slope is green.", "Pilgrims climb the stairs."],
             ["The cable car ascent", "<Pagoda>"])
    logs = []
    ev = {"The cable car ascent": JUNK5}
    out = f906.refill_thin_stops(t, ev, logs.append)
    b = body_of(out, 1)
    assert out == t, b
    for bad in ("video", "$", "…", "...", "<Other", "top2", "passengers", "world"):
        assert bad not in b
    assert any("[LOCAL-906K]" in x and "rejected" in x for x in logs), logs


def test_551_stop7_junk_is_never_a_refill():
    t = tour(["You see the <Statue>. It is large."], ["<Statue> Reclining Buddha"])
    logs = []
    out = f906.refill_thin_stops(t, {"<Statue> Reclining Buddha": JUNK7}, logs.append)
    assert out == t
    assert any("rejected" in x for x in logs)


def test_a_clean_article_sentence_still_refills():
    t = tour(["You ride the cabin. It is quiet."], ["The cable car ascent"])
    logs = []
    out = f906.refill_thin_stops(t, {"The cable car ascent": CLEAN}, logs.append)
    assert CLEAN in out


def test_clean_sentence_passes_the_bar():
    assert k.refill_reject(CLEAN, "The cable car ascent", None, "article") is None


def test_snippet_must_be_a_complete_clean_sentence():
    t = tour(["x."], ["The cable car ascent"])
    assert k.refill_reject(CLEAN, "The cable car ascent", t, "snippet") is None
    long_snip = ("The cable car ascent " + "passes quiet green hills and " * 7 + "ends at the station.")
    assert k.refill_reject(long_snip, "The cable car ascent", t, "snippet") is not None


def test_filler_branch_a_does_not_borrow_junk():
    t = tour(["You see the pagoda. It stands on the hill.", "You see the pagoda. It stands on the hill."],
             ["<Pagoda>", "The cable car ascent"])
    logs = []
    ev = {"<Pagoda>": "The pagoda stands on the hill.", "The cable car ascent": "Nothing useful here at all.",
          "<Elsewhere>": JUNK5}
    out = c.distinct_filler_bodies(t, ev, logs.append)
    assert "The video highlights" not in out and "$150" not in out and "…" not in out


def test_reject_logged_reports_and_returns_true():
    t = tour(["You ride the cabin."], ["The cable car ascent"])
    logs = []
    assert k.reject_logged(JUNK5, "The cable car ascent", t, logs.append, 1) is True
    assert logs and "[LOCAL-906K]" in logs[0]


# ── 2. hedge per clause ───────────────────────────────────────────────────────────────────────────────────
EV552 = ("The statue is the largest reclining Buddha in <Region>. "
         "It was the longest reclining Buddha in <Country> up to 2020 and remains one of the largest in <Region>.")


def test_scoped_claims_returns_every_clause():
    cl = c.scoped_claims("It was the longest reclining Buddha in <Country> up to 2020 and remains one of the largest in <Region>.",
                         include_hedged=True)
    assert [x["hedged"] for x in cl] == [False, True]
    assert {x["scope"] for x in cl} == {"<Country>", "<Region>"}
    assert "buddha" in cl[1]["toks"]


def test_hedge_in_second_clause_is_seen():
    s = "It is the largest reclining Buddha in all <Region>."
    assert c.check_claim(s, EV552, "<Pagoda> Statue")[0] == "ok"            # the web line supports it ...
    assert c.hedged_by_evidence(s, EV552, "<Pagoda> Statue") == \
        "It is one of the largest reclining Buddhas in <Region>."            # ... and the hedge in clause 2 wins


def test_552_stop2_rewritten_end_to_end():
    t = tour(["It is the largest reclining Buddha in all <Region>. Pilgrims climb the stairs to see it every day."], ["<Pagoda> Statue"])
    logs = []
    out = c.drop_unsupported_scope_claims(t, {"<Pagoda> Statue": EV552}, logs.append)
    assert "one of the largest reclining Buddhas in <Region>" in out
    assert "the largest reclining Buddha in all" not in out
    assert any("hedged" in x for x in logs)


def test_longest_and_largest_are_one_size_class():
    ev = "The <Statue> is one of the longest reclining Buddhas in <Region>."
    assert c.hedged_by_evidence("It is the largest reclining Buddha in <Region>.", ev, "<Pagoda>") is not None


def test_a_different_scope_hedge_does_not_apply():
    ev = "It was the longest in <Country> and remains one of the largest in <Other>."
    assert c.hedged_by_evidence("It is the largest reclining Buddha in <Region>.", ev, "<Pagoda>") is None


# ── 3. self-anchored thing ────────────────────────────────────────────────────────────────────────────────
def test_self_anchored_thing_is_kept():
    t = tour(["The statue at <Pagoda> was begun in 1963 and completed in 1966. Pilgrims climb the stairs to the top."],
             ["<Hill> Overlook"])
    logs = []
    out = c.repair_thing_referent(t, {"<Hill> Overlook": "The <Pagoda> stands on the hill."}, logs.append)
    assert "The statue at <Pagoda> was begun in 1963" in out
    assert not any("no antecedent" in x for x in logs)


@pytest.mark.parametrize("s", ["The statue on <Hill> is white.", "The temple of <Founder> was begun in 1900.",
                               "The tower in <City> was built in 1890.", "The statue at the foot of <Hill> is white."])
def test_self_anchor_shapes(s):
    t = tour([s + " Pilgrims climb the stairs."], ["<Lookout> Point"])
    assert s in c.repair_thing_referent(t, {}, None)


def test_bare_thing_is_still_dangling():
    t = tour(["The statue was begun in 1963. Pilgrims climb the stairs."], ["<Lookout> Point"])
    assert "The statue was begun" not in c.repair_thing_referent(t, {}, None)


# ── 4. exclusivity = record class ─────────────────────────────────────────────────────────────────────────
EXC = "Vietnam, the only country in <Region> that grows dragon fruit commercially, ships it all year."


def test_exclusivity_is_a_record_claim():
    r = c.record_claim(EXC)
    assert r and r["kind"] == "exclusivity"


def test_exclusivity_from_one_web_snippet_is_dropped():
    de.add({"<Farm>": [{"text": EXC, "kind": "web", "url": "https://one.example.com/a"}]}, "889")
    assert c.record_support(EXC, EXC, "<Farm>", c._entries_for("<Farm>")) == "bad"
    t = tour([EXC + " You walk on the path. Bananas grow nearby."], ["<Farm>"])
    out = c.drop_unsupported_scope_claims(t, {"<Farm>": EXC}, None)
    assert "the only country" not in out


def test_exclusivity_with_two_domains_or_a_reference_is_kept():
    de.add({"<Farm>": [{"text": EXC, "kind": "web", "url": "https://one.example.com/a"},
                       {"text": EXC, "kind": "web", "url": "https://two.example.org/b"}]}, "889")
    assert c.record_support(EXC, EXC, "<Farm>", c._entries_for("<Farm>")) == "ok"
    de.clear()
    de.add({"<Farm>": [{"text": EXC, "kind": "article"}]}, "889")
    assert c.record_support(EXC, EXC, "<Farm>", c._entries_for("<Farm>")) == "ok"


def test_a_plain_only_is_not_a_record():
    assert c.record_claim("It is the only way to reach the top.") is None


# ── 5. venue promo ────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("s", [
    "If you want to try local seafood, you can visit <Restaurant> right here on the banks of the <River>.",
    "You can visit <Name> restaurant for a late lunch after the walk.",
    "You can also try the <Name> cafe next door for fresh coffee.",
    "Choose cable car or trekking, with or without a guide, and visit the statue.",
])
def test_venue_promo_dropped(s):
    t = tour([s + " The market opens at dawn. Boats line the river bank."], ["<River> Bank"])
    out = f906.drop_promo(t, {}, None)
    assert s not in out and "Boats line" in out


def test_venue_promo_kept_when_the_stop_is_that_venue():
    s = "You can visit <Name> restaurant for a late lunch."
    t = tour([s + " It is by the river."], ["<Name> Restaurant"])
    assert s in f906.drop_promo(t, {}, None)


# ── 6. mode words ─────────────────────────────────────────────────────────────────────────────────────────
def test_driving_tour_walk_words():
    t = tour(["Dragon fruit grows on tall posts as you walk here. You can walk around the fields."], ["<Farm>"], cat="driving")
    out = k.fix_mode_words(t, None)
    b = body_of(out, 1)
    assert "walk" not in b.lower() and "grows on tall posts here." in b


def test_walking_tour_untouched():
    t = tour(["Dragon fruit grows on tall posts as you walk here. You can walk around the fields."], ["<Farm>"], cat="walking")
    assert k.fix_mode_words(t, None) == t


# ── 7. conflicting numbers ────────────────────────────────────────────────────────────────────────────────
def test_article_value_wins_over_web():
    art = "The statue measures 49 meters long and 7 meters high."
    de.add({"<Statue>": [{"text": art, "kind": "article"},
                         {"text": "A web page says it is 11 meters high.", "kind": "web", "url": "https://w.example.com/x"}]}, "889")
    ev = {"<Statue>": art + " A web page says it is 11 meters high."}
    t = tour(["The statue is 49 meters long and 11 meters high. Pilgrims climb the stairs."], ["<Statue>"])
    logs = []
    out = k.resolve_measure_conflicts(t, ev, logs.append)
    assert "49 meters long and 7 meters high" in out and "11 meters" not in out
    assert any("article value" in x for x in logs)


def test_7_kept_over_11():
    art = "The statue is 7 meters high."
    de.add({"<Statue>": [{"text": art, "kind": "article"}, {"text": "It is 11 meters high.", "kind": "web", "url": "https://a.example.com"}]}, "889")
    t = tour(["The statue is 7 meters high. Pilgrims climb the stairs."], ["<Statue>"])
    assert k.resolve_measure_conflicts(t, {"<Statue>": art + " It is 11 meters high."}, None) == t


def test_web_only_disagreement_omits_the_measure():
    ev = {"<Statue>": "One page says the statue is 49 meters long and 7 meters high. Another says it is 11 meters high."}
    de.add({"<Statue>": [{"text": "One page says the statue is 49 meters long and 7 meters high.", "kind": "web", "url": "https://a.example.com"},
                         {"text": "Another says it is 11 meters high.", "kind": "web", "url": "https://b.example.org"}]}, "889")
    t = tour(["The statue is 49 meters long and 11 meters high. Pilgrims climb the stairs."], ["<Statue>"])
    logs = []
    out = k.resolve_measure_conflicts(t, ev, logs.append)
    assert "11 meters" not in out and "49 meters long" in out
    assert any("omitted" in x for x in logs)


# ── whole pass ────────────────────────────────────────────────────────────────────────────────────────────
def test_ensure_bodies_end_to_end_no_junk():
    t = tour(["You ride the cabin. It is quiet.", "You see the <Pagoda>. It stands on the hill."],
             ["The cable car ascent", "<Pagoda>"], cat="driving")
    ev = {"The cable car ascent": JUNK5, "<Pagoda>": "The pagoda stands on the hill."}
    out = db905.ensure_bodies(t, ev, None)
    for bad in ("video", "$150", "…", "top2", "<Other"):
        assert bad not in out
