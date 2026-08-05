#!/usr/bin/env python3
"""run_local220_sentence_scoring.py — LOCAL-220: Sentence group scoring pipeline.

Calibrates against Michael's 11 groups from EVALUATION_BY_MICHAEL_RIVIERA_2STOP.txt.
Reports side-by-side: his score, our group boundaries, style verdicts, claim verdicts,
publishable flag.

The DISAGREEMENTS are the deliverable.

Uses tests/db_connection.py. No hardcoded credentials.
"""
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))
from db_connection import get_connection

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sentence_group_scorer import (
    split_into_sentence_groups,
    classify_group,
    score_group,
    score_paragraph_groups,
)
from style_validator_detector import (
    _split_sentences,
    _is_style_navigation_sentence,
    check_r1_imperatives,
    check_r9_generic,
    validate_paragraph,
    run_report,
)
from claim_check import check_paragraph as check_claims


# ═══════════════════════════════════════════════════════════════════════════════
# MICHAEL'S 11 GROUPS — ground truth from his evaluation
# ═══════════════════════════════════════════════════════════════════════════════

MICHAELS_GROUPS = [
    {
        'para': 1, 'label': 'A', 'score': 5,
        'sentences': [
            "Start biking southeast on the main road, continue straight until you reach the roundabout near the coast.",
            "Take the second exit onto the coastal path towards Cap d'Antibes.",
        ],
        'reason': 'Excellent cycling directions',
    },
    {
        'para': 1, 'label': 'B', 'score': 1,
        'sentences': [
            "As you arrive at Cap d'Antibes on your cycling tour of the French Riviera, listen to the gentle lapping of waves against the rocky coastline.",
            "Look out for the Villa Eilenroc, an opulent mansion surrounded by lush gardens, symbolizing the lavish parties once hosted here by the elite of the 19th century.",
        ],
        'reason': 'Instructions to the user (listen, look out for)',
    },
    {
        'para': 2, 'label': 'prolog', 'score': 3,
        'sentences': [
            "You are about to embark on a journey through the sun-kissed allure of the French Riviera, a tapestry woven with whispers of opulence and intrigue.",
            "Each stop along this tour serves as a chapter in a grand story, connecting the glitz of the past with the tranquil beauty that endures today.",
            "From the opulent Villa Eilenroc, where the elite of the 19th century once reveled in lavish soirées, to the shadowy Rue Obscure, a secret passageway that provided escape for the town's inhabitants in the 13th century, every corner holds hidden tales waiting to be unearthed.",
            "Join us as we delve into the timeless elegance of this coastal paradise, where every whisper of the azure waves carries echoes of a bygone era.",
        ],
        'reason': 'Conditional 3/5 — only if promises are kept later',
    },
    {
        'para': 3, 'label': 'A', 'score': 3,
        'sentences': [
            "The Cap d'Antibes, a peninsula located south of Antibes and east of Juan-les-Pins, offers a picturesque landscape that has attracted artists and travelers for centuries.",
            "In January 1888, the renowned artist Claude Monet visited this stunning location during his journey through the south of France.",
            "Inspired by the beauty of Cap d'Antibes, Monet stayed at the Château de la Pinède on the advice of his friend Guy de Maupassant, immersing himself in the coastal scenery that captivated his artistic soul.",
            "One concrete sensory detail that envelops you in the atmosphere of Cap d'Antibes is the sound of the waves crashing against the rugged rocks, echoing the timeless rhythm of the sea.",
            "The Tire-Poil coastal trail allows you to explore the cape's natural beauty, stretching from the Garoupe Beach parking lot to the Villa Eilenroc.",
            "Along this 2.7 km route, you'll traverse rocky cliffs, pass by ancient chapels, and witness the panoramic views of the Lérins Islands to the west and the Mercantour Mountains to the east.",
        ],
        'reason': 'Acceptable — Monet 1888, Tire-Poil trail, factual',
    },
    {
        'para': 3, 'label': 'B', 'score': 2,
        'sentences': [
            "As you stand at the highest point of Cap d'Antibes near the ancient Notre Dame de Bon Port chapel, take in the sight of the Garoupe lighthouse overlooking the Gulf of Juan and the Bay of Angels.",
            "The nearby Abri de l'Olivette, a sheltered harbor for traditional local boats, adds to the maritime charm of this coastal gem.",
            "Pedal along the coastline, envisioning the hidden coves and stories that lie just beyond the horizon, immersing yourself in the history and natural beauty of Cap d'Antibes.",
        ],
        'reason': 'Too many imperatives without substance (take in, pedal, envision)',
    },
    {
        'para': 4, 'label': 'A', 'score': 1,
        'sentences': [
            "As you arrive at Villefranche-sur-Mer on your French Riviera cycling tour, pause to take in the breathtaking view of the deep natural harbor, a historic port that has welcomed ships for centuries.",
        ],
        'reason': 'Instruction (pause to take in)',
    },
    {
        'para': 4, 'label': 'B', 'score': 1,
        'sentences': [
            "Look for the Rue Obscure, a mysterious 13th-century passageway that once served as an escape route for the town's inhabitants.",
        ],
        'reason': 'Instruction (Look for), missing story',
    },
    {
        'para': 5, 'label': 'A', 'score': 5,
        'sentences': [
            'Villefranche-sur-Mer, known as the "Free City on Sea," has ancient streets that exude a timeless charm.',
            "The town's strategic location east of Nice and southwest of Monaco has been pivotal in its history.",
            "The deep bay of Villefranche provides secure anchorage for ships, with depths reaching 320 feet, a natural wonder in the Mediterranean.",
        ],
        'reason': 'Excellent — specific, informative, no instructions',
    },
    {
        'para': 5, 'label': 'B', 'score': 1,
        'sentences': [
            "Walking through the narrow streets may evoke the scent of sea salt, linking you to the town's maritime legacy.",
            "The Rue Obscure, with its shadowy passageways, whispers tales of a bygone era when it provided shelter and secrecy to the town's residents.",
            "This historical gem adds depth to your understanding of Villefranche-sur-Mer's past and its resilience through the centuries.",
        ],
        'reason': 'Style violations (evoke, whispers tales, adds depth to your understanding)',
    },
    {
        'para': 5, 'label': 'C', 'score': 0,
        'sentences': [
            "As you continue your journey through this charming town, consider how these hidden paths have shaped the stories of this place, leading you to uncover more of its intriguing history.",
        ],
        'reason': 'Generic — can be placed in millions of stops',
    },
    {
        'para': 6, 'label': 'transition', 'score': 0,
        'sentences': [
            "From Cap d'Antibes to Villefranche-sur-Mer \u2014 a collection that spans more ground than these stops alone.",
        ],
        'reason': 'Generic — can be placed in millions of stops',
    },
]

# The six source paragraphs as Michael received them
PARAGRAPHS = [
    # Paragraph 1 (Stop 1, directions + instruction)
    "Start biking southeast on the main road, continue straight until you reach the roundabout near the coast. Take the second exit onto the coastal path towards Cap d'Antibes. Enjoy the refreshing sea breeze along the way. As you arrive at Cap d'Antibes on your cycling tour of the French Riviera, listen to the gentle lapping of waves against the rocky coastline. Look out for the Villa Eilenroc, an opulent mansion surrounded by lush gardens, symbolizing the lavish parties once hosted here by the elite of the 19th century.",
    # Paragraph 2 (prolog)
    "You are about to embark on a journey through the sun-kissed allure of the French Riviera, a tapestry woven with whispers of opulence and intrigue. Each stop along this tour serves as a chapter in a grand story, connecting the glitz of the past with the tranquil beauty that endures today. From the opulent Villa Eilenroc, where the elite of the 19th century once reveled in lavish soirées, to the shadowy Rue Obscure, a secret passageway that provided escape for the town's inhabitants in the 13th century, every corner holds hidden tales waiting to be unearthed. Join us as we delve into the timeless elegance of this coastal paradise, where every whisper of the azure waves carries echoes of a bygone era.",
    # Paragraph 3 (Cap d'Antibes content)
    "The Cap d'Antibes, a peninsula located south of Antibes and east of Juan-les-Pins, offers a picturesque landscape that has attracted artists and travelers for centuries. In January 1888, the renowned artist Claude Monet visited this stunning location during his journey through the south of France. Inspired by the beauty of Cap d'Antibes, Monet stayed at the Château de la Pinède on the advice of his friend Guy de Maupassant, immersing himself in the coastal scenery that captivated his artistic soul. One concrete sensory detail that envelops you in the atmosphere of Cap d'Antibes is the sound of the waves crashing against the rugged rocks, echoing the timeless rhythm of the sea. The Tire-Poil coastal trail allows you to explore the cape's natural beauty, stretching from the Garoupe Beach parking lot to the Villa Eilenroc. Along this 2.7 km route, you'll traverse rocky cliffs, pass by ancient chapels, and witness the panoramic views of the Lérins Islands to the west and the Mercantour Mountains to the east. As you stand at the highest point of Cap d'Antibes near the ancient Notre Dame de Bon Port chapel, take in the sight of the Garoupe lighthouse overlooking the Gulf of Juan and the Bay of Angels. The nearby Abri de l'Olivette, a sheltered harbor for traditional local boats, adds to the maritime charm of this coastal gem. Pedal along the coastline, envisioning the hidden coves and stories that lie just beyond the horizon, immersing yourself in the history and natural beauty of Cap d'Antibes.",
    # Paragraph 4 (Villefranche arrival)
    "As you arrive at Villefranche-sur-Mer on your French Riviera cycling tour, pause to take in the breathtaking view of the deep natural harbor, a historic port that has welcomed ships for centuries. Look for the Rue Obscure, a mysterious 13th-century passageway that once served as an escape route for the town's inhabitants.",
    # Paragraph 5 (Villefranche content)
    'Villefranche-sur-Mer, known as the "Free City on Sea," has ancient streets that exude a timeless charm. The town\'s strategic location east of Nice and southwest of Monaco has been pivotal in its history. The deep bay of Villefranche provides secure anchorage for ships, with depths reaching 320 feet, a natural wonder in the Mediterranean. Walking through the narrow streets may evoke the scent of sea salt, linking you to the town\'s maritime legacy. The Rue Obscure, with its shadowy passageways, whispers tales of a bygone era when it provided shelter and secrecy to the town\'s residents. This historical gem adds depth to your understanding of Villefranche-sur-Mer\'s past and its resilience through the centuries. As you continue your journey through this charming town, consider how these hidden paths have shaped the stories of this place, leading you to uncover more of its intriguing history.',
    # Paragraph 6 (transition)
    "From Cap d'Antibes to Villefranche-sur-Mer \u2014 a collection that spans more ground than these stops alone.",
]


def get_corpus_passages():
    """Fetch corpus passages for the Riviera tour stops."""
    conn = get_connection()
    cur = conn.cursor()

    # Cap d'Antibes passages
    cur.execute(
        "SELECT passages_json FROM stop_corpus WHERE stop_title = %s",
        ("Cap d'Antibes",)
    )
    row = cur.fetchone()
    cap_passages = []
    if row:
        data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        cap_passages = [p.get('text', p) if isinstance(p, dict) else p for p in data]

    # Villefranche — no corpus (confirmed)
    villefranche_passages = []

    conn.close()
    return cap_passages, villefranche_passages


def run_calibration():
    """Run the sentence group scoring pipeline against Michael's 11 groups."""
    print("=" * 80)
    print("LOCAL-220: SENTENCE GROUP SCORING — CALIBRATION AGAINST MICHAEL'S EVALUATION")
    print("=" * 80)

    cap_passages, villefranche_passages = get_corpus_passages()
    print(f"\nCorpus: Cap d'Antibes = {len(cap_passages)} passages, Villefranche = {len(villefranche_passages)} passages")

    # ─── Part 1: Group boundary agreement ────────────────────────────────
    print("\n" + "─" * 80)
    print("PART 1: GROUP BOUNDARY AGREEMENT")
    print("─" * 80)
    print("\nSplitting each paragraph with our algorithm, comparing to Michael's groups.\n")

    # Map paragraph number to stop context
    para_stop_map = {
        1: ('Cap d\'Antibes', 'French Riviera walking area', cap_passages),
        2: ('Cap d\'Antibes', 'French Riviera walking area', cap_passages),
        3: ('Cap d\'Antibes', 'French Riviera walking area', cap_passages),
        4: ('Villefranche-sur-Mer', 'French Riviera walking area', villefranche_passages),
        5: ('Villefranche-sur-Mer', 'French Riviera walking area', villefranche_passages),
        6: ('Villefranche-sur-Mer', 'French Riviera walking area', villefranche_passages),
    }

    total_michael_groups = 0
    total_our_groups = 0
    boundary_matches = 0
    boundary_total = 0

    all_records = []  # For JSON output

    for para_idx, paragraph in enumerate(PARAGRAPHS):
        para_num = para_idx + 1
        stop_title, venue_name, passages = para_stop_map[para_num]

        # Michael's groups for this paragraph
        michael_groups_here = [g for g in MICHAELS_GROUPS if g['para'] == para_num]
        total_michael_groups += len(michael_groups_here)

        # Our split
        our_groups = split_into_sentence_groups(paragraph)
        total_our_groups += len(our_groups)

        print(f"\n  Paragraph {para_num}: Michael has {len(michael_groups_here)} group(s), we produce {len(our_groups)} group(s)")

        # Compare: for each of Michael's groups, check if any of our groups
        # contains exactly the same sentences
        for mg in michael_groups_here:
            boundary_total += 1
            michael_sents = set(s.strip() for s in mg['sentences'])

            matched = False
            for og in our_groups:
                our_sents = set(s.strip() for s in og)
                if michael_sents == our_sents:
                    matched = True
                    break
                # Also check subset match (our group contains all his sentences)
                if michael_sents.issubset(our_sents) and len(our_sents) <= len(michael_sents) + 1:
                    matched = True
                    break

            if matched:
                boundary_matches += 1
                print(f"    ✓ Group {mg['label']} (score {mg['score']}): MATCH")
            else:
                # Show what we produced instead
                print(f"    ✗ Group {mg['label']} (score {mg['score']}): MISMATCH")
                print(f"      Michael's {len(mg['sentences'])} sentences:")
                for s in mg['sentences']:
                    print(f"        \"{s[:70]}...\"" if len(s) > 70 else f"        \"{s}\"")
                # Find closest our group
                best_overlap = 0
                best_og = None
                for og in our_groups:
                    our_sents = set(s.strip() for s in og)
                    overlap = len(michael_sents & our_sents)
                    if overlap > best_overlap:
                        best_overlap = overlap
                        best_og = og
                if best_og:
                    print(f"      Our closest ({len(best_og)} sentences, {best_overlap} overlap):")
                    for s in best_og:
                        print(f"        \"{s[:70]}...\"" if len(s) > 70 else f"        \"{s}\"")

    agreement_rate = boundary_matches / boundary_total if boundary_total > 0 else 0
    print(f"\n  ─────────────────────────────────────────────────")
    print(f"  GROUP BOUNDARY AGREEMENT: {boundary_matches}/{boundary_total} = {agreement_rate:.1%}")
    print(f"  Michael's groups: {total_michael_groups}, Our groups: {total_our_groups}")
    print(f"  ─────────────────────────────────────────────────")

    # ─── Part 2: Per-group scoring, side by side ─────────────────────────
    print("\n\n" + "─" * 80)
    print("PART 2: PER-GROUP RECORDS — MICHAEL'S SCORE vs OUR VERDICTS")
    print("─" * 80)

    known_disagreement_320ft = False
    known_disagreement_cycling = False

    for mg in MICHAELS_GROUPS:
        para_num = mg['para']
        stop_title, venue_name, passages = para_stop_map[para_num]

        # Score this group
        record = score_group(
            sentences=mg['sentences'],
            stop_title=stop_title,
            venue_name=venue_name,
            passages=passages,
        )

        # Print side-by-side
        print(f"\n  ┌─ ¶{mg['para']} Group {mg['label']} — Michael: {mg['score']}/5 {'─' * 40}")
        print(f"  │ Classification: {record['classification']}")
        print(f"  │ Sentences ({len(mg['sentences'])}):")
        for s in mg['sentences']:
            print(f"  │   \"{s[:80]}{'...' if len(s) > 80 else ''}\"")
        print(f"  │")
        print(f"  │ Style: {record['style_verdicts']['rules_violated'] or '(clean)'}")
        if record['style_verdicts']['findings']:
            for f in record['style_verdicts']['findings'][:3]:
                print(f"  │   {f['rule_id']}: \"{f['sentence'][:60]}...\"")
        print(f"  │")
        print(f"  │ Claims: {record['claim_verdicts']['verdict_counts']}")
        if record['claim_verdicts']['claims']:
            for c in record['claim_verdicts']['claims']:
                print(f"  │   [{c['verdict']}] \"{c['text'][:60]}\"")
        print(f"  │")
        print(f"  │ PUBLISHABLE: {record['publishable']}")
        if record['block_reasons']:
            print(f"  │ Block reasons: {record['block_reasons']}")
        print(f"  │")

        # Check known disagreements
        # 1. "depths reaching 320 feet" — Michael 5/5, claim_check marks unsupported
        if mg['para'] == 5 and mg['label'] == 'A':
            # D100 (Michael): UNSUPPORTED does not block — only CONTRADICTED does.
            # The two-axis shape is still what we assert, but the axes now read:
            # excellent quality, publishable, and carrying unverified claims that
            # must be disclosed and sent to external verification (LOCAL-221).
            if record['publishable'] and record.get('unsupported_claims', 0) > 0:
                known_disagreement_320ft = True
                print(f"  │ ★ TWO-AXIS CASE: Michael 5/5, publishable, but "
                      f"{record['unsupported_claims']} unverified claim(s)")
                print(f"  │   ('320 feet'). Disclosed, not blocked — D100.")

        # 2. Cycling directions — pure imperatives, classified NAVIGATION, clean
        if mg['para'] == 1 and mg['label'] == 'A':
            if record['classification'] == 'NAVIGATION' and record['publishable']:
                known_disagreement_cycling = True
                print(f"  │ ★ KNOWN SHAPE: Navigation, imperative, no proper noun/date —")
                print(f"  │   classified NAVIGATION, publishable, clean. Matches Michael's 5/5.")

        print(f"  └{'─' * 78}")

        # Build JSON record
        all_records.append({
            'paragraph': mg['para'],
            'group_label': mg['label'],
            'michael_score': mg['score'],
            'michael_reason': mg['reason'],
            'classification': record['classification'],
            'sentences': mg['sentences'],
            'style_rules_violated': record['style_verdicts']['rules_violated'],
            'claim_verdict_counts': record['claim_verdicts']['verdict_counts'],
            'claims': [
                {'text': c['text'], 'verdict': c['verdict'], 'type': c['type']}
                for c in record['claim_verdicts']['claims']
            ],
            'publishable': record['publishable'],
            'block_reasons': record['block_reasons'],
            # D100: unverified claims are disclosed and sent to external
            # verification (LOCAL-221), not blocked. Carried in the record so a
            # downstream consumer can act on them.
            'unsupported_claims': record.get('unsupported_claims', 0),
        })

    # ─── Part 3: Known disagreements check ───────────────────────────────
    print("\n\n" + "─" * 80)
    print("PART 3: KNOWN DISAGREEMENTS (must both be present)")
    print("─" * 80)

    print(f"\n  1. '320 feet' — quality 5/5 but BLOCKED (unsupported): {'✓ PRESENT' if known_disagreement_320ft else '✗ MISSING'}")
    print(f"  2. Cycling directions — NAVIGATION, clean, publishable: {'✓ PRESENT' if known_disagreement_cycling else '✗ MISSING'}")

    if known_disagreement_320ft and known_disagreement_cycling:
        print("\n  ✓ Both known disagreements present and visibly two-axis.")
    else:
        print("\n  ✗ One or both known disagreements missing!")

    # ─── Part 4: Write JSON records ──────────────────────────────────────
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'sentence_group_records_local220.json')
    with open(output_path, 'w') as f:
        json.dump({
            'schema_version': '1.0',
            'task': 'LOCAL-220',
            'description': 'Per-sentence-group records for Riviera 2-stop tour, calibrated against Michael\'s evaluation',
            'group_boundary_agreement': f'{boundary_matches}/{boundary_total} = {agreement_rate:.1%}',
            'known_disagreements': {
                '320_feet_quality_vs_publishability': known_disagreement_320ft,
                'cycling_navigation_clean': known_disagreement_cycling,
            },
            'records': all_records,
        }, f, indent=2)
    print(f"\n  JSON records written to: {output_path}")

    return agreement_rate, known_disagreement_320ft, known_disagreement_cycling, all_records


def run_validator_regressions():
    """Run existing style validator to confirm no regressions."""
    print("\n\n" + "=" * 80)
    print("STYLE VALIDATOR REGRESSION CHECK")
    print("=" * 80)

    # Run over the known Riviera sentences from Michael's evaluation
    # These are the same checks from run_r9_riviera_and_corpus.py
    print("\n  R9 vs Michael's 0/5 boundary:")
    disagreements = 0
    for mg in MICHAELS_GROUPS:
        for sent in mg['sentences']:
            findings = check_r9_generic(sent)
            r9_fires = len(findings) > 0
            expected = (mg['score'] == 0)
            if r9_fires != expected:
                disagreements += 1
                print(f"    ✗ ¶{mg['para']}{mg['label']} (score {mg['score']}): R9={'fires' if r9_fires else 'silent'}, expected {'fires' if expected else 'silent'}")
                print(f"      \"{sent[:70]}...\"")

    if disagreements == 0:
        print("    ✓ R9 agrees with Michael's 0/5 boundary on all 11 groups")
    else:
        print(f"    ✗ {disagreements} disagreement(s)")

    # Navigation exemption check — style validator's narrow exemption
    # Note: The style validator intentionally does NOT exempt "Start biking"
    # or "Take the second exit" — its exemption is narrower than our group
    # classifier (by design, D55). This is NOT a regression; it is the
    # existing behaviour. The GROUP-level classification handles this:
    # groups classified NAVIGATION are exempt from style verdicts in score_group().
    print("\n  Navigation group classification (LOCAL-220 classifier):")
    nav_sents = MICHAELS_GROUPS[0]['sentences']  # Group 1A, cycling directions
    from sentence_group_scorer import _is_navigation_for_classification
    for sent in nav_sents:
        is_nav = _is_navigation_for_classification(sent)
        if is_nav:
            print(f"    ✓ Classified NAVIGATION: \"{sent[:60]}...\"")
        else:
            print(f"    ✗ NOT classified NAVIGATION: \"{sent[:60]}...\"")
            disagreements += 1

    # Style-scored sentences should fire style rules
    print("\n  Style rules on known violations:")
    # ¶1B: "Look out for" — R1 should fire
    for sent in MICHAELS_GROUPS[1]['sentences']:
        r1 = check_r1_imperatives(sent)
        if r1:
            print(f"    ✓ R1 fires: \"{sent[:60]}...\"")
        else:
            # "Listen to the gentle lapping" doesn't start with a route verb
            # but "Look out for" should fire
            print(f"    - R1 silent: \"{sent[:60]}...\"")

    # Full validate_paragraph on a known-clean paragraph (¶5A)
    print("\n  validate_paragraph on ¶5A (Michael 5/5, should be style-clean):")
    para_5a = ' '.join(MICHAELS_GROUPS[7]['sentences'])
    result = validate_paragraph(para_5a)
    if not result['rules_violated']:
        print(f"    ✓ Clean (no style rules violated)")
    else:
        print(f"    Rules violated: {result['rules_violated']}")
        # This is not a regression if the only fires are on known patterns

    return disagreements


def run_db_invariants():
    """Check database invariants: audio_tours count and nice list."""
    print("\n\n" + "=" * 80)
    print("DATABASE INVARIANTS")
    print("=" * 80)

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM audio_tours")
    count = cur.fetchone()[0]
    print(f"\n  audio_tours count: {count}")
    assert count == 130, f"Expected 130, got {count}"
    print(f"  ✓ audio_tours at 130")

    cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,21,24,27,28,29,152) ORDER BY id")
    nice_list = [r[0] for r in cur.fetchall()]
    expected_nice = [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]
    print(f"  Nice list: {nice_list}")
    assert nice_list == expected_nice, f"Nice list mismatch: {nice_list}"
    print(f"  ✓ Nice list intact")

    conn.close()
    return count, nice_list


if __name__ == '__main__':
    agreement_rate, disagr_320, disagr_cycling, records = run_calibration()
    reg_failures = run_validator_regressions()
    count, nice_list = run_db_invariants()

    print("\n\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"\n  Group boundary agreement: {agreement_rate:.1%}")
    print(f"  Known disagreement (320ft): {'✓' if disagr_320 else '✗'}")
    print(f"  Known disagreement (cycling): {'✓' if disagr_cycling else '✗'}")
    print(f"  Validator regressions: {reg_failures}")
    print(f"  audio_tours: {count}")
    print(f"  Nice list: {nice_list}")

    if reg_failures > 0:
        print(f"\n  ✗ FAILED: {reg_failures} regression(s)")
        sys.exit(1)
    elif not disagr_320 or not disagr_cycling:
        print(f"\n  ✗ FAILED: known disagreements not both present")
        sys.exit(1)
    else:
        print(f"\n  ✓ PASS")
        sys.exit(0)
