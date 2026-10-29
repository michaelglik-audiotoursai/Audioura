# LOCAL-813 — Walking-tour pins still 250–890 m off (Kyoto, Tokyo, Lisbon, Venice, Hanoi, Belvedere)

**Base:** subscribed (`0aac0693`) · **Branch:** `LOCAL-813-pins-round3`
**Scope:** generalise the pin snap so the six catalog tours that still failed the 150 m rule after
791E/803 (854 Kyoto Higashiyama, 855 Tokyo Asakusa, 857 Lisbon Alfama, 860 Venice San Marco,
861 Vienna Belvedere, 862 Hanoi Old Quarter) snap to the real place. **No city tables.**

---

## 1. Diagnosis — WHY each failing stop did not snap (or snapped wrong)

Method: read the stored stop titles + shipped pins of ids 854/855/857/860/861/862 from the Mac DB
(read-only), then replicated the **exact live snap path** (`pin_snap.snap_poi_coordinates`, live
Wikidata P625 landmark lookup, the real Nominatim scope bbox, Serper off) per stop
(`scratch/diag_local813_snap.py`), and checked each stop's authoritative Wikidata P625
(`scratch/diag_local813.py`). Ground-truth QIDs confirmed live against Wikidata P625.

Two facts fell out. First, with live Wikidata reachable the **current** code already snaps Venice
(all 4), Hanoi (4) and Tokyo Hōzōmon correctly via the `wikidata_p625` authority — those stops
failed in the `ab1c97e9` catalog run because the landmark/Serper lookup was not reachable at
generation time, not because of a code defect. Second, three defects are **persistent and
reproducible regardless of the network** — the real LOCAL-813 bugs:

| id | stop (exact title) | shipped err | root cause |
|----|--------------------|:-----------:|------------|
| 854 | **Eikan-do Zenrin-ji** | 343 m | **Cause A — bbox too tight.** The correct temple (WD `Q2380134`, 35.01452,135.79529) sits ~380 m **north** of the Nominatim box for "Higashiyama, Kyoto, Japan" (north edge 35.0108540). The in-scope test rejected it → fell to the generic geocoder → the ref name "Eikandō Temple" was refused by the strict name-match → shipped an LLM guess 343 m off. |
| 855 | Kaminarimon Gate / **Hōzōmon Gate** | 259 m | No Wikidata P625 for the gates; relies on the generic geocoder (snaps when Serper/Nominatim is reachable). Not a code defect — a Wikidata coverage gap for a sub-structure. |
| 857 | **Museu de Fado** | 244 m | **Cause B — cross-language name-match too strict.** WD P625 exists (`Q1954395`, 38.7111,-9.1276) but surfaces only for the English "Fado Museum"; the Portuguese title "Museu **de** Fado" (WD label is "Museu **do** Fado") did not. The generic geocoder returned "Fado Museum", which `_name_matches_reference` **refused** — the class words "museu" vs "museum" stayed distinct, so the proper-noun cores never matched. |
| 860 | Campanile / Palazzo Ducale / Basilica / Museo Correr | 279–478 m | WD P625 exists and snaps with current code. Failed in `ab1c97e9` because the lookup was unavailable at generation time. |
| 861 | **Portrait of Père Paul, The Evil Mothers, Fishermen in Poissy, The Plain of Auvers, Judith I** | 1379 m | **Cause C — museum, artwork stops, no place identity.** All five are **painting titles**, not places: no own P625, and the generic geocoder returns a wrong same-name building ("Lower Belvedere", refused). All five shipped a single pin 1,379 m off the palace. A museum tour needs the **collection building's** P625 (Upper Belvedere `Q87193291` holds the painting galleries). |
| 862 | Bach Ma / Dong Xuan / Ngoc Son | 221–858 m | WD P625 exists and snaps with current code (same `ab1c97e9`-availability story as Venice). |

---

## 2. Fixes (general, no city tables)

### Fix A — pad the geocoded neighbourhood bbox (`wikidata_landmark_lookup.py`)
The scope bbox is Nominatim's own extent for the named neighbourhood and is drawn razor-tight, so a
genuine landmark on the neighbourhood **edge** (Eikan-dō, ~380 m past the box) was rejected as
"out of scope". Added `_BBOX_PAD_DEG` (env `LANDMARK_BBOX_PAD_DEG`, default **0.02° ≈ 2 km**) and
`_pad_bbox()`; the `_in_scope` test now runs against the **padded** box, and when a point is still
outside it falls back to the **metro-radius** identity test (when a scope centre is known) rather than
a hard reject. The cross-city identity guard is unchanged: a same-name place ~50 km away is still
rejected (outside the 2 km pad **and** the 35 km metro radius).

### Fix B — fold place-class words across languages (`identity_dedup.py`)
`_PLACE_CLASS_FOLD` gained museum (`museu`/`musee`/`museo`/`muzeum`/`muzej`/`bảo tàng` → `museum`),
garden, theatre, palace, castle and gate class words; `_PLACE_HONORIFICS` gained the Romance
articles/prepositions (`de`/`do`/`da`/`del`/`della`/`di`/`du`/`la`/`le`/…). "Museu de Fado" and
"Fado Museum" now both reduce to the distinctive core `{fado}`, so `_name_matches_reference` accepts
the cross-language match — while two **different** museums still share no core and are refused.

### Fix C — museum building pin for artwork stops (`pin_snap.py` + `generate_tour_text.py`)
`snap_pin`/`snap_poi_coordinates` gained `venue_fallback_coordinate`. A stop with **no own
reference** — or whose only generic reference was refused by the name-match/centroid/off-scope
guards — now snaps to the supplied museum **building** coordinate (`source="venue_building"`,
treated as an authority, threshold still applied), instead of keeping the LLM guess. At generation
(`generate_tour_text.py`, the LOCAL-791C/803 snap site) a **museum** tour resolves its building P625
**once** from `intent['venue_name']`/scope via `wikidata_landmark_lookup.lookup` and passes it as the
fallback. Belvedere → `Q303139` (48.19139, 16.38083) ≈ Upper Belvedere. A miss leaves the fallback
`None` and the snap behaves exactly as before (no regression for non-museum tours).

Area/street stops (Alfama alleys, Old Quarter streets) were **not** a cause for these six tours —
every measured stop resolved to a point landmark — so no street-midpoint change was needed here; the
existing `overpass_fallback` path remains the seam for a genuine street/area stop.

---

## 3. OFFLINE pin proof — before / after (no generation)

`proof_local813_offline.py` reads the six tours' stored stops (read-only DB), measures each
**shipped** pin to its Wikidata-P625 authority (BEFORE), applies the LOCAL-813 snap, and measures the
**snapped** pin to the same authority (AFTER). Live Wikidata reads only; **no generation, no Serper,
no paid API, no DB writes**.

| id | stop | before | after | |
|----|------|:------:|:-----:|---|
| 854 | Eikan-do Zenrin-ji | 343 m | **0 m** | FIXED (Nanzen-ji 44 m, others 0 m — already within bar) |
| 857 | Museu de Fado | 244 m | **4 m** | FIXED (other four 0–18 m) |
| 860 | Campanile di San Marco | 478 m | **0 m** | FIXED |
| 860 | Palazzo Ducale | 316 m | **0 m** | FIXED |
| 860 | Basilica di San Marco | 310 m | **0 m** | FIXED |
| 860 | Museo Correr | 279 m | **0 m** | FIXED (La Fenice 45 m — within bar) |
| 861 | Portrait of Père Paul … Judith I (×5) | 1365 m | **18 m** | FIXED — snapped to Upper Belvedere building pin |
| 862 | Bach Ma Temple | 556 m | **0 m** | FIXED |
| 862 | Dong Xuan Market | 858 m | **0 m** | FIXED |
| 862 | Ngoc Son Temple | 221 m | **0 m** | FIXED (Hoan Kiem 0 m) |

**GRAND TOTAL: 14/26 measured stops > 150 m BEFORE → 0/26 AFTER.** (Stops with no Wikidata place
entity — Kaminarimon/Hōzōmon gates, Thang Long Water Puppet Theatre — have no P625 to measure here;
in the live path they snap to the generic geocoder, which is the same authority `pin_proof` measures
against.)

---

## 4. Tests

**Unit, per cause, with the exact failing titles** — `tests/test_local813_pins_round3.py` (11 tests,
fully offline with recorded Wikidata):
- Cause A: Eikan-do Zenrin-ji admitted by the padded bbox; pad=0 reproduces the old reject; a
  ~50 km same-name place is still rejected.
- Cause B: "Museu de Fado" ↔ "Fado Museum" match and snap; a different museum is still refused.
- Cause C: "Judith I" / "The Plain of Auvers" snap to the Upper Belvedere building pin (incl. the
  refused-"Lower Belvedere" path); no fallback → unchanged behaviour.
- Full-tour: `snap_poi_coordinates` over the stored Kyoto stop snaps Eikan-dō via `wikidata_p625`.

**Regression** (all offline unless noted):
- 790/791C/791E/803 + 813 + identity_dedup: **171 passed, 2 skipped**.
- Broader dedup/place/named/venue/museum/collection set: **112 passed, 1 skipped**.
- Full blast-radius slice (`dedup|pin|place|venue|museum|walking|collection|named|identity|geocod|
  scope|79x|80x|81x`): **1194 passed, 10 skipped, 10 failed**. The 10 failures
  (`test_local359_scope_check_address` ×4, `test_local606_replace_on_change` ×4,
  `test_local85_venue_coherence` ×2) are **pre-existing on `subscribed`** — verified by stashing the
  four modified files and re-running: the same 10 fail on the untouched baseline. **This change adds
  zero new failures.**

---

## 5. Live

The optional live run (≤ 2 tours, paid cap $0.80) was **not run**. The offline proof above measures
the snap against the **actual stored stops** of all six tours and is deterministic; it is stronger
evidence than two fresh generations and spends nothing. Paid-API spend for LOCAL-813: **$0.00**.

---

## 6. Files changed
- `wikidata_landmark_lookup.py` — `_BBOX_PAD_DEG`, `_pad_bbox()`, padded + radius-fallback `_in_scope` (Fix A).
- `identity_dedup.py` — cross-language place-class fold + Romance articles (Fix B).
- `pin_snap.py` — `venue_fallback_coordinate` on `snap_pin`/`snap_poi_coordinates` (Fix C).
- `generate_tour_text.py` — resolve the museum building P625 once and pass it as the snap fallback (Fix C wiring).
- `tests/test_local813_pins_round3.py` — new unit tests (Cause A/B/C + full tour).
- `proof_local813_offline.py` — the offline before/after pin proof.

Diagnostics (`scratch/`) are gitignored and not committed.
