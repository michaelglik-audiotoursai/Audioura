#!/usr/bin/env python3
"""LOCAL-889 — key-fact coverage, removed claims stay removed, filler cap, and the
deterministic UNSUPPORTED rules. Offline. Evidence = English Wikipedia text recorded
in tests/fixtures/local889_recorded.json (verbatim sentences); the 888 delivered
text = submission_artifacts/local888/saigon_warm.txt. No venue name is in the code
under test (D769)."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import key_fact_coverage as kfc                   # noqa: E402
import strict_grounding_gate as sgg               # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REC = json.load(open(os.path.join(HERE, "fixtures", "local889_recorded.json"), encoding="utf-8"))
ROOT = os.path.dirname(HERE)
T888 = open(os.path.join(ROOT, "submission_artifacts", "local888", "saigon_warm.txt"),
            encoding="utf-8").read()

PALACE_FLED = ("The Independence Hall served as Thiệu's home and office from October 1967 to "
               "21 April 1975, when he fled the country as communist North Vietnamese forces "
               "swept southwards in the decisive Ho Chi Minh Campaign.")


def _lead(key):
    v = REC[key]
    lead = re.sub(r"\s+", " ", v["lead"])
    cut = max(lead.rfind(". "), 0)
    return lead[:cut + 1] if cut else lead


def ev(key, extra=()):
    v = REC[key]
    return f"{v['title']} - Wikipedia (en). " + " ".join([_lead(key)] + list(v["relevant"]) + list(extra))


def stop_sents(title_part):
    for n, t, body in sgg._split_blocks(T888):
        if title_part.lower() in t.lower():
            return t, sgg._content_sentences(sgg._block_body_prose(body))
    raise KeyError(title_part)


def all_supported(_system, user, _model):
    n = len(re.findall(r"(?m)^\d+\. ", user.split("FACTUAL SENTENCES:")[-1]))
    return {"verdicts": [{"i": i, "verdict": "SUPPORTED", "evidence": "x", "legend": False}
                         for i in range(1, n + 1)]}, 10, 10


# ═════════ 1. key facts are read from the evidence ═════════
def test_key_facts_city_hall_years():
    f = {x["kind"]: x for x in kfc.key_facts(ev("city_hall"), "City Hall")}
    assert f["years"]["years"] == ["1898", "1909"]


def test_key_facts_opera_event_and_architect():
    f = {x["kind"]: x for x in kfc.key_facts(ev("opera"), "Opera House")}
    assert f["event"]["year"] == "1944"
    assert f["architect"]["surname"] == "olivier"


def test_key_facts_palace_dated_event_and_designer():
    f = {x["kind"]: x for x in kfc.key_facts(ev("palace"), "Independence Palace")}
    assert f["event"]["date"] == (30, "apr", 1975)
    assert f["architect"]["surname"] == "thu"
    assert "1955" not in f["years"]["years"]          # a prize year is not a build year


def test_key_facts_post_office_architect_not_eiffel():
    f = {x["kind"]: x for x in kfc.key_facts(ev("post_office"), "Post Office")}
    assert f["architect"]["surname"] == "foulhoux"
    assert f["years"]["years"] == ["1886", "1891"]


def test_no_evidence_no_facts():
    assert kfc.key_facts("", "X") == []


# ═════════ 2. coverage after all passes ═════════
def test_city_hall_888_lost_its_years_and_they_are_restored():
    title, sents = stop_sents("City Hall")
    assert not kfc.fact_present(sents, {"kind": "years", "years": ["1898", "1909"]})
    logs = []
    out, rep = kfc.finalize_stop(title, sents, ev("city_hall"), classify_fn=all_supported,
                                 log=logs.append)
    text = " ".join(out)
    assert "1898" in text and "1909" in text
    assert rep["k"] == rep["K"] >= 1 and rep["k_before"] < rep["k"]
    # one plain evidence sentence per missing fact; a start+completion year pair that
    # no single evidence sentence states needs its two evidence sentences
    assert 1 <= len(rep["injected"]) <= 2
    assert any("[LOCAL-889] coverage City Hall" in l and f"{rep['k']}/{rep['K']} key facts" in l
               for l in logs)


def test_opera_888_lost_the_1944_event_and_it_is_restored():
    title, sents = stop_sents("Opera")
    assert "1944" not in " ".join(sents)
    out, rep = kfc.finalize_stop(title, sents, ev("opera"), classify_fn=all_supported)
    assert "1944" in " ".join(out)
    assert rep["k"] == rep["K"]


def test_injected_sentence_is_gated_once_more():
    title, sents = stop_sents("City Hall")
    calls = []

    def reject(system, user, model):
        calls.append(user)
        return {"verdicts": [{"i": 1, "verdict": "UNSUPPORTED", "evidence": "", "legend": False}]}, 1, 1
    out, rep = kfc.finalize_stop(title, sents, ev("city_hall"), classify_fn=reject)
    assert calls and "1898" not in " ".join(out)
    assert rep["k"] < rep["K"] and rep["refused"]


def test_nothing_injected_when_all_facts_present():
    title, sents = stop_sents("Independence Palace")
    out, rep = kfc.finalize_stop(title, sents, ev("palace"), classify_fn=all_supported)
    assert rep["k_before"] <= rep["k"]
    # the dated event (30 April 1975) was already stated, so it is not injected again
    assert not any(i.startswith("event") for i in rep["injected"])


def test_thin_evidence_stop_is_left_alone():
    sents = ["We could not confirm verified historical details for this stop.",
             "Take a moment and look around you at the street.",
             "Listen for the sounds that belong to this spot."]
    out, rep = kfc.finalize_stop("Cafe", sents, "", classify_fn=all_supported)
    assert out == sents and rep["K"] == 0


# ═════════ 3. removed claims stay removed ═════════
WRM = "War Remnants Museum"
REMOVED_517 = ("The War Remnants Museum occupies the very building that served as the "
               "US military’s intelligence hea")                  # as logged (cut at 100)
CAME_BACK = "The building was once the US military's intelligence headquarters during the Vietnam War."


def test_claim_key_matches_fragment_and_restatement():
    assert kfc.deny_record(WRM, REMOVED_517, "phase5.17-gates")
    assert kfc.is_denied(WRM, CAME_BACK)
    assert not kfc.is_denied(WRM, "Inside, you find exhibits about the First Indochina War and the "
                                  "Vietnam War, covering events from 1946 to 1975.")


def test_888_final_wrm_sentence_is_dropped_again():
    title, sents = stop_sents("War Remnants")
    assert any("intelligence headquarters" in s for s in sents)       # the 888 defect
    kfc.deny_record(title, REMOVED_517, "phase5.17-gates")
    logs = []
    out, rep = kfc.finalize_stop(title, sents, ev("wrm"), classify_fn=all_supported, log=logs.append)
    assert not any("intelligence headquarters" in s for s in out)
    assert rep["denied"] >= 1      # (+ years the TRUNCATED test evidence never states)
    # the log says which evidence line backs it: the stop's OWN article body
    assert any("War Remnants Museum - Wikipedia (en)" in l and "intelligence headquarters" in l
               for l in logs)


def test_gate_drops_it_even_when_the_judge_says_supported():
    kfc.deny_record(WRM, REMOVED_517, "phase5.17-gates")
    body = CAME_BACK + " Inside, you find exhibits about the First Indochina War."
    logs = []
    out, rep = sgg.apply_grounding_gate(WRM, body, ev("wrm"), classify_fn=all_supported,
                                        log=logs.append)
    assert "intelligence" not in out and "First Indochina" in out
    assert rep["unsupported"] == 1
    assert any("came back" in l for l in logs)


def test_gate_drops_are_recorded_and_block_a_later_refill():
    def drop_first(system, user, model):
        return {"verdicts": [{"i": 1, "verdict": "CONTRADICTED", "evidence": "", "legend": False}]}, 1, 1
    s = "The palace was designed by Alfred Foulhoux in a Gothic style during 1888."
    sgg.apply_grounding_gate("Palace X", s, "Some evidence about the palace " * 3, classify_fn=drop_first)
    again = "A Gothic style palace was designed by Alfred Foulhoux during 1888."
    out, rep = kfc.strip_denied("Palace X", [again])
    assert out == [] and rep == [again]


def test_coverage_cannot_reinject_a_contradicted_claim():
    title, sents = stop_sents("City Hall")
    fact = [x for x in kfc.key_facts(ev("city_hall"), title) if x["kind"] == "years"][0]
    for lead in fact["sentences"]:
        kfc.deny_record(title, lead, "gate:CONTRADICTED")
    out, rep = kfc.finalize_stop(title, sents, ev("city_hall"), classify_fn=all_supported)
    assert "1898" not in " ".join(out) and rep["refused"]


def test_unsupported_in_a_narrow_window_may_be_restored_from_the_lead():
    title, sents = stop_sents("City Hall")
    fact = [x for x in kfc.key_facts(ev("city_hall"), title) if x["kind"] == "years"][0]
    for lead in fact["sentences"]:
        kfc.deny_record(title, lead, "gate:UNSUPPORTED")
    out, _ = kfc.finalize_stop(title, sents, ev("city_hall"), classify_fn=all_supported)
    assert "1909" in " ".join(out)


def test_record_removed_between_texts():
    before = "Stop 1: Hall\n\nA long tale of the hall was told by the guild in 1800 here. Keep this one fact too.\n"
    after = "Stop 1: Hall\n\nKeep this one fact too.\n"
    assert kfc.record_removed_between(before, after, "scrub") == 1
    assert kfc.is_denied("Hall", "The tale of the hall was told by the guild in 1800.")


# ═════════ 4. filler cap ═════════
def _filler_count(sents):
    return sum(1 for s in sents if kfc.is_sensory(s))


def test_888_post_office_filler():
    title, sents = stop_sents("Post Office")
    assert _filler_count(sents) >= 2
    out, rep = kfc.cap_filler(sents)
    assert _filler_count(out) <= 1
    assert not any("hum of voices" in s for s in out)
    assert any("vaulted iron roof" in s for s in out)               # the concrete one survives
    assert not any("a reminder of the building" in s for s in out)  # reflective tail trimmed


def test_888_pier_has_one_sensory_sentence_and_no_coexist_line():
    title, sents = stop_sents("Pier")
    out, rep = kfc.cap_filler(sents)
    assert _filler_count(out) <= 1 and not any("coexist" in s for s in out)
    assert any("solid stone and concrete" in s for s in out)        # visible detail preferred
    assert any("ferry boats" in s and "reminder" not in s for s in out)


def test_888_city_hall_garden_scent_and_palace_conceals():
    _t, ch = stop_sents("City Hall")
    out, _ = kfc.cap_filler(ch)
    assert not any("scent of tropical flowers" in s for s in out)
    _t, pal = stop_sents("Independence Palace")
    out, _ = kfc.cap_filler(pal)
    assert not any("conceals more" in s for s in out)
    assert any("30 April 1975" in s for s in out)


def test_opera_bridging_tail_is_trimmed_not_the_fact():
    _t, op = stop_sents("Opera")
    out, _ = kfc.cap_filler(op)
    assert not any("bridging past and present" in s for s in out)
    assert any("1976" in s for s in out)
    assert not any("murmur of voices" in s for s in out)


def test_filler_cue_tests_are_generic():
    assert kfc.is_reflective("The old quay is a place where past and present coexist.")
    assert kfc.is_sensory("The scent of baking bread drifts from the doorway.")
    assert not kfc.is_sensory("The hall was opened in 1909 amid the hum of a crowd.")   # a dated fact
    s = "The clock tower was rebuilt in 1951, a reminder that the town recovered."
    assert kfc.trim_reflective_tail(s) == "The clock tower was rebuilt in 1951."


def test_filler_cap_respects_the_floor_for_reflective_only():
    sents = ["A quiet lane runs here.", "Past and present coexist on this corner."]
    out, _ = kfc.cap_filler(sents)
    assert len(out) == 2


# ═════════ 5. questionable claims are UNSUPPORTED ═════════
EIFFEL = ("Although Gustave Eiffel’s name is often associated with the post office, this is a "
          "misconception that arose from his earlier work in Saigon between 1860 and 1863.")
THIEU = ("Thiệu stayed here until 21 April 1975, when he fled as North Vietnamese forces advanced.")


def test_eiffel_saigon_1860_1863_is_unsupported_by_the_recorded_evidence():
    e = ev("post_office")
    assert "1860" not in e and "erroneously credited" in e            # evidence only says that
    assert "1860" in kfc.deterministic_unsupported(EIFFEL, e)
    # the 888 delivered sentence is exactly this claim
    assert any("between 1860 and 1863" in s for s in stop_sents("Post Office")[1])


def test_year_range_needs_one_evidence_sentence_with_both_ends():
    e = "The hall was built in 1801. A fire in 1850 damaged the roof. The hall closed."
    assert kfc.deterministic_unsupported("It stood between 1801 and 1850.", e)
    assert kfc.deterministic_unsupported("It was constructed between 1886 and 1891.",
                                         ev("post_office")) is None


def test_thieu_fled_on_the_resignation_date_is_unsupported():
    e = ev("palace", extra=[PALACE_FLED] + [x for x in REC["thieu"]["relevant"] if "21 April 1975" in x])
    assert "resigned" in e
    why = kfc.deterministic_unsupported(THIEU, e)
    assert why and "resignation" in why
    # evidence that records only the resignation does not make the departure claim true;
    # evidence that records BOTH on that day does
    ok = "On 21 April 1975 he resigned and fled the country."
    assert kfc.deterministic_unsupported(THIEU, ok) is None


def test_gate_applies_the_rules_when_the_judge_says_supported():
    e = ev("post_office")
    logs = []
    out, rep = sgg.apply_grounding_gate("Post Office", EIFFEL + " It was constructed between 1886 and 1891.",
                                        e, classify_fn=all_supported, log=logs.append)
    assert "1860" not in out and "1886" in out
    assert rep["unsupported"] == 1 and any("1860" in l for l in logs)


def test_judge_verdicts_still_rule_when_they_drop():
    def contradict(system, user, model):
        return {"verdicts": [{"i": 1, "verdict": "CONTRADICTED", "evidence": "", "legend": False}]}, 1, 1
    out, rep = sgg.apply_grounding_gate("Hall", "The hall was built in 1945 by the guild.",
                                        "The hall was built in 1801 by the guild " * 2, classify_fn=contradict)
    assert rep["contradicted"] == 1 and rep["unsupported"] == 0


# ═════════ 6. whole tour + harness ═════════
def test_finalize_tour_end_to_end_on_the_888_text():
    generic = "Generic recorded evidence about this place and its surroundings. " * 3
    evmap = {"Cathedral": generic, "Book Street": generic, "Bạch Đằng Pier": generic,
             "City Hall": ev("city_hall"), "Opera House": ev("opera"),
             "War Remnants Museum": ev("wrm"), "Post Office": ev("post_office"),
             "Independence Palace": ev("palace")}
    kfc.deny_record(WRM, REMOVED_517, "phase5.17-gates")
    out, rep = kfc.finalize_tour(T888, evmap, classify_fn=all_supported)
    blocks = {t: sgg._content_sentences(sgg._block_body_prose(b)) for _n, t, b in sgg._split_blocks(out)}
    assert "intelligence headquarters" not in " ".join(blocks["War Remnants Museum"])
    assert "1898" in " ".join(blocks["City Hall"]) and "1909" in " ".join(blocks["City Hall"])
    assert "1944" in " ".join(blocks["Opera House"])
    assert all(_filler_count(b) <= 1 for b in blocks.values())
    assert all(r["k"] == r["K"] for r in rep["stops"] if r["K"])
    assert len(blocks) == 10


def test_harness_checks_city_hall_years_not_the_name():
    import run_cloud_parity_proof as h
    base = ("Stop 7: City Hall\n\nOrientation: x\n"
            "Originally known as the Hôtel de Ville de Saïgon, it served as the municipal hall. "
            "A second. A third. A fourth. A fifth one here.\n")
    res = dict(h._criteria(base, lambda *a, **k: None, require_ten=False))
    label = [k for k in res if k.startswith("City Hall")][0]
    assert res[label] is False                                       # name only: now FAILS
    good = base.replace("A second.", "It was built from 1898 to 1909.")
    res = dict(h._criteria(good, lambda *a, **k: None, require_ten=False))
    assert res[label] is True


def test_evaluate_889_reports_coverage():
    import run_cloud_parity_proof as h
    out = h.evaluate_889(T888, {"City Hall": ev("city_hall"), "Opera House": ev("opera")})
    d = {l: ok for l, ok, _ in out}
    assert d["City Hall has 1898 and 1909"] is False
    assert d["no 'intelligence headquarters'"] is False
    assert d["Opera House has 1944 if its evidence has it"] is False
    assert d["<= 1 sensory sentence per stop"] is False
