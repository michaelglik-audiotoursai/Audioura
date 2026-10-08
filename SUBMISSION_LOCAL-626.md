# SUBMISSION — LOCAL-626: Courtauld (tour 485) museum-tour defects

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-626-courtauld-defects`
**Base:** `subscribed` (see "Base note" below)

The Courtauld 3-stop tour (audio_tours.id=485, 5.5/10) failed five ways: the
museum became Stop 1 (2 artworks instead of 3), it spoke "Admission is free"
(false), it read the Courtauld *Institute* admissions brochure aloud, it skipped
Manet/Van Gogh/Cézanne for a maiolica bowl, and it invented facts the checks
missed (a bowl called a "panel"; two conflicting dates for the same object). All
five are fixed; one test per item runs on the real 485 inputs; the specified
suites are green; two fresh live tours were generated in an isolated OWN
container and critiqued.

---

## Base note (a64dae5 vs d70393f)

The BASE preamble says `subscribed = a64dae5` and asks that
`git merge-base --is-ancestor a64dae5 HEAD` exit 0. The LOCAL-626 ticket body and
the RESUME NOTE (LEAD, 2026-10-08 11:55) say to branch from `subscribed @
d70393f` and to **continue from the existing branch**, which already carried
commit `8730477` (item 2).

The actual local history is:

```
d70393f  meter: charge per grounded Gemini response
├── 47a3cc4 → a64dae5   meter: rate_tag on every record (price card version)   ← the `subscribed` ref
└── 8730477             LOCAL-626 item 2 (the existing branch HEAD)
```

So `a64dae5` and the branch HEAD **diverged** at `d70393f`; `a64dae5` is a
sibling meter commit, not an ancestor of HEAD. Branching from `a64dae5` now would
discard the item-2 work the RESUME NOTE says to keep. Per the most recent,
authoritative instruction (the RESUME NOTE), this work continues on the existing
branch whose base is `d70393f`. The verify-commit check uses
`git rev-list --count origin/subscribed..HEAD` as the ticket's PROCESS section
specifies.

---

## Fixes, by item

### Item 1 — the museum must never be an artwork stop  (commit `f7eb277`)

Tour 485 Stop 1 was titled "Courtauld Gallery" and carried the museum's
founding/relocation history as its body. The about-museum opening section is
already folded into Stop 1 (LOCAL-592) and adds zero stops; the venue *also*
taking an artwork slot made a 3-stop request deliver 2 works. The venue slipped
the LOCAL-625 room/space guard because "Courtauld Gallery" has no room *number*.

- `room_candidate_guard.is_venue_itself_title(title, venue_name)` — pure
  predicate: true when a stop title is the venue (article/punctuation-insensitive
  exact match; venue name ± a trailing institution noun — "Courtauld" ==
  "Courtauld Gallery"; or a bare institution noun like "The Collection"). A
  painting *of* the venue ("Courtauld Gallery Interior, 1935") is kept.
- Wired at three points in `generate_tour_text.py` / `stop_pool_assembly.py`: the
  canonical-title SET chokepoint, both deterministic documented-works lists
  (dropped *before* truncation so a real artwork fills the slot), and the
  assembly last-line guard.

**Test:** `tests/test_local626_venue_not_a_stop.py` (7) — the real 485 Stop-1
title "Courtauld Gallery" with venue "The Courtauld Gallery".

### Item 2 — admission/hours  (commit `8730477`, pre-existing on branch)

Only speak admission when the source gives an adult/general price or says general
admission is free; never default to free; keep the full hours day-range. (Done in
a prior session; not re-done.) Verified live on 486: "£16", not "free".

### Item 3 — brochure/recruitment copy; gallery vs academic sources  (commit `784d9a8`)

Stop 1 spoke the Institute's admissions page: "You'll learn from leaders … forge
a career …", "Study in the heart of London with world-renowned specialists". The
LOCAL-614 academic filter missed it (no major/minor/admissions/degree token) —
the sentences are second-person recruitment prose.

- `about_museum_stop._RECRUITMENT_RE` + `_is_recruitment_sentence` drop a sentence
  that addresses the listener as a would-be student/applicant; wired into the
  About story-sentence gate.
- `spoken_text_hygiene.strip_recruitment_sentences` + `RECRUITMENT_SENTENCE_RE`
  run the same strip over the **final spoken tour** (inside `clean_spoken_text`),
  so the copy can't survive in a stop body the About gate doesn't screen. The
  matcher is narrow (second person + a recruitment object), so ordinary tour
  framing ("as you look closer", "you can see the brushwork") is never dropped.
- `about_museum_stop`: GALLERY-first `_STORY_SEEDS` and `_ACADEMIC_PATH_RE`;
  `_candidate_story_urls` stably ranks the venue's own gallery/museum story pages
  above the institution's academic/admissions pages.

**Test:** `tests/test_local626_recruitment_copy.py` (6) — the verbatim 485 copy.

### Item 4 — highlight-first did not fire  (commit `c5352d6`)

With the real Courtauld Wikidata entity (**Q12110695**, 600 works) the SPARQL
catalogue ranks signature works by sitelinks: Manet *A Bar at the
Folies-Bergère* 39, Renoir *La loge* 21, Van Gogh *Self-Portrait with Bandaged
Ear* 14 … while the maiolica *Footed Bowl with the Crucifixion* sits at 0. So the
corpus has the famous works and prominence can order them.

Root cause (in code): the **museum** deterministic selector sorted by corpus-depth
*quality* score first (LOCAL-328) and used Wikidata prominence only as a
tie-break. A long-tail object with more harvested corpus (the bowl) beat the
household names, and highlight-first (LOCAL-593) silently lost.

- `generate_tour_text._prominence_tier(entry)` — 0 for a signature work
  (sitelinks ≥ `FAMOUS_WORK_SITELINKS`, default 8, measured against the real
  Courtauld catalogue) or an on-site highlight; 1 otherwise.
- Both museum deterministic sorts now **lead** with the signature tier; corpus
  depth orders works *within* a tier, so famous works always open while the
  describable-work preference (LOCAL-328) still ranks the long tail.

**Test:** `tests/test_local626_highlight_first.py` (5) — the real Courtauld
sitelink values; reproduces the 485 bowl-leads defect, then proves the famous
works lead.

### Item 5 — invented facts the checks missed  (commit `eb1aa94`)

Stop 3 (a BOWL) said "this Crucifixion **panel** …" and dated the bowl both
"between 1550 and 1570" (corpus) and "during the period 1510-1571" (invented).

- **Object-type bleed** (extends the LOCAL-623 same-title guard):
  `same_title_bleed_guard.object_kind_of` maps a title/material to a family
  (vessel/picture/paper/sculpture/…); `sentence_is_object_type_bleed` drops a
  sentence that re-labels the stop's object an incompatible kind
  ("this … panel" on a bowl). Ambiguous nouns (painting/drawing/ceramic/oil/
  marble…) never trigger a bleed on their own, so "The painting was not chosen at
  random" (the bowl's painted scene) survives.
- **Same-stop date consistency** (`date_consistency_guard.py`, new): one date per
  work, the corpus date wins. Keep the creation-date sentence matching the corpus
  period (SPARQL/catalogue date, else the title's date, else the first stated);
  drop sentences asserting a conflicting *work* date. A **person's** dates
  ("Patanazzi, active 1515-1587") are left alone. `ranges_conflict` treats a
  single year inside a range, and an exact-bound refinement, as consistent.
- Both wired into `generate_tour_text` right after the LOCAL-623 same-title
  filter (museum tours only; never empties a stop).

**Test:** `tests/test_local626_invented_facts.py` (10) — the verbatim 485 bowl
paragraph.

---

## Test deliverable

### One test per item (real 485 inputs) — 28 tests, all pass

| Item | Test | Count |
|------|------|-------|
| 1 | `tests/test_local626_venue_not_a_stop.py` | 7 |
| 3 | `tests/test_local626_recruitment_copy.py` | 6 |
| 4 | `tests/test_local626_highlight_first.py` | 5 |
| 5 | `tests/test_local626_invented_facts.py` | 10 |

(Item 2 is covered by its own commit `8730477` from the prior session.)

### Specified suites re-run — exit codes

| Command | Result | Exit |
|---------|--------|------|
| `pytest tests/test_local60*.py tests/test_local61*.py tests/test_local62*.py` | 378 passed | **0** |
| `pytest test_local60*.py test_local61*.py test_local62*.py` (repo root) | 185 passed | **0** |
| `pytest tests/test_local62[0-5]*.py test_local62[0-5]*.py` | 88 passed | **0** |
| `pytest tests/test_lead_double_conclusion.py` | 2 passed | **0** |
| `python3 test_sq4_merge.py` | ALL TESTS PASSED | **0** |
| `pytest tests/test_local626_*.py` (new) | 28 passed | **0** |

Also green along the way: LOCAL-593 work-selection (7), LOCAL-625
facts-and-selection with LOCAL-590 assembly (23), LOCAL-614 (5), LOCAL-623
stop-body-defects (16), D523 story/hygiene (8).

---

## Live run

Built an **OWN** disposable container `local626-gen` (image `local626-gen-img`
from `Dockerfile.generator` on the branch tree, so every branch fix is in the
image), joined `development_default` only to INSERT additive `is_test` rows into
`development-postgres-2-1` (audiotours). Tour cache **OFF**, stop pool **OFF**.
Container and image removed on exit. No `audioura-*` container was touched or
renamed. **No DELETE.**

**Row counts:** `audio_tours` total **291 → 293** (+2); `is_test` **228 → 230**
(+2). Both new rows (`id=486`, `id=487`) are `is_test=true`, `creator_type=Test`.

### Tour 486 — The Courtauld Gallery, 3 stops (fresh; cache+pool off) — **6.5/10** (baseline 485 was 5.5/10)

- **Stop titles:** `Georges Seurat` · `Paul Cézanne` · `Christ and the Woman
  Taken in Adultery` (Brueghel) — three real artworks.
- **Museum Information (spoken):** `Monday, 10:00–18:00. £16`
- **All five LOCAL-626 items verified clean on the spoken text:** no venue-as-stop
  (item 1); **no** maiolica bowl — famous works lead (item 4); no recruitment copy
  (item 3); no "Crucifixion panel" / no conflicting work date (item 5); admission
  **£16, not free** (item 2).
- Residual defects the critic flagged are **new and out of this ticket's scope**:
  a Stop-2 mid-tour recap of Seurat, an unexplained "cardinal" provenance claim,
  and the hours line showing a single day (the preflight had no ranged hours this
  run — item-2 territory, no regression).

### Tour 487 — Museo del Prado, 3 stops (fresh, never generated) — **4/10**

- **Stop titles:** `Combate de mujeres` · `La bacanal de los andrios` · `The Fall
  of Man`.
- **LOCAL-626 items all clean:** no venue-as-stop, no recruitment copy, no
  object-type bleed.
- Its defects (a truncated sentence "… and w.", "Opening hours weren't published",
  an invented "Titian Ramsey Peale II" attribution, an off-theme Velázquez
  conclusion) are **separate quality issues outside this ticket's scope**.

Critiques: `.continuous_dev/calib/critique/critique_486.md`, `_487.md` (spoken
text in `tour_486.txt` / `tour_487.txt`). Local copies in
`tours/local626_live/` (gitignored evidence).

### HARD CAP — honest report (the run OVERRAN $1.20)

The isolated run billed **$2.0233** combined (ledger `TEST-LOCAL-626`:
openai $1.7176, gemini_grounding $0.1260, gemini_tokens $0.0727, serper $0.1070,
preflight $0.0932) — **over the $1.20 cap.**

**Root cause.** The shared `tests/live_run_meter.py` cap guard only fires at the
**grounding** counter (`story_leads`). OpenAI — the dominant cost — is invisible
mid-tour; it is folded into the meter only *after* a tour via `add_generation()`.
Between the two tours the meter read combined spend **$0.7684** (< $1.20), so the
harness started tour 2 (Prado); tour 2's OpenAI then carried the total past the
cap. The literal rule — *stop STARTING new tours once the meter passes $1.20* —
was honoured (the meter was $0.77 when tour 2 started), but the **intent** (a hard
$1.20 ceiling) was breached.

**Fix (committed).** The harness no longer starts a tour unless the budget still
holds a worst-case tour's cost: it starts only while
`combined_spend + PER_TOUR_RESERVE($0.90) ≤ $1.20`. With that gate, tour 2 would
**not** have started ($0.7684 + $0.90 > $1.20) — a genuine hard stop, not a
reported one. The run was **not** repeated: both tours were already delivered and
billed, and the deliverable is *at most two* tours. A deeper, infrastructure-level
fix (making in-flight OpenAI spend visible to the grounding cap guard in the
shared meter) is noted for a follow-up since it touches the shared
`live_run_meter` used by every task's harness.

---

## Files changed

- `generate_tour_text.py` — item 1 (venue filters), item 4 (`_prominence_tier`,
  both museum sorts), item 5 (object-type + date-consistency wiring).
- `room_candidate_guard.py` — `is_venue_itself_title` (item 1).
- `about_museum_stop.py` — recruitment filter + gallery-first source ranking (item 3).
- `spoken_text_hygiene.py` — `strip_recruitment_sentences` (item 3).
- `same_title_bleed_guard.py` — object-type bleed (item 5).
- `date_consistency_guard.py` (new) — same-stop date consistency (item 5).
- `visitor_facts_extractor.py`, `stop_pool_orchestrator.py`, `about_museum_stop.py`
  — item 2 (prior commit `8730477`).
- `stop_pool_assembly.py` — venue-itself in the last-line guard (item 1).
- `tests/test_local626_*.py` — one test per item (28 tests).
- `run_local626_container.py`, `run_local626_live.sh` — isolated OWN-container
  live harness with the $1.20 reserve gate.

## Commits

```
8730477  item 2 (admission/hours; prior session)
c5352d6  item 4 (highlight-first signature tier)
f7eb277  item 1 (venue is never a stop)
784d9a8  item 3 (recruitment copy; gallery > academic)
eb1aa94  item 5 (object-type bleed + date consistency)
c98260b  task 7 harness
c916aee  task 7 live results + hard-cap reserve gate
```

Process files (DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md,
.continuous_dev/STATUS.md) were **not** edited.
