# SUBMISSION — LOCAL-586

**Listener-chosen stops stamped a "VERIFICATION HARNESS" banner into real tours (garbled content)**

- **Agent:** Mac Mini Kiro
- **Branch:** `LOCAL-586-user-stops-banner`
- **Base:** `storied` (766b027) — verified `git merge-base --is-ancestor 766b027 HEAD` exits 0.
- **Scope:** local only. No GCloud (the GCloud repair is GCloud_Storied's after LEAD files the deploy).

---

## 1. Defect

Michael (2026-10-05, share `RY7jFTKu` → tour 371, translation of 370):
> "Some of the old tours are presented with only one stop and even that stop is garbled… when I
> wanted to get the new tour of the garbled one, I get the garbled one back."

Tour **370** was a ONE-stop listener-chosen tour (Chart House) requested by Michael's phone
(`cost_ledger.user_id = USER-1073427300`) through the orchestrator. Its `tour_content` opened with the
`⚠️ FORCED STOPS — VERIFICATION HARNESS (LOCAL-357)` block **repeated 70 times**, so the app rendered
a garbled stop header. The narration and audio were fine; only the content header was garbage. Tours
**366, 367** (2026-09-24) carried the same banner. **371** is the Russian translation of 370 (the
banner was not copied into it, but it was translated from the bad source).

The product feature "specify your own stops" (LOCAL-523/525/547, `USER_STOPS_ENABLED`) reaches the
engine's LOCAL-357 forced-stops path, whose own comments say *"THIS IS A VERIFICATION HARNESS — NOT A
PRODUCT FEATURE."* That path stamped the banner.

---

## 2. Root cause — TWO independent faults

### Fault A — the two callers were conflated
`generate_tour_text(..., forced_stops=[...])` was built (LOCAL-357) as an internal verification
harness and stamped the banner whenever `forced_stops` was present. Since LOCAL-523/525/547 promoted
the same `forced_stops` path to a **product** input (a listener's own chosen stops, forwarded by the
orchestrator → tour-generator `/generate`), the banner began landing on **real tours**.

### Fault B — the banner repeated 70×
The banner was built with Python **implicit string-literal concatenation**:

```python
_forced_banner = (
    "=" * 70 + "\n"
    "⚠️  FORCED STOPS — VERIFICATION HARNESS (LOCAL-357)\n"
    ...
    f"    Forced: {forced_stops}\n"
    "=" * 70 + "\n\n"
)
```

Adjacent string literals are joined at **compile time**. The f-string line
`f"    Forced: {forced_stops}\n"` sat immediately before the literal `"="`, so they merged into
`"    Forced: [...]\n="`, and the trailing `* 70` then repeated **the whole merged body 70 times** —
each block closed by a lone `=`. That is exactly the shape found in the DB (tour 370): one full 70-`=`
rule at the top, then 70 HARNESS blocks each closed by a single `=`, then the real tour. Confirmed:

```
HARNESS lines in tour 370 content : 70
full 70-'=' rules                 : 1
lone '=' lines                    : 70
```

---

## 3. The fix (Deliverable 1)

`generate_tour_text.py`:

- Added an explicit **`harness=False`** parameter. The banner is now gated on
  **`if harness and _forced_stops_active:`** — the mere presence of `forced_stops` no longer stamps it.
  The orchestrator / tour-generator `/generate` product path NEVER sets `harness`, so a listener's
  chosen-stops tour carries **no banner and no "not naturally selected" wording** — nothing in
  `tour_content` beyond the normal tour format. Only genuine verification-harness callers (run_* /
  tests) pass `harness=True`.
- `forced_stops` still drives injection/bypass/`total_stops` for **both** callers (unchanged). The
  cache-skip guard (`not _forced_stops_active`) is unchanged.
- The banner is now built in a single module-level helper **`_build_harness_banner(forced_stops)`**
  using `"\n".join([...])` of a list, so **no string literal is ever adjacent to a `* N`** and the
  banner is written **exactly once**. This both fixes Fault B and makes the banner unit-testable.

Verified: `HARNESS count = 1`, two 70-`=` rules, zero lone-`=` lines.

---

## 4. Tests (Deliverable 2) — red on storied, green after

`tests/test_local586_harness_banner.py` (12 tests):

- `test_harness_banner_appears_exactly_once` / `test_separator_bar_is_seventy_equals_not_a_lone_equal`
  — pin Fault B (the lone-`=` ×70 signature can never return).
- `test_product_path_forced_stops_produce_no_banner` — a listener's stops (`harness=False`) produce a
  tour with **no** `VERIFICATION HARNESS` / `FORCED STOPS` / `naturally-selected` text that parses to
  the requested stop.
- `test_harness_path_stamps_banner_once` — `harness=True` → banner present, once.
- `test_generate_tour_text_accepts_harness_flag`, `test_banner_write_is_gated_on_harness`,
  `test_builder_has_no_literal_adjacent_to_multiply` — the flag + gating are wired.
- `test_service_product_path_never_sets_harness`, `test_orchestrator_never_sets_harness` — the product
  entry the orchestrator uses forwards `forced_stops` but never requests the banner.

Red/green proof (stashing the fix restores storied `generate_tour_text.py`):

```
RUN AGAINST STORIED : 9 failed, 3 passed
GREEN AFTER         : 12 passed
```

Required suites kept green (paste):

```
tests/test_local357_forced_stops.py test_local394_never_drop_a_stop.py
tests/test_local576_named_anchors.py tests/test_local521_user_stops_validate.py
tests/test_local522_user_stops_route.py tests/test_gcs_ks1_user_stops_killswitch.py
tests/test_local586_harness_banner.py
→ 1 failed, 96 passed
```

The single failure is **pre-existing on storied** and unrelated:
`test_local357 ... test_forced_stops_creates_poi_list_from_names` asserts the source contains
`poi_list = [_new_poi(name) for name in forced_stops]`, but LOCAL-554 already changed that line to use
`_forced_titles`. It is RED on `storied` **before** this change (verified by stashing) and is left out
of scope. Two LOCAL-357 banner source-inspection tests were updated to inspect the module (the banner
literal moved into the helper); their intent is preserved.

---

## 5. Repair script (Deliverable 3) — run on the local DB

`repair_local586_harness_banner.py`:

- `--dry-run`: lists every `audio_tours` row whose `tour_content` column **or** stored ZIP member
  `tour_content.txt` contains the banner, with `id`, user (best-effort from `cost_ledger` by time —
  `audio_tours` has no user_id column), `created_at`, `stops_count`, where the banner lives, and the
  block count. Changes nothing.
- `--apply`: for each affected row it **first** backs up `tour_content` + `audio_tour` bytes to
  `/Volumes/AudiouraSSD/backup_local586/<id>.json` (+ `.zip`); then removes **only** the anchored
  leading banner region from the column and from the ZIP's `tour_content.txt`, **rewriting the ZIP so
  every other member (audio mp3, audio_N.txt, index.html, manifest.json, service-worker.js) is
  byte-identical** and original compression preserved; verifies every `audio_*.mp3` md5 is unchanged
  **before** writing; then `UPDATE`s the row. **No DELETE, no lat/lng change, no regeneration.**

Run on the local DB (`localhost:5433`). Dry-run then apply:

```
affected rows: 3
id=366  stops_count=3  banner_in=column×70, zip×70   28422 → 5880 chars (70 blocks removed)
id=367  stops_count=2  banner_in=column×70, zip×70   28712 → 6170 chars (70 blocks removed)
id=370  user=USER-1073427300  stops_count=1  banner_in=column×70, zip×70   19040 → 2448 chars
    audio md5 unchanged (e.g. 370 audio_1.mp3 = b688c9d1f591eb0b7cd09cbd8f526e21)
    UPDATED (no DELETE, lat/lng untouched)
```

Post-apply verification:

- Rows with the banner in `tour_content`: **0**.
- Tour 370 now starts `Step-by-Step Audio Guided Tour: restaurant tour, Boston, MA`.
- `lat/lng` and `stops_count` preserved; stored ZIP `tour_content.txt` banner = 0; `audio_1.mp3` md5
  matches the backup.
- Re-running `--dry-run` reports **0 affected**.
- **371** (RU translation of 370): no banner present — correctly **left untouched**.

Backups: `/Volumes/AudiouraSSD/backup_local586/{366,367,370}.json(+.zip)`.

---

## 6. Live container verification (Deliverable 4, D608)

- Rebuilt the generator **with the override**: copied the fixed `generate_tour_text.py` into
  `audioura-tour-generator-1`, committed it to image `audioura-tour-generator:local586`, and recreated
  the container with `USER_STOPS_ENABLED=true`, `COST_HARD_LIMIT_USD=1.00`,
  `TOUR_TEST_MODE_ALLOW_REQUEST=true`, preserving network `development_default`, alias `tour-generator`
  and the `tours` mount. Recreated the orchestrator with `USER_STOPS_ENABLED=true` (port 5002). The
  previous containers are preserved, stopped and renamed `*-pre586` (never deleted) for rollback.
- Submitted a 2-stop user-stops request through the app's endpoint
  `POST http://localhost:5002/generate-complete-tour`:
  `stops=["Chart House","Union Oyster House"]`, `location="Boston, MA"`, `tour_type="restaurant"`,
  `is_test=true`. Job `3e41c903…` → **completed** → row **393** (`is_test=t`).

`tour_content` head (NO banner — the product path is clean):

```
Step-by-Step Audio Guided Tour: Boston, MA - Restaurant Tour
Tour-Category: restaurant

Stop 1: Union Oyster House

Address: 41 Union St, Boston, MA 02108

Coordinates: 42.3611, -71.0569

Type/Specialty: Historic seafood restaurant
...
```

- `VERIFICATION HARNESS` count in the live `tour_content`: **0**. No "not naturally selected" wording.
  Normal tour format.
- Parsed stops: `Stop 1: Union Oyster House`, `Stop 2: Parker's Restaurant`.
  **Note (out of scope):** the forced list honoured Union Oyster House, but *Chart House* was replaced
  by Parker's Restaurant by the downstream existence/confidence gates (LOCAL-394/480 territory),
  independent of the LOCAL-586 banner fix. The banner contamination — the subject of this task — is
  confirmed gone on the product path.
- OpenAI cost for the run (cost_ledger): **$0.14 total** (spine $0.0068 + tour_generate $0.1337 + tts
  $0.00), under the $1 cap.
- Hid the test row: backed up its lat/lng (42.3608, -71.0495) + audio to
  `/Volumes/AudiouraSSD/backup_local586/393_testrow.json(+.zip)`, then `UPDATE lat=NULL, lng=NULL WHERE
  id=393`. Row kept (`is_test=t`), **never deleted**.

---

## 7. Files changed

| File | Change |
|------|--------|
| `generate_tour_text.py` | `harness=False` param; banner gated on `harness and _forced_stops_active`; `_build_harness_banner()` helper (join, no `* N` literal) — fixes conflation + 70× repetition. |
| `tests/test_local586_harness_banner.py` | New — 12 tests, red on storied / green after. |
| `tests/test_local357_forced_stops.py` | Two banner source-inspection tests retargeted to the module after the helper refactor (intent preserved). |
| `repair_local586_harness_banner.py` | New — dry-run/apply repair; backups; byte-identical ZIP rewrite; md5-verified audio; no DELETE / no lat-lng / no regen. |

## 8. Process

- `git add` + `git commit` after each step; first commit within 15 minutes; branch pushed with
  `git push -u origin LOCAL-586-user-stops-banner`.
- Did not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`, `.continuous_dev/STATUS.md`.
- `git rev-list --count storied..HEAD` ≥ 1 (verified in the final step).
