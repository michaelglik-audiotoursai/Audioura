# Review for Kiro — Part One Execution: Classification + Hedging Safety Net

**Reviewer:** Claude (main dev Mac)
**Subject:** The minimum bounded set of changes needed to test "non-museum tours get correctly classified AND don't fabricate confident-sounding facts"
**Supersedes for this pass:** Execute only what's below. Do not do fix #2 or #3 from `KIRO_REVIEW_01_tour_type_classification.md`, and do not start Part 2 of `KIRO_REVIEW_02_narrative_grounding.md` — those are separate, later work, already sequenced in their own files.

---

## Change 1 — S15 regex: add movie/book keywords

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
Full rationale in `KIRO_REVIEW_01_tour_type_classification.md`, "Recommended fix #1."

## Change 2 — normalize `'specialized'` to `'book'` at the source

Right after `tour_category` gets its final value from `_classify_tour_category(...)` in `generate_tour_text.py` (both call sites, ~lines 1515 and 1519), add:
```python
if tour_category == 'specialized':
    tour_category = 'book'
```
Full rationale in `KIRO_REVIEW_01_tour_type_classification.md`, "Fix #4." Without this, Change 1 makes tours get correctly *labeled* but they'd still silently render with the museum spine template underneath.

## Change 3 — hedging safety net for non-museum categories

Near `generate_tour_text.py:2828` (right after the existing `if not poi.get('verified', True):` museum-only hedging block), add:
```python
if tour_category != 'museum':
    description_prompt += """
IMPORTANT — GROUNDING HONESTY: No fact-checking has been performed on specific claims about
real people, events, or history for this stop. When you include a specific claim
(a named chef/owner, a specific historical event, a notable visitor, a specific date or
incident), use hedged, attributive framing rather than stating it as verified fact:
"local accounts describe...", "the story often told is...", "according to [publication/type
of source]...", "is said to have...". Do NOT invent specific names, dates, or incidents and
present them as confirmed history. General, well-known facts (a neighborhood's founding era,
a cuisine's regional origin, a book's publication year) can be stated plainly — the hedging
requirement is specifically for claims about particular people or particular events tied to
this specific stop, which is where fabrication risk is highest.
"""
```
Full rationale in `KIRO_REVIEW_02_narrative_grounding.md`, Part 1.

---

## Verify (this is the actual test pass)

1. Generate a movie-locations tour and a book tour via direct API call (bypass the app for now — its parser is separate, later work):
   ```
   curl -X POST http://localhost:5002/generate-complete-tour \
     -d '{"location":"London movie locations tour","tour_type":"museum","total_stops":5,"user_id":"test","narrative_tone":"general"}'
   ```
2. Check orchestrator/generator logs: confirm `Detected tour category: BOOK` (not `MUSEUM`, not left as `SPECIALIZED`), and confirm `[Storied] Spine generated:` shows it loaded `spine_book.txt`.
3. Read the actual generated description text for 2-3 stops. Confirm: (a) it reads like a movie-locations tour, not a museum tour with movie trivia bolted on, and (b) any specific claim about a named person/event uses hedged framing ("local accounts describe...", "is said to have...") rather than flat assertion.
4. Repeat for a restaurant-tour request that doesn't literally contain the word "restaurant"/"food" in the text (to make sure it doesn't fall back to museum) — confirm hedging shows up there too.

Report back what you find — including anything the hedging instruction *doesn't* catch, since this is a first pass at a prompt-only safety net, not a real verification pipeline (that's `KIRO_REVIEW_02` Part 2, separate and later).
