#!/usr/bin/env python3
"""run_local327_rescore.py — LOCAL-327: Before/after scores with corpus ceiling.

Shows the effect of the corpus-availability ceiling on tour scores.
"Before" = evaluate() without conn (no corpus lookup, no ceiling).
"After"  = evaluate() with conn (corpus loaded, ceiling applied).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))

from db_connection import get_connection, log_db_target
from tour_evaluator import evaluate


def rescore_tour(filepath: str, n_requested: int, conn):
    """Score a tour before/after corpus ceiling."""
    with open(filepath, 'r', encoding='utf-8') as f:
        tour_text = f.read()

    # Before: no conn = no corpus lookup = no ceiling
    eval_before = evaluate(tour_text, n_requested)
    # After: with conn = corpus loaded = ceiling applies
    eval_after = evaluate(tour_text, n_requested, conn=conn)

    return eval_before, eval_after


def main():
    conn = get_connection()
    log_db_target("rescore")

    tours_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tours')

    # Tours to rescore (at least 6 including the two named by Michael)
    tours = [
        ('LOCAL262_asian_arts_8stop_restored.txt', 8, 'Museum 8-stop (Asian Arts)'),
        ('LOCAL317_5stop_old_nice_restaurant.txt', 5, 'Old Nice Restaurant 317'),
        ('LOCAL318_5stop_old_nice_restaurant.txt', 5, 'Old Nice Restaurant 318'),
        ('Palais_Lascaris__Nice_museum_tour_20260727_174018.txt', 8, 'Palais Lascaris'),
        ('Musee_Matisse__Nice__France_museum_tour_20260709_150601.txt', 8, 'Musée Matisse'),
        ('pilot_chagall_resubmit.txt', 8, 'Chagall (pilot resubmit)'),
        ('Musee_national_Marc_Chagall__Nice__France_museum_tour_20260709_205602.txt', 8, 'Chagall 205602'),
        ('Musee_national_Marc_Chagall__Nice__France_museum_tour_20260709_213940.txt', 8, 'Chagall 213940'),
    ]

    print("=" * 110)
    print("LOCAL-327 RESCORE: Before/After Corpus-Availability Ceiling")
    print("=" * 110)
    print(f"{'Tour':<45} {'Before':<10} {'After':<10} {'Delta':<10} {'Stops changed'}")
    print("-" * 110)

    for filename, n, label in tours:
        filepath = os.path.join(tours_dir, filename)
        if not os.path.exists(filepath):
            print(f"  SKIP {filename}: file not found")
            continue

        eval_before, eval_after = rescore_tour(filepath, n, conn)
        if not eval_before or not eval_after:
            print(f"  SKIP {filename}: could not score")
            continue

        before_score = eval_before.score.base_score
        after_score = eval_after.score.base_score
        delta = after_score - before_score

        # Find changed stops
        changed = []
        for sb, sa_after in zip(eval_before.per_stop, eval_after.per_stop):
            if sb['classification'] != sa_after['classification']:
                changed.append(f"{sb['title'][:25]}:{sb['classification']}→{sa_after['classification']}")

        changed_str = '; '.join(changed) if changed else '(none)'
        print(f"  {label:<43} {before_score:>6.1f}    {after_score:>6.1f}    {delta:>+6.1f}    {changed_str}")

    # Detail for the museum 8-stop
    print("\n" + "=" * 110)
    print("DETAIL: Museum 8-stop (Asian Arts)")
    print("=" * 110)
    filepath = os.path.join(tours_dir, 'LOCAL262_asian_arts_8stop_restored.txt')
    if os.path.exists(filepath):
        eval_before, eval_after = rescore_tour(filepath, 8, conn)
        print(f"{'Stop':<45} {'Before':<12} {'After':<12} {'G%':<6}")
        print("-" * 75)
        for sb, sa in zip(eval_before.per_stop, eval_after.per_stop):
            marker = " ←" if sb['classification'] != sa['classification'] else ""
            print(f"  {sb['title'][:42]:<43} {sb['classification']:<12} {sa['classification']:<12} {sa['groundedness']:.0%}{marker}")

    # Detail for the restaurant tours
    for rname in ['LOCAL317_5stop_old_nice_restaurant.txt', 'LOCAL318_5stop_old_nice_restaurant.txt']:
        print(f"\n{'─' * 110}")
        print(f"DETAIL: {rname}")
        print(f"{'─' * 110}")
        filepath = os.path.join(tours_dir, rname)
        if os.path.exists(filepath):
            eval_before, eval_after = rescore_tour(filepath, 5, conn)
            if eval_before and eval_after:
                print(f"{'Stop':<45} {'Before':<12} {'After':<12} {'G%':<6}")
                print("-" * 75)
                for sb, sa in zip(eval_before.per_stop, eval_after.per_stop):
                    marker = " ←" if sb['classification'] != sa['classification'] else ""
                    print(f"  {sb['title'][:42]:<43} {sb['classification']:<12} {sa['classification']:<12} {sa['groundedness']:.0%}{marker}")

    conn.close()


if __name__ == '__main__':
    main()
