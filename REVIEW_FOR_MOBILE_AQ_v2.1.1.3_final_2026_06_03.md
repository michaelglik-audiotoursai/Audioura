# Review for Mobile Amazon-Q — v2.1.1+3 final (commits `4cfc29a` + `7c5cc46`)

**Date:** 2026-06-03
**Scope:** Flutter/Dart app code only.
**Readiness answer:** ✅ **Ready for LOCAL WiFi testing.** ❌ **NOT ready for CLOUD testing — even after Kiro finishes `/user`** — because of **two mobile gaps** the doc doesn't account for: the app sends no `X-API-Key` (the gateway now 401s cost endpoints), and `TranslationService` still hardcodes the LAN IP (so cloud multi-language fails). Both are mobile changes, not Kiro's.

---

## What's correct in v2.1.1+3 ✅
- **`tour_status_service.dart` rewrite:** clean, REST via `Endpoints(Service.orchestrator)`, keyed on `tour_xxx` tour_id, logs `rows_affected` with a ⚠️ on 0. Good.
- **`test_update_api.dart` deleted (Finding 1):** confirmed gone — the dangling-import problem is resolved, all 9 raw-SQL/dead files removed.
- **About-screen text (M3):** correct; `cloud_use_path_prefixes` stays `false`.
- **Version:** `2.1.1+3`, monotonic. ✅
- **Finding 2 (`/user` dependency):** correctly identified as a services issue (Kiro). Accurate.

So the M2/M3/cleanup work is well done. The problem is **what cloud generation now additionally requires** that this build doesn't provide.

## 🔴 Cloud blocker A — no `X-API-Key` header
Kiro's security fix (commit `26380ab`) made the gateway **require `X-API-Key`** on the cost-bearing/write endpoints — `/generate-complete-tour`, `/tour-status`, `/translate-with-audio`, `/process_newsletter` (401 without it). I searched the app: **`X-API-Key` appears nowhere.** Every POST sends only `{'Content-Type': 'application/json'}`. So in cloud:
- `POST /generate-complete-tour` → **401** → generation can't even start. **Hard blocker.**
- `POST /tour-status` → 401 (on top of the `/user` issue).
- `POST /translate-with-audio` → 401.

**Fix (new mobile task):** add an `X-API-Key: <key>` header to the cost-bearing POSTs (`tour_generator_screen` generate calls, `tour_status_service`, `translation_service`). The key value must be configurable — Sir Michael holds it (from Secret Manager `gateway-api-key`); store it in a build config or an About-screen field, not hardcoded in a committed file. (Note: it's only needed in **cloud** mode — local LAN services don't require it.)

## 🔴 Cloud blocker B — `TranslationService` bypasses `Endpoints`
`services/translation_service.dart:14-15` still hardcodes:
```dart
final serverIp = prefs.getString('server_ip') ?? Config.defaultServerIp;
final baseUrl = 'http://$serverIp:5030';
```
This was never migrated. In cloud mode it points at `http://192.168.0.218:5030` — the LAN IP, unreachable off-WiFi — so **multi-language tours fail at the translation step** (your smoke test 3 would fail before the Russian download). Unlike news/newsletter, translation **is** deployed (`Service.translation`, `/translate-with-audio` is routed on the live gateway), so it should be migrated now.

**Fix:** migrate to `Endpoints.url(Service.translation, '/translate-with-audio')` and drop the `serverIp`/`Config` hardcode (and add the `X-API-Key` header per blocker A, since this endpoint is key-protected).

## Your Q1 — SharedPreferences key cleanup
Low priority; acceptable as-is. Adding cleanup of `tour_id_$jobId` / `request_$jobId` after a terminal status is a nice tidy-up (prevents slow unbounded growth) but not required for this cycle. Do it when convenient.

---

## Direct answer to "ready to test after Kiro finishes?"
- **Local WiFi (smoke test 1):** ✅ ready now — no gateway, no API key, translation at `:5030` works on the LAN.
- **Cloud (smoke tests 2–4):** ❌ not ready, and **Kiro finishing `/user` is not sufficient.** Two mobile changes are still needed first:
  1. **Add `X-API-Key`** to the cost-bearing requests (blocker A) — without it, cloud generation 401s and never starts.
  2. **Migrate `TranslationService` to `Endpoints(Service.translation)`** (blocker B) — without it, cloud multi-language fails.
- After A + B (mobile) **and** `/user` + user-api (Kiro): cloud foreground generation and multi-language work; status bookkeeping (`rows_affected: 1`) comes online with `/user`. Cloud download already works.

Sequence: these two mobile fixes are a new small version (e.g. **`2.1.1+4`**). Sir Michael needs to hand you the `gateway-api-key` value for blocker A.

## iOS correlation (hand to iOS Amazon-Q)
Shared Dart — iOS rebuilds the same commit after A + B land; no Dart edits of its own.

---

## Bottom line
v2.1.1+3 is clean for what it changed (M2/M3/Finding 1 done right), and **fine to build and test on local WiFi**. But it is **not ready for cloud testing**: add the `X-API-Key` header (blocker A) and migrate `TranslationService` to `Endpoints` (blocker B) first — both are mobile-side, independent of Kiro. Kiro's `/user` fix only affects status bookkeeping, not whether cloud generation runs.
