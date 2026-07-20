# Tour-Quality Architecture — Storied vs. ④ New Architecture split

Source: `NewArchitecture_q-dev-chat-2026-06-29.md` (Strategic Advisor design conversation).
Decision (Sir Michael, 2026-06-29): pursue the vision, but split it so Storied stays shippable by end-July and the heavy/infra pieces land in the separate ④ New Architecture phase.

**Rule:** validate with a POC (below) BEFORE any code lands. All code on the `storied` branch only — `main` (frozen Beta) is untouched.

---

## INTO STORIED (Aug 1) — the "Sprint-1 core" (high ROI, low cost/risk)

| Piece (from the doc) | Maps to Storied task | Notes |
|---|---|---|
| **Fact-extraction + hallucination guard** | `wdvrdaw4bu` (richer stories) | gpt-3.5-turbo low-temp JSON fact sheet per stop, cross-checked; low-confidence → flag, don't publish. ~+$0.002/stop. |
| **Narrative spine generator** | `wdvrdaw4bu` | ONE gpt-4o call **per tour** (~$0.05), varies by tour type (museum/walking/restaurant/book). The differentiator. |
| **Per-stop callback injection** | `86aj2jnh7` (remove repetition) + `wdvrdaw4bu` | Spine passed as context into existing Phase 5 prompt — no new call. Creates the "re-hear the last stop" effect; kills repetition. |
| **Single onboarding question** | `wdvrdaw4bv` (SCOPED DOWN) | "What brings you here?" → 4 emoji (🎨 Art / 📖 History / 👨‍👩‍👧 Family / ✈️ First-time) → selects a default tone. UI + one routing variable. No server interest model in Storied. |

Cost of the Storied slice: ~**+$0.07/tour** (advisor estimate) — negligible at any sale price.

Tour-type coverage: spine templates per type (museum/walking/restaurant/book) — one generator, multiple templates. POC validates **museum** first; extend templates to the other types within Storied (low marginal effort).

---

## DEFER to ④ NEW ARCHITECTURE (post-Storied; separate epic `wdvrdaw13n`)

| Piece | Why deferred |
|---|---|
| **Deep RAG perspective layers** (3–4 per stop: Artist/Historian/Curator/Accessible, Wikipedia + museum-site grounding) | High effort; multiplies Phase-5 calls; not needed for the Aug-1 quality jump (the spine already delivers "richer"). |
| **Passive preference inference** (interest model from replay/pause/perspective-switch) | Heavy server feature + expands privacy/Data-Safety disclosure (behavioral profiling). |
| **Tour caching** — Level 1 exact + Level 2 partial reuse | Cost/scale asset; changes delivery semantics; interacts with the R2 blob path we just stabilized — do carefully, not rushed. |
| **Trend intelligence** — Level 3 (frequency counter, off-peak pre-generation, "Popular near you") | Scale feature; depends on caching; no Aug-1 dependency. |

**On "100 unsupervised parallel tasks":** don't. The content pipeline (`generate_tour_text.py`, Phase 3A/5) is the code we just stabilized for Beta. Sequence the ④ work into reviewed tasks (verify-don't-trust), not a parallel free-for-all.

---

## PRECURSOR — Proof of Concept (run BEFORE any Storied code)
Owner: Services Kiro. Validate quality + economics on a real tour before committing to the architecture. Deliverables:
1. The **current** Chagall (Musée National Marc Chagall, Nice) 10-POI tour text, as the pipeline produces it today (baseline).
2. A **spine-driven** version: draft a museum-type narrative-spine prompt, generate the spine for the 10 POIs, then regenerate the 10 stop descriptions using `facts + spine-position` as context.
3. Side-by-side: **measured cost** (USD) and **generation time** (seconds) for both, plus a short quality read (accuracy, non-repetition, "connected chapters" feel).
Acceptance: cost within ~+$0.07/tour of baseline AND a clear, human-noticeable quality lift. If yes → schedule the Storied Sprint-1 core. If no → revise the prompt before any pipeline code changes.
