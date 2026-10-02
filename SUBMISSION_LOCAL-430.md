# SUBMISSION_LOCAL-430.md

## Summary

LOCAL-430 closes the gap identified in D381: `_fetch_from_wayback()` fetched "whatever
snapshot you have" (`web/2/{url}`) and never inspected which one it got. Now:

1. **Snapshot timestamp parsed** from the redirect URL (`/web/{14-digit-ts}/{url}`)
2. **90-day staleness bound** enforced — snapshots older than this are refused
3. **Archive provenance visible** per work via `is_from_archive` / `wayback_snapshot_timestamp`
   (same mechanism as LOCAL-426's THIRD-PARTY, a third category)
4. MFA Unbound regression confirmed: Boris Fridman, Louis Broder, Mourlot Frères all present

---

## 1. Snapshot Timestamp Parsing

`_parse_wayback_timestamp(url)` extracts the 14-digit timestamp from the Wayback
redirect URL. The Wayback Machine redirects `/web/2/{url}` → `/web/{YYYYMMDDHHmmss}/{url}`.
After the redirect, `resp.url` carries the timestamp.

**Actual timestamps observed in today's live run:**
- MFA exhibitions listing: `20260729153204` (age: 13 days)
- MFA exhibition detail: `20260812064828` (age: 0 days — hours old)

---

## 2. Staleness Bound: 90 Days

**`WAYBACK_MAX_STALENESS_DAYS = 90`**

### Reasoning

Exhibition pages are time-bounded content. A major exhibition typically runs 3–6 months.
A snapshot that is 90 days old could still describe an active show (the show opened 3
months ago and is still running). Beyond 90 days, the risk of narrating a dismounted
exhibition outweighs the value of having *any* source. Specifically:

- **Why not 30 days?** Too aggressive — exhibition pages don't change frequently during
  a run. A show open since January still has the same page in March. 30 days would reject
  valid snapshots for current shows that the Wayback Machine simply hasn't re-crawled.
- **Why not 180 days?** Too permissive — an exhibition page from 6 months ago is more
  likely to describe a show that has since closed and been replaced.
- **Why 90 is generous enough:** The pipeline ALSO checks run dates when the page
  carries them (Step 4). If the exhibition's closing date has passed, the pipeline
  refuses the tour regardless of snapshot age. The staleness bound is a safety net for
  pages that *don't* carry explicit dates — which is exactly the dangerous case.
- **"No source" is safe:** The pipeline already handles the case where no exhibition
  content is found. It falls to third-party sources or returns a clean "not found"
  rather than silently inventing content. A stale archive that narrates a dismounted
  show is worse than no archive.

### Test boundaries

- 89 days → accepted ✓
- 91 days → rejected ✓
- 0 days (MFA today) → accepted ✓

---

## 3. Archive Provenance

### Mechanism

`ExhibitionChecklistResult` gains three fields:
- `is_from_archive: bool` — True when content came from web.archive.org
- `wayback_snapshot_timestamp: str` — e.g. "20260812064828"
- `wayback_age_days: Optional[int]` — e.g. 0

These are populated after Step 3 if `_last_wayback_metadata` is set (the module-level
store written by `_fetch_from_wayback()` on success).

### Log output categories (in `generate_tour_text.py`)

The provenance logging now has three categories (same log location, same mechanism):
1. `[LOCAL-426] ⚠️  THIRD-PARTY SOURCE — works came from {url}` (existing)
2. `[LOCAL-430] 📦 ARCHIVED SOURCE — venue's own words via web.archive.org (snapshot: ..., age: ... days)` (new)
3. (neither) — venue served content directly

**`is_third_party` is NOT set for archive content** — it's the venue's own words,
just served by a different host. The two flags are independent.

---

## 4. Neutralisation (Red Output)

### Staleness bound neutralised:

```
WITH staleness bound (90 days): text="''"
  ✓ CORRECTLY REJECTED (180-day snapshot)

  [LOCAL-430] Wayback snapshot timestamp: 20260213073904 (age: 180 days)
  [LOCAL-429] ✓ Wayback Machine success: https://www.example.com/old-exhibition (156 chars)
WITHOUT staleness bound (neutralised): text="'Test Exhibition\\nThis is a test exhibition with mor'"
  ✗ RED: With staleness bound neutralised, stale snapshot PASSES (wrong behavior)
```

### Timestamp parsing neutralised:

```
WITH _parse_wayback_timestamp active: ✓ stale rejected

  [LOCAL-430] ⚠ Could not parse snapshot timestamp from: https://web.archive.org/web/20260213073913/...
  [LOCAL-429] ✓ Wayback Machine success: https://www.example.com/old-exhibition (156 chars)
WITHOUT _parse_wayback_timestamp (neutralised): ✗ RED — stale content passes through
  Text starts: Test Exhibition
This is a test exhibition with more than twenty characters of co
```

### Metadata store neutralised:

```
WITH metadata store: _last_wayback_metadata = {snapshot_timestamp: 20260810073926, ...}
  ✓ Provenance would be attached to result
WITHOUT metadata store (neutralised): ✗ RED — is_from_archive=False, provenance LOST
  The result would show content_url=mfa.org with no indication it came from an archive
```

---

## 5. MFA Unbound Regression (PASS)

Live run: `mfa_unbound_LOCAL430.txt`

**All three names present in `TOUR_MFA_UNBOUND_EVAL.txt`:**

> "Louis Broder, known for his dedication to the livre d'artiste tradition,
> commissioned Miró to craft this portfolio"

> "Broder's vision was to produce editions where the artist, poet, and
> Mourlot Frères worked closely together"

> "The work's journey continued when Boris Fridman, a passionate collector
> of such artist's books, donated it to the Museum Boston."

**Archive provenance logged:**
```
  [LOCAL-430] Wayback snapshot timestamp: 20260812064828 (age: 0 days)
  [LOCAL-430] ARCHIVED SOURCE — snapshot 20260812064828, age 0 days
  [LOCAL-364] Result: ExhibitionChecklistResult(path=prose_llm, works=3, ..., ARCHIVED (snapshot: 20260812064828))
  [LOCAL-430] 📦 ARCHIVED SOURCE — venue's own words via web.archive.org (snapshot: 20260812064828, age: 0 days)
```

---

## 6. Palais Control (D302/D326)

`TOUR_PALAIS_LOCAL430.txt` — 4 stops, dates intact:

- Harpe by Naderman (Paris, **1780**)
- Violes gambe by William Turner (Londres, **1652**)
- Sacqueboute ténor by Anton Schnitzer (Nuremberg, **1581**)
- Basse de violon by Paolo Antonio Testore (Milan, **1696**)

4/4 stops, all with period-correct instrument dates. No archive involvement
(Palais Lascaris is not behind Cloudflare). No regression.

---

## 7. Test Results

**33 tests green** across the targeted suites:
- `test_local430_wayback_staleness.py` — 13 tests (timestamp parsing, staleness both sides, provenance)
- `test_local429_wayback_fallback.py` — 4 tests (existing, no regression)
- `test_local426_third_party_provenance.py` — 5 tests (existing, no regression)
- `test_local428_part4_attribution.py` — 5 tests (existing, no regression)
- `test_local429_prolog_ordering.py` — 3 tests (existing, no regression)
- `test_local260_prolog_structure.py` — 15 tests (existing, no regression)

No full-suite run (per D378/D379 instruction).

---

## 8. Exhibition Run Dates (Task point 4)

The MFA page carries exhibition dates which are already extracted by Step 4
(`_extract_closing_date`). If the closing date has passed, the pipeline refuses
the tour (`result.is_closed = True`). This mechanism predates LOCAL-430 and already
handles the strongest signal (explicit closing date on the page).

For pages without explicit dates, the 90-day staleness bound is the safety net.
The two mechanisms complement each other:
- **Page carries dates** → Step 4 catches closed shows regardless of snapshot age
- **Page lacks dates** → staleness bound prevents silently using 2019 snapshots

No new code was added for date extraction — it already works. The snapshot from today
(`20260812064828`) is well within bounds, and the content is verified present.
