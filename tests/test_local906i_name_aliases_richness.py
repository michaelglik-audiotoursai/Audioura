"""LOCAL-906I -- one person with many spellings, the same fact at one stop, no "The <Proper>", a spoken location, thin stops
refilled. Offline, $0, generic fixtures (D769), no network, no key."""
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("SERPER_API_KEY", None)
os.environ["THIN_STOP_SEARCH"] = "0"

import delivery_bodies_905 as db905  # noqa: E402
import key_fact_coverage as kfc  # noqa: E402
import leftovers_906f as f906  # noqa: E402
import route_content_896 as rc  # noqa: E402
import strict_grounding_gate as sgg  # noqa: E402

P_FULL = "Áldo Brénn Corwín"
P_ASCII = "Aldo Brenn Corwin"
EV1 = ("In 1872, the monk %s, known by his Dharma name Sonan and title Corwin, left Central Province for a quiet retreat. "
       "He lived in a cave on the slope. After his death in 1887, a group of his followers built the lower Lumen Pagoda. "
       "The mountain rises off National Route 1 near the town of Harbin." % P_FULL)
EV2 = ("The reclining Buddha statue on Orla Mountain measures 49 meters long and 7 meters high. "
       "The statue is surrounded by forest. Pilgrims climb a stairway to reach the statue. "
       "The statue was painted white in 2013.")
EV = {"Orla Mountain": EV1, "Reclining Buddha": EV2}

STOP1 = ("The Orla Mountain's most striking feature is the vast Reclining Buddha statue, which measures 49 meters long and "
         "7 meters high. The mountain is also home to Lumen Pagoda. After his death in 1887, a group of his followers built "
         "the lower Lumen Pagoda. His presence drew followers who helped build the pagoda. "
         "Orla Mount is a mountain located off of National Route 1 in the town of Harbin, Tessel District.")
STOP2 = ("You stand before the Reclining Buddha statue on Orla Mountain, which measures 49 meters long and 7 meters high. "
         "The statue is surrounded by forest.")


def _tour(b1, b2):
    return ("Alpha - Walking Tour\nTour-Category: walking\n\n"
            "Stop 1: Orla Mountain\n\nCoordinates: 1.0, 2.0\n\nType/Specialty: Natural attraction\n\n" + b1 +
            "\n\nDirections: Walk on to Reclining Buddha.\n\n"
            "Stop 2: Reclining Buddha\n\nCoordinates: 1.0, 2.0\n\nType/Specialty: Cultural landmark\n\n" + b2 +
            "\n\nThat's 2 stops in all.\n")


def _body(text, num):
    for s, e, n, _t in rc._stop_blocks(text):
        if n == num:
            return " ".join(ln for i, ln in enumerate(text[s:e].split("\n"))
                            if i > 0 and ln.strip() and not rc._KEYED.match(ln) and not rc._CLOSING_LINE.match(ln.strip()))
    return ""


@pytest.fixture(autouse=True)
def job():
    with rc.job_scope("t906i"):
        rc.clear_route()
        rc.set_evidence_904({})
        kfc.deny_reset()
        yield


# ── 1. one person, many spellings ───────────────────────────────────────────────────────────────────────
def test_aliases_are_one_person():
    names = [P_FULL, P_ASCII, "Sonan", "Corwin"]
    ctx = "the monk %s, known by his Dharma name Sonan and title Corwin, left" % P_FULL
    out = f906._distinct(names, "Orla Mountain", ctx, "")
    assert len(out) == 1 and out[0] == P_ASCII          # the plain, longest, diacritic-free form


def test_alias_cue_alone_links_unrelated_tokens():
    out = f906._distinct(["Aldo Brenn", "Sonan"], "T", "the monk Aldo Brenn, also called Sonan, left", "")
    assert len(out) == 1
    assert len(f906._distinct(["Aldo Brenn", "Sonan"], "T", "", "")) == 2     # without the cue: two names


def test_the_spelling_the_tour_uses_is_preferred():
    out = f906._distinct([P_FULL, "Corwin"], "T", "", "Later Corwin Aldo")
    assert out == ["Corwin"] or out == [P_ASCII]           # subset merge; the variant that exists
    out2 = f906._distinct([P_FULL, P_ASCII], "T", "", "")
    assert out2[0].isascii()


def test_two_different_people_stay_ambiguous():
    t = _tour("The mountain is quiet. After his death in 1887, followers built the lower Lumen Pagoda.", STOP2)
    ev = dict(EV, **{"Orla Mountain": "The monk Aldo Brenn built a hut here. The abbot Maro Delk later enlarged it."})
    logs = []
    out = f906.repair_person_pronoun(t, ev, logs.append)
    assert "After his death" not in out
    assert any("no unambiguous name" in x for x in logs)


def test_the_pronoun_is_named_from_the_aliased_evidence():
    t = _tour("The Orla Mountain is quiet. After his death in 1887, a group of his followers built the lower Lumen Pagoda. "
              "His presence drew followers who helped build the pagoda.", STOP2)
    logs = []
    out = f906.repair_person_pronoun(t, EV, logs.append)
    b = _body(out, 1)
    assert "Aldo Brenn Corwin's death in 1887" in b, b
    assert "After his death" not in b and "His presence" in b      # the later pronouns now have their referent
    assert any("named from the evidence (%s)" % P_ASCII in x for x in logs), logs


# ── 2. the introducing sentence is not removed when the evidence states it ────────────────────────────────
def test_judge_flake_does_not_remove_a_sentence_the_evidence_states():
    s1 = "In 1872, the monk %s, known by his Dharma name Sonan and title Corwin, left Central Province for a quiet retreat." % P_FULL
    body = s1 + " Pilgrims arrive by bus."

    def cls(system, user, model, **kw):
        return ({"verdicts": [{"i": 1, "verdict": "UNSUPPORTED", "evidence": "", "legend": False}]}, 10, 5)
    logs = []
    out, rep = sgg.apply_grounding_gate("Orla Mountain", body, evidence=EV1, classify_fn=cls, log=logs.append, trust_verbatim=True)
    assert "left Central Province" in out
    assert rep["unsupported"] == 0
    assert any("[LOCAL-906I] kept" in x for x in logs)


def test_an_unstated_claim_is_still_dropped_by_the_gate():
    body = "In 1872, the monk %s founded a great library with ten thousand scrolls and a school." % P_FULL

    def cls(system, user, model, **kw):
        return ({"verdicts": [{"i": 1, "verdict": "UNSUPPORTED", "evidence": "", "legend": False}]}, 10, 5)
    out, rep = sgg.apply_grounding_gate("Orla Mountain", body, evidence=EV1, classify_fn=cls, trust_verbatim=True)
    assert "library" not in out and rep["unsupported"] == 1


# ── 3. the same fact at two stops ─────────────────────────────────────────────────────────────────────────
def test_fact_stays_at_the_statue_stop():
    logs = []
    out = f906.drop_cross_stop_fact(_tour(STOP1, STOP2), EV, logs.append)
    assert "49 meters" not in _body(out, 1)
    assert "49 meters" in _body(out, 2)
    assert "vast Reclining Buddha statue" in _body(out, 1)          # the clause is cut, the feature stays
    assert any("fact belongs to stop 2" in x for x in logs)


def test_a_stop_with_nothing_else_keeps_its_fact():
    out = f906.drop_cross_stop_fact(_tour("The Orla Mountain statue measures 49 meters long and 7 meters high.", STOP2), EV)
    assert "49 meters" in _body(out, 1)


# ── 4. no "The <Proper Name>" ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("before,after", [
    ("The Orla Mountain's most striking feature is the statue.", "Orla Mountain's most striking feature is the statue."),
    ("The <Mountain>'s most striking feature is the statue.", "<Mountain>'s most striking feature is the statue."),
    ("The Ta Cu Mountain is quiet.", "Ta Cu Mountain is quiet."),
    ("You see the Orla Mountain from here.", "You see Orla Mountain from here."),
    ("The Reclining Buddha is vast.", "The Reclining Buddha is vast."),
    ("You stand before the Reclining Buddha statue on Orla Mountain.", "You stand before the Reclining Buddha statue on Orla Mountain."),
    ("The Great Hill is steep.", "The Great Hill is steep."),
    ("The mountain is steep.", "The mountain is steep."),
])
def test_proper_name_takes_no_article(before, after):
    assert f906.strip_proper_article(before) == after


# ── 5. an encyclopedia lead becomes a spoken location ─────────────────────────────────────────────────────
def test_lead_is_spoken():
    t = _tour("The mountain is quiet. Orla Mount is a mountain located off of National Route 1 in the town of Harbin, "
              "Tessel District. Mist covers the slope.", STOP2)
    out = f906.drop_encyclopedia_leads(t, None)
    b = _body(out, 1)
    assert "Orla Mountain lies off National Route 1 in the town of Harbin" in b, b
    assert "is a mountain located" not in b and "Mount Mount" not in b and "Orla Mount " not in b


def test_lead_is_dropped_when_the_stop_already_says_where():
    t = _tour("The mountain rises near the coast. Orla Mount is a mountain located off of National Route 1 in the town of "
              "Harbin. Mist covers the slope.", STOP2)
    assert "is a mountain" not in f906.drop_encyclopedia_leads(t, None)


# ── 6. thin stop refill ───────────────────────────────────────────────────────────────────────────────────
def test_thin_stop_is_refilled_from_the_evidence():
    ev = {"Orla Mountain": ("The mountain rises off National Route 1 near the town of Harbin. A stairway of 600 steps leads "
                            "to the summit shrine. Fog gathers in the valley every morning during the wet season. "
                            "He founded the shrine long ago. Book a tour today with our guides."),
          "Reclining Buddha": EV2}
    t = _tour("Mist covers the slope. The trail is steep.", STOP2)
    logs = []
    out = f906.refill_thin_stops(t, ev, logs.append)
    b = _body(out, 1)
    assert len(rc.split_sentences(b)) == 5, b
    assert "He founded" not in b and "Book a tour" not in b
    assert any("[LOCAL-906I] thin after removals" in x for x in logs)
    assert f906.refill_thin_stops(t, {}, None) == t       # no evidence: nothing invented


# ── replay of the logged shape ────────────────────────────────────────────────────────────────────────────
def test_replay_stop_1():
    t = _tour(STOP1, STOP2)
    logs = []
    out = db905.ensure_bodies(t, EV, logs.append)
    b1, b2 = _body(out, 1), _body(out, 2)
    assert "After his death" not in b1 and "His presence drew followers" in b1, b1   # named, not dropped
    assert "Aldo Brenn Corwin's death in 1887" in b1, b1
    assert out.count("49 meters") == 1 and "49 meters" in b2           # the fact once, at the statue stop
    assert not re.search(r"\bThe Orla Mountain", out)
    assert "Orla Mountain lies off National Route 1" in b1 or "rises off National Route 1" in b1, b1
    assert "is a mountain located" not in out and "Mount Mount" not in out
    assert len(rc.split_sentences(b1)) >= 4, b1


def test_lead_verbatim_never_drops_a_qualifier():
    """[LEAD review] 'the largest' is not the evidence's 'one of the largest'; 'was built' is not 'was not built'."""
    import key_fact_coverage as kfc
    ev = "The statue is one of the largest reclining Buddhas in <Region>, 49 meters long. The pagoda was not built in 1872 by the monk."
    assert kfc.verbatim_supported("The statue is the largest reclining Buddhas in <Region>, 49 meters long.", ev) is None
    assert kfc.verbatim_supported("The pagoda was built in 1872 by the monk himself.", ev) is None
    assert kfc.verbatim_supported("The statue is one of the largest reclining Buddhas in <Region>, 49 meters long.", ev)
