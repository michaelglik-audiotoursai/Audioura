#!/usr/bin/env python3
"""LOCAL-888 — coherence after the grounding gate drops sentences, the evidence-fed
refill (873C trigger), the dated signature event, the Café regression (stop
snippets reach the gate), the meter guard and the harness Eiffel check.

Fully offline; generic fixtures only (no venue names in the code under test, D769).
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import meter_guard as mg                      # noqa: E402
import stop_coherence as sc                   # noqa: E402
import strict_grounding_gate as sgg           # noqa: E402


# ═════════════ 1. dangling references / orphan openers ═════════════
def test_demonstrative_without_antecedent_is_flagged():
    sents = ["Installed in 1959, this statue replaced an older figure.",
             "The square is the city's point zero."]
    iss = sc.dangling_reference_issues(sents, "Old Cathedral", "Lyon")
    assert [i for i, _k, _f in iss] == [0]


def test_demonstrative_with_antecedent_is_fine():
    sents = ["A bronze statue was set up in front of the church in 1850.",
             "Installed in 1959, this statue replaced an older figure."]
    assert sc.dangling_reference_issues(sents, "Old Cathedral", "Lyon") == []


def test_rollup_and_echoes_openers_are_flagged():
    sents = ["The mill closed in 1901.",
             "The echoes of that upheaval remain in the walls.",
             "Together, these landmarks map out the town's journey."]
    kinds = {i: k for i, k, _f in sc.dangling_reference_issues(sents, "Mill", "Leeds")}
    assert kinds[1] == "demonstrative" and kinds[2] == "lead-in"


def test_deixis_of_the_stop_itself_is_not_dangling():
    sents = ["You are standing at the harbour wall.",
             "This spot was the town's first landing in 1702."]
    assert sc.dangling_reference_issues(sents, "Harbour Wall", "Bergen") == []


def test_those_final_hours_is_flagged():
    sents = ["The garrison surrendered at dawn on 3 May 1813.",
             "Those final hours were recorded by a clerk."]
    assert [i for i, _k, _f in sc.dangling_reference_issues(sents, "Fort", "Riga")] == [1]


# ═════════════ 2. bare surnames before the full name ═════════════
EV_NAME = ("President Pedro Alvares Calderon ordered the fortress rebuilt in 1862. "
           "The fortress faces the Estero River.")


def test_bare_surname_without_full_name_is_flagged():
    sents = ["Calderon fled the capital in 1871.", "You can see the walls today."]
    assert sc.bare_surname_issues(sents, EV_NAME, "Fortress", "Lima") == [(0, "Calderon")]


def test_full_name_first_clears_bare_surname():
    sents = ["Pedro Alvares Calderon ordered the walls rebuilt in 1862.",
             "Calderon fled the capital in 1871."]
    assert sc.bare_surname_issues(sents, EV_NAME, "Fortress", "Lima") == []


def test_place_words_are_not_treated_as_surnames():
    ev = "The Estero River flows past the fortress built in 1862."
    sents = ["The fortress overlooks the Estero all year."]
    assert sc.bare_surname_issues(sents, ev, "Fortress", "Lima") == []


# ═════════════ 3. the dated signature event ═════════════
EV_EVENT = ("Fort Alder - Wikipedia (en). Fort Alder is a stone fortress above the bay. "
            "It was captured by the militia on 4 March 1781 after a three-day siege. "
            "The fort was repaired in 1790.")


def test_signature_event_found_in_lead_with_full_date():
    ev = sc.signature_event(EV_EVENT)
    assert ev and (ev["day"], ev["month"], ev["year"]) == (4, "mar", 1781)


def test_event_must_be_stated_plainly_with_the_date():
    ev = sc.signature_event(EV_EVENT)
    allusion = ["The fort changed hands during the revolution.", "It was repaired in 1790."]
    plain = ["On 4 March 1781 the militia captured the fort after a three-day siege."]
    assert not sc.states_event(allusion, ev)
    assert sc.states_event(plain, ev)
    assert sc.states_event(["The militia took it on March 4, 1781."], ev)


def test_no_event_when_lead_has_no_full_date():
    assert sc.signature_event("Fort Alder - Wikipedia (en). A stone fort built in 1700.") is None


def test_insert_event_sentence_keeps_chronology():
    ev = sc.signature_event(EV_EVENT)
    out = sc.insert_event_sentence(["Built in 1700.", "Repaired in 1790."], ev)
    assert out[1].startswith("It was captured by the militia on 4 March 1781")


# ═════════════ 4. the gate: refill is fed evidence, coherence pass ═════════════
def _all_supported(system, user, model, **kw):
    n = len(re.findall(r"(?m)^\d+\. ", user))
    return ({"verdicts": [{"i": i, "verdict": "SUPPORTED", "evidence": "e", "legend": False}
                          for i in range(1, n + 1)]}, 80, 40)


TOUR = ("Stop 1: Fort Alder\n"
        "Orientation: You reach the bay wall.\n"
        "Installed in 1790, this gatehouse replaced an older one. "
        "The echoes of that siege remain in the walls.\n"
        "Directions: Continue to the next stop.\n")


def test_refill_receives_evidence_sentences_when_no_thin_facts():
    """873C 'did not run': the gate's rebuild got [] for stops without thin facts."""
    seen = {}

    def rebuild(title, facts):
        seen["facts"] = list(facts)
        return ["The fort stands above the bay.", "It was captured in 1781.",
                "It was repaired in 1790.", "A gatehouse was added in 1790.",
                "The walls are of local stone."]
    ev = {"Fort Alder": EV_EVENT}

    def cls(system, user, model, **kw):
        return ({"verdicts": [{"i": 1, "verdict": "UNSUPPORTED", "evidence": "", "legend": False},
                              {"i": 2, "verdict": "UNSUPPORTED", "evidence": "", "legend": False}]},
                50, 20) if "FACTUAL SENTENCES" in user and "gatehouse replaced" in user \
            else _all_supported(system, user, model)
    out, rep = sgg.ground_tour_text(TOUR, ev, classify_fn=cls, rebuild_fn=rebuild,
                                    max_cost_usd=1.0)
    assert seen["facts"], "rebuild must be handed the evidence's fact sentences"
    assert any("4 March 1781" in f for f in seen["facts"])
    assert rep["rebuilt"] == 1


def test_coherence_pass_renarrates_and_states_event():
    tour = ("Stop 1: Fort Alder\n"
            "Orientation: You reach the bay wall.\n"
            "Installed in 1790, this gatehouse replaced an older one. "
            "The fort was repaired in 1790. The bay is wide and grey today. "
            "You can hear gulls on the wall.\n"
            "Directions: Continue.\n")
    calls = []

    def narrate(system, user, model):
        calls.append(user)
        assert "REQUIRED EVENT" in user and "4 March 1781" in user
        return ({"sentences": [
            "Fort Alder is a stone fortress above the bay.",
            "On 4 March 1781 the militia captured it after a three-day siege.",
            "The fort was repaired in 1790.",
            "The bay is wide and grey today.",
            "You can hear gulls on the wall."]}, 200, 90)
    out, rep = sgg.ground_tour_text(tour, {"Fort Alder": EV_EVENT},
                                    classify_fn=_all_supported, coherence=True,
                                    narrate_fn=narrate, max_cost_usd=1.0)
    assert len(calls) == 1
    assert "On 4 March 1781 the militia captured it" in out
    assert "this gatehouse" not in out
    assert rep["coherence_fixed"] == 1


def test_event_inserted_deterministically_when_renarration_fails():
    tour = ("Stop 1: Fort Alder\nOrientation: x.\n"
            "The fort was repaired in 1790. The bay is wide and grey today. "
            "You can hear gulls on the wall. A cafe now stands near the gate.\n"
            "Directions: Continue.\n")
    out, rep = sgg.ground_tour_text(
        tour, {"Fort Alder": EV_EVENT}, classify_fn=_all_supported, coherence=True,
        narrate_fn=lambda s, u, m: (None, 0, 0), max_cost_usd=1.0)
    assert "captured by the militia on 4 March 1781" in out
    assert rep["coherence"][0]["event_inserted"] is True


def test_clean_stop_makes_no_extra_call():
    tour = ("Stop 1: Fort Alder\nOrientation: x.\n"
            "Fort Alder is a stone fortress above the bay. "
            "On 4 March 1781 the militia captured it. It was repaired in 1790. "
            "The bay is wide and grey today. You can hear gulls on the wall.\n"
            "Directions: Continue.\n")
    n = {"c": 0}

    def narrate(s, u, m):
        n["c"] += 1
        return (None, 0, 0)
    sgg.ground_tour_text(tour, {"Fort Alder": EV_EVENT}, classify_fn=_all_supported,
                         coherence=True, narrate_fn=narrate, max_cost_usd=1.0)
    assert n["c"] == 0


def test_no_evidence_stop_gets_a_disclosed_sensory_body_of_four():
    tour = ("Stop 1: Nameless Corner\nOrientation: x.\n"
            "It was founded in 1163 by a monk named Ansel. Take a moment here.\n"
            "Directions: Continue.\n")
    out, rep = sgg.ground_tour_text(tour, {}, classify_fn=_all_supported, max_cost_usd=1.0)
    body = sgg._block_body_prose(sgg._block_for(out, 1))
    sents = sgg._content_sentences(body)
    assert len(sents) >= 4
    assert "1163" not in out and "Ansel" not in out
    assert "could not confirm verified historical details" in out
    assert not any(sgg.is_factual_sentence(s) for s in sents[:-1])


# ═════════════ 5. Café regression: the stop's snippets reach the gate ═════════════
def test_snippets_become_evidence_texts():
    snips = [{"title": "Corner Cafe", "snippet": "Built in the 1960s as an officers' dormitory."},
             {"title": "", "snippet": "Now a cafe hub."}, "plain string", None, {}]
    out = sc.snippets_as_evidence_texts(snips)
    assert out[0].startswith("Corner Cafe Built in the 1960s")
    assert "Now a cafe hub." in out and "plain string" in out


def test_generator_records_stop_snippets_in_the_gate_sink():
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "generate_tour_text.py"), encoding="utf-8").read()
    assert "snippets_as_evidence_texts(_stop_snippets)" in src
    assert "_wiki_evidence_sink_record(\n                        _J._THIN_SINK_KEY, poi_name,\n                        snippets_as_evidence_texts" in src
    assert "_thin_sink_record(_J._THIN_SINK_KEY, _ek, _ev)" in src      # escalated facts too


def test_rebuild_report_exposes_escalated_facts():
    import thin_stop_delivery as tsd
    tour = "Stop 1: Plain Corner\nOrientation: x.\nA short body here.\nDirections: Go.\n"
    facts = [{"text": "Plain Corner was built in 1901 as a grain store."}]
    _, rep = tsd.rebuild_thin_delivered_stops(
        tour, "Leeds", escalate_fn=lambda *a, **k: {"facts": facts, "cost_usd": 0.0},
        narrate=False, fact_filter=None)
    assert rep.get("facts_by_title", {}).get("Plain Corner") == facts


def test_evidence_fact_sentences_picks_dated_and_named_sentences():
    out = sc.evidence_fact_sentences(EV_EVENT)
    assert any("1781" in s for s in out)
    assert all(len(s) >= 30 for s in out)


# ═════════════ 6. the meter ═════════════
LOG = ("  [LOCAL-883] grounding Cathedral: labelled 6, 2 kept\n"
       "  [LOCAL-883] grounding Post Office: labelled 6, 3 kept\n"
       "  [LOCAL-873C] delivered-body thin check: stop 10 'Thi Bar' NARRATED from facts\n")


def test_meter_undercount_is_loud_and_never_zero():
    v = mg.check_meter(rows_captured=0, usd_captured=0.0, run_log=LOG, audit_ran=True)
    assert v["ok"] is False and "METER FAILURE" in v["message"]
    assert v["record_usd"] >= mg.EST_FLOOR_IF_UNMETERED > 0


def test_meter_sound_run_records_metered_amount():
    v = mg.check_meter(rows_captured=40, usd_captured=0.071, run_log=LOG, audit_ran=True)
    assert v["ok"] and v["record_usd"] == 0.071


def test_meter_partial_capture_records_at_least_the_estimate():
    v = mg.check_meter(rows_captured=1, usd_captured=0.015, run_log=LOG, audit_ran=True)
    assert not v["ok"] and v["record_usd"] >= v["estimate_usd"] >= 0.06


def test_repoint_meter_log_updates_an_already_imported_module(tmp_path, monkeypatch):
    import types
    fake = types.SimpleNamespace(LOG="/meterlogs/paid_api_calls.jsonl")
    monkeypatch.setitem(sys.modules, "paid_api_meter", fake)
    target = str(tmp_path / "calls.jsonl")
    assert mg.repoint_meter_log(target) is True
    assert fake.LOG == target and os.environ["PAID_API_LOG"] == target
    monkeypatch.delenv("PAID_API_LOG", raising=False)


def test_meter_rows_counts_only_new_rows(tmp_path):
    p = tmp_path / "m.jsonl"
    p.write_text("\n".join(json.dumps({"usd": u}) for u in (0.01, 0.02, 0.03)) + "\n")
    assert mg.meter_rows(str(p), skip_rows=1) == (2, 0.05)
    assert mg.meter_rows(str(tmp_path / "none.jsonl")) == (0, 0.0)


# ═════════════ 7. harness false negative ═════════════
def test_eiffel_negation_is_a_correction():
    import run_cloud_parity_proof as h
    ok = "The post office was designed not by eiffel but by alfred foulhoux."
    bad = "The post office was designed by eiffel."
    assert re.search(h._EIFFEL_CORRECTION_RE, ok)
    assert not re.search(h._EIFFEL_CORRECTION_RE, bad)
