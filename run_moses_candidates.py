#!/usr/bin/env python3
"""run_moses_candidates.py — every Moses candidate, with its text and its verdict.

Michael, 2026-08-23: *"display all stories for Moses and Monotheism coming from
Gemini and the validator rejections of each."*

They were not on disk. The production loop printed one summary line per candidate
and kept the story text in a dict that died with the process — so this replays
stop 3 alone under production conditions and D514 writes every candidate out.

D512's verb discovery lives in `generate_tour_text`, not in the loop, so it is
installed here explicitly; without it `material_kind` scores with the narrower
hardcoded verb list and the `eventful` verdicts would not be the ones production
produced.
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

for line in open(os.path.join(HERE, '.env')):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

os.environ['STORIED_MODE'] = 'true'
os.environ['STORY_LOOP_ENABLED'] = '1'
os.environ.setdefault('DATABASE_URL',
                      'postgresql://admin:password123@localhost:5433/audiotours')
os.environ['STORY_LOOP_CANDIDATE_LOG'] = os.path.join(
    HERE, f"MOSES_CANDIDATES_{time.strftime('%Y%m%d_%H%M')}.jsonl")

# How many credit_lines to try. Production caps at 4 (D513a); this is also the
# cheapest way to answer whether that cap is the ceiling, so it is exposed.
os.environ.setdefault('STORY_LOOP_MAX_CREDIT_LINES',
                      os.environ.get('MOSES_MAX', '4'))

EXHIBITION = 'Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA'

# Stop 3 exactly as delivered by TOUR_LOOP_20260823_1253.txt — the loop mines its
# credit_lines from the stop's own post-gate prose, so this must be that prose.
STOP_TEXT = (
    "In 1974, Salvador Dalí crafted a series of illustrations for Sigmund Freud's "
    "challenging text \"Moses and Monotheism.\" Freud, the author, proposed a "
    "controversial hypothesis suggesting Moses was an Egyptian priest of Akhenaten, "
    "bringing a fresh perspective to biblical narratives. This synthesis of Dalí's "
    "surrealist imagery with Freud's psychoanalytic theories exemplifies the "
    "exhibition's thesis that collaborative artistic and literary efforts can "
    "transform a book into an art form of its own. Each illustration Dalí created "
    "magnifies Freud's provocative ideas, highlighting the potency of image and text "
    "when melded in such a revolutionary manner. This exhibit not only showcases "
    "Dalí's artistic prowess but also reflects how artists and authors of the time "
    "came together to challenge traditional narratives and redefine the book as a "
    "visual and intellectual canvas.")

MATRIX = {
    'canonical_title': 'Moses and Monotheism',
    'english_title': 'Moses and Monotheism',
    'artist': 'Salvador Dalí',
    'publisher': '',
    'printed_by': '',
    'printer': '',
    'collaborator': '',
    'credit_line': '',
    'medium': 'illustrated book, etching and lithography',
    'venue_name': 'Museum of Fine Arts, Boston',
}

try:
    from domain_verbs import install
    install(venue_name='Museum of Fine Arts, Boston', exhibition=EXHIBITION,
            category='museum', medium=MATRIX['medium'])
except Exception as e:
    print(f"[D512] verb discovery skipped: {e}")

from story_production_loop import run_for_stop   # noqa: E402

print(f"cap : {os.environ['STORY_LOOP_MAX_CREDIT_LINES']} credit_line(s)")
print(f"out : {os.path.basename(os.environ['STORY_LOOP_CANDIDATE_LOG'])}\n")

res = run_for_stop(MATRIX, STOP_TEXT, exhibition=EXHIBITION,
                   venue_url='https://www.mfa.org',
                   extra_entities=['Salvador Dalí', 'Sigmund Freud'])

print(f"\n{'=' * 70}")
print(f"{len(res['candidates'])} candidate(s) captured, "
      f"{'ACCEPTED' if res['story'] else 'none passed'}, ~${res['cost_usd']:.3f}")
print(f"{'=' * 70}")
