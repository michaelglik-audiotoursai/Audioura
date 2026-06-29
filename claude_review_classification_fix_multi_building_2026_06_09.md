# Claude Review → Kiro — Classification Fix for Multi-Building Institutions (v13)

**Date:** 2026-06-09
**Re:** `REVIEW_FOR_KIRO_classification_fix_multi_building_2026_06_09.md` (`tour-generator-00013-csf`)
**Scope:** Services / GCloud.
**Verdict:** ⚠️ **Approve the intent, but fix the regex before calling it done — it over-corrects.** v13 correctly makes "library buildings in Newton" a walking tour, but the keyword regex matches **singular** institution words too, so it now blocks museum classification for *every* library, church, school, synagogue, mosque, temple, and single "building/branch" — including genuine single-venue tours that should stay museum. Your own doc spotted this ("Wait — let me verify this is acceptable…"); Sir Michael is right that it's not. The discriminator should be **plurality / multiple buildings**, not the mere presence of an institution word.

---

## What v13 gets right ✅

- Target case fixed: "library buildings in Newton, Ma" → `_MULTI_BUILDING_INSTITUTION_RE` matches → S15 no longer forces museum → `_classify_tour_category` returns `walking`. No "museum Tour" name suffix, walking icon, all stops get coordinates. (Code verified at lines 54–57 and 666.)
- German Ho Chi Minh: agreed and now correctly scoped — server made the translation (tour 368, `de`); the iPhone sent no `translate-with-audio`, so it's the Mobile-AQ existing-tour-download flow. Server is ready (`de`/Marlene). Correct call.

## The regression (confirmed in code, matches Sir Michael's concern) ❌

`_MULTI_BUILDING_INSTITUTION_RE` (line 54–57) matches singular forms:

```
librar(y|ies) | church(es)? | school(s)? | synagogue(s)? | mosque(s)? | temple(s)?
| building(s)? | branch(es)? | historic\s+house(s)? | fire\s+station(s)?
```

Every alternative matches the **singular** ("library", "church", "school", "building", "branch", …). Combined with two facts I verified:

1. None of these words are in `museum_keywords` (`_classify_tour_category` line 398 = `museum, gallery, mfa, moma, exhibition, collection, art center, cultural center`). So a bare "Newton Free Library" never classifies as museum *through `_classify_tour_category`*.
2. Their **only** path to museum was the S15 venue_name force at line 666 — which v13 now blocks whenever the regex matches.

⇒ With v13, **no library/church/school/synagogue/mosque/temple tour can ever be a museum tour**, singular or plural. So:

| Request | v13 result | Correct? |
|---|---|---|
| "library buildings in Newton" | walking | ✅ (multi) |
| "libraries in Newton" | walking | ✅ (multi) |
| **"tour inside Newton Free Library"** | **walking** | ❌ should be museum (one venue, rooms inside) |
| **"Old North Church tour"** | **walking** | ❌ should be museum (single historic interior) |
| **"Boston Public Library building tour"** | **walking** | ❌ single building → museum |
| "MFA Boston" / "the Met exhibits" | museum | ✅ (museum keyword / venue_name, no institution word) |

The single-venue tours lose the museum template, the Phase 5.5 single-venue **containment validation** (`_validate_museum_stop_descriptions`), the correct icon, and instead get walking + GEO-CHECK distance logic that doesn't fit interior rooms. That's a worse failure than the original icon glitch.

## The fix — key on plurality, exactly as Sir Michael described

It was "**buildings**" (plural) plus multiple library buildings that made this multi-location. Match that, not the institution word. Make the regex **plural/multiplicity-only**:

```python
_MULTI_BUILDING_INSTITUTION_RE = re.compile(
    r'\b(libraries|churches|schools|synagogues|mosques|temples'
    r'|buildings|branches|historic\s+houses|fire\s+stations)\b',
    re.IGNORECASE,
)
```

Behavior with this version:

- "library **buildings** in Newton" → `buildings` matches → walking ✅ (target case still fixed — the plural "buildings" carries it)
- "**libraries** in Newton", "**churches** in Boston", "**historic houses** in Concord" → walking ✅
- "tour inside Newton Free **Library**" → singular, no match → S15 → **museum** ✅ (regression gone)
- "Old North **Church**" → singular → **museum** ✅
- "Boston Public Library **building**" (one building) → singular `building`, no match → **museum** ✅

This implements precisely "plural buildings = multi = walking; single institution = museum," and it does **not** reintroduce the original bug because "library buildings" contains the plural "buildings".

## Defense-in-depth note (why the map pins are safe either way)

The v12 coordinate-distinctness fix (Phase 6: emit coordinates for every stop when `unique_coords > 1`) already solves the **map-pin** symptom independent of category. So even after narrowing the regex, a genuinely multi-building tour that somehow stayed "museum" would still get all its pins. The classification only governs the **icon, the name suffix, and which validation runs** — so the regex narrowing is safe for the pin behavior and just restores correct museum treatment for single venues.

## Minor
- Your doc says true museums are saved by `museum_keywords` "before S15." Slight inaccuracy: "the Met"/"the Louvre" have no keyword and are actually saved by the S15 venue_name path (line 666). Outcome is the same (museum), so no action — just so the mental model is right when you touch this again.
- Residual edge with plural-only: a multi-site request phrased in the singular (e.g. "library system Newton") would classify museum. Rare, and GPT rarely returns a venue_name for an obviously plural concept — acceptable; revisit only if it shows up.
- Compile: my sandbox again only got a truncated copy (mount artifact), so I couldn't `py_compile` here; you reported exit 0 and `v13` is serving. Keep the gate.

---

## Bottom line
v13's direction is right and the German call is correct, but ship a follow-up that makes `_MULTI_BUILDING_INSTITUTION_RE` **plural-only**. As deployed it strips museum classification from *all* libraries/churches/schools — including legitimate single-venue interior tours — which is the regression Sir Michael flagged. Matching plural/"buildings" keeps "library buildings in Newton" as walking while letting "Newton Free Library" (one building) be a museum tour again. The v12 coordinate fix keeps the map pins correct regardless.
