"""LOCAL-875 / D768: local language decided at run time from the tour's location.

All offline/deterministic:
  * languages_for uses the 863R curated table + the request's named country + a
    well-known-city augmentation, with regional overrides (Quebec, Catalonia,
    Hong Kong) — no network needed for the six required cases;
  * the P31 Q-id map is a pure dict;
  * kind_words en/vi come from the place_kinds fixtures (no LLM); a third
    language uses an INJECTED fake llm, and a second call for it makes NO call;
  * classify_place is language-free: a P31 Q-id decides a Chinese temple, a
    Russian church and a French lighthouse; a Spanish market is `both`.

Nothing here touches the live DB (use_cache=False or injected backends) or any
paid API.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import local_language as L  # noqa: E402
import place_kinds as pk  # noqa: E402


class TestLanguagesFor(unittest.TestCase):
    """The six cases the ticket names, plus Hong Kong + coordinate input."""

    CASES = [
        ("Sophia's biking tour in Ho Chi Minh City, Vietnam", ["vi"]),
        ("Longshan Temple and Ximending walk, Taipei", ["zh-Hant"]),
        ("Montmartre walk, Paris", ["fr"]),
        ("Barcelona, Spain", ["ca", "es"]),
        ("Kitai-gorod walk, Moscow", ["ru"]),
        ("Old Montréal walk, Montréal", ["fr"]),
    ]

    def test_required_cases(self):
        for loc, expected in self.CASES:
            with self.subTest(loc=loc):
                self.assertEqual(L.languages_for(loc, use_cache=False), expected)

    def test_montreal_ascii_and_accented(self):
        self.assertEqual(L.languages_for("Montreal", use_cache=False), ["fr"])
        self.assertEqual(L.languages_for("Montréal", use_cache=False), ["fr"])

    def test_quebec_region_overrides_canada_default(self):
        # Canada's country default is en+fr; Quebec forces fr first (and only).
        self.assertEqual(L.languages_for("Quebec City", use_cache=False), ["fr"])

    def test_hong_kong_is_traditional_plus_english(self):
        self.assertEqual(L.languages_for("Hong Kong Island walk", use_cache=False),
                         ["zh-Hant", "en"])

    def test_catalonia_alias_without_country(self):
        # "Barcelona" alone still triggers the Catalonia regional override.
        self.assertEqual(L.languages_for("Gothic Quarter, Barcelona", use_cache=False),
                         ["ca", "es"])

    def test_plain_us_city_is_english(self):
        self.assertEqual(L.languages_for("Beacon Hill, Boston, MA", use_cache=False),
                         ["en"])

    def test_always_returns_at_least_english(self):
        self.assertEqual(L.languages_for("", use_cache=False), ["en"])
        self.assertEqual(
            L.languages_for("Nowhere-in-particular xyzzy", use_cache=False), ["en"])

    def test_local_language_single_code(self):
        self.assertEqual(L.local_language("Montmartre walk, Paris", use_cache=False),
                         "fr")
        self.assertEqual(
            L.local_language("Longshan Temple, Taipei", use_cache=False), "zh-Hant")

    def test_coordinates_via_injected_reverse_geocoder(self):
        # (lat, lng) for central Moscow -> reverse geocode returns ru country code.
        def fake_fetch(params):
            self.assertIn("lat", params)
            return [{"address": {"country_code": "ru"}}]
        self.assertEqual(
            L.languages_for((55.7558, 37.6173), fetch=fake_fetch, use_cache=False),
            ["ru"])

    def test_nominatim_forward_fetch_resolves_unknown_city(self):
        # A city not in the curated/augmentation tables resolves via injected
        # Nominatim forward geocode country_code.
        def fake_fetch(params):
            return [{"address": {"country_code": "gr"}, "lat": "37.9", "lon": "23.7",
                     "addresstype": "city", "type": "city", "class": "place"}]
        self.assertEqual(
            L.languages_for("Nafplio old town", fetch=fake_fetch, use_cache=False),
            ["el"])


class TestWikidataLanguageEnrichment(unittest.TestCase):

    def test_p37_p2936_mapped_and_appended(self):
        # Switzerland Q39: P37 de/fr/it/rm; we map the ones we know and append any
        # new code to the country-table answer.
        def fake(qid):
            return {"entities": {"Q39": {"claims": {
                "P37": [
                    {"mainsnak": {"datavalue": {"value": {"id": "Q188"}}}},   # de
                    {"mainsnak": {"datavalue": {"value": {"id": "Q150"}}}},   # fr
                    {"mainsnak": {"datavalue": {"value": {"id": "Q652"}}}},   # it
                ]}}}}
        codes = L.wikidata_languages_for_country("Q39", fetch=fake)
        self.assertEqual(codes, ["de", "fr", "it"])

    def test_enrichment_appends_without_reordering_table(self):
        # France table answer is ["fr"]; a P2936 that adds Breton-equivalent code
        # we know (none here) would append; an unknown qid is ignored, order kept.
        def fake(qid):
            return {"entities": {"Q142": {"claims": {
                "P37": [{"mainsnak": {"datavalue": {"value": {"id": "Q150"}}}}],
                "P2936": [{"mainsnak": {"datavalue": {"value": {"id": "Q7026"}}}}],  # ca
            }}}}
        langs = L.languages_for("Perpignan", country_qid="Q142",
                                wikidata_fetch=fake, use_cache=False,
                                _request_text="Perpignan, France")
        self.assertEqual(langs[0], "fr")
        self.assertIn("ca", langs)  # appended from Wikidata P2936


class TestP31Mapping(unittest.TestCase):
    """The P31 Q-id -> (group, subtype) map: the ten the ticket lists, each exact."""

    TEN = {
        "Q16970": ("religious", "church"),
        "Q44539": ("religious", "temple"),
        "Q863454": ("maritime", "pier"),
        "Q8502": ("peaks", "mountain"),
        "Q35509": ("depression", "cave"),
        "Q34038": ("water", "waterfall"),
        "Q39594": ("water", "bay"),
        "Q16560": ("royal", "palace"),
        "Q153562": ("performance", "opera_house"),
        "Q39715": ("maritime", "lighthouse"),
    }

    def test_ten_qids_present_and_correct(self):
        self.assertGreaterEqual(len(L.P31_SUBTYPE), 10)
        for qid, expected in self.TEN.items():
            with self.subTest(qid=qid):
                self.assertEqual(L.P31_SUBTYPE.get(qid), expected)

    def test_classify_place_uses_p31_first(self):
        for qid, (group, subtype) in self.TEN.items():
            with self.subTest(qid=qid):
                r = L.classify_place("某地", wikidata_instance_of=qid)
                self.assertEqual((r["group"], r["subtype"]), (group, subtype))
                self.assertGreaterEqual(r["confidence"], 0.9)  # wikidata confidence


class TestLanguageFreeClassification(unittest.TestCase):
    """A Chinese temple, a Russian church, a French lighthouse, a Spanish market."""

    def test_chinese_temple_by_p31(self):
        # 龍山寺 (Longshan Temple), P31 Q44539 -> religious/temple, language-free.
        r = L.classify_place("龍山寺", wikidata_instance_of="Q44539",
                             language="zh-Hant")
        self.assertEqual((r["group"], r["subtype"]), ("religious", "temple"))

    def test_russian_church_by_p31(self):
        # Храм Христа Спасителя (Cathedral of Christ the Saviour), P31 Q16970.
        r = L.classify_place("Храм Христа Спасителя", wikidata_instance_of="Q16970",
                             language="ru")
        self.assertEqual((r["group"], r["subtype"]), ("religious", "church"))

    def test_french_lighthouse_by_p31_and_by_name(self):
        r = L.classify_place("Phare de Cordouan", wikidata_instance_of="Q39715",
                             language="fr")
        self.assertEqual((r["group"], r["subtype"]), ("maritime", "lighthouse"))
        # and from the French name word alone (no P31)
        r2 = L.classify_place("Phare de Gatteville", language="fr")
        self.assertEqual((r2["group"], r2["subtype"]), ("maritime", "lighthouse"))

    def test_spanish_market_is_both(self):
        # Mercado de San Miguel — a famous market -> `both` (landmark + business).
        r = L.classify_place("Mercado de San Miguel", language="es")
        self.assertEqual(r["group"], "both")
        self.assertEqual(r["subtype"], "market")

    def test_russian_church_name_only_also_classifies(self):
        # Even without P31, the Russian stem "храм" classifies as religious/church.
        r = L.classify_place("Храм Василия Блаженного", language="ru")
        self.assertEqual(r["group"], "religious")


class TestKindWords(unittest.TestCase):

    def test_en_vi_from_fixtures_no_llm(self):
        def boom(_lang):
            raise AssertionError("fixtures must not call the LLM")
        en = L.kind_words("en", llm=boom, use_cache=False)
        vi = L.kind_words("vi", llm=boom, use_cache=False)
        self.assertIn("church", en)
        self.assertIn("temple", en)
        self.assertIn("street_area", en)
        self.assertIn("temple", vi)
        self.assertIn("chùa", vi["temple"])
        self.assertIn("nhà thờ", vi["church"])

    def test_third_language_generated_once_then_cached(self):
        calls = {"n": 0}

        def fake_llm(lang):
            calls["n"] += 1
            self.assertEqual(lang, "zh-Hant")
            return {"temple": ["寺", "廟"], "church": ["教堂"],
                    "palace": ["宮", "殿"], "street_area": ["街", "路"]}

        # use_cache=True exercises the per-process memo (DB may be absent offline,
        # which simply means the memo is the cache — still 0 calls on the second).
        first = L.kind_words("zh-Hant", llm=fake_llm, use_cache=True)
        second = L.kind_words("zh-Hant", llm=fake_llm, use_cache=True)
        self.assertEqual(first["temple"], ["寺", "廟"])
        self.assertEqual(second["temple"], ["寺", "廟"])
        self.assertEqual(calls["n"], 1, "second call must make NO LLM generation")

    def test_llm_failure_falls_back_to_english_fixture(self):
        def none_llm(_lang):
            return None
        out = L.kind_words("xx-NoSuchLang", llm=none_llm, use_cache=False)
        # Safe fallback so a stop still classifies.
        self.assertIn("church", out)
        self.assertIn("temple", out)

    def test_kind_word_keys_cover_subtypes_street_and_business(self):
        keys = set(L.KIND_WORD_KEYS)
        subtypes = {sub for _g, sub, _l in pk._T}
        self.assertTrue(subtypes <= keys)
        self.assertIn("street_area", keys)
        for w in pk.BUSINESS_WORDS:
            self.assertIn(w, keys)


class TestResearchHelpers(unittest.TestCase):

    def test_country_gl_hl(self):
        self.assertEqual(L.country_gl_hl("tw", "zh-Hant"),
                         {"gl": "tw", "hl": "zh-Hant"})
        self.assertEqual(L.country_gl_hl("fr", "fr"), {"gl": "fr", "hl": "fr"})
        self.assertEqual(L.country_gl_hl("ru", "ru"), {"gl": "ru", "hl": "ru"})

    def test_serper_local_queries_use_local_name_and_kind_words(self):
        words = {"temple": ["寺", "廟"]}
        out = L.serper_local_queries(
            "Longshan Temple", "Taipei", "zh-Hant", "tw",
            local_name="艋舺龍山寺", words=words, subtype="temple")
        self.assertEqual(out["gl"], "tw")
        self.assertEqual(out["hl"], "zh-Hant")
        self.assertEqual(out["local_name"], "艋舺龍山寺")
        self.assertTrue(out["queries"])
        # the local name is used, and at least one query carries a local kind word
        self.assertTrue(all("艋舺龍山寺" in q for q in out["queries"]))
        self.assertTrue(any("寺" in q or "廟" in q for q in out["queries"]))

    def test_local_alias_from_injected_label_fetch(self):
        def label(name, lang):
            return {"zh-Hant": "艋舺龍山寺"}.get(lang, "")
        self.assertEqual(L.local_alias("Longshan Temple", "zh-Hant",
                                       label_fetch=label), "艋舺龍山寺")
        # when the label equals the name, no alias is added
        self.assertEqual(L.local_alias("Paris", "fr",
                                       label_fetch=lambda n, l: "Paris"), "")

    def test_local_wikipedia_evidence_offline_injected(self):
        # The real non-English path follows the English article's interlanguage
        # link and marks the resulting page `trusted` (a local title rarely
        # string-matches the English stop name). Mirror that shape here.
        def fake_fetch(name, lang):
            return {"pages": [{"title": "艋舺龍山寺",
                               "lead": "艋舺龍山寺是台北市的寺廟。",
                               "wikitext": ""}],
                    "trusted": True}
        art = L.local_wikipedia_evidence("Longshan Temple", "zh-Hant",
                                         fetch_fn=fake_fetch, use_cache=False)
        self.assertIsNotNone(art)
        self.assertEqual(art["title"], "艋舺龍山寺")

    def test_escalate_bundle_offline(self):
        def wiki(name, lang):
            if lang in ("en", "zh-Hant"):
                return {"pages": [{"title": name, "lead": f"{name} lead ({lang}).",
                                   "wikitext": ""}]}
            return {"pages": []}
        bundle = L.escalate_local_language(
            "Longshan Temple", "Longshan Temple and Ximending walk, Taipei",
            wikidata_instance_of="Q44539", local_name="艋舺龍山寺",
            wiki_fetch_fn=wiki, use_cache=False)
        self.assertEqual(bundle["dominant"], "zh-Hant")
        self.assertEqual(bundle["languages"], ["zh-Hant"])
        self.assertEqual(bundle["country_code"], "tw")
        self.assertEqual(bundle["classification"]["subtype"], "temple")
        self.assertEqual(bundle["local_alias"], "艋舺龍山寺")
        self.assertEqual(bundle["serper"]["gl"], "tw")
        self.assertIn("en", bundle["wikipedia"])
        self.assertIn("zh-Hant", bundle["wikipedia"])


if __name__ == "__main__":
    unittest.main()
