#!/usr/bin/env python3
"""LOCAL-891 -- "supported" must also mean "about THIS stop". Offline.

Generic fixtures ("Some Church", "Some Street") carry the rule; the replay uses the LEAD 890 text
(submission_artifacts/local890/saigon_warm.txt) with STAND-IN bundles: the 890 evidence json did NOT
persist the per-stop evidence (``landmarks`` is {} and ``claim_provenance`` holds claims only), so the
bundles are rebuilt from the recorded Wikipedia text of tests/fixtures/local889_recorded.json and
local890_recorded.json plus ONE clearly synthetic city-level passage per case (marked SYNTHETIC).
This is an offline replay, not a live measurement."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import aboutness as ab                      # noqa: E402
import key_fact_coverage as kfc             # noqa: E402
import strict_grounding_gate as sgg         # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
R889 = json.load(open(os.path.join(HERE, "fixtures", "local889_recorded.json"), encoding="utf-8"))
R890 = json.load(open(os.path.join(HERE, "fixtures", "local890_recorded.json"), encoding="utf-8"))
T890 = open(os.path.join(ROOT, "submission_artifacts", "local890", "saigon_warm.txt"), encoding="utf-8").read()


def art(title, lead, passages=(), lang="en"):
    t = f"{title} - Wikipedia ({lang}). {lead}"
    if passages:
        t += "\nPassages: [History] " + " ".join(passages)
    return t


def rec(v, extra=()):
    return art(v["title"], v["lead"], list(v["passages"]) + list(extra))


def stop_sents(title_part, text=T890):
    for n, t, body in sgg._split_blocks(text):
        if title_part.lower() in t.lower():
            return t, sgg._content_sentences(sgg._block_body_prose(body))
    raise KeyError(title_part)


def overlap_judge(_system, user, _model):
    """A judge that says SUPPORTED for everything and names, per sentence, the evidence item with the
    most shared tokens -- what a real judge does with the item ids. Isolates the aboutness rule."""
    items = {}
    for m in re.finditer(r"(?m)^\[(E\d+) \| about_stop=(true|false)[^\]]*\] (.*)$", user):
        items[m.group(1)] = m.group(3)
    sents = re.findall(r"(?m)^(\d+)\. (.*)$", user.split("FACTUAL SENTENCES:")[-1])
    out = []
    for i, s in sents:
        st = set(ab.toks(s))
        best = max(items, key=lambda k: len(st & set(ab.toks(items[k]))), default="")
        out.append({"i": int(i), "verdict": "SUPPORTED", "evidence": "x", "legend": False, "source": best})
    return {"verdicts": out}, 10, 10


# ───────── generic fixtures ─────────
CITY_EVENT = ("Riverton crisis - Wikipedia (en). The crisis was a period of unrest in the city in 1963.\n"
              "Passages: [Events] Following the protest of Brother Anselm, the governor promised reforms but failed "
              "to deliver, prompting riots and raids on monasteries. During the raids Brother Anselm's relic was "
              "seized and became a grim symbol of the unrest. His protest inspired others and contributed to the "
              "coup of 2 November 1963.")
CHURCH_OWN = art("Some Church", "Some Church is a church in Riverton. It was completed in 1880 to a design by "
                 "Henri Moreau.", ["The church was damaged by fire in 1921 and restored in 1925.",
                                   "A bronze statue of the founder was placed in front of the church in 1903."])
CHURCH_BODY = ("The church was completed in 1880 to a design by Henri Moreau. "
               "Following the protest of Brother Anselm, the governor promised reforms but failed to deliver. "
               "During the raids, Brother Anselm's relic was seized and became a grim symbol of the unrest. "
               "His protest inspired others and contributed to the coup of 2 November 1963. "
               "The church was damaged by fire in 1921 and restored in 1925.")


# ═════════ 1. items carry about_stop ═════════
def test_own_article_items_are_about_the_stop():
    items = ab.build_items(CHURCH_OWN + "\n" + CITY_EVENT, "Some Church")
    own = [i for i in items if i["kind"] == "own_article"]
    assert own and all(i["about_stop"] for i in own)
    ctx = [i for i in items if not i["about_stop"]]
    assert ctx and all("Anselm" in i["text"] or "crisis" in i["text"] for i in ctx)


def test_city_event_item_is_context_not_about():
    items = ab.build_items(CHURCH_OWN + "\n" + CITY_EVENT, "Some Church")
    ev = [i for i in items if "Anselm" in i["text"]]
    assert ev and not any(i["about_stop"] for i in ev)


def test_non_own_passage_that_names_the_stop_is_about():
    sq = art("Old Square", "Old Square is a square in Riverton. It surrounds Some Church.",
             ["The square was named after the church. A statue stands in front of the church since 1959."])
    items = ab.build_items(sq, "Church")
    assert any(i["about_stop"] and "1959" in i["text"] for i in items)
    assert not items[0]["kind"] == "own_article"


def test_geo_tag_within_150m_lets_a_single_mention_stand():
    para = ("Plaza A is busy. It was rebuilt in 1950. Crowds gather each year. The plaza lies next to the "
            "church.")
    ref = ab.Referent("Church")
    assert ab.para_about(para, ref)[0] is False
    assert ab.para_about(para, ref, geo_m=90)[0] is True
    assert ab.para_about(para, ref, geo_m=400)[0] is False


# ═════════ 2. the gate ═════════
def test_gate_drops_the_city_event_but_keeps_the_church_facts():
    ev = CHURCH_OWN + "\n" + CITY_EVENT
    out, rep = sgg.apply_grounding_gate("Some Church", CHURCH_BODY, ev, classify_fn=overlap_judge)
    assert "Anselm" not in out and "1963" not in out
    assert "1880" in out and "1921" in out
    assert len(rep["offtopic"]) == 3
    assert all(o["source"] for o in rep["offtopic"])


def test_gate_request_carries_about_stop_and_judge_source():
    seen = {}

    def spy(system, user, model):
        seen["system"], seen["user"] = system, user
        return overlap_judge(system, user, model)
    sgg.apply_grounding_gate("Some Church", CHURCH_BODY, CHURCH_OWN + "\n" + CITY_EVENT, classify_fn=spy)
    assert "about_stop=true" in seen["user"] and "about_stop=false" in seen["user"]
    assert '"source"' in seen["system"]


def test_judge_naming_a_context_item_is_overridden_by_an_about_item_that_carries_it():
    items = ab.build_items(CHURCH_OWN + "\n" + CITY_EVENT, "Some Church")
    ctx_id = [i for i in items if not i["about_stop"]][0]["id"]
    r = ab.assess("The church was damaged by fire in 1921 and restored in 1925.", items, judge_source=ctx_id)
    assert r["ok"] and r["source"] != ctx_id


def test_sentence_that_ties_the_event_to_a_different_place_is_kept_once():
    items = ab.build_items(CHURCH_OWN + "\n" + CITY_EVENT, "Some Church")
    s1 = ("A few blocks away, at the old crossroads, Brother Anselm's relic was seized and became a grim "
          "symbol of the unrest.")
    s2 = ("A few blocks away, the governor promised reforms but failed to deliver, prompting riots and raids "
          "on monasteries.")
    r1 = ab.assess(s1, items)
    assert r1["ok"] and r1["other_place"]
    r2 = ab.assess(s2, items, other_place_used=1)
    assert not r2["ok"]                                    # cap: one per stop


def test_undecidable_sentence_keeps_the_judges_verdict():
    items = ab.build_items(CHURCH_OWN, "Some Church")
    assert ab.assess("The weather there is mild in spring.", items)["ok"]


def test_no_evidence_flow_unchanged():
    out, rep = sgg.apply_grounding_gate("Some Church", CHURCH_BODY, "", classify_fn=overlap_judge)
    assert rep["no_evidence"] and "1880" not in out


# ═════════ 3. tangent / repeat / filler / raw lead / pronoun opener ═════════
OFFICE = art("Some Post Office", "The Some Post Office is a post office in Riverton.",
             ["It was constructed between 1886 and 1891 and is now a tourist attraction.",
              "It was designed by Alfred Foulhoux, but is often erroneously credited to Gustave Eiffel."])


def test_tangent_stamp_sentence_is_dropped():
    body = ["It is often mistakenly credited to Gustave Eiffel, but Alfred Foulhoux was the architect.",
            "Known locally as the stork stamp for its depiction of the elegant bird, this stamp was the "
            "first national stamp issued in 1864.",
            "The introduction of the stamp enabled ordinary citizens to send letters and parcels.",
            "The Post Office was constructed between 1886 and 1891 and is now a tourist attraction.",
            "The large painted maps on the walls were created shortly after the completion in 1891."]
    out, rep = ab.clean_stop("Some Post Office", body, OFFICE)
    assert not any("stamp" in s for s in out)
    assert len(rep["tangent"]) == 2
    assert any("maps" in s for s in out)                    # a PART of the building stays
    assert out[0].startswith("The Some Post Office is often mistakenly credited")


def test_near_repeat_fact_is_stated_once():
    body = ["The hall became the venue for the People's Assembly, a pivotal moment for the city.",
            "The hall was designed by Henri Moreau.",
            "After the war in 1975, the new government started holding the People's Assembly at the hall."]
    ref = ab.Referent("Some Hall")
    reps = ab.near_repeats(body, ref)
    assert len(reps) == 1 and "people's assembly" in reps[0][2].lower()
    out, rep = ab.clean_stop("Some Hall", body, art("Some Hall", "Some Hall is a hall.", []))
    assert sum("People's Assembly" in s for s in out) == 1
    assert any("1975" in s for s in out)                    # the dated one stays


def test_filler_is_dropped_but_a_real_sentence_is_not():
    assert ab.is_filler("The building is located on a walking street, making it easy to find.")
    assert ab.is_filler("As you look up, you can see the multiple floors that house this complex.")
    assert not ab.is_filler("The building was completed in 1925 and has six floors.")
    body = ["You are standing in front of Some Cafe at 42 Main Street.",
            "It is now a complex of independent cafes and boutique stores.",
            "The building is on the walking street, making it easy to find.",
            "As you look up, you can see the multiple floors that house this multi-story complex."]
    out, rep = ab.clean_stop("Some Cafe", body, "")
    assert len(out) == 2 and len(rep["filler"]) == 2


def test_raw_lead_sentence_never_ends_a_stop():
    ref = ab.Referent("Some Museum")
    raw = "The Some Museum is a war museum at 28 Main Street, Old Ward, Riverton, Country."
    assert ab.is_raw_lead(raw, ref)
    assert not ab.is_raw_lead("The museum opened on 4 September 1975 as a small exhibition house.", ref)
    out, rep = ab.clean_stop("Some Museum", ["It opened in 1975.", "Photographs line the walls.",
                                             "Aircraft stand in the yard.", raw], "")
    assert out[-1] != raw and len(rep["raw_lead"]) == 1


# ═════════ 4. thin stop with a rich own article reaches 5 ═════════
def test_rich_own_article_refills_a_thin_stop_to_five():
    v = R889["wrm"]
    ev = rec(v, WRM_RICH)
    body = ["This museum first opened its doors on 4 September 1975, under the name Exhibition House for "
            "U.S. and Puppet Crimes.",
            "The displays gathered here do not shy from the brutal consequences of conflict.",
            "Inside, a poignant tribute honors the photojournalists who risked and often lost their lives.",
            "The War Remnants Museum is a war museum at 28 Võ Văn Tần Street, Xuân Hòa, Ho Chi Minh City, Vietnam."]
    out, rep = kfc.finalize_stop("War Remnants Museum", body, ev, classify_fn=overlap_judge)
    assert len(out) >= 5, out
    assert out[-1] != body[-1] and "Võ Văn Tần" not in " ".join(out)


# ═════════ 5. narrator input ═════════
def test_narrator_gets_no_city_event_as_this_stops_history():
    items, ctx = ab.narrator_items("Some Church", [CHURCH_OWN, CITY_EVENT], mode="drop")
    blob = " ".join(items)
    assert "Anselm" not in blob and "1880" in blob and ctx == ""


def test_narrator_labelled_mode_keeps_context_in_a_separate_block():
    items, ctx = ab.narrator_items("Some Church", [CHURCH_OWN, CITY_EVENT], mode="labelled")
    assert "Anselm" not in " ".join(items)
    assert "do not present as this stop's history" in ctx and "Anselm" in ctx


def test_narrator_unchanged_when_nothing_can_be_told_apart():
    only = [art("Elsewhere", "Elsewhere is a district.", ["Something happened in 1900."])]
    items, ctx = ab.narrator_items("Some Church", only, mode="drop")
    assert items == only and ctx == ""


# ═════════ 6. REPLAY on the LEAD 890 text (stand-in bundles) ═════════
# SYNTHETIC: the city-level Buddhist-crisis passage, reconstructed from the sentences the LEAD quoted.
CRISIS = art("Buddhist crisis", "The Buddhist crisis was a period of tension in South Vietnam in 1963.",
             ["Following the self-immolation of Thích Quảng Đức, Diệm promised reforms to ease Buddhist tensions "
              "but failed to deliver, prompting further protests and violent raids on Buddhist pagodas. During "
              "these raids, Thích Quảng Đức's heart was seized, becoming a grim symbol of ongoing conflict. His "
              "sacrifice inspired other monks to follow his example, escalating unrest that eventually "
              "contributed to the US-backed coup that toppled Diệm on 2 November 1963."])
# SYNTHETIC: a stamp-history article, the post office tangent.
STAMP = art("Postage stamps of Vietnam", "Vietnam issued its first stamp in 1864.",
            ["Known locally as the stork stamp for its depiction of the elegant bird, this stamp was the first "
             "Vietnamese stamp issued in 1864. The introduction of the stamp enabled ordinary citizens to send "
             "letters and parcels with official recognition."])
SQUARE = rec(R890["square"])
CATHEDRAL_EXTRA = ("Pigneau de Béhaine's statue stood before the cathedral until 1945. The cathedral was designed "
                   "by Jules Bourard and completed in 1880.")


# SYNTHETIC: the richer own-article passages the LEAD described for the live bundle (photographers' tribute,
# Agent Orange jars, the guillotine, the aircraft yard); the recorded article is thinner.
WRM_RICH = [
    "A memorial room pays tribute to the photojournalists who died documenting the war, with their cameras and "
    "photographs on display.",
    "Jars holding preserved deformed foetuses show the effects of Agent Orange on children born in the 1970s.",
    "A guillotine used by the French colonial authorities from the 1950s is shown in the Prison Systems exhibit.",
    "The outdoor yard displays captured American aircraft, tanks and artillery from the war.",
]


def _cathedral_bundles():
    own = art("Saigon Notre-Dame Basilica", R889["cathedral"]["lead"],
              list(R889["cathedral"]["passages"]) + [CATHEDRAL_EXTRA])
    return {"own+square+crisis": own + "\n" + SQUARE + "\n" + CRISIS,
            "square+crisis (no own article)": SQUARE + "\n" + CRISIS}


def test_replay_cathedral_drops_the_crisis_keeps_the_building_facts():
    title, sents = stop_sents("Cathedral")
    assert any("Thích Quảng Đức" in s for s in sents)
    for name, ev in _cathedral_bundles().items():
        out, rep = sgg.apply_grounding_gate(title, " ".join(sents), ev, classify_fn=overlap_judge)
        assert "Thích" not in out and "Diệm" not in out, name
        if name.startswith("own"):
            assert "1880" in out, name              # only the own article states the completion year
        assert "1959" in out, name
        assert len(rep["offtopic"]) >= 3, (name, rep["offtopic"])


def test_replay_cathedral_with_pigneau_and_bourard_in_evidence():
    ev = _cathedral_bundles()["own+square+crisis"]
    body = ("Jules Bourard designed the cathedral, which was completed in 1880. "
            "A bronze statue of Pigneau de Béhaine stood in front of the cathedral from 1903 until 1945. "
            "In 1959 a new statue of Our Lady of Peace was erected. "
            "Thích Quảng Đức's heart was seized during raids on pagodas.")
    out, rep = sgg.apply_grounding_gate("Cathedral", body, ev, classify_fn=overlap_judge)
    for k in ("Bourard", "Pigneau", "1959", "1880"):
        assert k in out, k
    assert "Thích" not in out


def test_replay_post_office_has_no_stamp_tangent():
    title, sents = stop_sents("Post Office")
    ev = rec(R889["post_office"]) + "\n" + STAMP
    out, rep = sgg.apply_grounding_gate(title, " ".join(sents), ev, classify_fn=overlap_judge)
    out2, rep2 = ab.clean_stop(title, sgg._content_sentences(out), ev)
    joined = " ".join(out2)
    assert "stamp" not in joined and "stork" not in joined
    assert "Foulhoux" in joined and "1891" in joined
    assert not joined.startswith("It ")                   # no antecedent-less opener


def test_replay_wrm_reaches_five_sentences_and_no_raw_lead_ending():
    title, sents = stop_sents("War Remnants")
    assert len(sents) == 4
    out, rep = kfc.finalize_stop(title, sents, rec(R889["wrm"], WRM_RICH), classify_fn=overlap_judge)
    assert len(out) >= 5, out
    assert "Võ Văn Tần" not in out[-1] and not ab.is_raw_lead(out[-1], ab.Referent(title))


def test_replay_wrm_thin_recorded_article_is_not_padded_with_context():
    """The RECORDED article has only six sentences: the refill takes what is there, never city material."""
    title, sents = stop_sents("War Remnants")
    out, rep = kfc.finalize_stop(title, sents, rec(R889["wrm"]) + "\n" + CRISIS, classify_fn=overlap_judge)
    assert "Thích" not in " ".join(out) and not ab.is_raw_lead(out[-1], ab.Referent(title))


def test_replay_city_hall_and_opera_unchanged_by_the_new_rules_where_clean():
    for part, key in (("City Hall", "city_hall"), ("Opera House", "opera")):
        title, sents = stop_sents(part)
        ev = rec(R889[key])
        out, rep = sgg.apply_grounding_gate(title, " ".join(sents), ev, classify_fn=overlap_judge)
        assert len(out) > 0
