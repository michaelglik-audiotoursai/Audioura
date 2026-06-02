# Investigation & Fix Handoff — Museum Exhibit Verification Gap
**For:** Kiro Amazon-Q (Services)
**From:** Claude
**Date:** 2026-06-01
**File:** `generate_tour_text.py`
**Function:** `_validate_museum_stop_descriptions()` and its pre-filter `_is_suspect()`
**Branch:** `services-migration`
**Severity:** High — produces confidently-wrong factual content in single-venue museum tours.

---

## 1. Symptom (reproduced by Sir Michael)

Request string: **"the old manse house-museum, Concord, MA"**, 4 stops, EN/RU/KO.

- Category classification: correct (`museum`, S15-forced from venue_name).
- Icons: correct.
- **Content: wrong.** Stop 2 = **"Thoreau's Bedroom"**, describing Thoreau's bed and personal artifacts. Those artifacts are housed at the **Concord Museum**, *not* The Old Manse. The tour presented an exhibit from a different institution as if it were inside the venue.

This is **not** a category/icon bug (Kiro's `9d0ce76`/`06ba427` are unrelated to it). It is a factual-accuracy bug in the venue-containment guard.

---

## 2. Was the verification called? Yes.

The pipeline has a dedicated guard, PHASE 5.5b, that runs for exactly this kind of tour:

```python
# generate_tour_text.py:1456-1460
if tour_category == 'museum' and _museum_venue_name:
    print(f"\nPHASE 5.5b: Validating descriptions are inside '{_museum_venue_name}'...")
    poi_list = _validate_museum_stop_descriptions(poi_list, _museum_venue_name, headers)
    print(f"OK PHASE 5.5b: {len(poi_list)} stop(s) passed venue description validation")
```

`_validate_museum_stop_descriptions` (generate_tour_text.py:335-437) is a genuine GPT fact-checker. For each *suspect* stop it asks:

> "Does this description refer to content physically located INSIDE '<venue>', or a DIFFERENT institution or fabricated exhibit?"

and removes stops that come back `inside_venue: false` with non-low confidence. For the Old Manse tour this code path ran. It simply never *checked* the "Thoreau's Bedroom" stop.

---

## 3. Root cause — the cost-saving pre-filter is blind to this failure mode

To avoid an API call per stop, the function only sends a stop to the GPT check when a cheap local pre-filter, `_is_suspect()`, flags it:

```python
# generate_tour_text.py:352-370
_INSTITUTION_MARKERS = {
    'museum', 'gallery', 'institute', 'society',
    'foundation', 'university', 'college', 'library'
}
_OVERLAP_STOP_WORDS = {'the', 'of', 'and', 'in', 'at', 'a', 'an', 'for'}

def _is_suspect(stop_name):
    """True if stop_name looks like a different institution than venue_name."""
    name_words = set(re.findall(r'[a-z]+', stop_name.lower()))
    if not (name_words & _INSTITUTION_MARKERS):
        return False  # no institutional marker — probably a room/exhibit
    ...
```

```python
# generate_tour_text.py:415-417
suspect = [p for p in candidates if _is_suspect(p.get('name', ''))]
clean   = [p for p in candidates if not _is_suspect(p.get('name', ''))]
# only `suspect` stops are sent to GPT; `clean` stops pass through unchecked
```

**The blind spot:** `_is_suspect` returns `True` only when the stop *name* contains an institution marker word (museum/gallery/institute/…). `"Thoreau's Bedroom"` contains none of them → `_is_suspect` returns `False` → the stop is bucketed as `clean` → it **bypasses the GPT containment check entirely** and is kept.

The pre-filter's design assumption — *"no institutional marker in the name → it's a harmless room/exhibit"* — is exactly inverted for this failure mode. The guard is good at catching "this stop is a whole different **institution by name**" and completely blind to "this stop is a real exhibit that physically lives in a **different** museum." The latter is the more common and more damaging hallucination, because it reads as plausible.

---

## 4. Fix (recommended)

### 4.1 Primary: check every stop on single-venue museum tours
For a venue-locked museum tour the per-stop containment check is worth running on **all** non-zero stops, not just institution-named ones. Cost is tiny: a typical tour is 4-8 stops, each check is one `gpt-3.5-turbo` call capped at 60 tokens. The existing remove-stop machinery is reused unchanged.

Minimal change — replace the name-only pre-filter split with "check all candidates" (keep stop 0 unconditional):

```python
# generate_tour_text.py ~415-417  (inside _validate_museum_stop_descriptions)
# BEFORE:
suspect = [p for p in candidates if _is_suspect(p.get('name', ''))]
clean   = [p for p in candidates if not _is_suspect(p.get('name', ''))]

# AFTER:
# Single-venue museum tours: verify EVERY stop's description is inside the venue.
# The name-only pre-filter (_is_suspect) missed exhibits that belong to a DIFFERENT
# museum but whose names contain no institutional marker (e.g. "Thoreau's Bedroom"
# is housed at the Concord Museum, not The Old Manse).
suspect = list(candidates)
clean   = []
```

`_is_suspect` can be retained for logging/telemetry, or kept for a future "large tour" cost-guard, but it must no longer gate the check on these tours. (If cost on very large tours is a concern, keep the all-stops check only when `len(candidates) <= 12`, else fall back to `_is_suspect`. For current tour sizes this branch never triggers.)

### 4.2 Secondary (defense in depth): assert containment in the description prompt
Make the PHASE 5 description-generation prompt explicitly forbid out-of-venue content, so the model is less likely to introduce the error in the first place:

> "Every stop MUST be a room, gallery, exhibit, or area physically located INSIDE '<venue_name>'. Do NOT include artifacts, collections, or rooms that are housed at any other institution, even if thematically related to the same person or topic."

Do this **in addition to** the post-check, not instead of it.

### 4.3 Guard against over-removal
PHASE 5.5b already keeps stop 0 unconditionally, so a tour can't drop to zero stops. But if checking-all-stops removes enough stops that the tour falls below the requested count, decide the desired behavior: (a) accept the shorter, correct tour, or (b) re-request replacement stops. Recommend (a) for now (a correct 2-stop tour beats a wrong 4-stop tour), with a log line noting the shortfall.

---

## 5. Acceptance test

Re-run: **"the old manse house-museum, Concord, MA"**, 4 stops.

- Expect PHASE 5.5b log to now show a GPT check for **every** stop (not "0 suspect").
- Expect "Thoreau's Bedroom" to be flagged `inside_venue: false` and removed (or, with §4.2, never generated).
- Expect the final tour to contain only stops genuinely inside The Old Manse.

Add regression strings: a venue with a famous person associated but artifacts elsewhere (e.g. "Orchard House, Concord, MA", "The Paul Revere House, Boston") to confirm no over-removal of legitimate in-venue rooms.

---

## 6. What this does NOT cover
Sir Michael's newsletter findings (#3 "2 of 5 articles downloaded", #4 "generated article text differs from source URL") are a separate subsystem (`news_processor_service.py` / `news_generator_service.py`) and are being investigated separately from the logs. They are unrelated to this exhibit-verification fix.
