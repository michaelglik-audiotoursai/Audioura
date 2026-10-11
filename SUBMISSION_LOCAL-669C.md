# SUBMISSION — LOCAL-669C

**The SAME painting still shipped twice (both arms): identity dedup must run on
the FINAL stop list, on every path; bilingual stop titles.**

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-669C-final-identity-gate` (from `subscribed` @ `09ca36b2`)
**Base ancestry:** `git merge-base --is-ancestor 09ca36b2 HEAD` → exit 0 ✓

---

## TL;DR

A single **final identity gate** now runs once, right before narration, on
**every** museum path. It stamps a Wikidata QID onto each stop by EXACT label
match (from the venue's QID→labels map and the D1v2 evidence log), collapses
same-work stops by identity, and refills any freed slot from the verified
reserve (works first, area stops last, never repeating). The grounded-highlights
call is now triggered by **count** (documented works < requested stops),
regardless of tier, and logs its decision either way. Surviving stops get one
**bilingual header** — `<local> (<English>)`, local first.

20 new tests + the full regression set pass. The live run **reproduced the bug
on the first attempt** and then confirmed the fix path offline; a second live
attempt was hard-blocked by OpenAI billing (`credit_balance_exhausted`), not by
any code fault. Task spend: **$0.6347** of the **$1.80** cap.

---

## 1. Diagnosis (both logs, confirmed)

`~/Audioura/.continuous_dev/bench/AB13/hcmc_off_670.log` (normal) and
`hcmc_on_671.log` (cheap).

- **Tour 670 (normal):** the stop list carried BOTH
  `North Central South Spring Garden` (the SPARQL English label, Q109406846) AND
  `Vườn xuân Trung Nam Bắc` (the grounded-highlights Vietnamese) — the SAME work
  twice. Contrary to the ticket's note, the log **does** contain `[LOCAL-669]`
  lines (highlights ran) — the real failure was downstream:
  - LOCAL-669B's identity-dedup pass **ran but collapsed nothing**. The
    highlights stop carried **no QID**, and its English GLOSS was
    *"Spring Garden of the **Center**, South, and North"* (US spelling) while the
    SPARQL English label said *"**Central**"*. The order-ignored token sets
    therefore differed by one word, and the D1v2 bilingual map did not bridge the
    Vietnamese to the English either. So neither the QID path nor the title path
    fired.
  - The dedup pass also lived **inside the thin-selection branch** — the
    exhibition/checklist museum path and any area-stop step that appends *after*
    it never reached it at all.
- **Tour 671 (cheap):** `North Central South Spring Garden` +
  `Central South and North Spring Garden` (pure word-order) + 3 area stops — the
  same single-work-twice defect, this time within English.

Root cause, in one line: **the collapse was not a final choke point, and its
identity rule had no reliable cross-language bridge when a QID was missing.**

## 2. The fix

### 2a. A reusable final identity gate — `identity_dedup.final_identity_gate()`
Pure function, no network, no LLM. Three steps:
1. **Stamp QIDs by EXACT label.** Build a normalised `label → QID` index from the
   venue's QID→labels map **and** the D1v2 evidence log's `sparql_labels`. A stop
   whose name/local/English title exactly matches a known label is that work —
   stamp its QID. The highlights stop is literally named Q109406846's
   `label_local` (`Vườn xuân Trung Nam Bắc`), so it collapses by QID **regardless
   of the Center/Central gloss** — the bridge the token sets could not make.
2. **Dedup by identity** (`dedup_by_identity`: QID, else order-ignored bilingual
   title set + the D1v2 word map), keeping the best-sourced survivor. A QID
   conflict (two different QIDs) is never merged.
3. **Refill** each freed slot from a verified reserve — works first, area/building
   stops last — skipping anything already present by identity. Never repeats.

### 2b. Single choke point, every path
The gate is called once in `_generate_tour_text_impl`, right before PHASE 3B stop
numbering (`generate_tour_text.py`), after every selection / verification /
fallback / area-stop step — so it covers fresh, pool, cache, thin, highlights,
and the exhibition/checklist branch alike. The old in-branch 669B pass is
superseded by this one.

### 2c. Robust bridge (found and fixed during the live run)
The first live run **reproduced the twin Spring Gardens** and showed the gate
logging *"no duplicates"* because the English stop's **per-stop evidence entry
carried an empty `qid`/`sparql_labels`** — the exact-label stamp had nothing to
key on. Fix: `VerificationResult` now carries the whole venue
`qid_to_labels` map (QID → {label_local, label_en, aliases}), captured into
`_d1v2_qid_to_labels` and passed to the gate. Both surface forms are now stamped
Q109406846 by exact label and collapse by QID even when the per-stop evidence is
empty. A test pins this exact case.

### 2d. Highlights trigger by count (ticket point 2)
`generate_tour_text.py`: the grounded highlights call now runs whenever
`documented works < requested stops` **regardless of verification tier** (was
gated on `tier == 'thin'`). The decision is logged either way:
`[LOCAL-669C] highlights trigger: documented works N < requested M …` /
`… skipped — documented works N >= requested M` / `… skipped — no story corpus`.

### 2e. Bilingual stop titles (ticket point 3)
`identity_dedup.bilingual_display_title()` builds `<local> (<English>)`, local
first, English in parentheses, sourced from the stop's own local/English pair
(highlights) or the work's SPARQL labels by QID. The gate attaches it as
`display_title`; the delivered header uses it (`Stop N: <local> (<English>)`),
with the F3 header assertion updated to match. One header per work — never two.
Mono-lingual works are left unchanged. (Base generation is English; translation
is a downstream service, so the English-tour format applies to the base.)

## 3. Files changed
- `identity_dedup.py` — `final_identity_gate`, `build_label_qid_index`,
  `stamp_qids_by_label`, `bilingual_display_title`, `_qid_labels_lookup`,
  `GateResult`.
- `generate_tour_text.py` — single gate call before PHASE 3B; `_final_gate_reserve`
  (surplus verified highlights); count-based highlights trigger + logging;
  `VerificationResult.qid_to_labels` + capture into `_d1v2_qid_to_labels`;
  bilingual `display_title` in the delivered header.
- `test_local669c_final_gate.py` — 20 tests (new).
- `run_local669c_container.py`, `run_local669c_live.sh` — live-run harness.

## 4. Tests (exit codes)
```
test_local669c_final_gate.py            20 passed   (exit 0)
test_local669b_identity_dedup.py        24 passed   (exit 0)
test_local669_grounded_highlights.py    25 passed   (exit 0)
test_local634_title_line.py              6 passed   (exit 0)
test_venue_identity.py                  16 passed   (exit 0)
tests/test_local381_title_is_not_a_description.py  29 passed (exit 0)
tests/test_local286_museum_prolog_and_dedup.py     31 passed (exit 0)
test_local628_stop_editor.py            23 passed   (exit 0)
test_local630_venue_truth.py            24 passed   (exit 0)
tests/test_local593_work_selection.py    7 passed   (exit 0)
```
The 669C suite includes: the **tour-670 fixture** (two Spring Gardens collapse by
QID stamped from the evidence log; **5 distinct works** survive after refill; no
Spring Garden twice; a duplicate reserve candidate is skipped), the **tour-671
fixture** (word-order collapse; area stops survive), the **Center/Central
QID-stamp bridge**, the **empty-per-stop-evidence** case (the live-run failure
mode) bridged by the venue QID→labels map, the **bilingual header** (local first,
one header per work, mono-lingual unchanged), and **regression** (QID conflict
never merged; refill prefers works over area stops; no-op on a clean list).

## 5. Live run (own container) — reproduced the bug; then hard-blocked by billing
Built `Dockerfile.generator` from this branch and ran HCMC, 5 stops, museum,
FRESH, in a disposable container (`docker run --rm --name local669c-gen -p 5171`,
`development_default` network, **never** `docker compose -p audioura`, never an
`audioura-*` container). NORMAL then CHEAP arm, task cap $1.80.

- **Run 1** (container host `4987fa846f8e`): reached PHASE 3B and the final gate.
  **It reproduced the bug** — both `North Central South Spring Garden` and
  `Vườn xuân Trung Nam Bắc` were in the stop list and the gate logged *"no
  duplicates"* because the per-stop evidence `qid`/`sparql_labels` were empty.
  This drove fix **2c**. All 5 narrations then failed with OpenAI **HTTP 429** →
  NO TOUR TEXT.
- **Run 2** (host `69a2f74dc31f`, with the fix): HTTP **429 at PHASE 3A intent**
  — generation never reached the gate.
- **Direct probe** of the OpenAI API: `HTTP 429`,
  `"type":"insufficient_quota"`, `"code":"credit_balance_exhausted"` — *"You have
  no credits remaining."* This is an account-billing blocker, not a code fault,
  and not something this task can resolve.

**Spend (from `paid_api_calls`, by container host):**
| host | service | calls | USD |
|---|---|---|---|
| 4987fa846f8e | run_local669c_container.py | 113 | 0.5204 |
| 69a2f74dc31f | run_local669c_container.py | 8 | 0.1143 |
| **total** | | **121** | **0.6347** |

All spend was on grounding/Serper (which succeeded); the OpenAI narration calls
were rejected at $0. **Total $0.6347 ≤ $1.80 cap.**

**Rows:** additive `is_test` only — and in fact **none** were inserted, because
both runs failed before the `_store` step (`audio_tours` `is_test` count stayed
396 before and after). No containers linger. No DELETE. No GCloud.

**What would unblock the live acceptance:** OpenAI credits on the configured key.
Once credits are present, `./run_local669c_live.sh` runs both arms and the
detectors (DELIVERED / NO_CITATION_STOP / DISTINCT_WORKS / BILINGUAL_HEADER)
assert 5 distinct works with one Spring Garden and the bilingual header.

## 6. Commits (branch, after each step)
```
5c5b0557  step 1: reusable final_identity_gate helper
a99e4191  step 2: wire final gate before narration; trigger by count; bilingual titles
517c29c2  step 3: tests for the final identity gate
4df5880b  step 4: live-run harness (own disposable container, both arms, cap $1.80)
73d533c4  step 5: carry venue QID->labels map to the gate (robust bridge)
```
Pushed to `origin/LOCAL-669C-final-identity-gate`.
