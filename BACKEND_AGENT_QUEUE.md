# Backend Agent (Services Kiro) — How to "work your queue"

**For Services Kiro.** When Sir Michael says **"work your queue,"** follow this file. **This file is NOT the task list** — the task list is a LIVE ClickUp list. Never expect tasks to be itemized here; always read them fresh from ClickUp.

## Step 0 — Confirm you're on the right ClickUp (do this first, every session)
1. The ClickUp MCP must be connected. If tools error, reconnect (`mcp-remote` → re-authorize as **michael.glik@gmail.com** — the account that owns these tasks).
2. **Self-test:** fetch task **`wdvrdaw4bt`** with `clickup_get_task`.
   - **Found** → you're on the correct workspace. Continue.
   - **Not found** → you are authenticated to the WRONG ClickUp account/workspace. Re-authorize as michael.glik@gmail.com and retry. Do not proceed until the self-test passes.

## Step 1 — Read your queue (live)
Your queue is the ClickUp list:
- **Space:** `MVP -- Release 1` (id `90137683357`)
- **List:** `🟦 Backend Agent (Kiro) — queue` — **list id `901327587897`**

List every task in that list with status **"to do"** or **"in progress"** (e.g., `clickup_filter_tasks` / `clickup_search` scoped to that list id, statuses unstarted+active). Work them **top to bottom** (highest priority / oldest first). If the list has no open tasks, report "queue empty" and stop — do NOT invent work.

> Storied / future-release tasks are **not** here — they live under the `② Storied` epic in the Go-To-Market space and get promoted into this list when scheduled. Only work what is in list `901327587897`.

## Step 2 — For each task
1. Execute per the task description.
2. Write a `REVIEW_FOR_KIRO_*.md` (or `code_review_*.md`) doc in the development directory: what changed, files + line numbers, **deployed image/revision**, and how you verified live.
3. Attach the doc to the ClickUp task, comment `Done — <doc>, revision <rev>`, then **move the task to `⏳ Waiting for Claude Review`** (list id `901327587900`) with `clickup_move_task`.
4. **Definition of done = deployed AND verified live.** Do NOT mark tasks Complete — Claude reviews and closes.
5. **Self-verify before moving to review** (verify, don't trust your own tools — check committed code / live revision).

## Guardrails — stop and ask before anything irreversible
Data deletes, billing, IAM changes, dropping/altering columns that hold live credentials, opening the gateway to anonymous traffic, or committing secrets (`key.properties`, `*.jks`, `build_secrets.env`). The gateway stays locked; if our app 401s, fix the app key, never weaken the gateway.

When you've moved your finished tasks to "Waiting for Claude Review," Sir Michael will tell Claude to review the pile.
