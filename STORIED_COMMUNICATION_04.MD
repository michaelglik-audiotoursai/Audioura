# STORIED_COMMUNICATION_04.MD

Opened 2026-09-23, continuing from `STORIED_COMMUNICATION_03.MD` (closed at 97 KB).
Volumes 01 and 02 are closed. **This is the live volume — maintain it here.**

## The rule for this file

Michael's questions verbatim and LEAD's final answers, chronological. **Questions and
conclusions only** — no tool output, no status chatter, no reasoning trace. If an
entry takes more than a minute to read it belongs in `DECISIONS.md` with a pointer
from here. Volume 01 reached 123 KB by ignoring this and became unsearchable; Volume
03 reached 97 KB the same way.

Append the exchange **before starting the next task**, not at session end — sessions
are killed and restarted by design (D252) and anything held only in context is lost.

---

## State at the moment this volume opened

**Tours.** Round 7's ten defects: four fixed and verified, four merged today, one
retired, one (LOCAL-528, anachronistic material on a part) completed but unreviewed.
Round 9 was generating — the first batch with every fix merged, same two venues as
rounds 7 and 8 so the comparison is clean.

**The one open quality problem.** Deterministic defects are fixed and stay fixed.
What survives is everything that requires knowing something about the world, and it
all scores CLEAN: Eiffel building Boston Logan, a church's dedication rendered as its
founder, Lindbergh landing on a jet bridge thirty years before jet bridges. LOCAL-527
now scores the first two; LOCAL-528 targets the third.

**Cost.** ~$0.21 per 4-stop tour, measured. **That excludes grounding** (~3.5c per
request, independent of tokens). LOCAL-533 will split them. Do not optimise before it
lands. Caching already works; the lever is hit rate (D581).

**Infrastructure.** Docker recovered by killing the backend process, not restarting
the app — data intact, 168 rows, and a factory reset must never be used because
`postgres_data` is a named volume the backup does not cover. The dispatcher now
requires an explicit allowlist and fails closed (D587) after releasing 35 tasks when
4 were intended.

**Open for Michael.** Hard drive chosen for active Docker/worktree work — he has dock
extensions, so no port-hub premium is needed. Subscribed untouched; Igor's E2E
(LOCAL-524) is the starting point, and it currently fails.

**Standing instruction as of the /clear:** finish round 9, run the Amazon-Q critique,
analyse it rather than trusting it, and **tell Michael when it comes back with nothing
left to fix.** Full detail in `REMINDER_NEXT_SESSION.md`.

---
