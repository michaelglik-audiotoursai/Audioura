# SUBMISSION — LOCAL-628: Final per-stop EDITOR pass

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-628-editor-pass` (from `subscribed` @ `1b03b78`)
**Base verified:** `git merge-base --is-ancestor 1b03b78 HEAD` → exit 0.

## Why (LEAD D637)
Four rounds of point fixes (LOCAL-623…627) each cleared their own defects, but
every new venue showed new variants of the same class — all introduced by the
many deterministic splice/removal passes that run AFTER narration (story beats,
G4 corrective, gloss gate, degrade, guards). KHM (tour 490) was the latest:
effect-before-cause ordering, a dangling "As a result…" opener, an orphan
"Visscher.", a gloss jammed into a name ("Pieter Bruegel, the 16th-century
Flemish painter known for landscapes, the Elder around 1567"), dropped words
("holdings art", "The effect, heightened the layering"), unintroduced references
("Ernest", "as part of this series"), and evasive filler ("must be appreciated in
person"). Point fixes do not converge. The fix is ONE LLM copy-edit per stop,
run LAST, that repairs what a human editor would fix in a single read — adding
no fact.

## What shipped

### 1. `stop_editor.py` — one gpt-4.1 copy-edit per stop
- `edit_tour_text(tour_text, …)` is the single pipeline entry point;
  `edit_stop(…)` edits one stop; both take an injectable `llm_fn` so tests never
  hit the network. The default `_default_editor_llm` is the one place that calls
  OpenAI (model `STOP_EDITOR_MODEL`, default **gpt-4.1**), metered through the
  house `cost_accumulator` exactly like `tour_conclusion._default_thematic_llm`.
- **Only the body narration is rewritten.** The `Stop N:` header, `Address:`,
  `Coordinates:`, the `Orientation:` block (listener-addressing — kept verbatim)
  and the `Directions:` hand-off are preserved.
- Full instruction contract: reorder (chronological for history, lead with the
  work); repair broken clauses / dangling openers ("As a result", "This move",
  "This detail") / dropped words; delete orphan fragments and evasive filler;
  introduce people on first mention using ONLY stop-local information; keep
  register and the Orientation; keep length within ±20 %; **add no fact, date,
  number, name or claim not already in the input stop.**

### 2. Validation, with the ORIGINAL as the fallback
`validate_edit` accepts an edit only when ALL hold:
- non-empty; length within **±25 %** of the original body;
- **no proper noun** present in the edit that is absent from the original;
- `claim_check.check_paragraph` (the same gate LOCAL-619B uses for the
  conclusion) finds **no new UNSUPPORTED/CONTRADICTED** claim, with the ORIGINAL
  body (+ its passages) as the evidence corpus.

On any failure the ORIGINAL stop is kept and the pass logs
`[LOCAL-628] stop N: rejected(<reason>)`; on success `[LOCAL-628] stop N: edited`.

### 3. Every path, idempotent, no re-spend
- **Fresh path:** `edit_tour_text` runs on `complete_tour` immediately BEFORE the
  LOCAL-619 conclusion rebuild and before the cache/pool store, so what is
  cached, pooled and shipped is the edited text.
- **Cache hit:** the direct-return path edits a pre-628 entry once; a post-628
  entry already carries the hidden marker and is a no-op.
- **Pool / by-reference / overview:** assembled from stored stop narration that
  was already edited on the fresh path before `store_delivered_tour`; new pool
  stops are generated through the recursive fresh path (edited there).
- A hidden idempotence marker (`<!-- LOCAL-628:stop-editor:v1 -->`, invisible to
  the TTS text and the reader) makes a second pass a no-op that never calls the
  LLM — proven by a test whose injected `llm_fn` raises if called.
- Gated behind `STOP_EDITOR` (default **ON**; `STOP_EDITOR=0` disables).

> Note: an earlier revision also ran the editor inside the shared
> `_apply_delivery_hours_guard`. That broke 4 deterministic LOCAL-616 unit tests
> (they assert exact body text and the LLM rewrote it) and was redundant — the
> guard's inputs are already edited. It was removed (commit `e6d2a5b`); the fresh
> path + cache-hit wiring cover every delivery path.

### 4. KHM "open daily" (closed Monday)
`venue_preflight.plan_b_opening_practicals` now runs
`reconcile_daily_with_closed_days(hours)` before building the spoken sentence.
When the grounded hours text BOTH asserts "daily"/"every day" AND names a closed
weekday, the daily claim is dropped so Stop 1 never says the museum is open daily
while the same text says it is closed on a day. The self-qualifying "every day
except Monday" idiom and a genuine 7-day "daily" with no closed day are left
unchanged. Example: `Open daily, 10:00–18:00, closed Mondays` →
`The museum is open 10:00–18:00, closed Mondays.`

## Tests
`test_local628_stop_editor.py` — **14 tests, all pass** — covers the ticket's six
cases: prompt contract; validation rejects an edit that adds a date/name
(injected `llm_fn`); fallback keeps the original; idempotence on a cache hit (no
re-spend); the KHM daily reconciliation; and the real 490 Stop 1 & Stop 2 bodies
(reconstructed with every named defect) through an injected "good" edit — which
validates (0 unsupported/contradicted, no new proper noun, within ±25 %), while a
variant adding a NEW name is rejected.

### Required suites — exit codes
| Suite | Result | Exit |
|---|---|---|
| `tests/test_local60*/61*/62*` | 378 passed | 0 |
| `test_local62[0-7]*` (repo root) | 133 passed | 0 |
| `tests/test_lead_double_conclusion.py` | 2 passed | 0 |
| `python3 test_sq4_merge.py` | ALL TESTS PASSED | 0 |
| `test_local628_stop_editor.py` (new) | 14 passed | 0 |

## Live (own container, cache + pool OFF, 3 stops each)
Built `local628-gen:latest` from this worktree and ran it as
`docker run --rm --name local628-gen` on the `development_default` network
against the shared `postgres-2`. **No `audioura-*` container was touched.** Rows
are additive `is_test` only; no DELETE.

### Van Gogh Museum, Amsterdam → `audio_tours` id **491** (never generated before)
- `[LOCAL-628] stop 1: edited` · `stop 3: edited` · "2 edited, 0 kept original"
- Tour total **$0.8062** (< $0.90 reserve gate). Editor gpt-4.1: 2 calls
  **$0.00748 = $0.0037/stop**.
- `critique.sh 491 3` → **Kiro 6.5/10**.

### Belvedere, Vienna → `audio_tours` id **492** (never generated before)
- `[LOCAL-628] stop 1/2/3: edited` · "3 edited, 0 kept original"
- Tour total **$0.4663** (< $0.90 reserve gate). Editor gpt-4.1: 3 calls
  **$0.01036 = $0.0035/stop**.
- `critique.sh 492 3` → **Kiro 3/10**.

**Live totals:** $0.8062 + $0.4663 = **$1.2725 < $1.50 hard cap**; each tour under
the $0.90 reserve gate. `audio_tours` **296 → 298** (+2); both new rows
`is_test = TRUE`.

### Belvedere Stop 1 — before → after the editor (captured via `STOP_EDITOR_DUMP_DIR`)
`edited=True reason=ok  len_before=2046  len_after=1710` (−16 %, within ±20 %).

BEFORE (editor input, abridged):
> "…This view, rich with history, places you at the heart of a momentous event:
> the signing of the Austrian State Treaty on May 15, 1955. Following the end of
> World War II, … Its choice as the venue underscored its importance; the grandeur
> of Johann Lucas von Hildebrandt's Baroque architecture lent gravity to the
> proceedings. … This decision was not without its wider geopolitical
> implications. The Federal People's Republic of Yugoslavia later acceded to this
> treaty…"

AFTER (editor output, abridged):
> "Stand in the Marble Hall of the Upper Belvedere… Here, you are at the heart of
> a momentous event: the signing of the Austrian State Treaty on May 15, 1955. The
> Belvedere… became a symbol of newfound sovereignty on that spring day. The
> grandeur of Johann Lucas von Hildebrandt's Baroque architecture lent gravity to
> the proceedings, and its selection as the venue underscored its importance. …
> This decision had wider geopolitical implications. The Federal People's Republic
> of Yugoslavia later acceded to the treaty, highlighting its reach and
> significance."

The editor reordered to lead cleanly, removed the "This view, rich with history"
redundancy, repaired "Its choice as the venue underscored… ; the grandeur of…"
into one sentence, tightened the geopolitical paragraph, and introduced NO new
fact (`reason=ok`). Stops 2 and 3 likewise `edited=True reason=ok`
(1219→1238, 1112→902). Full dumps in `local628_dump_belvedere/`.

## Honest assessment — the Kiro ≥ 7 target was NOT met (6.5 and 3)
This is the important part, stated plainly.

- **The editor delivered its contract.** On both tours the per-stop PROSE it
  targets is clean: the 491 critique calls the stops "work-and-artist-led with
  real emotional content and genuine stories"; the 492 Stop-1 before/after shows a
  faithful reorder+repair with no new facts. Every edit was validated and cheap
  (~$0.0035/stop), and the pass is idempotent.
- **The scores are dragged down by defects OUTSIDE the editor's per-stop-prose
  scope:**
  - **Belvedere (3/10):** the upstream STOP SELECTION picked three "a treaty was
    signed in this hall" diplomatic events for a world-class ART museum (Klimt's
    *The Kiss* and the Baroque collection never appear). That is a POI-ranking
    defect; a copy-editor that must add no fact cannot turn a treaty-signing stop
    into a Klimt stop. The critique's own top fix is "fix stop selection to
    prioritize the collection, not the venue's event history."
  - **Van Gogh (6.5/10):** the remaining defects are the CONCLUSION (re-tells
    Stop 1, institutional filler, a 2013 discovery factoid, a bare "3 stops"),
    cross-stop duplication, and hours never spoken — the LOCAL-619 / LOCAL-627 /
    practical-facts machinery, not the per-stop bodies.

In short: LOCAL-628 did exactly what it was scoped to do and did it well, but a
per-stop copy-editor cannot lift a tour whose SELECTION or CONCLUSION is the
problem. The highest-value next tickets, from the two live critiques, are: (1)
collection-over-venue stop ranking (Belvedere), (2) a cross-stop fact ledger +
conclusion rebuild that drops recycled facts and institutional filler (Van Gogh),
and (3) guaranteed spoken hours/admission in the conclusion — all outside this
ticket.

## Files
- `stop_editor.py` (new) — the editor module.
- `generate_tour_text.py` — fresh-path + cache-hit wiring (editor before the
  conclusion; idempotence-guarded).
- `venue_preflight.py` — `reconcile_daily_with_closed_days` + KHM daily fix.
- `test_local628_stop_editor.py` (new) — 14 tests.
- `run_local628_oneshot.py` (new) — the live one-shot driver.
- `local628_vangogh_run.log`, `local628_belvedere_run.log`,
  `local628_vangogh_tour.txt`, `local628_belvedere_tour.txt`,
  `local628_dump_belvedere/` — live evidence.

No change to DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md or
`.continuous_dev/STATUS.md`.
