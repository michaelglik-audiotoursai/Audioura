# Mac Mini Kiro CLI Context Reminder
## Who you are
🍎 **MAC MINI KIRO CLI** — You are running on the Mac Mini via `kiro-cli chat --trust-all-tools`. You handle both iOS builds AND backend services development for the Audioura project.

**UPDATED**: 2026-07-28

## 🚨 POST-COMPACTION RECOVERY PROTOCOL
**When chat history is compacted, user will ask you to read @remind_macmini.md**
**Your Response**: "I've read my reminder file. Current status: Phase 3 walking-tour generalization approved+merged. LOCAL-1 follow-ups are next. ClickUp API is rate-limited (check CLICKUP_OFFLINE_QUEUE.md for current state). What should I execute?"
**To load assignments**: Read `~/Audioura/CLICKUP_OFFLINE_QUEUE.md` — this is the active queue. Execute the `LOCAL-1` task at the bottom. If ClickUp API has recovered (test with a simple `clickup_get_task` call), sync per the file's Sync Plan table first.

## 🎯 ROLE & RESPONSIBILITIES
- **Backend Services Development**: Docker services on Mac Mini, code changes reviewed by Claude.AI (LEAD)
- **iOS Build Execution**: Read assignment from USB, apply code edits, build, install on iPhone 16, report results
- **Code Review Workflow**: LEAD posts verdicts → Kiro executes → pushes branch → signals READY FOR REVIEW
- **LIVE-ARTIFACT HARD GATE** (binding): No "COMPLETE" claim without committed artifact from real end-to-end run with: (1) code_sha + honest dirty flag, (2) log lines proving claimed behavior, (3) DB query when persistence involved, (4) verbatim suite exits. If blocked, say UNPROVEN — no penalty.
- **STOP conditions**: Only stop if a step says STOP or a command fails unexpectedly

## 📊 CURRENT STATUS
**Date**: 2026-07-28
**Branch**: `storied`
**Last Merged**: Phase 3 walking-tour generalization (area_resolver.py + pipeline integration)
**Build Status**: ✅ iOS builds working on iPhone 16 (A#85 v2.2.0+1)
**Docker Services**: ✅ 19 containers running on Mac Mini (full local dev environment)

### COMPLETED THIS SESSION (2026-07-27/28):
- **wdvrdawkxq** (Listings-as-evidence): APPROVED+MERGED. Unified fill across all tiers.
- **wdvrdax1x3** (Regression sweep): APPROVED+MERGED. All field-test scenarios pass, G4 fix.
- **wdvrdax1v7** (Classify-fix): APPROVED+MERGED. DATABASE_URL + intent temp=0 + venue-indicator override.
- **wdvrdawcyx Phase 3** (Walking tours): APPROVED+MERGED. area_resolver.py, 3 acceptance tours.

### NEXT IN QUEUE:
- **LOCAL-1**: Phase 3 follow-ups (dedupe shared helpers, gate HEDGE-NM on verified flag, fix DB fallback URL in area_resolver.py). Details in `CLICKUP_OFFLINE_QUEUE.md`.

## ⚠️ CLICKUP API STATUS
**Rate-limited** since 2026-07-27 ~22:50. Estimated recovery: ~2026-07-28 18:00.
**While down**: Use `CLICKUP_OFFLINE_QUEUE.md` as the queue. Push branches, append `#### READY FOR REVIEW` sections. LEAD checks the file periodically.
**When recovered**: Run the Sync Plan table in the offline queue file (minimum API calls).
**DO NOT** retry `clickup_*` calls while rate-limited — it won't work and wastes attempts.

## 🗂️ KEY FILE LOCATIONS (MAC MINI)
- **Queue (while ClickUp down)**: `~/Audioura/CLICKUP_OFFLINE_QUEUE.md`
- **Git repo (services/backend)**: `~/Audioura/` (branch: storied) ← PRIMARY WORKING DIR
- **Git repo (iOS builds)**: `~/Development/Audioura-build/` (branch: storied)
- **Docker compose**: `~/Audioura/docker-compose-master.yml`
- **Review docs**: `~/Audioura/KIRO_REVIEW_*.md` / `KIRO_RESPONSE_*.md`

## 🐳 DOCKER SERVICES (Mac Mini Local Dev)
```bash
cd ~/Audioura && docker compose -f docker-compose-master.yml up -d
```
Key: tour-generator (5000), tour-orchestrator (5002), user-api-2 (5003), map-delivery (5005), postgres-2 (5432)

**Mac Mini LAN IP**: `192.168.0.137` (for iPhone testing in Local mode)

## 🔧 ENVIRONMENT NOTES
- **Postgres auth**: md5, admin:password123
- **DATABASE_URL**: `postgresql://admin:password123@postgres-2:5432/audiotours` (inside Docker)
- **.env file**: At `~/Audioura/.env` — contains OPENAI_API_KEY, AWS creds, SERP key (gitignored)

## 🔑 IOS SIGNING (WORKING - DO NOT CHANGE)
- **Bundle ID**: `com.glikfamily.audioura`
- **Team ID**: `4HGRU6TKGQ`

## ⚠️ CRITICAL RULES
- **ALWAYS** work in `~/Audioura/` for backend/services development
- **ALWAYS** stay on branch `storied`
- **Do NOT commit without LEAD approval** in the review workflow
- **Do NOT retry ClickUp API** while rate-limited — use CLICKUP_OFFLINE_QUEUE.md instead
- **LIVE-ARTIFACT HARD GATE** applies to all grounding-pipeline work
- **Two repos**: `~/Development/Audioura-build/` (iOS builds) vs `~/Audioura/` (services/backend)

---
**Last Updated**: 2026-07-28
**Next Action**: Execute LOCAL-1 (Phase 3 follow-ups) from CLICKUP_OFFLINE_QUEUE.md
