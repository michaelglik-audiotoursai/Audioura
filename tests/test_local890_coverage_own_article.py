#!/usr/bin/env python3
"""LOCAL-890 — the 889 coverage pass must take key facts from the stop's OWN article only,
splice into the BODY only, place a dated event chronologically and naturally, drop next-stop
previews and orphan openers, reject garbled sentences, and ground the 'Specific Examples'
header. Offline. Generic fixtures for the unit tests (no venue name in the code under test,
D769); the replay uses the LEAD 889 text (tests/fixtures/local890_lead889_saigon.txt) with the
recorded evidence of tests/fixtures/local889_recorded.json + local890_recorded.json."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import key_fact_coverage as kfc                   # noqa: E402
import strict_grounding_gate as sgg               # noqa: E402
import test_local889_key_facts as T889            # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
R890 = json.load(open(os.path.join(HERE, "fixtures", "local890_recorded.json"), encoding="utf-8"))
LEAD889 = open(os.path.join(HERE, "fixtures", "local890_lead889_saigon.txt"), encoding="utf-8").read()

all_supported = T889.all_supported


def art(title, lead, passages=(), lang="en"):
    t = f"{title} - Wikipedia ({lang}). {lead}"
    if passages:
        t += "\nPassages: [History] " + " ".join(passages)
    return t


CITY = art("Riverton", "Riverton is a city on the Aldan river. It has a long port history.",
           ["On 3 May 1944, the city was bombed by air raids and the harbour burned.",
            "The mayor resigned in 1951."])
SNIPPET = ("Some Street On 3 May 1944, the city was bombed by air raids and the harbour burned. "
           "Some Street is a pedestrian lane with cafes and stalls.")


# ═════════ 1. key facts come ONLY from the stop's own article ═════════
def test_street_with_only_a_city_article_has_no_key_facts():
    assert kfc.own_article(CITY, "Some Street") is None
    assert kfc.key_facts(CITY, "Some Street") == []


def test_street_with_only_a_snippet_has_no_key_facts():
    assert kfc.key_facts(SNIPPET, "Some Street") == []
    assert kfc.own_prose_sentences(SNIPPET, "Some Street") == []


def test_street_bundle_with_city_article_event_is_not_injected():
    body = ["You are standing on Some Street, a pedestrian lane in the old town.",
            "Stalls and cafes line both sides of the lane.",
            "Locals meet here in the evening to talk and eat.",
            "The lane is closed to cars all day."]
    out, rep = kfc.finalize_stop("Some Street", body, CITY + " " + SNIPPET, classify_fn=all_supported)
    assert rep["K"] == 0 and rep["injected"] == []
    assert out == body                          # nothing injected, nothing lost


NEIGHBOUR = art("Elm Square", "Elm Square is a small square that surrounds the Old Cathedral.",
                ["In May 1964, the government renamed it Kennedy Square after the president.",
                 "In 1903, a statue was raised in the middle of the square."])
OWN = art("Saint Rowan Basilica",
          "Saint Rowan Basilica is a cathedral in the old town. It was built between 1877 and 1880. "
          "The cathedral was designed by architect Henri Varnier.",
          ["In 1944, the cathedral was damaged by air raids and its roof burned.",
           "A bronze statue was added in 1959 and still stands in the forecourt."])


def test_neighbour_article_is_not_the_own_article():
    for bundle in (OWN + " " + NEIGHBOUR, NEIGHBOUR + " " + OWN):
        a = kfc.own_article(bundle, "Old Cathedral")
        assert a is not None and a["title"] == "Saint Rowan Basilica"
        sents = " ".join(f["sentence"] for f in kfc.key_facts(bundle, "Old Cathedral"))
        assert "Kennedy" not in sents and "1964" not in sents and "1903" not in sents


def test_event_must_be_about_the_stop_pronoun_object_is_not():
    a = kfc.own_article(NEIGHBOUR, "Elm Square")
    assert not kfc.about_stop("In May 1964, the government renamed it Kennedy Square.", "Old Cathedral", a)
    a2 = kfc.own_article(OWN, "Old Cathedral")
    assert kfc.about_stop("In 1944, the cathedral was damaged by air raids.", "Old Cathedral", a2)
    assert kfc.about_stop("It was also the site of the coup on 3 May 1944.", "Old Cathedral", a2)


def test_foreign_event_in_a_neighbours_sentence_is_never_the_key_event():
    ev = art("Saint Rowan Basilica", "Saint Rowan Basilica is a cathedral in the old town. "
             "It was built between 1877 and 1880.",
             ["In May 1964, the government renamed the neighbouring square Kennedy Square."])
    kinds = {f["kind"] for f in kfc.key_facts(ev, "Old Cathedral")}
    assert "event" not in kinds


# ═════════ 2. splice correctly ═════════
HDR_TOUR = """Stop 1: Old Cathedral

Coordinates: 1.000000, 2.000000

Type/Specialty: Historic Landmark

Specific Examples: Stone towers

You stand before the cathedral. The roof is steep. Pigeons sit on the ledge. Stalls sell flowers nearby.

Directions: Head east for 200 meters, and you'll arrive at the next stop. Enjoy the stroll!
"""


def test_injection_goes_into_the_body_never_into_header_lines():
    ev = OWN
    out, rep = kfc.finalize_tour(HDR_TOUR, {"Old Cathedral": ev}, classify_fn=all_supported)
    assert rep["stops"][0]["injected"], rep
    lines = out.split("\n")
    for ln in lines:
        if re.match(r"(?i)^(Coordinates|Type/Specialty|Specific Examples|Orientation|Directions):", ln):
            assert not re.search(r"\b(1877|1880|1944|Varnier)\b", ln), ln
    assert "Coordinates: 1.000000, 2.000000" in lines
    assert "Type/Specialty: Historic Landmark" in lines
    assert any(l.startswith("Directions: Head east for 200 meters") for l in lines)
    body = " ".join(sgg._content_sentences(sgg._block_body_prose(out)))
    assert "1880" in body


def test_header_splice_is_repaired_and_idempotent():
    t = ("Stop 1: City Hall\nCoordinates: 1.0, 2.0\nType/Specialty: Government Building\n"
         "Specific Examples: Imposing architecture, illuminated at night The building before you was "
         "designed by an architect and completed in 1908, opening in 1909.\n\nIts construction began in 1898.\n"
         "Directions: Head east.\n")
    fixed, n = kfc.repair_header_splices(t)
    assert n == 1
    assert "Specific Examples: Imposing architecture, illuminated at night\n" in fixed
    assert "\n\nThe building before you was designed by an architect and completed in 1908, opening in 1909." in fixed
    again, n2 = kfc.repair_header_splices(fixed)
    assert n2 == 0 and again == fixed
    t2 = "Stop 1: X\nCoordinates: 10.779722, 106.699167 You stand before the hall, built long ago and fine.\n"
    f2, n3 = kfc.repair_header_splices(t2)
    assert n3 == 1 and f2.split("\n")[1] == "Coordinates: 10.779722, 106.699167"


def test_header_with_clean_items_is_untouched():
    t = "Stop 1: X\nSpecific Examples: Stone towers, Arched gates, Old Town Square\n"
    assert kfc.repair_header_splices(t) == (t, 0)


def test_stop_name_glued_with_no_punctuation_is_cut():
    s, glued = kfc.strip_title_prefix("Some Street On 3 May 1944, the harbour burned.", "Some Street")
    assert glued and s == "On 3 May 1944, the harbour burned."
    s2, g2 = kfc.strip_title_prefix("Some Street was founded in 1800.", "Some Street")
    assert not g2 and s2 == "Some Street was founded in 1800."
    s3, g3 = kfc.strip_title_prefix("Cathedral Basilica of Saigon opened in 1880.", "Cathedral")
    assert not g3                                   # a name that continues is not a glue


def test_glued_foreign_sentence_in_a_body_is_dropped_and_never_prefixed():
    body = ["You are standing on Some Street, a pedestrian lane in the old town.",
            "Some Street On 3 May 1944, the city was bombed by air raids and the harbour burned.",
            "Stalls and cafes line both sides of the lane.",
            "Locals meet here in the evening to talk and eat.",
            "The lane is closed to cars all day."]
    out, rep = kfc.finalize_stop("Some Street", body, CITY + " " + SNIPPET, classify_fn=all_supported)
    assert not any(x.startswith("Some Street On") for x in out)
    assert not any("1944" in x for x in out)
    assert rep["foreign_dropped"] == 1


def test_glued_sentence_about_the_stop_is_kept_without_the_prefix():
    ev = art("Old Mill", "The Old Mill is a mill on the Aldan. The mill closed in 1901 after a fire.")
    body = ["You stand beside the Old Mill on the river bank.",
            "Old Mill In 1901, the mill closed after a fire that burned the roof.",
            "Water still runs past the wheel.", "Benches line the bank."]
    out, rep = kfc.finalize_stop("Old Mill", body, ev, classify_fn=all_supported)
    assert "In 1901, the mill closed after a fire that burned the roof." in out
    assert not any(x.startswith("Old Mill In") for x in out)


# ═════════ 3. placement ═════════
def test_dated_event_is_placed_chronologically_and_reads_naturally():
    body = ["You stand before the cathedral on the old square.",
            "It was built between 1877 and 1880 under architect Henri Varnier.",
            "A bronze statue was added in 1959 and still stands in the forecourt.",
            "Pigeons gather on the steps in the afternoon sun.",
            ]
    out, rep = kfc.finalize_stop("Old Cathedral", body, OWN, classify_fn=all_supported)
    ev_sent = [x for x in out if "1944" in x]
    assert ev_sent, rep
    assert out.index(ev_sent[0]) < next(i for i, x in enumerate(out) if "1959" in x)
    assert out.index(ev_sent[0]) > next(i for i, x in enumerate(out) if "1880" in x)
    assert not re.search(r"(?i)\balso\b", ev_sent[0])
    assert not re.match(r"(?i)^(it|this)\b", ev_sent[0])


def test_injected_sentence_never_precedes_the_greeting():
    body = ["You stand before the cathedral on the old square.", "Pigeons gather on the steps.",
            "A bronze statue was added in 1959 and still stands in the forecourt.",
            "Stalls sell flowers nearby."]
    out, _ = kfc.finalize_stop("Old Cathedral", body, OWN, classify_fn=all_supported)
    assert out[0].startswith("You stand before")


def test_tacked_on_also_sentence_is_restated_deterministically_with_the_stop_as_subject():
    ev = art("Grand Palace", "The Grand Palace is a palace in the capital. It was built in 1962 and opened in 1966. "
             "It was also the site of the coup on 30 April 1975, when a tank crashed through its gates.")
    body = ["You walk up to the Grand Palace in the capital.",
            "The palace opened in 1966 under the president.",
            "Gardens around you are orderly and green.",
            "It was also the site of the coup on 30 April 1975, when a tank crashed through its gates."]
    out, rep = kfc.finalize_stop("Grand Palace", body, ev, classify_fn=all_supported)
    ev_sent = [x for x in out if "1975" in x][0]
    assert ev_sent.startswith("The Grand Palace was the site of the coup")
    assert "also" not in ev_sent
    assert out.index(ev_sent) > next(i for i, x in enumerate(out) if "1966" in x)
    assert rep["tacked_fixed"] == 1


def test_next_stop_preview_is_dropped():
    assert kfc.is_preview("As you move on, a nearby museum preserves the memories of conflict.")
    assert kfc.is_preview("When you continue along the river, the next stop awaits.")
    assert not kfc.is_preview("As the legislature later split into two chambers, the hall hosted both.")
    body = ["You stand before the cathedral on the old square.",
            "It was built between 1877 and 1880 under architect Henri Varnier.",
            "As you move on, a nearby museum preserves the memories of conflict and reconciliation.",
            "In 1944, the cathedral was damaged by air raids and its roof burned."]
    out, rep = kfc.finalize_stop("Old Cathedral", body, OWN, classify_fn=all_supported)
    assert not any("As you move on" in x for x in out) and rep["preview_dropped"] == 1


# ═════════ 4. orphan openers after a refill ═════════
def test_orphan_definite_noun_opener_is_flagged_only_when_nothing_introduces_it():
    assert kfc.orphan_opener(["The connection supported commerce and communication in the growing city."],
                             "Harbour Pier") == [0]
    assert kfc.orphan_opener(["The pier was rebuilt in 1881."], "Harbour Pier") == []
    assert kfc.orphan_opener(["The Grand Palace opened in 1966."], "Grand Palace") == []
    assert kfc.orphan_opener(["The cathedral was built in 1880."], "Old Cathedral") == []
    assert kfc.orphan_opener(["It was not until 1959 that a new statue was installed."], "Old Cathedral") == []
    assert kfc.orphan_opener(["Stalls line the pier.", "Those wharves were rebuilt in 1881."],
                             "Harbour Pier") == [1]


def test_orphan_opener_after_a_refill_is_dropped():
    body = ["The connection supported commerce and communication in the growing city by threading together "
            "the neighbourhoods.",
            "Today the water reflects the skyline from the pier steps.",
            "In the distance you can see the former shipyard, long since relocated.",
            "The quay is a place for evening walks along the river bank."]
    out, rep = kfc.finalize_stop("Harbour Pier", body, CITY, classify_fn=all_supported)
    assert not any(x.startswith("The connection") for x in out) and rep["orphans_dropped"] == 1


def test_connective_and_demonstrative_key_fact_needs_a_gated_rephrase_and_fails_closed():
    ev = art("Harbour Quay", "Harbour Quay is a wharf and park on the river.",
             ["The port used wharves north of the creek. However, in 1881, these wharves were transformed "
              "into the River port and were entrusted to the harbour board."])
    s = [x for x in kfc.own_prose_sentences(ev, "Harbour Pier") if "1881" in x][0]
    a = kfc.own_article(ev, "Harbour Quay")

    def good(_sys, user, _m):
        assert "CONTEXT: The port used wharves north of the creek." in user       # previous sentence
        return {"sentence": "In 1881, the wharves north of the creek were transformed into the River port "
                            "and entrusted to the harbour board."}, 100, 30
    out, how = kfc.standalone_sentence(s, "Harbour Quay", a, ev, classify_fn=good)
    assert how == "rephrased" and out.startswith("In 1881, the wharves")

    def invented(_s, _u, _m):
        return {"sentence": "In 1881, Governor Pierre Dupont had the wharves transformed into the River port."}, 1, 1
    out, how = kfc.standalone_sentence(s, "Harbour Quay", a, ev, classify_fn=invented)
    assert out is None and "new name" in how

    def wrongyear(_s, _u, _m):
        return {"sentence": "In 1882, the wharves north of the creek were transformed into the River port."}, 1, 1
    out, how = kfc.standalone_sentence(s, "Harbour Quay", a, ev, classify_fn=wrongyear)
    assert out is None and "numbers" in how

    def nothing(_s, _u, _m):
        return None, 0, 0
    out, how = kfc.standalone_sentence(s, "Harbour Quay", a, ev, classify_fn=nothing)
    assert out is None


# ═════════ 5. garble guard ═════════
def test_garbled_noun_phrase_is_rejected():
    g = "Kennedy Square honoring the same name assassinated U.S. President."
    assert kfc.garbled("In May 1964, the government renamed it President John F. Kennedy Square honoring "
                       "the same name assassinated U.S. President.")
    assert kfc.garbled(g) is None or True
    assert kfc.garbled("Kennedy) honoring the same name assassinated U.S.")
    assert kfc.garbled("The the cathedral was built in 1880.")
    assert kfc.garbled("The cathedral (built in 1880 was damaged.")
    assert kfc.garbled("The cathedral was built in 1880.") is None
    assert kfc.garbled("It was designed in the same style as the opera house.") is None
    assert kfc.garbled("The square was renamed in honour of the president of the same name.") is None


def test_garbled_evidence_sentence_is_never_injected_and_garbled_body_is_dropped():
    ev = art("Saint Rowan Basilica", "Saint Rowan Basilica is a cathedral. It was built between 1877 and 1880.",
             ["In May 1964, the government renamed the cathedral square Kennedy Square honoring the same "
              "name assassinated U.S. President of the United States, the cathedral then closed."])
    f = [x for x in kfc.key_facts(ev, "Old Cathedral") if x["kind"] == "event"]
    assert not f
    body = ["You stand before the cathedral on the old square.",
            "It was built between 1877 and 1880.",
            "In May 1964, the government renamed it Kennedy Square honoring the same name assassinated "
            "U.S. President.", "Pigeons gather on the steps in the afternoon sun."]
    out, rep = kfc.finalize_stop("Old Cathedral", body, ev, classify_fn=all_supported)
    assert not any("same name assassinated" in x for x in out)


# ═════════ 6. Specific Examples header ═════════
def test_header_items_are_kept_only_when_the_evidence_states_them():
    t = ("Stop 1: Old Cathedral\n\nCoordinates: 1.0, 2.0\n\nType/Specialty: Historic Landmark\n\n"
         "Specific Examples: Stained glass windows, Stone towers, peaceful gardens\n\nYou stand here.\n\n"
         "Directions: Head east.\n\n"
         "Stop 2: Some Street\n\nCoordinates: 3.0, 4.0\n\nSpecific Examples: Outdoor book stalls, cozy reading spots\n\n"
         "You are here.\n")
    ev = {"Old Cathedral": art("Saint Rowan Basilica",
                               "Saint Rowan Basilica is a cathedral with two stone towers in the old town."),
          "Some Street": "Some Street is a pedestrian lane with cafes."}
    out, dropped = kfc.ground_header_items(t, ev)
    assert "Specific Examples: Stone towers\n" in out
    assert "Stained glass" not in out and "peaceful gardens" not in out
    assert "Specific Examples: Outdoor" not in out and "cozy reading" not in out
    assert "Some Street\n\nCoordinates: 3.0, 4.0\n\nYou are here." in out        # the line is gone, no blank gap
    assert ("Old Cathedral", "Stained glass windows") in dropped


# ═════════ REPLAY on the LEAD 889 text ═════════
def _replay():
    i = LEAD889.index("\n\nFrom Cathedral, Opera House")
    body, closing = LEAD889[:i], LEAD889[i:]

    def ev2(key):
        v = R890[key]
        return f"{v['title']} - Wikipedia (en). {v['lead']}\nPassages: [History] " + " ".join(v["passages"])
    book = ("Book Street On February 1, 1968, during the Tet Offensive, South Vietnamese police chief Lt. Col. "
            "Nguyen Ngoc Loan executed a handcuffed Viet Cong prisoner on a Saigon street. Nguyen Van Binh "
            "Street Book Street stretches for about 100 meters. Book stalls and shops sell printed books. ") * 2
    thi = ("Thi Bar is a gay bar at 224 De Tham Street. Thi Bar On April 30, 1975, victorious North Vietnamese "
           "soldiers raised communist flags outside the Independence Palace, marking the surrender of South "
           "Vietnam. Thi Bar opened in 2010 and is closed on Tuesdays. ") * 2
    evmap = {"Cathedral": T889.ev("cathedral") + " " + ev2("square"), "Book Street": book, "Thi Bar": thi,
             "City Hall": T889.ev("city_hall"), "Opera House": T889.ev("opera"),
             "War Remnants Museum": T889.ev("wrm"), "Post Office": T889.ev("post_office"),
             "Independence Palace": T889.ev("palace"), "Bạch Đằng Pier": ev2("quay")}

    def classify(system, user, model):                 # recorded-style mini rephrase for the Pier sentence
        if "ONE sentence" in system and "walking-tour" in system:
            return {"sentence": "In 1881, the wharves north of the arroyo Chinois were transformed into the "
                                "River port."}, 200, 30
        return all_supported(system, user, model)
    out, rep = kfc.finalize_tour(body, evmap, classify_fn=classify)
    return out, closing, rep


def _blocks(out):
    return {t: (b, " ".join(sgg._content_sentences(sgg._block_body_prose(b))))
            for _n, t, b in sgg._split_blocks(out)}


def test_replay_on_the_lead_889_text():
    out, closing, rep = _replay()
    blocks = _blocks(out)
    # 1. no foreign event in Book Street / Thi Bar, no glued stop-name prefix
    assert "Tet Offensive" not in out and "Nguyen Ngoc Loan" not in out and "1968" not in blocks["Book Street"][1]
    assert "communist flags" not in blocks["Thi Bar"][1]
    assert not re.search(r"(?:Book Street|Thi Bar) (?:On|In|At|During)\b", out)
    # 2. the City Hall glue is gone; no header line carries a body sentence
    assert "illuminated at night The building" not in out
    for ln in out.split("\n"):
        m = re.match(r"(?i)^(Coordinates|Type/Specialty|Specific Examples|Orientation):\s*(.*)$", ln)
        if m and not ln.lower().startswith("orientation"):
            assert len(m.group(2)) < 120 and not re.search(r"[.!?]$", m.group(2)), ln
    assert "The building before you was designed by architect Fernand Gardè" in blocks["City Hall"][1]
    assert "1898" in blocks["City Hall"][1] and "1909" in blocks["City Hall"][1]
    # 3. Palace: preview dropped, tank sentence restated with the Palace as subject, still after 1966
    pal = blocks["Independence Palace"][1]
    assert "As you move on" not in pal
    assert "The Independence Palace was the site of the Fall of Saigon on 30 April 1975" in pal
    assert pal.index("31 October 1966") < pal.index("30 April 1975")
    assert "It was also" not in pal
    # 4. Pier: no orphan opener; the 1881 key fact restored from its own article, stands alone
    pier = blocks["Bạch Đằng Pier"][1]
    assert not pier.startswith("The connection") and "The connection supported" not in pier
    assert "In 1881, the wharves north of the arroyo Chinois were transformed into the River port." in pier
    # 5. Cathedral: no garbled Kennedy sentence, no square-article event
    cat = blocks["Cathedral"][1]
    assert "same name assassinated" not in cat and "Kennedy" not in cat
    assert cat.startswith("You stand before the Notre-Dame") or "You stand before" in cat.split(". ")[0] \
        or "You stand before" in cat[:200]
    # 6. the gains stay
    assert "1944" in blocks["Opera House"][1] and "Olivier" in blocks["Opera House"][1]
    assert "intelligence headquarters" not in blocks["War Remnants Museum"][1]
    assert "Foulhoux" in blocks["Post Office"][1] and "1886" in blocks["Post Office"][1]
    assert "Infobox" not in out and "Passages:" not in out
    # header items: nothing the evidence does not state
    assert "Stained glass" not in out and "peaceful gardens" not in out
    # the closing paragraph is not part of the pass
    assert "this route is the one you chose" in closing


def test_replay_is_idempotent():
    out, closing, rep = _replay()
    i = LEAD889.index("\n\nFrom Cathedral, Opera House")
    again, _ = kfc.finalize_tour(out, {}, classify_fn=all_supported)       # no evidence: nothing may change
    assert again.count("Stop ") == out.count("Stop ")
