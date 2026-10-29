# SUBMISSION — LOCAL-808B: re-score the 11 re-made catalog tours, extend the export bundle

**Branch:** `LOCAL-808B-catalog-rescore`
**Base:** `subscribed` = `6764ce9e` (verified: `git merge-base --is-ancestor 6764ce9e HEAD` exits 0)
**Date:** 2026-10-29
**DB:** Mac dev Postgres (`development-postgres-2-1`, db `audiotours`, user `admin`) — **read-only**, no writes, no `DELETE`.

## What was asked

LEAD re-made 11 tours after LOCAL-808 on newer code (pin snap + Wikidata + museum checks): walking ids
**844, 849, 852, 853, 854, 855, 857, 860, 862** (generator `ab1c97e9`) and museums **850 Met, 861 Belvedere**
(`1f4cb350`, stop pool OFF). Re-score each on the LOCAL-808 rubric and keep rule (score ≥ 7.5 **AND** every
landmark pin ≤ 150 m; museums share one building pin), decide museum "in-collection" with Wikidata **P195/P276**
(the LOCAL-809 check) rather than memory, update `catalog/CATALOG_REVIEW.md`, and add the kept tours to the
export bundle via `catalog_export.py` (manifest regenerated for ALL kept tours, old + new).

## Method

- **Content (P1 rubric, 0–10):** read each tour's `tour_content` — real places/exhibits, checkable facts,
  specific stories, cross-stop connection, directions, no garbled/off-topic paragraphs, no leaked meta-text.
- **Listen-check:** extracted each kept tour's stored ZIP and ran `ffprobe` — one MP3 per stop, plausible
  durations. Exported ZIP byte length verified equal to the DB `octet_length(audio_tour)` for every kept tour.
- **Pin-check (≤ 150 m):** ground-truthed each stop against **free** sources — Wikidata **P625** by QID, with
  **Nominatim (OSM)** fallback — and measured haversine distance. Several first-pass QID/OSM matches were
  obviously wrong (wrong continent / wrong entity) and were re-resolved before judging.
- **Museum in-collection:** Wikidata **P195** (collection) / **P276** (location) for each artwork, checked against
  the museum QID (Met `Q160236`, Belvedere `Q303139`).

## Budget

Pin + collection checks used only **free** Wikidata WDQS and Nominatim. **Paid-API spend: $0.00 metered**
(cap is $0.30 **total across all runs** — honored; the Serper key was never called). This mirrors LOCAL-808,
which also metered $0.00 on its pin checks.

## Results — 11 re-made tours

| id  | tour | score | worst pin | all ≤150 m | decision |
|-----|------|:---:|:---:|:---:|:---:|
| 844 | Montmartre, Paris (walk) | 7.5 | 113 m | ✓ | **KEEP** |
| 849 | Westminster, London (walk, 4/5) | 6.5 | 140 m | ✓ | DROP — leaked stop-count apology ×2; score < 7.5 |
| 850 | Metropolitan Museum, NY (museum) | 8.0 | 12 m | ✓ | **KEEP** |
| 852 | Gothic Quarter, Barcelona (walk) | 7.5 | 97 m | ✓ | **KEEP** |
| 853 | Gaudí architecture, Barcelona (walk) | 8.0 | 87 m | ✓ | **KEEP** |
| 854 | Higashiyama temples, Kyoto (walk) | 6.5 | 351 m | ✗ | DROP — pins |
| 855 | Asakusa & Senso-ji, Tokyo (walk, 4/5) | 6.0 | 260 m | ✗ | DROP — structural + pins |
| 857 | Alfama, Lisbon (walk) | 7.5 | 252 m | ✗ | DROP — pin (Museu do Fado 252 m) |
| 860 | San Marco, Venice (walk) | 7.5 | 477 m | ✗ | DROP — whole set ~300–480 m NW |
| 861 | Belvedere Museum, Vienna (museum) | 6.5 | 1379 m | ✗ | DROP — building pin |
| 862 | Old Quarter, Hanoi (walk) | 7.5 | 889 m | ✗ | DROP — pins |

**Kept from this batch (4): 844, 850, 852, 853.**

### Per-landmark pin distances (ground-truth source in parentheses)

- **844** Espace Dalí 14 (OSM), Sacré-Cœur 14 (OSM), Place du Tertre 16 (OSM), La Maison Rose 113 (OSM), Bateau-Lavoir 11 (OSM) — worst **113 m**.
- **849** Houses of Parliament 44 (WD Q62408), Westminster Abbey 28 (WD Q5933), The Cenotaph 140 (OSM), Churchill War Rooms 9 (OSM) — worst **140 m**.
- **850** Met building pin **12 m** (WD Q160236).
- **852** Barcelona Cathedral 78 (WD Q17155), Plaça del Rei 5 (OSM), Carrer del Bisbe 46 (OSM), Palau de la Generalitat 97 (OSM), Plaça Sant Jaume 12 (OSM) — worst **97 m**.
- **853** Casa Vicens 0 (WD Q746333), Casa Milà 57 (WD Q207870), Casa Batlló 13 (WD Q461371), Sagrada Família 6 (WD Q2470217), Hospital de Sant Pau 87 (WD Q507282) — worst **87 m**.
- **854** Nanzen-ji 161, Ryōzen Kannon 18, Eikan-dō 351, Kōdai-ji 69, Shōren-in 37 — worst **351 m** (OSM).
- **855** Kaminarimon 2, Hōzōmon 260, Nakamise 53, Asakusa Shrine 77 — worst **260 m** (OSM / WD Q670049).
- **857** Sta Luzia 9, Castelo de São Jorge 14, Igreja Sto António 17, Panteão 28, Museu do Fado 252 — worst **252 m** (OSM).
- **860** Campanile 477, Palazzo Ducale 328, Basilica 320, La Fenice 47, Museo Correr 280 — worst **477 m** (OSM / WD Q754194, Q1470912).
- **861** Belvedere building pin **1379 m** (stored 48.2031, 16.3747 vs the palace at 48.1914, 16.3808 — WD Q303139).
- **862** Bạch Mã 571, Đồng Xuân 889, Thăng Long 250, Ngọc Sơn 225, Hoàn Kiếm 0 — worst **889 m** (OSM / WD Q1151254).

## Museum in-collection — Wikidata P195/P276 (corrects LOCAL-808)

**850 Met (`Q160236`) — all 5 in-collection:**
Great Wave off Kanagawa `Q252485` (P195 Met); Allegory of the Catholic Faith `Q467359` (P195+P276 Met);
View of Toledo `Q883994` (P195+P276 Met); Melencolia I `Q1362177` (P195 Met); The Death of Socrates
`Q1752990` (P195+P276 Met). The LOCAL-808 Met tour had two Met-Store gift-shop products written up as exhibits
(scored 3.0) — the re-make has no fabricated stops. **8.0.**

**861 Belvedere (`Q303139`) — all 5 in-collection:**
Portrait of Père Paul (Monet) `Q27665416`; The Evil Mothers (Segantini) `Q749201`; Fishermen in Poissy
(Monet) `Q3234987`; The Plain of Auvers (Van Gogh) `Q26221225`; Judith I (Klimt) `Q2324643` — each P195+P276
Belvedere. **This corrects LOCAL-808**, which wrongly called Monet's *Portrait of Père Paul* and Van Gogh's
*The Plain of Auvers* foreign; both verify in the Belvedere. The exhibits are now correct, but the tour is
still dropped because its shared building pin is 1,379 m off the actual palace (and stop 1 carries fabricated
"€65; free for Métropole residents" boilerplate).

## Changes committed

- `catalog/CATALOG_REVIEW.md` — the summary-table rows for the 11 re-made ids now carry the LOCAL-808B scores,
  pins and decisions (marked ᴮ) and replace the old rows; the kept-tours line is **"Kept tours (10): 844, 845,
  846, 848, 850, 852, 853, 856, 858, 859"**; a new **LOCAL-808B re-score** section gives per-tour rationale with
  Wikidata QIDs; and the original one-line-reason list is annotated as superseded for those 11 ids.
- `catalog_export.py` — `KEEP_SCORES` extended to the 10 kept tours:
  `{844: 7.5, 845: 7.5, 846: 8.5, 848: 8.5, 850: 8.0, 852: 7.5, 853: 8.0, 856: 7.5, 858: 8.0, 859: 7.5}`.

**Export bundle regenerated** (`python3 catalog_export.py`): `catalog/export/manifest.json` now lists all **10**
kept tours, and `catalog/export/<id>.zip` was written for each with byte length equal to the stored DB ZIP.
`catalog/export/` is **gitignored** — the audio ZIPs and manifest stay on disk and are **not committed**.

## Listen-check (kept tours)

844 → 5 MP3 / 11.9 min; 850 → 5 MP3 / 12.4 min; 852 → 5 MP3 / 10.2 min (stop 2 short at 63 s, matches its thin
content); 853 → 5 MP3 / 10.5 min. One MP3 per stop, all readable by ffprobe; exported ZIP bytes == DB
`octet_length` for every kept tour.

## Notes

- The spec lists **844** among the 11 re-made ids; it is included and kept here. (An earlier task-tracker note
  omitted it — the spec was followed.)
- No writes to the source DB. No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
  SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, GCLOUD_STORIED_START_HERE.md, or TRAVEL_PROJECTS.md.
- Commit stages only the two changed files (no `git add -A`); ZIPs and manifest are not committed.
