#!/usr/bin/env python3
"""Test R9 (generic sentence deletion) — labelled set from Michael's evaluation.

LOCAL-216, D89: A sentence that fits any stop belongs to no stop — delete it.

Labelled set built from EVALUATION_BY_MICHAEL_RIVIERA_2STOP.txt:
- MUST FIRE: sentences Michael scored 0/5 ("should be removed")
- MUST NOT FIRE: sentences Michael scored 1-5 (rewritable or good)

The trap: R9 must NOT touch navigation (5/5), sourced generalities (5/5),
or sentences scored 1-2 (those are style failures, not generic — R1-R4 handle them).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from style_validator_detector import (
    check_r9_generic, apply_r9_deletions, apply_r9_to_description,
    validate_paragraph, check_r1_imperatives, check_r8_prompt_leakage,
    _split_sentences, _is_style_navigation_sentence,
)

# ═══════════════════════════════════════════════════════════════════════════════
# LABELLED SET — from Michael's evaluation, both directions
# ═══════════════════════════════════════════════════════════════════════════════

# ── MUST FIRE: Michael scored 0/5, said "should be removed" ──────────────────
MUST_FIRE = [
    # Paragraph 5C — 0/5
    "As you continue your journey through this charming town, consider how these hidden paths have shaped the stories of this place, leading you to uncover more of its intriguing history.",
    # Paragraph 6 — 0/5
    "From Cap d'Antibes to Villefranche-sur-Mer — a collection that spans more ground than these stops alone.",
]

# ── MUST NOT FIRE: Michael scored 1-5 ────────────────────────────────────────
# These are either GOOD (3-5) or REWRITABLE (1-2). R9 deletes; these must survive.
MUST_NOT_FIRE = [
    # ── 5/5 — Navigation (Paragraph 1A) ──
    "Start biking southeast on the main road, continue straight until you reach the roundabout near the coast.",
    "Take the second exit onto the coastal path towards Cap d'Antibes.",
    # ── 5/5 — Sourced facts with specifics (Paragraph 5A) ──
    "Villefranche-sur-Mer, known as the \"Free City on Sea,\" has ancient streets that exude a timeless charm.",
    "The town's strategic location east of Nice and southwest of Monaco has been pivotal in its history.",
    "The deep bay of Villefranche provides secure anchorage for ships, with depths reaching 320 feet, a natural wonder in the Mediterranean.",
    # ── 3/5 — Prolog with specifics (Paragraph 2) ──
    "You are about to embark on a journey through the sun-kissed allure of the French Riviera, a tapestry woven with whispers of opulence and intrigue.",
    "From the opulent Villa Eilenroc, where the elite of the 19th century once reveled in lavish soirées, to the shadowy Rue Obscure, a secret passageway that provided escape for the town's inhabitants in the 13th century, every corner holds hidden tales waiting to be unearthed.",
    # ── 3/5 — Content with dates and names (Paragraph 3A) ──
    "The Cap d'Antibes, a peninsula located south of Antibes and east of Juan-les-Pins, offers a picturesque landscape that has attracted artists and travelers for centuries.",
    "In January 1888, the renowned artist Claude Monet visited this stunning location during his journey through the south of France.",
    "Inspired by the beauty of Cap d'Antibes, Monet stayed at the Château de la Pinède on the advice of his friend Guy de Maupassant, immersing himself in the coastal scenery that captivated his artistic soul.",
    "The Tire-Poil coastal trail allows you to explore the cape's natural beauty, stretching from the Garoupe Beach parking lot to the Villa Eilenroc.",
    "Along this 2.7 km route, you'll traverse rocky cliffs, pass by ancient chapels, and witness the panoramic views of the Lérins Islands to the west and the Mercantour Mountains to the east.",
    # ── 2/5 — Style failure, not generic (Paragraph 3B) ──
    "As you stand at the highest point of Cap d'Antibes near the ancient Notre Dame de Bon Port chapel, take in the sight of the Garoupe lighthouse overlooking the Gulf of Juan and the Bay of Angels.",
    "The nearby Abri de l'Olivette, a sheltered harbor for traditional local boats, adds to the maritime charm of this coastal gem.",
    "Pedal along the coastline, envisioning the hidden coves and stories that lie just beyond the horizon, immersing yourself in the history and natural beauty of Cap d'Antibes.",
    # ── 1/5 — Style failure with specifics (Paragraph 1B) ──
    "As you arrive at Cap d'Antibes on your cycling tour of the French Riviera, listen to the gentle lapping of waves against the rocky coastline.",
    "Look out for the Villa Eilenroc, an opulent mansion surrounded by lush gardens, symbolizing the lavish parties once hosted here by the elite of the 19th century.",
    # ── 1/5 — Style failure, names Villefranche (Paragraph 4A) ──
    "As you arrive at Villefranche-sur-Mer on your French Riviera cycling tour, pause to take in the breathtaking view of the deep natural harbor, a historic port that has welcomed ships for centuries.",
    # ── 1/5 — Style failure, names Rue Obscure (Paragraph 4B) ──
    "Look for the Rue Obscure, a mysterious 13th-century passageway that once served as an escape route for the town's inhabitants.",
    # ── 1/5 — Style failure, mentions specific places (Paragraph 5B) ──
    "Walking through the narrow streets may evoke the scent of sea salt, linking you to the town's maritime legacy.",
    "The Rue Obscure, with its shadowy passageways, whispers tales of a bygone era when it provided shelter and secrecy to the town's residents.",
    "This historical gem adds depth to your understanding of Villefranche-sur-Mer's past and its resilience through the centuries.",
    # ── R8 prompt leakage (3A sentence) — already handled by R8, not R9 ──
    "One concrete sensory detail that envelops you in the atmosphere of Cap d'Antibes is the sound of the waves crashing against the rugged rocks, echoing the timeless rhythm of the sea.",
]


# ═══════════════════════════════════════════════════════════════════════════════
# DELETION INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════

# Paragraph where deletion empties it entirely
PARA_ALL_GENERIC = (
    "As you continue your journey through this charming town, consider how "
    "these hidden paths have shaped the stories of this place, leading you to "
    "uncover more of its intriguing history."
)

# Paragraph where one sentence is generic, the rest are good
PARA_MIXED = (
    "Villefranche-sur-Mer, known as the \"Free City on Sea,\" has ancient "
    "streets that exude a timeless charm. The town's strategic location east "
    "of Nice and southwest of Monaco has been pivotal in its history. The deep "
    "bay of Villefranche provides secure anchorage for ships, with depths "
    "reaching 320 feet, a natural wonder in the Mediterranean. As you continue "
    "your journey through this charming town, consider how these hidden paths "
    "have shaped the stories of this place, leading you to uncover more of its "
    "intriguing history."
)

# Paragraph 6 — single generic sentence
PARA_SINGLE_GENERIC = (
    "From Cap d'Antibes to Villefranche-sur-Mer — a collection that spans "
    "more ground than these stops alone."
)


# ═══════════════════════════════════════════════════════════════════════════════
# R1-R4, R7, R8 REGRESSION SET
# ═══════════════════════════════════════════════════════════════════════════════

R1_MUST_NOT_FIRE = [
    "Observers considered the design scandalous in 1887.",
    "Discoveries were made beneath the chapel floor in 1932.",
    "Explorers landed here in 1388 and named the cape.",
]

R8_MUST_FIRE = [
    "One concrete sensory detail that envelops you in the atmosphere of Cap d'Antibes is the sound of the waves crashing against the rugged rocks, echoing the timeless rhythm of the sea.",
    "What makes this stop notable is its strategic role during World War II, guiding ships and transmitting covert messages.",
]

R8_MUST_NOT_FIRE = [
    "The sound of waves carries up the cliff face.",
    "What makes the chapel unusual is its octagonal floor plan.",
]

NAV_MUST_NOT_FIRE = [
    "Head south on Promenade de la Croisette.",
    "Turn left at the fountain and continue past the Palais des Festivals.",
    "Start biking southeast on the main road, continue straight until you reach the roundabout near the coast.",
]


def run_tests():
    print("=" * 78)
    print("R9 GENERIC SENTENCE DELETION — LOCAL-216, D89")
    print("=" * 78)

    # ── MUST FIRE ──
    print("\n─── MUST FIRE (Michael's 0/5 sentences — 'should be removed') ───")
    fire_pass = 0
    fire_fail = 0
    for sent in MUST_FIRE:
        findings = check_r9_generic(sent)
        if findings:
            fire_pass += 1
            print(f"  ✓ FIRES: \"{sent[:80]}...\"")
        else:
            fire_fail += 1
            print(f"  ✗ MISSED: \"{sent[:80]}...\"")

    # ── MUST NOT FIRE ──
    print("\n─── MUST NOT FIRE (Michael's 1-5 sentences — keep or rewrite) ───")
    nofire_pass = 0
    nofire_fail = 0
    for sent in MUST_NOT_FIRE:
        findings = check_r9_generic(sent)
        if not findings:
            nofire_pass += 1
            print(f"  ✓ SILENT: \"{sent[:70]}\"")
        else:
            nofire_fail += 1
            print(f"  ✗ FALSE POSITIVE: \"{sent[:70]}\"")

    # ── DELETION: empty paragraph case ──
    print("\n─── DELETION: Empty paragraph case ───")
    result_empty = apply_r9_deletions(PARA_ALL_GENERIC)
    empty_ok = result_empty == ''
    print(f"  Input: \"{PARA_ALL_GENERIC[:60]}...\"")
    print(f"  Output: \"{result_empty[:60]}\" (empty={result_empty == ''})")
    print(f"  Empty paragraph correctly detected: {'✓' if empty_ok else '✗'}")

    # ── DELETION: mixed paragraph (keeps good, drops generic) ──
    print("\n─── DELETION: Mixed paragraph ───")
    result_mixed = apply_r9_deletions(PARA_MIXED)
    # The generic sentence should be gone, but the 5/5 sentences should remain
    mixed_has_generic = "continue your journey" in result_mixed
    mixed_has_good = "320 feet" in result_mixed and "Free City on Sea" in result_mixed
    mixed_ok = not mixed_has_generic and mixed_has_good
    print(f"  Generic text removed: {'✓' if not mixed_has_generic else '✗'}")
    print(f"  Good text preserved:  {'✓' if mixed_has_good else '✗'}")
    print(f"  Result preview: \"{result_mixed[:100]}...\"")

    # ── DELETION: single-sentence generic paragraph ──
    print("\n─── DELETION: Single generic sentence paragraph ───")
    result_single = apply_r9_deletions(PARA_SINGLE_GENERIC)
    single_ok = result_single == ''
    print(f"  Input: \"{PARA_SINGLE_GENERIC[:60]}...\"")
    print(f"  Output empty: {'✓' if single_ok else '✗'}")

    # ── DELETION: full description with empty paragraph removal ──
    print("\n─── DELETION: Full description (multi-paragraph) ───")
    full_desc = PARA_MIXED + "\n\n" + PARA_SINGLE_GENERIC
    new_desc, deleted, emptied = apply_r9_to_description(full_desc)
    print(f"  Sentences deleted: {deleted}")
    print(f"  Paragraphs emptied: {emptied}")
    print(f"  Single-sentence para removed: {'✓' if PARA_SINGLE_GENERIC not in new_desc else '✗'}")
    print(f"  Good content preserved: {'✓' if '320 feet' in new_desc else '✗'}")

    # ── DANGLING CONNECTIVE TEST ──
    print("\n─── DANGLING CONNECTIVE: Fix after deletion ───")
    para_dangling = (
        "As you continue your journey through this charming town, consider how "
        "these hidden paths have shaped the stories of this place, leading you to "
        "uncover more of its intriguing history. However, the Rue Obscure dates "
        "from 1260 and runs beneath the waterfront houses."
    )
    result_dangling = apply_r9_deletions(para_dangling)
    # The generic first sentence should be deleted; "However," at new start should be stripped
    dangling_ok = not result_dangling.startswith("However") and "1260" in result_dangling
    print(f"  Input starts with generic sentence + 'However, ...'")
    print(f"  Output: \"{result_dangling[:80]}...\"")
    print(f"  Dangling connective stripped: {'✓' if dangling_ok else '✗'}")

    # ── NAVIGATION EXEMPTION ──
    print("\n─── NAVIGATION EXEMPTION (must NEVER fire R9) ───")
    nav_pass = 0
    nav_fail = 0
    for sent in NAV_MUST_NOT_FIRE:
        findings = check_r9_generic(sent)
        if not findings:
            nav_pass += 1
            print(f"  ✓ NAV EXEMPT: \"{sent[:70]}\"")
        else:
            nav_fail += 1
            print(f"  ✗ NAV FALSE POSITIVE: \"{sent[:70]}\"")

    # ── R1 REGRESSION ──
    print("\n─── R1 REGRESSION (must not fire R1 on nouns) ───")
    r1_pass = 0
    r1_fail = 0
    for sent in R1_MUST_NOT_FIRE:
        result = validate_paragraph(sent)
        r1_findings = [f for f in result['findings'] if f['rule_id'] == 'R1_IMPERATIVE']
        if not r1_findings:
            r1_pass += 1
            print(f"  ✓ R1 SILENT: \"{sent[:70]}\"")
        else:
            r1_fail += 1
            print(f"  ✗ R1 FALSE POSITIVE: \"{sent[:70]}\"")

    # ── R8 REGRESSION ──
    print("\n─── R8 REGRESSION (prompt leakage) ───")
    r8_fire_pass = 0
    r8_fire_fail = 0
    for sent in R8_MUST_FIRE:
        findings = check_r8_prompt_leakage(sent)
        if findings:
            r8_fire_pass += 1
            print(f"  ✓ R8 FIRES: \"{sent[:70]}...\"")
        else:
            r8_fire_fail += 1
            print(f"  ✗ R8 MISSED: \"{sent[:70]}...\"")

    r8_nofire_pass = 0
    r8_nofire_fail = 0
    for sent in R8_MUST_NOT_FIRE:
        findings = check_r8_prompt_leakage(sent)
        if not findings:
            r8_nofire_pass += 1
            print(f"  ✓ R8 SILENT: \"{sent[:70]}\"")
        else:
            r8_nofire_fail += 1
            print(f"  ✗ R8 FALSE POSITIVE: \"{sent[:70]}\"")

    # ── DISABLE FLAG TEST ──
    print("\n─── DISABLE_R9_DELETION=1 flag ───")
    os.environ['DISABLE_R9_DELETION'] = '1'
    # The flag is checked by the caller (generate_tour_text.py), not by
    # apply_r9_to_description itself. Just verify the env var mechanism.
    flag_ok = os.environ.get('DISABLE_R9_DELETION', '').strip() == '1'
    print(f"  Flag correctly read: {'✓' if flag_ok else '✗'}")
    os.environ.pop('DISABLE_R9_DELETION', None)

    # ── SUMMARY ──
    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    total_pass = (fire_pass + nofire_pass + nav_pass + r1_pass +
                  r8_fire_pass + r8_nofire_pass +
                  (1 if empty_ok else 0) +
                  (1 if mixed_ok else 0) +
                  (1 if single_ok else 0) +
                  (1 if dangling_ok else 0))
    total_fail = (fire_fail + nofire_fail + nav_fail + r1_fail +
                  r8_fire_fail + r8_nofire_fail +
                  (0 if empty_ok else 1) +
                  (0 if mixed_ok else 1) +
                  (0 if single_ok else 1) +
                  (0 if dangling_ok else 1))

    print(f"  R9 must fire:         {fire_pass}/{len(MUST_FIRE)} pass")
    print(f"  R9 must NOT fire:     {nofire_pass}/{len(MUST_NOT_FIRE)} pass")
    print(f"  Navigation exempt:    {nav_pass}/{len(NAV_MUST_NOT_FIRE)} pass")
    print(f"  R1 regression:        {r1_pass}/{len(R1_MUST_NOT_FIRE)} pass")
    print(f"  R8 fires:             {r8_fire_pass}/{len(R8_MUST_FIRE)} pass")
    print(f"  R8 silent:            {r8_nofire_pass}/{len(R8_MUST_NOT_FIRE)} pass")
    print(f"  Empty-para deletion:  {'pass' if empty_ok else 'FAIL'}")
    print(f"  Mixed-para deletion:  {'pass' if mixed_ok else 'FAIL'}")
    print(f"  Single-sent deletion: {'pass' if single_ok else 'FAIL'}")
    print(f"  Dangling connective:  {'pass' if dangling_ok else 'FAIL'}")
    print(f"  TOTAL:                {total_pass}/{total_pass + total_fail} pass")

    if total_fail > 0:
        print(f"\n  ✗ {total_fail} FAILURES — rule needs adjustment")
        return 1
    else:
        print(f"\n  ✓ ALL PASS")
        return 0


if __name__ == '__main__':
    sys.exit(run_tests())
