"""LOCAL-872B -- the claim gate must keep TRUE famous facts (sourced from the stop's
Wikipedia article) and disclose, not delete, borderline history claims."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import landmark_claim_gate as lg  # noqa: E402
import landmark_wikipedia_evidence as lw  # noqa: E402

LOC = "Ho Chi Minh City, Vietnam"
NOTRE = "Notre-Dame Cathedral Basilica of Saigon"
NOTRE_SENTS = ("The cathedral was built between 1863 and 1880 by French colonists. "
               "It was consecrated as a basilica in 1959. "
               "Two bell towers rise 58 metres above the red brick facade.")
THIN = ["Notre-Dame Cathedral Basilica of Saigon is a landmark of Ho Chi Minh City."]

WIKITEXT_NOTRE = """{{Infobox church
| name = Notre-Dame Cathedral Basilica of Saigon
| architect = [[Jules Bourard]]<ref>x</ref>
| style = Romanesque Revival
| years_built = 1863-1880
| completed = {{start date|1880}}
| irrelevant = nothing
}}
'''Notre-Dame''' is a cathedral."""

WIKITEXT_PALACE = """{{Infobox building
| name = Independence Palace
| architect = [[Ngô Viết Thụ]]
| completion_date = 31 October 1966
}}"""


def _fake(pages_by_lang):
    def f(name, lang):
        return {"pages": pages_by_lang.get(lang, [])}
    return f


def test_parse_infobox_keeps_facts_drops_noise():
    box = lw.parse_infobox(WIKITEXT_NOTRE)
    assert "architect: Jules Bourard" in box and "years built: 1863-1880" in box
    assert "1880" in box and "irrelevant" not in box and "<ref" not in box and "[[" not in box


def test_local_languages():
    assert lw.local_languages("Old Quarter walk, Hanoi") == ["en", "vi"]
    assert lw.local_languages("Ho Chi Minh City, Vietnam") == ["en", "vi"]
    assert lw.local_languages("Boston, USA") == ["en"]


def test_evidence_for_includes_lead_and_infobox_en_and_local():
    pages = {
        "en": [{"title": NOTRE, "lead": "Built 1863 to 1880, consecrated 1959.", "wikitext": WIKITEXT_NOTRE}],
        "vi": [{"title": "Nhà thờ Đức Bà Sài Gòn", "lead": "Xây dựng 1863.", "wikitext": ""}],
    }
    ev = lw.evidence_for(NOTRE, LOC, fetch_fn=_fake(pages), use_cache=False)
    # the vi title does not name-match: only the en article is evidence
    assert len(ev) >= 1 and "Jules Bourard" in ev[0] and "consecrated 1959" in ev[0]


def test_unrelated_article_is_not_evidence():
    pages = {"en": [{"title": "Notre-Dame de Paris", "lead": "Built 1163.", "wikitext": ""}]}
    assert lw.evidence_for("Independence Palace", LOC, fetch_fn=_fake(pages), use_cache=False) == []


def test_transport_failure_is_none_not_a_crash():
    def boom(n, l):
        raise RuntimeError("down")
    assert lw.fetch_article("Independence Palace", "en", fetch_fn=boom, use_cache=False) is None


def test_notre_dame_dates_dropped_without_wikipedia_kept_with_it():
    # the LOCAL-872 regression: thin evidence -> true dates were lost
    ev_wiki = THIN + ["Notre-Dame Cathedral Basilica of Saigon - Wikipedia (en). Built 1863 to 1880, "
                      "consecrated 1959.\nInfobox: years built: 1863-1880; architect: Jules Bourard"]
    body = "Orientation: Face the cathedral. " + NOTRE_SENTS
    new, removed = lg.filter_stop_body(body, ev_wiki, NOTRE, location=LOC)
    assert "1863" in new and "1959" in new and not removed
    assert "It is sometimes said" not in new          # sourced -> no disclosure either


def test_unsourced_history_claim_is_disclosed_not_deleted():
    body = "Orientation: Face the cathedral. " + NOTRE_SENTS
    new, removed = lg.filter_stop_body(body, THIN, NOTRE, location=LOC)
    disc = []
    new, removed = lg.filter_stop_body(body, THIN, NOTRE, location=LOC, disclosures=disc)
    assert not removed and len(disc) >= 1
    assert "It is sometimes said that the cathedral was built between 1863 and 1880" in new
    assert lg.is_disclosed("It is sometimes said that the cathedral was consecrated as a basilica in 1959.")
    # idempotent: a second pass finds nothing left to change
    again, r2 = lg.filter_stop_body(new, THIN, NOTRE, location=LOC)
    assert again == new and not r2


def test_independence_palace_architect_sourced_and_disclosed():
    s = "Independence Palace was designed by the architect Ngô Viết Thụ."
    ev = ["Independence Palace - Wikipedia (en). The palace.\nInfobox: architect: Ngô Viết Thụ"]
    new, removed = lg.filter_stop_body(s, ev, "Independence Palace", location=LOC)
    assert new == s and not removed
    disc = []
    new2, removed2 = lg.filter_stop_body(s, ["The palace is in District 1."], "Independence Palace",
                                         location=LOC, disclosures=disc)
    assert not removed2 and disc and "It is sometimes said that Independence Palace" in new2


def test_disclosure_off_switch_still_drops():
    new, removed = lg.filter_stop_body("The cathedral was built in 1863.", THIN, NOTRE,
                                       location=LOC, disclose_borderline=False)
    assert "1863" not in new and removed


def test_miss_saigon_still_dropped_even_though_borderline_is_disclosed():
    s = "Over the decades the Opera House has staged productions of Miss Saigon."
    ev = ["Saigon Opera House - Wikipedia (en). Built 1900.\nInfobox: architect: Félix Olivier"]
    new, removed = lg.filter_stop_body(s, ev, "Saigon Opera House", location=LOC)
    assert "Miss Saigon" not in new and removed and removed[0]["kind"] == "production"


def test_performer_event_work_stay_drops():
    ev = ["Saigon Opera House - Wikipedia (en). Built 1900."]
    for s in ("The soprano Maria Callas sang here in 1960.",
              "The theatre hosted the Saigon Jazz Festival in 1995.",
              "The conductor Herbert Karajan led the orchestra here."):
        new, removed = lg.filter_stop_body(s, ev, "Saigon Opera House", location=LOC)
        assert not new.strip() or "sometimes said" not in new
        assert removed, s


def test_mixed_sentence_with_a_production_is_dropped_not_disclosed():
    s = "Built in 1901, the theatre staged productions of Miss Saigon."
    new, removed = lg.filter_stop_body(s, ["The Saigon Opera House."], "Saigon Opera House", location=LOC)
    assert "Miss Saigon" not in new and removed


def test_hanoi_ngoc_son_is_a_place_not_a_person():
    ev = ["Hoan Kiem Lake is a lake in Hanoi."]
    known = ["Hoan Kiem Lake", "Specific Examples: The Turtle Tower, the Ngoc Son Temple on an island"]
    for s in ("Across the water the bridge leads to an island crowned by Ngoc Son.",
              "Across the water a red bridge leads to a small island crowned by Ngoc Son Temple.",
              "Cross the bridge to the entrance of Ngoc Son Temple, which sits on the island."):
        new, removed = lg.filter_stop_body(s, ev, "Hoan Kiem Lake", known=known,
                                           location="Old Quarter walk, Hanoi")
        assert new == s and not removed, (s, removed)


def test_generate_tour_text_is_wired_for_wikipedia_evidence():
    src = open(os.path.join(os.path.dirname(__file__), "..", "generate_tour_text.py"),
               encoding="utf-8").read()
    assert "landmark_wikipedia_evidence" in src and "LOCAL-872B" in src


def test_disclosure_lowercases_only_function_words():
    assert lg.disclose("Another chapter arrived in 1959.").startswith("It is sometimes said that another chapter")
    assert lg.disclose("Bishop Colombert laid the stone.").startswith("It is sometimes said that Bishop")
