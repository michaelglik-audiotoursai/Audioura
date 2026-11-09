"""test_local878_never_empty_post_office.py — LOCAL-878 Bug 2.

Tour 547, stop 2 "Post Office" shipped EMPTY (I-CON 1.00) although the log said
evidence was "fed to the narrator". A stop that has verified evidence must produce
narration from that evidence (STOP_PIPELINE step 8 / D760): if the claim gate removes
every sentence, the stop is regenerated ONCE from the evidence alone — never shipped
empty.

Here we reproduce the empty result with the exact shape of the 547 Post Office stop
(its narration is all unsourced claims the gate drops) and assert the gate fills it
from the Saigon Central Post Office Wikipedia evidence, so it is NOT empty. We also
confirm that once the LOCAL-878 geo-gate supplies the CORRECT article, the short form
carries the post office's real facts.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import landmark_claim_gate as lg  # noqa: E402
import landmark_wikipedia_evidence as lw  # noqa: E402

LOC = "Ho Chi Minh City, Vietnam"

# The Saigon Central Post Office article, as the geo-gated evidence lookup returns it.
POST = ("Saigon Central Post Office - Wikipedia (en). The Saigon Central Post Office is a "
        "post office in Ho Chi Minh City, built between 1886 and 1891 in the French colonial "
        "style. It was designed by Alfred Foulhoux.\n"
        "Infobox: architect: Alfred Foulhoux; years built: 1886–1891; style: French colonial")


def test_post_office_all_dropped_is_filled_from_evidence_not_empty():
    # The narration the model produced is flagged unsourced end-to-end (the verifier
    # marked every sentence), so the per-sentence scrub empties the stop; it would
    # otherwise ship empty.
    s1 = "The post office was built in 1885 by a mysterious benefactor."
    s2 = "A secret tunnel once ran beneath it to the river."
    t = (f"Stop 1: Saigon Central Post Office\n{s1} {s2}\n\n"
         "Stop 2: Ben Thanh Market\nThe market is a long-standing landmark of the old quarter.\n")
    out, rep = lg.filter_tour_text(
        t, stop_titles={1: "Saigon Central Post Office", 2: "Ben Thanh Market"},
        stop_evidence={1: [POST]}, stop_authority={1: [POST]},
        stop_flagged={1: [s1, s2]}, location=LOC)
    first = out.split("Stop 2")[0]
    # Every original sentence was dropped, and the stop was refilled from evidence.
    assert rep["dropped"] >= 2
    body = first.split("Saigon Central Post Office")[-1]
    assert lg._has_real_sentence(body), "Post Office must not ship empty when evidence exists"
    assert rep.get("filled") and rep["filled"][0]["source"] == "wikipedia"
    assert "secret tunnel" not in first.lower() and "mysterious benefactor" not in first.lower()
    assert "1886" in first or "1891" in first or "Foulhoux" in first


def test_short_form_produces_sentences_from_post_office_evidence():
    sf = lw.short_form("Saigon Central Post Office", [POST])
    assert sf and len(sf) > 20
    assert "post office" in sf.lower()


def test_empty_post_office_with_evidence_never_ships_empty():
    # Stop body is empty to begin with (narrator returned nothing) but evidence exists.
    t = ("Stop 1: Saigon Central Post Office\n\n"
         "Stop 2: Ben Thanh Market\nA market with many stalls in the old quarter today.\n")
    out, rep = lg.filter_tour_text(
        t, stop_titles={1: "Saigon Central Post Office", 2: "Ben Thanh Market"},
        stop_evidence={1: [POST]}, stop_authority={1: [POST]}, location=LOC)
    first = out.split("Stop 2")[0]
    body = first.split("Saigon Central Post Office")[-1]
    assert lg._has_real_sentence(body), "Post Office must not ship empty when evidence exists"
    assert rep["filled"][0]["source"] == "wikipedia"


def test_geo_gated_lookup_feeds_the_right_post_office_to_the_fill():
    # End-to-end of Bug 1 + Bug 2: the geo-gated evidence lookup (HCMC pin) returns the
    # Saigon post office, and that evidence fills the emptied stop.
    SAI_POST = {
        "title": "Saigon Central Post Office",
        "lead": "Saigon Central Post Office is a post office in Ho Chi Minh City, built "
                "1886–1891 in the French colonial style, designed by Alfred Foulhoux.",
        "wikitext": "{{Infobox building\n| architect = Alfred Foulhoux\n| opened = 1891\n}}",
        "langlinks": [], "coord": (10.779840, 106.699097), "qid": "Q1319076",
    }

    def fetch(name, lang):
        return {"pages": [SAI_POST]}

    ev = lw.evidence_for("Post Office", LOC, langs=["en"], fetch_fn=fetch,
                         use_cache=False, pin=(10.779840, 106.699097))
    assert ev and "Saigon Central Post Office" in ev[0]
    sf = lw.short_form("Post Office", ev)
    assert sf and "post office" in sf.lower()
