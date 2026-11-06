"""LOCAL-870: wave-28 findings (tour 534, Sophia). All offline except one opt-in
live rater test (RUN_LIVE_RATING=1 + OPENAI_API_KEY; a few tenths of a cent).

1. Content rating: sexual orientation / gender identity is never a Mature signal.
2. Emoji never reach audio_N.txt or the TTS payload (logged).
3. A USER stop with only a MODEL coordinate and no reference ships with no pin,
   even when it is the last of its 250 m cluster.
4. A FAMOUS landmark user stop is classified landmark (story path), not business.
5. A person's name / street address never gets a word-etymology name bridge.
"""
import contextlib
import io
import os
import re
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pin_snap  # noqa: E402
import tour_content_rating as tcr  # noqa: E402
import tour_generation_modernized as tgm  # noqa: E402
import user_stop_context as usc  # noqa: E402
import user_stop_enrichment as use  # noqa: E402

EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]")

LGBT_TOUR = (
    "Stop 1: The LGBT bar Thi Bar Saigon. A gay bar on Đề Thám with a friendly crowd "
    "and a nightly drag show. Stop 2: Crazy Karaoke. Sing your heart out in a private "
    "room. Stop 3: An Spa. A quiet day spa for a massage and tea. Stop 4: Acoustic Bar. "
    "A live music bar with singers from many countries. " * 3)

EXPLICIT_TOUR = (
    "This tour visits venues that sell sex. Stop 1 graphically describes explicit "
    "sexual acts performed on stage and how to pay for them. " * 6)


class TestRatingPrompt(unittest.TestCase):
    """Offline: the instruction the model is held to (the model itself is covered
    by the opt-in live test below)."""

    def test_prompt_says_orientation_and_identity_never_mature(self):
        p = tcr.PROMPT
        self.assertRegex(p, r"(?i)sexual orientation or gender identity")
        self.assertRegex(p, r"(?i)NEVER a reason for .mature.")
        for w in ("LGBT bar", "drag", "karaoke"):
            self.assertIn(w, p)

    def test_prompt_keeps_policy_mature_and_not_allowed_definitions(self):
        # legal/CONTENT_POLICY.md: Mature = primary purpose drinking (bar crawl,
        # cocktail bars), nightlife as entertainment, gambling, profanity;
        # Not listed = sexual services / explicit sexual content.
        p = tcr.PROMPT
        self.assertIn("bar crawl", p)
        self.assertIn("explicit sexual content", p)
        self.assertIn("primary purpose", p)

    def test_prompt_is_what_classify_sends(self):
        sent = {}

        class _Msg:
            content = '{"rating": "general", "reason": "ok"}'

        class _Choice:
            message = _Msg()

        class _Usage:
            prompt_tokens = 1
            completion_tokens = 1

        class _Resp:
            choices = [_Choice()]
            usage = _Usage()

        class _Client:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kw):
                        sent["m"] = kw["messages"][0]["content"]
                        return _Resp()

        import openai
        old = getattr(openai, "OpenAI", None)
        openai.OpenAI = lambda *a, **k: _Client()
        try:
            detail, _ = tcr.classify("Sophia bars", LGBT_TOUR, 7)
        finally:
            if old is not None:
                openai.OpenAI = old
        self.assertEqual(detail["rating"], "general")
        self.assertIn("sexual orientation or gender identity", sent["m"])
        self.assertIn("Thi Bar Saigon", sent["m"])


@unittest.skipUnless(os.getenv("RUN_LIVE_RATING") == "1" and os.getenv("OPENAI_API_KEY"),
                     "live rater test is opt-in (RUN_LIVE_RATING=1)")
class TestRatingLive(unittest.TestCase):
    def test_lgbt_bar_drag_karaoke_tour_is_general(self):
        rating, detail = tcr.rate_text("Sophia's bars in Ho Chi Minh City", LGBT_TOUR, 4)
        self.assertEqual(rating, "general", detail)

    def test_explicit_sexual_content_is_not_general(self):
        rating, detail = tcr.rate_text("Adult tour", EXPLICIT_TOUR, 1)
        self.assertIn(rating, ("mature", "not_allowed"), detail)


class TestEmojiNeverInAudioTxtOrTts(unittest.TestCase):
    TEXT = ["Stop 5: The LGBT bar \U0001F308Thi Bar Saigon\nOrientation: A gay bar \U0001F308 on Đề Thám.\n"
            "Coordinates: 10.767660, 106.693960\n"]

    def test_zip_audio_txt_has_no_emoji_and_logs(self):
        tmp = os.path.join(os.path.dirname(__file__), "_tmp870")
        os.makedirs(tmp, exist_ok=True)
        old = tgm.TOURS_DIR
        tgm.TOURS_DIR = tmp
        buf = io.StringIO()
        path = None
        try:
            with contextlib.redirect_stdout(buf):
                name = tgm.create_modernized_tour_zip(
                    {"tour_name": "t870", "text_content": list(self.TEXT),
                     "audio_files": [b"x"]}, "job870000")
            path = os.path.join(tmp, name)
            with zipfile.ZipFile(path) as z:
                txt = z.read("audio_1.txt").decode()
        finally:
            tgm.TOURS_DIR = old
            if path and os.path.exists(path):
                os.remove(path)
            os.rmdir(tmp)
        self.assertNotRegex(txt, EMOJI)
        self.assertIn("Thi Bar Saigon", txt)
        self.assertIn("[LOCAL-863] TTS emoji strip at zip audio_1.txt", buf.getvalue())

    def test_tts_payload_has_no_emoji(self):
        with contextlib.redirect_stdout(io.StringIO()):
            out = tgm._strip_nav_fields_for_tts(self.TEXT[0])
        self.assertNotRegex(out, EMOJI)

    def test_helper_strips_every_stop_and_logs_stop_number(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out = tgm._strip_emoji_from_stop_texts(["a", "b \U0001F308 c"], "tour-modernized")
        self.assertEqual(out[0], "a")
        self.assertNotRegex(out[1], EMOJI)
        self.assertIn("tour-modernized audio_2.txt", buf.getvalue())


def _user_model_poi(name, coord, **kw):
    d = {"name": name, "title": name, "user_explicit": True,
         "coordinates": coord, "coord_source": "model"}
    d.update(kw)
    return d


def _snap(pois, **kw):
    logs = []
    pin_snap.snap_poi_coordinates(
        pois, scope="Ho Chi Minh City", scope_center=(10.776, 106.700),
        log=logs.append, reference_fn=lambda *a, **k: None,
        landmark_fn=lambda *a, **k: None, **kw)
    return logs


class TestLastOfClusterModelPin(unittest.TestCase):
    def test_user_stop_model_coord_cleared_when_neighbours_are_pins(self):
        star = _user_model_poi("A Star is Born", "10.7762, 106.6956")
        pois = [
            {"name": "Thi Bar", "user_explicit": True, "coordinates": "10.767660, 106.693960",
             "coord_source": "user_name_lookup"},
            {"name": "Acoustic Bar", "user_explicit": True, "coordinates": "10.781195, 106.689920",
             "coord_source": "user_name_lookup"},
            star,
        ]
        logs = _snap(pois)
        self.assertEqual(star["coordinates"], "")
        self.assertTrue(star.get("_no_coordinate"))
        self.assertTrue(any("[LOCAL-870]" in l and "A Star is Born" in l for l in logs), logs)
        self.assertEqual(pois[0]["coordinates"], "10.767660, 106.693960")

    def test_user_pin_source_is_kept(self):
        poi = _user_model_poi("A Star is Born", "10.7762, 106.6956",
                              coord_source="user_name_lookup")
        _snap([poi])
        self.assertEqual(poi["coordinates"], "10.7762, 106.6956")

    def test_non_user_stop_with_model_coord_not_cleared_by_this_rule(self):
        poi = {"name": "Some Cafe", "coordinates": "10.7762, 106.6956",
               "coord_source": "model"}
        _snap([poi])
        self.assertEqual(poi["coordinates"], "10.7762, 106.6956")

    def test_custom_user_stop_predicate_is_honoured(self):
        poi = {"name": "Title Only Stop", "coordinates": "10.7762, 106.6956",
               "coord_source": "model"}
        _snap([poi], is_user_stop_fn=lambda p: True)
        self.assertEqual(poi["coordinates"], "")


class TestFamousLandmarkUserStop(unittest.TestCase):
    def test_opera_house_is_landmark_even_with_business_type(self):
        for t in ("", "Live music venue", "Performing arts venue", "Concert hall"):
            self.assertEqual(use.classify_stop_kind("Saigon Opera House", t), "landmark", t)

    def test_businesses_with_institutional_words_stay_business(self):
        self.assertEqual(use.classify_stop_kind("Palace Bar", "Bar"), "business")
        self.assertEqual(use.classify_stop_kind("Temple Bar", "Pub"), "business")
        self.assertEqual(use.classify_stop_kind("Cathedral Cafe", "Cafe"), "business")
        self.assertEqual(use.classify_stop_kind("The Crazy Street", "Walking street"), "street_area")  # LOCAL-874
        self.assertEqual(use.classify_stop_kind("An Spa", "Spa"), "business")

    def test_existing_landmark_cases_unchanged(self):
        self.assertEqual(use.classify_stop_kind("Independence Palace", "Historical Site"),
                         "landmark")


class TestNameBridgeForPersonOrAddress(unittest.TestCase):
    FACTS = [{"kind": "name_meaning", "text": "Nguyen is a common Vietnamese surname."}]

    def test_person_name_gets_no_word_etymology(self):
        self.assertIsNone(
            usc.bridge_sentence("Book Street (Nguyễn Văn Bình)", "bookstore", self.FACTS))

    def test_pure_person_name_says_named_after(self):
        self.assertEqual(usc.bridge_sentence("Nguyễn Văn Bình", "street", self.FACTS),
                         "It is named after Nguyễn Văn Bình.")
        self.assertEqual(usc.bridge_sentence("Nguyễn Văn Bình", "", self.FACTS),
                         "It is named after Nguyễn Văn Bình.")

    def test_address_name_says_address(self):
        self.assertEqual(
            usc.bridge_sentence("Café Apartments 42 Nguyễn Huệ", "cafe", self.FACTS),
            "The cafe takes its name from its address on Nguyễn Huệ.")

    def test_comma_address_form_from_the_import(self):
        self.assertEqual(
            usc.bridge_sentence("Café Apartments, 42 Nguyễn Huệ", "cafe", self.FACTS),
            "The cafe takes its name from its address on Nguyễn Huệ.")

    def test_real_word_name_still_bridged(self):
        facts = [{"kind": "name_meaning", "text": "The longan fruit is called dragon eye."}]
        self.assertEqual(usc.bridge_sentence("Longan", "bar", facts),
                         "The bar probably takes its name from the longan fruit.")


if __name__ == "__main__":
    unittest.main()
