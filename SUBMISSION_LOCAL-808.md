# SUBMISSION — LOCAL-808: Starter catalog blind quality check + export bundle

**Branch:** `LOCAL-808-catalog-export` (base `subscribed` = c09692b5; `git merge-base --is-ancestor c09692b5 HEAD` → 0)
**Scope:** read-only review of DB `audiotours.audio_tours` ids **844–862** (19 tours), keep the good
ones, and produce an import bundle for GCloud_Storied. Nothing uploaded. No DB writes.

## What I did

1. **Pulled all 19 rows read-only** from the Mac dev Postgres (`development-postgres-2-1`, db
   `audiotours`), both `tour_content` and the stored `audio_tour` ZIP bytes. ZIP extraction was
   byte-exact (each extracted file equals `octet_length(audio_tour)`).

2. **Scored each tour 0–10** with the P1 house rubric (real places/exhibits with a heavy penalty for
   fabricated or wrong-place stops, checkable facts, specific stories, cross-stop connection,
   directions/pins, no garbled or off-topic prose, title quality). One line of reasons per tour is in
   `catalog/CATALOG_REVIEW.md`.

3. **Listen-check (ffprobe):** every tour has exactly one MP3 per delivered stop, each 52–192 s,
   9–12 min total, all readable. Audio was never a reason to drop. (847 and 851 correctly ship 4 MP3s
   because they only generated 4 stops.)

4. **Pin-check (≤ 150 m):** verified every stop coordinate against **Serper Places** and **Nominatim**,
   then ground-truthed every suspect stop against Nominatim's detailed records. Paid-API spend:
   **$0.00 metered** across 73 Serper Places calls (cap was $0.30).

5. **Export bundle** (`catalog_export.py` → `catalog/export/`): for each kept tour, the verbatim stored
   ZIP as `<id>.zip` plus `manifest.json` with the columns GCloud_Storied needs to INSERT.

6. **Importer** (`catalog_import.py`): dry-run by default, INSERT-only on `(request_string, language)`,
   reports row counts before/after. No DELETE, no UPDATE.

## Result: keep 6 of 19

**KEEP:** 845 Louvre (7.5), 846 Roman Forum (8.5), 848 British Museum (8.5), 856 Sultanahmet (7.5),
858 Prague Old Town (8.0), 859 Uffizi (7.5).

**DROP 13:** 844, 847, 849, 850, 851, 852, 853, 854, 855, 857, 860, 861, 862.

The dominant failure is **pins**: eight otherwise-good tours (844, 852, 855, 857, 860, 862, plus the
gross cases 854 and 861) are dropped on coordinates > 150 m. Two tours carry **fabricated / wrong-place
stops** (850 Met store products as exhibits; 861 Belvedere artworks not in the museum) and score 3.0–3.5.
Two under-delivered the stop count (847, 851). Full per-tour reasons: `catalog/CATALOG_REVIEW.md`.

## Deliverables

| file | committed? | what |
|------|:---:|------|
| `catalog/CATALOG_REVIEW.md` | yes | scoring table + keep/drop + one-line reasons + pin/audio findings |
| `catalog_export.py` | yes | builds `catalog/export/<id>.zip` + `manifest.json` (read-only on source DB) |
| `catalog_import.py` | yes | GCloud_Storied importer: dry-run default, INSERT-only, counts before/after, no DELETE/UPDATE |
| `.gitignore` | yes (modified) | adds `catalog/export/` so the audio ZIPs stay on disk, never committed |
| `catalog/export/*.zip` + `manifest.json` | **no (gitignored)** | the bundle, produced on disk for GCloud_Storied |

## Manifest / INSERT policy (per kept tour)

`tour_name, request_string, lat, lng, language, stops_count, tour_content, content_language, tour_kind`
from the source row, plus the catalog policy fields: `track='subscribed'`, `is_test=false`,
`price_tier=NULL` (free; `is_paid` is a GENERATED column, never inserted), `creator_type='audioura'`,
and `editor_score`. The manifest carries both `review_score` (raw 0–10, for humans) and `editor_score`
**clamped to [5.0, 8.0]** because `audio_tours.editor_score` has a CHECK constraint 5.0 ≤ score ≤ 8.0;
without the clamp the two 8.5 tours (846, 848) would violate it on INSERT.

## Verification evidence

- **Exporter ran:** 6 ZIPs written, all pass `unzip -t`, each byte length equals the source
  `octet_length(audio_tour)`; `editor_score` clamped 8.5 → 8.0 for 846/848; manifest has 6 tours.
- **`export/` is gitignored:** `git check-ignore catalog/export/859.zip catalog/export/manifest.json`
  returns both; `git status` never lists the ZIPs.
- **Importer dry-run** (against the local dev DB, read-only SELECTs only): row count 563 → 563 (delta 0);
  all 6 kept tours detected as already existing on `(request_string, language)` → would INSERT 0, skip 6.
  This proves both the INSERT-only guard and that dry-run writes nothing.
- **INSERT path proven schema-valid** by running one INSERT inside a transaction and rolling it back:
  the new row had `editor_score=7.5`, `track='subscribed'`, `creator_type='audioura'`,
  `is_paid=false` (generated from `price_tier=NULL`), `is_test=false`; all CHECK constraints satisfied;
  rollback restored 563 rows — no persisted write.

## How GCloud_Storied runs the import

```bash
# 1. receive catalog_export.py output: catalog/export/*.zip + catalog/export/manifest.json
# 2. dry-run first (no writes), review the plan and the before/after counts:
DATABASE_URL=postgresql://USER:PASS@CLOUDSQL_HOST:5432/DB python3 catalog_import.py
# 3. apply (INSERT-only; existing (request_string, language) rows are skipped, never modified):
DATABASE_URL=postgresql://USER:PASS@CLOUDSQL_HOST:5432/DB python3 catalog_import.py --apply
```

## Notes / constraints honoured

- Read-only on the source DB; no DELETE anywhere; importer does no UPDATE of existing rows.
- Paid-API spend for pin checks: $0.00 metered, well under the $0.30 cap (Serper only).
- Did not edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
  SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, GCLOUD_STORIED_START_HERE.md, TRAVEL_PROJECTS.md.
- Branch cut from HEAD (c09692b5), not from `origin/*`.
- The audio ZIPs are intentionally kept on disk under `catalog/export/` (gitignored) and are not committed.
