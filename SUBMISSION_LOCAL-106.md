##### READY FOR REVIEW

# SUBMISSION_LOCAL-106: End-to-End Swipe Loop — Gesture to Reordered Tour

**Task:** LOCAL-106 — Prove the swipe loop closes: gesture → preference vector → reordered tour  
**Branch:** `kiro/local106-swipe-e2e`  
**Author:** Mac Mini Kiro  
**Date:** 2026-08-01  

---

## Commit

commit: 30f2fa5
git rev-list --count subscribed..HEAD: 1

## Files Changed

| File | Lines | Purpose |
|------|-------|---------|
| tests/test_local106_swipe_e2e.py | 284 (new) | 6-step end-to-end scenario proving the swipe loop closes |
| SUBMISSION_LOCAL-106.md | this file | Submission artifact |

---

## Design Decisions

### 1. Why no live generation ($0.00 cost)

The task requires `is_test: true` to prevent polluting audio_tours. However, the running
orchestrator container does not have `TOUR_TEST_MODE=true` or `TOUR_TEST_MODE_ALLOW_REQUEST=true`
set — meaning the `is_test` request field would be silently ignored (line 1265 of
tour_orchestrator_service.py). A live generation would add a non-test row to audio_tours,
violating the "no DELETE FROM audio_tours" + "row count 88" constraint.

Instead, the test uses the **same stop_metrics data** that `generate_tour_text.py` reads
during Phase 4.5 to construct the stop ordering. This exercises the identical code path
(`bias_stop_ordering()`) that the orchestrator calls after generation.

### 2. Why Python-level calls for feedback instead of HTTP

The Dart app calls `POST /user/<user_id>/stop-feedback` on the orchestrator. This test
proves that route returns HTTP 404 — the function `register_preference_routes()` exists in
swipe_preference_service.py but is **never called** by any Flask app. The test calls
`record_feedback()` directly (the function the route *would* invoke) to prove the rest of
the pipeline works. The HTTP seam gap is reported as a finding.

### 3. Undo modeled as reversal swipe

The Dart `StopFeedbackService.undoLastSwipe()` (line 96-126) removes the entry from
the local queue if unsent, or records an opposite swipe if already flushed to server.
The test exercises the "already sent" path: recording `swipe: +1` to reverse a prior
`swipe: -1`. This is the exact server-side undo path.

### 4. Isolation proof via independent users with UUID-based IDs

User B is created with a fresh UUID-suffixed ID, has zero swipes, and gets `get_user_prefs() == None`
(cold start). `bias_stop_ordering()` with `user_id=USER_B` must return quality-only order
identical to the baseline. This proves the per-user keying in `user_class_prefs` works
and preferences cannot leak.

---

## Evidence

### Step 1 — Baseline order (16 Nice stops, quality-only)

```
  Baseline (quality-only) stop order:
     1. Castle Hill                              i_con=5.0 [historic]
     2. Cours Saleya Market                      i_con=5.0 [historic]
     3. Old Town (Vieux Nice)                    i_con=5.0 [historic]
     4. Place Masséna                            i_con=5.0 [historic]
     5. Place Rossetti                           i_con=5.0 [historic]
     6. Castle Hill (Colline du Château)         i_con=4.6 [historic]
     7. Palais de Justice                        i_con=4.6 [historic]
     8. Russian Orthodox Cathedral               i_con=4.6 [historic]
     9. Museum of Modern and Contemporary Art (M i_con=4.5 [historic]
    10. Nice Cathedral                           i_con=4.2 [historic]
    11. Nice Opera House                         i_con=4.2 [historic]
    12. Palais Lascaris                          i_con=4.2 [historic]
    13. Marc Chagall National Museum             i_con=4.0 [historic]
    14. Albert 1st Gardens                       i_con=3.8 [historic]
    15. Promenade des Anglais                    i_con=3.8 [historic]
    16. Lascaris Palace                          i_con=3.0 [historic]
```

### Step 2 — Swipe via the app's endpoint

```
  2a. Proving HTTP seam gap (the orchestrator does NOT register preference routes):
    HTTP 404 from orchestrator /user/.../stop-feedback
    ⚠ INTEGRATION SEAM BUG CONFIRMED: Route not registered on orchestrator

  2b. Calling record_feedback() directly (the Python function the route would call):
    Disliking 2 historic-heavy stops:
      DISLIKE: Castle Hill (h=0.40)
      DISLIKE: Cours Saleya Market (h=0.40)
    Liking 2 social/details-heavy stops:
      LIKE:    Lascaris Palace (s=0.33)
      LIKE:    Promenade des Anglais (s=0.32)
    4 swipes recorded successfully
```

### Step 3 — Derived preference vector (legible)

```
  Preference vector for test_local106_user_a:
    pref_details:  0.5095
    pref_historic: 0.4847
    pref_social:   0.5071
    swipe_count:   4
    interpretation: "neutral on details (0.51); neutral on social (0.51); neutral on historic (0.48)"
    confidence:    {'details': 1.26, 'historic': 1.49, 'social': 1.25}
  ✓ Vector is legible and reflects swipes (historic disliked → 0.4847 < 0.5)
```

### Step 4 — Regenerate same venue, order differs, disliked class still present

```
  Biased stop order (with preferences):
     1. Castle Hill                         combined=0.8497 =0
     2. Cours Saleya Market                 combined=0.8497 =0
     3. Old Town (Vieux Nice)               combined=0.8497 =0
     4. Place Masséna                       combined=0.8497 =0
     5. Place Rossetti                      combined=0.8491 =0
     6. Palais de Justice                   combined=0.7937 ↑1
     7. Russian Orthodox Cathedral          combined=0.7937 ↑1
     8. Castle Hill (Colline du Château)    combined=0.7932 ↓2
     9. Museum of Modern and Contemporary A combined=0.7797 =0
    10. Palais Lascaris                     combined=0.7377 ↑2
    11. Nice Opera House                    combined=0.7376 =0
    12. Nice Cathedral                      combined=0.7373 ↓2
    13. Marc Chagall National Museum        combined=0.7097 =0
    14. Promenade des Anglais               combined=0.6821 ↑1
    15. Albert 1st Gardens                  combined=0.6816 ↓1
    16. Lascaris Palace                     combined=0.5701 =0

  ✓ Order differs from baseline
  ✓ Disliked class (historic) still present — bias, not filter
```

### Step 5 — Undo one swipe, vector moves back

```
  pref_historic BEFORE undo: 0.4847
  Recorded reversal swipe (+1) for: Cours Saleya Market
  pref_historic AFTER undo:  0.5376
  Delta: +0.0529
  ✓ Vector moved back measurably (Δ = +0.0529)
```

### Step 6 — User B (untouched) gets unbiased order — ISOLATION PROOF

```
  User B preferences: None (cold start) ✓
  User B stop order:
     1. Castle Hill                         combined=1.0000 rank_change=0
     2. Cours Saleya Market                 combined=1.0000 rank_change=0
     3. Old Town (Vieux Nice)               combined=1.0000 rank_change=0
     4. Place Masséna                       combined=1.0000 rank_change=0
     5. Place Rossetti                      combined=1.0000 rank_change=0
     6. Castle Hill (Colline du Château)    combined=0.9200 rank_change=0
     7. Palais de Justice                   combined=0.9200 rank_change=0
     8. Russian Orthodox Cathedral          combined=0.9200 rank_change=0
     9. Museum of Modern and Contemporary A combined=0.9000 rank_change=0
    10. Nice Cathedral                      combined=0.8400 rank_change=0
    11. Nice Opera House                    combined=0.8400 rank_change=0
    12. Palais Lascaris                     combined=0.8400 rank_change=0
    13. Marc Chagall National Museum        combined=0.8000 rank_change=0
    14. Albert 1st Gardens                  combined=0.7600 rank_change=0
    15. Promenade des Anglais               combined=0.7600 rank_change=0
    16. Lascaris Palace                     combined=0.6000 rank_change=0

  ✓ User B order == baseline (unbiased) order
  ✓ NO PREFERENCE LEAKAGE — User A's swipes did NOT affect User B
  ✓ All rank_change = 0 for User B (cold start behaviour preserved)
  ✓ User A (personalized) ≠ User B (unbiased) — per-user isolation confirmed
```

### Constraints verified

```
audio_tours row count BEFORE: 88
audio_tours row count AFTER:  88
tours-near/43.7009358/7.2683912?radius=50 = [1, 12, 14, 17, 21, 24, 27, 28, 29]  ✓
```

---

## Integration Seam Finding: CRITICAL

### Bug: Preference API routes not registered on any running service

**Symptom:** `POST /user/<user_id>/stop-feedback` returns HTTP 404 on the orchestrator.

**Root cause:** `swipe_preference_service.py:302` defines `register_preference_routes(app)` but
this function is **never called** by any Flask app in the codebase. The orchestrator, user-api,
and all other running services do not import or invoke it.

**Impact:** The Dart app (`stop_feedback_service.dart:258`) calls:
```dart
final response = await Endpoints.post(
  Service.orchestrator,           // ← port 5002
  '/user/$userId/stop-feedback',  // ← this route doesn't exist
  body: body,
  timeout: const Duration(seconds: 10),
);
```
Every swipe from every user silently fails with 404. The offline retry queue (`_maxRetries=10`)
eventually drops the entry after 10 attempts (line 222). The preference system has never
received a single real user swipe.

**Fix required:** Add `register_preference_routes(app)` to `tour_orchestrator_service.py`
(one line, near the other route registrations). Alternatively, host it on a dedicated service
or the user-api.

### Secondary: is_test flag not active on running stack

The constraint specifies `is_test: true` for test generations. The running orchestrator
container lacks `TOUR_TEST_MODE=true` and `TOUR_TEST_MODE_ALLOW_REQUEST=true` env vars.
The `is_test` request field is silently ignored (tour_orchestrator_service.py:1265-1267).
A live generation would insert a non-test row, violating the row-count constraint.

This env var IS set in `docker-compose-master.yml` (line 75: `TOUR_TEST_MODE_ALLOW_REQUEST=true`)
but the running containers were not started from that file.

---

## What was tested live vs. stubbed

| Component | Live / Stubbed | Notes |
|-----------|---------------|-------|
| PostgreSQL (stop_metrics, user_stop_feedback, user_class_prefs) | **LIVE** | Real DB via tests/db_connection.py |
| `record_feedback()` — write to user_stop_feedback + update prefs | **LIVE** | Direct Python call to real DB |
| `get_user_prefs()` — read preference vector | **LIVE** | Reads from real user_class_prefs table |
| `bias_stop_ordering()` — reorder stops with preferences | **LIVE** | Uses real preference data from DB |
| HTTP `POST /user/.../stop-feedback` on orchestrator | **LIVE** | Called to confirm 404 (seam bug) |
| HTTP `GET /tours-near/...` on map-delivery | **LIVE** | Confirms 9 Nice tours unchanged |
| Tour text generation (GPT calls) | **NOT CALLED** | Used existing stop_metrics instead |
| Dart app `StopFeedbackService` | **NOT CALLED** | Python-side proves the backend path |

---

## Limitations

1. **No live generation was performed.** The `is_test` flag is not active on the running
   stack, and generating without it would violate the audio_tours row-count constraint.
   The test uses existing stop_metrics data to prove the ordering logic without incurring
   cost or inserting rows.

2. **The HTTP seam between app and backend is broken.** This is reported as a finding,
   not papered over. The Python functions work correctly; only the HTTP route registration
   is missing.

3. **Nice stop_metrics are all historic-dominant.** The class diversity is limited
   (all stops have class_historic ≥ 0.34), which means the preference delta is smaller
   than it would be with a venue having truly diverse content classes. The ordering
   still changes (6 stops moved), proving the mechanism works.

4. **Undo is modeled as reversal swipe, not DB deletion.** This matches the Dart app's
   "already flushed" undo path but means the swipe_count increases (5 after undo, not 3).
   The Dart app's "not yet sent" undo path (queue removal) was not tested at the backend.

5. **Cost: $0.00.** No LLM calls were made. Each generation for this venue would cost
   approximately $0.068 (the stated baseline). The test proves the ordering logic without
   incurring any generation cost.
