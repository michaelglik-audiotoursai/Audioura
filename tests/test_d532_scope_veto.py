"""[D532] Option B-real: the scope veto, tested in BOTH directions.

Michael selected "B with C's labelling" on 2026-08-26. B's failure mode is not
that it is too strict — it is that the obvious implementation is too lax and
tests green anyway. If "contradiction" means "the page refutes this title", the
veto never fires, and B silently becomes option A (D530's Guernica).

So this suite scores both directions, which is what D528 said was missing from
every extractor change made that week:

  MUST VETO    — works incompatible with a scope the page actually declares.
  MUST ADMIT   — works the page is merely SILENT about. Silence is not evidence.

The page text is the real one, captured on the wire 2026-08-25 and recorded in
STOPLIST_CHAIN.md. Nothing here is reconstructed.

Run:  OPENAI_API_KEY=... python3 tests/test_d532_scope_veto.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generate_tour_text import scope_contradicts, title_appears_in_page

# The MFA "Picasso, Miró, Dalí: Unbound" page, as extracted (STOPLIST_CHAIN.md).
MFA_PAGE = """Picasso, Miró, Dalí: Unbound
Related Events
Livres d'Artiste: Picasso, Miró, Dalí
$5 Third Thursday
Virtual Member Lecture: Picasso, Miró, Dalí
Extras
Step Inside the Exhibition
Sponsors
Abstract black-line drawing with bursts of red, yellow, green, and blue.
detail of two-page spread with gibberish handwritten text, with the center burned out
A Sound Bites concert, as seen from above, taking place in the Linde Family Wing for Contemporary Art
Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers), published by Louis Broder, printed by Mourlot Frères, Paris, 1971
Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by Mourlot Frères, Paris, 1971. Illustrated book with 40 color lithographs (including wrapper front and cover); publisher's vellum. Gift of Boris Fridman.
Bold, experimental, extravagant, and unbound, both literally and in the creative minds that produced them, livres d'artiste had no precedent. At the turn of the 20th century, they revolutionized the book as an art form. Livres d'artiste attracted many famous practitioners—Pablo Picasso, Joan Miró, and Salvador Dalí among them—but they were also deeply collaborative ventures. Authors, publishers, designers, and printmakers played essential roles in bringing them to life.
This exhibition introduces the imaginative world of this form through a group of extraordinary works by Spanish artists. Visitors can explore how images, words, and typography intersect, often in intricate ways that defy expectations. Some artists interpreted foundational texts, as Dalí did in his 1974 illustrations for Sigmund Freud's Moses and Monotheism; others partnered with writers to devise images and words in harmony at the outset, as in Juan Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955). Rarely on view, and resisting easy categorization, these livres d'artiste invite visitors into a world of artistic ambition in which creativity and the power of collaboration led to some of the most singular and compelling achievements of publishing in the 20th century.
Wednesday, September 16–Wednesday, October 7, 2026
Lead support is provided by the Jean S. and Frederic A. Sharf Exhibition Fund.
"""

SCOPE = {'requirements': "Picasso, Miro, Dali: Unbound exhibition",
         'venue_name': 'Museum of Fine Arts, Boston, MA'}

# Production order, which this suite mirrors: a knowledge-proposed work is first
# checked against the page (title_appears_in_page). If the page NAMES it, it is
# PROMOTED to confirmed and never reaches the veto. Only works the page is silent
# about are put to scope_contradicts.
#
# (title, artist, expected, why this case exists)
#   expected: 'veto' | 'admit' | 'promote'
CASES = [
    # ---- MUST VETO: incompatible with a scope the page DECLARES ----
    ("Guernica", "Pablo Picasso", 'veto',
     "D530 shipped this into the tour. Monumental oil painting, and it is in "
     "Madrid — contradicts both the declared livres d'artiste form and the venue."),
    ("The Persistence of Memory", "Salvador Dalí", 'veto',
     "D530 shipped this too. Oil on canvas at MoMA; the page declares an "
     "illustrated-book show at the MFA."),
    ("Nighthawks", "Edward Hopper", 'veto',
     "Artist dimension: the page declares 'a group of extraordinary works by "
     "Spanish artists'. Hopper is not one, and the page never says so."),

    # ---- MUST ADMIT: the page is SILENT, and silence is not evidence ----
    ("Le Chef-d'œuvre inconnu", "Pablo Picasso", 'admit',
     "THE CRUCIAL CASE. A real Picasso livre d'artiste (Vollard, 1931) that this "
     "page never mentions. Fits every declared dimension. A veto here means the "
     "check is doing membership, not contradiction — i.e. it is option D wearing "
     "B's name."),

    # ---- MUST PROMOTE: the page names them, so the page decides, not the model ----
    ("Le Lézard aux plumes d'or", "Joan Miró", 'promote',
     "Named in a credit line. This is the work D530 watched D1v2 delete. It must "
     "never reach the veto — and note WHY that matters: asked cold, the model "
     "calls this illustrated book a 'painting', which would veto it out of the "
     "very show it is the centrepiece of."),
    ("Au Soleil du Plafond", "Juan Gris", 'promote',
     "Named in body prose only. The extractor misses it (D528 defect 2), so "
     "knowledge re-proposes it and the PAGE is what brings it back. Same trap as "
     "above: identified cold, it comes back 'painting'."),
    ("Moses and Monotheism", "Salvador Dalí", 'promote',
     "Also prose-only, explicitly dated 1974 on the page."),
]


def main():
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        print("SKIP: OPENAI_API_KEY not set")
        return 0

    failures, not_run = [], 0
    print(f"[D532] scope veto — {len(CASES)} cases, all three outcomes\n")
    for title, artist, expected, why in CASES:
        # Stage 0, exactly as production does it before calling the veto.
        if title_appears_in_page(title, MFA_PAGE):
            got = 'promote'
            detail = 'page names it'
        else:
            r = scope_contradicts(title, artist, MFA_PAGE, SCOPE, api_key)
            if not r['ok']:
                print(f"  ??  {title[:40]:42s} check did not run: {r['reason'][:50]}")
                not_run += 1
                continue
            got = 'veto' if r['vetoed'] else 'admit'
            detail = f"dim={r['dimension']} work_form={(r.get('work') or {}).get('form','?')}"
        ok = (got == expected)
        print(f"  {'OK ' if ok else 'FAIL'} {title[:40]:42s} want={expected:7s} got={got:7s} {detail}")
        if not ok:
            print(f"       why this case exists: {why}")
            failures.append(title)

    print()
    if not_run:
        print(f"{not_run} case(s) could not run (API) — inconclusive, not a pass")
    if failures:
        print(f"FAILED {len(failures)}/{len(CASES)}: {failures}")
        return 1
    if not_run:
        return 2
    print(f"ALL TESTS PASSED ({len(CASES)}/{len(CASES)})")
    return 0


if __name__ == '__main__':
    sys.exit(main())
