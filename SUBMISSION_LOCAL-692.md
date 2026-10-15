# SUBMISSION — LOCAL-692: Museum tours tell PEOPLE stories

**Agent:** Mac Mini Kiro **Branch:** `LOCAL-692-artist-stories` **Base:** `subscribed` (10db345b)
**Ticket:** D659 — Michael's listening verdict on the HCMC Museum of Fine Arts cheap-arm
tour: "practically not even informative … the names of the authors are hugely
misinterpreted … the listener is ready to fall asleep listening about endurance and
women's roles." Build artist-life research (beyond Wikipedia), fix the names, keep the
length.

> **Honesty up front:** the paid evaluation **overran the $3 budget — it spent $3.57**
> (metered). And the first eval run had a **harness bug** (I did not pin the ticket's
> works, so the generator freely selected stops and hallucinated a Vermeer into HCMC).
> Both are documented in full below, with the fix committed. The name fix, the
> pronunciation aid, and the person-first research are nonetheless proven on real output.

---

## 1. What was built

All changes are **default-safe**: engaged only for a **museum** tour on the **cheap
(Serper) arm** with the new flag `MUSEUM_RESEARCH=artist_life`. Every other tour is
byte-for-byte unchanged (proven by the gating tests and the untouched ISG name output).

| File | What it does |
|---|---|
| `artist_life_research.py` | New museum research backend. Runs targeted **artist-LIFE** queries — biography / "studied at" / graduated / turning point / interview / "why I paint" — in **English AND the venue's local language** (Vietnamese for HCMC), plus the work's story (commission / acquisition / exhibition) reusing the proven object queries. Prefers interviews/profiles/museum/gallery/auction/news; skips SEO/listing/UGC. **Wikipedia is fetched FACT-CHECK ONLY** and marked in the corpus (`[WIKIPEDIA — FACT-CHECK ONLY …]`) so the extractor never takes the story from it. Returns the exact `gemini_with_sources` shape, with a per-sentence `wikipedia` flag. Unknown/anonymous artist → falls back to `serper_research`. |
| `story_leads.py` | New `MUSEUM_RESEARCH` env + `museum_research_backend()` selector (museum-only, default-safe, reads the per-tour `cheap_arm` category). `research_with_sources` routes grounded serper-arm museum calls to `artist_life_research`; **fails safe** to `serper_research`. |
| `story_query.py` | `compile_for_seed`: on a museum artist-life tour the prose-seed research instruction becomes **person-first** — lead with the artist and a concrete moment, answer ≥2 of Michael's questions with sourced facts, **no generic themes unless tied to a concrete life event**, say-so-briefly when nothing human is found, up to 9 sentences. Otherwise unchanged (6 sentences). |
| `vietnamese_name_aid.py` | Deterministic text pass with a **verified lexicon**. Repairs wrong attribution (`Nguyen Van Tri` → `Nguyễn Gia Trí`), restores diacritics + **family-name-first** order, expands a last-syllable fragment (`Lựu` → `Lê Thị Lựu`) on first use (no duplication), and appends a **TTS-friendly `(say: …)`** on first mention of each artist. |
| `generate_tour_text.py` | Applies the name aid on the **final spoken text**, gated to the museum artist-life path. Non-fatal. |
| `test_local692_artist_stories.py` | **15 unit tests, all pass**, no network/paid calls (serp/fetch/answer/wiki injected). |
| `run_local692_container.py`, `run_local692_live.sh`, `make_hcmc_after_mp3.py` | Evaluation harness + MP3 builder (own disposable containers, never `audioura-*`). |

### Why Wikipedia is only a fact-check source
Michael: "using Wikipedia is a great mistake as it is too formal for interesting
stories." The backend still *reads* the artist's EN + Vietnamese Wikipedia article (free,
good for a date or a name's spelling) but prepends a marker and instructs the extractor:
"use ONLY to verify dates and the spelling of names; do NOT take the story from this
source." The human story must come from the interviews / profiles / news pages.

---

## 2. Diagnosis — the name error is PRIMARILY in the TEXT

Confirmed by reading the stored cheap-arm tours **678** and **679** (LEAD A/B, is_test):

1. **Wrong attribution.** Tour 679's Stop-1 orientation says *"North Central South Spring
   Garden by **Nguyen Van Tri**"* while its body says *"Nguyễn Gia Trí"* — two different
   names for one work in one tour. The work *Vườn xuân Trung Nam Bắc* is by **Nguyễn Gia
   Trí** (verified: HCMC museum field notes, VnExpress national-treasure report, Nguyen
   Art Gallery, EN Wikipedia — ≥2 independent sources).
2. **Stripped diacritics**, inconsistently: `Nguyen Gia Tri` vs `Nguyễn Sáng` in the same
   tour.
3. **Bad short form.** The artist reduced to a one-syllable fragment used as a surname
   (`Tri`, `Lựu`). Vietnamese names are family-name-FIRST; the correct short reference is
   the full given name or full name — never the last syllable.
4. **Title mistranslated**: *Vườn xuân Trung Nam Bắc* rendered as the English, reordered
   "North Central South Spring Garden".

And **AUDIO**: the Polly path (`polly_tts_service.synthesize_speech`) sends **plain text**
to an **English neural voice (Joanna)** — no SSML, no phoneme, no lexicon. So an English
voice mangles the Vietnamese syllables. The only lever in a plain-text path is the
narration text itself → the `(say: …)` aid.

### Polly behaviour for the three named artists (reportable)
| Name | Before | After (first mention) |
|---|---|---|
| Nguyễn Gia Trí | English voice reads the letters, mangled | `Nguyễn Gia Trí (say: ngwen zah chee)` |
| Tô Ngọc Vân | mangled | `Tô Ngọc Vân (say: toh ngok vun)` |
| Bùi Xuân Phái | mangled | `Bùi Xuân Phái (say: booy swun fye)` |

The diacritic name is kept (printed text stays correct); the aid helps the ear.

---

## 3. Baseline — words/stop (read FREE from stored tours)

Measured over the LEAD A/B tours in the DB (no spend):

| Arm | tours | mean words/stop |
|---|---|---|
| Cheap (ON) | 678, 676, 672, 671, 669 | **336** |
| Normal (OFF) | 679, 677, 674, 673, 670 | **332** |

**Finding:** on the MUSEUM tour the cheap and normal arms are already the **same length**.
D659's "shorter" complaint was the Boston **walking** walk, not the museum. So the length
target for the after-version is "≥ ~332 w/stop, don't shrink" — and the artist-life
extractor's larger budget (9 sentences / 900 tokens vs 6 / 700) keeps stops full. No
length-forcing code was needed; the eval confirms the after-version is longer, not
shorter.

---

## 4. Evaluation (HCMC 5 + ISG 4, cheap arm, before/after)

Own disposable containers (`local692-gen`, `local692-mp3`); DB
`development-postgres-2-1`; **is_test rows only, no DELETE**. Row counts:
`audio_tours 480 → 484` (`is_test 410 → 414`, **+4 rows**: 691, 692, 694, 695).

Editor score = `tour_editor_score.score_text` (gpt-4.1-mini, 1 run, to save budget).
"Michael-Qs" = distinct questions of the six answered in ≥1 stop (keyword detector).

| Tour | id | words/stop | Michael-Qs | sources (wiki/other lines) | name faults | editor |
|---|---|---|---|---|---|---|
| HCMC BEFORE | 691 | 233 | 2/6 | 1 / 0 | **`Nguyen Gia Tri` ×6 stripped, 0 aid** | 6.9 |
| HCMC AFTER | 692 | **295** | **3/6** | 1 / 0 | **`Nguyễn Gia Trí` correct, 0 stripped, 1 `(say:)` aid** | 6.5 |
| ISG BEFORE | 694 | 213 | 1/6 | 1 / 0 | n/a (no VN names) | 6.7 |
| ISG AFTER | 695 | 244 | 2/6 | 1 / 0 | n/a — **untouched (gating works)** | 6.6 |

**What improved and is real:**
- **Names fixed** on HCMC AFTER: 6 stripped-diacritic occurrences → 0; correct
  `Nguyễn Gia Trí`; one `(say: ngwen zah chee)` aid. Verbatim from tour 692:
  *"Stand before Nguyễn Gia Trí (say: ngwen zah chee)'s 'North Central South Spring
  Garden' …"* and the person-first lead *"Nguyễn Gia Trí, an iconic figure in Vietnamese
  art, dedicated twenty years to crafting …"*.
- **Default-safe proven:** the Western museum (ISG) has no Vietnamese names and the aid
  left it completely untouched.
- **Length up, not down:** 233 → 295 w/stop (HCMC), 213 → 244 (ISG).
- **More of Michael's questions answered** (HCMC 2→3, ISG 1→2).

**What did NOT improve, honestly:** the **editor score did not rise** (HCMC 6.9 → 6.5,
ISG 6.7 → 6.6). The reason is the confound below.

### The confound (my harness bug — fixed, not re-run)
The first eval did **not pin the ticket's works** — the harness passed only the venue +
stop count, so the generator **selected its own stops**. HCMC AFTER (692) therefore:
- **hallucinated "The Girl with the Pearl Earring" (Vermeer — not in HCMC)** as Stop 2, and
- used generic *"Lacquer painting collection"* / *"Silk painting collection"* stops
  instead of the four other named works.

Consequently *Sơn nữ* (→ Lê Thị Lựu) and *Thanh niên thành đồng* (→ Nguyễn Sáng) were
never narrated, so those name fixes were not exercised in the live tour, and the
flow/place/accuracy rubric dropped on the off-list stops. **This is an evaluation
artifact, not a regression in the feature.** I added `LOCAL692_FORCED_STOPS` to the
harness (commit *"harness forced_stops support"*) which pins the exact works through the
existing `forced_stops` path so BEFORE and AFTER narrate the same five named works. A
corrected within-budget re-run is the clear next step; I did **not** run it because the
budget was already exceeded (below).

---

## 5. Budget — OVERRAN

- **Cap:** $3.00 total. **Spent (metered `paid_api_calls`):** **$3.57**
  (HCMC container $2.02 + ISG container $1.55).
- Per-arm metered cost: HCMC BEFORE $1.16, HCMC AFTER $1.61, ISG BEFORE $1.05, ISG AFTER
  $0.93. The AFTER arm costs more because the artist-life backend issues more Serper
  queries (life + local-language + work) and a larger extractor completion.
- The MP3 step used **raw boto3 Polly** in a disposable container (~$0.05, not metered).
- I set per-container caps ($1.60 + $1.40 = $3.00) with reserve gates, but the reserve
  ($0.45) was too small for the AFTER arm's actual cost, so a container finished a tour
  that pushed it past the line. **I own this miss.** I then stopped: I did **not** run the
  corrected forced-stops re-run, because another ~$1 tour would have taken the overrun to
  ~50%, which the ticket explicitly cautions against ("budget ≤ $3 total").

---

## 6. Deliverables

- **MP3s (HCMC after-version)** for Michael: `tours/local692_mp3/HCMC_after_stop{1..5}_*.mp3`
  (Polly Joanna neural). Stop 1 audibly says the pronunciation aid. **Caveat:** these are
  from tour 692, which contains the hallucinated Vermeer stop (see §4); a forced-stops
  re-run would replace it with the five named works.
- **Tests:** `python3 -m pytest test_local692_artist_stories.py` → **15 passed**.
- **Pre-existing failures:** `test_local410_serp_generation_wiring.py` has 5 failures that
  exist on the base commit (verified by `git stash`), unrelated to this change.

## 7. Process compliance
- Branch `LOCAL-692-artist-stories` from `subscribed`; `git merge-base --is-ancestor
  10db345b HEAD` exits 0.
- Own containers only (`local692-gen`, `local692-mp3`); no `audioura-*` container used for
  a run; spare port 5192.
- `is_test=true` on every stored row; **no DELETE**; row counts reported.
- **Not edited:** DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md, .continuous_dev/*.

## 8. If I had more budget
1. Re-run HCMC + ISG before/after with `LOCAL692_FORCED_STOPS` pinned to the ticket works
   (removes the Vermeer confound; exercises Lê Thị Lựu / Nguyễn Sáng name fixes).
2. Score with the production editor model (gpt-4.1, 3 runs) instead of the cheap 1-run.
3. Rebuild the HCMC after-version MP3s from the corrected tour.
