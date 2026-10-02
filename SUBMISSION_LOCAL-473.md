# SUBMISSION — LOCAL-473 · The Substitution Test Must Not Depend On Which Siblings Exist

**Branch:** `LOCAL-473-specificity-generic-sibling`
**Base:** `storied` @ `077c979` (verified: `git merge-base --is-ancestor 077c979 HEAD` → 0)
**ClickUp:** `wdvrdaxa7h`
**Supersedes:** LOCAL-472 (REJECTED). Its structural fixes are kept; its substitution
*method* is replaced.

---

## The defect LOCAL-472 shipped

LOCAL-472 ran the substitution test by swapping in a **named sibling stop from the
same tour**. LEAD ran the real model against Michael's Example A and got three
different answers from one paragraph:

```
siblings=['Villa Leopolda','Musee Matisse']        -> transferable=False conf=high   KEPT     <- WRONG
siblings=['Cap Ferrat']                             -> transferable=True  conf=medium KEPT     (medium never deletes)
siblings=['Cap Ferrat','Pointe des Douaniers']      -> transferable=True  conf=high   REMOVED  (correct)
```

Two independent failure modes were baked into the method:

1. **Dissimilar-sibling false negative.** Swapping a *museum* into a *cape* paragraph
   makes "panoramic sea views" break — a museum genuinely has none — so the model says
   SPECIFIC and the generic prose is kept. Real tours are mostly dissimilar stops (the
   Cimiez tour is a monastery, two museums, Roman ruins, a villa), so on a real tour the
   gate keeps the very prose it exists to delete.
2. **Confidence tied to sibling count.** TRANSFERABLE was `medium` on a 1-sibling tour
   and `high` only with ≥2 siblings — and `medium` never deletes. So the *number* of
   stops, not the paragraph, decided whether anything happened.

Both mean: **the verdict depended on the tour's other stops.** A stub can't catch this —
that's why LOCAL-472's 18 green tests missed it.

## The fix

Stop substituting a named sibling. Classify the stop's **kind** and substitute a
**generic same-kind referent**, so the swap measures the paragraph and nothing else.
Michael's test is *"say the same thing about another **location**"* — another location,
not another stop on this tour.

- `classify_stop_kind(stop_name, description)` — deterministic keyword classifier →
  `{'kind', 'referent'}`. Kinds: viewpoint / museum / church / ruin / restaurant / park /
  street / villa, with a neutral `another place of the same kind` fallback. No network.
- `check_paragraph_specificity(...)` now swaps in that generic referent
  (`"another coastal viewpoint"`, `"another art museum"`), makes **one** sibling-independent
  model call, and takes the verdict directly: TRANSFERABLE → `high`, SPECIFIC → not
  transferable. `sibling_stop_names` is still accepted (context/logging) but **does not
  affect the verdict**; the test runs identically with `siblings=[]`.

Confidence no longer depends on sibling count (that ambiguity was the defect). The
conservative-removal rule is unchanged: only `high`-confidence transferable deletes, and
a stop is never emptied (LOCAL-359 + never-empty-a-stop).

## The bar — all four met

### Bar 1 & 2 against the REAL model (`gpt-4o-mini`) — bar item 3

`tests/test_local473_live_model.py`, run with the live key. Actual verdicts pasted:

```
[LIVE gpt-4o-mini] stop="Cap d'Antibes" siblings=['Villa Leopolda', 'Musee Matisse'] -> transferable=True  conf=high kind=viewpoint referent='another coastal viewpoint'
   reason: Generic scene-setting claims apply to any coastal viewpoint.
[LIVE gpt-4o-mini] stop="Cap d'Antibes" siblings=['Cap Ferrat']                       -> transferable=True  conf=high kind=viewpoint referent='another coastal viewpoint'
   reason: Generic scene-setting claims apply to any coastal viewpoint.
[LIVE gpt-4o-mini] stop="Cap d'Antibes" siblings=[]                                   -> transferable=True  conf=high kind=viewpoint referent='another coastal viewpoint'
   reason: Generic scene-setting claims apply to any coastal viewpoint.

[LIVE gpt-4o-mini] stop='Cimiez Monastery' siblings=['Villa Leopolda', 'Musee Matisse'] -> transferable=False conf=high kind=church referent='another historic church'
   reason: Mentions Henri Matisse and specific historical events unique to Cimiez Monastery.
[LIVE gpt-4o-mini] stop='Cimiez Monastery' siblings=['Cap Ferrat']                       -> transferable=False conf=high kind=church referent='another historic church'
   reason: Mentions Henri Matisse and specific historical events unique to Cimiez Monastery.
[LIVE gpt-4o-mini] stop='Cimiez Monastery' siblings=[]                                   -> transferable=False conf=high kind=church referent='another historic church'
   reason: Mentions Henri Matisse and specific historical events unique to Cimiez Monastery.

[LIVE apply set0] removed=0 stops_affected=0
[LIVE apply set1] removed=0 stops_affected=0
[LIVE apply set2] removed=0 stops_affected=0
```

- **Bar 1** — Example A is `transferable=True` at `high` confidence for all three sibling
  sets. **Same verdict every time.**
- **Bar 2** — the Cimiez Monastery paragraph is `transferable=False` for all three sibling
  sets, and survives end-to-end through `apply_stop_specificity_gate` (0 removed) for each
  sibling shape.

`test_local473_live_model.py` skips cleanly when `OPENAI_API_KEY` is unset, so CI stays
deterministic; it runs for real in a keyed job.

### Bar 4 — LOCAL-472's structural fixes kept

- Whole accented names, NFC + NFD (`_norm`/D243) — unchanged, still covered by
  `tests/test_local472_stop_specificity.py`.
- Exactly one `_detect_named_entities` definition (`grep -c` = 1).
- Tests live in `tests/`.
- The suite can fail: forcing every verdict to TRANSFERABLE/high flips the Cimiez verdict
  to transferable/high (proven — would delete the paragraph, turning the Bar-2 tests red).
  `TestSuiteCanFail` in the stub suite documents the forced-verdict path.

## Tests

- `tests/test_local472_stop_specificity.py` — kept for CI (16 tests). One test
  (`test_only_high_confidence_deletes`) was rewritten: it previously asserted
  "single-sibling → medium → nothing removed", which was the LOCAL-472 defect; it now
  exercises the LOCAL-359 rule via the no-model (low-confidence) path, and a new
  `test_verdict_independent_of_sibling_count` asserts the invariant directly.
- `tests/test_local472_wiring.py` — kept (3 tests); the PHASE 5.152 call site executes.
- `tests/test_local473_generic_sibling.py` — new, stubbed (13 tests): kind classification,
  Example-A invariance and Cimiez survival across the three sibling sets, the referent is
  never a named sibling, and a can-fail test.
- `tests/test_local473_live_model.py` — new, live (bar item 3).

```
35 passed  (stubbed 472 + 472 wiring + 473 stubbed + 473 live)
```

## Files changed

- `stop_specificity_gate.py` — new module (LOCAL-472 base + LOCAL-473 generic-referent fix).
- `generate_tour_text.py` — added ONLY the PHASE 5.152 gate wiring block (single hunk at
  ~14692). The geocoding block and everything else are untouched.
- `tests/test_local472_*.py`, `tests/test_local473_*.py`.

## Process notes

- Branched from HEAD (`077c979`); base verified as ancestor.
- Did not touch `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/STATUS.md`,
  `PENDING_REMINDERS.md`, `GCLOUD_STORIED_START_HERE.md`, `geocode_stops.py`, the
  geocoding block in `generate_tour_text.py`, or anything under `audio_tour_app/`.
- Did not rebuild or restart any container.
