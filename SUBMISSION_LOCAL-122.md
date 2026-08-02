##### READY FOR REVIEW

# SUBMISSION_LOCAL-122: Refresh SUBSCRIBED_STATUS.md

**Commit:** `f360c02`  
**Branch:** `kiro/local122-subscribed-status-refresh`  
**Base:** `subscribed`  
**Agent:** Mac Mini Kiro  
**Date:** 2026-08-02

---

## Per-file changes

| File | Lines +/- | Description |
|------|-----------|-------------|
| `SUBSCRIBED_STATUS.md` | +315 / −178 | Full refresh: reconcile with RETURN_BRIEFING, correct per CLAIM_AUDIT, bring current |

---

## The two-document question

**Decision: Keep `SUBSCRIBED_STATUS.md` as a billing-only deep dive. Do NOT
retire it. Do NOT fold it into the briefing.**

**Reasoning:**

1. `RETURN_BRIEFING.md` (on `storied`) is 200+ lines covering tour quality,
   infrastructure, swipe personalization, unwired features, Docker state,
   decisions, and corrections. It is a "what happened" document.

2. `SUBSCRIBED_STATUS.md` answers a different question: "how does the billing
   system work, what is proven, and what do I do to ship it?" — the cost
   table, the tier-switch matrix, the Apple setup checklist, the
   proven/stubbed/needs-Michael breakdown.

3. Folding billing detail into the briefing would bury it (the briefing
   already has 6 sections and a reference table). A reader looking for "how
   much does a translation cost the user" would have to scan past tour quality
   findings and Docker diagnostics.

4. Retiring `SUBSCRIBED_STATUS.md` and pointing to the briefing removes the
   only place where all billing specifics are collected in one view.

**Governance rule:** If the two documents disagree, `SUBSCRIBED_STATUS.md`
governs on billing topics; `RETURN_BRIEFING.md` governs on everything else.

---

## Corrections applied (original claim alongside correction)

| # | Original claim (verbatim) | Correction | Source |
|---|---------------------------|------------|--------|
| 1 | "tour_generate $0.0633 our cost → user $0.32 (×5 multiplier)" | Mean measured at $0.0682 over 5 runs → user $0.34 | LOCAL-100 (5 runs, isolated stack) |
| 2 | "Tier-change via HTTP will 500. `tier_change.py` is not COPY'd into the orchestrator Dockerfile yet." | All six transitions work over HTTP. LOCAL-90 added the module to `Dockerfile.orchestrator` and proved all transitions. | SUBMISSION_LOCAL-90 |
| 3 | "Stale-image detection — correctly reports FRESH for all 15 healthy services (was falsely reporting STALE on 12 of them)" | Three containers ARE genuinely stale (running LOCAL-86 private images). Detection works correctly — what it reports stale IS stale. The fix was to the detector's comparison logic, not to the containers. | Original §6 already contained this info in a different section |
| 4 | Row count implicitly "60" (stated during tour-29 restoration) | Row count is now **88** — grew through test generations, all marked `is_test=true` via LOCAL-103's HTTP test-mode mechanism | SUBMISSION_LOCAL-103, LOCAL-104 |

**CLAIM_AUDIT cross-check:** The seven Acted-Upon claims in `CLAIM_AUDIT.md`
(on `storied`) concern `UNWIRED_AUDIT.md` (4 claims about mobile app callers
that don't exist), `SUBMISSION_LOCAL-95.md` (callback count from substring
matching), `SUBMISSION_LOCAL-98.md` (6/6 fact coverage not reproducible), and
`RETURN_BRIEFING.md` (tour hook claim). **None of the seven Acted-Upon claims
appear in `SUBSCRIBED_STATUS.md`** — they are all in other documents. No
correction from `CLAIM_AUDIT.md` was needed in this file.

---

## Branch attribution (every app claim now names its branch)

The refreshed document marks every feature with its branch:

- **`subscribed`:** Wallet UI, wallet API, entitlement gate, pricing engine,
  tier switching, swipe preferences (backend + Dart UI), charging wire,
  isolated deployment, RevenueCat provider
- **`storied`:** Cost metering (merged into both), stale-image detection, news
  cache, tour quality gate, sharing, spine quality gate
- **`storied` + `subscribed`:** Cost metering exists on both (LOCAL-60 merged
  to storied via D12, then into subscribed)

The document explicitly notes that Michael's phone talks to `storied`
containers (port 5002) and that `subscribed` features (wallet, preferences)
live on port 5102 until merge.

---

## New content added

1. **§4 Current blockers** — Docker builder hung (with impact statement),
   port-map mismatch between Dart app and subscribed stack
2. **§6 Tour quality gate** — mean 98.8, worst 87.8, gate ≥75, cleared
3. **§7 Swipe personalization loop** — closed end-to-end over HTTP, with the
   known port-map gap
4. **§9 Corrections** — explicit table showing what the original said and what
   is now known
5. **§10 Proven / Stubbed / Needs Michael** — one-place summary answering "what
   can I trust, what is aspirational, and what only I can do"

---

## What was removed

- The original "Stale-image detection" entry in §1 (detection is infrastructure,
  not billing — belongs in the briefing)
- The original "Test tour pollution fixed" entry (operational hygiene, not billing)
- The "Isolated deployment" section's E2E pass claim (the subscribed E2E depends
  on which container image is running; restated as "stack stands up correctly")
- Verbose evidence formatting (cost breakdown tables) replaced with summary +
  source reference

---

## Limitations

1. **Cannot verify `RETURN_BRIEFING.md` or `CLAIM_AUDIT.md` are present in this
   worktree** — they exist on `storied` but not on `kiro/local122-*`. I read them
   via `git show storied:RETURN_BRIEFING.md`. A reader on this branch must check
   `storied` for those files.

2. **No submissions LOCAL-112 through LOCAL-121 exist in this worktree** — some
   are on `storied` (LOCAL-113, LOCAL-120). Facts drawn from them (persona wired,
   referral wired, audit severity method) were verified via `git show` but are not
   directly readable from `ls`.

3. **The port-map mismatch (§4) is reported, not fixed.** Fixing it requires either
   a Dart code change (adjusts the app) or merging subscribed into storied (Michael's
   call). Neither is in scope for a documentation task.

4. **Docker builder state not independently verified in this task.** The claim
   "builder is hung" is carried from the task file and from `RETURN_BRIEFING.md`
   — not re-tested here (per constraint: no Docker builds).

5. **Row count stated as 88** — carried from SUBMISSION_LOCAL-103/104/107. Not
   re-queried (no DB access attempted in this documentation-only task).
