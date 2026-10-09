# SUBMISSION — LOCAL-636: Content correctness

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-636-content-correctness` (from `subscribed` @ `a4fbf8b`)
**Base verified:** `git merge-base --is-ancestor a4fbf8b HEAD` → exit 0.

Three content-correctness defects from Bench R2, each reproduced on the real
tour and fixed in an owned file with a grounded test. Live-proven on the National
Gallery (the R2 refusal). I did not touch `stop_editor.py` or
`cross_stop_reference_guard.py` (LOCAL-635), nor DECISIONS/CLAUDE/BACKLOG/
WORK_QUEUE/STATUS.

---

## Issue 1 — another work's text inside a stop

`same_title_bleed_guard.py` + `test_local636_text_bleed.py` (8 tests)

**1a. Painting vs sculpture (Uffizi 488).** Stop 1 *Leda col cigno* — an oil-and-
resin painting on panel — carried a sculpture condition blurb: *"various parts of
the sculpture were altered or added, including the head … does not originally
belong to this body."* The LOCAL-626 object-type guard already models object
FAMILIES (vessel / picture / paper / sculpture / …) and is wired in
`generate_tour_text.py`, keyed on the POI title + material field. It was a **no-op
here** because the title (*Leda col cigno*) carries no object noun and the POI
material field was empty, so `stop_kind` resolved to `None`.

Fix: `infer_stop_kind_from_body()` reads the stop's OWN declared medium from the
narration — an unambiguous object noun or a "medium ON support" phrase ("oil and
resin painting **on panel**" → picture) — and the tour-level filter resolves the
kind **once per whole stop body** (the medium and the bleed sit in different
paragraphs) and applies it to each paragraph. The lone sculpture sentence is now
dropped; a genuine bronze stop keeps its own sculpture language; an ambiguous
body ("the painting on the bowl") is never force-typed.

**1b. Cross-stop evidence bleed (Courtauld 485).** Stop 1 (*Paul Cézanne*) opened
with the Seurat stop's viewing text: *"The careful division of color, a hallmark
of Seurat's pointillist method …"*. `sentence_is_bleed` only fired on
creation-verb / "by X" attributions, so a foreign artist named **possessively**
with a technique noun slipped through.

Fix: a possessive style/technique bleed — a foreign artist named `<Name>'s
<method/style/pointillism/…>` while the stop's own artist is NOT named — is now a
bleed. A genuine comparison that names the stop's own artist ("unlike Seurat's
method, **Cézanne** …"), and an artist's technique in their own stop, are kept.

Verified on the real tour texts: tour 488's sculpture sentence is dropped and the
painting content kept; tour 485's Seurat sentence is dropped with no stop body
emptied.

---

## Issue 2 — the same story told twice across stops

`derepetition_guard.py` + `test_local636_repeated_story.py` (7 tests)

D533 (`strip_repeated_facts`) keyed every repeat on a `(year, entity)` signature,
so a reworded story with **no year** sailed through and the log read "No
cross-stop fact repetition detected."

* **Brera 513** told the Brera-name etymology twice — Stop 1 *"the Germanic word
  'braida,' meaning a grassy opening"* and Stop 2 *"its name drawn from an ancient
  word for a grassy opening"* — no year either side. Added a **keyphrase
  signature**: a rare bigram of adjacent distinctive LOWER-CASE common nouns
  (`grassy opening`). Proper nouns, sentence-initial words and quoted work titles
  are excluded, and BOTH tokens must be outside an expanded common
  tour/art/English set, so an ordinary collocation ("turning point", "faith and
  loss") never keys.
* **Courtauld 485** repeated the collector boast — Stop 1 *"the most important
  group of Cézanne's works in Britain"*, Stop 2 *"the largest collection of
  Seurat's work in the United Kingdom"*. Different artist, different wording, no
  shared year. A **superlative-collection signature** keyed on the canonicalised
  place (Britain and the United Kingdom collapse to one) catches it across
  artists.

`check_cross_stop_fact_repetition` now unions `fact_signatures` with
`keyphrase_signatures`; `strip_repeated_facts` keeps the FIRST telling and drops
the later one, never emptying a stop. Verified on the real tours: tour 513's
"grassy opening" count 2 → 1, tour 485's superlative boast 2 → 1 (the Stop-2
Seurat telling dropped, the Stop-1 Cézanne telling kept). Zero false positives on
previews, titles or ordinary prose.

---

## Issue 3 — the National Gallery failed to generate

`venue_resolver.py` + `test_local636_national_gallery.py` (8 tests)

Bench R2 job `59b34f98` refused the National Gallery ("could not find enough
verified material about 'The National Gallery'"); R1 had built tour 495.

**Reproduced and root-caused — it was NOT the P195 rule.** Live:
`resolve_venue("The National Gallery", "London")` → **Q180788**; SPARQL returns
**390 works**, **379** carry P195 including Q180788, and the LOCAL-632 P195 rule
rejects only **4** genuine P276-location leaks (e.g. "Salisbury Cathedral from the
Meadows", actually Tate Q430682 — a correct rejection). The deterministic
catalogue alone (~4,869 NG paintings in Wikidata) fills a 3-stop tour with **zero
Gemini dependency**, and `safe_preflight` already swallows Gemini errors.

The refusal happened in the provider-overload window (33/108 Gemini calls
failed). Selection does not need Gemini — but entity resolution needs Wikidata,
and `_search_entities` was a **single shot**: one transient 5xx/timeout returned
`None`, `resolve_venue` returned `None`, and the famous museum was refused as thin
evidence. `fetch_venue_works` already retried (LEAD); the first step, search, did
not.

Fix: `_search_entities` now retries a transient 500/502/503/504 or
timeout/connection error (3 attempts, 1.5s/3s backoff), preserving the 10s
per-attempt timeout, the None-on-failure contract, and the 429 dead-host-breaker
behaviour (429 still trips the breaker, no retry). A passing Wikidata stall no
longer sinks a famous, well-catalogued museum.

---

## Tests — full required suite, exit codes

| Suite | Result | Exit |
|---|---|---|
| `tests/test_local60*` `61*` `62*` | 378 passed | 0 |
| root `test_local62*` `63*` + `tests/test_local63*` (incl. the 3 new 636 files) | 277 passed | 0 |
| `tests/test_lead_*` | 5 passed | 0 |
| `test_local590_*` | 42 passed | 0 |
| `python3 test_sq4_merge.py` | ALL TESTS PASSED | 0 |

New tests: `test_local636_text_bleed.py` (8), `test_local636_repeated_story.py`
(7), `test_local636_national_gallery.py` (8).

---

## Live run — own container, after 20:00 EDT, cap $1.30

Harness: `run_local636_live.sh` + `run_local636_container.py`. Own disposable
container `local636-gen` (`--rm`, spare port 5097, network `development_default`);
never `docker compose -p audioura`, never an `audioura-*` container. Cache OFF,
stop pool OFF (fresh). Hard cap $1.30 combined via `tests/live_run_meter.py` with
a reserve gate (start a tour only if `spend + $0.80 <= $1.30`). Gate check:
clock ≥ 20:00 EDT before launch.

**National Gallery — the R2 refusal — GENERATED:** tour **516**, 3 stops:
*The Supper at Emmaus*, *The Toilet of Venus ('The Rokeby Venus')*, *The Hay
Wain* — all genuinely at the NG (P195 rule kept them), hours spoken, 0 network
failures.

**Metered total $0.6861** (< $1.30). The **reserve gate SKIPPED the Courtauld** to
honour the cap (`$0.7371 + $0.80 > $1.30`) — the gate working as required. The
Courtauld fixes are proven deterministically on the real R2 `tour_485` text (the
15 issue-1/issue-2 tests).

### detectors.py — tour 516
```
FAIL dangling_opener:
FAIL title_line_rewritten:
FAIL recall_unseen_work: ortraiture seen in works like the Self Portrait in a Straw Hat, which
516: 3 detector failure(s)
```
All three are **LOCAL-635 / LEAD territory, not LOCAL-636**:
`recall_unseen_work` and `dangling_opener` → `cross_stop_reference_guard.py` /
`stop_editor.py` (LOCAL-635); `title_line_rewritten` → the LEAD title line. My
own detectors confirm tour 516 has **0 cross-stop story repeats and 0
object-type / possessive-technique bleed**. Noted for those owners.

### critique.sh — tour 516
`critique_516.md` scores 4/10 but confirms the tour **generates** and that **all
three works are genuinely at the National Gallery** (criterion 8 location pass) —
proving the R2 refusal is fixed and the P195 rule keeps NG. Its flagged defects
(phantom cross-references to a Vigée Le Brun stop, the dangling "This decision",
the chronology-impossible influence claim, missing admission) are all outside my
owned files.

### Database — additive is_test only
| | before | after |
|---|---|---|
| `audio_tours` total | 321 | 322 |
| `audio_tours` is_test | 258 | 259 |

Exactly **+1** additive `is_test` row (id 516). **No DELETE.** The own container
was removed (`--rm`); the 13 `audioura-*` service containers were untouched. No
GCloud.

Artifacts: `submission_artifacts/local636_live/` (`critique_516.md`,
`detect_516.txt`, `tour_516.txt`); full log in `tours/local636_live/`.

---

## Files changed (owned only)

| File | Change |
|---|---|
| `same_title_bleed_guard.py` | body-kind inference + possessive-technique bleed (issue 1) |
| `derepetition_guard.py` | keyphrase + superlative-collection cross-stop signatures (issue 2) |
| `venue_resolver.py` | `_search_entities` transient-error retry (issue 3) |
| `test_local636_text_bleed.py` | new (8) |
| `test_local636_repeated_story.py` | new (7) |
| `test_local636_national_gallery.py` | new (8) |
| `run_local636_container.py`, `run_local636_live.sh` | isolated live harness |
| `submission_artifacts/local636_live/*` | live evidence |
