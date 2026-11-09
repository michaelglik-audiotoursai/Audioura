"""test_local873b_thin_stop_fixes.py — LOCAL-873B.

The bounce of LOCAL-873. Four fixes, each asserted here OFFLINE (no network, no
paid call):

  1. THE đ-FOLD AT SOURCE. ``user_stop_narration._fold`` (= ``user_stop_verify._fold``,
     the one the OLD D759 retrieval uses) now folds đ/Đ → d, so "Bạch Đằng Pier"
     folds to "bach dang pier" and an English "Bach Dang Pier" snippet is
     accepted by ``_snippet_names_venue`` (it was rejected before).

  2. BOOK STREET — escalated facts reach the delivered narration. 13 facts fed
     through the user-stop fact-sheet verify path (via ``thin_facts_by_title``)
     keep ≥ 5 fact-traceable sentences in the final text instead of being dropped
     as UNSUPPORTED.

  3. POST-NARRATION THIN CHECK. A delivered body with < 3 sourced specifics
     (Bạch Đằng Pier, Ho Chi Minh City Hall) is rebuilt from the sourced facts to
     carry ≥ 3 traceable specifics; a body that already has ≥ 3 is left untouched.

  4. WRONG-WARD ORIENTATION. With the Pier pin, the admin-geography filter drops
     the "Thủ Dầu Một ward" / "Bình Mỹ" / "northern part of Ho Chi Minh City"
     Orientation geography, and the delivered Orientation never names them.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import user_stop_narration as usn  # noqa: E402
import user_stop_verify as usv  # noqa: E402
import thin_stop_delivery as tsd  # noqa: E402


# ── 1. the đ-fold at source ───────────────────────────────────────────────────
class TestDjFoldAtSource(unittest.TestCase):
    def test_fold_folds_dj(self):
        # "Đằng" must fold to "dang", not "đang".
        self.assertEqual(usn._fold("Bạch Đằng Pier"), "bach dang pier")
        self.assertEqual(usn._fold("Đường Đồng Khởi"), "duong dong khoi")

    def test_verify_fold_is_the_same_helper(self):
        # One shared helper: user_stop_verify imports _fold from user_stop_narration.
        self.assertIs(usv._fold, usn._fold)

    def test_name_tokens_are_ascii(self):
        # The distinctive tokens are now ASCII (bach, dang), so an English snippet
        # can match them.
        self.assertEqual(usv._name_tokens("Bạch Đằng Pier"), ["bach", "dang", "pier"])

    def test_english_snippet_accepted_on_old_path(self):
        # The exact bug: an English "Bach Dang Pier" snippet was rejected because
        # "đang" never matched "dang". Now accepted.
        poi = {"type_specialty": "Riverfront Area"}
        self.assertTrue(usv._snippet_names_venue(
            "Bạch Đằng Pier", "Bach Dang Pier", "Bach Dang Pier in Ho Chi Minh City",
            poi, "Ho Chi Minh City"))

    def test_unrelated_snippet_still_rejected(self):
        poi = {"type_specialty": "Riverfront Area"}
        self.assertFalse(usv._snippet_names_venue(
            "Bạch Đằng Pier", "", "A guide to the best coffee in Paris.",
            poi, "Ho Chi Minh City"))


# ── 2. escalated facts reach the delivered narration (Book Street path) ───────
BOOK_STREET = "Nguyễn Văn Bình Book Street"

# 13 sourced facts the LOCAL-873 escalation returned for Book Street (the log's
# "escalated -> 13 sourced fact(s)"). Each is a specific, venue-naming fact.
THIRTEEN_FACTS = [
    "Nguyễn Văn Bình Book Street opened in 2016 as Vietnam's first dedicated book street.",
    "The street runs for about 100 meters beside the Saigon Central Post Office.",
    "More than 20 bookstores and publishers operate permanent stalls along the street.",
    "The street was named after Nguyễn Văn Bình, a 20th-century Catholic archbishop.",
    "Open-air cafes line the pedestrian street under rows of shade trees.",
    "The book street hosts literary events, author signings and seasonal book fairs.",
    "A book-exchange corner lets readers trade secondhand books along the street.",
    "The street attracts around 1.5 million visitors a year, many of them students.",
    "It was built on a former colonial-era service lane between two French buildings.",
    "The street sells books in Vietnamese, English, French and other languages.",
    "A small coffee kiosk at the entrance anchors the street's cafe culture.",
    "The city designed the street to foster a reading culture in District 1.",
    "Weekend crowds fill the street for poetry readings and children's book days.",
]


def _fake_openai_keep_facts(system, user, api_key, model, timeout=40, max_tokens=1500):
    """Offline verifier: label a sentence SUPPORTED when it shares >=3 content
    tokens with any fact-sheet source line, else SENSORY. Mirrors the real
    model's job (judge against the fact sheet) deterministically."""
    import json
    import re

    def toks(s):
        return {w for w in re.findall(r"[a-z]{4,}", s.lower())}

    # Parse the fact-sheet source lines and the numbered sentences per stop.
    stops_out = []
    # crude but sufficient parse of the user message the module builds
    blocks = user.split("STOP id=")
    for b in blocks[1:]:
        try:
            sid = int(b.split("—", 1)[0].strip())
        except Exception:
            continue
        src_part = b.split("FACT SHEET:", 1)[1].split("SENTENCES:", 1)
        fact_blob = src_part[0]
        sent_blob = src_part[1] if len(src_part) > 1 else ""
        source_tokens = []
        for ln in fact_blob.splitlines():
            ln = ln.strip()
            if ln.startswith("source:"):
                source_tokens.append(toks(ln))
        labels = []
        for ln in sent_blob.splitlines():
            m = re.match(r"\s*(\d+)\.\s*(.+)", ln)
            if not m:
                continue
            i = int(m.group(1))
            st = toks(m.group(2))
            supported = any(len(st & fs) >= 3 for fs in source_tokens)
            labels.append({"i": i, "label": "SUPPORTED" if supported else "SENSORY"})
        stops_out.append({"id": sid, "labels": labels})
    return {"stops": stops_out}, 100, 50


class TestBookStreetFactsReachNarration(unittest.TestCase):
    def test_thirteen_facts_keep_at_least_five_sentences(self):
        # A delivered Book Street block whose body is written FROM the 13 facts.
        body_sentences = [
            "Nguyễn Văn Bình Book Street opened in 2016 as Vietnam's first dedicated book street.",
            "The street runs for about 100 meters beside the Saigon Central Post Office.",
            "More than 20 bookstores and publishers operate permanent stalls along the street.",
            "The street was named after Nguyễn Văn Bình, a Catholic archbishop.",
            "The book street hosts literary events, author signings and seasonal book fairs.",
            "The street attracts around 1.5 million visitors a year.",
        ]
        tour = (
            "Step-by-step tour.\n\n"
            f"Stop 1: {BOOK_STREET}\n\n"
            "Coordinates: 10.780564, 106.699820\n\n"
            "Type/Specialty: Book Street\n\n"
            "Orientation: Take a moment at the entrance to get your bearings.\n\n"
            + " ".join(body_sentences) + "\n\n"
            "Directions: Head southwest for 600 meters.\n"
        )
        new_text, rep = self._run_with_patched_openai(tour)
        # >= 5 of the fact sentences survive in the final text.
        kept = sum(1 for s in body_sentences[:6]
                   if s.split(",")[0][:40] in new_text)
        self.assertGreaterEqual(kept, 5,
            f"expected >=5 fact sentences in final text, kept {kept}")

    def _run_with_patched_openai(self, tour):
        orig = usv._call_openai
        usv._call_openai = _fake_openai_keep_facts
        try:
            new_text, rep = usv.verify_user_stops_in_text(
                tour, [BOOK_STREET], "Ho Chi Minh City, Vietnam",
                api_key="x", model="gpt-4.1-mini", log=None,
                thin_facts_by_title={BOOK_STREET: THIRTEEN_FACTS},
                retrieve=False)
        finally:
            usv._call_openai = orig
        return new_text, rep


# ── 3. post-narration delivered-body thin check ───────────────────────────────
PIER = "Bạch Đằng Pier"
PIER_FACTS = [
    "Bạch Đằng Pier was built along the Saigon River as a key ferry terminal in the French colonial era.",
    "The pier served as a departure point for boats during the final days of the war in 1975.",
    "The riverfront promenade at the pier stretches for about 1.3 kilometers along the water.",
    "Bạch Đằng Pier is a landing for river tour boats that run to the Củ Chi Tunnels.",
]


class TestPostNarrationThinCheck(unittest.TestCase):
    def _tour(self, pier_body, museum_body):
        return (
            "Step-by-step tour.\n\n"
            f"Stop 1: {PIER}\n\n"
            "Coordinates: 10.775263, 106.706880\n\n"
            "Type/Specialty: Riverfront Area\n\n"
            "Orientation: Approach the pier from the promenade.\n\n"
            + pier_body + "\n\n"
            "Directions: Head south for 500 meters.\n\n"
            "Stop 2: War Remnants Museum\n\n"
            "Coordinates: 10.779511, 106.692090\n\n"
            "Type/Specialty: Museum\n\n"
            + museum_body + "\n"
        )

    def test_thin_delivered_body_rebuilt_to_three_specifics(self):
        pier_thin = ("Bạch Đằng Pier is a riverfront area in Ho Chi Minh City. "
                     "It is a pleasant place with lovely scenic views.")
        museum_ok = ("The War Remnants Museum was founded on September 4, 1975. "
                     "It welcomes over a million visitors each year. "
                     "The courtyard displays armored vehicles from the war. "
                     "A photography gallery inside opened to the public in 1995.")
        tour = self._tour(pier_thin, museum_ok)
        new_text, rep = tsd.rebuild_thin_delivered_stops(
            tour, "Ho Chi Minh City", facts_by_title={PIER: PIER_FACTS},
            escalate_fn=lambda *a, **k: None)
        self.assertEqual(rep["rebuilt"], 1)
        # The Pier block now carries >= 3 sourced specifics traceable to facts.
        pier_block = new_text.split("Stop 2:")[0]
        pier_body = "\n".join(
            l for l in pier_block.splitlines()
            if l.strip() and not l.lower().startswith(
                ("stop ", "coordinates:", "type/specialty:", "orientation:",
                 "directions:")))
        self.assertGreaterEqual(
            tsd.count_delivered_specifics(pier_body, PIER_FACTS), 3)

    def test_rich_delivered_body_left_untouched(self):
        pier_ok = (
            "Bạch Đằng Pier was built along the Saigon River as a ferry terminal. "
            "The pier served as a departure point for boats in 1975. "
            "The riverfront promenade stretches about 1.3 kilometers along the water. "
            "Today the pier is a landing for river tour boats bound for the Củ Chi Tunnels.")
        museum_ok = ("The War Remnants Museum was founded in 1975. "
                     "It welcomes over a million visitors each year. "
                     "The courtyard displays armored vehicles from the war. "
                     "A photography gallery inside opened in 1995.")
        tour = self._tour(pier_ok, museum_ok)
        new_text, rep = tsd.rebuild_thin_delivered_stops(
            tour, "Ho Chi Minh City", facts_by_title={PIER: PIER_FACTS},
            escalate_fn=lambda *a, **k: None)
        self.assertEqual(rep["rebuilt"], 0)
        self.assertEqual(new_text, tour)

    def test_escalates_now_when_no_facts_yet(self):
        # A thin stop with NO pre-gathered facts escalates once via escalate_fn.
        pier_thin = "Bạch Đằng Pier is a nice riverfront area."
        museum_ok = ("The War Remnants Museum was founded in 1975. "
                     "The courtyard displays armored vehicles from the war. "
                     "A photography exhibit inside opened in 1995. "
                     "The museum welcomes over a million visitors each year.")
        tour = self._tour(pier_thin, museum_ok)
        calls = []

        def fake_escalate(name, scope, **kw):
            calls.append(name)
            return {"facts": [{"text": f, "url": "http://x"} for f in PIER_FACTS],
                    "cost_usd": 0.004}

        new_text, rep = tsd.rebuild_thin_delivered_stops(
            tour, "Ho Chi Minh City", facts_by_title={}, escalate_fn=fake_escalate)
        self.assertIn(PIER, calls)
        self.assertEqual(rep["escalated"], 1)
        self.assertEqual(rep["rebuilt"], 1)
        self.assertLessEqual(rep["added_cost_usd"], 0.01 + 1e-9)

    def test_fact_filter_rejects_offpin_facts(self):
        # A fact_filter that rejects any fact mentioning a far-away place keeps it
        # out of the rebuilt body (mirrors the 855B off-pin pre-filter).
        pier_thin = "Bạch Đằng Pier is a nice riverfront area."
        museum_ok = ("The War Remnants Museum was founded in 1975. "
                     "The courtyard displays armored vehicles from the war. "
                     "A photography exhibit inside opened in 1995. "
                     "The museum welcomes over a million visitors each year.")
        tour = self._tour(pier_thin, museum_ok)
        facts = PIER_FACTS + [
            "The pier is 230 kilometers from Con Dao prison island."]

        def reject_condao(title, sentence, block):
            return "Con Dao" not in sentence

        new_text, rep = tsd.rebuild_thin_delivered_stops(
            tour, "Ho Chi Minh City", facts_by_title={PIER: facts},
            escalate_fn=lambda *a, **k: None, fact_filter=reject_condao)
        self.assertNotIn("Con Dao", new_text)
        self.assertEqual(rep["rebuilt"], 1)


# ── 4. wrong-ward Orientation ─────────────────────────────────────────────────
class TestWrongWardOrientation(unittest.TestCase):
    PIER_POI = {"name": PIER, "title": PIER, "user_explicit": True,
                "type_specialty": "Riverfront Area",
                "coordinates": "10.775263, 106.706880"}

    def test_admin_geo_filter_catches_the_wrong_ward(self):
        bad = ("Approach Bạch Đằng Pier from the riverside promenade where the "
               "Saigon River widens, near the boundary of Thủ Dầu Một ward. "
               "Take in the view toward Bình Mỹ across the Saigon River to the "
               "west, one of the adjacent wards that mark this northern part of "
               "Ho Chi Minh City.")
        scrubbed, dropped = usn.scrub_user_stop_body(
            bad, self.PIER_POI, "Ho Chi Minh City, Vietnam", source_gated=False)
        self.assertTrue(dropped)
        self.assertNotIn("Thủ Dầu Một", scrubbed)
        self.assertNotIn("Bình Mỹ", scrubbed)
        self.assertNotIn("northern part of Ho Chi Minh City", scrubbed)

    def test_final_text_scrub_strips_ward_from_orientation(self):
        tour = (
            "Step-by-step tour.\n\n"
            f"Stop 1: {PIER}\n\n"
            "Coordinates: 10.775263, 106.706880\n\n"
            "Type/Specialty: Riverfront Area\n\n"
            "Orientation: Approach the pier near the boundary of Thủ Dầu Một ward. "
            "Take in the view toward Bình Mỹ across the Saigon River to the west.\n\n"
            "Bạch Đằng Pier sits on the Saigon River in District 1. Boats depart "
            "here for the Củ Chi Tunnels.\n\n"
            "Directions: Head south for 500 meters.\n"
        )
        new_text, _n = usn.scrub_tour_text_user_stops(
            tour, [PIER], "Ho Chi Minh City, Vietnam")
        self.assertNotIn("Thủ Dầu Một", new_text)
        self.assertNotIn("Bình Mỹ", new_text)

    def test_on_pin_sentence_is_kept(self):
        good = ("Bạch Đằng Pier sits on the Saigon River in District 1. "
                "Boats depart here for the Củ Chi Tunnels.")
        scrubbed, dropped = usn.scrub_user_stop_body(
            good, self.PIER_POI, "Ho Chi Minh City, Vietnam", source_gated=False)
        self.assertIn("District 1", scrubbed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
