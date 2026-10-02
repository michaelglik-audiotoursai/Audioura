# SUBMISSION — GCS-LANG1

**Task:** Run the language gate on the narration, not the whole stop blob. Stage only.
**ClickUp:** `wdvrdayd40` (normal)
**Agent:** Services Kiro
**Base:** storied = `407c2c1` (verified: `git merge-base --is-ancestor 407c2c1 HEAD` → exit 0)
**Branch:** `kiro/gcs-lang1` (branched from HEAD; not from `origin/*`)
**Deployed nothing.** Michael is field-testing build 26 against `tour-editing:v3`.

---

## Problem

`_bulk_save_core` in `tour_editing_phase2.py` ran the language gate over the
**entire** stop blob:

```python
detected = _detect_text_language(stop_data['text_content'])
```

The blob always carries a Latin metadata header (`Coordinates:`, `Address:`,
`Type/Specialty:`, `Specific Examples:`, `Operational Details:`) and often Latin
place names, plus (in the reported case) one English `Orientation:` line.
Comprehend sees mixed scripts and returns a neighbouring language — a Russian
narration was reported as `cv` (Chuvash, which shares Cyrillic with `ru`) — so a
legitimate Russian edit was falsely rejected with `LANGUAGE_MISMATCH`. An
all-Russian body with the same header passed.

## Fix (only `tour_editing_phase2.py`)

Detect language on the **narration**, not the blob. Added
`_narration_for_language_detection(text)` and call it before
`_detect_text_language` at the gate:

```python
narration = _narration_for_language_detection(stop_data['text_content'])
detected = _detect_text_language(narration)
```

`_narration_for_language_detection`:
1. applies the existing GCS-SAN1 `_strip_nav_fields_for_tts` to remove the
   structured nav header (`Coordinates:`/`Address:`/…); and
2. **drops a single leading stop-name line** — the first non-blank line, unless
   it is itself an `Orientation:` line or a surviving nav line.

**Choice on the leading stop-name line: I strip it.** Stop names are frequently
Latin place names even inside a `ru`/`zh`/… tour (e.g. `Avenue Auguste Vérola`),
and that Latin name plus the Latin `Orientation:` line is exactly the
cross-script noise that misleads the detector. The `Orientation:` line and every
narrative paragraph are kept.

**Fail-open preserved:** if the stripped body is empty or too short (`< 25`
chars), `_detect_text_language` returns `None` and the save is **not** rejected —
today's behaviour, no new rejection invented.

**Nothing else changed:** the saved `.txt`, the TTS input
(`_strip_nav_fields_for_tts` is still applied separately at synthesis), the
voices — all untouched. This function only produces the string handed to the
detector.

### One added test seam (production-inert)

To let the local container run deterministically without AWS (acceptance #4),
`_detect_text_language` now goes through `_detect_dominant_language_raw`, which
consults an optional `LOCAL_LANGUAGE_STUB_URL` HTTP endpoint when set and
otherwise calls AWS Comprehend exactly as before. This mirrors the existing
`POLLY_TTS_URL` / `LOCAL_IDENTITY_TOKEN` seams. **Production never sets it, so
the Comprehend path is unchanged.**

---

## Acceptance criteria — evidence

### 1. Red → green (exact reported blob), Comprehend mocked deterministically

`tests/test_gcslang1_language_gate_narration.py` builds the exact blob (ru
narration + Latin header + one English `Orientation:` line, all from `\u`
escapes so the file stays ASCII) and mocks the detector deterministically
(mixed Cyrillic+Latin → `cv`; clean Cyrillic → `ru`; Latin → `en`).

- **RED** (pre-fix behaviour, detect on the raw blob): `400 LANGUAGE_MISMATCH`,
  `detected=cv`.
- **GREEN** (fix, detect on the stripped narration): `200`, save reaches the
  persistence path.

Both proven at the helper level **and** end-to-end through the real
`/update-multiple-stops` route.

### 2. Still rejects real mismatches + break-probe

Same test: an all-English narration on a `ru` tour → `400 LANGUAGE_MISMATCH`,
`detected=en`, rejected before the save. A **break-probe** neutralises
`_detect_text_language` and shows the same English blob then sails through — so
the guard is real and the test fails if the check is removed.

Plus: a header-only blob (empty stripped body) is **not** rejected (fail-open).

```
Results: 14 passed, 0 failed
```

### 3. Existing guards still pass

```
tests\test_gcslang1_language_gate_narration.py -> exit 0
tests\test_gcssan1_narration_and_tts_strip.py  -> exit 0   (29 passed)
tests\test_gcs5e_polly_auth_and_fail.py        -> exit 0   (9 passed)
tests\gcs5r_b1_import_guard.py                 -> exit 0   (PASS)
tests\test_local153_tour_editing_shims_guard.py-> exit 0   (7 passed)
tests\test_gcs5r2_update_stop_empty_text.py    -> exit 0   (6 passed)
```

### 4. Verify by effect against a local running container (both responses)

`tests/gcslang1_verify_language_gate.py` stands up local Postgres (docker,
`127.0.0.1:5546`) + MinIO (`127.0.0.1:9012`, R2 stand-in) + the auth-required
Polly stub + the deterministic language stub (`tests/gcslang1_lang_stub.py` via
`LOCAL_LANGUAGE_STUB_URL`), seeds a `ru` tour, and drives the **real**
`tour_editing_phase2.py` container over HTTP. The harness prints its R2 safety
refusal and only ever talks to local MinIO; no production writes.

**[A] Reported blob (ru narration + Latin header + English `Orientation:`) → HTTP 200:**
```json
{"download_url": "/tour/dc271444-5e61-4b65-9d8c-0a31552b3f43/download",
 "message": "Tour updated successfully with 1 text-to-speech audio file(s)",
 "new_tour_id": "dc271444-5e61-4b65-9d8c-0a31552b3f43",
 "status": "success",
 "stops": [{"audio_source": "tts_generated", "audio_updated": true,
            "generate_audio_from_text": true, "has_custom_audio": false,
            "stop_number": 1, "text_updated": true}]}
```

**[B] Genuine mismatch (all-English narration on the `ru` tour) → HTTP 400:**
```json
{"detected_language": "en", "error_code": "LANGUAGE_MISMATCH",
 "expected_language": "ru",
 "message": "This tour is in ru. The text for Stop 1 appears to be in en. Please write it in ru and try again.",
 "recoverable": true, "status": "error", "stop_number": 1}
```

```
RESULT: PASS — reported blob accepted; real mismatch still rejected.
```

### 5. Stage the redeploy (`--dry-run --editing-tag v4`) — deploy nothing

`bash deploy_gcs5e_tour_editing_only.sh --dry-run --editing-tag v4` (default tag
left unchanged; `v4` passed via flag). Every mutating call is printed only:

```
== Build + push tour-editing image .../tour-editing:v4 (own image, not shared audioura)
  [dry-run] docker build -f 'Dockerfile.cloudrun' --build-arg GIT_SHA='407c2c1' ...
            -t '.../services/tour-editing:v4' .
  [dry-run] docker push '.../services/tour-editing:v4'
== Deploy new tour-editing revision onto .../tour-editing:v4 (v1's env/secrets/flags)
  [dry-run] gcloud run deploy 'tour-editing' ... --image '.../tour-editing:v4'
            --port 5022 --no-allow-unauthenticated ...
DRY RUN COMPLETE — nothing was deployed. No gateway referenced.
```

---

## Files changed

- `tour_editing_phase2.py` — added `_narration_for_language_detection`, routed
  the gate through it, and added the production-inert `_detect_dominant_language_raw`
  test seam (+69/−2).
- `tests/test_gcslang1_language_gate_narration.py` — new red→green + still-rejects
  + break-probe + fail-open guard (Comprehend mocked deterministically).
- `tests/gcslang1_lang_stub.py` — new deterministic language-detection stub (no AWS).
- `tests/gcslang1_verify_language_gate.py` — new local-container verification-by-effect.

Not touched: the `_container.py`/`_final.py` copies, the gateway, the app, the
modernizer, the translation service, the deploy script's default tag, and none
of `DECISIONS.md`/`CLAUDE.md`/`BACKLOG.md`/`.continuous_dev/STATUS.md`/
`GCLOUD_STORIED_START_HERE.md`/`BUILD_NUMBERS.md`.

## Process notes

- Deployed nothing; staged `v4` dry-run only.
- Local Postgres/MinIO only; harness hard-refuses `r2.cloudflarestorage.com`;
  no production writes, no `DELETE FROM audio_tours`.
- Windows: `encoding="utf-8"` throughout; non-ASCII bodies built in-process from
  `\u` escapes (source files stay ASCII; no shell handles raw Cyrillic).

## Blocking questions

None.
