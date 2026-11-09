"""test_local873c_narrated_rebuild.py — LOCAL-873C.

LEAD read the 873B rebuild on Book Street (submission_artifacts/local873b/…,
Stop 3, Nguyễn Văn Bình Book Street) and found it reads like pasted web copy:

  1. the Orientation is repeated verbatim as the body's first three sentences;
  2. the appended facts are raw scraped copy with broken grammar / capitalisation
     ("Ho Chi Minh City Book Street Known as Nguyen Van Binh Book Street, is a
     cultural hub …");
  3. the facts are written WITHOUT diacritics (Nguyen Van Binh, Hai Ba Trung)
     while the rest of the tour uses the Vietnamese spelling.

873C: when the rebuild fires it makes ONE cheap gpt-4.1-mini call (temp 0.3)
constrained to the facts, rewriting the body as 5–7 spoken second-person
present-tense sentences, each traceable to a fact and cleared by the LOCAL-872
claim gate and the 873B fact-sheet verify; the Orientation is never repeated
(both directions). On failure/reject, the DETERMINISTIC append runs with the
three fixes (sentence-case, no "X Known as Y," fragment, local diacritic spelling
from the title). A rich stop is left unchanged. All OFFLINE — the LLM backend is
injected; no network, no paid call.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import thin_stop_delivery as tsd  # noqa: E402
from sentence_split import split_sentences  # noqa: E402
from thin_stop_search import fold  # noqa: E402

BOOK_STREET = "Nguyễn Văn Bình Book Street"

# The exact raw scraped facts the LOCAL-873 escalation returned for Book Street,
# as delivered by 873B (no diacritics, the "Known as" fragment, the list run-on).
BOOK_STREET_RAW_FACTS = [
    "Ho Chi Minh City Book Street Known as Nguyen Van Binh Book Street, is a "
    "cultural hub located in District 1, Ho Chi Minh City, Vietnam.",
    "Nguyen Van Binh book street is located right in the center of Ho Chi Minh "
    "City and stretches 100 meters from Hai Ba Trung street to Notre Dame Cathedral.",
    "Nguyen Van Binh street gathers many book publishers from the whole country "
    "and has a bookstore cafe, newspapers area, magazine area, stationery, old "
    "book exchange, book exhibition area, and newspapers or pictures area by topic.",
    "The book street opened in 2016 as the first book street in Vietnam.",
    "The street hosts literary events and book fairs throughout the year.",
]

ORIENTATION = ("Nguyễn Văn Bình Book Street is a book street in Ho Chi Minh "
               "City. It is known for charming book stalls, cozy cafés, "
               "literary events. Take a moment at the entrance to get your "
               "bearings before you go in.")


def _tour(body, orientation=ORIENTATION):
    return (
        "Step-by-step tour.\n\n"
        f"Stop 1: {BOOK_STREET}\n\n"
        "Coordinates: 10.780564, 106.699820\n\n"
        "Type/Specialty: Book Street\n\n"
        f"Orientation: {orientation}\n\n"
        + body + "\n\n"
        "Directions: Head southwest for about 600 meters.\n"
    )


def _book_street_body(new_text):
    block = new_text.split("Stop 1:")[1]
    out = []
    for ln in block.split("\n"):
        s = ln.strip()
        if not s:
            continue
        if s.lower().startswith(("stop ", "coordinates:", "type/specialty:",
                                 "specific examples:", "orientation:",
                                 "directions:", "sources")):
            continue
        out.append(ln)
    return "\n".join(out)


def _has_orientation_dup(body, orientation):
    def norm(s):
        return " ".join(fold(s).split())
    or_norms = [norm(s) for s in split_sentences(orientation) if len(norm(s)) >= 12]
    for s in split_sentences(body):
        n = norm(s)
        if not n:
            continue
        for on in or_norms:
            if n == on or (len(n) >= 12 and (n in on or on in n)):
                return True
    return False


# A fake narrator: rewrites the facts into clean second-person present-tense
# sentences (as the real gpt-4.1-mini is asked to). Each shares >=3 content
# tokens with a fact and repeats nothing from the Orientation.
def _fake_narrate_ok(system, user, model, temperature=0.3, timeout=40,
                     max_tokens=600):
    sentences = [
        "You are standing on Nguyễn Văn Bình Book Street in District 1.",
        "The street stretches 100 meters from Hải Bà Trưng street to Notre Dame Cathedral.",
        "It opened in 2016 as the first book street in Vietnam.",
        "Here many book publishers from across the country gather their stalls.",
        "You can browse a bookstore cafe, a magazine area, and an old book exchange.",
        "Throughout the year the street hosts literary events and book fairs.",
    ]
    return {"sentences": sentences}, 200, 90


def _fake_narrate_fail(system, user, model, temperature=0.3, timeout=40,
                       max_tokens=600):
    return None, 0, 0


class TestNarratedRebuild(unittest.TestCase):
    def test_narrated_body_no_orientation_dup_no_known_as_vietnamese(self):
        thin = ("Nguyễn Văn Bình Book Street is a book street in Ho Chi Minh City. "
                "It is known for charming book stalls, cozy cafés, literary events. "
                "Take a moment at the entrance to get your bearings before you go in.")
        tour = _tour(thin)
        new_text, rep = tsd.rebuild_thin_delivered_stops(
            tour, "Ho Chi Minh City, Vietnam",
            facts_by_title={BOOK_STREET: BOOK_STREET_RAW_FACTS},
            escalate_fn=lambda *a, **k: None,
            narrate_fn=_fake_narrate_ok)
        self.assertEqual(rep["rebuilt"], 1)
        self.assertEqual(rep.get("narrated"), 1)
        body = _book_street_body(new_text)
        sents = split_sentences(body)
        # >= 5 spoken sentences
        self.assertGreaterEqual(len(sents), 5, body)
        # no Orientation repeat (both directions)
        self.assertFalse(_has_orientation_dup(body, ORIENTATION), body)
        # no raw "Known as" fragment
        self.assertNotIn("Known as", new_text)
        # Vietnamese spelling present
        self.assertIn("Nguyễn Văn Bình", body)
        # second person / present tense cue
        self.assertIn("You", body)

    def test_fallback_path_no_known_as_vietnamese_no_dup(self):
        # Narration FAILS -> deterministic fallback with the 873C fixes.
        thin = ("Nguyễn Văn Bình Book Street is a book street in Ho Chi Minh City. "
                "It is known for charming book stalls, cozy cafés, literary events. "
                "Take a moment at the entrance to get your bearings before you go in.")
        tour = _tour(thin)
        new_text, rep = tsd.rebuild_thin_delivered_stops(
            tour, "Ho Chi Minh City, Vietnam",
            facts_by_title={BOOK_STREET: BOOK_STREET_RAW_FACTS},
            escalate_fn=lambda *a, **k: None,
            narrate_fn=_fake_narrate_fail)
        self.assertEqual(rep["rebuilt"], 1)
        self.assertEqual(rep.get("narrated", 0), 0)
        body = _book_street_body(new_text)
        # no raw "Known as" fragment survives the repair
        self.assertNotIn("Known as", new_text)
        # local diacritic spelling restored from the title
        self.assertIn("Nguyễn Văn Bình", body)
        # the verbatim Orientation sentences no longer open the body
        self.assertFalse(_has_orientation_dup(body, ORIENTATION), body)

    def test_rich_stop_left_unchanged(self):
        rich = (
            "You are standing on Nguyễn Văn Bình Book Street, which opened in 2016. "
            "The street stretches 100 meters toward Notre Dame Cathedral. "
            "Dozens of publishers from across the country set up stalls here. "
            "A bookstore cafe and an old book exchange line the shaded walk.")
        tour = _tour(rich)
        new_text, rep = tsd.rebuild_thin_delivered_stops(
            tour, "Ho Chi Minh City, Vietnam",
            facts_by_title={BOOK_STREET: BOOK_STREET_RAW_FACTS},
            escalate_fn=lambda *a, **k: None,
            narrate_fn=_fake_narrate_ok)
        self.assertEqual(rep["rebuilt"], 0)
        self.assertEqual(new_text, tour)

    def test_narration_rejects_unsourced_claim_then_falls_back(self):
        # A narrator that injects an unsourced named architect is caught by the
        # claim gate; if too few traceable sentences remain, it falls back.
        def _narrate_bad_claim(system, user, model, temperature=0.3, timeout=40,
                               max_tokens=600):
            return {"sentences": [
                "The street was designed by the famous architect Pham Van Dong.",
                "You see a grand marble arch built in 1702 at the entrance.",
            ]}, 50, 20

        import landmark_claim_gate as lcg

        def gate(sentence, title, evidence, loc):
            return lcg.unsourced_claims(sentence, title, evidence, known=(),
                                        location=loc or "")

        thin = ("Nguyễn Văn Bình Book Street is a book street in Ho Chi Minh City. "
                "Take a moment at the entrance to get your bearings.")
        tour = _tour(thin)
        new_text, rep = tsd.rebuild_thin_delivered_stops(
            tour, "Ho Chi Minh City, Vietnam",
            facts_by_title={BOOK_STREET: BOOK_STREET_RAW_FACTS},
            escalate_fn=lambda *a, **k: None,
            narrate_fn=_narrate_bad_claim, claim_gate_fn=gate)
        # The bad narration is rejected (not narrated); fallback rebuilds it.
        self.assertEqual(rep.get("narrated", 0), 0)
        self.assertNotIn("Pham Van Dong", new_text)
        self.assertNotIn("1702", new_text)


class TestRepairHelpers(unittest.TestCase):
    def test_repair_strips_known_as_fragment(self):
        raw = ("Ho Chi Minh City Book Street Known as Nguyen Van Binh Book "
               "Street, is a cultural hub located in District 1.")
        out = tsd.repair_fact_sentence(raw, BOOK_STREET)
        self.assertNotIn("Known as", out)
        self.assertTrue(out[0].isupper())

    def test_repair_restores_vietnamese_spelling(self):
        raw = "Nguyen Van Binh book street stretches 100 meters from Hai Ba Trung street."
        out = tsd.repair_fact_sentence(raw, "Nguyễn Văn Bình Book Street")
        self.assertIn("Nguyễn Văn Bình", out)

    def test_fact_sentences_apply_repair(self):
        out = tsd.fact_sentences(BOOK_STREET_RAW_FACTS, limit=8,
                                 require_specific=True, title=BOOK_STREET)
        joined = " ".join(out)
        self.assertNotIn("Known as", joined)
        self.assertIn("Nguyễn Văn Bình", joined)

    def test_dedup_against_orientation_both_directions(self):
        body = [
            "Nguyễn Văn Bình Book Street is a book street in Ho Chi Minh City.",
            "Take a moment at the entrance to get your bearings before you go in.",
            "It opened in 2016 as the first book street in Vietnam.",
        ]
        kept = tsd.dedup_against_orientation(body, ORIENTATION)
        self.assertEqual(len(kept), 1)
        self.assertIn("2016", kept[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
