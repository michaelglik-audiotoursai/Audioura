"""LOCAL-872 -- landmark / walking claim gate.

Built from the exact tour-544 case: the Saigon Opera House user stop shipped
"staged productions of Miss Saigon" with no source.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import landmark_claim_gate as lg  # noqa: E402

TITLE = "Saigon Opera House"
# What the research for the stop actually says (built 1900, Ferret + Olivier).
EVID = [
    "Saigon Opera House - Wikipedia. The Saigon Opera House, also the Municipal Theatre of "
    "Ho Chi Minh City, was built in 1900 by the French architects Eugene Ferret and Felix "
    "Olivier in the Flamboyant Gothic style on Lam Son Square.",
    "The Opera House served as the home of the Lower House of South Vietnam from 1955 to 1975.",
]
MISS_SAIGON = ("Over the decades the Opera House has staged productions of Miss Saigon, "
               "drawing audiences from around the world.")
BUILT = "Built in 1900 by Eugène Ferret, the theatre is a showpiece of French colonial design."


def _body(*sentences):
    return "Orientation: Stand on Lam Son Square. " + " ".join(sentences)


def test_exact_miss_saigon_sentence_is_dropped_with_log_form():
    body = _body(BUILT, MISS_SAIGON, "It remains a working theatre today.")
    new, removed = lg.filter_stop_body(body, EVID, TITLE, location="Ho Chi Minh City, Vietnam")
    assert "Miss Saigon" not in new
    assert any("Miss Saigon" in r["sentence"] and r["kind"] == "production" for r in removed)
    # the checker's log form
    r = next(r for r in removed if r["kind"] == "production")
    assert lg.claim_span_lines(r["kind"], r["claim"], r["sentence"]).startswith("UNSOURCED: '")


def test_sourced_built_1900_by_ferret_is_kept():
    body = _body(BUILT)
    new, removed = lg.filter_stop_body(body, EVID, TITLE, location="Ho Chi Minh City, Vietnam")
    assert "1900" in new and "Ferret" in new and not removed


def test_unsourced_year_or_architect_is_dropped():
    # 872B: a plausible claim about the venue's OWN history is disclosed, not dropped
    # (see tests/test_local872b_...); a performer/production is still dropped.
    new, removed = lg.filter_stop_body(
        _body("The tenor Pierre Dubois sang here in 1887."), EVID, TITLE)
    assert "Dubois" not in new and removed


def test_disclosed_sentence_is_kept():
    s = "It is sometimes said that the Opera House staged productions of Miss Saigon."
    new, removed = lg.filter_stop_body(_body(s), EVID, TITLE)
    assert "Miss Saigon" in new and not removed


def test_production_needs_source_naming_show_AND_venue():
    # a source about the show alone (a Manila theatre), and the venue alone: not enough
    only_show = EVID + ["Miss Saigon is a musical by Schonberg and Boublil that opened in London in 1989."]
    new, removed = lg.filter_stop_body(_body(MISS_SAIGON), only_show, TITLE)
    assert "Miss Saigon" not in new and removed
    # a source naming both, close together: kept
    both = EVID + ["In 2019 the Saigon Opera House staged productions of Miss Saigon "
                   "for the first time in Vietnam."]
    new, removed = lg.filter_stop_body(_body(MISS_SAIGON), both, TITLE)
    assert "Miss Saigon" in new and not removed


def test_production_alias_opera_house_counts_as_the_venue():
    both = ["The Opera House hosted a gala performance of Swan Lake in 1998."]
    s = "The theatre has staged Swan Lake."
    # alias 'opera house' is the last two words of the stop title
    new, removed = lg.filter_stop_body(s, both, TITLE)
    assert "Swan Lake" in new and not removed


def test_quoted_production_is_checked():
    s = 'The hall premiered "Les Miserables" in a gala season.'
    new, removed = lg.filter_stop_body(s, EVID, TITLE)
    assert removed and "Miserables" not in new


def test_pronoun_followup_goes_with_the_dropped_sentence():
    body = _body(MISS_SAIGON, "This production drew packed houses.", "The foyer is marble.")
    new, removed = lg.filter_stop_body(body, EVID, TITLE)
    assert "packed houses" not in new and "foyer is marble" in new


def test_named_performer_unsourced_dropped_sourced_kept():
    s = "The soprano Maria Callas sang here in 1960."
    new, removed = lg.filter_stop_body(s, EVID, TITLE)
    assert removed and "Callas" not in new
    new2, removed2 = lg.filter_stop_body(s, EVID + ["Maria Callas sang at the Opera House in 1960."], TITLE)
    assert "Callas" in new2 and not removed2


def test_named_event_unsourced_dropped():
    s = "The hall hosted the Geneva Conference delegates."
    new, removed = lg.filter_stop_body(s, EVID, TITLE)
    assert removed
    new2, removed2 = lg.filter_stop_body(s, EVID + ["The Geneva Conference delegates met near the hall."], TITLE)
    assert not removed2


def test_plain_description_untouched():
    s = ("The facade has carved garlands and a pair of caryatids. "
         "Walk around the square to see the theatre from three sides.")
    new, removed = lg.filter_stop_body(s, [], TITLE)
    assert new == s and not removed


def test_labels_and_structure_untouched():
    body = ("Coordinates: 10.77, 106.70\nAddress: 7 Lam Son Square\n\n"
            "Orientation: Stand at the steps.\n\n" + MISS_SAIGON + " The roof is copper.")
    new, removed = lg.filter_stop_body(body, EVID, TITLE)
    assert "Coordinates: 10.77, 106.70" in new and "Address: 7 Lam Son Square" in new
    assert "Orientation: Stand at the steps." in new
    assert "Miss Saigon" not in new and "roof is copper" in new


def test_tour_text_end_to_end_skips_business_stop():
    text = ("Welcome.\n\nStop 1: Saigon Opera House\n" + _body(BUILT, MISS_SAIGON) +
            "\n\nStop 2: Thi Bar\n" + _body("The bar staged productions of Miss Saigon.") + "\n")
    new, rep = lg.filter_tour_text(text, stop_evidence={1: EVID, 2: []},
                                   stop_titles={1: TITLE, 2: "Thi Bar"}, skip_stops=[2])
    assert "Miss Saigon" in new.split("Stop 2:")[1]         # covered by 855D, not here
    assert "Miss Saigon" not in new.split("Stop 2:")[0]
    assert rep["dropped"] == 1 and rep["scanned"] == 1 and rep["stops"] == 2


def test_idempotent():
    body = _body(BUILT, MISS_SAIGON)
    once, _ = lg.filter_stop_body(body, EVID, TITLE)
    twice, r2 = lg.filter_stop_body(once, EVID, TITLE)
    assert once == twice and not r2


def test_opera_house_keeps_five_sentences_when_sourced():
    body = _body(
        "The Saigon Opera House was built in 1900 by Eugène Ferret and Félix Olivier.",
        "It opened to a French colonial audience on Lam Son Square.",
        "The facade borrows from the Petit Palais in Paris.",
        "From 1955 to 1975 the building housed the Lower House of South Vietnam.",
        "Walk up the steps and look at the carved garlands over the door.",
        MISS_SAIGON)
    new, removed = lg.filter_stop_body(body, EVID + ["The facade resembles the Petit Palais in Paris."],
                                       TITLE, location="Ho Chi Minh City, Vietnam")
    n = len([s for s in new.replace("Orientation: Stand on Lam Son Square.", "").split(".") if s.strip()])
    assert n >= 5 and "Miss Saigon" not in new and "1900" in new and "Ferret" in new


def test_place_names_and_style_words_are_not_people():
    ev = ["Hoan Kiem Lake is a lake in the historical center of Hanoi."]
    for s in ("Across the water a bridge leads to an island crowned by Ngoc Son Temple.",
              "The hall is inspired by Gothic and Renaissance motifs.",
              "The roofline is crowned by Pagoda Gate towers."):
        new, removed = lg.filter_stop_body(s, ev, "Hoan Kiem Lake")
        assert new == s and not removed, (s, removed)


def test_possessive_place_is_not_a_production():
    s = "The opera house brought tours of European performance venues to Saigon's bustling center."
    new, removed = lg.filter_stop_body(s, EVID, TITLE, location="Ho Chi Minh City, Vietnam")
    assert new == s and not removed


def test_generate_tour_text_is_wired_for_the_walking_path():
    src = open(os.path.join(os.path.dirname(__file__), "..", "generate_tour_text.py"),
               encoding="utf-8").read()
    assert src.count("landmark_claim_gate") >= 2          # first pass + final-text re-apply
    assert "tour_category != 'museum' and os.environ.get('LANDMARK_CLAIM_GATE'" in src
    assert "classify_stop_kind as _csk872" in src          # business user stops stay with 855D
