# Review for Kiro — Tour Type Classification: why everything became "Museum"

**Reviewer:** Claude (main dev Mac)
**Subject:** User-reported regression — walking/biking/restaurant/book/movie tours all now come out as museum tours
**Severity:** High — this is a real, distinct application bug, unrelated to the Docker/infra work in the other `KIRO_REVIEW_*_docker_fixes.md` files. Confirmed with exact commits and line numbers, not speculation.
**Status:** Root cause fully identified. Two compounding backend bugs + one contributing client-side gap.

---

## Summary

Two independent bugs in `generate_tour_text.py`, both introduced in late May, plus a long-standing gap in the iPhone app's request parser that feeds bug #2. Not a Docker issue, not related to anything fixed in the other review rounds.

---

## Root cause #1 (primary) — the "force museum" safety net has no movie/book exception

`generate_tour_text.py:1501-1508`:
```python
if intent.get('venue_name') and not _EXPLICIT_NON_MUSEUM_TOUR_RE.search(location) and not _MULTI_BUILDING_INSTITUTION_RE.search(location):
    tour_category = 'museum'
    print(f"  [S15] Forced tour_category=museum from venue_name='{intent['venue_name']}'")
```

Whenever the AI's intent analysis (`analyze_tour_intent`) identifies *any* `venue_name` in the request, this forces the whole tour to `museum` category — unless the location text matches `_EXPLICIT_NON_MUSEUM_TOUR_RE` (line 45-50):

```python
_EXPLICIT_NON_MUSEUM_TOUR_RE = re.compile(
    r'\b(walking|restaurant|food|dining|culinary|self[- ]guided|architecture|architectural'
    r'|pub\s+crawl|bike|cycling|biking|shopping)'
    r'\s+tour\b',
    re.IGNORECASE,
)
```

Walking, restaurant, and biking tours are covered by this list. **`movie`, `film`, `book`, `novel`, and `literary` are not present at all.** So a request like "London movie locations tour" — if the AI's intent analysis attaches any venue name to it (e.g. thinks a mentioned landmark is "the venue") — gets forced to `museum`, full stop, regardless of what the user actually typed.

Introduced: commit `2e5eff1`, 2026-05-20, "S15 safety net: `_EXPLICIT_NON_MUSEUM_TOUR_RE` guard + [S15] log lines + 4 negative PHASE 1 prompt examples (Claude session 15 review)."

---

## Root cause #2 (compounding) — the fallback classifier checks `tour_type`, which is always "museum"

When there's no venue name (or the regex above does match), it falls through to `_classify_tour_category()` (line 401-439):

```python
def _classify_tour_category(location, tour_type):
    location_lower = location.lower()
    tour_type_lower = tour_type.lower()

    # ... walking-phrase check, food-keyword check ...

    museum_keywords = ['museum', 'gallery', 'mfa', 'moma', 'exhibition', 'collection', 'art center', 'cultural center']
    if any(keyword in location_lower or keyword in tour_type_lower for keyword in museum_keywords):
        return 'museum'

    specialized_keywords = ['book', 'movie', 'film', 'botanical', 'garden', 'park', 'novel', 'story', 'literary', 'filming']
    if any(keyword in location_lower or keyword in tour_type_lower for keyword in specialized_keywords):
        return 'specialized'
    ...
```

The museum check runs **before** the specialized (book/movie/park) check, and it matches against `tour_type_lower` as well as the location text. The `or keyword in tour_type_lower` clause was added in commit `9d0ce76` (2026-05-29) to fix a real, narrower problem — museums with names that don't contain an obvious museum keyword (e.g. "Medfield State Hospital"), where `tour_type` correctly said "museum" but the location text didn't. That fix was reasonable in isolation.

The problem: the client (iPhone app) sends `tour_type: "museum"` for almost every request regardless of what the user actually asked for (see below), so `tour_type_lower` is essentially always the literal string `"museum"`. Since `'museum'` is itself one of the `museum_keywords`, the check `keyword in tour_type_lower` trivially passes for **every single request** that reaches this function — swallowing biking tours, and anything else that doesn't hit the walking-phrase or food-keyword checks earlier, or the movie/book gap in root cause #1.

A later commit (`06ba427`, 2026-06-01) added an explicit "walking tour" phrase check at the very top of this function specifically to patch walking tours around this problem — but the same treatment was never applied to the specialized category, so book/movie/park requests remain vulnerable to falling into the museum bucket via `tour_type_lower`.

---

## Contributing factor — the app's own tour_type guesser doesn't know about most tour types

`audio_tour_app/lib/screens/tour_generator_screen.dart:109-135`, `_parseTourRequest()`:

```dart
String tourType = 'museum';
if (lowerRequest.contains('walking') || lowerRequest.contains('walk')) {
  tourType = 'walking';
} else if (lowerRequest.contains('museum')) {
  tourType = 'museum';
} else if (lowerRequest.contains('park')) {
  tourType = 'park';
} else if (lowerRequest.contains('exhibit')) {
  tourType = 'exhibit';
}
```

This is the **only** place `tour_type` gets set before the request leaves the app. There is no branch for "restaurant", "biking"/"bike", "book", or "movie" — a user typing any of those gets the default `'museum'` sent as `tour_type` regardless of what they actually asked for. This has been in the app since its first commit (2025-10-26, confirmed via `git log --diff-filter=A`), on both `main` and `storied` — it isn't itself the "sudden" regression, but it's the reason `tour_type_lower` is reliably "museum" in root cause #2, and it means the backend has to get the classification entirely right from the raw location text alone, with no help from the client.

---

## Why it feels sudden

Both backend commits landed within 9 days of each other in late May (`2e5eff1` on 5/20, `9d0ce76` on 5/29) — about two months before this report. The bug has likely been silently degrading movie/book/biking tours since then; it just may not have been exercised or noticed until now. This is a real, dateable regression, not a one-off fluke or user error.

---

## Recommended fix — three changes, ordered by impact

### 1. (Highest impact, smallest change) Add the missing keywords to the S15 safety-net regex

`generate_tour_text.py:45-50`:
```python
_EXPLICIT_NON_MUSEUM_TOUR_RE = re.compile(
    r'\b(walking|restaurant|food|dining|culinary|self[- ]guided|architecture|architectural'
    r'|pub\s+crawl|bike|cycling|biking|shopping'
    r'|movie|film|book|literary|novel)'          # <-- add these
    r'\s+tour\b',
    re.IGNORECASE,
)
```
This alone fixes movie/book tours whenever the phrase "movie tour", "book tour", "literary tour" etc. appears in the request text — the same mechanism that already protects walking/restaurant/biking.

### 2. Fix `_classify_tour_category`'s museum check to not use `tour_type` as a blind OR-match

Move the specialized-keyword check **before** the museum check, or stop matching `tour_type_lower` against `museum_keywords` entirely (only use it as a last-resort tie-breaker, after location-text-based checks for every category have failed):

```python
# Specialized tour indicators — check BEFORE museum, using location text primarily
specialized_keywords = ['book', 'movie', 'film', 'botanical', 'garden', 'park', 'novel', 'story', 'literary', 'filming']
if any(keyword in location_lower for keyword in specialized_keywords):
    return 'specialized'

# Museum indicators
museum_keywords = ['museum', 'gallery', 'mfa', 'moma', 'exhibition', 'collection', 'art center', 'cultural center']
if any(keyword in location_lower for keyword in museum_keywords):
    return 'museum'
elif any(keyword in tour_type_lower for keyword in museum_keywords):
    # tour_type-based fallback only when location text gave no signal at all
    return 'museum'
```
Be careful here — this function has already been patched twice for narrow regressions (the Medfield State Hospital case, then the walking-tour override). Whatever you change, re-verify both of those original cases still work, not just the new one. Search the codebase / prior `claude_review_*`/`REVIEW_FOR_KIRO_*` files for "Medfield" and "S15" for the original bug reports before touching this.

### 3. Give the app's own classifier real categories instead of guessing four

`tour_generator_screen.dart:109-135` — add branches for restaurant/food, biking/cycling, and book/movie, matching the same keyword sets the backend uses, so `tour_type` reaching the backend is actually meaningful instead of defaulting to `'museum'` for most requests:
```dart
String tourType = 'walking'; // safer default than 'museum'
if (lowerRequest.contains('walking') || lowerRequest.contains('walk')) {
  tourType = 'walking';
} else if (lowerRequest.contains('museum')) {
  tourType = 'museum';
} else if (lowerRequest.contains('restaurant') || lowerRequest.contains('food') || lowerRequest.contains('dining')) {
  tourType = 'restaurant';
} else if (lowerRequest.contains('bik') || lowerRequest.contains('cycl')) {
  tourType = 'biking';
} else if (lowerRequest.contains('movie') || lowerRequest.contains('film') || lowerRequest.contains('book') || lowerRequest.contains('literary')) {
  tourType = 'specialized';
} else if (lowerRequest.contains('park')) {
  tourType = 'park';
} else if (lowerRequest.contains('exhibit')) {
  tourType = 'exhibit';
}
```
Changing the default from `'museum'` to `'walking'` also directly weakens root cause #2's blast radius even before fix #2 above lands, since `tour_type_lower` will no longer default to a museum-matching string for unrecognized requests.

---

## Do fix #1 first, alone, and verify before touching #2 and #3

This mirrors how the Docker investigation went — small, verifiable steps beat one large change. Fix #1 is a one-line regex addition with no risk to existing walking/restaurant/biking behavior (it only adds new matches, doesn't change existing ones). Get that verified working for movie/book tours before touching the riskier `_classify_tour_category` reordering (#2) or the app-side parser (#3).

**Verify fix #1 with real requests, checking the actual returned tour content/type, not just that generation succeeds:**
```
curl -X POST http://localhost:5002/generate-complete-tour \
  -d '{"location":"London movie locations tour","tour_type":"museum","total_stops":5,"user_id":"test","narrative_tone":"general"}'
```
Poll `/status/<job_id>` and check the orchestrator logs for the `[S15]` / "Detected tour category:" print lines — confirm it now logs `SPECIALIZED` (or whatever category is appropriate) instead of `MUSEUM`, and that the generated content actually reads like a movie-locations tour, not a museum tour with movie-related venue names shoehorned in.

Do the same for a book-tour and a biking-tour request once fix #2 also lands.

---

## Fix #4 (required companion to #1 and #2 — otherwise the fix is hollow)

**The narrative "book with chapters" system is not museum-specific and doesn't need to be built — it already exists per-category.** Dedicated, comparably-developed spine templates exist for all four categories:

```
templates/spine_museum.txt      38 lines
templates/spine_walking.txt     47 lines
templates/spine_restaurant.txt  46 lines
templates/spine_book.txt        48 lines
```

`spine_book.txt` already has its own chapter vocabulary (`inciting_incident | rising_action | midpoint_turn | dark_moment | climax | resolution | epilogue`) and emotional-beat framing, purpose-built for literary/movie tours. The `STORIED_MODE` narrative pipeline (spine generation, fact sheets, story-type assignment) is gated only by the `STORIED_MODE` env var, not by `tour_category` — so once a tour is correctly classified, it's supposed to automatically pick up its own category's template.

**It doesn't, currently, because of a naming mismatch.** `_classify_tour_category()` returns the literal string `'specialized'` for book/movie/park requests. But `spine_generator.py`'s template loader — the function actually used — doesn't recognize that key:

```python
# spine_generator.py
_TEMPLATE_MAP = {"museum": "spine_museum.txt", "walking": "spine_walking.txt",
                  "restaurant": "spine_restaurant.txt", "book": "spine_book.txt"}

def _load_template(tour_category: str) -> str:
    filename = _TEMPLATE_MAP.get(tour_category.lower(), "spine_museum.txt")  # 'specialized' misses -> falls back to MUSEUM
    ...

def generate_spine(..., tour_category: str, ...):
    template = _load_template(tour_category)   # <-- this is the function actually called
```

There's already a `select_spine_template()` function in the same file that correctly maps `specialized/movie/film → book` and falls back to `spine_walking.txt` (not museum) for anything unrecognized — but it's dead code, never called from anywhere. `story_type_assigner.py` has the same pattern (`_CATEGORY_POOLS.get(tour_category.lower(), _DEFAULT_POOL)` with no `'specialized'` key either).

**Without this fix, fix #1 and #2 are cosmetic** — a movie/book tour will get correctly labeled `Tour-Category: specialized` in the output header, but will silently render using the *museum* spine/story-type pool underneath, producing museum-flavored narration for a movie tour rather than the book-chapter treatment that's already built and waiting for it.

**Recommended fix — normalize at the source, not in every consumer:** right where `tour_category` gets its final value in `generate_tour_text.py` (after the `_classify_tour_category(...)` calls at lines 1515/1519, and after the `'museum'` force at line 1507), add:
```python
if tour_category == 'specialized':
    tour_category = 'book'
```
This fixes every downstream consumer (`spine_generator`, `story_type_assigner`, and any future one) at a single point instead of patching each dict lookup individually. Simpler and lower-risk than deleting the dead `select_spine_template()` function or fixing each `_TEMPLATE_MAP`/`_CATEGORY_POOLS` separately.

**Verify:** after fixes #1, #2, and #4 all land, regenerate a movie-locations tour and check the orchestrator/generator logs for the `[Storied] Spine generated:` line — confirm it reports loading `spine_book.txt`, not `spine_museum.txt`, and that the generated prolog/chapters actually use book-tour framing (character motivations, fiction-to-reality connection) rather than museum framing (artist, medium, collection).

---

## Not doing right now

Not attempting fix #2 or #3 in this pass — flagging them so you have the full picture, but sequencing matters here given how narrowly-targeted the last two fixes to this exact function already were (Medfield State Hospital, then the walking-tour priority patch). Land #1, verify, report back, and we'll sequence #2, #3, and #4 from there the same way we did the Docker rounds. Note #4 only matters once #1 or #2 is actually producing `'specialized'`/`'book'` classifications to test against — verify it in the same pass as whichever of those two you land second.
