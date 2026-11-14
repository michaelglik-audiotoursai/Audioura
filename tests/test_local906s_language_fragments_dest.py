"""[LOCAL-906S] Foreign-language sentence, caption variants, a stop title as a place name, "known for <verb>", fragments, a dangling
"Their", a factless destination stop, cross-stop measures, operator / closing variants, unsupported period claims. $0, generic names (D769)."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("SERPER_API_KEY", None)
os.environ["THIN_STOP_SEARCH"] = "0"

import delivery_evidence_906h as de  # noqa: E402
import language_dest_906s as s  # noqa: E402
import owner_junk_906p as p  # noqa: E402
import refill_quality_906k as k  # noqa: E402
import route_content_896 as rc  # noqa: E402


@pytest.fixture(autouse=True)
def _job():
    with rc.job_scope("t906s"):
        rc.set_evidence_904({})
        de.clear()
        yield


KEEP = "The mountain rises above the old town and the river."
KEEP2 = "A small shrine sits near the summit path."
KEEP3 = "Pilgrims climb a stone stair to the summit each spring."


def tour(stops, closing="That's 3 stops in all."):
    out = "Step-by-step audio guided tour of Alpha Peak is a driving tour.\n\n"
    for n, (title, body, directions) in enumerate(stops, 1):
        out += (f"Stop {n}: {title}\n\nCoordinates: 10.{n}, 100.{n}\n\nType/Specialty: Landmark\n\n{body}\n\n"
                f"Directions: {directions}\n\n")
    return out + closing + "\n"


def one(body, title="Alpha Peak", ev=None, **kw):
    t = tour([(title, body, "Go on."), ("Beta Town", "A market town by the river. " + KEEP, "Go on."),
              ("Gamma Lake", "A still lake. " + KEEP2, "")])
    return s.run_pass(t, ev, kw.get("log"))


# ── 1. foreign language ───────────────────────────────────────────────────────────────────────────────────
VI = "Mũi Né là một phường thuộc tỉnh Lâm Đồng, Việt Nam."


def test_vietnamese_sentence_is_detected_and_english_with_vietnamese_names_is_not():
    assert s.foreign_language(VI) == "vi"
    assert s.foreign_language("Mũi Né is a coastal fishing ward in the Lâm Đồng Province of Vietnam.") is None
    assert s.foreign_language("Visit Phường Hòa Thuận and Bình Thuận in the north.") is None
    assert s.foreign_language("Le temple est situé dans une vallée avec des jardins.") == "fr"
    assert s.foreign_language("Der Turm ist ein Wahrzeichen und steht auf dem Hügel.") == "de"


def test_foreign_sentence_dropped_from_the_final_text_and_english_name_sentence_kept():
    logs = []
    out = one(f"{KEEP} {VI} The ward of Mũi Né lies in the Lâm Đồng Province. {KEEP2}", log=logs.append)
    assert "là một phường" not in out
    assert "The ward of Mũi Né lies in the Lâm Đồng Province." in out and KEEP in out
    assert any("another language" in m for m in logs)


def test_foreign_sentence_is_never_a_refill():
    assert "another language" in (k.refill_reject(VI, "Alpha Peak", None, "article", "", True) or "")
    assert k.refill_reject("Mũi Né is a coastal fishing ward in the Lâm Đồng Province of Vietnam.", "Mũi Né", None, "article", "", True) is None \
        or "another language" not in k.refill_reject("Mũi Né is a coastal fishing ward in the Lâm Đồng Province of Vietnam.", "Mũi Né", None, "article", "", True)


def test_a_non_english_tour_is_left_alone():
    es = ("El templo es una joya de la ciudad y los visitantes que llegan por la mañana encuentran un jardín con una vista de las "
          "montañas y del río que cruza el valle antes de llegar al mar.")
    assert not s.tour_is_english(es)


# ── 2. caption variants ───────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("x", [
    "Ham Tien beach, Beta Town, A person cleans a trash-strewn beach.",
    "A person cleans a trash-strewn beach.",
    "A man sells fruit by the road.",
    "A woman carries baskets along the shore.",
    "A group of tourists watches the sunset over the dunes.",
    "A child plays on the sand.",
    "Alpha Beach, A group walks along the water.",
])
def test_caption_variants_are_dropped(x):
    assert s.caption_variant(x) and p.junk_reason(x) == "photo caption"
    out = one(f"{KEEP} {KEEP2} {x}")
    assert x not in out and KEEP in out


@pytest.mark.parametrize("x", ["A man named Truong carved the statue in 1963.", "A person who lived here built the first hall.",
                               "A woman was the first abbess of the pagoda.", "A group of monks lives on the mountain and keeps the hall."])
def test_real_sentences_are_not_captions(x):
    assert not s.caption_variant(x)


# ── 3. a stop title as a place ────────────────────────────────────────────────────────────────────────────
DASH = "Dragon fruit country – the plantations along the road"
ARR = "Arriving at Gamma Hill – the mountain and its legends"


def test_orientation_look_for_dash_title_is_rewritten():
    x = f"Look for {DASH} in Beta Ward."
    assert s.title_as_place(x, DASH) == "You are now in Beta Ward."


def test_dash_topic_title_is_never_the_subject():
    out = s.title_as_place(f"{DASH} is an agricultural area known for dragon fruit.", DASH)
    assert out == "This area is an agricultural area known for dragon fruit."


def test_the_arriving_at_title_becomes_the_core():
    out = s.title_as_place(f"The {ARR} is home to two famous pagodas.", ARR)
    assert out == "Gamma Hill is home to two famous pagodas."


def test_title_rewrite_in_a_tour_orientation_and_body():
    t = tour([(DASH, f"{DASH} is an agricultural area known for dragon fruit. {KEEP} {KEEP2}", "Go."),
              (ARR, f"The {ARR} is home to two famous pagodas. {KEEP} {KEEP3}", "Go."), ("Gamma Lake", "A lake. " + KEEP2, "")])
    t = t.replace("Type/Specialty: Landmark\n\nDragon", f"Type/Specialty: Landmark\n\nOrientation: Look for {DASH} in Beta Ward.\n\nDragon", 1)
    out = s.run_pass(t)
    assert f"{DASH} is" not in out and "The Arriving at" not in out and "Look for Dragon fruit" not in out
    assert "You are now in Beta Ward." in out and "Gamma Hill is home to two famous pagodas." in out
    assert "Stop 1: " + DASH in out        # the heading and the Directions are the title itself


def test_a_named_stop_title_is_not_touched():
    assert s.title_as_place("Alpha Peak is a granite mountain.", "Alpha Peak") is None
    assert s.title_as_place("The cable car ascent is short.", "The cable car ascent") is None


# ── 4. known for <verb> ───────────────────────────────────────────────────────────────────────────────────
def test_known_for_bare_verb_never_delivered():
    x = "It is known for visit dragon fruit farms, taste fresh dragon fruit, and learn about the cultivation process."
    out = one(f"{KEEP} {KEEP2} {x}")
    assert "known for visit" not in out and KEEP in out
    y = "Beta Ward is a farming area, known for visit dragon fruit farms and taste fresh fruit."
    out2 = one(f"{KEEP} {KEEP2} {y}")
    assert "known for visit" not in out2 and "Beta Ward is a farming area." in out2


def test_known_for_noun_or_gerund_is_kept():
    x = "The area is known for dragon fruit farms and for swimming in the bay."
    assert x in one(f"{KEEP} {KEEP2} {x}")


# ── 5. fragments ──────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("x", [
    "As you explore, known for its market and cultural sites.",
    "Gamma Hill, located about 40 minutes away in Beta District.",
])
def test_fragments_are_dropped(x):
    assert rc.is_fragment(x)
    out = one(f"{KEEP} {KEEP2} {KEEP3} {x}")
    assert x not in out and KEEP in out


@pytest.mark.parametrize("x", [
    "The temple is located about 40 minutes away in Beta District.",
    "Gamma Hill, located 28 km west of the town, is a popular site.",
    "As you explore, you will find a market and cultural sites.",
])
def test_normal_located_sentences_are_kept(x):
    assert not rc.is_fragment(x)
    assert x in one(f"{KEEP} {KEEP2} {KEEP3} {x}")


def test_number_agreement_is_fixed_or_the_clause_goes():
    x = ("The Reclining Buddha here measures a striking 49 meters from head to toe, making it one of the longest Reclining Buddha statue "
         "on a mountains in Asia.")
    new = s.fix_agreement(x)
    assert new and "statues" in new and "on a mountains" not in new
    out = one(f"{KEEP} {KEEP2} {x}")
    assert "statue on a mountains" not in out
    ok = "It is one of the longest Reclining Buddha statues in Asia."
    assert s.fix_agreement(ok) is None and ok in one(f"{KEEP} {KEEP2} {ok}")


# ── 6. Their ──────────────────────────────────────────────────────────────────────────────────────────────
def test_their_with_no_plural_referent_is_dropped():
    x = "Their choice to establish the pagoda here was no small feat."
    body = f"The pagoda stands as a silent witness to nearly two centuries of spiritual dedication. {x} {KEEP}"
    logs = []
    out = one(body, title="Delta Pagoda", log=logs.append)
    assert x not in out and KEEP in out and any("Their/They" in m for m in logs)


@pytest.mark.parametrize("before", [
    "Two monks arrived from the coast and found the hill empty.",
    "Master Alpha and Master Beta crossed the valley.",
    "The villagers farmed the slope for generations.",
])
def test_their_with_a_plural_referent_is_kept(before):
    x = "Their choice to establish the pagoda here was no small feat."
    assert x in one(f"{before} {x} {KEEP}", title="Delta Pagoda")


# ── 7. destination stop ───────────────────────────────────────────────────────────────────────────────────
FILLER = ("Here, the landscape holds not just natural beauty but a tangible sense of ritual and endurance. "
          "This stop connects naturally to the earlier moments on your tour.")
CLOSE = ("This tour showcases the rich cultural and natural heritage of the area, highlighting sacred sites and breathtaking landscapes. "
         "Each stop invites reflection on the enduring connection between spirituality and the beauty of the environment. "
         "That's 3 stops in all.")
EV_DEST = ("Gamma Mountain is a granite mountain in the province. It rises 700 meters above the plain. "
           "The mountain holds two pagodas near the peak. Pilgrims climb a stone stair to the summit each spring.")


def dest_tour():
    t = tour([("Alpha Towers", "You stand at the towers. The towers were built in the 11th century as a sacred area.", "Go."),
              ("Beta Dunes", "The dunes shift with the wind. Sand covers the road each season.", "Go."),
              ("Gamma Mountain", FILLER, "")], closing="")
    t = t.replace("Directions: \n\n", "")
    return t + CLOSE + "\n\nIf you would like to eat nearby we can build you a restaurant tour.\n"


def test_connects_filler_is_template_filler():
    assert s.is_connects_filler("This stop connects naturally to the earlier moments on your tour.")
    assert not s.is_connects_filler("This stop connects the old road to the harbour.")


def test_factless_destination_is_refilled_from_its_evidence():
    ev = {"Gamma Mountain": EV_DEST}
    logs = []
    out = s.last_word(dest_tour(), ev, logs.append)
    assert "connects naturally" not in out and "tangible sense of ritual" not in out
    assert "granite mountain" in out or "two pagodas" in out
    assert "We could not confirm" not in out
    assert "That's 3 stops in all." in out and "restaurant tour" in out


def test_factless_destination_without_a_supported_sentence_gets_the_disclosure_body():
    logs = []
    out = s.last_word(dest_tour(), {"Gamma Mountain": "Book your private tour now and you will love it."}, logs.append)
    assert "connects naturally" not in out
    assert "We could not confirm verified historical details for this stop" in out
    assert any("disclosure body" in m for m in logs)
    assert s.last_word(out, {"Gamma Mountain": "Book your private tour now and you will love it."}).count("We could not confirm verified") == 1       # idempotent


def test_destination_with_no_body_at_all_gets_the_disclosure_body():
    t = dest_tour().replace(FILLER + "\n\n", "")
    out = s.last_word(t, {})
    assert "We could not confirm verified historical details for this stop" in out and "That's 3 stops in all." in out


# ── 8. cross-stop measures ────────────────────────────────────────────────────────────────────────────────
def test_cross_stop_measure_takes_the_article_value():
    art = "The reclining Buddha statue is 49 meters long and 7 meters high."
    de.add({"Alpha Pagoda": [{"text": "The pagoda stands on the slope.", "kind": "article"}],
            "Alpha Statue": [{"text": art, "kind": "article"}]}, "889")
    ev = {"Alpha Pagoda": "The pagoda stands on the slope.", "Alpha Statue": art}
    t = tour([("Alpha Pagoda", "Here, you find the famous Reclining Buddha statue, which is 49 meters long and 11 meters high. "
                               + KEEP + " " + KEEP2, "Go."),
              ("Alpha Statue", "The Reclining Buddha is one of the largest Reclining Buddha statues in the region. It measures 49 meters in "
                               "length and stands 7 meters high. " + KEEP3, "Go."),
              ("Gamma Lake", "A lake. " + KEEP2, "")])
    logs = []
    out = s.unify_measures(t, ev, logs.append)
    assert "11 meters" not in out and out.count("7 meters high") == 2 and "49 meters long" in out
    assert any("across the tour" in m and "article" in m for m in logs)


def test_cross_stop_measure_of_different_objects_is_untouched():
    t = tour([("Alpha Pagoda", "The bridge by the pagoda is 40 meters long. " + KEEP, "Go."),
              ("Alpha Statue", "The reclining Buddha statue is 60 meters long. " + KEEP3, "Go."), ("Gamma Lake", "A lake. " + KEEP2, "")])
    assert s.unify_measures(t, {}) == t


# ── 9. operator / closing variants ────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("x", [
    "These tours often start from Alpha City and offer private charters for a personalized experience.",
    "You can also find recommended ways to get here and explore nearby attractions.",
])
def test_operator_variants_dropped(x):
    assert s.variant_reason(x)
    out = one(f"{KEEP} {KEEP2} {x}")
    assert x not in out and KEEP in out


def test_closing_variants_dropped_but_the_count_and_the_offer_stay():
    out = s.run_pass(dest_tour(), {"Gamma Mountain": EV_DEST})
    assert "This tour showcases" not in out and "Each stop invites" not in out
    assert "That's 3 stops in all." in out and "restaurant tour" in out


def test_normal_tour_sentences_are_not_operator_copy():
    for x in ("This tour begins at the harbour.", "The tour of the old town ends at the market.", "Each stone was cut by hand."):
        assert not s.variant_reason(x)


# ── 10. period claims ─────────────────────────────────────────────────────────────────────────────────────
def test_unsupported_decade_clause_is_cut_and_effect_tail_dropped():
    x = "The cable car system here, installed in the early 2000s, represents a modern engineering effort to reach the summit."
    y = ("The installation of this cable car system changed the mountain's relationship with its visitors, significantly increasing "
         "the flow of pilgrims and tourists alike.")
    ev = {"Alpha Peak": "Alpha Peak is a granite mountain. A cable car runs to the summit. The pagoda was founded in 1890."}
    logs = []
    out = one(f"{KEEP} {x} {y} {KEEP2}", ev=ev, log=logs.append)
    assert "early 2000s" not in out and "significantly increasing" not in out
    assert "The cable car system here represents a modern engineering effort to reach the summit." in out
    assert "changed the mountain's relationship with its visitors." in out


def test_supported_decade_is_kept():
    x = "The cable car system here, installed in the early 2000s, represents a modern engineering effort to reach the summit."
    ev = {"Alpha Peak": "The cable car was installed in 2003 and carries pilgrims to the summit."}
    assert x in one(f"{KEEP} {x} {KEEP2}", ev=ev)


def test_unsupported_century_sentence_dropped_supported_kept():
    x = "This site was remote and wild in the late 19th century, filled with untamed animals and thick forest."
    assert x not in one(f"{KEEP} {x} {KEEP2}", ev={"Alpha Peak": "The mountain is a granite massif."})
    assert x in one(f"{KEEP} {x} {KEEP2}", ev={"Alpha Peak": "The site was remote in the late 19th century."})
