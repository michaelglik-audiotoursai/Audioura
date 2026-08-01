#!/usr/bin/env python3
"""
LOCAL-91: Test that the corpus fallback carries provenance through
to the practical_facts_gate, and that the gate still rejects false claims.

Acceptance criteria:
1. Corpus-extracted admission ("5 €") is VERIFIED when source text matches.
2. A fabricated admission ("€99") is DROPPED — the gate fires.
3. Provenance flows: source_url and source_text are set from the corpus page.
4. Gate is NOT bypassed — no "trusted source" exemption.
"""
import sys
import os
import re
import unittest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from practical_facts_gate import (
    run_practical_facts_gate,
    gate_and_fix,
    PracticalClaim,
    extract_practical_claims,
)
from visitor_facts_extractor import extract_visitor_facts_from_text


# ─── Fixtures ────────────────────────────────────────────────────────────────

# Simulated corpus page text for Palais Lascaris (what story_miner would have fetched)
PALAIS_CORPUS_PAGE_TEXT = """
Palais Lascaris Informations pratiques Adresse 15 rue Droite 06300 Nice
Horaires de visite du 1 janvier au 31 décembre
Lundi : 10h00 - 18h00
Mardi : Fermé
Mercredi : 10h00 - 18h00
Jeudi : 10h00 - 18h00
Vendredi : 10h00 - 18h00
Samedi : 10h00 - 18h00
Dimanche : 10h00 - 18h00
Fermé le 1er janvier, dimanche de Pâques, 1er mai et 25 décembre.
Tarifs musées de la Photographie Palais Lascaris Archéologie Préhistoire Terra Amata Art Naïf
Tarif normal Tarif réduit groupe plus 10 personnes
Entrée unique 5 € 4 €
Pass 10 Musées de 4 jours 15 € 10 €
Pass Musées de Nice moins de 18 ans étudiants demandeurs emploi Gratuit
Les conditions tarifaires Ticket Gratuit sur présentation d'un justificatif
Enfant de moins de 18 ans Étudiants Demandeurs d'emplois
Le saviez-vous ? Pass Musées de Nice : un accès gratuit pour les habitants de la Métropole !
Il permet à tous les habitants de la Métropole Nice Côte d'Azur âgés de plus de 18 ans
de visiter gratuitement les musées et galeries municipaux.
"""

PALAIS_CORPUS_PAGE_URL = "https://www.nice.fr/fr/culture/musees-et-galeries/palais-lascaris-le-palais/tarifs-et-horaires"


class TestCorpusProvenance(unittest.TestCase):
    """Test that corpus fallback carries provenance for gate verification."""

    def test_extraction_from_corpus_text(self):
        """Verify extract_visitor_facts_from_text finds admission in corpus page."""
        facts = extract_visitor_facts_from_text(PALAIS_CORPUS_PAGE_TEXT, "fr")
        self.assertFalse(facts.is_empty(), "Should extract at least one fact from corpus page")
        # Should find admission with €5
        self.assertIn("€5", facts.admission or "",
                      f"Expected €5 in admission, got: '{facts.admission}'")
        # Should find Tuesday closed
        self.assertTrue(
            any("tuesday" in d.lower() or "mardi" in d.lower() for d in facts.closed_days),
            f"Expected Tuesday/Mardi in closed_days, got: {facts.closed_days}"
        )
        print(f"  [PASS] Corpus extraction: admission='{facts.admission}', "
              f"closed={facts.closed_days}, hours={len(facts.hours)}")

    def test_corpus_claim_verified_with_source_text(self):
        """Gate VERIFIES a correct corpus-extracted admission claim when source_text is provided."""
        facts = extract_visitor_facts_from_text(PALAIS_CORPUS_PAGE_TEXT, "fr")
        formatted_info = facts.format_en()
        # Build a tour text with the extracted info
        tour_text = f"Stop 1: Entrance Hall\n\nMuseum Information: {formatted_info}\n\nDescription here."

        # Run the gate with source_text from the same corpus page
        result = run_practical_facts_gate(
            tour_text,
            source_url=PALAIS_CORPUS_PAGE_URL,
            source_text=PALAIS_CORPUS_PAGE_TEXT,
        )

        # Admission claim should be VERIFIED (provenance carried)
        admission_claims = [c for c in result.claims if c.claim_type == 'admission']
        self.assertTrue(len(admission_claims) > 0, "Should have at least one admission claim")

        # At least one admission claim must be verified
        verified_admissions = [c for c in result.verified_claims if c.claim_type == 'admission']
        self.assertTrue(len(verified_admissions) > 0,
                        f"Admission should be VERIFIED with corpus source text. "
                        f"Dropped: {[c.value for c in result.dropped_claims]}")

        for c in result.audit_log:
            print(f"    AUDIT: {c}")
        print(f"  [PASS] Corpus admission VERIFIED via provenance")

    def test_corpus_claim_no_source_is_dropped(self):
        """Gate DROPS a corpus-extracted claim when source_text is NOT provided."""
        facts = extract_visitor_facts_from_text(PALAIS_CORPUS_PAGE_TEXT, "fr")
        formatted_info = facts.format_en()
        tour_text = f"Stop 1: Entrance Hall\n\nMuseum Information: {formatted_info}\n\nDescription here."

        # Run the gate WITHOUT source_text — simulates the old broken path
        result = run_practical_facts_gate(
            tour_text,
            source_url="",
            source_text="",  # No source — claim cannot be verified
        )

        # ALL claims should be DROPPED
        self.assertTrue(len(result.dropped_claims) > 0,
                        "Claims should be DROPPED when no source_text is available")
        self.assertEqual(len(result.verified_claims), 0,
                         "No claims should be verified without source_text")
        print(f"  [PASS] No source_text → all claims DROPPED (gate holds)")

    def test_false_claim_rejected_with_source(self):
        """Gate REJECTS a fabricated admission claim even when source_text IS provided."""
        # Fabricate a false claim: €99 admission for Palais Lascaris (it's €5)
        tour_text = "Stop 1: Entrance Hall\n\nMuseum Information: Closed on Tuesday. €99 admission\n\nDescription."

        # Run the gate WITH the real source text — but the claim (€99) is wrong
        result = run_practical_facts_gate(
            tour_text,
            source_url=PALAIS_CORPUS_PAGE_URL,
            source_text=PALAIS_CORPUS_PAGE_TEXT,
        )

        # The €99 claim should be DROPPED — it's not in the source
        admission_drops = [c for c in result.dropped_claims if c.claim_type == 'admission']
        self.assertTrue(len(admission_drops) > 0,
                        f"Fabricated €99 should be DROPPED. "
                        f"Verified: {[c.value for c in result.verified_claims]}")

        for c in result.audit_log:
            print(f"    AUDIT: {c}")
        print(f"  [PASS] Fabricated €99 REJECTED by gate (provenance check works)")

    def test_provenance_fields_populated(self):
        """Verify that the gate result carries source_url and source_text on claims."""
        facts = extract_visitor_facts_from_text(PALAIS_CORPUS_PAGE_TEXT, "fr")
        formatted_info = facts.format_en()
        tour_text = f"Stop 1: Entrance Hall\n\nMuseum Information: {formatted_info}\n\nDescription."

        result = run_practical_facts_gate(
            tour_text,
            source_url=PALAIS_CORPUS_PAGE_URL,
            source_text=PALAIS_CORPUS_PAGE_TEXT,
        )

        # Every claim should have source_url and source_text attached
        for claim in result.claims:
            self.assertEqual(claim.source_url, PALAIS_CORPUS_PAGE_URL,
                             f"Claim '{claim.value}' missing source_url")
            self.assertTrue(len(claim.source_text) > 100,
                            f"Claim '{claim.value}' missing source_text")
        print(f"  [PASS] All {len(result.claims)} claims carry provenance fields")

    def test_corpus_fallback_path_simulation(self):
        """Simulate the full LOCAL-91 corpus fallback path end-to-end.

        Mimics what generate_tour_text.py now does:
        1. Primary extraction fails (empty result)
        2. Corpus pages are available from story_miner
        3. Extract from corpus → get facts with provenance
        4. Gate verifies → claims pass
        """
        # Simulate _story_corpus_result from story_miner
        story_corpus_result = {
            'pages': [
                {'url': 'https://www.nice.fr/fr/culture/musees-et-galeries/palais-lascaris-le-palais',
                 'text': 'Le Palais Lascaris est un palais et musée situé dans la vieille ville de Nice.',
                 'title': 'Collection'},
                {'url': PALAIS_CORPUS_PAGE_URL,
                 'text': PALAIS_CORPUS_PAGE_TEXT,
                 'title': 'tarifs-et-horaires'},
            ],
            'source_urls': ['https://www.nice.fr/fr/culture/musees-et-galeries/palais-lascaris-le-palais'],
            'combined_text': 'Le Palais Lascaris...' + PALAIS_CORPUS_PAGE_TEXT,
        }

        # Simulate the LOCAL-91 fallback logic (same as in generate_tour_text.py)
        _sourced_visitor_info = ''  # Primary extraction "failed"
        _visitor_info_source_url = ''
        _visitor_info_source_text = ''

        # --- LOCAL-91 corpus fallback ---
        _best_corpus_facts = None
        _best_corpus_score = -1
        _best_corpus_page_url = ''
        _best_corpus_page_text = ''

        for _cp in story_corpus_result['pages']:
            _cp_text = _cp.get('text', '')
            _cp_url = _cp.get('url', '')
            if not _cp_text or len(_cp_text) < 100:
                continue
            _cp_lower = _cp_text[:2000].lower()
            _fr_sig = sum(1 for w in ['fermé', 'horaires', 'tarifs', 'ouvert', 'gratuit', 'mardi']
                          if w in _cp_lower)
            _en_sig = sum(1 for w in ['closed', 'hours', 'admission', 'open', 'free', 'tuesday']
                          if w in _cp_lower)
            _cp_lang = "en" if _en_sig > _fr_sig else "fr"
            _cp_facts = extract_visitor_facts_from_text(_cp_text, _cp_lang)
            _cp_score = 0
            _cp_score += min(len(_cp_facts.hours), 2) * 2
            if _cp_facts.admission:
                _cp_score += 3
                if re.search(r'€\d+|\d+\s*€', _cp_facts.admission):
                    _cp_score += 2
            if _cp_facts.closed_days:
                _cp_score += 1
            if _cp_score > _best_corpus_score:
                _best_corpus_score = _cp_score
                _best_corpus_facts = _cp_facts
                _best_corpus_page_url = _cp_url
                _best_corpus_page_text = _cp_text

        if _best_corpus_facts and not _best_corpus_facts.is_empty():
            _formatted = _best_corpus_facts.format_en()
            if _formatted and len(_formatted) >= 10:
                _sourced_visitor_info = _formatted
                _visitor_info_source_url = _best_corpus_page_url
                _visitor_info_source_text = _best_corpus_page_text[:10000]

        # Verify we got visitor info
        self.assertTrue(bool(_sourced_visitor_info),
                        "Corpus fallback should produce visitor info")
        self.assertTrue(bool(_visitor_info_source_url),
                        "Corpus fallback should carry source_url")
        self.assertTrue(bool(_visitor_info_source_text),
                        "Corpus fallback should carry source_text")
        self.assertIn("€5", _sourced_visitor_info,
                      f"Should include €5 admission. Got: {_sourced_visitor_info}")

        # Now run the gate — it should VERIFY the claims
        tour_text = f"Stop 1: Entrance\n\nMuseum Information: {_sourced_visitor_info}\n\nWelcome."
        result = run_practical_facts_gate(
            tour_text,
            source_url=_visitor_info_source_url,
            source_text=_visitor_info_source_text,
        )

        self.assertTrue(len(result.verified_claims) > 0,
                        f"Gate should verify corpus-fallback claims. "
                        f"Dropped: {[(c.claim_type, c.value) for c in result.dropped_claims]}")

        # Check the audit lines contain VERIFIED
        verified_audit = [l for l in result.audit_log if 'VERIFIED' in l]
        self.assertTrue(len(verified_audit) > 0,
                        "Should have at least one VERIFIED audit line")

        for line in result.audit_log:
            print(f"    AUDIT: {line}")
        print(f"\n  [PASS] Full corpus fallback path: {_sourced_visitor_info}")
        print(f"         Source: {_visitor_info_source_url}")
        print(f"         Gate: {len(result.verified_claims)} verified, "
              f"{len(result.dropped_claims)} dropped")


class TestGateStillRejectsFalse(unittest.TestCase):
    """Prove the gate was not weakened — false claims are still rejected."""

    def test_matisse_free_rejected_when_source_says_paid(self):
        """The Musée Matisse "Free" error (LOCAL-74 regression) must still be caught."""
        # Matisse source says €12 — uses "tarif normal" pattern the gate recognizes
        matisse_source = """
        Musée Matisse practical information opening hours admission
        Tarif normal : 12 €
        Tarif réduit : 8 €
        Gratuit pour les résidents de la Métropole Nice Côte d'Azur
        Free for Nice Métropole residents with proof
        Children under 18 free
        Closed on Tuesday
        """
        # A false "Free" claim (the old bug)
        tour_text = "Stop 1: Nu bleu IV\n\nMuseum Information: Free\n\nDescription."

        result = run_practical_facts_gate(
            tour_text,
            source_url="http://musee-matisse-nice.org/practical-information",
            source_text=matisse_source,
        )

        # "Free" must be DROPPED (source has €12, so unconditional free is rejected)
        self.assertTrue(len(result.dropped_claims) > 0,
                        "Unconditional 'Free' must be DROPPED when source says €12")
        admission_verified = [c for c in result.verified_claims if c.claim_type == 'admission']
        # The unconditional "Free" should NOT be verified
        for c in admission_verified:
            self.assertNotEqual(c.value.strip().lower(), "free",
                                "Unconditional 'Free' must NEVER be verified for Matisse")

        for line in result.audit_log:
            print(f"    AUDIT: {line}")
        print(f"  [PASS] Matisse 'Free' still REJECTED (LOCAL-74 regression guard holds)")

    def test_fabricated_price_rejected(self):
        """A completely fabricated price (€200) is rejected by the gate."""
        source = "Tarif normal Entrée unique 5 € 4 € Gratuit enfants"
        tour_text = "Stop 1: Hall\n\nMuseum Information: €200 admission\n\nDescription."

        result = run_practical_facts_gate(tour_text, source_url="https://example.com", source_text=source)

        admission_drops = [c for c in result.dropped_claims if c.claim_type == 'admission']
        self.assertTrue(len(admission_drops) > 0,
                        f"Fabricated €200 must be DROPPED. Verified: "
                        f"{[(c.claim_type, c.value) for c in result.verified_claims]}")
        print(f"  [PASS] Fabricated €200 REJECTED by gate")


if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("LOCAL-91: Corpus Fallback Provenance Tests")
    print("=" * 70)
    unittest.main(verbosity=2)
