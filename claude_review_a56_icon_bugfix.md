# Claude.AI Review — A#56 Tour-Type Icon Bug Fix

**Date**: 2026-05-20  
**Branch**: `Tours_Step_Maps`  
**Commit**: `51cc93e`  
**Reviewer**: Services Amazon-Q  
**Files changed**: `generate_tour_text.py`, `tour_generation_modernized.py`

---

## 1. Problem Description

The Audioura mobile app displays a map button on each tour stop. The button icon should
reflect the tour category:

| Category | Expected icon |
|---|---|
| `walking` | 🚶 |
| `restaurant` | 🍴 |
| `museum` | 🏛️ |
| `specialized` / default | 🗺️ |

### Observed failures during user testing

| Tour | Expected | Actual | Reason |
|---|---|---|---|
| "Walking tour in Waltham, MA" | 🚶 | 🗺️ (default) | No `Tour-Category:` header in file — old tour |
| "Boston Civil War and underground railroad" | 🚶 (user expected) | 🏛️ | **Pre-bugfix regex bug, not a classifier issue.** Mobile hardcodes `tour_type="museum"`; PHASE 6 appends `"- Museum Tour"` to the title because the location doesn't contain "museum"; the old title-string regex matched "Museum" in that suffix. `_classify_tour_category()` actually returns `'walking'` for this location — the bugfix now respects that. |

The Waltham tour failure was the actionable bug. The Boston Civil War icon was technically
correct (no food/walking keywords → `museum` classification) but exposed the underlying
fragility of the original approach.

---

## 2. Root Cause Analysis

### Original approach (before fix)

`tour_generation_modernized.py` used a regex on the tour title string to infer category:

```python
_TOUR_CATEGORY_RE = re.compile(
    r'\b(walking|restaurant|food|museum|gallery|specialized)\b', re.IGNORECASE
)

def _tour_icon_for_name(tour_name):
    """Infer tour category icon from tour title string."""
    if tour_name is None:
        return '🗺️'
    m = _TOUR_CATEGORY_RE.search(tour_name)
    if not m:
        return '🗺️'
    word = m.group(1).lower()
    if word in ('restaurant', 'food'):
        return '🍴'
    if word in ('museum', 'gallery'):
        return '🏛️'
    if word == 'specialized':
        return '🗺️'
    return '🚶'  # walking
```

### Why it failed

In `generate_tour_text.py` PHASE 6, the title is assembled as:

```python
if tour_type.lower() in location.lower():
    # tour_type already in location — don't repeat it
    tour_title = f"Step-by-Step Audio Guided Tour: {location}"
else:
    tour_title = f"Step-by-Step Audio Guided Tour: {location} - {tour_type.title()} Tour"
```

For the request `location="walking tour in Waltham, Ma"`, `tour_type="walking"`:
- `"walking"` IS in `"walking tour in Waltham, Ma"` → branch taken
- Title written: `"Step-by-Step Audio Guided Tour: walking tour in Waltham, Ma"`
- The regex WOULD match `"walking"` in this title — so the regex approach should have worked

**Actual failure**: The Waltham tour (ID 270) was generated BEFORE the A#56 code was
deployed. It had no `Tour-Category:` header. The old `_tour_icon_for_name()` was also
not yet deployed. The tour was served from the DB ZIP as-is, with no icon logic at all,
defaulting to 🗺️.

**Structural fragility**: Even if the regex worked for existing titles, it was parsing a
human-readable string that could change format. The authoritative value — `tour_category`
from `_classify_tour_category()` — was already computed in PHASE 2 and available in scope.
There was no reason not to write it directly into the file.

---

## 3. Fix Implementation

### 3.1 `generate_tour_text.py` — PHASE 6 (write authoritative header)

```python
# PHASE 6: Assemble the complete tour
# Line 1: title
# Line 2: Tour-Category header (authoritative — tour_category is in scope from PHASE 2)
# Line 3: blank
# Then stops

complete_tour = tour_title + "\n" + f"Tour-Category: {tour_category}" + "\n\n"
```

`tour_category` is the return value of `_classify_tour_category(location, tour_type)`
called at PHASE 2. It is one of: `'walking'`, `'restaurant'`, `'museum'`, `'specialized'`.

### 3.2 `tour_generation_modernized.py` — parse header, direct dict lookup

```python
# Module level — single source of truth for icon mapping
_CATEGORY_ICONS = {'walking': '🚶', 'restaurant': '🍴', 'museum': '🏛️', 'specialized': '🗺️'}

# parse_tour_content_to_modernized() — reads the header written by generate_tour_text.py
category_match = re.search(r'^Tour-Category:\s*(\w+)', tour_content, re.IGNORECASE | re.MULTILINE)
tour_category = category_match.group(1).lower() if category_match else ''

# Returns dict including tour_category
return {
    'tour_name': tour_name,
    'tour_category': tour_category,
    'text_content': text_content,
    'audio_files': []
}

# generate_html_with_external_audio() — direct lookup, no string parsing
icon = _CATEGORY_ICONS.get(tour_data.get('tour_category', ''), '🗺️')
map_button = f'<button class="map-btn" onclick="openMap({i})" title="View on map">{icon}</button>'
```

`_TOUR_CATEGORY_RE` and `_tour_icon_for_name()` were removed entirely.

---

## 4. Tour Content File Format (post-fix)

```
Step-by-Step Audio Guided Tour: walking tour in Waltham, Ma
Tour-Category: walking

Stop 1: Waltham Watch Factory
Address: 250 Watch St, Waltham, MA 02453
Coordinates: 42.3765, -71.2356
...
```

Old tours (pre-fix) have no `Tour-Category:` line → `tour_category = ''` → default 🗺️.
Graceful degradation confirmed.

---

## 5. Translation Survival

Map buttons are siblings of `<h3>` elements, not children:

```html
<div class="audio-item">
    <h3>Stop 1: Waltham Watch Factory: Audio 1</h3>
    <button class="map-btn" onclick="openMap(1)" title="View on map">🚶</button>
    <audio id="audio-0" controls preload="metadata">...</audio>
</div>
```

`translation_service.py` calls `h.clear()` on `<h3>` elements to replace text content.
`h.clear()` removes children of the tag, not siblings. The map button is a sibling →
it survives translation unchanged. The icon emoji is baked into English HTML and is
language-neutral.

---

## 6. Review Questions for Claude.AI

1. **Header placement**: `Tour-Category:` is written as line 2 of the file (after title,
   before blank line, before stops). `parse_tour_content_to_modernized()` uses
   `re.MULTILINE` to find it anywhere in the file. Is there any risk of a stop description
   accidentally containing `Tour-Category: walking` and being misread? Should the regex
   be anchored to the first N lines?

2. **`_classify_tour_category()` coverage**: The function checks food → museum →
   specialized → walking keywords in order. The `walking` branch only fires on city/
   neighborhood keywords (`city`, `downtown`, `neighborhood`, `district`, `street`,
   `avenue`, `center`, `town`). A request like `"historic sites in Concord, MA"` has
   none of these keywords and falls through to the default `return 'walking'`. Is the
   default correct? Should it be `'specialized'` instead?

3. **`_pre_category` guard vs `tour_category`**: `_pre_category` is computed with
   `_classify_tour_category(location, "")` (empty tour_type) to suppress the mobile
   app's hardcoded `tour_type="museum"`. Then `tour_category` is computed again with
   `_classify_tour_category(location, tour_type)` at PHASE 2. These can differ when
   `tour_type` adds signal (e.g. `tour_type="museum"` for a genuine museum request).
   Is this two-call design correct, or should `tour_category` also use `""` as tour_type
   to be consistent with `_pre_category`?

4. **Old tours**: Pre-fix tours in the DB have no `Tour-Category:` header. They default
   to 🗺️. Is there a migration path worth considering (e.g. re-running
   `_classify_tour_category()` on the DB `tour_name` field as a one-time backfill)?
   Or is graceful degradation to 🗺️ acceptable permanently?

5. **`convert_old_tour_to_modernized()`**: This function in `tour_generation_modernized.py`
   does NOT parse `Tour-Category:` and does NOT return `tour_category` in its dict.
   It appears to be dead code (no callers found). Should it be removed, or does it serve
   a purpose?

---

## 7. Code Diff Summary

### `generate_tour_text.py`

```diff
- complete_tour = tour_title + "\n\n"
+ complete_tour = tour_title + "\n" + f"Tour-Category: {tour_category}" + "\n\n"
```

### `tour_generation_modernized.py`

```diff
- _TOUR_CATEGORY_RE = re.compile(
-     r'\b(walking|restaurant|food|museum|gallery|specialized)\b', re.IGNORECASE
- )
- def _tour_icon_for_name(tour_name):
-     """Infer tour category icon from tour title string."""
-     if tour_name is None:
-         return '🗺️'
-     m = _TOUR_CATEGORY_RE.search(tour_name)
-     if not m:
-         return '🗺️'
-     word = m.group(1).lower()
-     if word in ('restaurant', 'food'):
-         return '🍴'
-     if word in ('museum', 'gallery'):
-         return '🏛️'
-     if word == 'specialized':
-         return '🗺️'
-     return '🚶'

+ _CATEGORY_ICONS = {'walking': '🚶', 'restaurant': '🍴', 'museum': '🏛️', 'specialized': '🗺️'}

  def parse_tour_content_to_modernized(tour_content):
      tour_name_match = re.search(r'Step-by-Step Audio Guided Tour: (.+?)\n', tour_content)
      tour_name = tour_name_match.group(1) if tour_name_match else "Audio Tour"

+     category_match = re.search(r'^Tour-Category:\s*(\w+)', tour_content, re.IGNORECASE | re.MULTILINE)
+     tour_category = category_match.group(1).lower() if category_match else ''

      ...

-     return {'tour_name': tour_name, 'text_content': text_content, 'audio_files': []}
+     return {'tour_name': tour_name, 'tour_category': tour_category, 'text_content': text_content, 'audio_files': []}

  def generate_html_with_external_audio(tour_data):
      ...
-     icon = _tour_icon_for_name(tour_data.get('tour_name'))
+     icon = _CATEGORY_ICONS.get(tour_data.get('tour_category', ''), '🗺️')
```

---

## 8. Test Cases Needed (mobile)

1. Generate a new **walking** tour (e.g. "walking tour in Newton Center, MA") → expect 🚶
2. Generate a new **restaurant** tour (e.g. "restaurant tour in North End, Boston") → expect 🍴
3. Generate a new **museum** tour (e.g. "Jackson Homestead and Museum Newton MA") → expect 🏛️
4. Load an **old tour** (pre-fix, no `Tour-Category:` header) → expect 🗺️ (graceful default)
5. Generate a tour and translate it → expect icon unchanged in translated version
