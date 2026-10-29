# SUBMISSION — LOCAL-804B: Failure triage clean-up

**Branch:** `LOCAL-804B-triage-clean` (base `subscribed` = `fa577b7f`)
**Scope:** exclude test traffic, surface the real root cause, gate
`user_confusion`, and ship the nightly launchd plist FILE.

`git merge-base --is-ancestor fa577b7f HEAD` → exit 0 (branched from local HEAD,
not `origin/*`).

---

## What the LEAD review found (first report) and what each fix does

### 1. Test traffic dominated → exclude it by default (`--include-tests` to audit)

The first report's group #1 was 74 of 91 events: `exhibition_closed` from tour
`test-local365-type` — the LOCAL-365 test suite writing `failure_events` into the
shared Mac DB. The other "real" rows were from user_id `test_local156_fe633157`,
also a harness.

- `is_test_event(ev)` / `_looks_like_test_id(value)` flag an event as test/harness
  when its `user_id`, `tour_id` or `job_id`:
  - starts with `test` / `TEST` / `test_` / `test-`,
  - starts with `p1-` (the p1 probe ids), or
  - contains a `local-NNN` / `localNNN` / `LOCAL_NNN` harness id anywhere
    (regex `\blocal[-_]?\d{2,}\b`), or
  - carries an explicit `is_test` flag.
- `filter_test_events(events, include_tests=False)` drops them by default and
  returns the excluded count (reported for transparency even when kept).
- `run(..., include_tests=False)` and the `--include-tests` CLI flag wire it in.
  The confusion-evidence scan (fix 3) is built from the KEPT events only, so a
  test row can never vouch for a production failure.

**Live effect:** the re-run excluded **77** test/harness events (74 + 3), leaving
14 real events — group #1 is gone.

### 2. Root cause hidden → look it up in `paid_api_calls`, add a `budget` class

Groups #3/#4 ("no stops could be generated") were really the shared stack's
`DAILY_PAID_LIMIT_USD` refusing paid calls (a provider **402 "out of credit"**).
That is not an engineering defect.

- `read_paid_budget_refusals(conn, since)` reads the paid-API ledger for budget /
  credit refusals: `status = 402` / `429`, or detail naming `DAILY_PAID_LIMIT`,
  `out of credit`, `insufficient_quota`, `payment required`. READ-ONLY; makes NO
  paid call.
- `enrich_root_causes(events, refusals)` attributes a **reasonless** failure
  (`_is_reasonless_failure`: a `generation_failed` / reasonless generator job /
  reasonless `tour_request`, and never a row that already names an exception) to
  a budget refusal within a **15-minute** window (`_nearest_budget_refusal`).
- New **`budget`** class (severity 2, owner `LEAD → ops/budget`), plus a
  `_BUDGET_HINTS` fast-path so a message that itself says `DAILY_PAID_LIMIT_USD`
  / `out of credit` / 402 is `budget` directly. `budget` wins group resolution
  and precedes the `generation_failed → our_bug` rule, so a starved budget is
  never filed as a defect. A dedicated **"Budget / credit"** report section
  routes these to ops, not engineering.

**Live effect:** this window's two real generation failures (14:28/14:29 on
10-28) had NO 402 within 15 min (earliest 402 was 21:38 that day), so they stay
`our_bug` — correct. The budget path is proven by unit fixtures.

### 3. `user_confusion` for `tour_request_failed` was a guess → require evidence

- `build_confusion_evidence(events)` pre-scans for CLIENT-side evidence:
  - a client `FailureReporter` event (`service='app'`, or a real device
    `platform` ≠ `server`/`unknown`) for the same tour/user, or
  - a **retry** of the same request (same normalised `request_text` or `tour_id`
    appears ≥ 2×).
- `classify_event(ev, evidence)` now classes a reasonless `tour_request_failed`
  as `user_confusion` **only** with that evidence; otherwise **`unknown`** (never
  a guessed class). The old blanket `tour_request_failed → user_confusion` and
  the `tour_requests → our_bug` source-default are both removed.

**Live effect:** group `3cbf18a3195023a1` (11 × "tour request failed", no client
signal) is now **`unknown`**, not a fabricated user_confusion.

### 4. Nightly launchd plist (FILE ONLY — LEAD installs it)

`.continuous_dev/com.audioura.failure-triage.plist` runs `failure_triage.py`
`--days 7` at **02:30 daily** (`StartCalendarInterval` Hour 2 / Minute 30)
against the **Mac dev DB** (`DB_HOST=localhost`, `DB_PORT=5433`), writing
`reports/`. **No `--llm`** → NO paid-API call, cost $0.

Also fixed the plist so it is well-formed XML: its comment contained `--` and a
bare `<date>` token, both illegal inside an XML comment — `launchctl load` /
`plistlib` would have rejected the file. It now parses (verified with
`plistlib.load` and `plutil -lint`).

---

## Tests

`test_local804_failure_triage.py` — **31 passing** (17 original + 14 new /
updated), no database, deterministic `NOW`:

- Test-traffic: id-prefix + harness-id detection, all-id-field checks,
  `filter_test_events` default vs `--include-tests`, and a `run()` end-to-end
  mirroring the first report (74 test + 1 real → 1 kept, 74 excluded).
- Budget: `_BUDGET_HINTS` classification, `enrich_root_causes` attribution within
  the window, window is bounded (a far refusal is NOT attributed), a real
  exception is never stolen into budget, and the budget group wins with the
  ops/budget owner + report section.
- Evidence gate: `tour_request_failed` is `unknown` without evidence,
  `user_confusion` with a client report, `user_confusion` with a retry; plus
  `_is_client_signal` cases.
- Plist: parses as a plist, runs `failure_triage.py`, has no `--llm`, is 02:30
  daily on `localhost:5433`, and is a FILE (not installed).

One original assertion was updated on purpose: a 402 "out of credit" is now the
dedicated `budget` class, not generic `external`.

## Live re-run (committed report)

```
DB_HOST=localhost DB_PORT=5433 … python3 failure_triage.py --days 7
[D723] failure_triage: 14 events (77 test/harness excluded) → 4 groups (4 new).
report=./reports/failure_triage_2026-10-29.md drafts=2 llm_cost=$0.0000
```

`reports/failure_triage_2026-10-29.md` regenerated. By class: our_bug=2,
budget=0, user_confusion=1, unknown=11. Paid-API cost **$0** (no `--llm`).
Report carries no raw user text / emails / request strings (redaction verified).

## Constraints honoured

- READ-ONLY DB (session set READ ONLY, SELECTs only); no DB writes; no `DELETE`.
- Committed explicitly (no `git add -A`): the four changed files only.
- Untouched: DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`
  except the new plist FILE, SUBSCRIBED_COMMUNICATION_01.MD, `legal/`,
  GCLOUD_STORIED_START_HERE.md, TRAVEL_PROJECTS.md.
- Draft files and `reports/.triage_seen.json` are runtime artifacts
  (`new_kiro_session_is_required_*.md` is gitignored) and are NOT added.

## Files

- `failure_triage.py` — exclusion, root-cause lookup, `budget` class, evidence
  gate, report sections, `--include-tests`.
- `test_local804_failure_triage.py` — new fixtures/tests for all four items.
- `.continuous_dev/com.audioura.failure-triage.plist` — well-formed XML.
- `reports/failure_triage_2026-10-29.md` — the live re-run.
