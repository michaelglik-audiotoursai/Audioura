#!/usr/bin/env python3
"""Run R9 over the Riviera 2-stop tour and all stored tours.

LOCAL-216: Per-sentence table (R9 verdict vs Michael's score) and
corpus-wide deletion rate.

Uses tests/db_connection.py. No hardcoded credentials.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))
from db_connection import get_connection

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from style_validator_detector import (
    check_r9_generic, apply_r9_to_description, _split_sentences,
    _is_style_navigation_sentence, validate_paragraph,
)
from stop_anchor_detector_v2 import parse_tour_stops


def run_riviera_analysis():
    """Per-sentence R9 verdict vs Michael's score for the Riviera tour."""
    print("=" * 78)
    print("R9 vs MICHAEL'S SCORES — Riviera 2-Stop Tour (Tour 163)")
    print("=" * 78)

    # The six paragraphs and Michael's sentence-group scores
    # Format: (paragraph_num, group_label, score, sentences)
    michaels_groups = [
        (1, "A", 5, [
            "Start biking southeast on the main road, continue straight until you reach the roundabout near the coast.",
            "Take the second exit onto the coastal path towards Cap d'Antibes.",
        ]),
        (1, "B", 1, [
            "As you arrive at Cap d'Antibes on your cycling tour of the French Riviera, listen to the gentle lapping of waves against the rocky coastline.",
            "Look out for the Villa Eilenroc, an opulent mansion surrounded by lush gardens, symbolizing the lavish parties once hosted here by the elite of the 19th century.",
        ]),
        (2, "prolog", 3, [
            "You are about to embark on a journey through the sun-kissed allure of the French Riviera, a tapestry woven with whispers of opulence and intrigue.",
            "Each stop along this tour serves as a chapter in a grand story, connecting the glitz of the past with the tranquil beauty that endures today.",
            "From the opulent Villa Eilenroc, where the elite of the 19th century once reveled in lavish soirées, to the shadowy Rue Obscure, a secret passageway that provided escape for the town's inhabitants in the 13th century, every corner holds hidden tales waiting to be unearthed.",
            "Join us as we delve into the timeless elegance of this coastal paradise, where every whisper of the azure waves carries echoes of a bygone era.",
        ]),
        (3, "A", 3, [
            "The Cap d'Antibes, a peninsula located south of Antibes and east of Juan-les-Pins, offers a picturesque landscape that has attracted artists and travelers for centuries.",
            "In January 1888, the renowned artist Claude Monet visited this stunning location during his journey through the south of France.",
            "Inspired by the beauty of Cap d'Antibes, Monet stayed at the Château de la Pinède on the advice of his friend Guy de Maupassant, immersing himself in the coastal scenery that captivated his artistic soul.",
            "One concrete sensory detail that envelops you in the atmosphere of Cap d'Antibes is the sound of the waves crashing against the rugged rocks, echoing the timeless rhythm of the sea.",
            "The Tire-Poil coastal trail allows you to explore the cape's natural beauty, stretching from the Garoupe Beach parking lot to the Villa Eilenroc.",
            "Along this 2.7 km route, you'll traverse rocky cliffs, pass by ancient chapels, and witness the panoramic views of the Lérins Islands to the west and the Mercantour Mountains to the east.",
        ]),
        (3, "B", 2, [
            "As you stand at the highest point of Cap d'Antibes near the ancient Notre Dame de Bon Port chapel, take in the sight of the Garoupe lighthouse overlooking the Gulf of Juan and the Bay of Angels.",
            "The nearby Abri de l'Olivette, a sheltered harbor for traditional local boats, adds to the maritime charm of this coastal gem.",
            "Pedal along the coastline, envisioning the hidden coves and stories that lie just beyond the horizon, immersing yourself in the history and natural beauty of Cap d'Antibes.",
        ]),
        (4, "A", 1, [
            "As you arrive at Villefranche-sur-Mer on your French Riviera cycling tour, pause to take in the breathtaking view of the deep natural harbor, a historic port that has welcomed ships for centuries.",
        ]),
        (4, "B", 1, [
            "Look for the Rue Obscure, a mysterious 13th-century passageway that once served as an escape route for the town's inhabitants.",
        ]),
        (5, "A", 5, [
            "Villefranche-sur-Mer, known as the \"Free City on Sea,\" has ancient streets that exude a timeless charm.",
            "The town's strategic location east of Nice and southwest of Monaco has been pivotal in its history.",
            "The deep bay of Villefranche provides secure anchorage for ships, with depths reaching 320 feet, a natural wonder in the Mediterranean.",
        ]),
        (5, "B", 1, [
            "Walking through the narrow streets may evoke the scent of sea salt, linking you to the town's maritime legacy.",
            "The Rue Obscure, with its shadowy passageways, whispers tales of a bygone era when it provided shelter and secrecy to the town's residents.",
            "This historical gem adds depth to your understanding of Villefranche-sur-Mer's past and its resilience through the centuries.",
        ]),
        (5, "C", 0, [
            "As you continue your journey through this charming town, consider how these hidden paths have shaped the stories of this place, leading you to uncover more of its intriguing history.",
        ]),
        (6, "transition", 0, [
            "From Cap d'Antibes to Villefranche-sur-Mer \u2014 a collection that spans more ground than these stops alone.",
        ]),
    ]

    print("\n{:<5} {:<10} {:<7} {:<10} {:<6} {}".format(
        "Para", "Group", "Score", "R9_fires", "Match", "Sentence (first 70 chars)"))
    print("-" * 120)

    disagreements = 0
    total_sentences = 0

    for para_num, group_label, score, sentences in michaels_groups:
        for i, sent in enumerate(sentences):
            total_sentences += 1
            findings = check_r9_generic(sent)
            r9_fires = len(findings) > 0

            # Expected: R9 should fire ONLY on score=0
            expected_fire = (score == 0)
            match = (r9_fires == expected_fire)
            if not match:
                disagreements += 1

            marker = "✓" if match else "✗ DISAGREE"
            fire_str = "YES" if r9_fires else "no"

            label = f"{para_num}{group_label}" if i == 0 else ""
            score_str = str(score) if i == 0 else ""

            print(f"{label:<5} {'':10} {score_str:<7} {fire_str:<10} {marker:<6} {sent[:70]}")

    print("\n" + "-" * 78)
    print(f"Total sentences: {total_sentences}")
    print(f"Disagreements:   {disagreements}")
    if disagreements == 0:
        print("✓ R9 perfectly matches Michael's 0/5 vs 1-5 boundary")
    else:
        print(f"✗ {disagreements} disagreement(s) — R9 fires on a non-zero or misses a zero")

    return disagreements


def run_corpus_scan():
    """Run R9 over all stored tours and report deletion rate."""
    print("\n\n" + "=" * 78)
    print("CORPUS-WIDE R9 DELETION RATE")
    print("=" * 78)

    conn = get_connection()
    import psycopg2.extras
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT id, tour_name, tour_content FROM audio_tours WHERE tour_content IS NOT NULL AND tour_content != ''")
    tours = cur.fetchall()

    total_tours = len(tours)
    total_sentences = 0
    total_deleted = 0
    total_paras_emptied = 0
    tours_affected = 0
    tour_details = []

    for tour in tours:
        content = tour['tour_content']
        if not content:
            continue

        stops = parse_tour_stops(content)
        tour_deleted = 0
        tour_emptied = 0
        tour_sentences = 0

        for stop in stops:
            for para in stop['paragraphs']:
                if len(para.strip()) <= 30:
                    continue
                sentences = _split_sentences(para)
                meaningful = [s for s in sentences if len(s) >= 10]
                tour_sentences += len(meaningful)

                _, deleted, emptied = apply_r9_to_description(para)
                tour_deleted += deleted
                tour_emptied += emptied

        total_sentences += tour_sentences
        total_deleted += tour_deleted
        total_paras_emptied += tour_emptied

        if tour_deleted > 0:
            tours_affected += 1
            tour_details.append({
                'id': tour['id'],
                'name': tour['tour_name'][:40],
                'deleted': tour_deleted,
                'emptied': tour_emptied,
                'sentences': tour_sentences,
            })

    # Report
    deletion_rate = (total_deleted / total_sentences * 100) if total_sentences > 0 else 0

    print(f"\n  Tours scanned:          {total_tours}")
    print(f"  Total sentences:        {total_sentences}")
    print(f"  Sentences R9 deletes:   {total_deleted}")
    print(f"  Paragraphs emptied:     {total_paras_emptied}")
    print(f"  Tours affected:         {tours_affected}")
    print(f"  Deletion rate:          {deletion_rate:.1f}%")

    if deletion_rate > 15:
        print(f"\n  ✗ STOP: deletion rate {deletion_rate:.1f}% exceeds 15% ceiling.")
        print(f"    At this rate R9 is rewriting the product, not identifying filler.")
        print(f"    This is Michael's call, not ours.")
    else:
        print(f"\n  ✓ Deletion rate {deletion_rate:.1f}% is within the 15% ceiling.")

    # Show affected tours
    if tour_details:
        print(f"\n  Affected tours ({tours_affected}):")
        for t in sorted(tour_details, key=lambda x: x['deleted'], reverse=True)[:15]:
            print(f"    Tour {t['id']:>3}: {t['deleted']} deleted, {t['emptied']} emptied  ({t['name']})")

    # Database invariant checks
    cur.execute("SELECT COUNT(*) as cnt FROM audio_tours")
    row_count = cur.fetchone()['cnt']
    print(f"\n  audio_tours row count: {row_count}")

    # Nice list check
    cur.execute("""
        SELECT id FROM audio_tours
        WHERE tour_name ILIKE '%nice%'
        AND id NOT IN (SELECT id FROM audio_tours WHERE is_test = true)
        ORDER BY id
    """)
    nice_rows = cur.fetchall()
    nice_ids = [r['id'] for r in nice_rows]
    print(f"  Nice list: {nice_ids}")

    conn.close()
    return deletion_rate


if __name__ == '__main__':
    disagreements = run_riviera_analysis()
    rate = run_corpus_scan()

    print("\n" + "=" * 78)
    print("FINAL VERDICT")
    print("=" * 78)
    if disagreements > 0:
        print(f"  ✗ {disagreements} disagreement(s) with Michael's scores")
        sys.exit(1)
    elif rate > 15:
        print(f"  ✗ Deletion rate {rate:.1f}% exceeds 15% ceiling — STOP")
        sys.exit(1)
    else:
        print(f"  ✓ R9 agrees with Michael's boundary, deletion rate {rate:.1f}%")
        sys.exit(0)
