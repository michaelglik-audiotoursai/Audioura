# SUBMISSION — LOCAL-703: Launch window (D664)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-703-launch-window` (from `subscribed` = `d55fc079`)
**App build:** `2.4.22+59` → **`2.4.23+60`**

A new community must win its first **two qualifying members** (the organiser does **not** count)
within **168 h (7 days)** of creation, or it is **archived** and its invite code stops working.
Paid communities count members holding a **verified paid pass**; free communities count **joined**
members. Launch is checked on every join / pass verification; `launched_at` is stamped **once** and
never reverted. The organiser sees a **live countdown** on the community page and in the creation
confirmation, turning green **"Launched 🎉"** once met, and is reminded at **48 h** and **12 h** left.

---

## 1. Migration — `migration/sql/037_community_launch_window.sql`

The **next free number** (036 was the LOCAL-702 hand-over migration). Purely **additive** and
**idempotent** (ADD COLUMN IF NOT EXISTS / guarded CHECK / value-asserting backfill), wrapped in one
transaction. Adds to `communities`:

- `launch_deadline TIMESTAMPTZ` — `created_at + COMMUNITY_LAUNCH_HOURS` (168 h). The API sets it on
  create; the migration **backfills existing communities** (the two demo communities) to
  `NOW() + 168 h` from the moment the rule ships.
- `launched_at TIMESTAMPTZ NULL` — stamped once the bar is met; never reverted.
- `archived_reason VARCHAR(32)` — `'launch_window_missed'` (this task) or `'handover_expired'`
  (LOCAL-702's 30-day path; already-archived rows are backfilled to the latter). CHECK-guarded.
- `launch_reminded_48h_at`, `launch_reminded_12h_at TIMESTAMPTZ` — reminder bookkeeping (guards
  against double-send).
- Partial index `idx_communities_launch_window (launch_deadline) WHERE status='active' AND launched_at IS NULL`.

> **I did NOT apply this to the shared/production DB.** Per PROCESS I applied it to **my own test DB
> `audiotours_test` only** and confirmed a re-run is clean (idempotent — all ALTERs skip with
> NOTICE). **LEAD: please run `037_community_launch_window.sql` against the shared dev DB.**

## 2. Server — `user-tracking/communities_api.py`

- Config: `COMMUNITY_LAUNCH_HOURS=168`, `COMMUNITY_LAUNCH_MEMBERS_NEEDED=2`,
  `LAUNCH_REMINDER_HOURS=(48, 12)` — all env-overridable.
- `_qualifying_member_count(cur, community_id, is_paid)` — members **excluding the owner**; for a
  **paid** community only rows with `transaction_id IS NOT NULL` (a verified paid pass) count, so a
  free join never counts toward a paid community's bar (the D664 reading: "free-joined don't count
  for paid").
- `_check_and_maybe_launch(...)` — one-way: stamps `launched_at` once the count reaches 2; a no-op
  thereafter (never reverts). Called on **every free join** and **every successful pass verify**.
- `create_community` sets `launch_deadline = NOW() + make_interval(hours => COMMUNITY_LAUNCH_HOURS)`.
- `_community_page` payload gains `launch: {deadline, hours_left, members_needed: 2, members_so_far,
  launched, launched_at}`. `hours_left` is `ceil` of the remaining hours and **never negative** (a
  partial final hour reads **1** — the hourly cadence matters for the last hours).
- `get_community_by_code` → **410 `{"error":"community_closed"}` ("This community has closed.")**
  once the community is `archived` (covers the launch miss and the LOCAL-702 hand-over expiry).
  Members keep their downloads (D658) and reach the community via `/communities/mine`, not the code.
- `run_launch_window(cur, now=None)` + `POST /communities/launch-window/run` — the job: archive
  every **active, un-launched** community past its deadline (`status='archived'`,
  `archived_reason='launch_window_missed'`, `archived_at`), and stamp the **48 h / 12 h** organiser
  reminders once each. A **launched** community is never archived. Idempotent.

## 3. `>>> LEAD: wire the launch-window tick (DAILY *and* HOURLY) <<<`

The launch-window job is a tick like the existing reminder / archive ticks. I ship the endpoint +
the pure `run_launch_window` function; **LEAD wires it on the same scheduler**. Unlike the 30-day
archive tick, this one must run **hourly as well as daily** — the organiser's countdown is shown in
whole hours, so the final hours (and the 12 h reminder) need an hourly pass to be accurate.

**The tick line (hourly, and so also daily):**

```bash
# Hourly — archive communities that missed the 2-members-in-168h bar, and fire the
# 48h / 12h organiser reminders (D664). Hourly cadence keeps the countdown's last hours exact.
curl -fsS -X POST "$USER_API_BASE/communities/launch-window/run" -H "X-API-Key: $GATEWAY_API_KEY"
```

(or, in-process on the same cron that calls `run_reminders` / `archive_stale_handovers`:)

```python
from communities_api import run_launch_window
result = run_launch_window(cur)   # {'archived': [...], 'reminded_48h': [...], 'reminded_12h': [...]}
conn.commit()
```

Idempotent: a launched community is skipped (`launched_at IS NULL` guard), an archived community is
no longer `active`, and each reminder column guards its own bucket — a second run the same hour
archives/reminds nothing new. `COMMUNITY_LAUNCH_HOURS` overrides the 168-h window if ever needed.

## 4. App — `audio_tour_app/` (build `2.4.23+60`)

- **`lib/services/communities_models.dart`** — new `CommunityLaunch` model
  (`deadline / hoursLeft / membersNeeded / membersSoFar / launched / launchedAt`), wired into
  `Community` (defensive parse, sane defaults when the field is absent). New `CodeResolution`
  (`community` / `closed`) to distinguish a 410 from a not-found. New `CommunityCopy` copy:
  `launchCountdown(...)` → **"152 h left to get 2 paid members — 1 of 2 so far"** (free:
  "…2 members…"), green **"Launched 🎉"** when launched; `createLaunchRule(paid)` for the Create
  screen; `communityClosed = "This community has closed."`.
- **`lib/services/communities_service.dart`** — `resolveByCodeResult(code)` returns a
  `CodeResolution` (**410 → `closed: true`**); `resolveByCode` delegates to it (back-compat).
- **`lib/screens/home_screen.dart`** — the invite-code search shows **"This community has closed."**
  when the code resolves to an archived community (410), instead of the generic not-found message.
- **`lib/screens/community_page_screen.dart`** — `_launchCountdownSection`: the organiser's **live
  countdown card** (owner-only; hidden once archived; green when launched; `Key('launch_countdown_text')`).
- **`lib/screens/communities_about_screen.dart`** — the **launch rule** is stated on the Create
  screen above the Create button (paid vs free wording), and the **creation confirmation** dialog
  shows the live countdown line.

## 5. Tests

**Server — `tests/test_local703_launch_window.py` (16 tests, all green):** deadline set on create
+ payload; paid: 1 member not launched, 2 → launched, owner excluded, a free join is refused (402)
so it can't pad a paid bar; free: 2 joins → launched, owner excluded; the job archives a
past-deadline unlaunched community (`archived_reason='launch_window_missed'`) and its code → **410
community_closed**; the job is idempotent; an in-window community is left active; a **launched
community is never archived**; the **48 h / 12 h reminders fire once each**; a launched community
gets no reminders; `hours_left` math (never negative; last partial hour reads 1).

**Combined community suites green:**

```
tests/test_local690_communities.py tests/test_local700_communities_ux.py \
tests/test_local701_community_tours.py tests/test_local702_organiser_steps_down.py \
tests/test_local703_launch_window.py   →  94 passed in 3.30s
```

**App — `audio_tour_app/test/launch_window_countdown_test.dart` (21 tests, all green):** the exact
countdown wording (paid / free / launched), `createLaunchRule`, `communityClosed`,
`CommunityLaunch` + `Community` parsing, and `CodeResolution`. `flutter test` → **45 passed**;
`flutter analyze` on the changed files → **no errors** (only pre-existing lints elsewhere).

## PROCESS

Own containers + test DB only — I ran against `audiotours_test`, never `-p audioura`, never renamed
`audioura-*`, and did **not** apply the migration to the shared DB (LEAD does — see §1/§3). No edits
to DECISIONS / CLAUDE / BACKLOG / WORK_QUEUE / `.continuous_dev`. App build bumped. Branch pushed to
`origin/LOCAL-703-launch-window`.
