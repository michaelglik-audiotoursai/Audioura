##### READY FOR REVIEW

# LOCAL-118: Tour Hook Analysis — Does the Spine Hook Reach the Listener?

**Branch:** `kiro/local118-tour-hook-analysis`  
**Commit:** `cdb483a`  
**Agent:** Mac Mini Kiro  
**Date:** 2026-08-02

---

## Summary

The UNWIRED_AUDIT (LOCAL-108) identified `tour_hook_generator.py` as an unwired module
and stated "the hook exists in the data but never reaches the audio output." This
investigation found that diagnosis is **incorrect** — the spine's `tour_hook` field IS
consumed by `generate_tour_text.py:6091` and reaches the listener as the opening paragraph
of Stop 1's audio, through a richer code path than the dead module provides.

**Recommendation:** Do not wire `tour_hook_generator.py`. Reclassify it from UNWIRED to
DEAD (superseded). The UNWIRED_AUDIT's deduplicated count drops from 8 to 7.

---

## Per-File Changes

| File | Change |
|------|--------|
| `TOUR_HOOK_ANALYSIS.md` | New — full analysis with 7 verbatim hook values, pipeline trace, app inspection, cost calculation, and recommendation |
| `SUBMISSION_LOCAL-118.md` | New — this file |

---

## Acceptance Evidence

### AC1: At least five real `tour_hook` values quoted verbatim from the database

Seven values quoted from `tour_cache.spine_json`, spanning museum, walking, nature, and
biking tours across Nice, Boston, Monaco, and Seattle. All sourced via host-side query
through `tests/db_connection.py`.

### AC2: Insertion point named precisely

**File:** `generate_tour_text.py`  
**Function:** The prolog generation block (not a named function — inline at lines 6091–6199)  
**Line 6091:** `_tour_hook = _storied_spine.get("tour_hook", "")`  
**Line 6142:** Fed to GPT-3.5 prolog prompt  
**Line 6189:** Expanded result stored as `_saved_prolog`  
**Line 6324:** Injected into Stop 1 text body  

The hook reaches audio via Stop 1's text → Polly TTS → MP3.

### AC3: Definite statement about app support

The Flutter app (`audio_tour_app/lib/screens/tour_player_screen.dart`, 249 lines) has
**no separate intro track slot**. It loads `index.html` and auto-starts `audio1` (Stop 1).
There is no `audio0`, no `intro.mp3`, no pre-stop playback concept. The prolog reaches the
listener because it is INSIDE Stop 1's text, not as a separate track.

### AC4: Cost per tour, calculated

| Scenario | Cost |
|----------|------|
| Hypothetical `tour_hook_generator.py` wiring | $0.0018/tour |
| Already-incurred live prolog cost | $0.0042/tour |

The question is moot — the feature is already implemented via a costlier but better path.

### AC5: Recommendation that commits either way

**Do not wire.** The hook already becomes audio. The module is dead code to be cleaned up,
not a feature gap to be closed.

---

## Verbatim Evidence

### Evidence: tour_hook is consumed at line 6091

```python
# generate_tour_text.py:6091
_tour_hook = _storied_spine.get("tour_hook", "")
```

### Evidence: hook is fed to the prolog prompt

```python
# generate_tour_text.py:6141-6142
_prolog_prompt = f"""Write a compelling 80-190 word tour introduction...
Tour hook: {_tour_hook}
```

### Evidence: prolog is injected into Stop 1

```python
# generate_tour_text.py:6324-6325
if i == 0 and _saved_prolog:
    poi_content += f"{_saved_prolog}\n\n"
```

### Evidence: prolog appears in stored tour audio text

Tour ID 29 (French Riviera Biking Tour), Stop 1 content:
```
You are about to embark on a journey through the sun-soaked streets of the
French Riviera, a tapestry woven with threads of timeless allure and hidden
tales. As you cycle through this landscape of luxurious villas and ancient
fortifications, you will uncover the secrets that whisper through the
centuries, from pirates to painters, from Roman times to modern luxury...
```

This text goes through `build_mp3.py` → Polly TTS → the listener hears it.

### Evidence: `tour_hook_generator.py` has zero importers

```
$ grep -rn "tour_hook_generator\|generate_tour_hook_audio" --include="*.py" | grep -v "tour_hook_generator.py"
(no results)
```

Zero importers — but this is because it was superseded, not because the feature is missing.

### Evidence: App has no intro track mechanism

```dart
// tour_player_screen.dart:148-156 (auto-start logic)
if (typeof startTour === 'function') {
  startTour();
} else {
  var audio1 = document.getElementById('audio1');
  if (audio1) { audio1.play(); }
}
```

Starts at `audio1` (Stop 1). No `audio0` or intro element.

---

## Limitations

1. **No live audio playback verification** — confirmed the text path (hook → prolog → Stop 1
   text → file) but did not play the actual MP3 to verify Polly produced it. This requires
   a running Polly container.
2. **Cannot verify all 88 tours have prolog in Stop 1** — checked 3 storied tours (IDs 27, 28, 29);
   non-storied tours (older) don't have spines and therefore have no hook/prolog at all.
3. **The prolog fallback path is weak** — when GPT-3.5 fails, the raw hook (a formulaic question)
   is used as-is. This is a quality issue but not a "feature never speaks" issue.
4. **No Docker builds** — all analysis via host-side database queries and static code reading.

---

## Database Verification

```
Row count before: 88
Row count after:  88
```
