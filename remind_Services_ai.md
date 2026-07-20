# Services Kiro Context Reminder
## Who you are
🔧 **SERVICES KIRO** — **CRITICAL**: Always start ALL replies with "🔧 SERVICES KIRO -"

**UPDATED**: 2026-07-13 (B6 DELIVERED — `b8d5d96`+`ad5208d` pushed. All 4 items proven in committed artifact. Awaiting LEAD re-verification.)

1. You are **Services Kiro** responsible for all Docker services in `C:\Users\micha\eclipse-workspace\AudioTours\development\`. You have blanket approval to change code, run Python programs, start/stop Docker services without waiting for approval.
2. You maintain this file and update it after significant changes.
3. Task management via ClickUp (Storied space, list 🟦 Services — Kiro, ID `1000410000000733`).

---

## 🚨 CRITICAL IDENTITY RULES
- **ALWAYS** prefix every reply with "🔧 SERVICES KIRO -"
- **GIT BRANCH**: `storied` (off `main` = `beta-2.1.1+18`). **Never touch `main`.**
- **VERSION**: `2.2.0+1` (distinct from Beta's 2.1.x)
- **LAST GIT STATE**: `ad5208d` — B6 pilot (child of `b8d5d96` code commit). work_stories WRITE+READ, elements→generation per-status wiring, i-con delta all proven.
- **NEXT ACTION ON RECOVERY**: Read this file, then run the full QUEUE PROTOCOL (see 📋 QUEUE PROTOCOL below). SQ4 is CLOSED (LEAD acceptance `1000410000006988`) — do not re-open. Current open work is in the 🟦 list (as of 2026-07-14: `wdvrdawkxp` PALAIS-FIX hardening, then `wdvrdawkxq` evidence-not-requirement design).
- **WORKFLOW**: Blanket approval for all service changes. One task = one commit = one review.
- **NEVER perform string surgery on assembled text** — corrections on STRUCTURED DATA only.
- **NEVER fabricate examples** — use verbatim from actual files.
- **Report accurately** — never claim PASS without running the actual check.
- **NEVER claim PASS without QA exit 0** — report inflation is a critical violation; show verbatim exit codes.

---

## 🔥 IMMEDIATE WORK: B6 Hard Gate (Michael's ruling `1000410000006774`)

**Source:** Michael's ruling (comment `1000410000006774`) + LEAD verdict (comment `1000410000006768`)
**Context:** SQ4 merge machinery ACCEPTED (B1-B5 fixed). Criterion 2 MET via documented `origin` element + `legend` guardrail. B6 descope DENIED — all four items required in ONE commit.

### Four B6 deliverables (ALL required together):

**1. `work_stories` live WRITE** — pilot JSON must carry evidence of the store record (not just log-line claims; actual `[work_stories] STORED` evidence in the artifact).

**2. `work_stories` live cache-HIT READ** — a warm-cache pilot run proving the read serves cached elements with **zero SERP queries**, in the committed artifact. Strategy: run pilot TWICE — first run mines fresh (proves WRITE), second run on same work hits cache (proves READ with `story_mining_status: cache_only`, `total_queries: 0`).

**3. Elements→generation wiring** — scored elements reach `generate_tour_text`, with per-status phrasing:
- `documented` → state as fact (no attribution needed)
- `reported` → inline attribution ("According to [source]…")
- `legend` → "The story goes that…"
- `disputed` → expose both sides with sources

**4. i-con delta** — `stop_metrics` i_con rows for the SQ4-generated Matisse + Chagall stops vs the LOCKED advisory baseline:
- Matisse: 3.81
- Uffizi: 3.66
- Chagall: 3.99
- Chagall cache-hit: 3.51

### Implementation plan:
1. Modify `generate_tour_text_service.py` (or the generation prompt) to accept ranked elements and include per-status instructions
2. Modify pilot driver to: (a) run fresh mining, (b) capture STORED evidence, (c) run a second time on same work to prove cache-HIT read with zero SERP, (d) run generation with elements, (e) run i-con evaluator, (f) capture stop_metrics
3. Commit code + BOTH pilot artifacts (fresh + warm)
4. Pilot as CHILD commit of code commit (N1 procedural rule)

### Standing gates:
- Clean `code_sha` (pilot as child commit)
- Per-tour Serper query-count + cost logged
- D2: full per-query domains+tiers for ALL results
- QA exit 0 on element-backed generation

### Key files to modify:
- `generate_tour_text_service.py` — inject story elements into generation prompt
- `generate_tour_text.py` — accept elements, format per-status instructions
- `run_pilot_w7_wired.py` — add warm-cache second run + generation + i-con evaluation
- `icon_evaluator.py` — already exists, just needs to be called on generated text

---

## 📋 ACCEPTED (not to be re-litigated):
- B1-B5 merge fixes (same-type-only gate, connected-components, no cross-type merge, no blob)
- RS1/RS2 legend guardrail (single fluid cut stays at `legend`)
- RS6 E1 fired (English-series query generated)
- D2 per-query domains present
- Criterion 2 MET (documented `origin` element + legend guardrail)
- Accuracy: documented element is `origin` ("Blue Nude II was conceived during Matisse's time in Nice…" from wiki+centrepompidou), NOT `date`

---

## 📋 TASK STATUS

| Task | Status | Next |
|------|--------|------|
| wdvrdawdje (Story Quality) | **ACTIVE — SQ4 CIL cycle 3, B6 DELIVERED (awaiting LEAD)** | LEAD re-verifies B6 from committed artifacts |
| wdvrdawcyx (Generic Grounding) | Phase 2 CLOSED, conditions met | Phase 3 approach post (after SQ4 closes) |

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
- **openai library in container is v0.x** — use `openai.ChatCompletion.create()` not `openai.OpenAI()`

---

## 📊 GIT LOG (recent, on `storied` branch)
```
ad5208d B6 pilot: work_stories WRITE+READ proven, elements→generation wired (per-status), i-con delta +0.52/+1.01/+0.16 vs baseline
b8d5d96 B6: elements→generation wiring (per-status phrasing) + B6 pilot driver + B6 wiring fixture
931f7c4 SQ4 pilot: B1-B5 fix proven — 18 distinct elements, no single-blob, documented date cluster + legend guardrail
6aefe0a SQ4 B1-B5 fix: same-type-only merge gate, connected-components union, improved LLM prompt with negative examples, cross-type separation fixtures
fcbf68d SQ4 Commit 1: LLM merge pass (M1) + E1 english-series query + merge fixtures (RS2 legend boundary, RS3 real 1952 cluster)
39aeae9 D1+D2+D3+D5: domain diversity cap, pilot includes fetch_log+per-query tiers, museedevence.fr seeded, date validation in W7
327eec5 Q1+Q3+code_sha: person picker skips artist, english_title query, pilot records git HEAD
3f2e046 W7 wiring: fact_refinement_queries in extract output, execute_fact_refinement orchestration
```

---

## ⚠️ CRITICAL RULES (learned the hard way)
1. **NEVER perform string surgery on assembled text** — corrections on STRUCTURED DATA before assembly
2. **NEVER relax checks** — failed checks → corrective actions
3. **NEVER fabricate examples** — use verbatim text from actual files
4. **Hardcoded per-venue config abandoned completely** — everything discovered at runtime
5. **Queue scan = LIST scan + comment scan, always both** (see 📋 QUEUE PROTOCOL) — checking comments on one task is NOT a queue scan
6. **Git branch**: `storied`. Never touch `main`.
7. **Fail-closed**: infrastructure unavailable = FAILURE, never skip
8. **TODO comments go on separate lines** — NEVER inside string literals
9. **Artifacts ARE committed** — "status: completed" is a container claim, not evidence
10. **NEVER claim PASS without QA exit 0** — report inflation is a critical violation
11. **Pilot as CHILD commit** — code_sha == HEAD, not amend-sibling pattern
12. **Delivered = production call site + wiring fixture** — function-without-callsite is report inflation
13. **Same-type-only merge** — cross-type pairs NEVER candidates (B1 fix)
14. **Report accurately** — name the element the evidence actually supports (documented=origin, not date)
15. **work_stories deferred 3×** → hard gate. No further SQ close until exercised or Michael descopes.

---

## 🐳 DOCKER SERVICES (relevant subset)
```
development-tour-generator-1:5000     # generate_tour_text.py + service
development-postgres-2-1:5432         # PostgreSQL (admin:password123)
development-tour-orchestrator-1:5002  # tour_orchestrator_service.py
```

---

## 📋 QUEUE PROTOCOL (BINDING — Michael's directive 2026-07-14)

**Any invocation — "work on your queue", "check for new directives", "continue", session recovery — means the SAME full protocol. There is no comment-only mode.**

**Step 1 — LIST scan (new tasks):** `clickup_filter_tasks` on list `1000410000000733` (🟦 Services — Kiro). Every task with status `to do` or `in progress` (or bounced back by LEAD) is queue work. New tasks arrive WITHOUT any comment on tasks you already watch — a list scan is the ONLY way to see them.

**Step 2 — Comment scan (new directives on known tasks):** for each open/active task, fetch comments UNPAGINATED, newest-first. Before declaring "no new directives," verify the max comment ID exceeds your own last post ID. Always cite the comment ID you are responding to.

**Step 3 — Execute:** work the highest-priority actionable item (priority order: urgent > high > normal; LEAD bounces outrank new work). Design tasks marked "approach comment BEFORE coding" get a CIL approach comment first, never code. One task = one focused commit → move to 🔵 Claude — Review.

**Step 4 — Report:** list what the LIST scan found (task IDs + statuses) and what the comment scan found (max comment IDs), THEN your action. "Queue is clear" requires evidence of BOTH scans.

**Failure log:** 2026-07-14 — declared "queue clear" after comment-scan-only while 2 new high-priority tasks (`wdvrdawkxp`, `wdvrdawkxq`) sat in the list. This protocol exists because of that miss.

- My last post: `1000410000006790` (update after every post)
