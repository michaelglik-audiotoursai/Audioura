##### READY FOR REVIEW

# LOCAL-120: Audit Severity Method — Diagnose Failure, Write Checklist, Re-verify

**Branch:** `kiro/local120-audit-severity-method`  
**Commit:** (see below)  
**Agent:** Mac Mini Kiro  
**Date:** 2026-08-02

---

## Summary

The UNWIRED_AUDIT (LOCAL-108) correctly detected all 6 deduplicated UNWIRED
symbols (zero importers / zero call sites). Its **severity justification** was
wrong in 4 of 6 cases — a 67% error rate on the judgement that drives task
priority and dispatch. In every wrong case, the audit claimed "the mobile app
calls this endpoint and gets 404" without reading a single Dart file.

---

## 1. Diagnosis: Why the Severity Method Failed

### The two errors identified by the task

| Symbol | Audit claimed | Reality | What would have caught it |
|--------|--------------|---------|--------------------------|
| `persona_endpoints.py` | "Mobile persona UI sends these requests to 404" | Zero Dart files call POST/GET /user/persona. App stores persona locally via SharedPreferences. | `grep -rn "persona" audio_tour_app/lib/` → 2 hits, both are comment lines about "personalization", none are HTTP calls |
| `tour_hook_generator.py` | "hook never becomes audio" | Hook IS consumed at `generate_tour_text.py:6091`, fed to prolog prompt, expanded 80-190 words, injected into Stop 1, goes through TTS | `grep -rn "tour_hook" generate_tour_text.py` → line 6091: `_tour_hook = _storied_spine.get("tour_hook", "")` |

### Root cause (shared by both)

The audit inferred **impact** from **absence of callers** without verifying the
other side of the connection:

1. Persona: assumed the mobile app calls the endpoint because the endpoint
   "sounds user-facing." Never checked whether any Dart file makes that HTTP call.
2. Tour hook: assumed the module is the only path from hook-field to audio.
   Never searched for the field name (`tour_hook`) across the full codebase —
   only searched for the module name (`tour_hook_generator`).

**The logical gap:** "Module X has zero importers" + "Module X implements feature
Y" ≠ "Feature Y is broken." Feature Y may be implemented elsewhere, or the
client may not exercise it yet.

---

## 2. Severity Checklist for Future Audits

Before assigning severity above "server-side gap" to any UNWIRED finding:

- [ ] **1. Identify the claimed caller.** Name the specific file and line that
  exercises the dead code. "The mobile app" is insufficient.
- [ ] **2. Verify the caller exists.** Grep the client codebase (Dart/JS/etc.)
  for the URL path, endpoint name, or feature keyword. Record command + output.
- [ ] **3. Trace the data path, not just the module.** If the claim is "field X
  is never consumed," grep for the field name across ALL files. Another path
  may already handle it.
- [ ] **4. Observe the breakage.** Show: (a) the client code making the call,
  (b) the URL it targets, (c) the route that should handle it. If (a) doesn't
  exist, severity is "server gap for future use."
- [ ] **5. Distinguish superseded from missing.** Search for the function's
  *purpose* (not its name). If done by different code, the module is DEAD
  (superseded), not UNWIRED.

**Rule:** A finding that fails check #2 (no caller in client) CANNOT be
classified as "broken user-facing feature."

---

## 3. Re-verification of the Remaining Four

### 3a. `sharing_endpoints.py` (POST /tour/share)

**Original audit claim:** "Share button in app is non-functional for creating new shares"

**Re-verification against checklist:**
- Check #1 (identify caller): audit claimed "share button in app"
- Check #2 (verify caller exists): `grep -rn "share\b\|tour/share\|Icons.share" audio_tour_app/lib/` → **zero hits** for share URL or share button
- Check #4 (observe breakage): no client code makes this call

**Corrected verdict:** UNWIRED detection was correct (blueprint was unregistered
at time of audit). Severity was **overstated** — no share button exists in the
mobile app. Server-side capability gap for future use. Now wired (LOCAL-110).

**Was the wiring task correct?** Yes — the endpoint works correctly and should
be available. The priority framing ("broken user-facing feature") was wrong.

---

### 3b. `referral_endpoints.py`

**Original audit claim:** "The mobile app has referral UI (LOCAL-52). All requests 404."

**Re-verification against checklist:**
- Check #1 (identify caller): audit cited "LOCAL-52" as the referral UI task
- Check #2 (verify caller exists): `grep -rn "referral" audio_tour_app/lib/` → **zero hits**
- Check #4 (observe breakage): no Dart file makes any referral HTTP call

**Corrected verdict:** UNWIRED detection was correct. Severity was **overstated**
— no referral UI exists in the mobile app. The reference to LOCAL-52 appears to
be a planned/future feature. Server-side capability gap. Now wired (LOCAL-114).

**Was the wiring task correct?** Yes — the referral engine and endpoints work
correctly. Priority framing was wrong.

---

### 3c. `register_preference_routes`

**Original audit claim:** "every swipe from every user returns 404. The mobile app
sends these requests; they silently fail."

**Re-verification against checklist:**
- Check #1 (identify caller): audit claimed "the mobile app"
- Check #2 (verify caller exists): `grep -rn "stop-feedback\|stop_feedback\|user.*preferences" audio_tour_app/lib/` → **zero hits** for preference/swipe API calls
- Check #2 (additional): `grep -rn "swipe\|like\|dislike\|thumbs" audio_tour_app/lib/` → zero hits for swipe UI elements
- Check #4 (observe breakage): no swipe-to-rate UI exists in the mobile app

**Corrected verdict:** UNWIRED detection was correct. Severity was **overstated**
— no swipe UI exists in the mobile app. Server-side capability for future
client-side swipe feature. Now wired (LOCAL-112).

**Was the wiring task correct?** Yes. Priority framing was wrong.

---

### 3d. `spine_quality_scorer`

**Original audit claim:** "no spine quality gate on spine generation. A low-quality
spine passes through unchecked."

**Re-verification against checklist:**
- Check #1 (identify caller): no mobile caller claimed — this is a server-internal quality gate
- Check #2 (N/A): claim is server-side, not client-facing
- Check #3 (trace data path): the spine flows directly from `generate_spine()` to tour text generation. No intermediate scoring existed.
- Check #4 (observe breakage): breakage is low-quality tour narratives, not a 404. Observable only in output quality.

**Corrected verdict:** UNWIRED detection was correct. Severity was **correctly
stated**. The audit made no mobile-breakage claim. It correctly identified a
missing server-side quality gate. Now wired (LOCAL-111) with threshold of 2/4
and one retry.

**Was the wiring task correct?** Yes, and severity framing was accurate.

---

## 4. Summary Table — All Six Findings

| # | Symbol | Detection | Severity claim | Severity correct? | Now wired? | Evidence |
|---|--------|-----------|---------------|-------------------|------------|----------|
| 1 | `persona_endpoints.py` | ✓ Correct | "Mobile UI sends to 404" | ✗ Wrong — no Dart caller | Yes (LOCAL-113) | `grep "persona" audio_tour_app/lib/` = 0 HTTP calls |
| 2 | `tour_hook_generator.py` | ✓ Correct | "hook never becomes audio" | ✗ Wrong — superseded, hook reaches audio via prolog | Reclassified DEAD | `generate_tour_text.py:6091` consumes field |
| 3 | `sharing_endpoints.py` | ✓ Correct | "Share button non-functional" | ✗ Wrong — no share button in app | Yes (LOCAL-110) | `grep "share\b" audio_tour_app/lib/` = 0 share UI |
| 4 | `referral_endpoints.py` | ✓ Correct | "mobile app has referral UI" | ✗ Wrong — no referral UI exists | Yes (LOCAL-114) | `grep "referral" audio_tour_app/lib/` = 0 hits |
| 5 | `register_preference_routes` | ✓ Correct | "every swipe returns 404" | ✗ Wrong — no swipe UI in app | Yes (LOCAL-112) | `grep "stop-feedback" audio_tour_app/lib/` = 0 |
| 6 | `spine_quality_scorer` | ✓ Correct | "no quality gate" | ✓ Correct — server-side gap | Yes (LOCAL-111) | No mobile claim made; gap was real |

### Error rate

- **Detection:** 6/6 correct (100%)
- **Severity:** 4/6 wrong (67% error rate on severity justification)
- **Impact:** All 4 wrong-severity findings were reported to the owner as
  "broken user-facing features" and dispatched as tasks. The wiring was still
  correct to do, but the priority framing overstated urgency.

---

## Per-File Changes

| File | Change |
|------|--------|
| `UNWIRED_AUDIT.md` | Amended — added LOCAL-120 correction section (per-symbol table, diagnosis, checklist, corrected counts) |
| `SUBMISSION_LOCAL-120.md` | New — this file |

---

## Verbatim Evidence

### Evidence: persona endpoint not called by mobile app

```
$ grep -rn "persona" audio_tour_app/lib/ | grep -v SharedPreferences | grep -v shared_pref
audio_tour_app/lib/screens/tour_generator_screen.dart:192:      // Include narrative tone from onboarding (Storied personalization)
audio_tour_app/lib/screens/tour_generator_screen.dart:1366:      // Include narrative tone from onboarding (Storied personalization)
```

Two comment lines. Zero HTTP calls to `/user/persona`.

### Evidence: referral not called by mobile app

```
$ grep -rn "referral" audio_tour_app/lib/
(empty — zero results)
```

### Evidence: sharing POST not called by mobile app

```
$ grep -rn "tour/share\|/share" audio_tour_app/lib/
(empty — zero results)
```

### Evidence: swipe/preference endpoint not called by mobile app

```
$ grep -rn "stop-feedback\|stop_feedback\|/preferences" audio_tour_app/lib/
(empty — zero results)
```

### Evidence: tour_hook IS consumed via prolog path

```
$ grep -n "tour_hook" generate_tour_text.py
6091:    _tour_hook = _storied_spine.get("tour_hook", "")
6142:        f"Tour hook: {_tour_hook}\n"
```

Line 6091: extracted. Line 6142: fed to GPT-3.5 prolog prompt. Result → Stop 1 text → TTS.

### Evidence: spine_quality_scorer now wired

```
$ grep -n "score_spine" generate_tour_text.py
4782:                    from spine_quality_scorer import score_spine as _score_spine
4783:                    _sq_score, _sq_breakdown = _score_spine(_storied_spine, total_stops=len(_poi_names))
4800:                            _retry_score, _retry_breakdown = _score_spine(_retry_spine, total_stops=len(_poi_names))
```

Quality gate with threshold 2/4 and one retry. Wired at LOCAL-111.

---

## Limitations

1. **Analysis only — no Docker builds.** Docker builder hung (constraint). All
   verification is grep/AST/static reading.
2. **Dart client check is grep-based.** If the mobile app uses string
   interpolation to construct URLs without the literal endpoint name, grep would
   miss it. However, the Endpoints class in `audio_tour_app/lib/config/endpoints.dart`
   centralizes all service URLs and uses named constants — no dynamic construction
   observed.
3. **Cannot verify Cloud Run production deployment.** The `main` branch may have
   different client code.
4. **"Planned feature" attribution is inference.** When I say "server-side API
   for future use," this is inferred from the absence of a client caller. It may
   also be dead code from an abandoned feature — the distinction requires product
   knowledge I don't have.
5. **The task states 33% (2/6) error rate; analysis shows 67% (4/6).** The
   additional two (sharing, referral) made the same error pattern as persona
   (claimed mobile breakage without checking Dart). Whether these count depends
   on whether the task's "six" refers to the 6 deduplicated UNWIRED findings or
   a different grouping. I report what the evidence shows.
