**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-293
**Base:** storied
**Branch:** kiro/local293-landmark-extraction

# Wikipedia section headings are being registered as landmarks.

Read `DECISIONS.md` D187, `SUBMISSION_LOCAL-290.md` (which found this and left
it open, correctly), `area_resolver.py` — `discover_landmarks()` and
`_wikipedia_landmark_extraction()`.

## ⚠️ NO container rebuilds (D48). Ceiling **$1.00**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.
LOCAL-292 is in the description-generation/post-assembly path. Stay out of it.

## The defect

LOCAL-290 fixed the existence gate and reported honestly that
`verify_landmarks` still matches **0 of 28** discovered landmarks. They
attributed it to the landmark cache holding article section headings rather than
place names, and said their matching code was not the cause. **They were right.**
`_wikipedia_landmark_extraction()` contains this:

```python
# Extract from section headers (== Name ==)
sections = re.findall(r'^==+\s*(.+?)\s*==+', text, re.MULTILINE)
...
for section in sections:
    ...
    landmarks.append(Landmark(name=section))
```

Every `== Heading ==` in the area's Wikipedia article becomes a `Landmark`. That
is how "Canton of Sainte-Maxime" and "Origin of term" entered the cache. The
existing filter rejects a `generic` list, anything under 4 or over 60
characters, "list of…", "see …", and all-caps — none of which excludes a
heading that merely looks like a proper noun.

The consequence is not cosmetic. `discover_landmarks` reports "28 landmarks"
and the verification path then matches none of them, so a real signal is
diluted to zero by name-only noise.

## Scope

**Path 3 must produce places, not headings.**

Paths 1 and 2 (`_sparql_coordinate_query`, `_sparql_p131_query`) return real
landmarks carrying a **QID and coordinates**. Path 3 appends `Landmark(name=...)`
with neither. That asymmetry is the tell.

Choose one and justify it in the submission:

- **Resolve before admitting** — look each extracted name up in Wikidata and
  keep it only if it resolves to an entity with coordinates inside the area's
  bounding box. This preserves the path's value (Wikipedia articles do name real
  local places that SPARQL misses) at the cost of a lookup per candidate.
- **Drop path 3 entirely** if resolution proves it contributes almost nothing
  once filtered. **Measure before deleting** — report how many survive
  resolution across at least three areas.

**Either way, a `Landmark` without a QID or coordinates must not enter the
cache.** If a name cannot be resolved to a place, it is not a landmark.

## The line you must not cross

**Do not fix this by widening the reject-list.** Adding "Origin of term" and
"Canton of …" to a blocklist treats the symptom; the next article has different
headings. The structural problem is that a heading is being trusted as a place
name without any check that it *is* one. That is the same shape as the bug
LOCAL-290 just fixed in the existence gate — a name accepted or rejected without
consulting a source that would know.

**Do not weaken the SPARQL paths** to compensate. They are the ones working.

## Verification

Run landmark discovery for **at least three areas** — French Riviera, Nice, and
one other (Cannes or Menton). Report for each:

- landmarks found per path (SPARQL bbox / P131 / Wikipedia), before and after;
- how many Wikipedia-path candidates resolved to a QID with in-area
  coordinates, and how many were discarded;
- the **`verify_landmarks` match rate before and after** — currently 0/28. This
  is the number that proves the fix.
- every discarded candidate, so LEAD can confirm nothing real was lost.

Then generate **one 8-stop Riviera tour** and confirm the delivered stop count
has not regressed from the 8/8 LOCAL-290 achieved. Copy it to
`/Users/micha/Audioura/tours/`.

## Traps

- **Cleanup rule (D141):** delete only rows this run created, by an id captured
  at creation, and only after `SELECT is_test` on that id returns `true`.
  `audio_tours` before and after; Nice list `[1,12,14,17,24,29,152]`.
- Tests run against `audiotours_test` (D148).
- **Run every example you paste and confirm the output matches** (D97, D103).
- Judge protected-file changes from `git merge-base`, never `storied..HEAD` (D147).
- Read the delivered tour as prose (D161).
- **D186:** the spine stays on gpt-4o.
- `tests/test_local115_referral_abuse_controls_guard.py` calls `sys.exit()` at
  module scope and breaks any `pytest tests/` run that collects it. Pre-existing,
  not yours — run your suites by filename.

## Acceptance criteria

- No `Landmark` enters the cache without a QID and in-area coordinates.
- Section headings no longer appear as landmarks; evidence shown.
- `verify_landmarks` match rate reported before and after, across ≥3 areas.
- Every discarded candidate listed.
- SPARQL paths unchanged; 8-stop delivery not regressed.
- `git status --short` clean. No container rebuilt.

## PROCESS

Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-293.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
