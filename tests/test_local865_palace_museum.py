"""LOCAL-865 — Palais Lascaris delivered 1/6: "27 R4 candidates failed canonical match".

Fixtures use the EXACT strings from the measured runs (LOCAL-861 museum A/B, cloud
tour 528, the D1v2 log of the diagnosis run).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import palace_museum_stops as pms  # noqa: E402

# Exact log strings
LOG_R4 = ("[R4] Replenishment exhausted: 1/6 stops (stop_count_warning) — stopped because "
          "the model returned no further new, verifiable works; "
          "27 R4 candidate(s) failed canonical match")
LOG_TIER = "[D1v2] Canonical titles union: 10 site/wiki + 1 SPARQL = 11 total"
CANON = [
    "Basse de violon by Paolo Antonio Testore (Milan, 1696)",
    "Guitar by Antonio de Torres (Almeria, 1884)",
    "Harpe by Naderman (Paris, 1780)", "Raquel",
    "Sacqueboute ténor by Anton Schnitzer (Nuremberg, 1581)",
]
VENUE_PIN = (43.697694444444444, 7.27725)       # "Coords: 43.697694444444444, 7.27725"
OFFSET_PIN = (43.707306, 7.305403)               # tour 528 / t1331 "Coordinates:" line

NICE_FR = (
    "https://www.nice.fr/fr/culture/musees-et-galeries/palais-lascaris-le-palais",
    "Edifié au milieu du XVIIème siècle, ce « joyau du Baroque » vous propose des expositions "
    "temporaires et une riche collection d’instruments de musique anciens.\n"
    "Situé au cœur de la vieille ville, il est le monument le plus remarquable du baroque civil "
    "niçois par son escalier monumental orné de fresques et ses salons luxueusement décorés.\n"
    "Pharmacies de garde\n"
    "La façade principale du palais épouse la courbe de la rue Droite, jadis artère principale "
    "de la cité. Elle se détache nettement par son caractère solennel et son opulence.\n"
    "Le plafond à fresque représente Psyché portée par Mercure dans l’Olympe. La profusion "
    "d’ornements qui entoure le cartouche central est fréquente dans la peinture décorative.\n"
    "Cette grande salle qui précède d’une part la chapelle du palais et d’autre part l’enfilade "
    "des petits salons a dû être reconstituée dans son état du XVIIe siècle.\n")
FR_WIKI = (
    "https://fr.wikipedia.org/wiki/Palais_Lascaris",
    "Des tapisseries flamandes et d'Aubusson ornent les murs du musée et un mobilier des XVIIe "
    "siècle et du XVIIIe siècle décorent les différentes pièces du musée .\n")
EN_WIKI = (
    "https://en.wikipedia.org/wiki/Palais_Lascaris",
    "Today the palace devotes its exhibition space to the permanent exhibit of the collection "
    "of historical musical instruments, built around the bequest of Antoine Gautier (1825–1904).\n")
PAGES = [{"url": u, "text": t} for u, t in (NICE_FR, FR_WIKI, EN_WIKI)]


def test_log_strings_are_the_diagnosed_ones():
    # The tier that skipped the thin-only fallbacks, and the count that was reported.
    assert "27 R4 candidate(s) failed canonical match" in LOG_R4
    assert "10 site/wiki + 1 SPARQL" in LOG_TIER   # 10 > 1 SPARQL => exhibit_museum tier


def test_lascaris_is_a_palace_museum():
    assert pms.is_palace_museum("Palais Lascaris, Nice, France")
    assert not pms.is_palace_museum("Isabella Stewart Gardner Museum, Boston", "")


def test_features_come_from_the_venues_own_pages():
    out = pms.detect_feature_stops("Palais Lascaris, Nice, France", PAGES, needed=6,
                                   exclude_names=["Raquel (panneau, fin du XVIe siècle)"])
    names = [o["name"] for o in out]
    assert len(out) == 6, names
    assert "The Musical Instrument Collection" in names
    assert "The Frescoed and Painted Ceilings" in names
    assert "The Grand Staircase" in names
    assert "The Palace Chapel" in names
    for o in out:
        assert o["verified"] is True and o["_stop_kind"] == "collection_area"
        assert o["_feature_sources"], "every feature carries its grounding sentence (D756)"
        for src in o["_feature_sources"]:
            assert "lascaris" in src["url"].lower()


def test_apothecary_not_invented_when_corpus_does_not_name_it():
    # "Pharmacies de garde" is site chrome (a rota of on-duty chemists), NOT the
    # palace apothecary — it must never ground an apothecary stop.
    out = pms.detect_feature_stops("Palais Lascaris, Nice", PAGES, needed=8)
    assert "The 17th-Century Apothecary" not in [o["name"] for o in out]


def test_apothecary_ships_when_a_page_names_it():
    pages = PAGES + [{"url": "https://www.nice.fr/fr/culture/palais-lascaris-pharmacie",
                      "text": "L’apothicairerie du XVIIe siècle du palais Lascaris conserve "
                              "ses pots en faïence et ses bocaux d’origine.\n"}]
    out = pms.detect_feature_stops("Palais Lascaris, Nice", pages, needed=8)
    assert "The 17th-Century Apothecary" in [o["name"] for o in out]


def test_other_venues_pages_never_ground_a_feature():
    # D756: a page about ANOTHER venue (no 'lascaris') must not supply a feature.
    foreign = [{"url": "https://en.wikipedia.org/wiki/Palazzo_Spinola",
                "text": "The Palazzo Spinola has a grand staircase and frescoed ceilings "
                        "painted by Genoese masters in the seventeenth century.\n"}]
    assert pms.detect_feature_stops("Palais Lascaris, Nice", foreign, needed=6) == []


def test_non_palace_returns_nothing_and_zero_needed_returns_nothing():
    assert pms.detect_feature_stops("Isabella Stewart Gardner Museum, Boston", PAGES,
                                    needed=6) == []
    assert pms.detect_feature_stops("Palais Lascaris, Nice", PAGES, needed=0) == []


def test_exclude_names_respected():
    out = pms.detect_feature_stops("Palais Lascaris, Nice", PAGES, needed=6,
                                   exclude_names=["The Grand Staircase"])
    assert "The Grand Staircase" not in [o["name"] for o in out]


def test_narration_instruction_binds_to_sourced_facts():
    out = pms.detect_feature_stops("Palais Lascaris, Nice", PAGES, needed=1)
    txt = pms.feature_narration_instruction(out[0])
    assert "ONLY" in txt and out[0]["_feature_facts"][0] in txt
    assert pms.feature_narration_instruction({"name": "x"}) == ""


def test_pin_resolver_outranks_stop1_offset_point():
    pin, src = pms.pick_venue_pin(resolver=VENUE_PIN, corpus=None, first_stop=OFFSET_PIN)
    assert src == "resolver_p625" and pin == VENUE_PIN


def test_pin_falls_back_in_order():
    assert pms.pick_venue_pin(known=(1.0, 2.0), resolver=VENUE_PIN)[1] == "known"
    assert pms.pick_venue_pin(resolver=(None, None), first_stop=OFFSET_PIN)[1] == "model_first_stop"
    assert pms.pick_venue_pin(resolver=(0.0, 0.0))[1] == "none"


def _hav_m(a, b):
    import math
    R = 6371000.0
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def test_the_offset_was_2_5_km_and_the_fix_is_under_100_m():
    assert 2000 < _hav_m(OFFSET_PIN, VENUE_PIN) < 3000
    pin, _ = pms.pick_venue_pin(resolver=VENUE_PIN, first_stop=OFFSET_PIN)
    assert _hav_m(pin, VENUE_PIN) < 100


def test_generate_tour_text_is_wired():
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "generate_tour_text.py"), encoding="utf-8").read()
    assert "from palace_museum_stops import detect_feature_stops" in src
    assert "_verification_tier in ('thin', 'exhibit_museum')" in src
    assert "first_poi_coordinates = (_venue_coord[0], _venue_coord[1])" in src
    assert "from palace_museum_stops import pick_venue_pin" in src
