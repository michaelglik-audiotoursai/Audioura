# Claude Review → Kiro — Museum Multi-Building Coordinates Fix

**Date:** 2026-06-09
**Re:** `REVIEW_FOR_KIRO_museum_multi_building_coordinates_2026_06_09.md` (`tour-generator-00012-fnr`)
**Scope:** Services / GCloud.
**Verdict:** ✅ **Approve the coordinates fix** — it's correct and resolves the single-pin symptom. But the user reported **three** problems and this addresses **one**. The museum *icon* is deferred (and it's more than cosmetic — the misclassification also corrupts the tour *name*), and the **German Ho Chi Minh download → English is not addressed at all** in this doc. Flagging both so they don't fall through.

---

## 1. Coordinates / multi-building fix — VERIFIED ✅

`generate_tour_text.py` lines 1673–1682 match the handoff exactly:

```python
if tour_category == 'museum':
    all_coords = [p.get("coordinates") for p in poi_list if p.get("coordinates")]
    unique_coords = set(all_coords)
    is_single_building = len(unique_coords) <= 1
    coords_eligible = (i == 0) if is_single_building else True
else:
    coords_eligible = True
if coords_eligible and poi.get("coordinates"):
    poi_content += f"Coordinates: {poi['coordinates']}\n\n"
```

Logic is sound across the matrix: multi-building "museum" (2 distinct coords, like the Newton libraries) → every stop gets a `Coordinates:` line → every stop a map pin; true single-venue museum (identical coords) → first stop only, preserving the old behavior; non-museum → all stops. Additive and low-risk — it only *adds* previously-suppressed coordinates. The iPhone log confirms the bug it fixes (line 40: `MAP: Loaded 1 POIs` for the 2-stop library tour). After this, both stops should pin. Approved.

(Compile note: my sandbox again only got a null-byte/truncated copy of the file, so I couldn't `py_compile` it here; the section I read is clean and `v12` is deployed and serving. Keep the `py_compile` deploy gate.)

---

## 2. Museum icon — deferred, but it's MORE than cosmetic (the name is wrong too)

You classified the icon as "cosmetic, not blocking." The icon itself, sure — but the **same root cause** (`_classify_tour_category` treating "library" as museum-class, so `tour_type='museum'`) also leaks into the **tour name**:

`tour_orchestrator_service.py:760` → `tour_name = f"{location} - {tour_type} Tour"`.

So tour 366's stored name became "…- museum Tour", which is exactly why the iPhone log's Russian title reads **"…- экскурсия по музею"** ("…- museum tour") for a *library* tour (log line 20). The user is shown a library tour labeled a museum tour — user-visible and wrong, not just an icon glyph.

So the misclassification produces three artifacts from one cause: (a) the single-pin bug — now patched at the symptom level, (b) the wrong icon, (c) the wrong "museum Tour" name suffix. The coordinates fix treats (a); (b) and (c) remain.

**Recommendation:** address the classification rather than each symptom. A "library buildings" / multi-building-institution request should not inherit the museum icon *or* the "museum Tour" name. Be careful though — the `museum` category is also what triggers the single-venue containment validation (Phase 5.5, `_validate_museum_stop_descriptions`), so don't just relabel libraries as walking. Cleaner: a distinct category (e.g. `institution-multi`) or detect "multiple buildings" up front and route it to multi-stop handling with an appropriate icon/name. Not blocking the retest, but it's the real fix and the user explicitly reported the icon.

---

## 3. German Ho Chi Minh download → English — NOT ADDRESSED (and not a coordinates issue)

The user reported two bad-news items; this doc only covers the libraries. The **"download existing Ho Chi Minh tour in German, got English"** problem is not mentioned anywhere in the handoff and is untouched by `v12`.

What I can confirm:
- **Server-side German is ready.** `voice_map['de'] = 'Marlene'` (translation_service line 148), and the `/translate-with-audio` route translates any non-`en` language it's handed (no allow-list gate in the route). AWS Translate supports `de`. So if the app sends a `de` translate request for that tour, the server will produce German text + Marlene audio.
- **The provided log doesn't contain the German attempt.** It shows the app *browsing* Ho Chi Minh tours (`/tours-near/10.77…/106.71…`, line 51) but **no** `translate-with-audio` call with `de`. So it can't be traced from this log.

The telling contrast: the *generated* library tour auto-fired a translation (log line 15–16, `Requesting translations for: ru`), but the *existing/browsed* Ho Chi Minh tour download apparently did **not** fire a `de` translation. That points to the **existing-tour download flow not requesting translation at all** (a Mobile-AQ flow gap), rather than a translation-service bug. Two other possibilities to rule out: `de` not enabled in the `supported_languages` DB table (data, not code — would drop it from the UI list / gate it), or a separate download-translate path that ignores the language.

**Recommendation (next step, separate from this fix):** capture a log of the German download. If the app sends **no** `de` `translate-with-audio` request → it's Mobile-AQ (the existing-tour download must trigger translation the way generate does). If it **does** and English comes back → check the `supported_languages` row for `de` (enabled?) and the translate path. Either way it's its own work item; please don't let it close out under the coordinates fix.

---

## Minor (carry-over)
`TOUR_STATUS … rows_affected: 0` (log 31–32) again — the `tour_19eacfc00ee` vs integer-`366` id mismatch. Known mobile tracking issue, not blocking.

---

## Bottom line
`tour-generator-00012-fnr` correctly fixes the multi-building map-pin bug — approve and retest "library buildings in Newton, Ma" (expect 2 pins). But close the loop on the other two reported problems: the museum misclassification still mislabels the tour's **name** ("museum Tour") and icon — fix it at the classification, not per-symptom — and the **German download returning English** is entirely unaddressed and needs its own investigation (most likely the existing-tour download flow isn't requesting translation). Server-side German itself is ready.
