"""LOCAL-39 acceptance evidence runner.

Demonstrates the composed pipeline: LOCAL-35 structured extraction feeding
LOCAL-36's provenance gate. Both mechanisms work together:
- LOCAL-35 extracts closed_days, hours (seasonal), admission (conditional)
- LOCAL-36 verifies each claim against the raw source text
- Structured facts with source_url pass the gate; unsourced claims are dropped.

Expected results (LEAD-verified against musee-matisse-nice.org):
| Venue              | Closed   | Hours                                                  | Admission                                    |
|--------------------|----------|--------------------------------------------------------|----------------------------------------------|
| Asian Arts Museum  | Tuesday  | 10:00–17:00 (1 Sep–30 Jun), 10:00–18:00 (1 Jul–31 Aug)| FREE                                         |
| Musée Matisse      | Tuesday  | 10:00–17:00 (1 Nov–31 Mar), 10:00–18:00 (1 Apr–31 Oct)| €12; free for Métropole residents             |
| Palais Lascaris    | Tuesday  | 10:00–18:00                                            | €5; free for Métropole residents              |

Usage:
    python3 run_local39_acceptance.py
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from visitor_facts_extractor import (
    extract_visitor_facts_from_text,
    VisitorFacts,
    VisitorInfoWithProvenance,
)
from practical_facts_gate import gate_and_fix, run_practical_facts_gate


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


def simulate_pipeline(label: str, page_text: str, page_lang: str,
                     source_url: str, expected: dict) -> bool:
    """Simulate the full LOCAL-39 pipeline for a venue.

    1. Extract structured facts (LOCAL-35)
    2. Format into Museum Information string
    3. Create simulated tour text with that info
    4. Run practical facts gate (LOCAL-36) with the source text
    5. Verify the result passes the gate AND matches expected values
    """
    print(f"\n{'─' * 70}")
    print(f"  {label}")
    print(f"{'─' * 70}")

    # --- Step 1: Structured extraction (LOCAL-35) ---
    facts = extract_visitor_facts_from_text(page_text, page_lang)
    formatted = facts.format_en()
    print(f"  [LOCAL-35] Extracted: {formatted}")
    print(f"    closed_days: {facts.closed_days}")
    print(f"    hours: {facts.hours}")
    print(f"    admission: '{facts.admission}'")

    # --- Step 2: Simulate tour text with the extracted info ---
    simulated_tour = f"""Stop 1: {label}
Museum Information: {formatted}
Description: A beautiful museum in Nice with an extraordinary collection.
"""

    # --- Step 3: Run practical facts gate (LOCAL-36) ---
    # The gate gets the raw source text (same text the extractor parsed)
    fixed_tour, gate_result = gate_and_fix(
        simulated_tour,
        source_url=source_url,
        source_text=page_text,
        verbose=True,
    )

    # --- Step 4: Verify ---
    errors = []

    # Check extraction correctness
    if expected.get('closed_day') and expected['closed_day'] not in facts.closed_days:
        errors.append(f"EXTRACTION FAIL: Expected closed on {expected['closed_day']}, got {facts.closed_days}")
    if expected.get('min_hour_ranges') and len(facts.hours) < expected['min_hour_ranges']:
        errors.append(f"EXTRACTION FAIL: Expected ≥{expected['min_hour_ranges']} hour ranges, got {len(facts.hours)}")
    if expected.get('admission_contains'):
        for s in expected['admission_contains']:
            if s.lower() not in facts.admission.lower():
                errors.append(f"EXTRACTION FAIL: Admission missing '{s}': got '{facts.admission}'")
    if expected.get('admission_must_not_be'):
        for s in expected['admission_must_not_be']:
            if facts.admission == s:
                errors.append(f"EXTRACTION FAIL: Admission must NOT be '{s}' but it is")
    if expected.get('hours_must_contain'):
        for s in expected['hours_must_contain']:
            found = any(s in h['time'] or s in h.get('period', '') for h in facts.hours)
            if not found:
                errors.append(f"EXTRACTION FAIL: Hours must contain '{s}' but don't: {facts.hours}")

    # Check gate result — verified claims should pass, not be dropped
    if gate_result.dropped_claims:
        # Only flag if the dropped claim is one we expect to be present
        for dc in gate_result.dropped_claims:
            errors.append(f"GATE DROP: '{dc.value}' was dropped (type: {dc.claim_type})")

    # Check that the Museum Information line survived in the fixed tour
    if formatted and "Museum Information:" not in fixed_tour:
        errors.append("GATE FAIL: Museum Information line was removed from tour")

    if errors:
        for e in errors:
            print(f"  *** {e}")
        return False
    else:
        print(f"  ✓ Extraction correct + Gate PASSED")
        return True


def main():
    print("=" * 70)
    print("LOCAL-39 ACCEPTANCE: Visitor Facts (LOCAL-35) + Provenance Gate (LOCAL-36)")
    print("=" * 70)
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Pipeline: visitor_facts_extractor → practical_facts_gate")

    all_pass = True

    # --- Asian Arts Museum ---
    ok = simulate_pipeline(
        "Asian Arts Museum (départemental)",
        ASIAN_ARTS_FR_PAGE, "fr",
        "https://www.nice.fr/fr/culture/musees-et-galeries/musee-des-arts-asiatiques",
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
    ok = simulate_pipeline(
        "Musée Matisse (municipal)",
        MATISSE_EN_PAGE, "en",
        "https://www.musee-matisse-nice.org/practical-information/",
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
    ok = simulate_pipeline(
        "Palais Lascaris (municipal)",
        PALAIS_FR_PAGE, "fr",
        "https://www.nice.fr/fr/culture/musees-et-galeries/palais-lascaris-702",
        {
            'closed_day': 'Tuesday',
            'min_hour_ranges': 1,
            'admission_contains': ['€5', 'Métropole'],
            'admission_must_not_be': ['FREE', 'Free'],
            'hours_must_contain': ['18:00'],
        }
    )
    all_pass = all_pass and ok

    # --- Matisse "Free" injection test ---
    # Simulate what happens if somehow the tour text says "Free" for Matisse
    # The gate should DROP it because the source says €12.
    print(f"\n{'─' * 70}")
    print(f"  INJECTION TEST: Matisse with fabricated 'Free admission'")
    print(f"{'─' * 70}")

    injected_tour = """Stop 1: Musée Matisse
Museum Information: Closed on Tuesday. Free admission
Description: A beautiful museum dedicated to the works of Henri Matisse.
"""
    fixed_injected, inject_result = gate_and_fix(
        injected_tour,
        source_url="https://www.musee-matisse-nice.org/practical-information/",
        source_text=MATISSE_EN_PAGE,
        verbose=True,
    )
    if inject_result.dropped_claims:
        print(f"  ✓ CORRECTLY DROPPED fabricated 'Free admission' claim")
    else:
        print(f"  *** FAIL: Fabricated 'Free admission' was NOT dropped!")
        all_pass = False

    # --- Summary ---
    print()
    print("=" * 70)
    print(f"  LOCAL-39 RESULT: {'ALL PASS' if all_pass else 'FAILURES DETECTED'}")
    print("=" * 70)

    # --- Comparison table ---
    print()
    print("  Pipeline Output vs Expected:")
    print()
    print(f"  {'Venue':<25} {'Expected':<45} {'Got':<45}")
    print(f"  {'-'*25} {'-'*45} {'-'*45}")

    asian = extract_visitor_facts_from_text(ASIAN_ARTS_FR_PAGE, 'fr')
    matisse = extract_visitor_facts_from_text(MATISSE_EN_PAGE, 'en')
    palais = extract_visitor_facts_from_text(PALAIS_FR_PAGE, 'fr')

    print(f"  {'Asian Arts':<25} {'FREE':<45} {asian.admission:<45}")
    print(f"  {'Matisse':<25} {'€12; free for Métropole residents':<45} {matisse.admission:<45}")
    print(f"  {'Palais Lascaris':<25} {'€5; free for Métropole residents':<45} {palais.admission:<45}")
    print()
    print(f"  Key verification: Matisse is '€12; free for Métropole residents', NOT 'Free'")

    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main())
