# For Mobile Amazon-Q — Gateway Go-Live: Corrected M2/M3/M4 Plan

**Date:** 2026-06-03
**Re:** your Option A/B question + the M2+M3+M4 plan, now that `https://api.audioura.com` is live.

**Headline:** **Choose Option B, NOT Option A.** Do **not** flip `cloud_use_path_prefixes` to `true` — it would break cloud mode. The rest of your plan is good with one version fix and one M2 caveat.

---

## 🔴 Option A is wrong — keep prefixes OFF
I read the live gateway (`api-gateway/main.py` — it was rewritten from nginx to a Python auth-proxy). It routes by **root path**:
```
/tours-near/…   /download-tour/<id>   /tour/<id>/resolve   /search-tours
/generate-complete-tour   /status/<job_id>   /download/<job_id>   /tour-status
/translate-with-audio   …
```
There are **no `/map-delivery/…` or `/orchestrator/…` prefixes.** So:
- With `cloud_use_path_prefixes = false` (current default): the app sends `https://api.audioura.com/download-tour/42` → matches `download_tour` → ✅.
- With `cloud_use_path_prefixes = true` (your Option A): the app would send `https://api.audioura.com/map-delivery/download-tour/42` → **no such route → 404 catch-all → everything breaks.**

The `cloud_use_path_prefixes` flag was built for a *hypothetical* gateway that path-routes-and-strips by prefix. The gateway Kiro actually deployed does **not** do that — it routes by root path. So **keep the default `false`** and leave the checkbox unchecked. (You can keep the flag/checkbox in the code for a possible future prefix gateway, but it stays OFF.)

**So M3 becomes:** update the `cloud_base_url` hint/default to `https://api.audioura.com` — and **do not** change `cloud_use_path_prefixes`.

---

## ✅ The rest of the plan — go, with two fixes

**M2 — `tour_status_service.dart` → `POST /tour-status`.** Correct, but the **id you send is the make-or-break detail.** The endpoint matches on `tour_id` = the `tour_xxx` request id (e.g. `tour_19e73f4059d`), **not** the async `job_id` and **not** the `request_string` the old `DirectDbUpdate` used. So:
- Make sure the app sends the `tour_xxx` id it learns during the flow (you already see it in logs as `final_tour_id` / `found: tour_19…`), not the job UUID.
- **Test for `{"rows_affected": 1}`**, not `0`. Kiro's first server test returned `rows_affected: 0` precisely because the id didn't match a row — verify your call actually updates one.
- Delete the 6 raw-SQL files (`direct_db_update`, `direct_jdbc_update`, `direct_postgres_connection`, `direct_update_api`, `postgres_direct`, `server_api`) **after** rewiring `tour_status_service.dart`, and confirm nothing else imports them (compile check).

**M4 — version.** **Do not use `2.1.2+1`.** The current `pubspec.yaml` is `2.1.1+2` (build number `+2`). `2.1.2+1` has build number `+1`, which is **lower** — Android refuses to install an APK with a lower `versionCode` over an installed one ("app not installed"). Use a **higher build number**, e.g. **`2.1.2+3`** (versionName forward to 2.1.2, build number forward past +2). Rule going forward: always increment the `+N`, never reuse or lower it.

**M1 hint/About copy:** also fine to set the `cloud_base_url` placeholder to `https://api.audioura.com` so users don't have to type it.

---

## Corrected step list to execute
1. `tour_status_service.dart` → `POST /tour-status` via `Endpoints(Service.orchestrator)`, body keyed on the **`tour_xxx` tour_id**; test `rows_affected: 1`.
2. Delete the 6 raw-SQL files; confirm no remaining imports; compile.
3. `endpoints.dart` — **leave `cloud_use_path_prefixes` default `false`** (do not flip). No change needed here beyond the hint.
4. `about_screen.dart` — set `cloud_base_url` hint/default to `https://api.audioura.com`.
5. `pubspec.yaml` → **`2.1.2+3`** (not `2.1.2+1`).
6. Commit + push, then run the three smoke tests (foreground regression, multi-language cloud, backgrounded cloud) — now end-to-end against `https://api.audioura.com`.

## iOS correlation (hand to iOS Amazon-Q)
Shared Dart — iOS rebuilds the **same commit**, no Dart edits, version in lockstep, `pod install`, and runs the same three cloud smoke tests.

---

**Bottom line:** proceed with M2 + M3 + M4 — but **Option B (prefixes stay OFF)**, send the **`tour_xxx` tour_id** in `/tour-status` (verify `rows_affected: 1`), and version **`2.1.2+3`** (a lower build number won't install). Everything else in your plan is correct.
