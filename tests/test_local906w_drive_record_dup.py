"""[LOCAL-906W] Drive record / antecedent / closing / near-duplicate / title glue / body travel time. Generic names only (D769), offline."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("SERPER_API_KEY", None)
os.environ["THIN_STOP_SEARCH"] = "0"

import drive_quality_906v as v  # noqa: E402
import language_dest_906s as s906s  # noqa: E402
import leftovers_906c as c  # noqa: E402
import route_content_896 as rc  # noqa: E402
import stub_promo_906t as t  # noqa: E402

REC = "This statue is the longest reclining Buddha in Asia."
ALT = "Alternatively, you can climb through the jungle to see the gigantic reclining Buddha statue."


def tour(stops, closing="That's {n} stops in all.\n"):
    out = ["Step-by-step audio guided tour from Alpha Town to Omega Mountain in Region, Country is a driving tour.\n"]
    for k, (title, body) in enumerate(stops, 1):
        out.append(f"Stop {k}: {title}\n\nCoordinates: 10.{k}, 108.{k}\n\nType/Specialty: Landmark\n\n{body}\n\nDirections: Go on.\n")
    out.append(closing.format(n=len(stops)))
    return "\n".join(out)


def test_record_hedged_to_the_narrower_scope_the_evidence_states():
    ev = {"Omega Mountain": "Omega Mountain has the longest reclining Buddha statue in Asia.",
          "Reclining Buddha": "It is the longest reclining Buddha statue in Southeast Asia."}
    txt = tour([("Omega Mountain", "You can ride a cable car to the top. " + ALT + " " + REC + " The path is steep.")])
    buf = []
    out = t.run_pass(txt, ev, buf.append)
    assert "one of the longest reclining Buddhas in Southeast Asia" in out
    assert "the longest reclining Buddha in Asia" not in out
    assert any("narrower scope" in m for m in buf)


def test_record_hedged_against_hedged_evidence_on_a_differently_keyed_stop():
    ev = {"Omega Mountain, Region": "The statue is one of the longest reclining Buddha statues in Southeast Asia."}
    out = t.run_pass(tour([("Omega Mountain", ALT + " " + REC)]), ev)
    assert "the longest reclining Buddha in Asia" not in out


def test_retold_pass_prefers_the_hedged_sentence_over_an_unhedged_record():
    hedged = "This statue is one of the longest reclining Buddhas in Southeast Asia."
    assert v.keep_key(hedged, "Omega Mountain") > v.keep_key(REC, "Omega Mountain")
    assert v.keep_key(ALT, "Omega Mountain") > v.keep_key(REC, "Omega Mountain")
    # a superlative's scope word is not a specific
    assert v._plain_specificity(REC, "Omega Mountain") < rc.specificity(REC)


def test_retold_pass_keeps_the_sentence_that_introduces_the_thing():
    body = "You can ride a cable car to the top. " + ALT + " " + REC
    buf = []
    out = v.retold_pass(tour([("Omega Mountain", body)]), buf.append)
    blk = out.split("Stop 1:")[1]
    assert "This statue" not in blk or "statue" in blk.split("This statue")[0]      # never a dangling "This statue"
    assert not (REC in blk and ALT not in blk)


def test_dangling_this_statue_after_retold_is_dropped():
    # the introducing sentence is the loser of a same-event group and is not kept for it: the antecedent check runs afterwards
    body = "The stop has a cable car. " + REC
    out = c.repair_thing_referent(tour([("Omega Mountain", body)]), {})
    assert "This statue" not in out


def test_closing_variant_dropped():
    x = "By exploring these significant landmarks, you gain insight into the artistry and history that shape this beautiful area."
    assert s906s.variant_reason(x)
    assert t.promo_reason(x)
    for z in ("By visiting these places, you will discover the stories that shape this region.",
              "By seeing these sites you learn how the coast grew."):
        assert s906s.variant_reason(z)
    assert not s906s.variant_reason("By climbing the 183 steps you reach the lamp room.")
    txt = tour([("Omega Mountain", "The tower is 20 metres high."), ], closing=x + " That's {n} stops in all.\n")
    assert "By exploring these" not in t.run_pass(txt, {})


def test_near_duplicate_in_one_stop_is_merged_keeping_the_first():
    a = "These towers are among the oldest Champa towers that remain largely undamaged."
    b = "Poshanu Towers are among the oldest Champa towers that are not much damaged."
    assert v.same_telling(a, b, "Poshanu Cham Towers")
    assert not v.same_telling("The towers were built in 1280.", "A small market sells fish every morning.", "Poshanu Cham Towers")
    txt = tour([("Poshanu Cham Towers", "You are standing at Poshanu Cham Towers. " + a + " Despite their small size, the carving shows skill. " + b)])
    out = v.retold_pass(txt)
    assert a in out and b not in out


def test_pronoun_repair_does_not_glue_the_title_before_the_same_noun():
    txt = tour([("The cable car ascent", "This cable car system, designed in Austria. The ascent covers 1,279 meters.")])
    out = c.repair_pronoun_opener(txt)
    assert "The cable car system, designed in Austria." in out
    assert "ascent car system" not in out
    # the plain repair still names the title
    out2 = c.repair_pronoun_opener(tour([("Omega Statue", "This statue is 49 meters long.")]))
    assert "The Omega Statue is 49 meters long." in out2


def test_body_travel_time_dropped_on_a_route_tour():
    x = "If you start from Alpha Town, the trip to Omega Mountain takes about 40 to 44 minutes by car."
    txt = tour([("Omega Mountain", "The mountain rises 649 meters above the plain. " + x + " A cable car runs to the top.")])
    buf = []
    out = v.sentence_pass(txt, buf.append)
    assert "40 to 44 minutes" not in out and "The mountain rises 649 meters" in out
    assert any("travel time" in m for m in buf)
    # a plain 897 clause cut no longer leaves "If you start from <Origin>."
    assert rc._cut_left_sub("If you start from Alpha Town.")
    assert not rc._cut_left_sub("If you start early, you see the sunrise.")
