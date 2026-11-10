#!/usr/bin/env python3
"""LOCAL-887 offline tests (no network, no LLM): the grounding gate must SEE the passage
that supports a sentence; a defining event deep in an article is found; a local-language
article is used when no en article exists; a departure sentence is FACTUAL."""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import strict_grounding_gate as g  # noqa: E402
import landmark_wikipedia_evidence as lwe  # noqa: E402
import signature_story as sig  # noqa: E402

# ---- City Hall replay: a 17 KB bundle whose supporting passage sits past char 6000 ----
FILLER = ("Ho Chi Minh was a revolutionary leader who spent years abroad and returned "
          "to lead the movement in later decades. ") * 3
LEAD = ("Ho Chi Minh City Hall is a building in the city centre, now the seat of the "
        "People's Committee. ")
SUPPORT = ("The Hôtel de Ville was constructed between 1898 and 1909 to designs by the "
           "architect Paul Gardès in the French colonial style.")
BUNDLE = LEAD + "\n" + "\n".join(FILLER + f"Paragraph {i}." for i in range(70)) + "\n" + SUPPORT + "\n" + \
    "\n".join(FILLER + f"Tail {i}." for i in range(30))
SENT = "The building was constructed between 1898 and 1909 to designs by Paul Gardès."


def judge_by_window(system, user, model):
    """A stand-in judge: SUPPORTED iff the year AND the name are in the EVIDENCE it was sent."""
    ev = user.split("EVIDENCE:\n", 1)[1].split("\n\nFACTUAL SENTENCES:", 1)[0]
    ok = "1898" in ev and "Gardès" in ev
    return {"verdicts": [{"i": 1, "verdict": "SUPPORTED" if ok else "UNSUPPORTED",
                          "evidence": "", "legend": False}]}, 100, 20


class CityHallReplay(unittest.TestCase):
    def test_bundle_is_long_and_support_is_past_old_cut(self):
        self.assertGreater(len(BUNDLE), 16000)
        self.assertGreater(BUNDLE.index("1898"), 6000)

    def test_old_head_truncation_would_drop_it(self):
        self.assertNotIn("1898", BUNDLE[:6000])

    def test_gate_keeps_the_supported_sentence(self):
        out, rep = g.apply_grounding_gate("City Hall", SENT + " You stand before it.", BUNDLE,
                                          classify_fn=judge_by_window)
        self.assertIn("1898", out)
        self.assertEqual(rep["unsupported"], 0)
        self.assertEqual(rep["kept"] >= 1, True)

    def test_focus_window_is_bounded_and_keeps_the_lead(self):
        w = g.focus_evidence(BUNDLE, [SENT])
        self.assertLessEqual(len(w), g.EVIDENCE_WINDOW + 10)
        self.assertIn("Gardès", w)
        self.assertIn("People's Committee", w)

    def test_second_look_rescues_a_chunk_outside_the_first_window(self):
        calls = []

        def fn(system, user, model):
            calls.append(user)
            ev = user.split("EVIDENCE:\n", 1)[1].split("\n\nFACTUAL SENTENCES:", 1)[0]
            sup = "1898" in ev and len(calls) > 1      # first call: hostile window
            if len(calls) == 1:
                return {"verdicts": [{"i": 1, "verdict": "UNSUPPORTED"}]}, 10, 5
            return {"verdicts": [{"i": 1, "verdict": "SUPPORTED" if sup else "UNSUPPORTED"}]}, 10, 5
        # make the first window miss the support: many chunks matching the tokens better
        noise = "\n".join(f"Paul Gardès and the 1898 survey, note {i}, are unrelated filler text here." for i in range(300))
        ev = LEAD + "\n" + noise + "\n" + SUPPORT.replace("Gardès", "Gardès")
        out, rep = g.apply_grounding_gate("City Hall", SENT, ev, classify_fn=fn)
        self.assertEqual(len(calls) <= 2, True)

    def test_short_evidence_unchanged(self):
        self.assertEqual(g.focus_evidence("abc def", ["x"]), "abc def")


# ---- signature story: a famous event deep in the article --------------------------
def make_article():
    """A generic fixture landmark (NOT the Palace): the defining event sits at the end."""
    paras = ["== History =="]
    for i in range(40):
        paras.append(f"The Harbour Fort committee met in {1700 + i} to discuss the repair of the "
                     f"eastern wall and the supply of timber for the roof, as recorded by clerk "
                     f"Anton Weller number {i}.")
    paras.append("== Siege ==")
    paras.append("On 12 March 1848 an insurgent cannon tank crashed through the main gates of the "
                 "Harbour Fort and the garrison surrendered, ending the siege of the port.")
    return "\n".join(paras)


class FamousEvent(unittest.TestCase):
    def test_event_sentence_found_in_full_article(self):
        ev = lwe.event_sentences(make_article(), 3)
        self.assertTrue(ev and "12 March 1848" in ev[0])

    def test_passage_selection_favours_famous_event(self):
        psg = lwe.select_passages(make_article(), "", cap=700)
        self.assertIn("crashed through the main gates", psg)

    def test_signature_prompt_carries_the_event_even_when_evidence_is_long(self):
        long_ev = ("Harbour Fort is a coastal fortress. " * 400) + \
                  "On 12 March 1848 an insurgent cannon tank crashed through the main gates of the Harbour Fort."
        self.assertGreater(len(long_ev), sig.MAX_INPUT_CHARS)
        prompt = sig._build_user_prompt("Harbour Fort", long_ev, "Anytown")
        self.assertIn("12 March 1848", prompt)

    def test_no_hard_coded_venue(self):
        src = open(os.path.join(os.path.dirname(__file__), "..", "landmark_wikipedia_evidence.py"),
                   encoding="utf-8").read()
        self.assertNotIn("Independence Palace", src.split("_FAMOUS_RE")[1][:2500])


# ---- local-language article when no en article ------------------------------------
class LocalLanguage(unittest.TestCase):
    def test_vi_article_is_used_when_no_en(self):
        import local_language as ll

        def fake_fetch(name, lang):
            if lang == "vi":
                return {"pages": [{"title": "Bến Bạch Đằng", "extract": "Bến Bạch Đằng là bến tàu trên sông Sài Gòn.",
                                   "wikitext": "", "coord": (10.7735, 106.7068)}]}
            return {"pages": []}
        art_calls = []
        orig = lwe.fetch_article

        def spy(name, lang="en", **kw):
            art_calls.append((name, lang))
            if lang == "vi" and "Bạch" in name and "(" not in name:
                return {"title": "Bến Bạch Đằng", "lead": "Bến Bạch Đằng là bến tàu trên sông Sài Gòn.",
                        "infobox": "", "full_text": "== Lịch sử ==\n" + "Bến được xây dựng năm 1860 bởi người Pháp để phục vụ tàu thuyền trên sông. " * 3}
            return None
        lwe.fetch_article = spy
        try:
            out = ll.escalate_local_language("Bạch Đằng Pier (tour-bus + waterbus)",
                                             "Ho Chi Minh City, Vietnam", languages=["vi"],
                                             country_code="vn", use_cache=False,
                                             llm=lambda lang: {}, pin=(10.7735, 106.7068))
        finally:
            lwe.fetch_article = orig
        self.assertIn("vi", out["wikipedia"])
        # the qualifier-stripped name was tried
        self.assertIn(("Bạch Đằng Pier", "vi"), art_calls)
        item = lwe.format_item(out["wikipedia"]["vi"], "vi")
        self.assertIn("Wikipedia (vi)", item)
        self.assertIn("Passages:", item)
        block = lwe.narrator_block("Bạch Đằng Pier", [item])
        self.assertIn("1860", block)               # narrator sees the local passage

    def test_thin_escalation_exposes_local_items(self):
        import thin_stop_search as ts
        art = {"title": "Bến Bạch Đằng", "lead": "Bến Bạch Đằng là bến tàu.", "infobox": "", "full_text": ""}
        rep = ts.escalate_thin_stop(
            "Bạch Đằng Pier", "Ho Chi Minh City, Vietnam", existing_facts=[],
            serp_fn=lambda q: [], fetch_fn=lambda u: "", llm_fn=lambda *a: (None, 0, 0),
            escalate_fn=lambda *a, **k: {"dominant": "vi", "wikipedia": {"vi": art}, "serper": {}},
            use_cache=False)
        self.assertEqual(len(rep["local_wikipedia_items"]), 1)
        self.assertIn("Wikipedia (vi)", rep["local_wikipedia_items"][0])


# ---- departure cue -------------------------------------------------------------------
class DepartureCue(unittest.TestCase):
    def test_departure_sentence_is_factual(self):
        for s in ("Parties leaving from here set out to explore the narrow tunnels beyond the city.",
                  "Boats depart from this pier every hour toward the delta islands.",
                  "Tours start at this pier and run along the river."):
            self.assertTrue(g.is_factual_sentence(s), s)

    def test_pure_navigation_still_exempt(self):
        self.assertFalse(g.is_factual_sentence("Follow the path from here and head north along the river."))

    def test_departure_without_evidence_is_dropped(self):
        out, rep = g.apply_grounding_gate(
            "Pier", "Parties leaving from here set out to explore the narrow tunnels beyond the city.", "")
        self.assertEqual(rep["unsupported"], 1)


if __name__ == "__main__":
    unittest.main()


# ---- City Hall REPLAY from the recorded 887 warm state ---------------------------
import json  # noqa: E402
FIX = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "local887_recorded.json"),
                     encoding="utf-8"))


class CityHallRecordedReplay(unittest.TestCase):
    """Root cause: the accepted 'own article' for City Hall was the biography 'Ho Chi Minh'
    (coordinate-less; match name 'Trụ sở Ủy ban Nhân dân Thành phố Hồ Chí Minh'), so
    1898/1909/Gardè were never in the 16.8 KB bundle and the gate was right to say
    UNSUPPORTED."""
    MN = FIX["city_hall_match_name"]
    PIN = tuple(FIX["city_hall_pin"])
    CITY = FIX["location"]

    def test_recorded_887_article_was_the_biography(self):
        en = FIX["city_hall_887_accepted_article"]["en"]
        self.assertEqual(en["title"], "Ho Chi Minh")
        self.assertNotIn("1898", en["lead"] + en["full_text"])

    def test_biography_rejected_by_pick(self):
        en = FIX["city_hall_887_accepted_article"]["en"]
        raw = {"pages": [{"title": en["title"], "lead": en["lead"], "wikitext": "",
                          "coord": None, "qid": ""}]}
        lwe._p625_for_qid, orig = (lambda q: None), lwe._p625_for_qid
        try:
            self.assertIsNone(lwe._pick(self.MN, raw, pin=self.PIN, city=self.CITY, match_name=self.MN))
            vi = FIX["city_hall_887_accepted_article"]["vi"]
            raw_vi = {"pages": [{"title": vi["title"], "lead": vi["lead"], "wikitext": "",
                                 "coord": None, "qid": ""}], "trusted": True}
            self.assertIsNone(lwe._pick(self.MN, raw_vi, pin=self.PIN, city=self.CITY, match_name=self.MN))
        finally:
            lwe._p625_for_qid = orig

    def test_biography_cache_row_fails_revalidation(self):
        en = FIX["city_hall_887_accepted_article"]["en"]
        self.assertFalse(lwe._revalidate_payload(en, self.MN, pin=self.PIN, city=self.CITY))

    def test_geo_fallback_finds_the_building(self):
        pages = {}
        for it in FIX["city_hall_fixed_items"]:
            p = lwe.split_item(it)
            pages[(p["title"], p["lang"])] = p

        def geos(pin, lang, r):
            return FIX["city_hall_geosearch"][lang]

        def ft(title, lang):
            p = pages.get((title, lang))
            if not p:
                return {"pages": []}
            return {"pages": [{"title": title, "lead": p["lead"], "wikitext": "",
                               "coord": self.PIN, "qid": "", "full_text": p["passages"]}]}
        art = lwe.geo_fallback_article(["City Hall", self.MN], "en", self.PIN, self.CITY,
                                       geosearch_fn=geos, fetch_title_fn=ft)
        self.assertEqual(art["title"], "Ho Chi Minh City Hall")
        art_vi = lwe.geo_fallback_article(["City Hall", self.MN], "vi", self.PIN, self.CITY,
                                          geosearch_fn=geos, fetch_title_fn=ft)
        self.assertIn("1898", art_vi["lead"])

    def test_gate_keeps_1898_1909_garde_sentence_on_fixed_evidence(self):
        ev = " ".join(FIX["city_hall_fixed_items"])
        sent = ("Construction of the Hôtel de Ville began in 1898 and it opened in 1909, "
                "directed by the architect Fernand Gardè.")

        def judge(system, user, model):
            w = user.split("EVIDENCE:\n", 1)[1].split("\n\nFACTUAL SENTENCES:", 1)[0]
            ok = all(t in w for t in ("1898", "1909", "Gardè"))
            return {"verdicts": [{"i": 1, "verdict": "SUPPORTED" if ok else "UNSUPPORTED"}]}, 1, 1
        out, rep = g.apply_grounding_gate("City Hall", sent, ev, classify_fn=judge)
        self.assertIn("1898", out)
        self.assertEqual(rep["unsupported"], 0)


class PierRecorded(unittest.TestCase):
    def test_pier_vi_article_found_at_pin(self):
        pin = tuple(FIX["pier_pin"])
        art = lwe.geo_fallback_article(
            ["Bạch Đằng Pier (tour-bus + waterbus)", "Bach Dang Quay"], "vi", pin, FIX["location"],
            geosearch_fn=lambda p, lang, r: FIX["pier_geosearch"][lang],
            fetch_title_fn=lambda t, lang: FIX["pier_vi_page"] if t == "Bến Bạch Đằng" else {"pages": []})
        self.assertIsNotNone(art)
        self.assertEqual(art["title"], "Bến Bạch Đằng")

    def test_far_or_unnamed_page_rejected(self):
        pin = tuple(FIX["pier_pin"])
        art = lwe.geo_fallback_article(
            ["Bạch Đằng Pier"], "vi", pin, FIX["location"],
            geosearch_fn=lambda p, lang, r: [{"title": "Khách sạn Majestic Saigon", "dist_m": 40}],
            fetch_title_fn=lambda t, lang: {"pages": [{"title": t, "lead": "x", "coord": pin}]})
        self.assertIsNone(art)


class EponymCoverage(unittest.TestCase):
    def test_title_covers_name(self):
        self.assertFalse(lwe.title_covers_name("Trụ sở Ủy ban Nhân dân Thành phố Hồ Chí Minh", "Ho Chi Minh"))
        self.assertTrue(lwe.title_covers_name("Saigon Opera House", "Saigon Opera House"))
        self.assertTrue(lwe.title_covers_name("Longshan Temple", "艋舺龍山寺"))
        self.assertTrue(lwe.title_covers_name("Bạch Đằng Pier", "Bến Bạch Đằng"))


class PluralEventCue(unittest.TestCase):
    def test_battles_sentence_is_factual(self):
        self.assertTrue(g.is_factual_sentence(
            "The name Bạch Đằng recalls the historic Bạch Đằng River, famous for legendary "
            "battles where Vietnamese forces defeated invaders."))
