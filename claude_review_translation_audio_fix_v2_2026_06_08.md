# Claude Review → Kiro — Translation Audio Fix v2

**Date:** 2026-06-08
**Re:** `REVIEW_FOR_KIRO_translation_audio_fix_v2_2026_06_08.md`
**Scope:** Services/GCloud only.
**Verdict:** ✅ **Testing warranted — deploy and retest.** All three items I flagged in v1 are resolved and verified in code. No further fixes required server-side before the retest. The only remaining blocker is mobile-side (`zh→ko`), which is correctly scoped to Mobile-AQ.

---

## Verified in code ✅

**1. Audio text now sourced from `audio_N.txt` (was my main concern).**
`translate_zip_audio()` modernized branch (lines 333–376, both copies) now loops each `audio_N.mp3`, reads its sibling `audio_{i}.txt` as the exact source text (line 335–341), translates it, synthesizes Polly audio, writes it back to `audio_N.mp3` (367–369), and **writes the translated script back to `audio_N.txt`** (371–372) so script and audio stay in sync. The HTML-paragraph grouping is now a lazy-loaded last resort that only fires when `audio_N.txt` is missing (342–357). This is the precise 1:1 mapping I recommended — the heuristic mismatch is gone. ✅

**2. Dockerfile builds the correct (non-stale) file.**
`translation-service/Dockerfile` has `COPY translation_service.py .` with build context `translation-service/`. That file is now **82,776 bytes** (the fixed version) — not the old 8 KB stub. The `--source=development/translation-service` deploy will ship exactly the file Kiro edited. My v1 stale-file caution is resolved. ✅

**3. Both copies are in lockstep.**
`development/translation_service.py` (82,803 B) and `translation-service/translation_service.py` (82,776 B) carry identical fixes (27-byte diff is the local-Docker header). `'ko':'Seoyeon'` present in both (line 151). `'ko'` in `supported_languages` in both orchestrators (tour line 1087, news line 152). ✅

---

## Testing instructions hold

- `DELETE FROM audio_tours WHERE id IN (356,357)` then re-request RU from the app validates the **fallback** path (355 has no `tour_content`) — now accurate thanks to the `audio_N.txt` source.
- A **new** tour after the Cloud Tasks deploy exercises the **primary** path (`tour_content` populated by the worker) — also correct.
- Both paths now produce translated audio matched per stop.

## One reminder, not a blocker

Korean stays broken end-to-end until **Mobile-AQ** maps "Korean"→`ko` (the app sent `zh`, log line 34). Server side is fully ready. Don't read a failed Korean retest as a server regression — it's the pending mobile fix. The two mobile items (Korean code, English translated titles) are correctly listed for Mobile-AQ; say the word and I'll write that Mobile-AQ doc.

---

## Bottom line
**Approve and test.** The `audio_N.txt` source fix, the Dockerfile build-the-right-file confirmation, and the dual-copy parity are all verified. Deploy `translation-service`, delete 356/357, retest RU (audio should now be Tatyana-voiced Russian matched per stop). Korean waits on the mobile `zh→ko` change.
