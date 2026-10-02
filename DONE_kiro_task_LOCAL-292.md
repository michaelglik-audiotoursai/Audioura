**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-292
**Base:** storied
**Branch:** kiro/local292-empty-stop

# A stop whose description fails to generate ships as an empty shell.

Read `DECISIONS.md` D161, `generate_tour_text.py` — the `[LOCAL-251]`
post-assembly gate that strips `[GENERATION_FAILED:<stop>]`, and the Phase 5
description-generation retry path.

## ⚠️ NO container rebuilds (D48). Ceiling **$1.00**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.
**LOCAL-289 is in `unglossed_reference_gate.py` and LOCAL-290 is in the
selection/existence path — stay out of both.** Your change is the failure
handling around description generation and the post-assembly gate.

## The evidence

A 2-stop Riviera tour generated tonight on merged `storied`, delivered to
`tours/`:

```
Stop 2: Eze Village

Address: 06360 Èze, France
Coordinates: 43.7272, 7.3619
Type/Specialty: Medieval Village
Specific Examples: Narrow cobblestone streets, medieval architecture, ...

Orientation: Position yourself to best view this location.

Musée Matisse (Nice) is 7 kilometers from here — we can build a cycling tour...
```

**There is no narration. The stop is a header, an address, a generic orientation
fallback, and then the tour ends.** Half of a 2-stop tour.

The log says exactly what happened:

```
[LOCAL-47] Eze Village: tier=rich, facts=8
[CORPUS-GATE] stop='Eze Village' verdict=COVERED action=PASSED
Generating description for Stop 2: Eze Village by , ...
...
STRIPPING: [GENERATION_FAILED:Eze Village]
[LOCAL-280] Recap: fewer than 2 delivered stops — skipped
```

Note the sequence. The stop had **8 facts of rich corpus**. Generation failed
anyway. The post-assembly gate stripped the failure marker — and stripping the
marker **removed the evidence while leaving the empty stop in the tour**. The
recap then correctly detected that only one stop had content and suppressed
itself, so the tour also lost its conclusion.

Measured across `tours/`: **13 of 1 782 stops (0.7%)** have a title and fewer
than 15 words of body. Low in aggregate; catastrophic on a 2-stop tour, which is
the shape Michael reads most.

## Scope

### 1. Retry a failed description before giving up

Generation failed on a stop with rich corpus, which suggests a transient fault
rather than missing material. Retry at least once — the prolog path already has
`_PROLOG_MAX_RETRIES` (LOCAL-119); follow that pattern rather than inventing a
new one. Log the attempt count.

### 2. Never ship an empty stop

If a description is still missing after retry, the stop must **not** appear in
the delivered tour. Remove it entirely — header, address, coordinates,
orientation, all of it — and deliver a shorter tour with an honest stop count.

**A stop with an address and no narration is worse than a missing stop.** The
listener is told to stand somewhere and then told nothing.

### 3. Stripping the marker must not hide the failure

`[LOCAL-251]` strips `[GENERATION_FAILED:X]` from the output, which is right for
the *text* but currently the only trace. After stripping, the pipeline must:

- log the failure at the same prominence as an existence-gate drop;
- record it in the run's summary counts (requested / generated / failed /
  delivered), so a short tour is explained rather than silent.

### 4. The stop count must tell the truth

The tour header and any stop-count field must reflect stops **with narration**,
not stops proposed. If a stop is removed under (2), the count follows it.

## The line you must not cross

**Do not paper over the gap with generated filler.** If we cannot say anything
sourced about a stop, the answer is to drop the stop, never to emit a paragraph
of scenery to fill the hole. That is the fabrication this whole programme exists
to prevent.

**Do not suppress the recap as the fix.** The recap suppressing itself was a
*symptom* — it correctly noticed only one stop had content. Once empty stops are
removed, a 2-stop request that delivers 1 real stop should produce a
single-stop tour with a coherent closing, not a silent one.

## Verification

Run **five 2-stop** and **two 8-stop** Riviera tours — enough to hit the failure
at least once given the measured rate. Report for each:

- stops requested / generated / failed / delivered;
- whether a retry fired and whether it succeeded;
- confirmation that no delivered stop has a header without narration;
- the closing, verbatim, on any tour that lost a stop.

Then re-run the corpus scan and report the empty-stop count against the current
baseline of **13 / 1 782**.

Copy all tours to `/Users/micha/Audioura/tours/`.

## Traps

- **Cleanup rule (D141):** delete only rows this run created, by an id captured
  at creation, and only after `SELECT is_test` on that id returns `true`.
  `audio_tours` before and after; Nice list `[1,12,14,17,24,29,152]`.
- Tests run against `audiotours_test` (D148).
- **Run every example you paste and confirm the output matches** (D97, D103).
- Judge protected-file changes from `git merge-base`, never `storied..HEAD` (D147).
- **Read every delivered tour as prose (D161).** This defect was invisible in
  every metric — word count, stop count and cost all looked plausible. It was
  found by reading the file.
- **D186:** the spine stays on gpt-4o.

## Acceptance criteria

- A failed description is retried at least once, with the attempt logged.
- No delivered tour contains a stop header without narration.
- A stop removed for failed generation is removed completely, and the stop count
  follows.
- The failure is logged and counted after the marker is stripped.
- No filler is generated to fill a gap.
- Empty-stop count reported against the 13 / 1 782 baseline.
- `git status --short` clean. No container rebuilt.

## PROCESS

Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-292.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.

---

# ⚠️ RESUMING — a previous session stalled. Read this before starting.

**LEAD, 2026-08-06 00:41.** The first attempt ran for 58 minutes, wrote code, and
then hung — 0% CPU, no file activity for 15+ minutes, nothing committed. Killed
and re-dispatched.

**Your worktree already contains ~91 uncommitted lines** in
`generate_tour_text.py`, tagged `[LOCAL-292]`. It implements **scope item 1
(retry)** and looks sound on inspection: transient HTTP codes {429,500,502,503,
504} with exponential backoff, a non-transient retry-once path, and
Timeout/ConnectionError handling — following the LOCAL-119 `_PROLOG_MAX_RETRIES`
pattern the task asked for.

**Do not start over.** Run `git diff` first, keep what is good, and continue with
scope items 2–4, which are untouched:

- **2.** never ship an empty stop — remove it entirely, header and all;
- **3.** stripping `[GENERATION_FAILED:X]` must still log and count the failure;
- **4.** the stop count must reflect stops with narration.

**On the stall itself:** the likely cause is a bare `requests` call or a
`time.sleep` in a retry loop with no ceiling. Whatever you add, give every
network call an explicit timeout and cap total retry wait. **Do not add an
unbounded sleep.** If a generation cannot complete, fail fast and let scope
item 2 drop the stop — that is the whole point of the task.

Commit early so a second stall does not cost the work again.
