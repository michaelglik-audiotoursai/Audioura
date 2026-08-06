**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-290
**Base:** storied
**Branch:** kiro/local290-stop-loss

# We drop real Riviera places because we have not scraped them yet.

Read `DECISIONS.md` **D162** (the standing rule this violates), D187, D170,
`stop_existence_gate.py`, `generate_tour_text.py` (PHASE 3A selection, the
`[LOCAL-245]` gate, R4 replenishment / UNIFIED-FILL).

## ⚠️ NO container rebuilds (D48). Ceiling **$1.50**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.
LOCAL-289 is in `unglossed_reference_gate.py`; stay out of it.

## The evidence

An 8-stop French Riviera request, logged tonight:

```
[verify_landmarks] 0/7 stops verified against 28 discovered landmarks (tier: rich)
[EXISTENCE-GATE] ENFORCE — 5/7 stops verified (71%), dropping 2 unverified
   [VERIFIED]   'Saint-Jean-Cap-Ferrat' — stop_corpus(geographic): 'Cap Ferrat'
   [UNVERIFIED] 'Old Town of Menton'    — no evidence
   [UNVERIFIED] "Corniche d'Or"         — no evidence
[LOCAL-245] EXISTENCE-GATE ENFORCE: dropped 2 unverified stop(s), 5 remain (requested 8)
[LOCAL-245] EXISTENCE-GATE: delivering SHORT tour — 5/8 stops
```

Michael, told the tours were losing stops:

> *"Somehow I did not see any and neither can I imagine not having enough stops
> over the path as long."*

**He is right.** The Riviera does not run out of places. Three separate faults
produce a 5-stop tour from an 8-stop request:

### Fault 1 — the selector proposed 7 for a request of 8

Before any verification, one stop is already missing. Find out why PHASE 3A
returns fewer candidates than requested and make it return at least N, ideally
N plus a margin, so the gate has something to work with.

### Fault 2 — "verified" means "present in our own corpus"

Every VERIFIED line resolves against `stop_corpus`. Old Town of Menton and the
Corniche d'Or are real, well-documented places that fail because **we have not
scraped them**, not because they do not exist.

**This is D162 automated.** That decision was written after LEAD spent eight days
treating "a general web search does not show it" as proof of absence, and
deleted genuine corpus over it. The standing rule is: *before calling something
non-existent, check the source that would actually know.* A corpus lookup is not
that source.

**Fix:** when a stop fails the corpus lookup, fall through to a real existence
check — Wikipedia/Wikidata by name, the same tier-1 path the museum branch
already uses — before declaring it unverified. Only drop a stop that fails
*that*. A fabricated place must still fail; the bar is evidence, not our
scraping backlog.

### Fault 3 — 28 landmarks discovered, 0 matched

`verify_landmarks` reports `0/7 stops verified against 28 discovered landmarks`.
Twenty-eight real landmarks were retrieved and not one matched a proposed stop.
That is a **name-normalisation failure**, the D187 pattern — corpus existed under
"Old Town of Antibes" while the selector drew "Old Town Antibes". Note this
task's own example: *"Old Town **of** Menton"*.

Apply the normalised matching LOCAL-277 added, on both sides, before concluding
no match. Report the match rate before and after.

### Fault 4 — nothing backfills

Having dropped 2 stops, the pipeline delivers 5 rather than replenishing to 8.
R4 replenishment exists (LOCAL-19 made it actually run). Find out why it does not
fire here, and make a short tour trigger a refill before delivery.

## Why this matters more than it looks

N is the denominator of the whole rubric and every undelivered stop scores
**−1.0 × share**. An 8-request delivering 5 loses **37.5 points** before a single
sentence is judged — larger than any prose-quality term in the index. Six tours
in the corpus currently score *negative* for this reason alone.

## The line you must not cross

**Do not weaken the gate into a rubber stamp.** LOCAL-281 established that a
fabricated name must fail and that Le Chantecler in *Lyon* must fail the
proximity check. Those must still fail. The change is *adding a real
existence check before rejecting*, not removing the rejection.

**Do not backfill with junk.** A replenished stop goes through the same
verification as an original. Better a 7-stop tour of real places than an 8-stop
tour with an invented one.

**D170 still binds:** selection stays free. Do not narrow toward stops we have
corpus for — that is precisely the disease being treated here.

## Verification required

Run **three 8-stop** and **two 2-stop** Riviera tours. Report for each:

- stops requested / proposed by the selector / verified / delivered;
- every UNVERIFIED stop with the reason, and whether the tier-1 fallback then
  confirmed it;
- the `verify_landmarks` match rate before and after the normalisation fix;
- whether replenishment fired, and what it added.

**A run that still delivers short must say so plainly** with the reason. Partial
progress honestly reported is acceptable; a silent short tour is not.

Copy all tours to `/Users/micha/Audioura/tours/`.

## Traps

- **Cleanup rule (D141):** delete only rows this run created, by an id captured
  at creation, and only after `SELECT is_test` on that id returns `true`.
  `audio_tours` before and after; Nice list `[1,12,14,17,24,29,152]`.
- Tests run against `audiotours_test` (D148).
- **Run every example you paste and confirm the output matches** (D97, D103).
- Judge protected-file changes from `git merge-base`, never `storied..HEAD` (D147).
- Read every delivered tour as prose (D161).
- **D186:** the spine stays on gpt-4o.

## Acceptance criteria

- A real place absent from `stop_corpus` is no longer dropped as "no evidence".
- A fabricated place still fails; the Lyon proximity case still fails.
- Selector proposes at least N candidates.
- `verify_landmarks` match rate materially improved; before/after reported.
- Replenishment fires on a short tour.
- 8-stop requests deliver 8, or the shortfall is explained per stop.
- `git status --short` clean. No container rebuilt.

## PROCESS

Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-290.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
