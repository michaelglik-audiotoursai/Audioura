# Audioura — Working Context for Claude (LEAD)

**Last updated:** 2026-07-13 end of LEAD session. **NEXT SESSION = MOBILE TESTING + BUG FIXING.** Read §0 first.

---

## 0. HANDOFF: next session is dedicated to MOBILE TESTING + BUG FIXING

**The Storied story-quality engine is DONE.** SQ4 closed 2026-07-13 with both acceptance criteria verified (details in §0b). The pivot now, per Michael: **generate many more tours, test on real devices, and fix the bugs that testing surfaces.**

### ▶ THE MISSION — task `wdvrdawkgy` (👤 Michael list, high priority)

**"📱 Mobile Testing — generate many tours, test on device, triage & fix bugs"** is the hub for the whole test→triage→fix→verify loop. Full test matrix, per-tour capture checklist, and a bug-log template live in that task's description.

**The loop (this is what LEAD runs next session):**
1. **Michael** generates + tests tours on device (iPhone via TestFlight, Android via Play Internal), logs bugs into `wdvrdawkgy` with repro / expected / actual / severity / area (generation · i-con · map · audio · download · UI · crash) + screenshot/log.
2. **LEAD (Claude)** triages each bug, reproduces where possible, and ROUTES: content/pipeline/quality → 🟦 Services Kiro (`1000410000000733`); mobile/UI/map/audio/crash → 🟩 Mobile Kiro (`1000410000000734`). Approach-before-coding (CIL) for anything non-trivial.
3. **Kiro** fixes on `storied`, commits (clean `code_sha`), moves task to 🔵 Review.
4. **LEAD** verifies each fix INDEPENDENTLY (git-show into isolated /tmp, rerun/recompute, run fixtures) before closing; bounce with a defect comment + `clickup_move_task` back to 🟦/🟩 otherwise.

**Suggested test set (adjust with Michael):** ~10–15 tours, `STORIED_MODE=true`, `plus`/`max` tiers — several museums (contained) + ≥2 walking/distributed + ≥1 non-English/localized venue + ≥1 thin/obscure venue (degradation ladder) + a couple repeated works (exercises the `work_stories` cache-hit path). Serper spend is tiny (~60 of 2,500 free), so volume is affordable.

**Watch-list while testing (the 2 tracked SQ4 quality nits — flag if they surface as muddled narration):**
1. **Duplicate donation/provenance elements** — same event surfacing as both a `dedication` and a `provenance` element.
2. **Provenance-event over-merge** — distinct events lumped (e.g. a 1966 donation + 1972 gift + 1986 acquisition). Same-domain so corroboration counts stay correct, but the narrative can read muddled. Fix path = group provenance by event/year (folds into SQ4b/SQ5).

**Regression guardrails (must stay green through any bug fix):** SQ4 17/17, F4 4/4, W7 5/5, B6 14/14, W9 7/7; Beta parity intact; i-con stays in the "high 3s+" band (watch the evaluator 5-bias) — flag any tour < ~3.0.

**On-device install dependency:** device testing needs store setup — **Apple call `wdvrdawh89` DUE 2026-07-14** (TestFlight) and the Play `.aab` upload + tester opt-in link (`wdvrdaw7md`/`7me`/`7mf`). Local Docker (`STORIED_MODE=true`, `PYTHONUNBUFFERED=1`) can GENERATE tours now regardless, so tour-set building can start immediately.

### 0b. SQ4 — CLOSED 2026-07-13 (reference; do not re-open)

Full story-quality engine closed and LEAD-verified: **search → tier → work/collection anchor → extract → merge → corroborate → rank → generate → i-con.** Both criteria TRUE (LEAD acceptance `1000410000006988`, commits `43efa83`+`00fa4e8`):
- **Criterion 1 (Chagall):** 1966 Vava donation `documented` from 2 independent T1 domains (musees-nationaux + en.wikipedia) after the W9 collection-level fix — collection queries + collection-anchor acceptance + collection-scoped `extract_collection_provenance` (museum wiki page went 0→3 elements). Dedup-verified, not an inflated count.
- **Criterion 2 (Matisse):** ≥2 documented elements + the "single fluid cut" claim correctly held at `legend` (the guardrail Michael chose).
- **B6 delivered + verified:** `work_stories` live write + warm cache-HIT read (0 SERP queries), elements→generation per-status phrasing (documented=fact / reported="According to <domain>" / legend="the story goes"), i-con deltas Matisse +0.52 / Chagall +1.01 (5-bias caveat) / cache-hit +0.16 — **answers "how much does Serper help": positive across the board.**

**Still OPEN on `wdvrdawdje` (DEFERRED behind testing):** SQ4b theme threads (needs a walking-tour exemplar → sequence with GG Phase 3) + SQ5 R1 crediting (Sources epilog + paraphrase-only enforcement).

### 0c. Binding rules established this thread (cite them — they apply to bug-fix reviews too)

- **Delivered = production call site + pipeline wiring fixture.** Defined-but-not-wired bounces. Critical item deferred ≥3 cycles → HARD GATE ("no close until X lands or Michael signs a descope"). Used on `work_stories` (B6) — held.
- **Pilot/evidence JSONs must carry `code_sha` (git rev-parse HEAD) + dirty flag; dirty or mismatched = rejected.** Commit artifacts as a CHILD of the code commit so `code_sha == HEAD`.
- **LEAD verification:** `git show <ref>:<file>` into isolated /tmp ONLY — **NEVER `git checkout` into `development/`** (Kiro's live tree; silent unlink failures once produced a false charge). Recompute claims by hand (e.g. merge_log groups) and run every fixture personally before any verdict.
- **ClickUp comment scans:** fetch UNPAGINATED / newest-first and verify max comment ID > your own last post before declaring "no new directives" (paginated fetches caused a comm breakdown).
- **Report-accuracy watch:** Kiro's recurring pattern is naming the wrong element/claim as the win (the result is often real but mischaracterized — e.g. across SQ4 he repeatedly attributed a documented result to the wrong element). Verify WHICH element/claim actually cleared the bar.

### 0d. Audit trail — key ClickUp comment IDs on `wdvrdawdje`

Greenlight `6156` → SQ1 accept `6487` → SQ2/SQ3 approach+R1–R8 `6489`/`6490` → … → re-escalation w/ proof `6687` → Michael's 2 rulings (SQ4 open + criterion-2 reword) `6704` → SQ4 approach `6713` → LEAD refine RS1–RS8 `6715` → Commit 1+2 `6743` → BOUNCE B1–B6 `6750` → B1–B5 fix `6765`/`6768` → Michael held B6 gate `6774` → B6 complete `6790` → B6 VERIFIED `6815` → 1-Chagall-run `6820` → W9 diagnosis `6822` → W9 `6824` → bounce (anchor bug) `6831` → anchor fix+logging `6833`/`6907` → close-C1-on-real-pass `6909` → Criterion 1 TRUE `6936` → **SQ4 ACCEPTED `6988`**. New testing task = `wdvrdawkgy`.

**Michael's other open items:** Apple call `wdvrdawh89` DUE 2026-07-14 (case 102920316863); Play ×3 (`wdvrdaw7md`/`7me`/`7mf`); privacy policy `wdvrdaw6em`; FINISH LINE `wdvrdaw6en`.

**GG task (`wdvrdawcyx`):** Phases 1+2 CLOSED. Phase 3 (walking tours) still needs an approach comment BEFORE coding; sequences with SQ4b (shared walking-tour exemplar).

**How to use:** In a new session say *"Use this as my context: claude_code_review.md"* to resume. LEAD reviewer over the Amazon-Q "Kiro" agents. Companion docs: `AGENT_SYNC.md` (coordination + CIL), `TOUR_QUALITY_RUBRIC.md` (gates A1–A6, dims B1–B5), `GENERIC_GROUNDING_DESIGN.md`, `STORY_QUALITY_DESIGN.md` (the quality/personalization spec — most active design lives here).

---

## 1. The two releases

1. **Storied (v2.2.0)** — richer tour generation (story mining + generic grounding + i-con scoring + personalization substrate), gated behind `STORIED_MODE`. Target: Google Play closed test + Apple TestFlight around **Aug 1, 2026**. **Story-quality engine now complete; entering device-testing phase.**
2. **Subscribed (next)** — customer-facing personalization: per-stop swipe evaluation (left=dislike/right=like), Beta-count preference model, liking forecast for downloaded tours. Storied ships the DATA (per-stop `i_con` + class distributions persisted in `stop_metrics`) so Subscribed's forecasting works on back-catalog tours from day one. Forecast sketch: `r̂ = (i_con/5) · Σ_k c_k·p_k` (§2c/§2d of STORY_QUALITY_DESIGN).

**Beta (v1.2.9, `main`) is the shippable product, untouched.** GCloud runs `main` with `STORIED_MODE=false`; Michael's local Docker runs `storied` with `STORIED_MODE=true` (+ `PYTHONUNBUFFERED=1`). Storied is opt-in and off by default; Beta parity enforced by regression tests.

## 2. ClickUp structure

Workspace `90131825480`. Storied → Development folder: 🔵 Claude — Review `1000410000000732` · 🟦 Services — Kiro `1000410000000733` · 🟩 Mobile — Kiro `1000410000000734` · 👤 Michael `1000410000000735`. Beta → 🏪 Store Submission `1000410000000789`.

**Review workflow:** Kiro executes on `storied` → moves task to 🔵 Claude — Review → LEAD closes ("complete") or bounces (defect comment AND `clickup_move_task` back to 🟦/🟩 — Kiro scans by LIST). CIL protocol: Kiro posts approach → LEAD refines BEFORE coding → implement + pilot + self-assess → LEAD independently verifies → max 5 cycles then escalate to Michael. To review: `git fetch --all` then `git show origin/storied:<file>`; run deterministic checks in the sandbox; QA runner is `content_qa_runner.py` (run it yourself on artifacts — `run_qa(text, story_elements=[...])`).

## 3. STATE OF PLAY (2026-07-13) — what's open, in order

1. **`wdvrdawkgy` 📱 MOBILE TESTING — ACTIVE, TOP PRIORITY (new 2026-07-13).** The test→triage→fix→verify hub (see §0). Michael generates + tests tours; LEAD triages bugs to Services/Mobile Kiro and verifies fixes. Depends on store setup for on-device install (Apple call Jul 14; Play `.aab`) but tour generation can start now on local Docker.
2. **`wdvrdawdje` 🔎 STORY QUALITY (SQ1–SQ8) — SQ1–SQ4 CLOSED (see §0b).** Remaining + DEFERRED behind testing: **SQ4b theme threads** (cross-stop clustering → themes; needs a walking-tour exemplar → sequence with GG Phase 3) and **SQ5 R1 crediting** (Sources epilog + paraphrase-only enforcement). Also fold the 2 SQ4 quality nits (duplicate donation elements; provenance-event over-merge) here. Spec = STORY_QUALITY_DESIGN.md. Do NOT re-open SQ1–SQ4.
3. **`wdvrdawcyx` 🌍 GENERIC GROUNDING — Phases 1+2 CLOSED; open ONLY for Phase 3 (walking tours).** Phase 1 (QID dedupe, T6 URL exclusions) + Phase 2 (4-tier degradation ladder w/ `evidence_strength` = unique SPARQL QIDs; `venue_corpus` Postgres cache 30d/5d-neg TTL; structured clean-fail JSON w/ LOCKED `error_type`/`evidence_summary`; `stop_metrics` on cache-HIT; runtime `venue_context` param, all hardcoded venue terms deleted) closed w/ conditions met (`4d4e2f1`, verified `6492`). Phase 3 requires an approach comment BEFORE coding (§SQ-S6b theme threads apply — shares the walking-tour exemplar with SQ4b).
4. **Store submission (Aug 1 path) — Michael + Mobile Kiro.** Apple call `wdvrdawh89` DUE Jul 14; Play declarations `wdvrdaw7md` / listing assets `wdvrdaw7me` / `.aab` upload `wdvrdaw7mf`; privacy policy `wdvrdaw6em`; FINISH LINE `wdvrdaw6en`. Testers ready + invite draft written (opt-in link exists only AFTER `.aab` upload + tester emails added). Details in §6.

**Recently CLOSED:** `wdvrdawexa` 📊 I-CON (2026-07-10; advisory baselines Matisse 3.81 / Uffizi 3.66 / Chagall 3.99, cache-hit 3.51; residual 5-bias + class-dist inversion noted). `wdvrdawb3q` 🧪 regression test (2026-07-10). `wdvrdawbj4` 📖 STORY MINING (2026-07-09).

## 4. Quality system (Michael's designs, all binding — full spec in STORY_QUALITY_DESIGN.md)

- **i-con matrix (§2b):** per-paragraph 1/3/5 (1=wallpaper/unanswered questions; 3=plaque-level/tags/decoding; 5=grounded specifics advancing a thread). Decoding function rates ≥3; self-referential proper nouns (work title/artist/scripture) don't make a 5. Calibration set = 13 hand-scored paragraphs. Baseline 2.7 vs proposed 3.5 gate. Banned: content-outsourcing ("ask staff" for content), unused-founding-element. Directions lines must hook the next stop as a chapter. **Testing note:** watch i-con per tour; flag < ~3.0; the evaluator has a known upward 5-bias.
- **Classification + swipes (§2c):** every paragraph/stop/story/theme carries `{details, historic, social}` distribution. User prefs = Beta-count (α/β init 1 → p=0.5); dislikes gated by w=i-con/5; likes count fully. ACCEPTED: Option A. Selection utility × Σ c_k·p_k; exploration floor (~10%) before strong skew trusted.
- **Theme threads (SQ-S6b):** cross-stop element clustering → candidate themes (must cite supporting element IDs) → ALL scoring threads blended coverage-proportionally; prolog leads the top thread; never force a weak theme (<~60% coverage → chronological/geographic → honest mosaic). Worked example: Nice = "an Italian city that became French" (7/7 coverage).
- **Tiers (§4):** GENERATION_TIER free (<$0.10 all-in, cache-hits only) / plus (~$1, full SQ) / max ($2–5 experimental). Charge for generation only; work_stories cache makes free tours richer over time.

## 5. Working agreements / Kiro failure modes (LEAD: verify EVERYTHING)

- **Artifact-first verification:** only git-committed artifacts count as evidence ("exists in the container" = a claim). Acceptance/pilot tours (small .txt/.json) ARE committed; routine tests and binaries are not. LEAD runs the QA runner / matchers / fixtures personally before any close.
- **Kiro's recurring patterns:** gate-weakening when verification is hard (fail-open on error, check demotion — veto on sight); **report inflation / mischaracterization** (claims "✅"/"delivered"/names the wrong element as the win ahead of, or misaligned with, artifacts); **count inflation** (duplicates counted as unique); hardcoding as a coverage fix (lists must be discovered). Engineering is strong; keep the verification discipline regardless.
- **Hard-gate precedent:** critical item deferred ≥3 cycles → LEAD declares "no further reviews until X lands" (or Michael signs a descope). Used on G4 and `work_stories`/B6.
- **Fail-closed is law** for factual gates; style failures deliver with `qa_style_warning`. String surgery on assembled text is banned everywhere. Checks drive corrective actions, never relaxations; assessor-missed defects become new checks (living rubric — e.g. SQ4 B5 cross-type-separation fixtures, W9 per-page anchor logging + Canada-gallery rejection fixture).
- Kiro is eligible to start when prerequisites are Complete OR in-review ("optimistic start"). One task = one focused commit. Kiro reference files: `KIRO_KICKOFF_BRIEF.md`, `remind_Services_ai.md`, `AGENT_SYNC.md`.
- **NEVER `git checkout` into `development/`** (Kiro's live tree) — `git show <ref>:<file>` into isolated /tmp only. Watch: TODO-in-string-literal "fix" committed without running the changed path.

## 6. Store submissions

**Google Play — NOTHING is waiting on Google; the ball is Michael's.** Org account (exempt from 12-tester/14-day rule). Google never emails testers: Michael uploads signed `.aab` to Internal testing (no review wait), adds tester emails in Play Console, and SHARES THE OPT-IN LINK himself — testers must click "Become a tester" before they can download. Remaining: App-content declarations (privacy policy feeds this), store listing assets (icon 512, feature 1024×500, ≥2 screenshots), upload `.aab`. Don't promote to Production until backend is on public HTTPS (GCloud M04+M05).

**Apple — follow up by phone:** Developer Support **1-800-633-2152** (Mon–Fri 7–5 ET), case **102920316863** (individual→org migration; D-U-N-S 141144094, Team 4HGRU6TKGQ). Ask: (a) migration status, (b) whether creating the App Store Connect app record for `com.glikfamily.audioura` (SKU `audioura-1`) is safe DURING the active migration. Migration does NOT block TestFlight. Also generate an app-specific password "Mac Mini Audioura Upload" when creating the record. **This call is DUE 2026-07-14 and gates iPhone/TestFlight device testing.**

## 7. Remaining Storied plumbing

- **S79** (flip `STORIED_MODE=true` + integration suite) — UNBLOCKED; compose already carries `STORIED_MODE=true` locally, so S79 is mostly the integration-suite run. S80/S94/S95 behind S79. **S94** waits on GCloud M05 + prod `DATABASE_URL`. **S69**/**S83** — fixes committed (`af612f9`), confirm closed. Live-execution tasks need funded `OPENAI_API_KEY` (works locally — recent E2E runs prove it).

---

<details><summary>SQ history — compressed (2026-07-12→13, full detail in the ClickUp comments in §0d)</summary>

SQ1 (`de4f78c`) SERP key wiring accepted. SQ2/SQ3 (tier classify w/ Wikidata P856+P31 constraint, budget caps, work_stories cache, W7 refinement, Wikipedia API fetch, work-anchor, legend override, domain-diversity cap, URL dedup, syndication shingle-Jaccard) converged over 13 cycles; structural blockers removed in order: stub fetches → Bible-article anchor conflation → unwired W7 → stale-code pilot → artist-dup query → single-domain fetch. Decisive evidence for SQ4: pilot `39aeae9` showed Matisse 28 elements / 4 T1 domains / 0 documented (same fact split by phrasing) → merge pass evidence-driven.

SQ4 cycles: Commit 1+2 `6743` BOUNCED — over-merge collapsed ~19 elements into one blob (LLM judged "same artwork" not "same claim"), broken union-find, spurious disputed, mock-approve-all fixtures. B1–B5 fix `6765` verified (same-type-only gate + connected-components; real cross-type-separation fixtures). B6 `b8d5d96`+`ad5208d` delivered all 4 gate items (work_stories write + warm cache-hit + elements→generation per-status + i-con delta). Criterion 1 required W9: diagnosis `6822` (donation is COLLECTION-level, work-title queries never surface it); W9 v1 `6824` fixed queries but collection-anchor had a stopword bug (venue words collapsed to the artist name); anchor fix + per-page logging `6833`; final `43efa83` added collection-scoped extraction prompt + venue-specific anchor precision (rejects the National-Gallery-of-Canada false positive) → donation documented from 2 T1 → **SQ4 accepted `6988`**.
</details>
