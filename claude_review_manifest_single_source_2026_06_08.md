# Claude Review → Kiro — Manifest Title Fix + Single Source of Truth

**Date:** 2026-06-08
**Re:** `REVIEW_FOR_KIRO_manifest_fix_single_source_2026_06_08.md` (`translation-service-00009-7rh`)
**Scope:** Services / GCloud only. Focus: **no cloud regressions.**
**Verdict:** ✅ **Approve** — the fix is correct, the file deletion is safe, and cloud + local now build from one file. Two must-dos before you consider it closed: (1) run a `py_compile` gate (I hit a truncated read — explained below), (2) be aware the legacy branch still doesn't translate the manifest. Plus one strategic note that directly answers Sir Michael's parity concern.

---

## 1. File deletion — SAFE, no cloud regression ✅

Verified the deleted top-level copy is genuinely unreferenced:

- **Nothing imports it as a module.** `grep -rn "import translation_service"` across the repo → no hits. It's a Flask entrypoint, never imported, so deletion can't break another service.
- **Cloud Run uses the surviving file.** `translation-service/Dockerfile`: `COPY translation_service.py .`, build context `translation-service/`, deploy `--source=development/translation-service`. The file it copies exists. ✅
- **Local uses the same file.** `docker-compose.yml:124` → `build: ./translation-service`. Same file. ✅
- **`Dockerfile.cloudrun` (`COPY *.py /app/`) is irrelevant here** — the translation service has its own Dockerfile; no service that uses `Dockerfile.cloudrun` imports the deleted module.
- No `.sh` / `.yml` / `Dockerfile*` references the deleted top-level path.

**Result:** true single source of truth at `development/translation-service/translation_service.py`, built identically by Compose and Cloud Run. This is the right cleanup. No build or import regression.

## 2. Manifest fix in the fallback path — CORRECT and COMPLETE ✅

- The cloud branch is reached as designed: `translate_tour_with_audio` → `if not tour_content:` (184) → `_translate_tour_from_zip` (196) → `translate_zip_audio`.
- The new manifest update (`translate_zip_audio`, lines 409–424) is **correctly scoped**: it sits in the modernized-format branch, after the HTML is written, before the re-zip — so it runs **once**, not inside the per-stop loop. It reads `manifest['name']`, translates it, writes `name` + `short_name`, with `ensure_ascii=False` (good — preserves Cyrillic/CJK). Uses `with open(...)` properly (cleaner than the snippet in your handoff).
- The re-zip (426–433) includes the updated `manifest.json`, and `_translate_tour_from_zip` persists the ZIP to `audio_tours.audio_tour` and returns the new id (1547–1576). So the app downloads the updated manifest → reads `data['name']` → translated title. **End-to-end correct for cloud (fallback) tours.** ✅
- Primary path manifest update (1351–1366) is intact; both paths now write the translated name. ✅

## 3. Parity / no lost functionality ✅

Confirmed the consolidation didn't drop prior fixes — all present in the single file: `ko: Seoyeon` voice, `_restore_metadata_labels` (coordinate preservation), `_strip_nav_fields_for_tts`, and the `audio_{i}.txt` source-of-truth logic. The host copy of the file is complete and valid through `app.run` (line 1712).

---

## Must-do before closing

**A. Run a compile gate before every deploy.** When I read the deployed file through one tool it came back **truncated at line 1633** mid-statement (`name_col = 'tour_name' if content_t…`) and failed `py_compile`; through the host file tool the same file was complete and valid to line 1712. That mismatch was a read/sync artifact on my side, **not** evidence your disk file is broken — but it's a free, decisive check, and a truncated `translation_service.py` would crash the container on boot (worst-case cloud regression). Add to your deploy script:

```bash
python -m py_compile development/translation-service/translation_service.py || { echo "ABORT: syntax error"; exit 1; }
```

If it passes on your machine, the deploy is safe. Please confirm it does.

**B. Legacy base64 branch still doesn't translate the manifest.** The manifest update you added is only in the **modernized** branch (`is_modernized_format`, 409–424). The legacy embedded-base64 branch (441+) has no equivalent, so a legacy-format tour translated via the fallback would still show an English title. Low risk (modernized is the live format), but note it so it's not a surprise later — or add the same block to the legacy branch for completeness.

---

## Strategic — this is the real answer to the dev/prod-parity concern

Sir Michael's worry ("cloud and local don't go through the same code") is valid, and your "same file, different branch on `tour_content`" explanation is correct — but the durable risk isn't the two *files* (now fixed), it's the **two translation branches**: `translate_tour_with_audio` (primary, `tour_content` populated) vs `translate_zip_audio` (fallback, `tour_content` NULL). They carry parallel logic, and *this very bug* was a fix landing in one branch but not the other. Every future fix has the same trap.

Two ways to actually close the parity gap:

1. **Backfill `tour_content`** for the old NULL tours so the fallback path is effectively dead in production — then cloud and local both run the primary path, and the fallback becomes a rarely-exercised safety net.
2. **Converge the branches** so manifest/coordinate/title handling lives in one shared helper both call, instead of being duplicated.

Either removes the "works locally, breaks on cloud" class for this service. Until then: whenever you test locally, also test a tour with `tour_content = NULL` so the fallback branch gets exercised in dev, not discovered in prod.

---

## Bottom line
Approve `translation-service-00009-7rh`: deletion is safe, single-source consolidation is correct, fallback now translates the manifest title. Run the `py_compile` gate (A) and note the legacy-branch gap (B). For lasting parity, backfill `tour_content` or merge the two branches.
