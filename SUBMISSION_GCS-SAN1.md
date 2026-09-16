# SUBMISSION — GCS-SAN1

**Agent:** Services Kiro
**Branch:** `gcs-san1-narration-sanitiser` (based on `storied` = `5e53c56`)
**ClickUp:** `wdvrdayd3d` (urgent)
**Reported by:** Michael on-device, 2026-09-15, Preview tour 421. Verified by `Storied_Tours`.

Two separate faults in the **deployed** editing service made an edited stop save
corrupted text and speak its metadata header aloud. Both are now fixed in
`tour_editing_phase2.py`, with a red→green test and a staged (dry-run only)
redeploy.

## Base / branch discipline
- `git rev-parse HEAD` = `5e53c564c2303f9fd42d2d10351c79f297691eb7` at branch creation.
- `git merge-base --is-ancestor 5e53c56 HEAD` exits `0` (verified before and after
  committing). Branched from local `HEAD`, never from `origin/*`.

## Which file is deployed (not re-investigated)
`tour-editing` runs **`tour_editing_phase2.py`** (`--command python --args
tour_editing_phase2.py`, image `tour-editing:v2`). `tour_editing_phase2_container.py`
and `tour_editing_phase2_final.py` carry the same bad regex but are **not deployed**,
so per the task they were **left untouched**.

---

## Fault 1 — `sanitize_user_input` destroyed prose
Applied to every saved stop's text (`update-multiple-stops`), it:
- turned every `Coordinates:` into `Coordinates_` (`re.sub(r'[<>:"/\|?*]', '_', …)` — a *filename* rule),
- collapsed **all** newlines to one line (`re.sub(r'\s+', ' ', …)`), running the header into the narration,
- deleted apostrophes/quotes and stripped SQL keywords (`l'Impératrice` → `lImpératrice`).
  This bought nothing: **every DB call in the service is parameterised (`%s`)**, so
  string-stripping is not what prevents injection.

**Fix (LEAD decision):** added **`sanitize_narration_text`** and pointed the single
narration caller at it. It keeps only what narration needs:
- control-character removal, **but preserving `\t`, `\n`, `\r`** so line structure
  and the nav header survive (`re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', …)`),
- `clean_markdown_formatting`,
- `<script>…</script>` / `javascript:` / `on*=` stripping,
- the 10,000-char cap.

Dropped from the narration path: the SQL block, the `[<>:"/\|?*]` filename regex, and
the `\s+`→`' '` whitespace collapse.

`sanitize_user_input` is **unchanged** and remains available for any caller that
genuinely needs a filesystem-safe token. It had exactly one caller
(`update-multiple-stops`), which now calls `sanitize_narration_text`; a filesystem-safe
string, if ever needed, must be derived separately at the point of use.

## Fault 2 — the editing service sent the nav header to Polly
`generate_audio_for_stop` posted `text_content` to `/synthesize` unchanged, so Polly
spoke `Coordinates: …`, `Address: …`, etc. The generation pipeline does not:
`tour_generation_modernized.py:_strip_nav_fields_for_tts` removes those lines before
synthesis, and `translation_service.py` mirrors it.

**Fix:** duplicated the exact regex + four-line helper into `tour_editing_phase2.py`
(with a comment naming the two files it is kept in sync with) — **not** imported,
because `tour_generation_modernized` builds a Flask app and a job store at import.
The strip is applied to the **`/synthesize` payload only**, inside
`generate_audio_for_stop`; the `audio_N.txt` written to disk still contains every line.
`tour_generation_modernized.py` and `translation_service.py` were **not modified**.

---

## Acceptance criteria — evidence

### 1 & 2 — Round-trip + red→green (sanitiser)
`tests/test_gcssan1_narration_and_tts_strip.py` prints both the old and new sanitiser
output for the same Russian stop (name + nav header + `Orientation` + two narrative
paragraphs, containing `l'Impératrice` and `Coordinates: 43.7066, 7.2831`):

**RED — `sanitize_user_input` (current/pre-fix), one unbroken line, `_` for `:`,
apostrophe gone:**
```
'Памятник ИмператрицеAddress_ Promenade des Anglais, NiceCoordinates_ 43.7066, 7.2831Type_Specialty_ MonumentSpecific Examples_ statue de lImpératriceOperational Details_ open dailyOrientation_ Смотрите на набережную.Здесь стояла статуя de lImpératrice, символ эпохи.Второй абзац повествования продолжает историю.'
```

**GREEN — `sanitize_narration_text` (fixed), newlines/colons/apostrophes intact:**
```
"Памятник Императрице\nAddress: Promenade des Anglais, Nice\nCoordinates: 43.7066, 7.2831\nType/Specialty: Monument\nSpecific Examples: statue de l'Impératrice\nOperational Details: open daily\nOrientation: Смотрите на набережную.\n\nЗдесь стояла статуя de l'Impératrice, символ эпохи.\nВторой абзац повествования продолжает историю."
```

The test also runs a **real `bulk-save` round-trip** (local seeded source dir + mocked
R2/Postgres; the harness never contacts `r2.cloudflarestorage.com`), then reads back
`audio_1.txt` from the built ZIP and asserts it keeps its newlines, its
`Coordinates: 43.7066, 7.2831`, its `l'Impératrice`, and the same shape as an untouched
stop (`Address:`/`Coordinates:`/`Orientation:` present).

> **Windows note (not a code fault):** on Windows, Python's text-mode `open(...,'w')`
> translates `\n`→`\r\n` on write, so the round-trip `.txt` reads back with `\r\n`. The
> deployed container is Linux, where no translation happens. The byte-identity
> assertion therefore compares newline-agnostically (CRLF→LF), which reflects the
> deployed behaviour. I did **not** touch the pipeline's file-writing — that is out of
> scope for this task.

### 3 — TTS input excludes nav lines and nothing else
Asserted on the **exact** text captured by a Polly stub:
```
"Памятник Императрице\nOrientation: Смотрите на набережную.\n\nЗдесь стояла статуя de l'Impératrice, символ эпохи.\nВторой абзац повествования продолжает историю."
```
No `Address:`/`Coordinates:`/`Type/Specialty:`/`Specific Examples:`/`Operational
Details:` line; the stop name, `Orientation:` and both narrative paragraphs remain.
The test also asserts `TTS == saved .txt minus ONLY the nav lines` (nothing else changed).

### 4 — Safety still enforced, proven by a break-probe
The test feeds `<script>…</script>`, a `javascript:` href and an `onclick=` handler
through `sanitize_narration_text` and asserts all three are stripped, and that a
15,000-char input is capped to 10,000. A **break-probe** runs the same input through a
cleaner with the XSS rules removed and asserts `<script>` survives there — so the
safety assertions are real, not hollow.

### 5 — Existing guards still pass
```
tests/test_gcs5e_polly_auth_and_fail.py            EXIT=0   (9 passed)
tests/gcs5r_b1_import_guard.py                     EXIT=0
tests/test_local153_tour_editing_shims_guard.py    EXIT=0   (7 passed)
tests/test_gcs5r2_update_stop_empty_text.py        EXIT=0   (6 passed)
tests/test_gcssan1_narration_and_tts_strip.py      EXIT=0   (29 passed)
```

### 6 — Preservation-by-exact-text
**Yes — this also fixes the preservation problem.** Preservation matches an unchanged
stop by exact text (`orig_data['text_content'] == text_content`). Previously the saved
text was mangled by `sanitize_user_input`, so an "unchanged" stop no longer matched its
original and its audio was needlessly regenerated (and mis-spoken). With
`sanitize_narration_text` the saved text is content-identical to the source, so the
exact-text match holds and the original audio is preserved. The round-trip test asserts
the saved `.txt` is content-identical (newline-agnostic) to the submitted edit.

### 7 — Staged redeploy only (dry-run pasted, NOT deployed)
Reused `deploy_gcs5e_tour_editing_only.sh`, bumped to stage **`tour-editing:v3`**
(rollback target now the live `v2`). `--dry-run` (the default) deploys nothing — every
mutating call is printed:
```
== Build + push tour-editing image .../tour-editing:v3 ...
  [dry-run] docker build -f 'Dockerfile.cloudrun' --build-arg GIT_SHA='5e53c56' --build-arg RELEASE_TAG='v3t-gcs-san1' -t '.../tour-editing:v3' .
  [dry-run] docker push '.../tour-editing:v3'
== Deploy new tour-editing revision onto .../tour-editing:v3 ...
  [dry-run] gcloud run deploy 'tour-editing' ... --image '.../tour-editing:v3' --command python --args tour_editing_phase2.py --port 5022 --no-allow-unauthenticated ... --quiet
== ROLLBACK (if v3 misbehaves) — route 100% of traffic back to v2
...
DRY RUN COMPLETE — nothing was deployed. No gateway referenced.
```
The exact live `v2` revision name is left as a `<CONFIRM_LIVE_V2_REVISION>` placeholder
(to be confirmed against the live service before `--apply`) rather than a fabricated
revision ID; Option B rolls back by the `v2` image tag without needing the revision.

---

## PROCESS compliance
1. **Deployed nothing** — no `docker push`, no `gcloud run deploy/update`. Dry-run only.
2. Touched only `tour_editing_phase2.py`, `deploy_gcs5e_tour_editing_only.sh` and the new
   test. Not `api-gateway/`, not `audio_tour_app/`, not the other `tour_editing*` copies,
   not `tour_generation_modernized.py`, not `translation_service.py`.
3. Local harness only; it mocks R2/Postgres and never contacts
   `r2.cloudflarestorage.com`. No `DELETE FROM audio_tours`, no production writes.
4. Did not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/STATUS.md`,
   `GCLOUD_STORIED_START_HERE.md`, `BUILD_NUMBERS.md`.
5. Windows-safe: `encoding="utf-8"` on every read/write; Cyrillic/French bodies built
   in-process (no shell interpolation of raw non-ASCII).
6. Committed per fault and pushed. See commits below.

## Commits
- `ea49768` — GCS-SAN1 Fault 1: stop filename-sanitising saved narration
- `65f3061` — GCS-SAN1 Fault 2: strip nav header from TTS input so Polly stops reading it

## Not this task
The invented sculpture/artist in the regenerated stop 2 («Вечная бдительность», "Сара
Леви") is the fabrication problem (D562), owned by `Storied_Tours` — untouched here.

## Blocking questions
None.
