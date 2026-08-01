"""LOCAL-35 unit tests for visitor_facts_extractor.

Tests structured extraction against the three ground-truth venues:
- Asian Arts Museum (départemental, genuinely FREE, seasonal hours)
- Musée Matisse (municipal, €12, free for Métropole residents, seasonal hours)
- Palais Lascaris (municipal, €5, free for Métropole residents, uniform hours)

Usage:
    python3 -m pytest tests/test_local35_visitor_facts.py -v
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from visitor_facts_extractor import extract_visitor_facts_from_text, VisitorFacts


# ============================================================
# Simulated page texts (from actual official sites as of 2026-07)
# ============================================================

ASIAN_ARTS_FR_TEXT = """
Retrouvez les horaires et les tarifs du musée des arts asiatiques.
Horaires Du mercredi au lundi, de 10h à 17h du 1er septembre au 30 juin.
Du mercredi au lundi, de 10h à 18h du 1er juillet au 31 août.
Fermé le mardi, le 1er janvier, le 1er mai et le 25 décembre.
Tarifs Individuels Groupes Scolaires
Individuels Visite libre Entrée gratuite.
Visite guidée 5€ par adulte. 2,50€ jeune de 14 à 18 ans.
Ateliers 10€ par adulte.
Cérémonie du thé 10€ par adulte.
Groupes Visite libre Gratuit, mais réservation obligatoire.
Visite guidée 50€ par groupe (max. 20 personnes)
"""

MATISSE_EN_TEXT = """
Practical information Getting here Musée Matisse 164, avenue des Arènes de Cimiez 06000 Nice
Opening times Museum open daily except Tuesdays
From November 1st to March 31th: open from 10 am to 5 pm
From April 1st to October 31st: open from 10 am to 6 pm
Ticket office closes 30 minutes before closing time.
Closed on January 1st, Easter Sunday, May 1st and December 25th.
Museum Tickets Musée Matisse – 12€
Musée Matisse (group rate) – 9€ Per person, for groups of minimum 10 people
Nice Museums Pass The pass is free for residents of Nice and the towns located
within the Métropole Nice Côte d'Azur. It provides free entry to all the city's
museums and galleries.
4-day Nice Museums Pass – 15€ Access to all municipal museums for 4 days.
Free admission valid proof required Children under 18 Students Job-seekers
"""

PALAIS_FR_TEXT = """
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
Tarifs musées de la Photographie Palais Lascaris Archéologie Préhistoire Art Naïf
Tarif normal Tarif réduit groupe plus 10 personnes
Entrée unique 5 € 4 €
Pass 10 Musées de 4 jours 15 € 10 €
Pass Musées de Nice moins de 18 ans étudiants demandeurs emploi Gratuit
Le saviez-vous ? Pass Musées de Nice : un accès gratuit pour les habitants de la Métropole !
Il permet à tous les habitants de la Métropole Nice Côte d'Azur âgés de plus de 18 ans
de visiter gratuitement les musées et galeries municipaux.
"""


class TestAsianArtsMuseum:
    """Ground truth: départemental, Tuesday closed, seasonal hours, FREE."""

    def test_closed_day(self):
        facts = extract_visitor_facts_from_text(ASIAN_ARTS_FR_TEXT, 'fr')
        assert 'Tuesday' in facts.closed_days

    def test_has_seasonal_hours(self):
        facts = extract_visitor_facts_from_text(ASIAN_ARTS_FR_TEXT, 'fr')
        assert len(facts.hours) >= 2, f"Expected >=2 seasonal ranges, got {facts.hours}"

    def test_hours_include_winter(self):
        facts = extract_visitor_facts_from_text(ASIAN_ARTS_FR_TEXT, 'fr')
        # Must have 10:00–17:00 for Sep–Jun
        winter = [h for h in facts.hours if '17:00' in h['time']]
        assert winter, f"No winter hours found in {facts.hours}"
        assert 'Sep' in winter[0].get('period', ''), f"Winter period wrong: {winter[0]}"

    def test_hours_include_summer(self):
        facts = extract_visitor_facts_from_text(ASIAN_ARTS_FR_TEXT, 'fr')
        # Must have 10:00–18:00 for Jul–Aug
        summer = [h for h in facts.hours if '18:00' in h['time']]
        assert summer, f"No summer hours found in {facts.hours}"
        assert 'Jul' in summer[0].get('period', ''), f"Summer period wrong: {summer[0]}"

    def test_admission_is_free(self):
        facts = extract_visitor_facts_from_text(ASIAN_ARTS_FR_TEXT, 'fr')
        assert facts.admission == "FREE", f"Expected FREE, got '{facts.admission}'"

    def test_admission_not_five_euros(self):
        """Must NOT pick up guided tour price as general admission."""
        facts = extract_visitor_facts_from_text(ASIAN_ARTS_FR_TEXT, 'fr')
        assert '€5' not in facts.admission, f"Picked up guided tour price: {facts.admission}"
        assert '€10' not in facts.admission, f"Picked up workshop price: {facts.admission}"

    def test_formatted_output_has_hours(self):
        facts = extract_visitor_facts_from_text(ASIAN_ARTS_FR_TEXT, 'fr')
        formatted = facts.format_en()
        assert '10:00' in formatted, f"No hours in formatted: {formatted}"
        assert '17:00' in formatted, f"No winter closing time in formatted: {formatted}"
        assert '18:00' in formatted, f"No summer closing time in formatted: {formatted}"


class TestMuseeMatisse:
    """Ground truth: municipal, Tuesday closed, seasonal hours, €12, free for Métropole."""

    def test_closed_day(self):
        facts = extract_visitor_facts_from_text(MATISSE_EN_TEXT, 'en')
        assert 'Tuesday' in facts.closed_days

    def test_has_seasonal_hours(self):
        facts = extract_visitor_facts_from_text(MATISSE_EN_TEXT, 'en')
        assert len(facts.hours) >= 2, f"Expected >=2 seasonal ranges, got {facts.hours}"

    def test_admission_not_free_unconditional(self):
        """CRITICAL: Must NOT say 'Free' unconditionally."""
        facts = extract_visitor_facts_from_text(MATISSE_EN_TEXT, 'en')
        # Must not be just "FREE"
        assert facts.admission != "FREE", f"Admission is incorrectly 'FREE': {facts.admission}"
        assert facts.admission != "Free", f"Admission is incorrectly 'Free': {facts.admission}"

    def test_admission_has_price(self):
        facts = extract_visitor_facts_from_text(MATISSE_EN_TEXT, 'en')
        assert '€12' in facts.admission, f"Missing price in admission: {facts.admission}"

    def test_admission_has_condition(self):
        facts = extract_visitor_facts_from_text(MATISSE_EN_TEXT, 'en')
        assert 'Métropole' in facts.admission or 'resident' in facts.admission.lower(), \
            f"Missing Métropole condition: {facts.admission}"

    def test_formatted_mentions_price_and_condition(self):
        facts = extract_visitor_facts_from_text(MATISSE_EN_TEXT, 'en')
        formatted = facts.format_en()
        assert '€12' in formatted
        assert 'free for' in formatted.lower()


class TestPalaisLascaris:
    """Ground truth: municipal, Tuesday closed, 10:00-18:00, €5, free for Métropole."""

    def test_closed_day(self):
        facts = extract_visitor_facts_from_text(PALAIS_FR_TEXT, 'fr')
        assert 'Tuesday' in facts.closed_days

    def test_has_hours(self):
        facts = extract_visitor_facts_from_text(PALAIS_FR_TEXT, 'fr')
        assert len(facts.hours) >= 1, f"No hours found: {facts.hours}"
        assert '18:00' in facts.hours[0]['time'], f"Wrong time: {facts.hours[0]}"

    def test_admission_not_free_unconditional(self):
        """CRITICAL: Must NOT say 'Free' unconditionally."""
        facts = extract_visitor_facts_from_text(PALAIS_FR_TEXT, 'fr')
        assert facts.admission != "FREE"
        assert facts.admission != "Free"

    def test_admission_has_price(self):
        facts = extract_visitor_facts_from_text(PALAIS_FR_TEXT, 'fr')
        assert '€5' in facts.admission, f"Missing price: {facts.admission}"

    def test_admission_has_condition(self):
        facts = extract_visitor_facts_from_text(PALAIS_FR_TEXT, 'fr')
        assert 'Métropole' in facts.admission or 'resident' in facts.admission.lower(), \
            f"Missing condition: {facts.admission}"

    def test_formatted_has_all_fields(self):
        facts = extract_visitor_facts_from_text(PALAIS_FR_TEXT, 'fr')
        formatted = facts.format_en()
        assert 'Tuesday' in formatted
        assert '18:00' in formatted
        assert '€5' in formatted
        assert 'free for' in formatted.lower()


class TestEdgeCases:
    """Ensure the extractor doesn't break on edge cases."""

    def test_empty_text(self):
        facts = extract_visitor_facts_from_text("", "fr")
        assert facts.is_empty()

    def test_short_text(self):
        facts = extract_visitor_facts_from_text("hello", "fr")
        assert facts.is_empty()

    def test_nav_junk_no_crash(self):
        facts = extract_visitor_facts_from_text(
            "Télécharger le recueil 2026 Cliquez ici pour en savoir plus", "fr")
        assert facts.is_empty()

    def test_free_does_not_override_paid_when_condition_present(self):
        """If 'gratuit' appears in a residents-only context, the general price wins."""
        text = """
        Tarif normal Entrée unique 10 € Tarif réduit 8 €
        Pass Musées gratuit pour les habitants de la Métropole Nice Côte d'Azur.
        """
        facts = extract_visitor_facts_from_text(text, 'fr')
        assert '€10' in facts.admission
        assert 'Métropole' in facts.admission


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
