"""test_local828_venue_identity_gate.py — LOCAL-828.

Unit tests for the venue-identity gate that drops injected research passages
belonging to ANOTHER museum/venue on a museum tour.

THE EXACT CASE (GCloud_Storied wave 7, gen 00016-62s, cheap arm): a Rijksmuseum
tour opened Stop 1 with a paragraph about Museum Catharijneconvent, Utrecht — a
different museum in a different city. These tests pin:

  * the Catharijneconvent passage is DROPPED for a Rijksmuseum tour, by subject
    AND by its catharijneconvent.nl domain, and the Rijksmuseum's own passage is
    kept;
  * Louvre vs Louvre Abu Dhabi / Louvre-Lens — a SEPARATE institution that shares
    the "Louvre" token is dropped, the Louvre's own passage is kept;
  * the Met vs The Met Cloisters — a separate institution is dropped, the Met's
    own passage is kept;
  * Belvedere vs Lower Belvedere — the SAME institution (a sub-unit) is KEPT;
  * the mandated log line, the city-contradiction rule, and the research-result
    (supports) scrub shape.

All offline, deterministic, no network/LLM/DB.

Run: python3 -m pytest test_local828_venue_identity_gate.py -q
"""
import re
import unittest

import venue_identity_gate as vig


# ─── identities ───────────────────────────────────────────────────────────────

RIJKS = vig.build_identity(
    venue_name="Rijksmuseum", qid="Q190804",
    official_url="https://www.rijksmuseum.nl", city="Amsterdam, Netherlands")
LOUVRE = vig.build_identity(
    venue_name="Louvre", qid="Q19675",
    official_url="https://www.louvre.fr", city="Paris, France")
MET = vig.build_identity(
    venue_name="The Metropolitan Museum of Art", qid="Q160236",
    official_url="https://www.metmuseum.org", city="New York",
    aliases=["The Met", "The Met Fifth Avenue"])
MET_FIFTH = vig.build_identity(
    venue_name="The Met Fifth Avenue", qid="Q160236",
    official_url="https://www.metmuseum.org", city="New York",
    aliases=["The Metropolitan Museum of Art"])
BELVEDERE = vig.build_identity(
    venue_name="Belvedere", qid="Q303139",
    official_url="https://www.belvedere.at", city="Vienna, Austria")


# ─── 1. the exact Rijksmuseum / Catharijneconvent case ────────────────────────

CATH = ("Museum Catharijneconvent in Utrecht is the national museum of Christian "
        "art and heritage in the Netherlands, housed in a former medieval convent.")
RIJKS_OWN = ("The Rijksmuseum in Amsterdam is the national museum of the "
             "Netherlands, home to Rembrandt's The Night Watch.")


class RijksmuseumCatharijneconvent(unittest.TestCase):
    def test_catharijneconvent_dropped_by_subject(self):
        is_other, reason, detail = vig.passage_is_other_venue(CATH, RIJKS)
        self.assertTrue(is_other)
        self.assertEqual(reason, "subject")
        self.assertTrue(detail)

    def test_catharijneconvent_dropped_by_domain(self):
        # Even a thinner passage that does not spell out the museum is dropped when
        # it comes from the other venue's official domain while naming it.
        is_other, reason, _ = vig.passage_is_other_venue(
            CATH, RIJKS, url="https://www.catharijneconvent.nl/collectie")
        self.assertTrue(is_other)
        # subject fires first here; domain is the backstop.
        self.assertIn(reason, ("subject", "domain"))

    def test_rijksmuseum_own_passage_kept(self):
        is_other, _, _ = vig.passage_is_other_venue(RIJKS_OWN, RIJKS)
        self.assertFalse(is_other)

    def test_rijksmuseum_own_domain_kept(self):
        is_other, _, _ = vig.passage_is_other_venue(
            RIJKS_OWN, RIJKS, url="https://www.rijksmuseum.nl/en/rijksstudio")
        self.assertFalse(is_other)

    def test_filter_keeps_own_drops_other(self):
        passages = [
            {"text": RIJKS_OWN, "url": "https://www.rijksmuseum.nl/en"},
            {"text": CATH, "url": "https://www.catharijneconvent.nl/"},
        ]
        kept, dropped = vig.filter_research_passages(passages, RIJKS)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["text"], RIJKS_OWN)
        self.assertEqual(len(dropped), 1)

    def test_mandated_log_line(self):
        line = vig.other_venue_drop_log_line(
            "Museum Catharijneconvent", "https://www.catharijneconvent.nl/")
        self.assertTrue(line.startswith("[LOCAL-828] other-venue passage dropped "))
        self.assertIn("Museum Catharijneconvent", line)
        self.assertIn("catharijneconvent.nl", line)


# ─── 2. Louvre vs Louvre Abu Dhabi / Louvre-Lens ──────────────────────────────

class LouvreSharedName(unittest.TestCase):
    def test_louvre_abu_dhabi_dropped(self):
        txt = ("The Louvre Abu Dhabi opened in 2017 on Saadiyat Island, designed "
               "by Jean Nouvel.")
        is_other, reason, detail = vig.passage_is_other_venue(txt, LOUVRE)
        self.assertTrue(is_other)
        self.assertEqual(reason, "subject")
        self.assertIn("abu dhabi", detail)

    def test_louvre_lens_dropped(self):
        txt = ("The Louvre-Lens is a satellite museum in Lens, in the Pas-de-Calais "
               "region of northern France.")
        is_other, reason, _ = vig.passage_is_other_venue(txt, LOUVRE)
        self.assertTrue(is_other)
        self.assertEqual(reason, "subject")

    def test_louvre_itself_kept(self):
        txt = ("The Louvre in Paris is the world's largest art museum and houses "
               "the Mona Lisa.")
        is_other, _, _ = vig.passage_is_other_venue(txt, LOUVRE)
        self.assertFalse(is_other)


# ─── 3. the Met vs The Met Cloisters ──────────────────────────────────────────

class MetCloisters(unittest.TestCase):
    def test_met_cloisters_dropped_for_met(self):
        txt = ("The Met Cloisters, in Fort Tryon Park, is the branch of the "
               "museum devoted to the art and architecture of medieval Europe.")
        is_other, reason, _ = vig.passage_is_other_venue(txt, MET)
        self.assertTrue(is_other)
        self.assertEqual(reason, "subject")

    def test_met_cloisters_dropped_for_met_fifth_avenue(self):
        # The live-tour request form "The Met Fifth Avenue" must also distinguish it.
        txt = ("The Met Cloisters focuses on medieval European art and "
               "architecture in upper Manhattan.")
        is_other, reason, _ = vig.passage_is_other_venue(txt, MET_FIFTH)
        self.assertTrue(is_other)
        self.assertEqual(reason, "subject")

    def test_met_own_passage_kept(self):
        txt = ("The Metropolitan Museum of Art on Fifth Avenue in New York is the "
               "largest art museum in the United States.")
        is_other, _, _ = vig.passage_is_other_venue(txt, MET)
        self.assertFalse(is_other)
        is_other2, _, _ = vig.passage_is_other_venue(txt, MET_FIFTH)
        self.assertFalse(is_other2)

    def test_met_own_work_named_under_full_name_kept(self):
        # A "The Met Fifth Avenue" tour must KEEP a passage that places the Met's
        # own work at "the Metropolitan Museum of Art" — the full name is an alias,
        # not a foreign museum. (Over-drop precision guard.)
        txt = ("Washington Crossing the Delaware is an 1851 oil painting now held "
               "at the Metropolitan Museum of Art in New York.")
        is_other, reason, _ = vig.passage_is_other_venue(txt, MET_FIFTH)
        self.assertFalse(is_other, f"must keep the Met's own work, got {reason}")

    def test_met_work_at_another_museum_dropped(self):
        # American Gothic is at the Art Institute of Chicago, not the Met.
        txt = ("American Gothic is a 1930 painting by Grant Wood in the collection "
               "of the Art Institute of Chicago.")
        is_other, reason, _ = vig.passage_is_other_venue(txt, MET_FIFTH)
        self.assertTrue(is_other)
        self.assertEqual(reason, "subject")


# ─── 4. Belvedere vs Lower Belvedere (SAME institution — allowed) ─────────────

class BelvedereSameInstitution(unittest.TestCase):
    def test_lower_belvedere_kept(self):
        txt = ("The Lower Belvedere hosts the temporary exhibitions of the "
               "Belvedere, in the former palace of Prince Eugene.")
        is_other, reason, _ = vig.passage_is_other_venue(txt, BELVEDERE)
        self.assertFalse(is_other, f"Lower Belvedere must be kept, got {reason}")

    def test_upper_belvedere_kept(self):
        txt = "The Upper Belvedere holds Gustav Klimt's The Kiss."
        is_other, _, _ = vig.passage_is_other_venue(txt, BELVEDERE)
        self.assertFalse(is_other)

    def test_belvedere_itself_kept(self):
        txt = ("The Belvedere in Vienna is a historic palace complex and one of "
               "Austria's most important art museums.")
        is_other, _, _ = vig.passage_is_other_venue(txt, BELVEDERE)
        self.assertFalse(is_other)

    def test_a_genuinely_other_vienna_museum_dropped(self):
        # A different Vienna museum, named with its institution head word, is still
        # OTHER even though it is in the same city as the Belvedere.
        txt = ("The Albertina Museum in Vienna holds one of the world's largest "
               "print rooms, including works by Dürer.")
        is_other, reason, _ = vig.passage_is_other_venue(txt, BELVEDERE)
        self.assertTrue(is_other)
        self.assertEqual(reason, "subject")


# ─── 5. city is NOT a standalone drop reason (828B precision) ─────────────────
#
# LOCAL-828B BOUNCE: the 828(A) standalone city rule dropped any passage with an
# "in <City>" phrase whose city was not the venue's — gutting the art history on
# every museum tour (a Van Gogh painted in Arles, a Rembrandt from Leiden,
# Washington crossing at Trenton). There is NO standalone city reason now. A city
# is only ever a property of an OTHER venue already named as the subject.

class CityIsNotAStandaloneDrop(unittest.TestCase):
    def test_work_made_in_another_city_kept(self):
        # A work made in another city is KEPT — the subject is the work, not a venue.
        txt = ("Starry Night Over the Rhone was painted by Van Gogh in Arles in "
               "1888.")
        is_other, reason, _ = vig.passage_is_other_venue(txt, RIJKS)
        self.assertFalse(is_other, f"work-history must be kept, got {reason}")

    def test_rembrandt_from_leiden_kept(self):
        txt = "Rembrandt was born in Leiden in 1606 and later worked in Amsterdam."
        is_other, reason, _ = vig.passage_is_other_venue(txt, RIJKS)
        self.assertFalse(is_other, f"artist-history must be kept, got {reason}")

    def test_bare_other_city_phrase_kept(self):
        # A bare "in <City>" with no named other venue is KEPT (no subject venue).
        txt = ("The collection was assembled in Utrecht over several centuries by "
               "local benefactors.")
        is_other, reason, _ = vig.passage_is_other_venue(txt, RIJKS)
        self.assertFalse(is_other, f"bare city must be kept, got {reason}")

    def test_other_venue_with_its_city_dropped(self):
        # A city attached to a NAMED other venue IS dropped — via subject.
        txt = ("Museum Catharijneconvent in Utrecht is the national museum of "
               "Christian art and heritage in the Netherlands.")
        is_other, reason, _ = vig.passage_is_other_venue(txt, RIJKS)
        self.assertTrue(is_other)
        self.assertEqual(reason, "subject")

    def test_city_contradicts_helper_removed(self):
        # The standalone city rule is gone — the helper no longer exists.
        self.assertFalse(hasattr(vig, "passage_city_contradicts"))


# ─── 6. research-result (supports) scrub shape ────────────────────────────────

class ScrubResearchResult(unittest.TestCase):
    def _result(self):
        return {
            "text": CATH + " " + RIJKS_OWN,
            "sources": [
                {"domain": "catharijneconvent.nl", "url": "https://www.catharijneconvent.nl/"},
                {"domain": "rijksmuseum.nl", "url": "https://www.rijksmuseum.nl/en"},
            ],
            "supports": [
                {"text": CATH, "sources": [
                    {"domain": "catharijneconvent.nl", "url": "https://www.catharijneconvent.nl/"}]},
                {"text": RIJKS_OWN, "sources": [
                    {"domain": "rijksmuseum.nl", "url": "https://www.rijksmuseum.nl/en"}]},
            ],
            "queries": ["rijksmuseum history"],
            "error": "",
        }

    def test_drops_other_support_and_prunes_source(self):
        out = vig.scrub_research_result(self._result(), identity=RIJKS)
        texts = [s["text"] for s in out["supports"]]
        self.assertIn(RIJKS_OWN, texts)
        self.assertNotIn(CATH, texts)
        self.assertNotIn(CATH, out["text"])
        urls = [s["url"] for s in out["sources"]]
        self.assertIn("https://www.rijksmuseum.nl/en", urls)
        self.assertNotIn("https://www.catharijneconvent.nl/", urls)

    def test_no_identity_is_noop(self):
        r = self._result()
        out = vig.scrub_research_result(r, identity=None)
        self.assertEqual(len(out["supports"]), 2)

    def test_flat_text_scrub_without_supports(self):
        r = {"text": CATH + " " + RIJKS_OWN, "sources": [], "supports": [],
             "queries": [], "error": ""}
        out = vig.scrub_research_result(r, identity=RIJKS)
        self.assertNotIn("Catharijneconvent", out["text"])
        self.assertIn("Rijksmuseum", out["text"])


# ─── 7. gate activation is museum-only and identity-gated ─────────────────────

class GateActivation(unittest.TestCase):
    def setUp(self):
        import cheap_arm
        self._cheap_arm = cheap_arm
        self._cat_token = None
        self._id_token = None

    def tearDown(self):
        if self._cat_token is not None:
            self._cheap_arm.reset_tour_category(self._cat_token)
        if self._id_token is not None:
            vig.reset_tour_venue_identity(self._id_token)

    def test_inactive_without_identity(self):
        self._cat_token = self._cheap_arm.set_tour_category("museum")
        self._id_token = vig.set_tour_venue_identity(None)
        self.assertFalse(vig.gate_active_for_museum())

    def test_inactive_for_non_museum_category(self):
        self._cat_token = self._cheap_arm.set_tour_category("walking")
        self._id_token = vig.set_tour_venue_identity(RIJKS)
        self.assertFalse(vig.gate_active_for_museum())

    def test_active_for_museum_with_identity(self):
        self._cat_token = self._cheap_arm.set_tour_category("museum")
        self._id_token = vig.set_tour_venue_identity(RIJKS)
        self.assertTrue(vig.gate_active_for_museum())


# ─── 8. empty / degenerate inputs never crash ─────────────────────────────────

class Degenerate(unittest.TestCase):
    def test_empty_passages(self):
        kept, dropped = vig.filter_research_passages([], RIJKS)
        self.assertEqual(kept, [])
        self.assertEqual(dropped, [])

    def test_empty_identity_keeps_everything(self):
        empty = vig.build_identity()
        is_other, _, _ = vig.passage_is_other_venue(CATH, empty)
        self.assertFalse(is_other)

    def test_filter_text_never_empties(self):
        # If every sentence is other-venue, the original text is returned unchanged.
        text = CATH
        scrubbed, dropped = vig.filter_text_sentences(text, RIJKS)
        self.assertEqual(scrubbed, text)
        self.assertTrue(dropped)


if __name__ == "__main__":
    unittest.main(verbosity=2)


# ─── 9. PRECISION on REAL research fixtures (LOCAL-828B) ──────────────────────
#
# The 828B bounce requires a precision test on REAL research. During the two live
# tours (./run_local828_live.sh, cheap museum arm, LOCAL828_CAPTURE on) the gate
# appended every passage it evaluated — text + source URL + its decision — to
# fixtures/local828b_research_fixtures.jsonl. Here we REPLAY those real passages
# through the gate and assert the precision properties the LEAD demanded:
#
#   * ZERO own-venue passages dropped,
#   * ZERO work-history passages dropped for a city mention (a work made in /
#     depicting / now hung in another place),
#   * the Catharijneconvent paragraph (and the other real other-venue passages in
#     fixtures/local828b_other_venue_fixtures.jsonl) ARE dropped,
#   * and we report the drop count per tour, before and after.
#
# Offline: the fixtures are static JSONL; no network/LLM/DB.

import json
import os

_FIX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
_REAL_FIX = os.path.join(_FIX_DIR, "local828b_research_fixtures.jsonl")
_OTHER_FIX = os.path.join(_FIX_DIR, "local828b_other_venue_fixtures.jsonl")

# Identities as the LIVE run bound them — deliberately THIN (the live resolver gave
# the Met a bare request name, no aliases, domain '-'): the gate must self-enrich.
_FIX_IDENTITIES = {
    "Rijksmuseum": vig.build_identity(
        venue_name="Rijksmuseum", official_url="https://www.rijksmuseum.nl",
        city="Amsterdam"),
    "The Met Fifth Avenue": vig.build_identity(
        venue_name="The Met Fifth Avenue", city="New York"),
    "Louvre": vig.build_identity(venue_name="Louvre", city="Paris"),
    "Belvedere": vig.build_identity(venue_name="Belvedere", city="Vienna"),
}

# A city cue ("in <City>", "completed in Germany") — the signal 828(A) wrongly
# dropped on. Used to label the work-history subset.
_CITY_CUE_RE = re.compile(r"\bin\s+[A-Z][A-Za-z\u00c0-\u00ff]+")


def _load_jsonl(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


class RealResearchPrecision(unittest.TestCase):
    def setUp(self):
        self.real = _load_jsonl(_REAL_FIX)
        self.other = _load_jsonl(_OTHER_FIX)

    def test_fixtures_present_and_cover_both_tours(self):
        self.assertTrue(self.real, "real research fixtures missing — run "
                        "./run_local828_live.sh with LOCAL828_CAPTURE set")
        venues = {r["venue"] for r in self.real}
        self.assertIn("Rijksmuseum", venues)
        self.assertIn("The Met Fifth Avenue", venues)

    def test_zero_own_venue_or_work_history_drops(self):
        """Replaying EVERY real captured passage, the gate drops NONE of them: the
        live research for each tour was about THAT venue / its works, so a correct
        precision-first gate removes nothing. This is the direct refutation of the
        828(A) over-drops (own-domain pages, the venue's own works, and
        work-history city mentions)."""
        bad = []
        for r in self.real:
            ident = _FIX_IDENTITIES[r["venue"]]
            is_other, reason, detail = vig.passage_is_other_venue(
                r["text"], ident, url=r.get("url", ""))
            if is_other:
                bad.append((r["venue"], reason, detail, r["text"][:90]))
        self.assertEqual(bad, [], f"own-venue/work-history passages wrongly "
                         f"dropped: {bad}")

    def test_work_history_city_mentions_are_kept(self):
        """Explicitly pin the work-history-with-a-city subset (a work made in /
        hung in another place): every one is KEPT. There must be at least one such
        passage in the real capture, or the test is vacuous."""
        wh = [r for r in self.real
              if _CITY_CUE_RE.search(r["text"]) and not r["text"].lstrip().startswith("{")]
        self.assertTrue(wh, "no work-history city-cue passage captured — fixture "
                        "does not exercise the 828(A) city over-drop")
        for r in wh:
            ident = _FIX_IDENTITIES[r["venue"]]
            is_other, reason, _ = vig.passage_is_other_venue(
                r["text"], ident, url=r.get("url", ""))
            self.assertFalse(is_other, f"work-history city mention wrongly dropped "
                             f"({reason}): {r['text'][:100]}")

    def test_catharijneconvent_and_real_other_venues_dropped(self):
        """The real other-venue passages (the exact Catharijneconvent bleed +
        curated siblings) ARE dropped, each by SUBJECT (never by a bare city)."""
        self.assertTrue(self.other, "other-venue fixtures missing")
        cath_seen = False
        for r in self.other:
            ident = _FIX_IDENTITIES[r["venue"]]
            is_other, reason, detail = vig.passage_is_other_venue(
                r["text"], ident, url=r.get("url", ""))
            self.assertTrue(is_other, f"real other-venue passage NOT dropped: "
                            f"{r['text'][:90]}")
            self.assertIn(reason, ("subject", "domain"))
            if "catharijneconvent" in r["text"].lower():
                cath_seen = True
                self.assertEqual(reason, "subject")
        self.assertTrue(cath_seen, "the Catharijneconvent fixture must be present")

    def test_report_drop_counts_before_and_after(self):
        """Report (and sanity-check) the per-tour drop count. 'Before' = the 828(A)
        over-dropping behaviour as recorded in the submission logs; 'after' = this
        precision-first gate replayed on the same real passages = 0 own-venue drops.
        Printed for the submission; asserted only that AFTER is 0 for real research
        and that the other-venue fixtures all drop."""
        per_tour = {}
        for r in self.real:
            ident = _FIX_IDENTITIES[r["venue"]]
            is_other, _, _ = vig.passage_is_other_venue(
                r["text"], ident, url=r.get("url", ""))
            slot = per_tour.setdefault(r["venue"], {"evaluated": 0, "dropped": 0})
            slot["evaluated"] += 1
            if is_other:
                slot["dropped"] += 1
        other_drops = 0
        for r in self.other:
            ident = _FIX_IDENTITIES[r["venue"]]
            is_other, _, _ = vig.passage_is_other_venue(
                r["text"], ident, url=r.get("url", ""))
            if is_other:
                other_drops += 1
        print("\n[LOCAL-828B precision] real-research drop counts (after):")
        for v, s in sorted(per_tour.items()):
            print(f"    {v}: evaluated={s['evaluated']} dropped={s['dropped']}")
        print(f"    other-venue fixtures dropped: {other_drops}/{len(self.other)}")
        for v, s in per_tour.items():
            self.assertEqual(s["dropped"], 0,
                             f"{v} dropped {s['dropped']} own/work-history passages")
        self.assertEqual(other_drops, len(self.other))
