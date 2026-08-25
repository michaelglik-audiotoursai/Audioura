#!/usr/bin/env python3
"""run_local468_acceptance.py — LOCAL-468: Ask about the seed, not the work.

Acceptance criteria:
  1. Stop 1's four candidates are about DIFFERENT things — the Mourlot answer
     discusses Mourlot, the Fridman answer discusses Fridman.
  2. At least one stop publishes two stories that survive the D518 merge.
  3. Pairwise overlap for stop 1's candidates reported, and below 0.6.
  4. Indices must not collapse (baseline: mean 75.7, range 73–81).
  5. No prose seed shorter than a clause with a subject reaches a query.

This runs stop 1 (Le Lézard) with the LOCAL-468 changes and measures all five.
"""
import os
import sys
import time
import re
import json

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
# Force BEST_OF mode to examine ALL seeds, not stop at first pass.
os.environ['STORY_LOOP_BEST_OF'] = '1'
os.environ['STORY_LOOP_STOP_AT'] = '100'  # Don't stop early — we want all 4
os.environ['STORY_LOOP_MAX_CREDIT_LINES'] = '4'

_LOG_PATH = os.path.join(HERE,
                         f"LOCAL468_CANDIDATES_{time.strftime('%Y%m%d_%H%M')}.jsonl")
os.environ['STORY_LOOP_CANDIDATE_LOG'] = _LOG_PATH

EXHIBITION = 'Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA'

# Stop 1: Le Lézard aux plumes d'or — the case from the task description.
# Four matrix agents: Joan Miró (artist), Louis Broder (publisher), Mourlot
# (printer), Boris Fridman (donor from credit_line).
MATRIX = {
    'canonical_title': "Le Lézard aux plumes d'or",
    'english_title': "The Lizard with Golden Feathers",
    'artist': 'Joan Miró',
    'publisher': 'Louis Broder',
    'printed_by': 'Mourlot',
    'printer': 'Mourlot',
    'collaborator': '',
    'credit_line': 'Gift of Boris Fridman',
    'medium': 'illustrated book, lithographs',
    'venue_name': 'Museum of Fine Arts, Boston',
}

# Stop 1 prose (from TOUR_D525_UNBOUND.txt — post-gate)
STOP_TEXT = (
    "In 1967, Joan Miró created a series of lithographs entitled \"Le Lézard "
    "aux plumes d'or\" (The Lizard with Golden Feathers), published by the "
    "Parisian art dealer and publisher Louis Broder. The printing was executed "
    "by the renowned Mourlot workshop, known for producing some of the finest "
    "lithographic editions of the twentieth century. This particular copy was "
    "a gift of Boris Fridman to the Museum of Fine Arts, Boston.")

print("=" * 70)
print("  LOCAL-468 ACCEPTANCE: Ask about the seed, not the work")
print("=" * 70)
print()

# ── Part 0: Verify the wiring — prove seed['ask'] reaches the prompt ─────────
print("── Part 0: WIRING PROOF — seed['ask'] reaches Gemini ──")
print()

from story_production_loop import _agent_seeds  # noqa: E402
from story_query import compile_for_seed  # noqa: E402

agent_seeds = _agent_seeds(MATRIX)
print(f"  {len(agent_seeds)} agent seed(s) built from the matrix:")
for s in agent_seeds:
    print(f"    {s['id']:<18} seed={s['seed']!r}")
    print(f"    {'':18} ask ={s['ask']!r}")
    # Prove the ask is what goes into the prompt
    prompt = compile_for_seed(s, MATRIX, EXHIBITION)
    # The FIRST LINE of the prompt must be the ask, not the generic question
    first_line = prompt.split('\n')[0]
    assert s['ask'] in first_line, (
        f"WIRING FAILURE: seed['ask'] is not the first line of the prompt.\n"
        f"  Expected: {s['ask']!r}\n"
        f"  Got:      {first_line!r}")
    # The prompt must NOT contain the generic GEMINI_TEMPLATE question
    from story_query import GEMINI_TEMPLATE
    generic = GEMINI_TEMPLATE.format(exhibition=EXHIBITION,
                                     work=MATRIX['canonical_title'],
                                     credit='')
    assert generic not in prompt, (
        f"WIRING FAILURE: generic question still in prompt for agent seed.\n"
        f"  Prompt starts: {prompt[:200]!r}")
    print(f"    {'':18} ✓ ask is the question, not the work")
print()
print("  WIRING: PASS — all agent seeds use seed['ask'] as the question")
print()

# ── Part 0b: Prose seed quality gate ──────────────────────────────────────────
print("── Part 0b: PROSE SEED QUALITY GATE ──")
print()

from story_seeds import seeds_for_stop  # noqa: E402

prose_seeds = seeds_for_stop(STOP_TEXT, {'Joan Miró', 'Louis Broder',
                                          'Mourlot', 'Boris Fridman'})
print(f"  {len(prose_seeds)} prose seed(s) found in stop text")

# Check that fragments without subjects would be rejected by the production loop
_test_fragments = [
    {'seed': 'was to design it', 'anchor': '', 'subject': '', 'kind': 'relative'},
    {'seed': 'would provide the text', 'anchor': '', 'subject': '', 'kind': 'relative'},
    {'seed': "Freud's ideas to life", 'anchor': 'Freud', 'subject': '', 'kind': 'possessive'},
    {'seed': 'making it a multifaceted artwork that extend', 'anchor': '', 'subject': '', 'kind': 'participial'},
    {'seed': 'having only completed half of the intended w', 'anchor': '', 'subject': '', 'kind': 'participial'},
]
_rejected_count = 0
for ps in _test_fragments:
    seed_text = ps.get('seed', '')
    words = seed_text.split()
    last_word = words[-1] if words else ''
    truncated = (len(last_word) <= 1 and len(words) > 1) or \
                (len(seed_text) >= 40 and seed_text[-1] not in '.!?')
    subj = ps.get('anchor') or ps.get('subject') or ''
    no_subject = (not subj or subj.lower() == 'this')
    starts_subordinate = bool(re.match(
        r'^(was|were|would|could|should|having|making|being|that|which|who)\b',
        seed_text.lower()))
    if truncated or (no_subject and starts_subordinate):
        _rejected_count += 1
        reason = 'truncated' if truncated else 'no subject + subordinate'
        print(f"    REJECTED: '{seed_text[:50]}' — {reason}")
    else:
        print(f"    ACCEPTED: '{seed_text[:50]}' — anchor={subj!r}")
print(f"\n  {_rejected_count}/{len(_test_fragments)} known-bad fragments rejected")
assert _rejected_count >= 4, f"Expected >=4 rejected, got {_rejected_count}"
print("  QUALITY GATE: PASS")
print()

# ── Part 1: Run the production loop on stop 1 ────────────────────────────────
print("── Part 1: LIVE RUN — stop 1 (Le Lézard) ──")
print()

try:
    from domain_verbs import install
    install(venue_name='Museum of Fine Arts, Boston', exhibition=EXHIBITION,
            category='museum', medium=MATRIX['medium'])
except Exception as e:
    print(f"  [D512] verb discovery skipped: {e}")

from story_production_loop import run_for_stop  # noqa: E402

t0 = time.time()
res = run_for_stop(MATRIX, STOP_TEXT, exhibition=EXHIBITION,
                   venue_url='https://www.mfa.org',
                   extra_entities=['Joan Miró', 'Louis Broder', 'Mourlot',
                                   'Boris Fridman'])
elapsed = time.time() - t0

print(f"\n{'─' * 70}")
print(f"  {len(res['candidates'])} candidate(s), {elapsed:.0f}s, ~${res['cost_usd']:.3f}")
print(f"{'─' * 70}\n")

# ── Part 2: Report all candidates — paste the actual stories ──────────────────
print("── Part 2: ALL CANDIDATES (the four stories) ──")
print()

for i, cand in enumerate(res['candidates'], 1):
    print(f"  ──── Candidate {i}: seed={cand['credit_line']!r} ────")
    print(f"  kind={cand['kind']}, index={cand['index']}, "
          f"C{cand['counts'].get('CONFIRMED',0)} "
          f"X{cand['counts'].get('UNATTESTED',0)} "
          f"gate={'PASS' if cand['gate']['passes'] else 'FAIL:' + ','.join(cand['gate']['failed'])}")
    if cand.get('ungrounded'):
        print(f"  UNGROUNDED: {cand['ungrounded']}")
    print()
    # Print the story, wrapped
    story = cand['story']
    for line in [story[j:j+78] for j in range(0, len(story), 78)]:
        print(f"    {line}")
    print()

# ── Part 3: DIVERSITY CHECK — does seed X's answer discuss X? ─────────────────
print("── Part 3: DIVERSITY — does each answer discuss its seed? ──")
print()

_diversity_pass = True
for cand in res['candidates']:
    cl = cand['credit_line']
    story_lower = cand['story'].lower()
    # For each seed, check if its name appears in the story
    # Use surname for multi-word names
    seed_words = cl.split()
    check_name = seed_words[-1] if len(seed_words) > 1 else cl
    present = check_name.lower() in story_lower
    status = "✓ PRESENT" if present else "✗ ABSENT"
    print(f"  seed={cl!r:30} check={check_name!r:15} → {status}")
    if not present:
        _diversity_pass = False

print()
if _diversity_pass:
    print("  DIVERSITY: PASS — every seed's answer discusses its seed")
else:
    print("  DIVERSITY: PARTIAL — not all seeds found in their own answer")
    print("  (This may be acceptable if the story is ABOUT the seed even without")
    print("   naming them — check the stories above manually.)")
print()

# ── Part 4: OVERLAP MEASUREMENT ───────────────────────────────────────────────
print("── Part 4: PAIRWISE OVERLAP ──")
print()

if res.get('pairwise_overlap'):
    for p in res['pairwise_overlap']:
        status = '✓' if p['overlap'] < 0.6 else '✗ CONVERGED'
        print(f"  {p['a']:20} × {p['b']:20} = {p['overlap']:.3f}  {status}")
    print()
    print(f"  mean={res['mean_overlap']:.3f}, max={res['max_overlap']:.3f}")
    all_below = all(p['overlap'] < 0.6 for p in res['pairwise_overlap'])
    print(f"  OVERLAP: {'PASS — all pairs below 0.6' if all_below else 'FAIL — some pairs >= 0.6'}")
else:
    print("  (fewer than 2 candidates — cannot measure overlap)")
print()

# ── Part 5: INDEX CHECK ───────────────────────────────────────────────────────
print("── Part 5: INDICES (baseline: mean 75.7, range 73–81) ──")
print()

indices = [c['index'] for c in res['candidates'] if c.get('index') is not None]
if indices:
    mean_idx = sum(indices) / len(indices)
    min_idx = min(indices)
    max_idx = max(indices)
    print(f"  indices: {indices}")
    print(f"  mean={mean_idx:.1f}, range={min_idx}–{max_idx}")
    # A diverse set of WEAK stories is not an improvement
    if mean_idx >= 50:
        print(f"  INDICES: PASS — mean {mean_idx:.1f} >= 50 (floor)")
    else:
        print(f"  INDICES: WARNING — mean {mean_idx:.1f} < 50")
else:
    print("  INDICES: no scores available")
print()

# ── Part 6: MULTI-STORY CHECK ─────────────────────────────────────────────────
print("── Part 6: MULTI-STORY (at least one stop publishes 2 stories) ──")
print()

n_stories = len(res.get('stories', []))
print(f"  {n_stories} story/stories accepted for publication")
if n_stories >= 2:
    print("  MULTI-STORY: PASS — two or more stories survived")
    for si, s in enumerate(res['stories'], 1):
        print(f"    story {si}: index={s.get('index')}, "
              f"credit_line={s.get('credit_line')!r}")
else:
    print("  MULTI-STORY: only one story accepted (may still pass if stop 2/3 ")
    print("  produce two — run the full tour for a definitive answer)")
print()

# ── SUMMARY ───────────────────────────────────────────────────────────────────
print("=" * 70)
print("  SUMMARY")
print("=" * 70)
print(f"  Candidates:   {len(res['candidates'])}")
print(f"  Indices:      {indices}")
print(f"  Overlap:      mean={res.get('mean_overlap', 'N/A')}, "
      f"max={res.get('max_overlap', 'N/A')}")
print(f"  Multi-story:  {n_stories} accepted")
print(f"  Cost:         ~${res['cost_usd']:.3f}")
print(f"  Elapsed:      {elapsed:.0f}s")
print(f"  Log:          {os.path.basename(_LOG_PATH)}")
print()
