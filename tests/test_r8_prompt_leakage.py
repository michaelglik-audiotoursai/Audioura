#!/usr/bin/env python3
"""Test R8 (prompt leakage) against labelled set — both directions.

LOCAL-213: Validates the rule fires on real leaked sentences and does NOT fire
on legitimate narration.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from style_validator_detector import check_r8_prompt_leakage, validate_paragraph

# ═══════════════════════════════════════════════════════════════════════════════
# MUST FIRE — real examples from stored tours
# ═══════════════════════════════════════════════════════════════════════════════
MUST_FIRE = [
    # Tour 163 — the canonical defect (Cap d'Antibes)
    "One concrete sensory detail that envelops you in the atmosphere of Cap d'Antibes is the sound of the waves crashing against the rugged rocks, echoing the timeless rhythm of the sea.",
    # Tour 50
    "One concrete sensory detail that immerses you in the experience is the rhythmic sound of fishmongers tossing fresh seafood to eager customers at the famous Pike Place Fish Market.",
    # Tour 101
    "One concrete sensory detail that immerses you in the market's atmosphere is the melodic sound of street musicians serenading shoppers as they browse the stalls.",
    # Tour 105
    "One concrete sensory detail that envelops you here is the sound of footsteps echoing through the museum's halls, a symphony of exploration and discovery.",
    # Tour 106
    "Amidst the vast array of exhibits, one concrete sensory detail transports you into the heart of history — the faint scent of aged paper and the echoes of footsteps on polished marble floors.",
    # Tour 145
    "A concrete sensory detail that envelops you in the atmosphere of the park is the sound of seagulls circling overhead, their cries mingling with the gentle lapping of the water against the shore.",
    # Tour 154
    "What makes this stop notable is its strategic role during World War II, guiding ships and transmitting covert messages.",
    # Tour 157
    "What makes this stop notable is its connection to Picasso, who found solace here, away from the bustling art scene.",
    # Tour 162
    "What makes this stop notable is that Picasso created an impressive body of work during his stay, including paintings, ceramics, and drawings, all inspired by the stunning surroundings of Antibes.",
    # Tour 170
    "One concrete sensory detail that envelops you at this stop is the salty sea breeze that carries the fragrant scents of pine trees and wildflowers, creating a sensory symphony of nature's elements.",
    # Tour 154 (second instance)
    "One concrete sensory detail that immediately envelops you is the scent of blooming flowers and herbs that waft through the air, creating a fragrant tapestry unique to this picturesque locale.",
]

# ═══════════════════════════════════════════════════════════════════════════════
# MUST NOT FIRE — legitimate narration
# ═══════════════════════════════════════════════════════════════════════════════
MUST_NOT_FIRE = [
    # Normal sensory description without prompt scaffolding
    "The sound of waves carries up the cliff face.",
    "Salt air fills the promenade in the early morning.",
    "The carving repays a closer look at one detail in particular.",
    "The market smells of lavender and rotisserie chicken.",
    # "What makes" about a non-stop entity
    "What makes the chapel unusual is its octagonal floor plan.",
    "What makes this building distinctive is the use of local sandstone.",
    # Normal use of "detail" in free prose
    "One detail stands out: the iron bolt holes where chains once ran.",
    "Every detail of the facade speaks to the architect's obsession with symmetry.",
    "A sensory world opens when you step inside — incense, cool stone, silence.",
    # Historical narrative with "notable"
    "The fortress is notable for its role in the 1707 siege.",
    "This stretch of coast is notable for the clarity of its water.",
    # Normal "atmosphere" usage
    "The atmosphere inside the nave shifts perceptibly as clouds pass.",
    "A distinctly Mediterranean atmosphere pervades the narrow streets.",
    # Navigation that mentions "stop"
    "Head south on Promenade de la Croisette towards the next stop.",
]

# ═══════════════════════════════════════════════════════════════════════════════
# R1 REGRESSION — these must still NOT fire R1 (existing word-boundary cases)
# ═══════════════════════════════════════════════════════════════════════════════
R1_MUST_NOT_FIRE = [
    "Observers considered the design scandalous in 1887.",
    "Discoveries were made beneath the chapel floor in 1932.",
    "Explorers landed here in 1388 and named the cape.",
]

# Navigation exemption (D69, D60)
NAV_MUST_NOT_FIRE = [
    "Head south on Promenade de la Croisette.",
    "Turn left at the fountain and continue past the Palais des Festivals.",
    "Cross the street and enter the museum courtyard.",
]


def run_tests():
    print("=" * 78)
    print("R8 PROMPT LEAKAGE — LABELLED SET VALIDATION")
    print("=" * 78)

    # ── MUST FIRE ──
    print("\n─── MUST FIRE (real leaked sentences) ───")
    fire_pass = 0
    fire_fail = 0
    for sent in MUST_FIRE:
        findings = check_r8_prompt_leakage(sent)
        if findings:
            fire_pass += 1
            print(f"  ✓ FIRES: \"{sent[:80]}...\"")
        else:
            fire_fail += 1
            print(f"  ✗ MISSED: \"{sent[:80]}...\"")

    # ── MUST NOT FIRE ──
    print("\n─── MUST NOT FIRE (legitimate narration) ───")
    nofire_pass = 0
    nofire_fail = 0
    for sent in MUST_NOT_FIRE:
        findings = check_r8_prompt_leakage(sent)
        if not findings:
            nofire_pass += 1
            print(f"  ✓ SILENT: \"{sent[:80]}\"")
        else:
            nofire_fail += 1
            print(f"  ✗ FALSE POSITIVE: \"{sent[:80]}\"")
            print(f"           Rule: {findings[0]['rule_id']}")

    # ── R1 REGRESSION ──
    print("\n─── R1 REGRESSION (must not fire R1) ───")
    r1_pass = 0
    r1_fail = 0
    for sent in R1_MUST_NOT_FIRE:
        result = validate_paragraph(sent)
        r1_findings = [f for f in result['findings'] if f['rule_id'] == 'R1_IMPERATIVE']
        if not r1_findings:
            r1_pass += 1
            print(f"  ✓ R1 SILENT: \"{sent[:80]}\"")
        else:
            r1_fail += 1
            print(f"  ✗ R1 FALSE POSITIVE: \"{sent[:80]}\"")

    # ── NAVIGATION EXEMPTION ──
    print("\n─── NAVIGATION EXEMPTION (must not fire any rule) ───")
    nav_pass = 0
    nav_fail = 0
    for sent in NAV_MUST_NOT_FIRE:
        result = validate_paragraph(sent)
        errors = [f for f in result['findings'] if f['severity'] == 'error']
        if not errors:
            nav_pass += 1
            print(f"  ✓ NAV EXEMPT: \"{sent[:80]}\"")
        else:
            nav_fail += 1
            print(f"  ✗ NAV FALSE POSITIVE: \"{sent[:80]}\"")
            for e in errors:
                print(f"           {e['rule_id']}: {e['sentence'][:60]}")

    # ── SUMMARY ──
    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    total_pass = fire_pass + nofire_pass + r1_pass + nav_pass
    total_fail = fire_fail + nofire_fail + r1_fail + nav_fail
    print(f"  Must fire:       {fire_pass}/{len(MUST_FIRE)} pass")
    print(f"  Must NOT fire:   {nofire_pass}/{len(MUST_NOT_FIRE)} pass")
    print(f"  R1 regression:   {r1_pass}/{len(R1_MUST_NOT_FIRE)} pass")
    print(f"  Nav exemption:   {nav_pass}/{len(NAV_MUST_NOT_FIRE)} pass")
    print(f"  TOTAL:           {total_pass}/{total_pass + total_fail} pass")
    
    if total_fail > 0:
        print(f"\n  ✗ {total_fail} FAILURES — rule needs adjustment")
        return 1
    else:
        print(f"\n  ✓ ALL PASS")
        return 0


if __name__ == '__main__':
    sys.exit(run_tests())
