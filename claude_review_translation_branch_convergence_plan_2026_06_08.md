# Claude → Kiro — Translation Service: Converge the Two Branches Into Shared Helpers

**Date:** 2026-06-08
**Scope:** Services only. File: `development/translation-service/translation_service.py` (single source of truth).
**Goal:** Eliminate the duplicated logic across the primary (`tour_content`) and fallback (ZIP) translation paths so a fix can never again land in one path but not the other. Behavior-preserving refactor — no output changes, just one code path feeding two thin input adapters.

**Guiding principle (Sir Michael's):** *the code that runs locally and on cloud must be identical; only parameters differ, and parameters live in config (env / JSON / YAML), never in forked code.* This refactor serves that principle directly — after it, both Docker Compose and Cloud Run run the same helpers regardless of a tour's data state, and the only thing that varies is input data and configured values (voice map, language list, DB DSN, AWS region).

---

## 1. Where the duplication is today (the drift surface)

Two entry points, each with its own ZIP-assembly function, duplicating five concerns:

| Concern | Primary path | Fallback path | Drifted before? |
|---|---|---|---|
| Per-stop translate + `_restore_metadata_labels` + TTS strip/translate + Polly | `translate_tour_with_audio` 218–248 | `translate_zip_audio` 333–381 | coordinates (fixed late in fallback) |
| Write `audio_N.mp3` + `audio_N.txt` | `_create_mobile_compatible_zip` 1278–1286, 1351–1365 | `translate_zip_audio` 363–377 | — |
| Translate HTML `h1–h6` / `p` | `_create_mobile_compatible_zip` 1291–1325 | `translate_zip_audio` 383–397 | — |
| Set HTML `<title>` | `_create_mobile_compatible_zip` 1216–1218 | `translate_zip_audio` 400–403 | — |
| Update `manifest.json` name/short_name | `_create_mobile_compatible_zip` 1351–1366 | `translate_zip_audio` 409–424 | **yes — the title bug** |
| Re-zip `extract_dir` | `_create_mobile_compatible_zip` 1367–1374 | `translate_zip_audio` 426–439 | — |

**The only genuine difference between the two paths** is the *source of each stop's English text*:
- Primary: DB `tour_content`, split by `_split_tour_content_into_stops` (215).
- Fallback: the ZIP's `audio_N.txt` files, with HTML-paragraph grouping as a last resort (335–357).

Everything downstream of "I have a list of English stop texts + a tour name" is — or should be — identical. That's the seam.

---

## 2. Target architecture — four shared helpers + two thin adapters

Extract these (names are suggestions; keep them methods on `TranslationService`):

**(a) `_collect_stop_sources(tour_row, extract_dir) -> list[str]`**  *(the ONLY branch-specific logic)*
Returns the ordered list of English per-stop source texts. Two small internal adapters:
- from `tour_content` (folds in 215 + the split helper), used when `tour_content` is populated;
- from the ZIP (`audio_N.txt`, HTML fallback — folds in 333–357), used when it isn't.
Pick the adapter on `if tour_row.tour_content:` — the same predicate `translate_tour_with_audio` already uses at line 184.

**(b) `_translate_stop(source_text, lang) -> (display_text, tts_text)`**
One stop's text work, folding in the currently-duplicated logic:
- `display_text = _restore_metadata_labels(source_text, translate_text(source_text, lang), lang)` (keeps the English `Coordinates:`/`Address:` lines for map pins),
- `tts_text = translate_text(_strip_nav_fields_for_tts(source_text), lang)` (so Polly never reads coordinates).
Returns both. (Folds in 223–227 and 363–369.)

**(c) `_synthesize(tts_text, lang) -> bytes|None`**
Thin wrapper over `generate_audio` (143). Centralizes the "Polly returned nothing → keep original" decision.

**(d) `_assemble_translated_zip(original_zip_bytes, translated_name, stops, lang) -> bytes`**  *(the single home for title/manifest/HTML/re-zip)*
`stops` is a list of `{display_text, audio_bytes}`. One function that:
1. extracts the original ZIP,
2. writes each `audio_N.mp3` (audio_bytes) **and** `audio_N.txt` (display_text, which carries coordinates),
3. translates visible HTML `h1–h6` / `p`,
4. sets the HTML `<title>` to `translated_name`,
5. updates `manifest.json` `name` + `short_name` (`ensure_ascii=False`),
6. re-zips and returns bytes.
This is the critical consolidation: **title + manifest now live in exactly one place**, so the bug you just fixed becomes structurally impossible to reintroduce. Handle both audio formats here by parameter (modernized = write mp3 files; legacy = re-embed base64) so legacy tours also get the translated title/manifest — closing the gap I flagged in the last review.

**Optional (e) `_insert_translated_tour(...)`** — both entry points run near-identical `INSERT INTO audio_tours … RETURNING id` (260–267 and 1563–1570). Fold into one helper to kill a third copy.

### The two entry points after the refactor

Both shrink to the same shape:

```
def translate_tour_with_audio(id, lang):       # and _translate_tour_from_zip(...)
    row = load_tour(id)
    translated_name = translate_text(row.tour_name, lang)
    with extract(row.audio_tour) as extract_dir:
        sources = _collect_stop_sources(row, extract_dir)      # ← only differing step
        stops = []
        for s in sources:
            display, tts = _translate_stop(s, lang)
            stops.append({"display_text": display, "audio_bytes": _synthesize(tts, lang)})
        zip_bytes = _assemble_translated_zip(row.audio_tour, translated_name, stops, lang)
    return _insert_translated_tour(translated_name, ..., zip_bytes, lang)
```

After this, `translate_tour_with_audio` and `_translate_tour_from_zip` differ in *nothing* except which adapter `_collect_stop_sources` chooses. `_create_mobile_compatible_zip` and `translate_zip_audio` are deleted (their bodies absorbed into the shared helpers).

---

## 3. Configuration vs. code (so local == cloud)

While you're in here, make sure nothing that varies by environment is hard-branched in code. Move/keep these as configured values, identical code reading them:
- **Voice map** (`'ko':'Seoyeon'`, etc.) and **supported languages** — a single in-file dict is fine *as long as it's one file*; better, a `languages.yaml` / DB table both envs read.
- **DB DSN, AWS region, Polly settings, PORT** — already env-driven; confirm no literal fallback diverges between Compose and Cloud Run.
- **Thresholds** that live in the tour-generator (`tour_settings.py`) are already centralized — good pattern; mirror it here if any magic numbers appear.

The test: grep the file for any `if ENV ==`, hostname, or `localhost` literal that changes behavior. There should be none — only `os.getenv(...)` reads.

---

## 4. Behavior-preserving test checklist (must exercise BOTH entry points)

This is the safety net — run it before and after, expect identical results:

1. **Primary path** — a tour with `tour_content` populated. Request RU + ZH. Assert: `manifest.json` `name` is translated; HTML `<title>` and `h1` translated; each `audio_N.txt` begins with an English `Coordinates:` line; audio is in-language; stop count matches.
2. **Fallback path** — a tour with `tour_content = NULL` (e.g. an older tour, or null it in a staging row). Same request, **same assertions**. This is the path that only exists because of legacy data and is the one that keeps breaking — it must be tested every time.
3. **Parity assertion** — for an equivalent tour, the two paths should produce structurally identical ZIPs (same file list, same manifest keys, coordinates present in both). A quick `unzip -l` + manifest diff is enough.
4. **Legacy format** — one base64-embedded tour, confirm it now also gets a translated title/manifest (the previously-missing case).
5. **Compile gate** — `python -m py_compile development/translation-service/translation_service.py` in the deploy script, abort on failure. (Carry-over from the last review — cheap insurance against a truncated file taking the container down on boot.)

---

## 5. Rollout

1. Refactor in one commit, helpers + both entry points together; delete the two old assembly functions in the same commit so no dead duplicate lingers.
2. `py_compile` + run the checklist locally (both paths).
3. Deploy to **staging**, smoke-test both a populated and a NULL-`tour_content` tour.
4. Promote to prod. Because local, staging, and prod now run the identical helpers, the smoke test in staging is finally a real predictor of prod — which is the whole point.

**Longer term, to retire the fallback entirely:** backfill `tour_content` for the old NULL tours. Once production has no NULL-`tour_content` tours, the fallback adapter is dead weight kept only as a safety net — but with this refactor it's no longer a *divergent* path, just an alternate input source feeding the same code.

---

## Bottom line
Yes — converging into shared helpers is exactly the fix, and it's the right one. The seam is clean: one `_assemble_translated_zip` owns title/manifest/HTML/re-zip, one `_translate_stop` owns per-stop text, and the two entry points differ only in a single input adapter. Keep environment-specific values in config so local and cloud run byte-identical code. Gate every deploy on `py_compile` and the two-path checklist, and staging smoke tests finally mean something.
