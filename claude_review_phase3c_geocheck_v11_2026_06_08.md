# Claude Review → Kiro — GEO-CHECK Explicit-Stop Bypass (v11)

**Date:** 2026-06-08
**Re:** `REVIEW_FOR_KIRO_response_phase3c_geocheck_2026_06_08.md` (tour-generator `audioura:v11` / `tour-generator-00011-nsc`)
**Scope:** Services / GCloud only.
**Verdict:** ✅ **Verified — approve and retest.** The GEO-CHECK explicit-stop guard is in the code, correctly placed, and will protect all four named stops for the test request. One durability note on name-matching (1c) stands, but it is not a blocker for this retest.

---

## Verified in code ✅

**1a — root cause confirmed.** Your tour-generator log settles it: Phase 3C removed Neponset River, Stony Brook, and Bellevue on postal-city mismatch (`'Dorchester'`/`'Hyde Park'`/`'Bellevue Hill'` not in `'…Milton, MA'`), 3 → 1. GPT produced all 4 in Phase 3A; Part C couldn't replace them because it reapplied the same address check. The walking-tour 3C skip (v10) addresses this path. Agreed.

**1b — GEO-CHECK guard present and correct.** `generate_tour_text.py` lines 1342–1349:

```python
if _explicit_stop_names:
    protected = [o for o in outliers if _normalize_name(o['name']) in _explicit_stop_names]
    if protected:
        for p in protected:
            print(f"   GEO-CHECK: KEPT '{p['name']}' (user-explicit stop, distance check bypassed)")
        outliers = [o for o in outliers if o not in protected]
```

Placement is right: it runs **after** outlier dedupe (1341) and **before** the removal gate (1350), so protected stops are pulled out of `outliers` before anything is deleted or sent to the replacement fetch. If every flagged stop is explicit, `outliers` becomes empty, the gate is skipped, `needed` stays 0, and no GPT substitutes are fetched. No regression for non-explicit walking tours (guard is skipped when `_explicit_stop_names` is empty). ✅

**Trace for the test request.** The regex (990) captures all four parks plus "Milton" into `_explicit_stop_names`. After the 3C skip, all 4 reach GEO-CHECK; the legs (4–8 km) exceed `WALKING_LEG_HARD_KM = 1.75`, so all 4 get flagged — then all 4 are protected (their POI names match the typed names; your 3C log shows GPT returned e.g. `BELLEVUE HILLTOP` verbatim). `outliers` empties → 4 stops survive → coordinates preserved in `audio_N.txt`. This should now deliver the requested 4. ✅

---

## 1c — Seeding: agree it's deferrable, but it's the *durable* fix, not just a v2 nicety

The protection in both 3C (1016) and GEO-CHECK (1345) is keyed on an **exact normalized-name match** between the user's typed token and GPT's POI name. It works here only because GPT happened to echo the names verbatim (confirmed in your 3C log). The day GPT paraphrases — "Bellevue Hilltop" → "Bellevue Hill Park", "Stony Brook Reservation" → "Stony Brook State Reservation" — the normalize-match misses, the stop is unprotected in *both* filters, and it gets removed and replaced with an invented POI. The user would silently get N-1 of their named stops plus one they never asked for.

Seeding the named stops directly (geocode the user's exact strings, set them as `poi_list`, skip the filters for them) makes the match hold *by construction* and removes the dependency on GPT's wording. So I'd reframe your "DEFERRED — GPT already returns them" as: fine to defer for this retest, but it's the real hardening, and the failure mode is a quiet wrong-stop substitution, not an error. Worth a ticket.

For this retest specifically, no action needed — names match.

---

## Other items

- **Issue 2 (coordinates):** unchanged, already verified, ship.
- **Issue 3 (titles/Chinese):** services side now returns translated `name` + writes manifest/HTML title in `translation-service-00008`. On retest, confirm whether ZIPs contain `manifest.json`; if not, the response `name` is the channel for Mobile-AQ to consume. (Per my corrected note — title translation is a services responsibility and is now in place.)
- **TOUR_STATUS rows_affected=0:** agreed, the `tour_19ea7b2f9d6` vs integer-`358` mismatch is mobile tracking, not blocking.

---

## Retest checklist (services)

Re-run: `walking tour with stops at BLUE HILLS RESERVATION, NEPONSET RIVER RESERVATION, STONY BROOK RESERVATION, BELLEVUE HILLTOP, Milton, MA`.

In the tour-generator log, expect:
1. `PHASE 3C: skipped for walking tours …`
2. `GEO-CHECK: KEPT '…'` ×4 (one per park) — and **no** `GEO-CHECK: REMOVED` and **no** Part C replacement fetch.
3. Final tour = **4 stops**, each `audio_N.txt` beginning with an English `Coordinates:` line.

If any park logs `REMOVED` instead of `KEPT`, that's the name-mismatch case from 1c — capture the POI name GPT returned vs. what the user typed, and seeding becomes the fix.

**Bottom line:** v11 is correct for the tested request — approve and retest. Keep seeding (1c) on the backlog as the durable guard against GPT name drift.
