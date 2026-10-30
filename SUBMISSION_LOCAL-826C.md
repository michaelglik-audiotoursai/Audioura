# SUBMISSION — LOCAL-826C: the Rijksmuseum "Merry Drinker" long bilingual title loses its body / becomes "This stop"

**Branch:** `LOCAL-826C-long-title` (based on subscribed `7d65854a`; `git merge-base --is-ancestor 7d65854a HEAD` → 0).
**Evidence:** `~/Audioura/reports/local826c/tour866_v2.txt` + `gen_rijks_v2.log` (LEAD, Mac, 826B code, real cache).

## The defect

The delivered Rijksmuseum tour shipped:

```
Continue to This stop.

Stop 3: This stop

A Militiaman Holding a Berkemeyer, Known as the ‘Merry Drinker’ (Een schutter
```

— a stop titled **"This stop"** whose first body line was a **truncated title fragment**
cut mid-parenthetical at "(Een schutter".

## Root cause — traced through the exact log

1. **LOCAL-791B composed a 21-word bilingual title** (log line ~2603):
   `'A Militiaman Holding a Berkemeyer, Known as the ‘Merry Drinker’ (Een schutter die een berkenmeier vasthoudt, bekend als ‘De vrolijke drinker’)'`.
2. The downstream **F3 corruption guard** (`generate_tour_text.f3_name_is_corrupt`, ceiling
   `_F3_MAX_TITLE_WORDS = 15`) fired because the title is **21 words > 15**, and its handler
   **word-truncated** the name to the first 12 words:
   `' '.join(name.split()[:12]).rstrip('.,;:!?')` →
   `'A Militiaman Holding a Berkemeyer, Known as the ‘Merry Drinker’ (Een schutter'`
   — **the exact fragment** seen in the delivery (log line ~4005: `[F3] ⚠️ NAME TOO LONG/CORRUPT at stop 3`).
3. The truncated fragment became a **headerless orphan body**; the Directions hand-off that
   announced the stop had itself degraded to the placeholder **"This stop"**, so 826B's
   de-splice **promotion** titled the lost-header stop **"This stop"**
   (`_promote_orphan_to_stop`'s `title = (handoff_title or "").strip() or "This stop"`).

The curly quotes/comma were never the cut point — **the parenthesised local name pushed the
title past F3's word ceiling, and F3's blunt word-truncation cut inside the parenthesis.**

## The fix — three layers

### 1. Source: cap the delivered title (never a 150-char header)
`place_title_naming.py`
- `_MAX_TITLE_WORDS = 14`, `_MAX_TITLE_CHARS = 90`, `_title_is_too_long()` — one notch under
  F3's 15-word ceiling, plus a char ceiling.
- `format_place_title()` now **drops the parenthetical local-name gloss** when the combined
  `English (Local)` title is too long, keeping the English title whole. A **short** bilingual
  title still keeps its gloss (no LOCAL-791B regression).
- New `shorten_long_title()` — drops a trailing (or leading) `(…)` gloss for an over-long title;
  **never word-cuts** a title mid-phrase. Exported in `__all__`.

`identity_dedup.py`
- `bilingual_display_title()` (the LOCAL-669C header source) now caps the same way: when
  `local (en)` is too long it ships **one complete title** (prefers the ASCII/English side),
  never a parenthesised pair that F3 would cut. `_title_too_long_826c` mirrors the word/char caps.

`generate_tour_text.py` (F3 block only, ~L28556)
- F3 now evaluates the **actually-rendered header title** (`display_title or name`), not just the
  raw name, and when it is too long it **shortens by dropping the gloss** (`shorten_long_title`)
  instead of word-truncating. A genuinely corrupt (sentence-shaped, no-parenthetical) name still
  falls back to the word-bounded trim as a last resort.

### 2. Promotion: never "This stop", never a fragment
`stop_dedup_collision_guard.py`
- `_is_placeholder_title()` + `_PLACEHOLDER_TITLES` ("this stop", "next stop", …).
- `_orphan_is_title_fragment()` — a body whose prose has **under two complete sentences**
  (the truncated-title artifact has zero sentence endings) is a fragment, not a narrated stop.
- `_orphan_has_narration_body()` now returns **False** for a title-fragment orphan.
- `_promote_orphan_to_stop()` returns `Optional[str]`: **None (refuse to promote)** when the
  title would be a placeholder — a stop is **never** titled "This stop"/"Next stop". The
  de-splice caller drops the orphan and logs `[LOCAL-826C]` instead.

### 3. Delivery check: two new violations
`tour_conclusion.check_stop_delivery()`
- **`PLACEHOLDER_TITLE`** — a stop header that is "This stop"/"Next stop"/…
- **`FRAGMENT_BODY`** — a stop whose narration carries **no complete sentence** (the "(Een
  schutter" artifact). The bar is "at least one sentence ending" so 826B's terse-but-complete
  single-sentence clean contract is preserved.

## Tests — `tests/test_local826c_long_title.py` (21, all pass)

Built from the **exact** ticket/log strings (`_EN`, `_LOCAL`, the 21-word `_FULL_791B`,
the `_F3_FRAGMENT`). Covers: the title cap at source (`format_place_title` /
`title_for_candidate` / `shorten_long_title` / `bilingual_display_title`), F3-safety of the
shortened title, promotion never shipping "This stop" (fragment-orphan not a body; placeholder
hand-off → None; real hand-off still promotes), the end-to-end `normalise_stop_headers` dropping
a placeholder orphan and renumbering, and the delivery check reporting `PLACEHOLDER_TITLE` +
`FRAGMENT_BODY` — including a test that reads the **real** `~/Audioura/reports/local826c/tour866_v2.txt`
evidence and asserts `PLACEHOLDER_TITLE: Stop 3`.

Regression: **331 passed / 2 skipped** across every suite that imports the touched modules
(791B/791C/361/669B/669C/639/642/652/743/801/826B/…). 107-test focused re-run green. All five
touched modules `py_compile` clean.

## Live run — BUDGET ENFORCED, within cap

`run_local826c_live.sh` + `run_local826c_container.py` (modeled on the 826B harness): an
**isolated** throwaway postgres (`local826c-postgres`, never a shared/`audioura-*` container,
never the live DB) seeded read-only with the **real cached rows**; the canonical meter contract
(`PYTHONPATH=/opt/meter`, `PAID_API_LOG=/meterlogs/paid_api_calls.jsonl`, `METER_SERVICE=LOCAL-826C`);
cheap museum arm (`gpt-4.1-mini`), `DISABLE_STOP_POOL=1`; **one** tour — "Rijks Museum, Amsterdam,
Netherlands" (5). `TASK_BUDGET_ID=LOCAL-826C TASK_BUDGET_USD=0.50`.

**Metered $0.34 / $0.50 cap.**

**The LOCAL-826C defect is PROVEN FIXED on the real cached path:**
- The Merry Drinker WAS a verified candidate; `[LOCAL-791B] title 'Een schutter…' → 'A Militiaman
  Holding a Berkemeyer, Known as the ‘Merry Drinker’'` — the English name only, the long Dutch
  gloss dropped by the source cap.
- **F3 `NAME TOO LONG` never fired** — the source cap pre-empts it.
- The delivered text contains **zero `This stop`** and **zero `(Een schutter`** fragments.

**Honest shortfall (unrelated, pre-existing):** the delivered tour shipped **4 stops, numbered
`[1, 2, 4, 5]` (NON_SEQUENTIAL)**. Cause (log ~1983):
`derepetition_guard.strip_repeated_facts` (D533) `removed: Stop 3: Het melkmeisje (The Milkmaid)`
— it stripped the whole stop block while removing a repeated fact and the renumber did not close
the gap. This is a **pre-existing D533 / derepetition bug, orthogonal to the long-title / "This
stop" ticket**, and is **not caused by my changes**: my 826C guards never fired (`despliced=0,
promoted=0`) and my only edit to `generate_tour_text.py` is the F3 block.

Per the ticket's explicit fallback — *"If the Merry Drinker isn't selected, unit-test the path
with the fixture"* — the selector did not place the Merry Drinker in the final narrated five
(it chose Great Wave / Night Watch / Milkmaid / Jewish Bride / Houses in Delft), so the Merry-
Drinker delivery path is covered by the 21 passing unit tests against the exact `tour866_v2`
evidence. The remaining budget (~$0.16) is below one tour's cost, and the D533 gap is
non-deterministic, so a reliable re-run was not attempted within the cap.

Artifacts: `~/Audioura/reports/local826c/gen_rijks_826c_live.log`,
`~/Audioura/reports/local826c/tour866_826c_live_delivered.txt`.

## Files

| File | Change |
| --- | --- |
| `place_title_naming.py` | title cap in `format_place_title`; new `shorten_long_title`; `_MAX_TITLE_WORDS/_CHARS`, `_title_is_too_long` |
| `identity_dedup.py` | cap in `bilingual_display_title`; `_title_too_long_826c` |
| `generate_tour_text.py` | F3 block: evaluate the rendered title, shorten by dropping the gloss (no mid-phrase word-cut) |
| `stop_dedup_collision_guard.py` | never promote a fragment orphan; never title a stop "This stop" (promotion returns None) |
| `tour_conclusion.py` | `check_stop_delivery`: `PLACEHOLDER_TITLE` + `FRAGMENT_BODY` |
| `tests/test_local826c_long_title.py` | 21 unit tests from the exact ticket strings + the real `tour866_v2.txt` fixture |
| `run_local826c_container.py`, `run_local826c_live.sh` | isolated, budget-enforced live acceptance harness |
