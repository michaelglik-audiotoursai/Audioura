"""LOCAL-35 acceptance evidence runner.

Demonstrates that the visitor facts extraction produces correct, complete,
and unambiguous Museum Information for all three Nice museum venues.

Ground truth (LEAD-verified):
| Venue              | Closed   | Hours                                                  | Admission                                    |
|--------------------|----------|--------------------------------------------------------|----------------------------------------------|
| Asian Arts Museum  | Tuesday  | 10:00–17:00 (1 Sep–30 Jun), 10:00–18:00 (1 Jul–31 Aug)| FREE                                         |
| Musée Matisse      | Tuesday  | 10:00–18:00 (seasonal split on live site)              | €12; free for Métropole residents             |
| Palais Lascaris    | Tuesday  | 10:00–18:00                                            | €5; free for Métropole residents              |

Usage:
    python3 run_local35_acceptance.py
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from visitor_facts_extractor import extract_visitor_facts_from_text, VisitorFacts


# ============================================================
# Simulated page texts — taken verbatim from official sites 2026-07-30
# ============================================================

ASIAN_ARTS_FR_PAGE = """
Retrouvez les horaires et les tarifs du musée des arts asiatiques.
Horaires Du mercredi au lundi, de 10h à 17h du 1er septembre au 30 juin.
Du mercredi au lundi, de 10h à 18h du 1er juillet au 31 août.
Fermé le mardi, le 1er janvier, le 1er mai et le 25 décembre.
Tarifs Individuels Groupes Scolaires
Individuels Visite libre Entrée gratuite.
Visite guidée 5€ par adulte. 2,50€ jeune de 14 à 18 ans, étudiant, demandeur d'emploi.
Offre famille 5€ pour un adulte accompagné par un enfant.
Ateliers 10€ par adulte.
Cérémonie du thé 10€ par adulte.
Groupes Visite libre Gratuit, mais réservation obligatoire.
Visite guidée 50€ par groupe max. 20 personnes.
"""

MATISSE_EN_PAGE = """
Practical information Getting here Musée Matisse 164, avenue des Arènes de Cimiez 06000 Nice
Opening times Museum open daily except Tuesdays
From November 1st to March 31th: open from 10 am to 5 pm
From April 1st to October 31st: open from 10 am to 6 pm
Ticket office closes 30 minutes before closing time.
Closed on January 1st, Easter Sunday, May 1st and December 25th.
Museum Tickets Musée Matisse – 12€
Musée Matisse group rate – 9€ Per person, for groups of minimum 10 people
Nice Museums Pass The pass is free for residents of Nice and the towns located
within the Métropole Nice Côte d'Azur. It provides free entry to all the city's
museums and galleries. Children and individuals under 18 from the metropolitan
area are also admitted free.
4-day Nice Museums Pass – 15€ Access to all municipal museums and galleries for 4 days.
4-day Nice Museums Pass for groups – 10€ per person minimum 10 people
Free admission valid proof required Children under 18 Students Job-seekers
Holders of disability card
"""

PALAIS_FR_PAGE = """
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
Les moins de 18 ans peuvent également entrer gratuitement sans avoir besoin de ce pass.
"""


def check_venue(label: str, page_text: str, page_lang: str, expected: dict):
    """Extract and verify against ground truth."""
    facts = extract_visitor_facts_from_text(page_text, page_lang)
    formatted = facts.format_en()

    print(f"\n{'─' * 70}")
    print(f"  {label}")
    print(f"{'─' * 70}")
    print(f"  Museum Information: {formatted}")
    print(f"  Fields:")
    print(f"    closed_days: {facts.closed_days}")
    print(f"    hours: {facts.hours}")
    print(f"    admission: '{facts.admission}'")
    print()

    # Verify against expected
    errors = []
    if expected.get('closed_day') and expected['closed_day'] not in facts.closed_days:
        errors.append(f"FAIL: Expected closed on {expected['closed_day']}, got {facts.closed_days}")
    if expected.get('min_hour_ranges') and len(facts.hours) < expected['min_hour_ranges']:
        errors.append(f"FAIL: Expected ≥{expected['min_hour_ranges']} hour ranges, got {len(facts.hours)}")
    if expected.get('admission_contains'):
        for s in expected['admission_contains']:
            if s.lower() not in facts.admission.lower():
                errors.append(f"FAIL: Admission missing '{s}': got '{facts.admission}'")
    if expected.get('admission_must_not_be'):
        for s in expected['admission_must_not_be']:
            if facts.admission == s:
                errors.append(f"FAIL: Admission must NOT be '{s}' but it is")
    if expected.get('hours_must_contain'):
        for s in expected['hours_must_contain']:
            found = any(s in h['time'] or s in h.get('period', '') for h in facts.hours)
            if not found:
                errors.append(f"FAIL: Hours must contain '{s}' but don't: {facts.hours}")

    if errors:
        for e in errors:
            print(f"  *** {e}")
        return False
    else:
        print(f"  ✓ All checks pass")
        return True


def main():
    print("=" * 70)
    print("LOCAL-35 ACCEPTANCE EVIDENCE: Visitor Facts Extraction")
    print("=" * 70)
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Module: visitor_facts_extractor.py")

    all_pass = True

    # --- Asian Arts Museum ---
    ok = check_venue(
        "Asian Arts Museum (départemental)",
        ASIAN_ARTS_FR_PAGE, "fr",
        {
            'closed_day': 'Tuesday',
            'min_hour_ranges': 2,
            'admission_contains': ['FREE'],
            'admission_must_not_be': ['€5', '€10'],
            'hours_must_contain': ['17:00', '18:00', 'Sep', 'Jul'],
        }
    )
    all_pass = all_pass and ok

    # --- Musée Matisse ---
    ok = check_venue(
        "Musée Matisse (municipal)",
        MATISSE_EN_PAGE, "en",
        {
            'closed_day': 'Tuesday',
            'min_hour_ranges': 2,
            'admission_contains': ['€12', 'Métropole'],
            'admission_must_not_be': ['FREE', 'Free'],
            'hours_must_contain': ['17:00', '18:00'],
        }
    )
    all_pass = all_pass and ok

    # --- Palais Lascaris ---
    ok = check_venue(
        "Palais Lascaris (municipal)",
        PALAIS_FR_PAGE, "fr",
        {
            'closed_day': 'Tuesday',
            'min_hour_ranges': 1,
            'admission_contains': ['€5', 'Métropole'],
            'admission_must_not_be': ['FREE', 'Free'],
            'hours_must_contain': ['18:00'],
        }
    )
    all_pass = all_pass and ok

    # --- Summary ---
    print()
    print("=" * 70)
    print(f"  RESULT: {'ALL PASS' if all_pass else 'FAILURES DETECTED'}")
    print("=" * 70)

    # --- Comparison table ---
    print()
    print("  Ground Truth vs Extracted:")
    print()
    print(f"  {'Venue':<25} {'Expected Admission':<40} {'Extracted':<40}")
    print(f"  {'-'*25} {'-'*40} {'-'*40}")

    asian = extract_visitor_facts_from_text(ASIAN_ARTS_FR_PAGE, 'fr')
    matisse = extract_visitor_facts_from_text(MATISSE_EN_PAGE, 'en')
    palais = extract_visitor_facts_from_text(PALAIS_FR_PAGE, 'fr')

    print(f"  {'Asian Arts Museum':<25} {'FREE':<40} {asian.admission:<40}")
    print(f"  {'Musée Matisse':<25} {'€12; free for Métropole residents':<40} {matisse.admission:<40}")
    print(f"  {'Palais Lascaris':<25} {'€5; free for Métropole residents':<40} {palais.admission:<40}")

    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main())
