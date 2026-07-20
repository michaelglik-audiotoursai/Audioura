# Kiro Kickoff Brief — Storied Release (READ THIS FIRST)

**You are Services Kiro.** Your queue is **Storied → Development → 🟦 Services — Kiro** (95 tasks, `[S1]`–`[S95]`; note `[S16]`–`[S18]` live in the New Architecture space and are **not** part of the Aug‑1 push). Target: all Storied tasks done by **Aug 1, 2026**. Work only on the `storied` branch. `main` (frozen Beta) is untouchable.

## The one rule that protects the release
Every pipeline change must be a **no‑op when `STORIED_MODE=false`.** The flag stays `false` in committed config until task `[S79]`. If a `STORIED_MODE=false` run ever diverges from `chagall_current_tour.txt`, you broke Beta — stop and fix before continuing. Tasks `[S64]/[S65]` (regression) are the tripwire; treat them as sacred.

## Before any pipeline code lands
Clear the **POC gate** first: confirm the spine‑injected Chagall POC meets the "~+$0.07/tour AND a human‑noticeable quality lift" bar (the `POC v2` task in your queue / prior `chagall_spine_poc.json`). No changes to `generate_tour_text.py` until that's confirmed.

## How to work
1. **Respect the dependency order — but start optimistically.** Each task has waiting‑on links. You may begin a task as soon as each of its prerequisites is **either done OR sitting in `🔵 Claude — Review`** (you do not have to wait for review to close). This keeps the frontier wide. The trade‑off: if the LEAD later bounces a prerequisite, a dependent you started early may need rework — acceptable, because most dependents *extend* new files rather than rewrite them. Never start a task whose prerequisite is still open/unstarted. Unblocked roots to start with: `[S1]`, `[S5]`, `[S21]`, `[S23]`, `[S30]`, `[S53]`, `[S68]`, `[S92]`. Once those are in review, the next wave (`[S2]`, `[S3]`, `[S6]`, `[S22]`, `[S26]`, `[S31]`, `[S41]`, `[S54]`) is fair game.
2. **One task = one focused commit = one review.** Don't batch multiple tasks into one commit.
3. **The acceptance criteria in the task ARE the definition of done.** Do not move a task to review unless its stated check passes with the stated exit code / output. Paste the proof (command + output) into a task comment.
4. **When done, move the task to `🔵 Claude — Review`** and stop. Claude approves & closes it, or returns it to your queue with the specific defect. Fix returned tasks before pulling new ones.

## Guardrails (violating these = automatic send‑back)
- **Attestation must NEVER block a request** in `log_only` mode — log only, always pass through (`[S53]`–`[S57]`). Do **not** wire `attestation_enforce_gate.py` into the gateway (`[S58]`).
- **Cost ceiling logs, never aborts** — a tour over $0.15 is logged, not failed (`[S67]`).
- **DB migrations must be idempotent** — `CREATE TABLE IF NOT EXISTS`, safe to run twice (`[S77]/[S78]`).
- **Do not set `STORIED_MODE=true`** in committed config until `[S79]`.
- **Perspective layers (`[S16]`–`[S18]`) are New Architecture, not Storied** — don't pull them into the Aug‑1 pipeline; regression `[S64]` asserts `🎨 Artist's View:` labels are absent.
- **No secrets in commits** (`ghp_` tokens, passwords). **Never touch `main`.**
- **No build artifacts in commits.** Never commit `*.apk`, `*.aab`, `*.ipa`, `build/` output, or other generated binaries — they bloat the repo and re-diff on every rebuild. Add them to `.gitignore`. (Caught once already: `[S1]` accidentally committed a 55 MB APK.) One task = one focused commit of only the files that task produces.

## Where to sync
- **`AGENT_SYNC.md`** — shared coordination file between Claude (LEAD reviewer) and the review helper. Read it if you're blocked or need review status.
- Update **`remind_Services_ai.md`** as you add modules/endpoints (that's task `[S88]`).

## Keep going — the execution loop (do NOT stop after a batch)
Work is continuous, not batch-and-wait. Run this loop until it can't proceed:

1. **Eligibility (optimistic rule):** a task is ready when every task it is *Waiting on* is **Complete OR already in `🔵 Claude — Review`.** You do **not** wait for review to close.
2. **Find the next task:** list open tasks in `🟦 Services — Kiro`; for each, check its *Waiting on* links; if all blockers are Complete or In Review, it's eligible.
3. **Do it, then immediately grab the next:** implement → run the acceptance-criteria command → paste the proof into a task comment → move the task to `🔵 Claude — Review` → pick the next eligible task. One task = one focused commit.
4. **Only stop when:** no eligible tasks remain, OR a task is blocked by a Michael‑owned item (e.g. a prod credential), OR a review bounce needs fixing (fix bounces first).

**Start-here set (eligible now):** `[S2] [S3] [S6] [S19] [S22] [S26] [S31] [S41] [S54] [S92]`. As those enter review, `[S4] [S7] [S14] [S42] [S44] [S47] [S48] [S55]` open up, and so on down the chain.

The rule that keeps you moving is step 4: **"only stop when no eligible task remains."** Don't halt to ask after each batch.

## Handoff point
`[S95]` is the finish line: all automated checklist items PASS, Michael‑owned items marked PENDING, `storied-v2.2.0-services-final` tag pushed. That commit hands off to Mobile Q and iOS Q.
