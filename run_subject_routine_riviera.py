#!/usr/bin/env python3
"""run_subject_routine_riviera.py — LOCAL-237: Run subject routine on Michael's
5 reviewed paragraphs from RIVIERA_2STOP_ROUND2.

Reports per-promise outcomes and compares against his Villa Eilenroc rewrite.
"""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))
from db_connection import get_connection
from subject_validate_expand import (
    gather_promises, process_paragraph, is_subject_routine_enabled
)

# ─── The 5 paragraphs Michael reviewed ──────────────────────────────────────

PARAGRAPH_1 = (
    "Start cycling south on the main road with the sea on your right until you "
    "reach the peninsula's tip with a lighthouse visible in the distance. As you "
    "arrive at Cap d'Antibes, the tranquil sounds of waves lapping against the "
    "rugged coastline greet you. The shimmering waters and the gentle sea breeze "
    "create a serene atmosphere, inviting you to explore the beauty of this "
    "stunning peninsula."
)

PARAGRAPH_2 = (
    "You are about to embark on a journey through the French Riviera, where the "
    "sun-kissed shores of Cap d'Antibes and the medieval charm of Eze Village "
    "converge to paint a vivid tapestry of natural beauty, artistic inspiration, "
    "and historical intrigue. Here, the serene coastline has nurtured the "
    "creativity of renowned artists like Picasso, while the cobblestone streets "
    "of Eze whisper tales of bygone eras. As you wind through the picturesque "
    "landscapes, you'll uncover the timeless allure that has beckoned both "
    "artists and aristocrats to these idyllic shores, each stop offering a new "
    "chapter in the riveting story of this enchanting region."
)

PARAGRAPH_3 = (
    "Cap d'Antibes, situated on the French Riviera, holds a special place in "
    "the region's history and culture. This cape, along with Cap Ferrat to the "
    "northeast, forms a significant feature of the landscape, housing "
    "prestigious establishments like the Hôtel du Cap-Eden-Roc and Grand-Hôtel "
    "du Cap-Ferrat. These iconic hotels are renowned for their exclusivity and "
    "luxury, attracting visitors from around the world. In the literary world, "
    "Cap d'Antibes has inspired notable works, including F. Scott Fitzgerald's "
    'novel "Tender Is the Night." This masterpiece captures the essence of the '
    "French Riviera during the Jazz Age, depicting the poignant tale of Dick "
    "Diver and his wife, Nicole, against the backdrop of this enchanting coastal "
    "setting. The breathtaking sentier Littoral is a scenic coastal path nearly "
    "3.5 kilometers long. It begins at plage de la Garoupe and culminates at "
    "Cap d'Antibes near Villa Eilenroc. The trail offers stunning views of the "
    "coastline, allowing visitors to appreciate the natural beauty of the "
    "surroundings. At Cap d'Antibes, the tranquil vistas and vibrant atmosphere "
    "have inspired artists like Picasso, infusing their work with the essence "
    "of this coastal paradise. Cycling along the shimmering waters, you are not "
    "just exploring a physical landscape but also delving into a rich tapestry "
    "of history and culture that defines the French Riviera. The mystical allure "
    "of Eze Village beckons you forward, promising more wonders and discoveries "
    "along your journey."
)

PARAGRAPH_4 = (
    "Position yourself at the entrance of Eze Village, a medieval gem perched "
    "on a rocky outcrop overlooking the azure waters of the French Riviera. "
    "Take a moment to absorb the ancient aura emanating from the cobblestone "
    "streets and weathered stone buildings that have stood witness to centuries "
    "of history."
)

PARAGRAPH_5 = (
    "In 200 BC, the area surrounding Èze saw its first inhabitants settle near "
    "Mount Bastide. The Antonine Itinerary mentions the bay of Èze as Avisionis "
    "portus, highlighting its maritime significance in antiquity. The timeless "
    "allure of Eze Village resides in its ability to transport visitors back "
    "through the annals of time. The aged stone walls exude a palpable sense "
    "of antiquity, each crack and crevice holding a story. The gentle rustle "
    "of the Mediterranean breeze mingles with the distant chime of church bells, "
    "creating a harmonious symphony of past and present. Wandering through the "
    "narrow alleyways, you'll encounter artisanal workshops where local "
    "craftsmen keep age-old traditions alive, infusing modernity with a touch "
    "of history. As you pause to admire the intricate ironwork adorning "
    "centuries-old doors, the connection between past and present becomes "
    "tangible, a thread weaving through the fabric of time. This stop on the "
    "French Riviera cycling tour offers a profound glimpse into the enduring "
    "spirit of a village steeped in history. The medieval charm of Eze Village "
    "serves as a bridge between ancient civilizations and contemporary life, "
    "inviting you to ponder the enduring legacy of those who once walked these "
    "very streets. At the apex of Jardin Exotique, you can gaze out over the "
    "panoramic vista of the Riviera. The hillsides hold a multitude of tales "
    "from a bygone era. As you cycle onward, remember Eze Village, a testament "
    "to the enduring allure of the French Riviera's rich historical tapestry."
)

PARAGRAPHS = [
    ("Cap d'Antibes", "Paragraph 1 (Orientation)", PARAGRAPH_1),
    ("Cap d'Antibes", "Paragraph 2 (Prolog)", PARAGRAPH_2),
    ("Cap d'Antibes", "Paragraph 3 (Description)", PARAGRAPH_3),
    ("Eze Village", "Paragraph 4 (Orientation)", PARAGRAPH_4),
    ("Eze Village", "Paragraph 5 (Description)", PARAGRAPH_5),
]

# ─── Michael's Villa Eilenroc rewrite facts (from his review) ────────────────
# These are the facts he supplied for the Villa Eilenroc section:
MICHAELS_VILLA_EILENROC_FACTS = {
    'Charles Garnier': 'architect',
    '1867': 'year built',
    'Hugh-Hope Loudon': 'commissioner',
    'Eilenroc = Cornelie reversed': 'name origin (wife\'s name)',
    'the Beaumonts in 1927': 'later owners',
    'the Fitzgeralds': 'literary connection (F. Scott & Zelda)',
}


def run_riviera_analysis():
    """Run the subject routine on Michael's 5 paragraphs and report results."""
    print("=" * 80)
    print("LOCAL-237: Subject Validate Expand — RIVIERA_2STOP_ROUND2 Analysis")
    print("=" * 80)
    print()

    conn = get_connection()
    total_cost = 0.0
    all_promises = 0
    all_expanded = 0
    all_deleted = 0

    for stop_title, para_label, paragraph in PARAGRAPHS:
        print(f"\n{'─' * 70}")
        print(f"  {para_label} — Stop: {stop_title}")
        print(f"{'─' * 70}")
        print(f"  Text: {paragraph[:120]}...")
        print()

        # Stage 1: Gather only (show what we find)
        promises = gather_promises(paragraph)
        print(f"  Promises found: {len(promises)}")

        if not promises:
            print("  (No promises detected — paragraph either delivers or is navigation)")
            continue

        for i, p in enumerate(promises):
            print(f"\n  Promise {i+1}:")
            print(f"    Sentence: \"{p['sentence'][:100]}...\"" if len(p['sentence']) > 100
                  else f"    Sentence: \"{p['sentence']}\"")
            print(f"    Type: {p['promise_type']}")
            print(f"    Subject: {p['subject']}")
            print(f"    Span matched: \"{p['subject_span']}\"")

        # Full pipeline
        result = process_paragraph(
            paragraph=paragraph,
            stop_title=stop_title,
            venue_name="French Riviera cycling tour",
            conn=conn,
        )

        total_cost += result['cost']
        all_promises += len(result['promises_found'])
        all_expanded += result['expanded_count']
        all_deleted += result['deleted_count']

        print(f"\n  Pipeline results:")
        print(f"    Expanded: {result['expanded_count']}")
        print(f"    Deleted: {result['deleted_count']}")
        print(f"    Cost: ${result['cost']:.4f}")

        for r in result['promises_found']:
            outcome = r['outcome']
            print(f"\n    → {r['sentence'][:80]}...")
            print(f"      Outcome: {outcome}")
            if outcome == 'EXPANDED':
                exp = r['expansion']
                print(f"      New: \"{exp['new_sentence'][:120]}\"")
                print(f"      Source quoted: \"{exp['source_quoted'][:120]}\"")
                print(f"      Method: {exp['method']}")
                if r.get('validation', {}).get('url'):
                    print(f"      URL: {r['validation']['url']}")
                print(f"      Tier: {r.get('validation', {}).get('tier')}")
            elif 'DELETED' in outcome:
                print(f"      Reason: {r.get('reason', 'N/A')}")

    conn.close()

    # ─── Summary ─────────────────────────────────────────────────────────────
    print(f"\n\n{'═' * 80}")
    print("SUMMARY — 5 Paragraphs")
    print(f"{'═' * 80}")
    print(f"  Total promises found: {all_promises}")
    print(f"  Expanded: {all_expanded}")
    print(f"  Deleted: {all_deleted}")
    print(f"  Total cost: ${total_cost:.4f}")
    print(f"  Cost per paragraph: ${total_cost / 5:.4f}")
    print(f"  Cost per tour (est. 6 paragraphs): ${total_cost / 5 * 6:.4f}")

    # ─── Villa Eilenroc comparison ───────────────────────────────────────────
    print(f"\n\n{'═' * 80}")
    print("COMPARISON: Michael's Villa Eilenroc rewrite — what could this routine find?")
    print(f"{'═' * 80}")
    print()
    print("Michael supplied these facts for Villa Eilenroc:")
    for fact, role in MICHAELS_VILLA_EILENROC_FACTS.items():
        print(f"  • {fact} — {role}")

    print()
    print("This routine's reach:")
    print("  The stop_corpus for Cap d'Antibes has 7 passages. Checking each")
    print("  fact against what the corpus and external search would yield:")
    print()

    # Check what's findable
    _check_villa_eilenroc_facts(conn=None)


def _check_villa_eilenroc_facts(conn=None):
    """Check how many of Michael's Villa Eilenroc facts are findable."""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    try:
        from subject_validate_expand import validate_subject

        facts_to_check = [
            ("Charles Garnier", "architect of Villa Eilenroc"),
            ("1867", "year Villa Eilenroc was built"),
            ("Hugh-Hope Loudon", "who commissioned Villa Eilenroc"),
            ("Eilenroc Cornelie", "name origin — Cornelie reversed"),
            ("Beaumonts 1927", "later owners of Villa Eilenroc"),
            ("Fitzgerald", "literary connection to Cap d'Antibes"),
        ]

        findable = 0
        total = len(facts_to_check)

        for subject, description in facts_to_check:
            result = validate_subject(
                subject=subject,
                stop_title="Cap d'Antibes",
                venue_name="French Riviera cycling tour",
                conn=conn,
            )
            status = "FOUND" if result['found'] else "NOT FOUND"
            source = result.get('source', 'none') if result['found'] else 'none'
            if result['found']:
                findable += 1
                print(f"  ✓ {subject} ({description})")
                print(f"    Source: {source}")
                passage = result.get('passage', '')
                print(f"    Passage: \"{passage[:150]}\"")
            else:
                print(f"  ✗ {subject} ({description})")
                print(f"    Not found in stop_corpus, venue_corpus, or external search")
            print()

        print(f"  FINDABLE: {findable}/{total} ({findable/total*100:.0f}%)")
        print(f"  This is the honest measure of whether the routine can match")
        print(f"  Michael's knowledge.")
        if findable < total:
            print(f"\n  The {total - findable} unfound facts represent the gap between")
            print(f"  what the routine can source and what a human researcher finds.")
    finally:
        if close_conn:
            conn.close()


if __name__ == '__main__':
    run_riviera_analysis()
