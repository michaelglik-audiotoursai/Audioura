"""LOCAL-906B -- tour 552 (LEAD proof of 906): Stop 2's three grounded sentences vanished with no log line, the 905
refill then inserted a verbless fragment, Stop 1 said the same fact twice, and Stop 2 kept an address Stop 1 lost.
Offline, $0, generic names, no network (the thin-stop escalation is stubbed everywhere it could be reached).

1  bisect: the step that took the sentences (873B append onto the closing + 619B cut) now keeps them
2  every sentence removal of every delivery pass is logged (sentence sets compared with the log)
3  a refill / kept sentence is a sentence (verbless fragment rejected, valid sentence accepted)
4  no near-duplicate within a stop (paraphrase, and the same fact with a different date)
5  a stop moved to another stop's verified pin inherits that stop's address verdict
"""
import os
import re
import sys
from collections import Counter

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["THIN_STOP_SEARCH"] = "0"          # never reach the paid escalation from a test

import delivery_bodies_905 as db905  # noqa: E402
import pin_snap  # noqa: E402
import route_content_896 as rc  # noqa: E402
import route_leftovers_906 as l906  # noqa: E402
import single_place_903 as sp903  # noqa: E402
import thin_stop_delivery as tsd  # noqa: E402
import tour_conclusion as tc  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures", "local906b_single_dirty.txt")
EV = {"<Mountain>": "The mountain rises 649 meters above the plain. A cable car and a forest trail lead up. "
                    "In 1872 a sage retreated to the forest.",
      "<Statue>": "The statue lies on a terrace near the summit. In 1958 a monk began building the statue, "
                  "which measures 49 meters in length."}
FACTS = ["The reclining Buddha statue measures 49 meters in length and 7 meters in height.",
         "Construction of the statue began in 1958 under a monk.",
         "The statue is one of the largest of its kind in Southeast Asia."]
NO_ESCALATION = lambda *a, **k: None   # noqa: E731

THIN_STOP2 = (
    "This is a step-by-step audio-guided walking tour of Alpha Mountain and the Beta Statue in Kappa.\n\n"
    "Stop 1: Alpha Mountain\n\nCoordinates: 10.828056, 107.882774\n\nType/Specialty: Natural Landmark\n\n"
    "The mountain rises above the plain and is reached by a cable car or a forest trail. A pagoda stands halfway up "
    "the slope and shelters a small community of monks. In 1872 a sage retreated into the forest of the mountain.\n\n"
    "Directions: Walk on to Beta Statue.\n\n"
    "Stop 2: Beta Statue\n\nCoordinates: 10.828056, 107.882774\n\nType/Specialty: Cultural Landmark\n\n"
    "Beta Statue is an exhibit at this venue.\n\n"
    "That's 2 stops in all.\n\n"
    "If you would like to eat nearby we can build you a restaurant tour.\n")


def _fx():
    with open(FIX, encoding="utf-8") as f:
        return f.read()


def _stop_sents(text, n):
    for s, e, num, _t in rc._stop_blocks(text):
        if num == n:
            return [x for ln in text[s:e].split("\n")[1:] if ln.strip() and not rc._KEYED.match(ln)
                    for x in rc.split_sentences(ln)]
    raise AssertionError(n)


@pytest.fixture(autouse=True)
def _plain_job():
    with rc.job_scope("t906b"):
        rc.clear_route()
        yield


# ── 1. bisect: which step took Stop 2's sentences ─────────────────────────────────────────────────────────
def test_bisect_873b_appends_to_the_closing_and_619b_cut_them():
    """The step: 873B (thin_stop_delivery) appended the rebuilt facts to the LAST body paragraph of the last
    stop, which is the tour's closing (the offer line). The rule: 619B ``_split_tail`` cuts everything from the
    first closing opener / count line to the end, so the facts went with the old conclusion and nothing logged.
    Rebuild the shape the old way (facts after the closing) and run the 619B step on it: they are kept."""
    shape = (THIN_STOP2.replace("<Statue> is an exhibit at this venue.\n\n", "")
             .replace("If you would like to eat nearby we can build you a restaurant tour.\n",
                      "If you would like to eat nearby we can build you a restaurant tour. " + " ".join(FACTS) + "\n"))
    logs = []
    out = tc.rebuild_conclusion(shape, venue_name="V", log=logs.append)
    s2 = _stop_sents(out, 2)
    for f in FACTS:
        assert f in out, (f, out)
    # the facts are Stop 2's body, ahead of the rebuilt conclusion
    assert out.index(FACTS[0]) < out.index("That's 2 stops in all.")
    assert any('[LOCAL-906B] Stop 2: kept "' + FACTS[0][:60] in x for x in logs), logs
    assert out.count("That's 2 stops in all.") == 1 and out.count("If you would like to eat nearby") == 1
    assert len(s2) >= 4


def test_bisect_facts_after_the_count_sentence_are_kept_but_a_recap_naming_another_stop_is_not():
    shape = (THIN_STOP2.replace("<Statue> is an exhibit at this venue.\n\n", "")
             .replace("That's 2 stops in all.\n\n", "That's 2 stops in all. " + " ".join(FACTS) + "\n\n"))
    out = tc.rebuild_conclusion(shape, venue_name="V", log=lambda m: None)
    assert all(f in out for f in FACTS) and out.index(FACTS[0]) < out.index("Across these stops")
    recap = shape.replace(" ".join(FACTS), "Alpha Mountain carries a tale rooted in the legends of this land.")
    logs = []
    out2 = tc.rebuild_conclusion(recap, venue_name="V", log=logs.append)
    assert "carries a tale" not in out2
    assert any('dropped "Alpha Mountain carries a tale' in x for x in logs), logs     # and the drop is logged


def test_873b_never_appends_to_the_closing_of_the_last_stop():
    out, rep = tsd.rebuild_thin_delivered_stops(
        THIN_STOP2, "Kappa", facts_by_title={"Beta Statue": FACTS, "Alpha Mountain": ["x"]}, narrate=False,
        escalate_fn=NO_ESCALATION, log=lambda *_a: None)
    body = _stop_sents(out, 2)
    assert rep["rebuilt"] >= 1
    i_facts, i_count = out.index(FACTS[0]), out.index("That's 2 stops in all.")
    assert i_facts < i_count, "facts must sit in the stop body, ahead of the closing"
    assert out.rstrip().endswith("restaurant tour."), "the offer stays the last line"
    assert body[0].startswith("<Statue> is an exhibit") or FACTS[0] in " ".join(body)


def test_replay_552_shape_873b_then_619b_then_guards_keep_the_grounded_sentences():
    """The whole delivery order on the 552 shape: 873B rebuild -> 619B conclusion -> single-place guards (904/906)
    -> 905. Stop 2 ends with its grounded sentences, not an empty body refilled by a fragment."""
    logs = []
    t, _ = tsd.rebuild_thin_delivered_stops(
        THIN_STOP2, "Kappa", facts_by_title={"Beta Statue": FACTS, "Alpha Mountain": ["x"]}, narrate=False,
        escalate_fn=NO_ESCALATION, log=lambda *_a: None)
    t = tc.rebuild_conclusion(t, venue_name="V", log=logs.append)
    t = rc.apply_single_place_guards(t, logs.append, evidence_by_title={"Beta Statue": " ".join(FACTS)})
    t = db905.ensure_bodies(t, {"Beta Statue": " ".join(FACTS)}, logs.append)
    s2 = _stop_sents(t, 2)
    assert sum(1 for f in FACTS if f in t) == 3, t
    assert not any("empty body on delivery" in x for x in logs), logs
    assert len([x for x in s2 if not rc._CLOSING_LINE.match(x)]) >= 3


# ── 2. every removal is logged ───────────────────────────────────────────────────────────────────────────
def _prose(text):
    out = []
    for s, e, num, _t in rc._stop_blocks(text):
        for i, ln in enumerate(text[s:e].split("\n")):
            if i == 0 or not ln.strip() or (rc._KEYED.match(ln) and not re.match(r"(?i)^\s*orientation", ln)):
                continue
            out += [(num, x) for x in rc.split_sentences(ln)]
    return Counter(out)


PASSES = [
    ("drop_carry_filler", lambda t, L: rc.drop_carry_filler(t, L)),
    ("strip_invented_route", lambda t, L: rc.strip_invented_route(t, L)),
    ("cap_single_place_filler", lambda t, L: rc.cap_single_place_filler(t, EV, L)),
    ("drop_fragments", lambda t, L: rc.drop_fragments(t, L, force=True)),
    ("drop_unsupported_comparatives", lambda t, L: rc.drop_unsupported_comparatives(t, EV, L, force=True)),
    ("drop_unsupported_claims", lambda t, L: l906.drop_unsupported_claims(t, EV, L)),
    ("drop_contradicting_orientation", lambda t, L: l906.drop_contradicting_orientation(t, L)),
    ("drop_repeated_sentences", lambda t, L: l906.drop_repeated_sentences(t, L)),
    ("drop_within_stop_duplicates", lambda t, L: rc.drop_within_stop_duplicates(t, L)),
    ("tone_first_stop", lambda t, L: l906.tone_first_stop(t, None, L)),
    ("drop_template_closing", lambda t, L: l906.drop_template_closing(t, L)),
    ("content_pass", lambda t, L: l906.content_pass(t, EV, L)),
    ("apply_single_place_guards", lambda t, L: rc.apply_single_place_guards(t, L, evidence_by_title=EV)),
    ("ensure_bodies", lambda t, L: db905.ensure_bodies(t, EV, L)),
    ("rebuild_conclusion", lambda t, L: tc.rebuild_conclusion(t, venue_name="V", log=L)),
    ("cap_unsupported_numbers", lambda t, L: rc.cap_unsupported_numbers(t, EV, L)),
    ("cap_unsupported_facts", lambda t, L: rc.cap_unsupported_facts(t, EV, L)),
    ("consistent_superlatives", lambda t, L: rc.consistent_superlatives(t, EV, L)),
    ("strip_body_travel", lambda t, L: rc.strip_body_travel(t, L)),
    ("normalize_directions", lambda t, L: rc.normalize_directions(t, L, force=True)),
    ("finalize_898", lambda t, L: rc.finalize_898(t, EV, L)),
]


@pytest.mark.parametrize("name,fn", PASSES, ids=[p[0] for p in PASSES])
def test_every_removed_sentence_is_logged(name, fn):
    """Run the pass on the dirty fixture; every sentence it removed has its first 80 characters in a log line."""
    logs = []
    before = _fx()
    after = fn(before, logs.append)
    gone = list((_prose(before) - _prose(after)).elements())
    joined = "\n".join(logs)
    silent = [(n, x[:80]) for n, x in gone if x[:80] not in joined]
    assert not silent, f"{name} removed text without a log line: {silent}"


def test_the_dirty_fixture_really_exercises_the_passes():
    """Guard the guard: the passes together remove a good number of sentences, so the test above is not vacuous."""
    logs = []
    out = rc.apply_single_place_guards(_fx(), logs.append, evidence_by_title=EV)
    assert sum((_prose(_fx()) - _prose(out)).values()) >= 5 and len(logs) >= 5


def test_a_pass_that_removes_silently_is_caught_by_the_comparison():
    """The comparison itself works: a fake pass that drops a sentence without logging is flagged."""
    before = _fx()
    after = before.replace("Lush greenery along the trails of the old forest. ", "")
    gone = list((_prose(before) - _prose(after)).elements())
    assert gone and all(x[:80] not in "" for _n, x in gone)


def test_619b_logs_the_old_conclusion_it_replaces_and_the_orphan_paragraph_it_drops():
    logs = []
    tc.rebuild_conclusion(THIN_STOP2, venue_name="V", log=logs.append)
    assert any('[LOCAL-619B] Stop 2: dropped "That\'s 2 stops in all."' in x for x in logs), logs
    t = ('Stop 1: Gamma Hall\n\nBody here is long enough.\n\nStop 2: Delta Court\n\nBody two is here and long.\n\n'
         '"Mona Lisa" hangs in another museum far away.\n')
    new, rep = tc.drop_orphan_work_paragraphs(t)
    assert rep["dropped"] == 1 and "Mona Lisa" not in new


# ── 3. a refill / kept sentence is a sentence ─────────────────────────────────────────────────────────────
VERBLESS = "49-meter-long, 7-meter-high reclining Buddha statue, one of the largest in Southeast Asia."


@pytest.mark.parametrize("s", [
    VERBLESS,
    "Lush greenery along the trails of the old forest.",
    "Stunning views from the summit of the mountain and the sea.",
])
def test_verbless_text_is_a_fragment(s):
    assert rc.is_verbless(s) and rc.is_fragment(s)


@pytest.mark.parametrize("s", [
    "The reclining Buddha lies on a terrace near the summit of the mountain.",
    "In 1872, a sage sought solitude in the forest of the mountain.",           # irregular past
    "Pilgrims reach the terrace by a long stone stairway from the lower pagoda.",
    "Walk on to the reclining Buddha statue.",                                    # imperative
    "That's 8 stops in all.",
    "Die Statue ist 49 Meter lang und 7 Meter hoch.",                              # not English: never judged
    "Beautiful!",
])
def test_whole_sentences_are_not_fragments(s):
    assert not rc.is_fragment(s)


def test_905_rejects_the_verbless_refill_and_takes_the_next_option():
    only = {"Beta Statue": VERBLESS + " Ticket offers are sold online."}
    assert db905._own_evidence_sentence("Beta Statue", {rc.fold("Beta Statue"): VERBLESS}, rc) is None
    t = THIN_STOP2.replace("Beta Statue is an exhibit at this venue.\n\n", "")
    logs = []
    out = db905.ensure_bodies(t, only, logs.append)
    assert VERBLESS not in out
    # no valid own sentence -> neighbour / honest body, as designed (never the fragment)
    assert any("[LOCAL-905] Stop 2" in x and "refilled" in x and "own evidence" not in x for x in logs), logs
    assert _stop_sents(out, 2)


def test_905_accepts_a_valid_sentence_even_behind_a_fragment():
    blob = VERBLESS + " The reclining Buddha statue lies on a terrace near the summit of the mountain."
    got = db905._own_evidence_sentence("Beta Statue", {rc.fold("Beta Statue"): blob}, rc)
    assert got and got.startswith("The reclining Buddha statue lies")
    t = THIN_STOP2.replace("Beta Statue is an exhibit at this venue.\n\n", "")
    logs = []
    out = db905.ensure_bodies(t, {"Beta Statue": blob}, logs.append)
    assert got in out and VERBLESS not in out
    assert any("refilled (own evidence)" in x for x in logs), logs


def test_904_refill_never_adds_a_verbless_fragment():
    before = _fx()
    after = rc.drop_fragments(rc.cap_single_place_filler(before, EV), force=True)
    out = rc.refill_thin_stops(before, after, {"<Statue>": VERBLESS + " " + " ".join(FACTS)})
    assert VERBLESS not in out


def test_drop_fragments_drops_a_kept_verbless_sentence_and_logs_it():
    logs = []
    t = THIN_STOP2.replace("Beta Statue is an exhibit at this venue.",
                           "The Beta Statue lies on a terrace near the summit. " + VERBLESS)
    out = rc.drop_fragments(t, logs.append, force=True)
    assert VERBLESS not in out and "lies on a terrace" in out
    assert any(VERBLESS[:60] in x for x in logs), logs


# ── 4. no near-duplicate within a stop ───────────────────────────────────────────────────────────────────
A1872 = ("In 1872, Master <A>, a great sage with the Dharma name <B>, sought solitude by retreating into the wild, "
         "untouched forest of <Mountain>, a place then teeming with dangerous animals and free of human footprints.")
B19C = ("In the late 19th century, a great sage known as Master <C>, with the Dharma name <B> and the Dharma title <A>, "
        "secluded himself in the tranquil surroundings of <Mountain>.")


def test_same_fact_with_a_different_date_is_a_duplicate():
    assert rc.same_fact(A1872, B19C, "<Mountain>")
    assert not rc.same_fact(A1872, "A pagoda stands halfway up the slope and shelters a small community of monks.",
                            "<Mountain>")
    assert rc.specificity(A1872) > rc.specificity(B19C)


def test_within_stop_duplicate_dropped_keeping_the_more_specific_and_logged():
    t = ("Stop 1: <Mountain>\n\nCoordinates: 10.8, 107.8\n\n" + B19C + " " + A1872 + " The mountain rises 649 meters "
         "above the plain.\n\nDirections: Walk on to <Statue>.\n\nStop 2: <Statue>\n\nCoordinates: 10.8, 107.8\n\n"
         "The statue lies on a terrace near the summit.\n\nThat's 2 stops in all.\n")
    logs = []
    out = rc.drop_within_stop_duplicates(t, logs.append)
    s1 = _stop_sents(out, 1)
    assert A1872 in s1 and B19C not in s1 and len(s1) == 2
    assert any('[LOCAL-906B] Stop 1: dropped "In the late 19th century' in x for x in logs), logs
    assert rc.drop_within_stop_duplicates(out) == out, "idempotent"


def test_two_identical_sentences_keep_exactly_one():
    s = "A pagoda stands halfway up the slope and shelters a small community of monks."
    t = f"Stop 1: <Mountain>\n\nCoordinates: 10.8, 107.8\n\n{s} {s}\n\nStop 2: <Statue>\n\nThe statue lies here.\n"
    assert rc.drop_within_stop_duplicates(t).count(s) == 1


def test_content_pass_runs_the_within_stop_guard():
    t = _fx()
    logs = []
    out = l906.content_pass(t, EV, logs.append)
    s1 = _stop_sents(out, 1)
    assert not (A1872 in s1 and B19C in s1)
    assert any("same fact as" in x for x in logs), logs


def test_904_refill_skips_an_evidence_sentence_that_repeats_a_sentence_of_the_stop():
    """The 552 defect: Stop 1 had one sentence; the thin refill appended a near-duplicate of it from the evidence."""
    stop1 = ("Stop 1: <Mountain>\n\nCoordinates: 10.8, 107.8\n\n" + A1872 + " Mood one that reads as filler here, "
             "serene and tranquil, a testament to peace. Mood two that reads as filler here, with gentle breezes "
             "and a spiritual harmony.\n\nDirections: Walk on to <Statue>.\n\n")
    rest = ("Stop 2: <Statue>\n\nCoordinates: 10.8, 107.8\n\nThe <Statue> lies on a terrace near the summit. "
            "Pilgrims reach the terrace by a long stone stairway.\n\nThat's 2 stops in all.\n")
    before = stop1 + rest
    after = before.replace(" Mood one that reads as filler here, serene and tranquil, a testament to peace.", "") \
                  .replace(" Mood two that reads as filler here, with gentle breezes and a spiritual harmony.", "")
    ev = {"<Mountain>": B19C + " " + A1872 + " The mountain rises 649 meters above the plain and is reached by a "
                        "cable car or a forest trail."}
    logs = []
    out = rc.refill_thin_stops(before, after, ev, logs.append)
    s1 = _stop_sents(out, 1)
    assert B19C not in s1, s1
    assert not (A1872 in s1 and any(rc.same_fact(A1872, x, "<Mountain>") for x in s1 if x != A1872)), s1


# ── 5. the address check covers every stop ───────────────────────────────────────────────────────────────
REV = "Lập Nghĩa, Xã Hàm Thuận Nam, Tỉnh Lâm Đồng, Việt Nam"
WRONG = "<Mountain>, Tánh Linh District, Bình Thuận, Vietnam"


def _pois_and_rows():
    pois = [{"name": "<Mountain>", "address": WRONG, "coordinates": "10.828056, 107.882774"},
            {"name": "<Statue>", "address": WRONG, "coordinates": "10.9311, 107.6356"}]
    rows = [{"snapped": True, "new_coordinate": (10.828056, 107.882774), "source": "serper"},
            {"snapped": False, "reference": (10.9311, 107.6356), "rejected_900b": True,
             "reason": "snap rejected (outside scope)"}]
    return pois, rows


def test_moved_stop_inherits_the_address_verdict_of_the_stop_it_moved_to():
    pois, rows = _pois_and_rows()
    logs = []
    assert sp903.agree_single_place(pois, rows, "DISTRICT", logs.append) == 1
    assert pois[1]["_pin_moved_to_stop"] == 0
    dropped = pin_snap.verify_addresses(pois, rows, scope="", reverse_fn=lambda a, b: REV, log=logs.append)
    assert pois[0]["address"] == "" and pois[1]["address"] == "", logs
    assert dropped == 2
    assert any("[LOCAL-906B] address dropped for '<Statue>'" in x and "inherits" in x for x in logs), logs


def test_moved_stop_keeps_an_address_that_agrees_with_the_donor_pin():
    pois, rows = _pois_and_rows()
    for p in pois:
        p["address"] = "Thuan Hoa, Ham Thuan Nam, Kappa, Zedland"
    sp903.agree_single_place(pois, rows, "DISTRICT")
    assert pin_snap.verify_addresses(pois, rows, scope="", reverse_fn=lambda a, b: REV) == 0
    assert pois[0]["address"] and pois[1]["address"]


def test_moved_stop_with_its_own_wrong_address_is_judged_on_the_donor_pin():
    pois, rows = _pois_and_rows()
    pois[0]["address"] = ""                                  # the donor has no address of its own to judge
    sp903.agree_single_place(pois, rows, "DISTRICT")
    pin_snap.verify_addresses(pois, rows, scope="", reverse_fn=lambda a, b: REV)
    assert pois[1]["address"] == ""


def test_an_unmoved_stop_is_checked_on_its_own_as_before():
    pois = [{"name": "<Mountain>", "address": WRONG}, {"name": "<Statue>", "address": "Thuan Hoa, Ham Thuan Nam, K, Z"}]
    rows = [{"snapped": True, "new_coordinate": (10.8, 107.8)}] * 2
    pin_snap.verify_addresses(pois, rows, scope="", reverse_fn=lambda a, b: REV)
    assert pois[0]["address"] == "" and pois[1]["address"]
