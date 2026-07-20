# Story Quality — Design Brief (brainstorm draft v1)

**Author:** LEAD (Claude) · 2026-07-07 · **Status:** for Michael's review + brainstorm, then tasking
**Origin:** Michael's observation (2026-07-07): Googling individual paintings surfaces many rich stories (links/articles) beyond museum sites + Wikipedia. Current story mining (`wdvrdawbj4`) is venue-scoped: museum site + en/local wiki. The best stories about a WORK often live elsewhere — other museums' pages about the same artist/technique, quality journalism, exhibition essays, academic articles.
**Relationship to other docs:** this expands **Step 3 (Story mining)** of `GENERIC_GROUNDING_DESIGN.md`. Generic Grounding discovers WHICH works; Story Quality discovers the best STORY about each work. Quality bar: `TOUR_QUALITY_RUBRIC.md` (esp. B3, B5, delivery rule R1).

## Principle

> Stories are FOUND per WORK, not per venue. For every verified stop, the pipeline runs targeted web searches, gates sources by reputation, corroborates claims across independent sources, ranks the candidate stories by type and fit, and credits everything per R1. Zero per-venue or per-artist handcrafting — queries are synthesized from discovered canonical entities, so the same code serves museums and walking tours.

## 0. Empirical grounding (LEAD probe, 2026-07-07)

Four live searches, chosen to span story types and tour types:

| Probe | What the wider web yielded (beyond museum site + wiki) | Story type |
|---|---|---|
| *Song of Songs* cycle (Chagall, Nice) | "To Vava my wife my joy and my lightness" dedication; anticlockwise hang = love escaping linear time (France Today, museum agenda page) | dedication / intention |
| *Blue Nude* cutouts (Matisse) | 1941 cancer → wheelchair → "painting with scissors"; "seconde vie" quote; Blue Nudes I–III each cut in hours (Tate, Centre Pompidou, PBS, Saint Louis Art Museum, Met, PMC medical-humanities journal) | origin / turning point |
| *The Sorrows of the King* (Matisse) | Final self-portrait; references Rembrandt's *David Playing the Harp before Saul*; black silhouette = the artist in his armchair (en.wiki + several weak sources) | technique / reference |
| Promenade des Anglais (walking-tour POI) | 1820: English residents funded construction to employ beggars after a harsh winter; name evolution "Camin dei Inglés" → 1860 annexation (Perfectly Provence, France Today, Culture Trip, en.wiki) | anecdote / origin |

**Findings that shape the design:**
1. **The thesis holds** — per-work searches surface stories the venue corpus doesn't have, for museums AND walking POIs.
2. **Noise is severe** — the same SERPs contained print-shop/reproduction sellers (`bluesurfart`, `artlithographies`, `henrimatisse.org`-style SEO sites), Flickr, Pinterest, personal blogs, Substack, Grokipedia. A reputation gate is mandatory, not optional.
3. **Corroboration is a real signal** — the illness→scissors story appears independently at Tate, Pompidou, PBS, SLAM, PMC. Cross-source agreement can separate "documented" from "reported once."
4. **Hedged material exists** — "Legend has it…" (Promenade). Usable narratively ONLY if attributed as legend, never asserted as fact.

## 1. Pipeline (new module: `work_story_searcher.py`, feeding the existing extractor)

**SQ-S1 — Query synthesis (deterministic base + bounded LLM refinement).** For each verified stop (canonical title + artist + venue/city from Generic Grounding Steps 0–2), emit templated queries: `"{title}" {artist} story behind`, `"{title}" {artist} history making`, `"{title}" {artist} controversy`, and for distributed tours `"{poi}" {city} history story behind`. Localized per `country→lang` (same rule as GG Step 1). ~2–3 queries/stop.
*Why the BASE queries are deterministic (Michael's Q, 2026-07-07):* (a) reproducibility — same work → same queries → testable, cacheable by query key, and CIL cycles compare like with like; (b) cost — an LLM call per query per stop buys nothing when the template already contains the only entities that matter; (c) safety — LLM-synthesized queries drift off-entity (paraphrased/hallucinated titles pull in evidence for the WRONG work — an A6 violation entering through the search door). **LLM refinement IS used, bounded, in the retry round:** when yield is thin, Tier-3 leads + an LLM propose refined queries (e.g. adding "Vence chapel commission"), with a hard rule that every refined query still contains the exact canonical title or its verified local-language form.

**SQ-S2 — Search execution.** SERP API call per query (provider = open question 1). Collect top ~8 results/query: `{title, url, snippet}`.

**SQ-S3 — Source reputation gate (classifier, not hand-list).** Classify each result domain into tiers by CLASS — rules + cached lookups, never a per-venue registry:
- **Tier 1** — institutions & references: museum/institutional domains (verifiable via Wikidata: domain appears as some entity's P856), `.edu`, `.gov`, national-museum TLD patterns, established encyclopedic sources.
- **Tier 2** — quality journalism & exhibition press: recognizable news orgs, art-history publications, academic (PMC, JSTOR-hosted).
- **Tier 3** — blogs/UGC/Substack/Flickr: **leads only** — a Tier-3 claim may seed a query refinement but can NEVER be evidence on its own.
- **Reject** — commerce (shop/product/reproduction pages — detect via cart/price/product markup), aggregator SEO farms, user-photo hosts.

**SQ-S4 — Fetch + work-anchored extraction.** Fetch Tier 1–2 pages (cap ~6/stop, parallel). Run `story_element_extractor` per page with the **work anchor**: the page must reference the canonical title (M3-fixed matcher: multilingual stop-words, content-word rules — "the" is not evidence). Artist-generic pages that never mention THIS work are not evidence for this stop (the artist-article ban, applied at work level). Extended element types: `origin, intention, dedication, turning_point, technique, reference_work, controversy, reception, provenance, person, date, quote, legend`.

**SQ-S5 — Corroboration scoring.** Group extracted claims by semantic key (normalized subject+predicate). Claim statuses:
- `documented` — ≥2 **independent** Tier 1–2 sources. Independence is real, not nominal: near-identical text across domains = syndication/copying, counts as ONE source (the "eating rocks" trap — Michael 2026-07-07: repetition of a joke must not embolden it into fact). Tier-3 sources NEVER corroborate, even each other.
- `reported` — single Tier 1–2 source → delivered only with inline attribution ("According to the Tate…").
- `disputed` — sources conflict, or the claim is a live controversy (provenance disputes, recipe wars, attribution fights). Delivered WITH the dispute exposed: "it's debated — X says…, while Y insists…", sources named (Michael's controversy rule, 2026-07-07). Often the most engaging material — the dispute IS the story.
- `legend` — folklore-typed → always delivered as legend ("The story goes that…"), never as fact.
Additional guard: humor/satire/joke-context detection at extraction time — a claim whose source context is comedic or user-generated jest is dropped regardless of how many pages repeat it. Nothing below `legend` reaches the narrative. **Fail-closed applies to verification only:** a work with zero found stories degrades to the B3 interpretive fallback (invented, clearly interpretive) — the gate never relaxes, the ladder degrades.

**SQ-S6 — Story ranking + tour-level selection (the "which story does this stop deserve" step).**
Per-stop candidate score = weighted sum of:
- *Type value* (default priors: origin/dedication/turning_point > controversy/anecdote > technique/reference > reception; provenance/looting stories score high but see open question 3),
- *Corroboration* (documented > reported > legend),
- *Specificity* (named people, dates, quotes — B1's currency; penalize plaque-restating description),
- *Spine fit* (the spine's chapter role modulates: an emotional-climax chapter prefers turning_point/dedication; an opening chapter prefers origin).

Then a **tour-level diversity pass** (B5): selection across stops is a constrained pick — no story type may dominate (e.g. max ~2 origin stories per 5 stops); prefer the assignment maximizing total score subject to type variety. The spine generator receives the SELECTED story elements per stop plus runner-up elements as texture, and weaves multi-story stops only when both elements are `documented`.

**SQ-S6b — Theme threads: one story, not a bag of facts (Michael's directive, 2026-07-07).**
*The problem (Michael's Nice walking-tour probe):* per-POI search returns rich but DISCONNECTED fragments — the Promenade's English origin, Castle Hill's views, Cours Saleya's market. Interesting beads, no necklace. A tour must tell ONE story that each stop advances, engaging the user to continue.
*Theme discovery:* after S5, cluster elements ACROSS stops by shared entities/motifs (people, eras, events, cultural forces) — deterministic entity-overlap pass first, then one LLM pass that NAMES candidate themes and must cite the supporting element IDs (`grounded_on` discipline; a theme is a claim and obeys claim rules).
*Theme scoring:* coverage (fraction of stops with ≥1 supporting element), evidence strength (documented > reported), distinctiveness, and arc potential (does it have a beginning, a turn, a payoff?).
*Thread-conditioned selection:* S6's ranking gains a thread-fit term — the chosen story per stop is the one that ADVANCES the theme; the individually-best off-theme story survives as runner-up texture. The spine's prolog poses the thread as a promise or question, transitions carry mini-hooks toward the next chapter, the epilog pays it off.
*Worked example (Michael's own POI list, elements verified 2026-07-07):* thread **"An Italian city that became French"** covers 7/7 stops — Vieux Nice (Italian-influenced alleys), Place Masséna (Turin-style ochre arcades), Castle Hill (Savoyard citadel razed by Louis XIV in 1706 after a cannonball found the powder magazine), Port Lympia (Sardinian-era harbor, pointu boats), Cours Saleya (Ligurian market culture), Promenade des Anglais ("Camin dei Inglés" renamed at the 1860 Treaty-of-Turin annexation), Promenade du Paillon (the modern French city built over the old border river). Alternate documented threads from the same element set: "a city built by winters" (1820 English charity project, Queen Victoria's 1890s seasons, February carnival) and "walked by seekers of light" (Nietzsche, Matisse, Fitzgerald on the same seafront).
*Multi-thread blending (Michael's revision, 2026-07-08):* do NOT pick one thread and discard the rest — ALL scoring threads enrich each stop's informational context, weighted by coverage: with threads covering 7, 5, and 4 stops, weights are 7/16, 5/16, 4/16 (coverage-proportional, summing to 1; ~3 threads is a good number). The PROLOG leads with the top thread; per-stop content draws on whichever threads that stop supports, at their weights.
*Personalization hook:* when 2–3 themes score well, offer the choice of EMPHASIS to the user at generation time — this is the personalization feature meeting story quality.
*Degradation (never force a weak theme):* no theme reaches ~60% coverage → organizing-principle fallback (chronological or geographic progression), else honest mosaic mode. A forced theme is an invented claim and violates B3.
*Museum case:* degenerate single-thread — the venue-level origin story (chapel→museum) IS the theme; same machinery, no special-casing.
*Query addition (from Michael's probing pattern):* walking-tour S1 templates gain `"{poi}" {city} who walked here famous visitors` — people are natural thread material.

**SQ-S7 — Crediting per R1.** Every delivered element carries `{source_name, url, snippet}` end-to-end. Inline credit for quotes and all `reported`/`legend` claims; epilog Sources line gains the search-found domains alongside museum site + Wikipedia. Paraphrase-only rule unchanged — snippets are evidence, never prose.

**SQ-S8 — Cache (split strategy, Michael 2026-07-07).** Work-level, not venue-level, in the same Postgres as GG Step 5 (key = work QID when Wikidata-resolved, else normalized title+artist). Two layers with different lifetimes:
- **Core data** (title, artist, medium, dates, coords, canonical sources): TTL 90–180 days — stable, expensive to re-mine, safe to hold.
- **Story elements** (`elements_json`, `sources_json`, statuses): TTL ~30 days + event-driven invalidation (new exhibition / loan / news about the work detected at the venue's agenda page → invalidate and re-mine).
- **Narrative text: never cached.** The delivered story is assembled fresh per tour (personalization, spine fit, tier) from cached elements — so the expensive part (mining) amortizes while the product stays current.
A famous work mined once serves every future tour that includes it — the moat compounds faster than venue caching alone. **Seed job:** rides along with GG Step 5's pre-mine (scheduled master task, e.g. weekly): for each seeded venue, pre-mine stories for its top works so popular tours are near-instant on first request.

## 2. Guard rails (banned patterns honored by construction)

- No theme-word/topic-overlap matching anywhere — work-anchored evidence with the M3 matcher rules (A6).
- No artist-article-as-evidence — at the work level this time (A1/A2).
- No string surgery — ranking/selection operates on the STRUCTURED element list before assembly; corrections drop/replace elements and re-run assembly (B2 lesson from `wdvrdawbj4`).
- No fail-open — SERP/API/network failure for a stop means that stop proceeds with venue-corpus elements or the interpretive fallback, and the failure is logged; it never means "skip the reputation gate."
- Checks drive corrective actions — thin story yield triggers query refinement (one bounded retry with Tier-3 leads), then honest degradation. Never a relaxed threshold.

## 2b. i-con: per-paragraph informational-context scoring (Michael's metric, 2026-07-08)

Every stop's paragraphs (excluding the tour prolog inside Stop 1 and all `Directions:` lines) are scored on Michael's matrix: **1** = no information (look-and-see description the visitor detects unaided; rhetorical questions without answers), **3** = information with little emotional appeal (plaque-level facts; tag-claims without explanation — "consider his sacrifices" naming none; repetition of prolog material), **5** = interesting information (grounded specifics — dates, people, events traceable to story elements — that advance a thread or deliver a documented story). Stop score = paragraph average; tour score = stop average.

**Evaluator (SQ6): hybrid.** Deterministic signals per paragraph: date/proper-noun/number density; claim-traces-to-story-element; thread-element reference; prolog/cross-stop overlap; unanswered-question detector; generic-filler lexicon. Then an LLM rubric pass, few-shot calibrated on Michael's hand-scored paragraphs (Chagall 2026-07-08 tour, Stops 1–2 — the founding calibration set), REQUIRED to quote the sentence that earns each score. Calibration protocol: Michael and the evaluator score the same stop blind; disagreements ≥2 points become new few-shots.

**Known failure signatures i-con must catch** (from the 2026-07-08 Chagall tour): the unanswered-question paragraph (Stop 2: "How did the museum evolve after his passing?" — while the 1988-dation element sat unused in story_elements); the unexplained tag ("consider the sacrifices Chagall made" — which?); the prolog-repeat (chapel→museum restated instead of advanced); zero-date stops; **the unused-founding-element** (Stop 3 never told the 1966 Marc+Valentina donation → 1973 museum creation, though the element was mined — deterministic check: high-value elements with zero usage in their stop); **content-outsourcing** (Stop 3: "engage with the museum staff for additional context" — BANNED: staff referrals are for wayfinding (A4) only, never for content). Delivery rule additions: `Directions:` lines must frame the next stop as the next chapter of the journey (hook), not just name it; no paragraph may refer the visitor elsewhere for the tour's own content.

**Calibration set (Michael + LEAD blind-scored, 2026-07-08 Chagall tour):** Stop 1 (Michael): 5,1,3,3,3 → 3.0. Stop 2: Michael 5,3,3,1 / LEAD 3,3,1,1 — two 2-point splits taught the rubric's key refinement: *decoding function* (naming the depicted story; giving a framework for how to look) rates ≥3 even when visually self-evident; 1 is reserved for aesthetic wallpaper with no decoding value. Stop 3 (post-refinement): 3,1,3,1 — **4/4 blind match, both averages 2.0**. These 13 hand-scored paragraphs + the refinement note are the evaluator's founding few-shots. Structural ruling (Michael): the Orientation/description/Directions structure is intentional and kept; Orientation paragraphs score as content everywhere except Stop 1's tour prolog.

**Reference 5-level example** (what per-work search finds that the venue corpus lacks — Michael's Sorlier research, 2026-07-08): Charles Sorlier (1921–1990), Chagall's master printer at Atelier Mourlot and collaborator of 25+ years, donated his personal archive of prints and rare proofs to the museum in 1986/1988 rather than selling it — making the museum one of the world's most comprehensive repositories of Chagall's graphic work. Documented, emotionally loaded, thread-advancing — the exact target quality for SQ mining. (Also flagged: the 2026-07-08 tour's Stop 3 conflates the five-canvas Song of Songs cycle with the Bible lithograph series — A6-adjacent entity conflation for QA.)

Gate thresholds (proposal, Michael to confirm after calibration): tour i-con avg ≥ 3.5; no stop avg < 3; no more than one 1-scored paragraph per stop. (2026-07-08 baseline tour: ~2.7 — fails, as both assessors' readings say it should.)

## 2c. Content classification + swipe personalization (Michael's design, 2026-07-08)

**Universal taxonomy (all tour types):** every paragraph/story/theme carries a soft distribution over three classes — `details` (dates, names, colors, subject descriptions, menus/prices, building specifics), `historic` (human history, epochs, biography, cultures), `social` (relationships, celebrities, atmosphere). Distributions sum to 1. Stop distribution = i-con-weighted average of its paragraphs (wallpaper must not dominate classification). Produced by the same SQ6 evaluator pass that scores i-con.
**Founding calibration few-shots (Michael's hand labels):** "vibrant hues dance…" ¶ → 70% details / 30% social; "early 1950s return to France…" ¶ → 50% historic / 25% details / 25% social; Stop 2 (Sacrifice of Isaac) stop-level → 0.50/0.15/0.35; themes: "Italian city that became French" → historic; "built by winters" → 50/50 historic/social; "seekers of light" → 50/50 social/details.

**User preference model (Beta-count, per user, per class k):** counters α_k, β_k init 1 (→ p_k = 0.5 start per Michael). Swipe right (like): α_k += c_k·w with w = 1. Swipe left (dislike): β_k += c_k·w with **w = i-con/5** (Michael's rule: low-info dislikes blame the writing, not the topic; likes despite low info are strong topic signals and count fully). Preference **p_k = α_k/(α_k+β_k)**; (α_k+β_k) doubles as confidence. Worked example (Michael's scenario — Stop 2, c=(0.50,0.15,0.35), i-con 2/5, two left swipes): p = (0.417, 0.472, 0.439).
**Selection integration:** SQ-S6 ranking gains a personalization term (story utility scaled by Σ_k c_k·p_k); SQ-S6b's coverage-proportional thread weights are modulated the same way. Cold start = neutral (0.5,0.5,0.5) → today's behavior unchanged.
**Immediate scope:** per-stop class distributions ship with SQ6 (evaluator emits i-con + distribution per paragraph). Swipe capture + preference storage is a Mobile-Kiro + backend task, sequenced after SQ6. Track per-customer: (α,β) per class; per-stop shown rating r (init 0.5, ±0.1 per swipe, clamped [0,1]).

## 2d. Release architecture: i-con in Storied, swipes in Subscribed (Michael's decision, 2026-07-08)

**Storied (v2.2.0):** every generated tour gets per-stop `i_con` + class distribution computed at generation time and PERSISTED — i-con serves as the tour-quality evaluator now, and the persisted metadata is the substrate Subscribed needs later (a customer downloading an EXISTING tour must already find its stops scored and classified). Advisory first: i-con is logged, persisted, and reported in the QA output with the proposed gates (avg ≥3.5 etc.) printed as PASS/FAIL — but it does not reject jobs until thresholds are confirmed against a corpus of scored tours. Preference model accepted: **Beta-count (Option A)** per §2c.

**Persistence (Postgres, Storied migration):**
`stop_metrics(id, job_id, tour_id, stop_index, stop_title, i_con NUMERIC(3,2), class_details, class_historic, class_social NUMERIC(4,3) /*sum≈1*/, paragraphs JSONB /*per-paragraph {i_con, class_dist, flags[]}*/, evaluator_version, created_at)` — tour-level aggregate (i_con_avg, min stop) stored on the job/tour record and included in the tour payload to the app.

**Subscribed (next release, design-ready now — DO NOT build in Storied):**
`user_stop_feedback(user_id, tour_id, stop_index, swipe ±1, rating_after, created_at)` · `user_class_prefs(user_id, α/β per class, updated_at)` — updates per §2c. Liking forecast for any already-scored stop: **r̂ = (i_con/5) · Σ_k c_k·p_k** (sketch; calibrate against real swipe data). Because stop_metrics ships in Storied, Subscribed's forecasting works on back-catalog tours from day one.

## 3. QA / rubric additions

- New QA check: every `documented`-status claim in delivered text traces to ≥2 evidence entries; every `reported`/`legend` claim has inline attribution phrasing present.
- New QA check: story-type diversity across stops (template-smell guard, B5).
- Rubric B3 scoring note: "found" now means found ANYWHERE reputable, credited — a stop scored 5 should carry a wider-web story when museum+wiki are thin.
- Assessment artifact: per-stop story table (type, status, sources) appended to each cycle's ClickUp comment, so LEAD can audit evidence snippets, not match scores.

## 4. Cost & latency → tiered generation (Michael's decision, 2026-07-07)

**Per-stop cache-miss cost** (10-stop tour = 30 SERP calls + ~50 page extractions):
- SERP: Serper ~$0.3–1/1k, Bright Data ~$1.5/1k, Brave $5/1k (free tier removed Feb 2026), Google CSE ~$5/1k → 30 queries ≈ **$0.01–0.15 depending on provider** (Serper cheapest; multiple keys for A/B per Michael — funded).
- Extraction: GPT-4o-mini ≈ $0.01 / GPT-3.5 ≈ $0.08 / GPT-4o ≈ $0.50+ for ~50 pages.
- So the story-mining layer on a fully-cache-miss 10-stop tour: **~$0.02 (cheap stack) to ~$0.65 (premium stack)**, plus existing generation (~$0.05) and TTS (standard ~$0.08, neural ~$0.30, generative ~$0.60 for ~20K chars).

**`GENERATION_TIER` flag (free | plus | max)** — testers (incl. Michael) can generate the same tour at multiple tiers to compare; the flag is the experiment harness for ROI:
| Tier | Target cost (all-in, 10 stops, incl. voice) | Story mining | Models | Voice |
|---|---|---|---|---|
| `free` | < $0.10 | venue corpus + `work_stories` CACHE HITS only (free tours get richer over time as paid mining fills the cache — zero marginal cost) | 4o-mini extraction | standard |
| `plus` | ~ $1 | full SQ pipeline, 3 queries/stop, cache-miss mining allowed | 4o-mini extract, 4o narrative | neural |
| `max` | $2–5 experimental | 5 queries/stop, ~10 pages/stop, refinement round always on, editorial rewrite pass, candidate-spine ranking (generate 2 spines, keep the better) | 4o everywhere | generative |
**Economics (Michael):** charge for GENERATION only; once produced, serving is free. Like a film: expensive to make once, cheap to serve many — and `work_stories` makes every generation cheapen the next. The `max` tier tests whether "the best tour money can buy" is the product: some users pay $10 for visible quality who won't pay $0.10 for something they don't value.
Latency: 5–10s/stop parallelized, overlaps GG mining; seed job + cache make popular venues near-instant.

## 5. Acceptance (generic, empirical — same spirit as GG's)

Zero config changes, evidence files auditable:
1. **Chagall/Nice:** the Song of Songs stop tells the Vava dedication story, credited.
2. **Matisse/Nice:** a cutout-era stop tells illness→scissors with ≥2-source corroboration in the evidence log.
3. **Restaurant/food tour (Nice):** a salade niçoise stop exposes the Médecin "never boiled potato" controversy as `disputed` with sources; a socca stop delivers the 1543 siege tale as `legend` and the dockworker street-food history as `documented` (probed live 2026-07-07: Wikipedia, Culture Trip, food-history sources all yield these).
4. **Walking tour (Nice):** Promenade des Anglais stop tells the 1820 beggars-built-it story via the SAME code path — AND the tour carries a documented theme thread covering ≥60% of stops (e.g. "an Italian city that became French"), posed in the prolog and paid off in the epilog, with each on-thread stop advancing it; if no thread reaches coverage, the run must show the explicit degradation decision in its evidence log.
5. Every delivered story claim traces to a snippet; QA exit 0; zero uncredited `reported`/`disputed` claims.

## 6. Decisions (Michael, 2026-07-07 — questions closed)

1. **SERP provider:** choose by cost; Michael will fund keys from multiple providers to determine ROI. Tier budgets: free < $0.10/tour all-in, plus ~$1, max $2–5 experimental (see §4 and the `GENERATION_TIER` flag).
2. **Tier-3 (blogs/Substack):** usable for idea generation AND query refinement — but any claim without Tier-1/2 proof is DROPPED. Corroboration must be independent (syndicated copies count once); satire/joke context is rejected outright (the "eating rocks" trap). Baked into SQ-S5.
3. **Controversy:** include — often the top attention-getters — but the controversial nature must be exposed ("it's not proven, but discussed at…") with sources. New `disputed` status in SQ-S5.
4. **Cache:** split strategy — long TTL (90–180d) for core data, ~30d + event-driven invalidation for story elements, narrative text never cached (SQ-S8). Seed job: yes, rides along with GG's pre-mine as a scheduled master task.
5. **Sequencing:** PARALLEL development with a clear interface contract between GG and SQ; SQ prototypes immediately on Chagall/Matisse as exemplars. → **Interface contract to pin before Kiro tasking:** GG delivers to SQ, per stop: `{canonical_title, local_title, artist, work_qid?, venue{name,qid,city,country,lang}, tour_type: contained|distributed}`; SQ returns per stop: `{selected_elements[], runner_up_elements[], each: {type, status: documented|reported|disputed|legend, text, sources[{name,url,snippet}]}}`.

## 7. Proposed task breakdown (for 🟦 Services — Kiro, after Michael's review)

| ID | Task | Depends on |
|---|---|---|
| SQ1 | `work_story_searcher.py`: query synthesis + SERP integration + result collection | SERP key (Q1) |
| SQ2 | Source reputation classifier (tier rules + Wikidata-P856 institutional check + commerce/UGC detection) | SQ1 |
| SQ3 | Work-anchored extraction (extended element types) + corroboration scoring (`documented`/`reported`/`legend`) | SQ2, M3 matcher fix |
| SQ4 | Story ranking + tour-level diversity selection + spine integration (selected elements per stop) | SQ3 |
| SQ4b | Theme discovery + thread-conditioned selection (SQ-S6b): cross-stop element clustering, theme scoring, thread-fit ranking term, spine promise/payoff, coverage-based degradation | SQ4 |
| SQ5 | R1 crediting extension: inline attribution for `reported`/`legend`/quotes; epilog Sources expansion | SQ3 |
| SQ6 | QA checks (attribution-present, corroboration-trace, type-diversity) + rubric/assessment-artifact update | SQ4, SQ5 |
| SQ7 | `work_stories` Postgres cache + TTL | SQ3 |
| SQ8 | Acceptance run: Chagall + Matisse + Promenade walking tour, zero config, evidence audit | all |

Each SQ task runs through CIL: Kiro posts approach → LEAD refines → implement + pilot + self-assess → LEAD independent assessment.
