# SUBMISSION — LOCAL-823

**Cheap arm on a museum (Belvedere, Vienna): junk stop "Fußzeile", body duplicated
into the title, gpt-4o still used.**

- **Base:** subscribed (`efb9b977`) — `git merge-base --is-ancestor efb9b977 HEAD` exits 0.
- **Branch:** `LOCAL-823-cheap-museum-junk`
- **Budget:** `TASK_BUDGET_ID=LOCAL-823 TASK_BUDGET_USD=1.20` — spent **$0.6981** (meter log).

---

## The three defects (GCloud wave-5 proof tour 474, cheap museum arm)

1. **Junk stop "Fußzeile".** Stop 2 of the German-language Belvedere tour was
   titled *Fußzeile* ("page footer") — website chrome scraped as an artwork title.
2. **Body duplicated onto the title line.** Stop 1's body text was duplicated onto
   its `Stop N:` title line.
3. **gpt-4o still used.** Cost $1.03, of which **gpt-4o $0.75**, although
   `NARRATION_MODEL=gpt-4.1-mini`. Some museum step called gpt-4o directly and
   ignored the cheap arm.

---

## Root cause & fix, per defect (file:line)

### Issue #1 — site-chrome in a non-English language (`Fußzeile`)

`junk_title_guard.is_junk_page_title` (**junk_title_guard.py:447**) is the ONE
shared junk-title predicate every title path calls — `exhibition_site_first.py`
(:668, :896), `pool_museum_checks.py:288`, `stop_pool_orchestrator.py:238`,
`generate_tour_text.py:15449`, `artwork_selection_guard.py:581`,
`site_candidate_guard.py:436`. Its section/nav sets (`_SECTION_LABELS`,
`_GENERIC_WORD_TITLES`) were **English-only**, so German `Fußzeile` and every other
non-English CMS label sailed through.

**Fix:** added `_SITE_CHROME_MULTILINGUAL` (a frozenset data table of
footer/header/imprint/privacy/navigation/search/menu/legal/sitemap words in **de,
fr, it, es, nl, pt, vi** — incl. `fußzeile`/`fusszeile`) and check it as **rule 2b**
in `is_junk_page_title`, matched against the normalised whole title (`_norm()`), so
every title path is covered by the one shared place. A real work whose title merely
*contains* such a word is untouched (only an exact whole-title match is rejected).

### Issue #2 — stop title is a prefix copy of its body

The `Stop N:` title comes from `poi['name']` at the final assembly
(**generate_tour_text.py:25811**). The title is chosen before the body exists
(**generate_tour_text.py:7243**), so a body-prefix copy only arises when a later
path re-derives the title from body text.

**Fix:** NEW module **`stop_title_body_dup_guard.py`** —
`title_is_body_prefix` / `repair_title` / `repair_tour_text_title_body_dup`. The
**delivery check** is wired into the single delivery choke point in
`generate_tour_text.py` immediately **after** the LOCAL-722 duplicate-stop dedup
(step *3z-ii*) and **before** the conclusion/header rebuild, so a repaired title
flows into the rebuilt "first stop" orientation. A short proper-name title the body
merely opens by naming ("Austrian State Treaty was signed…") is **never** touched;
only a long, sentence-shaped title that IS the body's opening run is shortened to a
clean banner. `repair_title` is the reusable source-side helper for any caller that
finalises a `(title, body)` pair. Deterministic, idempotent.

### Issue #3 — gpt-4o bypassed the cheap arm (every museum-path LLM call listed)

The cheap-arm selector `narration_model_route()` (**generate_tour_text.py:250**)
already routes `NARRATION_MODEL` through `cheap_arm.effective_env` by category. Two
museum-path LLM calls **did not use it** and defaulted to gpt-4o:

| # | call site | before | after |
|---|-----------|--------|-------|
| a | **generate_tour_text.py:22802** — per-stop **narration/description writer** (the big cost: gpt-4o-2024-08-06, 39 calls, $0.70 in the evidence log) | `description_data['model'] = story_pass_model()` → `gpt-4o` | `_narration_model` from `narration_model_route()` (cheap-arm-aware) |
| b | **generate_tour_text.py:22727 → story_pass.py:306** — **story pass** | `generate_story_for_stop(...)` with no `model=` → `STORY_PASS_MODEL` default `gpt-4o` | `model=_sp_model` from `narration_model_route()` |

Both fall back to `story_pass_model()` (`gpt-4o`) when the cheap arm is off, so the
**D370 default is preserved byte-for-byte**; a non-openai bake-off route falls back
to the OpenAI model so the production POST transport is unchanged.

**Every other `gpt-4o` literal on the museum path is out of scope and stays:** they
are CHECK/verify gates (`_check_model()` / `_held_model(...)` — intent, is-restaurant,
geo/venue scope, etc.) and the `TOUR_SCOPE_VETO_MODEL` default (`gpt-4o-mini`).
None is narration; the cheap arm only ever governed the narration/story model.

---

## Tests

- **`test_local823_multilingual_junk.py`** — the exact `Fußzeile` string + de/fr/it/es/nl/pt/vi
  chrome all rejected; real multilingual works (The Kiss, Le Déjeuner sur l'herbe,
  Las Meninas, …) never rejected; the shared `filter_out_junk_titles` drops chrome and
  keeps works.
- **`test_local823_title_body_dup.py`** — the defect shape repaired, short proper-name
  titles untouched, idempotent, clean tour unchanged (21 tests).
- **`test_d370_story_pass_model.py`** — updated: the call-site binding now asserts the
  narration writer routes through `narration_model_route()` and added
  `TestNarrationRouteDefault` (default == `gpt-4o`; museum cheap arm → `gpt-4.1-mini`;
  off-list category → production default).

**Regressions:** `791*`, `802`, `811`, `813`, `814` + the junk / cheap-arm / title
suites + the two new tests: **335 passed, 3 skipped**. Two pre-existing failures are
NOT caused by this change (confirmed by `git stash` at the base):
`test_local424_call_site_binding.py` (verify_stop_claims binding) and
`test_d498_matrix_and_top_size.py::test_summary_says_the_counts_overlap` (reads the
stale `modified_generate_tour_text.py`).

---

## Live — budget enforced ($1.20 cap)

Runner `run_local823_container.py` + wrapper `run_local823_live.sh`: an **isolated
throwaway `local823-postgres`** (never the shared/live DB), the meter contract
(`meter_container_env.docker_meter_args` — bind-mounted `~/Audioura/meterlogs`,
canonical `PAID_API_LOG`, `PYTHONPATH=/opt/meter`, `METER_SERVICE=LOCAL-823`),
`TASK_BUDGET_ID=LOCAL-823 TASK_BUDGET_USD=1.20`, cheap arm
`CHEAP_ARM_CATEGORIES=museum NARRATION_MODEL=gpt-4.1-mini RESEARCH_BACKEND=serper`.
At most 2 tours, both on the cheap arm.

| tour | result | stops |
|------|--------|-------|
| **Belvedere Museum, Vienna, Austria** (German site) | **PASS** | Judith I · Death and the Maiden · Fishermen in Poissy · Portrait of Père Paul · The Evil Mothers |
| **Musée d'Orsay, Paris, France** (French site) | **PASS** | L'Origine du monde · Le Déjeuner sur l'herbe · Bal du moulin de la Galette · Une moderne Olympia · La Nuit étoilée |

- **No `Fußzeile` / site-chrome** anywhere in either delivered tour (grep clean).
- **No title/body duplication** — every stop title is a short proper name.

Delivered files: `Belvedere_Museum__Vienna__Austria_museum_tour_20261030_035212.txt`,
`Musée_d_Orsay__Paris__France_museum_tour_20261030_040300.txt`.

### Per-model cost (meter_report.py, service `LOCAL-823`)

```
TOTAL (status-200 rows, this task): $0.6981  /  cap $1.20   — 540 requests

  gemini/gemini-flash-latest   72 calls   $0.2696
  serper                      160 calls   $0.1780
  openai/gpt-4.1-mini         101 calls   $0.1554   ← narration now on the cheap arm
  openai/gpt-4.1               10 calls   $0.0408
  openai/gpt-4o (non-mini)      4 calls   $0.0353   ← CHECK/verify gates only
  openai/gpt-4o-mini          193 calls   $0.0229
```

**Issue #3 proven:** gpt-4o (non-mini) fell from **$0.75 of a $1.03 tour** to
**$0.0353** across the whole two-tour task, and those 4 remaining calls are
verify/check gates — the narration runs on gpt-4.1-mini (101 calls, $0.1554).

### `task_budget_report.py LOCAL-823`

```
$ python3 task_budget_report.py LOCAL-823
No ledger for task LOCAL-823 (~/.audioura_task_budgets/LOCAL-823.json). No runs recorded yet.
```

`LiveRunMeter` writes the per-task budget ledger to `~/.audioura_task_budgets/`
**inside** the `--rm` container, which is not bind-mounted, so the host ledger is
empty. The **authoritative spend record is the bind-mounted meter log**
(`~/Audioura/meterlogs/paid_api_calls.jsonl`, `service=LOCAL-823`), summed by
`meter_report.py --since 2026-10-30` → **$0.6981**, well under the $1.20 cap. The
in-container LiveRunMeter reserve gate (cap $1.20) was also active per tour.

---

## Files changed / added

- `junk_title_guard.py` — multilingual site-chrome table + rule 2b (issue #1).
- `stop_title_body_dup_guard.py` *(new)* — title/body prefix-dup delivery guard (issue #2).
- `generate_tour_text.py` — narration writer + story pass routed through the cheap arm (issue #3); title/body delivery check wired in.
- `test_d370_story_pass_model.py` — call-site binding updated to the cheap-arm route; default preserved.
- `test_local823_multilingual_junk.py`, `test_local823_title_body_dup.py` *(new)* — unit tests from the exact strings.
- `run_local823_container.py`, `run_local823_live.sh` *(new)* — isolated live-run harness with the meter + budget contract.
