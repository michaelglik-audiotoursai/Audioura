# SUBMISSION — LOCAL-688: "Why this score" + public scoring page + stable scores (D655, D656)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-688-why-this-score` (from `subscribed` @ `1512dddc`)
**Build:** 2.4.14+47 → **2.4.15+48**
**Status:** Backend proven on the dev DB (read-only) + unit/endpoint tests green. App compiles clean (`flutter analyze`: 0 errors in all touched files); app UI itself is unproven on a device — handing to LEAD for the on-device check.

## Why
LOCAL-685 (D655) gave every visible tour an evaluated starting score 5.0–8.0
("★ 6.6 · Audioura score") from `tour_editor_score.py` (gpt-4.1 rubric: story,
specificity, place, flow, accuracy; one evidence sentence per criterion in
`audio_tours.editor_score_detail`). Michael (2026-10-14): guides and listeners
will want to know how the score is made; it must look objective; **free for
everyone**. This ships the "why", a public page, stable (3-run) scores, and one
free re-score after an edit.

## What shipped

### 1. Stable scores — `tour_editor_score.py`
A single rubric run wobbles ±0.4 at temperature 0 (the model is not
deterministic). `score_text(..., runs=RUBRIC_RUNS)` now grades the **same script
three times** and averages each of the five criteria (re-rounded to the 0.5
grid) **before** the 5.0–8.0 mapping. The mapping itself (`map_to_range`,
`RUBRIC_LOW/HIGH`, `SCORE_MIN/MAX`) is unchanged from LOCAL-685.
- `editor_score_detail` now carries every run's five grades in `detail['runs']`
  (auditable), a `run_count`, and `rubric_version = 2` (bumped from the implicit
  1). Evidence/summary come from the first run; the published per-criterion
  grades are the averages.
- `RUBRIC_RUNS` is overridable via env `EDITOR_SCORE_RUNS` (and the `runs=` arg
  in tests) for cost control. `--dry-run / --tour / --backfill / --rescore` are
  untouched.
- **I did not re-score the live DB** (the ticket reserves that for LEAD). Old
  rows keep their LOCAL-685 single-run detail (no `runs`/`rubric_version`); the
  endpoint handles that — `rubric_version` reads back `null` until LEAD
  re-scores, then `2`.

### 2. DB — additive, idempotent (`migration/sql/026_rescore_requested_version.sql`)
- `audio_tours.rescore_requested_version INTEGER NULL` — the content version a
  free re-score was last requested for. NULL = never requested. (Migration 025's
  `editor_score` columns are unchanged.)

### 3. map-delivery endpoints (`map_delivery/app.py`) — all PUBLIC, no auth
- **`GET /tour/<id>/score-explanation`** →
  `{score, label, criteria:[{name,label,grade,evidence}], summary, scored_at,
  rubric_version, tour_id, scored_tour_id}`. A **translation returns its
  original's** explanation (resolved via `_resolve_original_id`, same rule as the
  shown rating prior). **404** when the governing tour has no evaluated score
  yet. Reads only what `tour_editor_score.py` wrote — no model call.
- **`POST /tour/<id>/rescore-request {user_id}`** — the guide's one free
  re-score of **their own** tour. Ownership is the **same check the curator Price
  control uses** (`_user_is_tour_creator` → explicit `creator_user_id` else the
  earliest `tour_requests.secret_id` of the original). Clears the original's
  `editor_score` (the 5-minute tick re-scores it) and stamps the content
  version. **403** non-owner / missing user; **409** a second request for the
  **same content version** (one per version, with a friendly message); **200**
  `{status:'queued', version}` on success. `user_id` is read from the JSON body,
  the query, or `X-User-Id`. Degrades safely when migration 026 is not yet
  applied: it detects the column via `information_schema` and still clears the
  score (fail open, never 500).
- **`GET /how-we-score`** — the public **"How Audioura scores tours"** page.
  Self-contained HTML (no external CSS/JS), phone-readable: the five criteria,
  what 3 / 5 / 6.5 / 8 / 9.5 mean, why the range is 5–8 (9–10 reserved for
  listeners), that it is the same for every tour and **free**, that a guide may
  request one re-score after editing, and that **listeners take over from the
  fourth rating**.

### 4. App — "Why this score" (`audio_tour_app/`)
- `services/score_explanation_service.dart` — `fetch()` (→ `ScoreExplanation`,
  null on 404/error), `requestRescore()` (→ `RescoreResult` for 200/409/403),
  `howWeScoreUrl()`.
- `widgets/why_this_score_sheet.dart` — `showWhyThisScoreSheet(...)` bottom
  sheet: the five criteria as **bars with grade + the evidence sentence**, the
  editor's one-line summary, and a **"How Audioura scores tours"** link
  (url_launcher). When the tour has listener ratings it shows **both**
  "Listeners: 8.3 (5 ratings) · Audioura: 6.6" and the line that **from the
  fourth rating on, the listeners decide**.
- `widgets/rate_tour_dialog.dart` — `TourRatingBadge` gained an optional
  `onTap` (and a faint ⓘ hint); tapping the badge opens the sheet. Wired at
  **both** badge sites in `home_screen.dart`: the tour dialog and the home
  **List** view.
- `screens/my_tours_screen.dart` — a **"Request re-score"** item in the guide's
  ⋯ menu on their own (non-translation, numeric-id) tour: confirm dialog →
  `DeviceService.getUserId()` → `requestRescore` → outcome snackbar.
- `pubspec.yaml` — **2.4.15+48**.

## Tests — `tests/test_local688_why_this_score.py` (no paid API calls; model mocked)
`22 passed` (14 LOCAL-688 + 8 LOCAL-685), run against `audiotours_test`:
- **Stable scores (pure, mocked judge):** three runs averaged per criterion;
  averaging collapses a 0.5 single-run wobble to one stable grade; mapping
  unchanged from LOCAL-685; detail JSON shape (criteria floats, evidence per
  criterion, summary, `rubric_version == 2`, `runs`, summed tokens); `runs=`
  override.
- **`/how-we-score` (pure):** 200, `text/html`, contains all five criteria and
  the range / free / re-score / "fourth rating" copy and the 3/5/6.5/8/9.5
  anchors.
- **score-explanation (DB):** an original returns its block; a **translation
  returns the ORIGINAL's** (same score, `scored_tour_id` = original); an
  **unscored tour → 404**.
- **rescore-request (DB):** owner may request **once per version** then **409**;
  score cleared + version stamped on success; **403** non-owner; **403** missing
  user; a request against a **translation resolves to the original**.
- `tests/test_local685_editor_score.py` still passes.

> Note: `tests/test_local666_*` and `tests/test_local671_*` have pre-existing
> failures on this base (`1512dddc`) — their mocked DB rows don't match the
> current 21-column SELECT in `/tour-info`. I confirmed they fail identically on
> the **base** `map_delivery/app.py` (diffed; ran one against the base file).
> **Not caused by this branch.**

## Live test (dev DB `development-postgres-2-1`, localhost:5433, read-only)
No `audioura-*` container touched; no write to `audio_tours`.

**`GET /tour/557/score-explanation` → HTTP 200** (score 7.9, label "Audioura
score"; five criteria with grades 8.0 / 8.5 / 8.5 / 8.0 / 9.0 and evidence
sentences; summary present; `scored_at` 2026-10-14; `rubric_version` null — this
row predates the 3-run scorer). `scored_tour_id` = 557.

**`GET /tour/388/score-explanation` → HTTP 200** (score 8.0; five criteria 8.5 /
9.0 / 8.5 / 8.0 / 9.0 with evidence; summary present). `scored_tour_id` = 388.

**3-run scorer `--dry-run --tour 557`** (the one allowed paid call, ≈3¢):
```
 557  7.9  (stor=8.0 spec=8.0 plac=8.5 flow=8.0 accu=9.0, avg 8.3)  Walking tour in Boston dedicated to Massachusetts
1 tour(s); tokens in 7821, out 943; ~$0.0232 (dry run, nothing written)
```
Confirmed nothing was written: tour 557's `editor_score` is still 7.9 after the
dry run.

## For LEAD
- Apply migrations **025** (if not already) and **026** to the live DB.
- Re-score with the new 3-run scorer (`tour_editor_score.py --backfill
  --rescore`, or per-tour) so `editor_score_detail` gains `runs` + `rubric_version=2`.
- On-device check of the "Why this score" sheet (badge tap in the tour dialog
  and the List) and the guide's "Request re-score" menu item. **Unproven on a
  device — handing to LEAD.**

## Commits (on `LOCAL-688-why-this-score`, from `1512dddc`)
1. `320e83bb` stable scores — 3-run averaging, `rubric_version=2`, `runs`
2. `7405561b` migration 026 — `rescore_requested_version`
3. `eda63b9f` map-delivery endpoints — score-explanation / rescore-request / how-we-score
4. `899b3eb4` tests
5. `4a5d1e80` app — Why-this-score sheet, re-score menu, bump 2.4.15+48
6. `abe21577` rescore-request degrades safely without migration 026
