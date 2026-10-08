# SUBMISSION — LOCAL-619B: the conclusion is about the TOUR, not a list of stops

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-619B-thematic-conclusion` (from `subscribed` @ `fd47495`)
**Ruling:** Michael, D634 (2026-10-07) — *"Naming all stops, especially if there
are more than 3, will be very annoying to the listeners: the conclusion should be
about our tour: what are the common elements in the stops and the theme of the
tour."*

---

## 1. What was wrong

LOCAL-619 (merged) fixed the broken `"That's N stops — …"` splice and made the
count honest, but its conclusion still **enumerated**:

> From X to Y, you have followed the thread of the collection of <museum>. That's
> N stops in all. Along the way, a few moments stand out. <stop>: … <stop>: …

For a 4-stop tour that reads as a roll-call — exactly what D634 bans.

## 2. What ships now — a THEMATIC conclusion

`tour_conclusion.build_conclusion` now produces a conclusion **about the tour as a
whole**, 2–4 sentences, in this shape (D634 (a)–(e)):

- **(a) thread / theme** — the discovered tour theme (SQ-S6b
  `theme_thread_discoverer`) when one was chosen, otherwise a phrase **derived
  from the stops' common elements** (shared century/period, recurring subject or
  genre), otherwise the venue's own collection;
- **(b) one line of meaning** — why the thread matters / what to take away;
- **(c) optionally ONE named example** — never a list (at most one delivered
  title appears in the whole conclusion);
- **(d) the stop count** — stated **only when correct** (it is counted from the
  delivered text, so when present it is always correct; omitted for a 1-stop
  overview);
- **(e) the restaurant offer** — the last sentence.

There is **no "From X to Y"** and **no per-stop recap**.

### The cheap-LLM writer (metered + validated, with deterministic fallback)

A cheap LLM (`gpt-4o-mini`, `CONCLUSION_LLM_MODEL`) may write (a)+(b) **from the
delivered stops' text only**:

- **Metered** via `cost_accumulator.add_llm_usage(...)` — the spend lands on the
  network meter / tour cost scope like every other LLM call.
- **Validated** with the existing **claim/G4 machinery**: the draft is checked
  with `claim_check.check_paragraph(draft, …, passages=<delivered stop narration>)`
  and rejected if it carries **any** `UNSUPPORTED` or `CONTRADICTED` claim — i.e.
  any date / number / attribution / proper-noun predicate not already in the
  delivered text. It is also rejected if it contains a `From … to …` construction,
  states the stop count, or names more than one delivered title.
- **Deterministic fallback**: on *any* failure — no API key, network error, a
  smuggled fact, a From→to, a two-title enumeration — the builder falls back to the
  deterministic common-element **template**, which is always true and always
  present. The template is also what ships when no key is configured.

### Wiring (one choke point, idempotent, no re-spend)

`rebuild_conclusion` gained `use_llm` / `llm_fn` / `api_key`. The three
`generate_tour_text` call sites:

- **Fresh path** — first build with the discovered theme preferred and
  `use_llm=True` (the metered, validated LLM pass).
- **Every-path delivery guard** (fresh / pool / cache / by-reference / overview) —
  **preserves** an already-present, count-correct thematic conclusion (so the
  fresh path's theme/LLM body survives to delivery); otherwise it builds one,
  using the LLM only when no thematic conclusion exists yet. A re-run / cache hit
  is deterministic and **never re-spends**. (`has_thematic_conclusion()` gates
  this.)
- **Overview path** — unchanged single-stop deterministic rebuild (no LLM).
- **Cache-trim** (`tour_cache_layer1`) — deterministic rebuild, no LLM (no
  re-spend on a cache serve).

## 3. Tests

`tests/test_local619_real_conclusion.py` was rewritten to the thematic form (the
fixtures are still the real delivered tours 440/441/442). The ticket's criteria as
tests (`TestThematicConclusionCriteria`):

1. **no stop list** — at most ONE delivered title in the conclusion;
2. **no "From … to …"**;
3. **every factual noun appears in the stops** — `claim_check.check_paragraph`
   against the delivered narration yields 0 unsupported/contradicted;
4. **restaurant offer last**;
5. **count correct when present**.

Plus `TestLLMThematicBodyValidation` (injected `llm_fn`, offline): a grounded
draft is accepted; a smuggled fact / a From→to / a two-title draft are each
rejected and fall back to the template; no-key uses the template.

### Suite exits (individual, `set +e`)

| suite | result | exit |
|---|---|---|
| `tests/test_local619_real_conclusion.py` | 21 passed | 0 |
| `tests/test_local60*` / `test_local61*` / `test_local62*` | 350 passed | 0 |
| `test_local617_work_first.py` | 47 passed | 0 |
| `test_local618_*.py` (4 files) | 33 passed | 0 |
| `test_sq4_merge.py` | script-style (pytest collects 0); `python3 test_sq4_merge.py` → `ALL TESTS PASSED` | 0 |

One regression surfaced on the first full run and was fixed:
`test_local616_hours_guard_every_path.py::test_idempotent` — the new "preserve
existing thematic conclusion" branch skipped `rebuild_conclusion`'s
`.strip()+"\n"` normalisation, so a second guard pass dropped the trailing newline
(770 vs 769 bytes). Fixed by normalising the preserved text's trailing newline.

## 4. Live run (isolated, metered, cap $1.50)

Disposable container (`local619b-gen`, `--rm`), image built from this branch tree
(so the thematic builder and wiring are baked in), joined `development_default`
**only** to INSERT additive `is_test` rows. **2 never-seen museums × 4 stops**,
combined cap **$1.50**. Harness: `run_local619b_live.sh` + `run_local619b_container.py`
+ `tests/live_run_meter.py`.

### Städel Museum, Frankfurt → audio_tours id **462** (path=fresh, 4 stops)

Stops: *Melencolia I*, *Heller Altarpiece*, *Rhinocerus*, *Ritter, Tod und Teufel*.

> **Together, these works reflect the Renaissance's deep engagement with human
> intellect, emotion, and the exploration of existential themes. This ongoing
> dialogue challenges us to contemplate the complexities of our own existence, as
> seen in Dürer's "Ritter, Tod und Teufel. That's 4 stops in all.**
>
> If you would like to eat nearby we can build you a restaurant tour.

(LLM-written body, claim/G4-grounded.) D634 criteria: **all 5 PASS** — 1 title
named (the single example, ≤1 OK); no From→to; claim/G4 unsupported+contradicted
= 0; restaurant last; count 4 = delivered 4.

### Musée des Beaux-Arts de Lille → audio_tours id **463** (path=fresh, 4 stops)

Stops: *Bouquet de fleurs*, *Jésus au jardin des Oliviers*, *La plage de Berck*,
*Portrait de Marguerite Elisabeth de Largillierre*.

> **This tour highlights the evolution of museum techniques and renovations,
> showcasing how institutions like the Musée des Beaux-Arts de Lille have enriched
> their collections through significant acquisitions and thoughtful curation.
> Understanding this evolution emphasizes the ongoing importance of preserving
> cultural narratives and the dynamic relationship between art and its historical
> context. That's 4 stops in all.**
>
> If you would like to eat nearby we can build you a restaurant tour.

D634 criteria: **all 5 PASS** — 0 titles named; no From→to; claim/G4 = 0;
restaurant last; count 4 = delivered 4.

### Meter

`TEST-LOCAL-619B` TOTAL **$1.1100** (openai $0.9502, gemini_grounding $0.0840 /
6 queries / 8 requests, gemini_tokens $0.0258, serper $0.0500, preflight $0.0314).
Under the $1.50 cap, not capped. One `cost_ledger` row
`10d8d8c8-6301-44a7-8101-e5a58963fa5e`, `description='test run'`.

Full log: `tours/local619b_live/local619b_live.log` (tours/ is gitignored).

### `critique.sh` scores

- **462 Städel — 4.5/10**
- **463 Lille — 3/10**

(critiques at `~/Audioura/.continuous_dev/calib/critique/critique_462.md`,
`…/critique_463.md`.)

**Honest read of the scores vs. this ticket's scope.** Both scores are driven by
**pre-existing, out-of-scope** stop-body defects the critic lists under criteria
1/2/3/5/8, none introduced here:

- 462: a garbled/contradictory hours block, cross-stop recap back-references
  ("as you recently admired…"), and an orphan "Bosch's 'Ecce Homo'" line.
- 463: an **institutional** theme ("Evolution of Museum Techniques and
  Renovations") leaking into the stop bodies, with stops leading on
  accession dates / Sotheby's / €220,000, plus a garbled sentence.

On the **conclusion** (criterion 6) specifically:

- 462: the critic quoted only *"That's 4 stops in all."* and called it "no real
  conclusion" — but the thematic body (the Renaissance sentences above) **is**
  present directly above that line and is what the listener hears; the count is
  the optional, correct (d) clause, not the whole close.
- 463: "conclusion is about the theme, not the art." This is correct — and it is a
  faithful consequence of the **upstream** SQ-S6b theme discoverer producing an
  *institutional* theme. The conclusion builder's job is to reflect the delivered
  tour's thread, which it did. The fix for an institutional theme belongs in
  `theme_thread_discoverer` / the LOCAL-617 institutional-theme rejection (it
  already rejects such themes for stop bodies but one still reached the thread
  here), not in the conclusion builder. I have **not** changed theme discovery, as
  that is out of this ticket's scope; flagging it for a follow-up.

In both cases the conclusion itself satisfies all five D634 criteria and is
grounded by claim/G4.

## 5. Data safety

Only **additive `is_test=true`** rows were written (ids 462, 463). **No DELETE**,
no GCloud. The container was `--rm`; the image was removed on exit.

## 6. Files

- `tour_conclusion.py` — thematic `build_conclusion`; `_derive_common_elements`,
  `_template_thematic_body`, `_best_example_title`; `_llm_thematic_body` +
  `_default_thematic_llm` (metered) + `_thematic_draft_ok` (claim/G4 validation);
  `has_thematic_conclusion`; `rebuild_conclusion` `use_llm` passthrough; opener
  patterns recognise both the new thematic and legacy From→to forms.
- `generate_tour_text.py` — fresh path first LLM build with discovered theme;
  every-path guard preserves/rebuilds; trailing-newline idempotency fix.
- `tests/test_local619_real_conclusion.py` — rewritten to thematic expectations +
  LLM validation/fallback tests.
- `run_local619b_live.sh`, `run_local619b_container.py` — isolated live-run harness.
