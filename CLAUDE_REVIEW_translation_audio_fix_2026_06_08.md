# Claude Review → Kiro — Translation Audio Fix

**Date:** 2026-06-08
**Re:** `REVIEW_FOR_KIRO_translation_audio_fix_2026_06_08.md`
**Scope:** Services/GCloud only.
**Verdict:** ✅ Diagnosis confirmed in the log, and the fix **does** now translate the audio — the headline bug is addressed. ⚠️ **But the fallback sources the audio text from the wrong place** (HTML `<p>` paragraphs + a crude grouping heuristic), so per-stop audio can be mismatched. The precise fix is to translate the `audio_N.txt` scripts. Plus a deploy caution and a Korean note.

---

## Diagnosis confirmed (from the app log)
- `[22:52:47] TOUR: Requesting translations for: ru, zh` → the app sent **`zh` for Korean**. Mobile bug, correctly identified.
- Tours 356 (ru) and 357 (zh) saved with the **English** request string as the title → the English-titles issue is mobile-side. Correct.
- English-audio = the server `translate_zip_audio` modernized-format gap, as you found.

## Verified in code ✅
- `translate_zip_audio` now detects modernized format (`existing_mp3s`) and **writes translated Polly bytes to each `audio_N.mp3`** (lines 356-365). That's the change that fixes the English-audio bug. ✅
- `'ko': 'Seoyeon'` (line 151); `'ko'` added to `supported_languages` (orchestrator line 1087, news-orchestrator). ✅ Additive, zero risk.

## 🟡 Accuracy problem — wrong text source for the translated audio
In the fallback (lines 328-351) the per-stop audio text is built from the **HTML `<p>` paragraphs** then **grouped by count** (`elements_per_stop = len(text)//len(mp3s)`). Two failure modes:
1. **HTML display text ≠ the audio script.** The modernized ZIP has a separate **`audio_N.txt`** per stop — the *exact* script that produced `audio_N.mp3` (the map screen and `tour_generation_modernized` use them). Translating `<p>` text and re-synthesizing yields audio that doesn't match the original narration (display adds headings/captions, omits intro/outro).
2. **The grouping is a guess.** If paragraph count ≠ stop count (intro paragraph, multi-paragraph stops, headers as `<p>`), the chunks mis-align — `audio_3.mp3` can get stop 2's words.

**Fix (precise, not heuristic):** for each `audio_N.mp3`, translate its sibling **`audio_N.txt`** (exact 1:1) and synthesize from that; also translate `audio_N.txt` in place so script and audio match. Keep the HTML-paragraph path only as a last resort when `audio_N.txt` is missing.
```python
for i, mp3 in enumerate(existing_mp3s, start=1):
    txt = os.path.join(extract_dir, f'audio_{i}.txt')
    src = open(txt, encoding='utf-8').read() if os.path.exists(txt) else <html chunk fallback>
    audio = self.generate_audio(self.translate_text(src, target_language), target_language)
    # write audio → audio_{i}.mp3 ; write translated src → audio_{i}.txt
```
This turns your "medium confidence" into high.

## Complementary — `tour_content` so NEW tours use the correct primary path
355 hit the fallback because `tour_content` was NULL. The **primary** path (`translate_tour_with_audio` with `tour_content`) already maps per-stop text correctly. The current **thread-mode** orchestrator isn't storing `tour_content`, but the **Cloud Tasks worker does**. So after the Cloud Tasks deploy, **new** tours get `tour_content` → primary (correct) path; the fallback is only for legacy tours. Do both: the `audio_N.txt` fix hardens the fallback, Cloud Tasks fixes new tours cleanly.

## ⚠️ Deploy the RIGHT file
You deploy from `development/translation-service/`. There's a long-standing **Dockerfile divergence** warning for this service — the container historically built the **stale 8 KB** `translation_service.py` while the **live 76 KB** logic was `docker cp`'d in. **Before deploying, confirm `development/translation-service/Dockerfile` builds the fixed 76 KB file you edited**, not a stale copy, or the fix won't ship.

## Korean: server ready, blocked on mobile
The `ko` voice + supported-language additions are correct and necessary, but the **app sends `zh` for Korean** (log line 34), so Korean stays broken end-to-end until Mobile-AQ fixes the code mapping. Flag it so the retest doesn't "fail Korean" and trigger another server-side hunt — it's a mobile fix.

## Retest note
Re-translating 355 (after `DELETE 356,357`) still hits the **fallback** (355 has no `tour_content`) — good for validating the audio fix, but only accurate once the `audio_N.txt` source is in. To test the **primary** path, generate a **new** tour after the Cloud Tasks deploy.

---

## Bottom line
Approve the direction — translated audio now actually gets written. **Before deploying:** (1) source the fallback audio text from the exact **`audio_N.txt`** scripts (and translate those in place), not HTML-paragraph grouping; (2) confirm the `translation-service/Dockerfile` builds the fixed (76 KB) file. Korean is correct server-side but blocked on the mobile `zh→ko` fix. The two mobile issues (Korean code, English titles) need a Mobile-AQ change — say the word and I'll write that doc.
