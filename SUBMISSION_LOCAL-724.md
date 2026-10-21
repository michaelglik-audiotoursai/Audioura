# SUBMISSION — LOCAL-724: Make the approved Content Policy true in the code

**Task:** ClickUp `wdvrdaz2ye` (D656 add. 2)
**Branch:** `LOCAL-724-content-rating-truth`
**Base (code_sha):** `7f4e360dbf60f4982344c0e4831a43a23a0ce492` (subscribed; `git merge-base --is-ancestor 7f4e360d HEAD` → 0)
**Agent:** Mac Mini Kiro

The approved Content Policy (ClickUp `wdvrdayzt1`, Michael 2026-10-20) promised behaviour
LOCAL-687 did not fully deliver. This change closes the five gaps the review found.

---

## The five items

### Item 1 + 2 — Rate before listing, in the serving path, no launchd dependency — **DONE**
A new ORIGINAL tour is now rated **inside the serving/generation path, in the same
transaction that makes it listable, before that transaction commits** — so the row
carries its `content_rating`/`review_status` the instant it can appear in `/tours-near`.
The rater runs in the orchestrator/worker, not the Mac Mini launchd tick, so it also
works on GCloud. The OpenAI key is read from the environment by `OpenAI()`
(`OPENAI_API_KEY`; on GCloud injected from Secret Manager by name) and is **never
written** to a file, task, commit or comment.

- `tour_content_rating.py`: new **`rate_tour_row(cur, tour_id, tour_name, tour_content,
  stops_count)`** — rates one original and writes the four 027 columns through the
  caller's cursor. It does **not** commit (the caller owns the transaction), is
  schema-tolerant (SAVEPOINT guard), and **never raises** — rating must never fail a
  tour store. A row it cannot rate (short text / model error / old schema) is left for
  the launchd backfill, which stays as the safety net.
- `tour_orchestrator_service.py` `store_audio_tour`: new-insert path calls
  `rate_tour_row` **before `conn.commit()`**. Test rows (`is_test`) are skipped, exactly
  as the backfill skips them.

Design choice (vs. "make NULL mean held"): I rate **before listing** rather than making
NULL globally held, because the listing layer (and LOCAL-687's own tests) treat a NULL
rating on *old* tours as general so they keep working. Making NULL globally held would
hide every pre-687 tour and break `test_local687_content_rating.py`. Rating in the same
transaction gives the stronger guarantee the approved text wants (no "listed as General
for a short time" window) without touching old tours. The launchd backfill remains for
anything the synchronous rater could not reach.

### Item 3 — Whole text, not the first 24,000 characters — **DONE**
`tour_content_rating.py`: the text is now split into overlapping ~24k-char windows
(`_chunk_text`, `CHUNK_CHARS=24000`, `CHUNK_OVERLAP=500`) that together cover **every
character**; each window is classified and the tour takes the **most restrictive** rating
any window earns (`not_allowed` > `mature` > `general`), short-circuiting once
`not_allowed` is seen. A tour at/under 24k is still **one** model call (unchanged cost
for the common case). Chosen over tail-sampling because sampling can miss mature content
in the *middle* of a long tour; chunking reads every character once. Reason reported is
the deciding window's; `detail['chunks']` records how many windows were judged.

### Item 4 — Editing re-rates — **DONE**
Every path that changes a tour's text now re-rates (or holds) it, synchronously, before
the change becomes visible:
- `tour_orchestrator_service.py` REPLACE path (LOCAL-606): after the text changes and
  before commit, `rate_tour_row` recomputes the rating; if it cannot rate synchronously,
  **`clear_rating`** holds the tour (`content_rating = NULL`, `review_status = 'pending'`
  — the listing layer hides `pending`) until the backfill re-rates it.
- `tour_editing_phase2.py` `/promote` (custom-edit → new listable original): the new row
  is rated before commit, held if it cannot be rated.
- `tour_content_rating.py`: new **`clear_rating(cur, tour_id)`** helper.

### Item 5 — Server-side report endpoint (row per report) — **DONE** (not deferred)
- `migration/sql/042_tour_reports.sql`: new **`tour_reports`** table (one row per report:
  `tour_id` FK `ON DELETE SET NULL`, `tour_name` snapshot, `reason`, `reporter_user_id`,
  `status` open|reviewed|dismissed default `open`, `created_at`). Additive, idempotent.
- `map_delivery/app.py`: **`POST /report-tour`** (OPTIONS→204; requires `tour_id` OR
  `tour_name`; inserts exactly one row; returns `201 {status:received, report_id}`), with
  a self-healing table create. It **only records** a report — it never hides, lists,
  approves or rejects a tour.
- `audio_tour_app/lib/screens/my_tours_screen.dart`: "Report This Tour" now POSTs to
  `/report-tour` (green in-app confirmation on success) and falls back to the old
  `mailto:` only on network/err. Dialog text changed from "opens an email" to "sends the
  report to our review team in the app". *(The Flutter wiring is written and reviewed but
  not exercised in a running app build in this task; the server endpoint is proven live
  below.)*

---

## ⚠️ Flag — who may approve (NOT changed, per D656 add. 2)
`review_queue.py` approve/reject is a **command-line tool** guarded only by shell/DB
access: the code does **not** restrict *who* runs it to a human — anyone with a shell on
the box (including a Claude/agent session) could run `python3 review_queue.py approve
<id>`. Its docstring names the reviewer "LEAD or Michael", and the approved policy says a
person reviews anything not clearly general. Per D656 add. 2 (approvals stay with Michael
personally) I did **not** change `review_queue.py` or the policy text — flagging it as the
task requires. Making approval human-only (e.g. an interactive confirmation or an
operator identity the queue records/validates) would be a follow-up, and the policy text
would have to be settled first if a non-human is ever to approve.

---

## Live proof (own isolated stack; launchd tick never ran)
Isolated stack only: `docker compose -p local724 -f docker-compose.local724-proof.yml`
— own Postgres (host `:55433`, own volume `local724_pg`) + own map-delivery (host
`:55005`) **built from this worktree**. The shared `audioura-*` containers and
`development-postgres-2-1` were **never touched** (confirmed still running after; I only
ever used `-p local724`, spare ports, and host-side Python pointed at the isolated DB).
No launchd tick runs in this project. (pg15's SCRAM needed the isolated role switched to
`md5` for the map-delivery image's older libpq — isolated DB only.)

Driver `live_local724_proof.py` drove the **real** serving-path function
`tour_orchestrator_service.store_audio_tour` (the exact function the orchestrator runs
after generation) with **real, model-generated** tour text and **real** rating calls
(key from env), then queried the **own** map-delivery `/tours-near`.

Results:
- **Item 1+2** — Tour 1 (general) appears in `/tours-near` already carrying
  `content_rating='general'` at its **first** appearance; `[LOCAL-724] rated tour 1
  general` is logged *before* `store_audio_tour` returns (rated before commit/listing).
- **Item 3** — Tour 2 has mature content **only at char 24,080** → rated
  `mature [pending]` across **2 windows**; it is **hidden** from `/tours-near` without
  `adult=1`, and still hidden *with* `adult=1` (pending review). A first-24k-only rater
  would have said general.
- **Item 4** — Re-storing tour 1 (same creator → REPLACE path) with bar-crawl text
  re-rated it `general → mature [pending]`, `rated_at_changed=True`; the edited tour is
  held.
- **Item 5** — `POST /report-tour` → `201 {report_id:1}`, exactly **one** `tour_reports`
  row (`status=open`); missing `tour_id`+`tour_name` → `400`; `OPTIONS` → `204`;
  `audio_tours` untouched by the report.

**Row counts (isolated DB, declared):** `audio_tours` 0 → 2; `tour_reports` 0 → 1;
`audio_tour_versions` 0 → 1 (REPLACE archive). Stack + volume torn down with `down -v`.
**No `DELETE FROM audio_tours` on any shared/live DB.** No live/shared DB rows were
written — all writes were in the throwaway isolated DB.

Why not the full multi-service generator: the rate-before-listing guarantee lives
entirely in `store_audio_tour → rate_tour_row → /tours-near`, all exercised here with
real model calls. Spinning tour-generator/modernized/TTS as well would add $0.30–0.65 per
tour with no added proof of *this* guard, so I kept the run to the serving path to respect
the ≤ $2 budget.

**Cost:** a few cents (2 `gpt-4o-mini` text generations + ~4 `gpt-4.1-mini` rating calls),
well under $2.

---

## Tests
- `python3 -m pytest tests/test_local687_content_rating.py -q` → **21 passed** (stays
  green).
- `tests/test_local724_content_policy_truth.py` (new, hermetic, no paid calls — `classify`
  monkeypatched) → **15 passed**. Covers each item: chunk coverage + short=1-call +
  mature-after-24k + not_allowed short-circuit (item 3); `rate_tour_row` writes the
  columns **without committing** + skips short text + is non-blocking on model error
  (items 1+2); `clear_rating` holds (NULL + pending) + held-is-not-listable via the real
  predicate + re-rate overwrites (item 4); `/report-tour` 201/one-row + never touches
  `audio_tours` + 400 + OPTIONS 204 (item 5).
- Combined: **36 passed**.
- **Red test** (break the guard, show it fails — reproducible): temporarily changing the
  real `_content_visible` so `not_allowed` returns `True` turns the suite **2 failed / 34
  passed** (`test_not_allowed_is_hidden`, `BrokenFilterGoesRedTest.test_not_allowed_must_be_hidden`);
  reverting returns **36 passed**. The suite also carries
  `RateBeforeListingRedTest`, which asserts that an unrated (rater-skipped) mature tour
  wrongly lists as general — the exact bug this task fixes.
- Note: `tests/test_local671_original_language.py` fails 8 tests on the **pristine** base
  (confirmed by `git stash` of my `map_delivery/app.py`) — pre-existing, **not** caused by
  this change.

---

## Files
Modified: `tour_content_rating.py`, `tour_orchestrator_service.py`,
`tour_editing_phase2.py`, `map_delivery/app.py`,
`audio_tour_app/lib/screens/my_tours_screen.dart`.
New: `migration/sql/042_tour_reports.sql`, `tests/test_local724_content_policy_truth.py`,
`docker-compose.local724-proof.yml`, `live_local724_proof.py`.

Not edited (per PROCESS): DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE,
`.continuous_dev/`, STORIED_COMMUNICATION_04.MD, `review_queue.py`, the policy text.
