"""test_local826_canon_and_shortfall.py — LOCAL-826.

Three defects, all from the exact field strings:

  Bug 1 — the museum canonical-title verification DROPS famous works that ARE in
          the venue's SPARQL set, because cross-language dedup folds one label out
          of the matchable set and the alias target points at the folded-out label.
          Evidence (1): Orsay, "[D1v2] DROPPED 'L'Origine du monde' — no canonical
          title match" (same for Olympia / La Nuit étoilée / La Naissance de Vénus).

  Bug 2 — the fuzzy match ACCEPTS a wrong work on a shared place name.
          Evidence (2): Orsay, "[D1v2] VERIFIED 'L'Église d'Auvers-sur-Oise' →
          canonical: 'Chaumes de Cordeville à Auvers-sur-Oise'" — a DIFFERENT
          Van Gogh painting, accepted on the toponym "Auvers-sur-Oise" alone.

  Bug 3 — the D616 shortfall line says "N exhibitions on view" even when the
          shortfall was OUR OWN dedupe/filters, not the venue's on-view list.
          Evidence (3): GCloud 494/495/496, "<Museum> currently has 1 exhibition
          on view, so this tour has 1 stop rather than the 5 you asked for."

The matcher tests build a canonical set and alias/bilingual maps exactly as the
generator does (venue_resolver.build_dynamic_aliases +
story_miner.build_bilingual_map_from_sparql), so they exercise the real code path
without any network.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import story_miner as sm
from story_miner import match_candidate_to_canonical
from venue_resolver import build_dynamic_aliases, build_canonical_titles_from_works
from about_museum_stop import build_shortfall_sentence


def _install(works):
    """Install CANONICAL_ALIASES + bilingual map from works, as the generator does,
    and return the cross-language-folded canonical set (local label preferred)."""
    sm.CANONICAL_ALIASES = build_dynamic_aliases(works)
    sm.build_bilingual_map_from_sparql(works)
    # Simulate filter_corpus_titles' cross-language dedup: keep the LOCAL label
    # only (the famous-work failure mode), so the EN alias target is folded out.
    titles = set()
    for w in works:
        titles.add(w.get("label_local") or w.get("label_en"))
    return titles


# Minimal SPARQL-shaped works for the Orsay famous four. EN and local labels, as
# fetch_venue_works returns them (verified live against Q23402).
ORSAY_WORKS = [
    {"qid": "Q1", "label_en": "The Origin of the World", "label_local": "L'Origine du monde", "aliases": []},
    {"qid": "Q2", "label_en": "Olympia", "label_local": "Olympia", "aliases": []},
    {"qid": "Q3", "label_en": "Starry Night Over the Rhône", "label_local": "La Nuit étoilée", "aliases": []},
    {"qid": "Q4", "label_en": "The Birth of Venus", "label_local": "La Naissance de Vénus", "aliases": []},
    {"qid": "Q5", "label_en": "A Modern Olympia", "label_local": "Une moderne Olympia", "aliases": []},
    {"qid": "Q6", "label_en": "The Church at Auvers", "label_local": "L'église d'Auvers-sur-Oise", "aliases": []},
    {"qid": "Q7", "label_en": "Thatched Cottages at Cordeville", "label_local": "Chaumes de Cordeville à Auvers-sur-Oise", "aliases": []},
    {"qid": "Q8", "label_en": "Doctor Gachet's Garden at Auvers", "label_local": "Le Jardin du docteur Gachet à Auvers", "aliases": []},
    {"qid": "Q9", "label_en": "Mademoiselle Gachet in her garden", "label_local": "Mademoiselle Gachet dans son jardin à Auvers-sur-Oise", "aliases": []},
]

# Filler works so the document-frequency gate behaves as on a real venue set
# (hundreds of titles): a word that appears in only two titles must read as
# DISTINCTIVE, as it does live. Each filler contributes unique content words.
ORSAY_WORKS += [
    {"qid": f"F{i}", "label_en": f"Filler Painting Number {i}",
     "label_local": f"Tableau de remplissage numéro {i}", "aliases": []}
    for i in range(1, 60)
]


class TestBug1CrossLanguage(unittest.TestCase):
    """A famous work present in SPARQL under EITHER label must verify from a
    candidate in EITHER language — never DROPPED 'no canonical title match'."""

    def setUp(self):
        self.titles = _install(ORSAY_WORKS)

    def test_french_candidates_verify(self):
        # These are the exact strings the field run DROPPED.
        for c in ["L'Origine du monde", "Olympia", "La Nuit étoilée", "La Naissance de Vénus"]:
            m = match_candidate_to_canonical(c, self.titles, "")
            self.assertIsNotNone(m, f"{c!r} must verify, not be DROPPED")

    def test_english_candidate_follows_alias_to_surviving_local_label(self):
        # The EN label was folded out of the set; the alias target is absent, so
        # the matcher must FOLLOW it to the surviving French label of the same work.
        m = match_candidate_to_canonical("Starry Night Over the Rhône", self.titles, "")
        self.assertIsNotNone(m)
        self.assertEqual(m[0], "La Nuit étoilée")
        m2 = match_candidate_to_canonical("The Birth of Venus", self.titles, "")
        self.assertIsNotNone(m2)
        self.assertEqual(m2[0], "La Naissance de Vénus")

    def test_alias_target_present_prefers_itself(self):
        # When BOTH labels survive, the exact normalized candidate still wins.
        titles = set(self.titles) | {"Starry Night Over the Rhône"}
        m = match_candidate_to_canonical("Starry Night Over the Rhône", titles, "")
        self.assertIsNotNone(m)
        self.assertEqual(m[0], "Starry Night Over the Rhône")


class TestBug2DistinctiveSubject(unittest.TestCase):
    """A shared PLACE name must never be enough. The distinctive subject words
    must match, or a QID/exact alias."""

    def setUp(self):
        self.titles = _install(ORSAY_WORKS)

    def test_eglise_does_not_match_chaumes_on_toponym(self):
        # With BOTH the real Église title and the Chaumes title present, the exact
        # title wins and the wrong Chaumes accept never happens.
        m = match_candidate_to_canonical("L'Église d'Auvers-sur-Oise", self.titles, "")
        self.assertIsNotNone(m)
        self.assertEqual(m[0], "L'église d'Auvers-sur-Oise")

    def test_eglise_dropped_when_only_wrong_work_present(self):
        # The field failure: the right title is absent; only works sharing the
        # toponym remain. A toponym-only overlap must DROP, not falsely VERIFY.
        titles = {
            "Chaumes de Cordeville à Auvers-sur-Oise",
            "Le Jardin du docteur Gachet à Auvers",
            "Auvers-sur-Oise",
            "Mademoiselle Gachet dans son jardin à Auvers-sur-Oise",
        }
        m = match_candidate_to_canonical("L'Église d'Auvers-sur-Oise", titles, "")
        self.assertIsNone(m, f"toponym-only overlap must DROP, got {m!r}")

    def test_olympia_not_modern_olympia(self):
        # Olympia (Manet) ≠ Une moderne Olympia (Cézanne): the longer title adds a
        # distinctive word ("moderne"), so the bare candidate is a different work.
        m = match_candidate_to_canonical("Olympia", {"Une moderne Olympia"}, "")
        self.assertIsNone(m, f"'Olympia' must not match 'Une moderne Olympia', got {m!r}")

    def test_olympia_matches_olympia_when_present(self):
        m = match_candidate_to_canonical("Olympia", {"Olympia", "Une moderne Olympia"}, "")
        self.assertIsNotNone(m)
        self.assertEqual(m[0], "Olympia")

    def test_olympia_matches_its_own_material_enriched_form(self):
        # LOCAL-34 appends a medium/material qualifier to a bare SPARQL title
        # ("Olympia" → "Olympia (toile)"). A material word is a DESCRIPTOR, not a
        # distinguishing subject: the bare famous title must still match its own
        # enriched form, even while "Une moderne Olympia" (distinct subject) does
        # not. df is realistic here (the full ORSAY_WORKS set), so "olympia" reads
        # as distinctive exactly as in a live venue set.
        titles = set(self.titles)
        titles.discard("Olympia")
        titles.add("Olympia (toile)")
        m = match_candidate_to_canonical("Olympia", titles, "")
        self.assertIsNotNone(m, "bare 'Olympia' must match its enriched 'Olympia (toile)'")
        self.assertEqual(m[0], "Olympia (toile)")
        # And the specificity gate still keeps the two Olympias apart.
        m2 = match_candidate_to_canonical("Olympia", {"Une moderne Olympia"}, "")
        self.assertIsNone(m2)

    def test_the_railway_maps_to_le_chemin_de_fer_not_le_pont(self):
        # The Railway (Manet, NGA) → Le Chemin de fer, NOT Le pont d'Argenteuil.
        # Genuine cross-language resolution goes through the ALIAS path (the EN
        # label folded out of the set, followed to the surviving local label) —
        # exactly as the generator installs it from SPARQL works.
        works = [
            {"qid": "R1", "label_en": "The Railway", "label_local": "Le Chemin de fer", "aliases": []},
            {"qid": "R2", "label_en": "The Argenteuil Bridge", "label_local": "Le pont d'Argenteuil", "aliases": []},
        ]
        titles = _install(works)   # local labels only; EN folded out
        m = match_candidate_to_canonical("The Railway", titles, "")
        self.assertIsNotNone(m)
        self.assertEqual(m[0], "Le Chemin de fer")


class TestBug3ShortfallAttribution(unittest.TestCase):
    """'N exhibitions on view' only when the count is the venue's own on-view list;
    otherwise the neutral honest line."""

    def test_sourced_count_keeps_exhibition_phrasing(self):
        # Byte-identical to the LOCAL-600/612 contract (default count_is_sourced=True).
        s = build_shortfall_sentence("MassArt Art Museum, Boston, MA", 3, 5, 7)
        self.assertEqual(
            s,
            "MassArt Art Museum currently has 3 exhibitions on view, so this tour "
            "has 5 stops rather than the 7 you asked for.")

    def test_unsourced_count_uses_neutral_line(self):
        # The GCloud 494/495/496 situation: the shortfall was OUR dedupe, not the
        # venue's on-view count. No false "N exhibitions on view".
        s = build_shortfall_sentence(
            "Musée d'Orsay, Paris, France", 1, 1, 5, count_is_sourced=False)
        self.assertNotIn("exhibition", s.lower())
        self.assertNotIn("on view", s.lower())
        self.assertEqual(
            s,
            "We could confirm 1 stop at Musée d'Orsay, so this tour has 1 stop "
            "rather than the 5 you asked for.")

    def test_unsourced_plural_grammar(self):
        s = build_shortfall_sentence("X Museum", 9, 3, 5, count_is_sourced=False)
        self.assertEqual(
            s,
            "We could confirm 3 stops at X Museum, so this tour has 3 stops "
            "rather than the 5 you asked for.")

    def test_unsourced_still_silent_when_ask_met(self):
        self.assertEqual(
            build_shortfall_sentence("X Museum", 1, 5, 5, count_is_sourced=False), "")
        self.assertEqual(
            build_shortfall_sentence("X Museum", 1, 5, None, count_is_sourced=False), "")

    def test_neutral_line_keeps_the_shortfall_tail(self):
        # The tail "rather than the N you asked for" must be identical on both lines.
        s = build_shortfall_sentence("Y Museum", 2, 2, 6, count_is_sourced=False)
        self.assertIn("rather than the 6 you asked for.", s)


if __name__ == "__main__":
    unittest.main(verbosity=2)
