# SUBMISSION — LOCAL-804 (P2): nightly failure triage → ranked report → draft task files

**Decision:** D723 ("1) record, 2) analyze, 3) prioritize, 4) fix")
**Base:** `subscribed` @ `0a6c5b2b` · **Branch:** `LOCAL-804-failure-triage`

## What this delivers

LOCAL-785 built step **(1) record** — `failure_events` (migration 054),
`failure_log.record`, the client `FailureReporter` — and `failure_report.py`
dumps the raw groups. Nothing turned those records into work. This task is steps
**(2) analyze + (3) prioritize**, and it seeds **(4) fix**:

`failure_triage.py` reads the last N days (default 7) of recorded failures,
groups them by a normalised signature, classifies and ranks each group, and
writes a ranked Markdown report plus DRAFT task files for the worst of OUR bugs.
It is **read-only on the database** and runs nightly from a launchd agent.

## Files (all new; nothing existing was edited)

| File | What |
| --- | --- |
| `failure_triage.py` | The tool: readers, grouping, classification, ranking, report + draft rendering, optional capped LLM, CLI. |
| `test_local804_failure_triage.py` | 17 unit tests over a **20-row synthetic fixture** across all classes. |
| `.continuous_dev/com.audioura.failure-triage.plist` | launchd FILE (LEAD installs) — 02:30 nightly, Mac DB, read-only, no `--llm`. |
| `reports/failure_triage_2026-10-29.md` | The first live report (read-only run against the Mac DB). |
| `drafts/new_kiro_session_is_required_DRAFT-9fefdfd5.md` | DRAFT our_bug task (generation_failed). |
| `drafts/new_kiro_session_is_required_DRAFT-f2d5f1d1.md` | DRAFT our_bug task (generation_failed + Exception). |
| `drafts/new_kiro_session_is_required_DRAFT-14821d08.md` | DRAFT our_bug task (40-minute poll-cap abandon). |

`reports/.triage_seen.json` (the run-to-run "which signatures are new" memory)
is intentionally **not committed** — it is regenerated on every run.

## How it works

### 1. Reads four sources (the whole picture of a night's failures)
- `failure_events` — the durable recorder (every surface).
- `lookup_escalations WHERE tier_found='none'` — genuine "nothing found" even
  the dearer tiers (LOCAL-784) could not rescue; a user-confusion signal.
- `generator_jobs WHERE status IN ('error','failed')` — generator deaths (LOCAL-775).
- `tour_requests WHERE status='failed'` — user-visible request failures.

### 2. Groups by signature
`sha1(source + service + error_code + exception_type + normalise(message))[:16]`,
**reusing `failure_log.normalise_message`** so "tour 445 failed" and "tour 446
failed" collapse into one group across ids, numbers and quoted strings — the
same normalisation the recorder signs with.

### 3. Classifies (rule-based, D723's five classes)
`our_bug` · `external` · `user_confusion` · `expected` · `unknown`.
Precedence (first match wins): a Free-tier refusal is `expected`; a LEAD
override (`triage_source='lead'`) is authoritative; explicit codes
(`generation_failed`→our_bug, `no_results_found`/`exhibition_not_found`→
user_confusion); a named provider (Overpass/Wikimedia/OpenAI/Gemini, 402/429)→
external; a 5xx→our_bug; a network exception→external, any other exception→
our_bug; then the stored auto-triage; then a source default (a reasonless
generator/tour-request failure still means the user got no tour → our_bug).
The stored vocabulary is mapped into the five classes (`ux`/`absence`→
`user_confusion`).

### 4. Ranks
`score = count × severity × recency`; severity `our_bug 3 · external 2 ·
user_confusion 1 · expected 0 · unknown 1`; recency `≤1d 1.0 · ≤7d 0.6 · else
0.3`. **New** signatures (not in `.triage_seen.json`) float to the top.

### 5. Emits
- `reports/failure_triage_<date>.md` — top 15 groups (count, first/last seen,
  **redacted** example, class, suggested owner) + a **"User confusion"** section
  listing the screens/actions, so Michael gets UI fixes, not just bug tickets.
- `drafts/new_kiro_session_is_required_DRAFT-<sig8>.md` for the top-3 `our_bug`
  groups — evidence + a proposed fix area. These filenames are **deliberately
  outside the dispatcher glob** (`new_kiro_session_is_required_LOCAL-*.md`, see
  `restart.sh`) and are **never added to RELEASED.txt**. LEAD reviews and
  promotes the real ones by renaming to a LOCAL ticket.

### Redaction
The report/drafts carry **no user text** (quoted literals stripped), **no
emails, no secret ids/uuids** — only tour ids survive, as the spec allows.

### Optional `--llm` (off by default)
One `gpt-4.1-mini` classify per **new unknown** group only, hard-capped **before
any call** at ≤ $0.02/night and a $0.05 absolute ceiling. With `--llm` off, the
tool makes **no network call** (pure stdlib + psycopg2). The nightly plist does
not pass `--llm`, so it costs nothing.

## Read-only guarantee
`_connect` issues `SET SESSION READ ONLY`; only `SELECT`s are run; the tool never
writes to the DB. Verified live: the four tables' row counts were identical
before and after the run (`77 / 10 / 12 / 326`).

## Live result (Mac DB `localhost:5433`, last 7 days)
`91 events → 8 groups (all new on first run)`. Top group: 74× `exhibition_closed`
(user_confusion — a UI fix: tell the user up front a show has closed). 5 `our_bug`
groups (generation_failed ×, a 40-minute poll-cap abandon, a cancelled job) →
3 DRAFTs written. Full output in `reports/failure_triage_2026-10-29.md`.

## Tests
`python3 -m pytest test_local804_failure_triage.py` → **17 passed**. The 20-row
fixture exercises grouping (ids/numbers collapse), classification (every class +
LEAD-override and expected-refusal precedence), ranking (score math + new-on-top
+ expected-scores-zero), redaction (email/quoted-text/uuid stripped, tour id
kept), draft content (outside the dispatcher glob, evidence + fix area), dry-run
(writes nothing), and the LLM path (labels only new unknowns; cap blocks calls
at zero budget) — all without a database.

## How to run / install
```bash
# Ad-hoc, read-only, against the Mac DB:
DB_HOST=localhost DB_PORT=5433 DB_NAME=audiotours DB_USER=admin \
  DB_PASSWORD=password123 python3 failure_triage.py --days 7

# Nightly (LEAD installs the agent):
cp .continuous_dev/com.audioura.failure-triage.plist \
   ~/Library/LaunchAgents/com.audioura.failure-triage.plist
launchctl load -w ~/Library/LaunchAgents/com.audioura.failure-triage.plist
```

## Scope / constraints honoured
Read-only, no DB writes, no `DELETE`. No edits to DECISIONS.md, CLAUDE.md,
BACKLOG.md, WORK_QUEUE, SUBSCRIBED_COMMUNICATION_01.MD, `legal/`,
GCLOUD_STORIED_START_HERE.md, TRAVEL_PROJECTS.md, or `.continuous_dev/` except
adding the new plist FILE. Committed by name (never `git add -A`). Branched from
HEAD (`0a6c5b2b`), not from origin.
