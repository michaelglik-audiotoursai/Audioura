# SUBMISSION — LOCAL-641: Fresh tours put Stop 2's orientation into Stop 1

**Branch:** `LOCAL-641-fresh-equals-reuse` (from `subscribed` @ `44f15c6`)
**Agent:** Mac Mini Kiro

## TL;DR

A **fresh** delivery opened **Stop 1 with Stop 2's orientation** while Stop 2 lost
its own; the **same stops reused** opened each stop with its own orientation
(fresh Kiro 4 vs reuse 8–8.5). The exact shift point is
`stop_pool_orchestrator._overall_from_new`: it scanned the **whole** gen_text for
the first `Orientation:` label and returned it as Stop 1's overall seed. When
Stop 1's own orientation was folded into opening prose (no `Orientation:` label of
its own), that first match belonged to **Stop 2**. The reuse path passes
`overall_orientation=None` and never did this — which is exactly why reuse was
correct and fresh was not.

**Fix (root cause):** scope `_overall_from_new` to the **Stop-1 block only** (the
text before the Stop-2 header). If Stop 1 has no own `Orientation:` label, it
returns `None`, so **no later stop's orientation is ever hoisted onto Stop 1** —
making a fresh delivery behave like a reuse delivery.

**Live Courtauld fresh (id 545):** each stop now opens with ITS OWN orientation;
the old Seurat "tapestry of discrete points / pointillist" line on Van Gogh is
GONE and Stop 2 (Seurat) keeps its own orientation. The LOCAL-641 defect does not
appear in `critique.sh` or `detectors.py`.

---

## 1. The exact shift point (gen_text → parsed units → assembled text)

The fresh path (`stop_pool_orchestrator`, K==0 and K>0 branches) runs:

```
gen_text  ──parse_delivered_stops──▶ units (each unit's orientation recovered
          │                           from its own raw_block — CORRECT)
          └──_overall_from_new──────▶ overall_orientation  ◀── THE BUG
                                      assemble_building_tour injects it as
                                      Stop-1's orientation seed (s0['orientation']
                                      = overall + base)
```

`parse_delivered_stops` and `assemble_building_tour` are **not** the shift point:
with each stop's `Orientation:` at the top of its block, both fresh and reuse
assemble correctly (verified in the fixture test). The shift is entirely in
`_overall_from_new`:

```python
# BEFORE (buggy): searches the WHOLE text; first Orientation: match wins.
m = re.search(r'^Orientation:\s*(.+?)(?:\n\n|\Z)', new_text or "", re.M | re.S)
```

When Stop 1's orientation is folded into opening prose (the museum opening
section — About + hours — carries Stop 1's "where to stand", so Stop 1 has **no
`Orientation:` label of its own**), the first `Orientation:` label in the text is
**Stop 2's**. That Stop-2 orientation is injected onto Stop 1. The LOCAL-630
item-4 renamer then rewrote the foreign title (Seurat → Van Gogh), masking it;
cross-stop fact dedupe then dropped the now-duplicated orientation from Stop 2,
leaving Stop 2 with none.

### Evidence (R10 bench texts)

`tour_485_R10_fresh.txt` (FRESH, Kiro 4):
> Stop 1: *Van Gogh's iconic Self-Portrait with Bandaged Ear*
> Orientation: "To best appreciate **Van Gogh's iconic Self-Portrait with Bandaged
> Ear**'s work … stand close enough that the surface becomes a **tapestry of
> discrete points** … **Seurat's pointillist technique**" ← this is **Stop 2
> (Seurat)'s** orientation, renamed.
> Stop 2 (Seurat) and Stop 3 (Manet): **no Orientation**.

`tour_485_g1.txt` / `tour_485_g2.txt` (REUSE, Kiro 8 / 8.5):
> Stop 2: *Georges Seurat* — Orientation: "To best appreciate **Georges Seurat**'s
> work … tapestry of discrete points … Seurat's pointillist technique" ← its OWN.
> Stop 3: *Manet* — Orientation: "… directly in front of **Manet's A Bar at the
> Folies-Bergère** …" ← its OWN.

Reproduced deterministically (Stop 1 unlabelled, Stops 2/3 labelled):
`_overall_from_new` returned Stop 2's "tapestry of discrete points … pointillist"
orientation and the assembly put it on Stop 1.

---

## 2. The fix — a fresh delivery == a reuse delivery of the same stops

`stop_pool_orchestrator.py` — `_overall_from_new` is now scoped to the Stop-1
block:

```python
headers = list(re.finditer(r'^Stop (\d+):\s*.+?\s*$', text, re.M))
if headers:
    stop1_start = headers[0].end()
    stop1_end   = headers[1].start() if len(headers) > 1 else len(text)
    search_region = text[stop1_start:stop1_end]   # Stop-1 block ONLY
else:
    search_region = text                           # legacy no-header fallback
m = re.search(r'^Orientation:\s*(.+?)(?:\n\n|\Z)', search_region, re.M | re.S)
return m.group(1).strip() if m else None
```

Behaviour (verified):

| gen_text shape                           | returns                       |
|------------------------------------------|-------------------------------|
| Stop 1 has its own `Orientation:`        | Stop 1's own orientation      |
| Stop 1 unlabelled, Stop 2 labelled       | **None** (no forward pull)    |
| single stop                              | its own                       |
| no `Stop N:` header at all (legacy)      | whole-text fallback           |

Because the reuse path already passes `overall_orientation=None`, and the fresh
path now returns `None` whenever Stop 1 has no own label, **fresh and reuse now
assemble identically** — each stop keeps its own orientation; no later orientation
is hoisted onto Stop 1. The fixture test asserts fresh == reuse per-stop.

---

## 3. `_fix_orient_work` neutralised to a logging detector

`tour_conclusion.fix_orientation_work_mismatch` (LOCAL-630 item 4) **no longer
renames** a foreign work-title. It now detects the mismatch, logs
`[LOCAL-641] orientation mismatch: Stop N (<own>) Orientation names foreign stop
work <foreign> …`, and returns the text **unchanged**. The rename hid the real
defect (and would corrupt a legitimately comparative orientation). Callers
(`generate_tour_text.py`) still receive a `str`, now unmodified.

Verified: logs on a mismatch and leaves text byte-for-byte unchanged; silent no-op
when every orientation names its own work.

---

## 4. Tests — exit codes

New: `tests/test_local641_fresh_equals_reuse.py` (6 tests). Drives the **real**
`parse_delivered_stops` + `_new_unit_from_parsed` + `_overall_from_new` +
`assemble_building_tour` (no DB/network/LLM) on a Courtauld-shaped gen_text where
Stop 1's orientation is folded into opening prose. Asserts (1) `_overall_from_new`
never returns a later stop's orientation; (2) every assembled stop names its own
work and no foreign stop's, none lost; (3) fresh == reuse per-stop.
**Non-vacuous:** 4/6 fail against the pre-fix `_overall_from_new`.

Also updated `test_local630_venue_truth.py::TestItem4OrientationOwnWork` for the
new detector contract (text unchanged + `[LOCAL-641]` logged; silent no-op on a
clean tour; idempotent).

Required suites (all exit 0):

```
[1] test_local60*/61*/62*                      296 passed            EXIT=0
[2] test_local63*                              174 passed, 1 skipped EXIT=0
[3] tests/test_local63*                         16 passed            EXIT=0
[4] tests/test_lead_*                            8 passed            EXIT=0
[5] test_local590_*                             42 passed            EXIT=0
[6] tests/test_local641_fresh_equals_reuse       6 passed            EXIT=0
[7] python3 test_sq4_merge.py                  ALL TESTS PASSED      EXIT=0
```

---

## 5. Live run (own container, cache + pool OFF — fresh)

Own disposable container `local641-gen` (`docker run --rm`, image
`local641-gen-img`, spare port 5098, network `development_default`,
`DISABLE_TOUR_CACHE=1 DISABLE_STOP_POOL=1`). **Never** `docker compose -p
audioura`; never renamed/replaced an `audioura-*` container (13 still running).
Combined hard cap **$1.30** via `tests/live_run_meter.py` with the reserve gate.
Container + image removed by the cleanup trap.

### Courtauld fresh — `audio_tours` id 545 (is_test=true) — the R10 defect venue

Per-stop orientation **AS DELIVERED** (the fix in production):

- **Stop 1 — Van Gogh's iconic Self-Portrait with Bandaged Ear**
  `Orientation: You are about to explore The Courtauld Gallery … showcasing Van
  Gogh's iconic Self-Portrait with Bandaged Ear, Georges Seurat's groundbreaking
  works, and Manet's captivating A Bar at the Folies-Bergère. **Your first stop is
  Van Gogh's iconic Self-Portrait with Bandaged Ear.** As you stand before [it] …
  position yourself to directly face the canvas.`
  → names its OWN work; the old Seurat "tapestry of discrete points / pointillist"
  orientation is **gone**.
- **Stop 2 — Georges Seurat**
  `Orientation: Stand before Georges Seurat's "Young Woman Powdering Herself" …
  This intimate portrayal reveals **Seurat's mastery of pointillism** …`
  → its OWN orientation, **no longer lost**.
- **Stop 3 — Manet's A Bar at the Folies-Bergère**
  Opens on the Manet painting (its own body opener).

**`[LOCAL-641] orientation mismatch` log count = 0** — nothing to detect, because
no later orientation was hoisted onto Stop 1. Consistent with the fix.

**detectors.py 545 3 courtauld** → 1 failure: `recall_unseen_work` on Stop 2's
"echoing … Van Gogh's 'Self-Portrait with Bandaged Ear' … which you encountered
earlier". Van Gogh **is** Stop 1 (encountered earlier), so this is a valid
continuity link, not an unseen-work defect (critique rates it Low/acceptable). It
is **not** an orientation-shift defect.

**critique.sh 545** → **Kiro 5.5/10**. The critique calls the stops "three
genuinely substantial, art-first stops" and the **orientation shift is not in the
defects table**. The 5.5 is from defects **orthogonal to LOCAL-641**:

| Stop | Defect | Owner (not this ticket) |
|---|---|---|
| 1 | Mangled admission: "Admission is 9.\n\n00 pounds" (currency split across a paragraph break) + a duplicate `Museum Information: … £16` field line + £16 vs £9 price conflict | practical-facts/hours composer (LEAD D640 / LOCAL-629/633/638) |
| 3 | Mid-sentence truncation: "our place within To grab the audience's attention" | segment-stitching integrity |
| 2 | Dangling provenance pronoun: "Six years later, in 1932, he … gift it" (no named donor) | provenance antecedent guard |

These are pre-existing and untouched by this change (the diff only touches
`_overall_from_new` and the detector). The **Kiro ≥ 7.5 target is blocked by these
orthogonal defects, not by the LOCAL-641 orientation shift, which is resolved.**

Cost: `tour_total $0.7503` (openai $0.6008, gemini_grounding $0.0700,
gemini_tokens $0.0355, serper $0.0440, preflight $0.0166). Host spend after:
**$0.8052**.

### National Gallery — gated by the cap (reserve gate honoured)

The reserve gate **correctly SKIPPED** the National Gallery:
`spend_so_far $0.8052 + reserve $0.80 > cap $1.30`. A second full tour would have
breached the $1.30 combined cap, so it was not run. The National Gallery R4 class
("Stop 1's Orientation describes Stop 2's painting") is the **same mechanism** and
is covered by the deterministic `GEN_STOP1_UNLABELLED` fixture in the new test,
which fails pre-fix and passes post-fix.

### Rows (additive is_test only)

```
audio_tours total:   350 → 351  (+1)
audio_tours is_test: 287 → 288  (+1)   # exactly one additive row, id=545
```

No DELETE. No GCloud.

---

## Files changed

```
stop_pool_orchestrator.py                 | 36 +-   # root-cause fix: _overall_from_new scoped to Stop-1 block
tour_conclusion.py                        | 63 +-   # fix_orientation_work_mismatch → logging-only detector
tests/test_local641_fresh_equals_reuse.py | +254   # new fresh-path fixture test (non-vacuous)
test_local630_venue_truth.py              | 32 +-   # LOCAL-630 item-4 test updated for detector contract
run_local641_container.py                 | +220   # isolated live harness
run_local641_live.sh                      | +73     # isolated live harness
```

## Commits

```
747adb6 LOCAL-641: fix fresh==reuse orientation shift at root cause
91f781d LOCAL-641: fresh-path fixture test — each stop's orientation names its own work, fresh==reuse
7e05390 LOCAL-641: update LOCAL-630 item-4 test for detector contract
c4c56df LOCAL-641: isolated live harness (Courtauld + National Gallery, 3 stops, fresh)
```
