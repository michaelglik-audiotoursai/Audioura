# Services Kiro Context Reminder
## Who you are
🔧 **SERVICES KIRO** — **CRITICAL**: Always start ALL replies with "🔧 SERVICES KIRO -"

**UPDATED**: 2026-07-12 (Phase 2 CLOSED. SQ1 is next priority.)

1. You are **Services Kiro** responsible for all Docker services in `C:\Users\micha\eclipse-workspace\AudioTours\development\`. You have blanket approval to change code, run Python programs, start/stop Docker services without waiting for approval.
2. You maintain this file and update it after significant changes.
3. Task management via ClickUp (Storied space, list 🟦 Services — Kiro, ID `1000410000000733`).

---

## 🚨 CRITICAL IDENTITY RULES
- **ALWAYS** prefix every reply with "🔧 SERVICES KIRO -"
- **GIT BRANCH**: `storied` (off `main` = `beta-2.1.1+18`). **Never touch `main`.**
- **VERSION**: `2.2.0+1` (distinct from Beta's 2.1.x)
- **LAST GIT STATE**: `e2c6ebd` — Phase 2 final remediation complete. All items accepted.
- **NEXT ACTION ON RECOVERY**: Read this file top to bottom. Execute the SQ1 approach post (see IMMEDIATE WORK below).
- **WORKFLOW**: Blanket approval for all service changes. One task = one commit = one review.
- **NEVER perform string surgery on assembled text** — corrections on STRUCTURED DATA only.
- **NEVER fabricate examples** — use verbatim from actual files.
- **Report accurately** — never claim PASS without running the actual check.
- **NEVER claim PASS without QA exit 0** — report inflation is a critical violation; show verbatim exit codes.

---

## 🔥 IMMEDIATE WORK: SQ1 on wdvrdawdje (Story Quality)

### Michael's directive (2026-07-11):
> "SQ1 on wdvrdawdje takes priority over the Phase 3 approach post."

### What to do NOW:
1. **Read `development/STORY_QUALITY_DESIGN.md`** in full — it is the spec (Michael approved 2026-07-07)
2. **Post SQ1–SQ3 implementation approach** as a ClickUp comment on task `wdvrdawdje` for LEAD refinement BEFORE coding
3. Do NOT code until LEAD refines the approach

### SQ1 scope (from task description):
- `work_story_searcher.py`: deterministic query synthesis (+ bounded LLM refinement round, exact-canonical-title rule) + SERP integration
- **Blocked on SERP key(s) from Michael** — stub with a fixture-based SERP mock until then so SQ2–SQ3 aren't blocked
- CIL protocol applies: approach → LEAD refines → implement + pilot + self-assess → LEAD review

### Guard rails (veto-on-sight):
- No theme-word matching
- No artist-article-as-evidence (work-anchored only)
- No string surgery on assembled text
- No fail-open anywhere (SERP/network error → proceed with venue-corpus elements + log, never skip the gate)

---

## 📋 PHASE 2 CLOSE CONDITIONS (carry to first Phase 3 commit)

These two items are MANDATORY in the first commit of Phase 3 (wdvrdawcyx), whenever that starts:
1. Extract `compute_tier(n_verified, evidence_strength)` to module level in `generate_tour_text.py`; call it from the pipeline; import it in `test_tier_computation.py`
2. Commit the two G4 false-positive sentences as permanent unit fixtures

Phase 3 itself requires an approach comment before coding (walking-tour generalization, §SQ-S6b theme threads apply).

---

## 📋 TASK STATUS

| Task | Status | Next |
|------|--------|------|
| wdvrdawdje (Story Quality) | **ACTIVE — SQ1 approach post** | Read STORY_QUALITY_DESIGN.md, post approach |
| wdvrdawcyx (Generic Grounding) | Phase 2 CLOSED (conditional) | Phase 3 approach post (after SQ1) |
| wdvrdawb3q (Regression test) | CLOSED | None |
| wdvrdawexa (I-CON) | CLOSED | None |
| wdvrdawbj4 (Story Mining) | CLOSED | None |

---

## 🏗️ TWO ENVIRONMENTS
| Environment | Branch | URL | Mode |
|---|---|---|---|
| **GCloud (production)** | `main` (`beta-2.1.1+18`) | `https://api.audioura.com` | DO NOT TOUCH |
| **Local Docker** | `storied` | `http://localhost:5000` | `STORIED_MODE=true` |

### Container
- `development-tour-generator-1` — port 5000, `STORIED_MODE=true`
- Rebuild: `docker-compose -f docker-compose-master.yml build tour-generator && docker-compose -f docker-compose-master.yml up -d tour-generator`
- Postgres: `development-postgres-2-1` — password `password123`, user `admin`, db `audiotours`

---

## 🏗️ PHASE 2 ARCHITECTURE (what was built — reference only)

### Degradation Ladder (4 tiers)
- RICH (evidence_strength ≥8): full found-mode, R4 replenishment enabled
- MEDIUM (evidence_strength 3-7): verified stops only, R4 DISABLED
- THIN (evidence_strength 1-2): fewer honest stops, no fabricated names
- UNRESOLVABLE (0 verified OR entity resolution failed): structured clean-fail JSON

### Tier Computation (B8 — unique QID count)
```python
_unique_sparql_qids = set(w.get('qid', '') for w in sparql_works if w.get('qid'))
_evidence_strength = len(_unique_sparql_qids)
if _n_verified == 0: 'unresolvable'
elif _evidence_strength >= 8: 'rich'
elif _evidence_strength >= 3: 'medium'
else: 'thin'
```

### G4 Proper-Noun Grounding (B7 — runtime venue context)
- `_COMMON_PROPER`: art-period closed class only (renaissance, baroque, etc.)
- Venue-derived terms injected at runtime via `venue_context` param to `run_qa()`
- No hardcoded venue/city/artist terms

### venue_corpus Cache
- Table: `venue_corpus` in Postgres (QID PK, corpus_version, no DEFAULT on tier)
- Positive TTL: 30d, Negative: 5d
- Auth: `admin:password123@postgres-2:5432/audiotours`

### Key Files
- `generate_tour_text.py`: VerificationResult, tier computation, cache, R4 gating
- `venue_resolver.py`: cache_get/cache_put, entity resolution
- `generate_tour_text_service.py`: structured error response, venue_context wiring
- `content_qa_runner.py`: G4 with venue_context, D3 checks, single-venue consistency
- `test_tier_computation.py`: 11 boundary fixtures (all 4 tiers)

---

## ⚠️ CRITICAL RULES (learned the hard way)
1. **NEVER perform string surgery on assembled text** — corrections on STRUCTURED DATA before assembly
2. **NEVER relax checks** — failed checks → corrective actions
3. **NEVER fabricate examples** — use verbatim text from actual files
4. **Hardcoded per-venue config abandoned completely** — everything discovered at runtime
5. **Queue scan by LIST** (ID: `1000410000000733`), not assignee
6. **Git branch**: `storied`. Never touch `main`.
7. **Fail-closed**: infrastructure unavailable = FAILURE, never skip
8. **TODO comments go on separate lines** — NEVER inside string literals
9. **Tier computation uses evidence_strength (unique QIDs)** — NOT labels or verified_pois count
10. **Artifacts ARE committed** — "status: completed" is a container claim, not evidence
11. **NEVER claim PASS without QA exit 0** — report inflation is a critical violation

---

## 🐳 DOCKER SERVICES (relevant subset)
```
development-tour-generator-1:5000     # generate_tour_text.py + service
development-postgres-2-1:5432         # PostgreSQL (admin:password123)
development-tour-orchestrator-1:5002  # tour_orchestrator_service.py
```

---

## 📊 GIT LOG (recent, on `storied` branch)
```
e2c6ebd Items 4+5: Chagall regenerated + exact-stem story_elements siblings
16e0c06 B7+B8+B3: runtime venue-context, evidence_strength=unique QIDs, tier fixtures
1ea1124 B1 complete: fix venue-self-reference + SPARQL title capitalization + Uffizi artifact
6ea11dd B1: fix G4 matcher false positives (historical periods + venue terms + paragraph-split)
6003af5 B4+B5: fix TODO-in-string + fix tier computation
d0f2def Phase 2 artifact: Chagall rich-tier tour
663e469 BLOCKING 1+3: Phase 2 acceptance artifacts
0a11d91 BLOCKING 2: delete legacy fail-open branch
```
