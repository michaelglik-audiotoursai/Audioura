"""MFA Unbound, 3 stops — real pipeline, with ONLY the blocked page fetch stubbed.

Why this exists (LEAD, 2026-08-11 23:1x):

`find_exhibition_checklist` cannot reach the exhibition page. The URL is not the
problem — a Serper search returns `https://www.mfa.org/exhibition/picasso-miro-dali-unbound`
as the FIRST organic hit. The problem is that mfa.org is currently answering
**HTTP 429** to every request, so `_fetch_page` returns 0 chars, the checklist
returns `path=fallback, works=0`, and the tour fails with `tier: unresolvable`.

This script substitutes ONE thing: the bytes of that page, captured earlier from
the live site and committed at `tests/fixtures/mfa_unbound_page_text.txt`. Those
bytes then go through the REAL `prose_llm_extract_works`, and everything
downstream — ranking, D1v2 verification, the gpt-4o story pass (D370), the story
gate, the verifier — is the untouched production pipeline.

**This is not proof that the pipeline can find the exhibition.** It is proof of
what the tour reads like once it has the right three works. LOCAL-425 owns the
real discovery fix (search-first URL resolution + 429 backoff).

No production file is modified. The patch is applied here, at runtime.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import exhibition_checklist
from exhibition_checklist import ExhibitionChecklistResult, prose_llm_extract_works

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "tests", "fixtures", "mfa_unbound_page_text.txt")
PAGE_URL = "https://www.mfa.org/exhibition/picasso-miro-dali-unbound"
LOCATION = "Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA"
STOPS = 3

_real_find = exhibition_checklist.find_exhibition_checklist


def _pinned_find(venue_base_url, exhibition_name, venue_name='', venue_language='en'):
    """Try the real lookup first; fall back to the captured page only if it fails."""
    try:
        res = _real_find(venue_base_url, exhibition_name, venue_name, venue_language)
        if res and res.works:
            print(f"  [PINNED] real lookup succeeded ({len(res.works)} works) — fixture NOT used")
            return res
        print(f"  [PINNED] real lookup returned path={res.path}, works=0 — using captured page")
    except Exception as e:
        print(f"  [PINNED] real lookup raised {e!r} — using captured page")

    page_text = open(FIXTURE, encoding="utf-8").read()
    works = prose_llm_extract_works(page_text, "Picasso, Miró, Dalí: Unbound")
    print(f"  [PINNED] prose extraction from captured page: {len(works)} works")
    for w in works:
        print(f"    - {w.get('title')} | {w.get('artist')} | {w.get('date')}")

    res = ExhibitionChecklistResult()
    res.works = works
    res.path = 'prose_llm'
    res.page_shape = 'prose_llm_extraction'
    res.exhibition_url = PAGE_URL
    res.page_text = page_text
    res.reason = (f'PINNED: {len(works)} works from captured page bytes '
                  f'({PAGE_URL} returns HTTP 429 live)')
    return res


exhibition_checklist.find_exhibition_checklist = _pinned_find

from generate_tour_text import generate_tour_text as gen_tour

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "TOUR_MFA_UNBOUND_3STOP.txt")

print("=" * 72)
print("  MFA UNBOUND — 3 stops, real pipeline, page fetch pinned to captured bytes")
print(f"  location    : {LOCATION}")
print(f"  story model : {os.environ.get('TOUR_STORY_MODEL', 'gpt-4o (D370 default)')}")
print("=" * 72)

tour_text, output_file, coords = gen_tour(
    LOCATION,
    "contained",
    out,
    total_stops=STOPS,
    persona=None,
    user_id="mfa_unbound_pinned",
    job_id="mfa_unbound_pinned",
)

if not tour_text:
    print("FAILED: no text generated")
    sys.exit(1)

stops = [ln for ln in tour_text.splitlines() if ln.startswith("Stop ")]
print(f"\nSTOPS: {len(stops)}")
for s in stops:
    print("  ", s)
print(f"CHARS: {len(tour_text)}  WORDS: {len(tour_text.split())}")
print(f"SAVED: {out}")
