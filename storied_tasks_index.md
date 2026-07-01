# Storied Release Tasks Index

Master index of all 95 Storied release tasks (S1–S95), organized into 7 groups. This file tracks task ownership, target delivery week, output artifacts, and completion status for the Storied narrative tour engine release.

---

## Group 1: Spine & Content (S1–S20)

| # | Name | Artifact | Owner | Week | Status |
|---|------|----------|-------|------|--------|
| S1 | Create spine template file for museum tours | templates/spine_museum.txt | Services Kiro | W1 | |
| S2 | Create spine template files for walking, restaurant, book types | templates/spine_*.txt | Services Kiro | W1 | |
| S3 | Write spine_generator.py — call OpenAI with spine template | spine_generator.py | Services Kiro | W1 | |
| S4 | Wire spine into generate_tour_text.py (STORIED_MODE gate) | generate_tour_text.py | Services Kiro | W1 | |
| S5 | Write fetch_wikipedia_summary() in rag_retriever.py | rag_retriever.py | Services Kiro | W1 | |
| S6 | Write fetch_wikidata_facts() in rag_retriever.py | rag_retriever.py | Services Kiro | W1 | |
| S7 | Wire RAG into spine generation (enrich unique_angle) | spine_generator.py | Services Kiro | W1 | |
| S8 | Write cost_tracker.py — per-tour OpenAI cost logging | cost_tracker.py | Services Kiro | W1 | |
| S9 | Add spine quality scorer — automated rubric check | spine_quality_scorer.py | Services Kiro | W2 | |
| S10 | Write narrative_weaver.py — expand spine into narration | narrative_weaver.py | Services Kiro | W2 | |
| S11 | Integrate plant/callback into narration text | narrative_weaver.py | Services Kiro | W2 | |
| S12 | Write cliffhanger injector for stop transitions | narrative_weaver.py | Services Kiro | W2 | |
| S13 | Add emotional-beat tone enforcement to narration | narrative_weaver.py | Services Kiro | W2 | |
| S14 | Write tour_content_validator.py — structural checks | tour_content_validator.py | Services Kiro | W2 | |
| S15 | Integrate unique_angle into Phase 3B descriptions | generate_tour_text.py | Services Kiro | W2 | |
| S16 | Perspective layer — Artist's View (NEW ARCHITECTURE, not Aug 1) | N/A | Services Kiro | — | |
| S17 | Perspective layer — Historian's View (NEW ARCHITECTURE) | N/A | Services Kiro | — | |
| S18 | Perspective layer — Local's View (NEW ARCHITECTURE) | N/A | Services Kiro | — | |
| S19 | Write tour_cache_layer1.py — spine cache by venue+stops | tour_cache_layer1.py | Services Kiro | W1 | |
| S20 | Wire tour_cache_layer1.py into generate_tour_text() | generate_tour_text.py | Services Kiro | W2 | |

**Subtotal: 20 tasks**

---

## Group 2: De-repetition & Directions (S21–S40)

| # | Name | Artifact | Owner | Week | Status |
|---|------|----------|-------|------|--------|
| S21 | Define story-type taxonomy JSON file | story_type_taxonomy.json | Services Kiro | W1 | |
| S22 | Write assign_story_types() in story_type_assigner.py | story_type_assigner.py | Services Kiro | W1 | |
| S23 | Build forbidden-phrase regex list in derepetition_guard.py | derepetition_guard.py | Services Kiro | W1 | |
| S24 | Write rewrite_flagged_phrases() using GPT | derepetition_guard.py | Services Kiro | W2 | |
| S25 | Integrate derepetition into narration pipeline | narrative_weaver.py | Services Kiro | W2 | |
| S26 | Write cross-stop repetition detector | derepetition_guard.py | Services Kiro | W2 | |
| S27 | Add per-stop uniqueness scorer | derepetition_guard.py | Services Kiro | W2 | |
| S28 | Write transition_writer.py — inter-stop connectors | transition_writer.py | Services Kiro | W2 | |
| S29 | Integrate transitions into final tour output | generate_tour_text.py | Services Kiro | W2 | |
| S30 | Fix fabricated directions — generate_real_directions() | directions_generator.py | Services Kiro | W2 | |
| S31 | Write coordinate_validator.py — verify POI coordinates | coordinate_validator.py | Services Kiro | W2 | |
| S32 | Integrate real directions into walking tour output | generate_tour_text.py | Services Kiro | W2 | |
| S33 | Add indoor navigation mode for museum tours | directions_generator.py | Services Kiro | W2 | |
| S34 | Write directions quality check (no fabricated distances) | directions_generator.py | Services Kiro | W2 | |
| S35 | Add direction caching (same route = same directions) | directions_generator.py | Services Kiro | W2 | |
| S36 | Write OSRM/Mapbox fallback for walking directions | directions_generator.py | Services Kiro | W3 | |
| S37 | Integrate emotional-arc progression into transitions | transition_writer.py | Services Kiro | W3 | |
| S38 | Add callback references to transition text | transition_writer.py | Services Kiro | W3 | |
| S39 | Write full-tour coherence scorer | tour_content_validator.py | Services Kiro | W3 | |
| S40 | Integration test: full pipeline with derepetition + directions | tests/ | Services Kiro | W3 | |

**Subtotal: 20 tasks**

---

## Group 3: Personalization (S41–S46)

| # | Name | Artifact | Owner | Week | Status |
|---|------|----------|-------|------|--------|
| S41 | Design persona schema JSON | persona_schema.json | Services Kiro | W2 | |
| S42 | Write persona_manager.py — CRUD operations | persona_manager.py | Services Kiro | W2 | |
| S43 | Write persona_prompt_modifier.py — inject persona into prompts | persona_prompt_modifier.py | Services Kiro | W3 | |
| S44 | DB migration: create user_personas table | migration/ | Services Kiro | W3 | |
| S45 | Add POST/GET /user/persona endpoints | tour-generator service | Services Kiro | W3 | |
| S46 | Wire persona lookup into generate_tour_text() | generate_tour_text.py | Services Kiro | W3 | |

**Subtotal: 6 tasks**

---

## Group 4: Sharing & Referral (S47–S52)

| # | Name | Artifact | Owner | Week | Status |
|---|------|----------|-------|------|--------|
| S47 | Write generate_shareable_tour_id() in tour_sharing.py | tour_sharing.py | Services Kiro | W3 | |
| S48 | DB migration: create shared_tours table | migration/ | Services Kiro | W3 | |
| S49 | Add POST /tour/{id}/share endpoint | tour-sharing service | Services Kiro | W3 | |
| S50 | Add GET /tour/{tour_id} endpoint — retrieve shared tour | tour-sharing service | Services Kiro | W3 | |
| S51 | Write referral_tracker.py — track share opens | referral_tracker.py | Services Kiro | W3 | |
| S52 | Add referral analytics endpoint GET /referrals/{user_id} | tour-sharing service | Services Kiro | W3 | |

**Subtotal: 6 tasks**

---

## Group 5: Attestation (S53–S58)

| # | Name | Artifact | Owner | Week | Status |
|---|------|----------|-------|------|--------|
| S53 | Write attestation_verifier.py — log-only validator | attestation_verifier.py | Services Kiro | W3 | |
| S54 | Add Google Play Integrity verification call | attestation_verifier.py | Services Kiro | W3 | |
| S55 | Add Apple App Attest verification call | attestation_verifier.py | Services Kiro | W3 | |
| S56 | Wire attestation into gateway (log-only mode) | api-gateway/main.py | Services Kiro | W3 | |
| S57 | Add attestation metrics/logging dashboard | attestation_verifier.py | Services Kiro | W3 | |
| S58 | Write attestation_enforce_gate.py (NOT activated for Aug 1) | attestation_enforce_gate.py | Services Kiro | W3 | |

**Subtotal: 6 tasks**

---

## Group 6: Integration & QA (S59–S80)

| # | Name | Artifact | Owner | Week | Status |
|---|------|----------|-------|------|--------|
| S59 | Add Storied env vars to Dockerfiles/docker-compose | Dockerfiles | Services Kiro | W3 | |
| S60 | Write storied_smoke_test.py — E2E smoke test | storied_smoke_test.py | Services Kiro | W3 | |
| S61 | Write data_safety_storied_delta.md — Play Store update | data_safety_storied_delta.md | Services Kiro | W3 | |
| S62 | Write play_store_storied_delta.md — listing changes | play_store_storied_delta.md | Services Kiro | W3 | |
| S63 | Write app_privacy_storied_delta.md — Apple privacy | app_privacy_storied_delta.md | Services Kiro | W3 | |
| S64 | Regression test: STORIED_MODE=false produces identical output | tests/ | Services Kiro | W4 | |
| S65 | Regression test: compare against chagall_current_tour.txt | tests/ | Services Kiro | W4 | |
| S66 | Performance benchmark: Storied tour vs current (time + cost) | tests/ | Services Kiro | W4 | |
| S67 | Add cost ceiling logger (log, never abort if >$0.15) | cost_tracker.py | Services Kiro | W4 | |
| S68 | Write storied_version_constants.py | storied_version_constants.py | Services Kiro | W3 | |
| S69 | Add SERVICE_VERSION to all modified service files + health | services | Services Kiro | W4 | |
| S70 | Write storied_changelog.md — user-facing feature list | storied_changelog.md | Services Kiro | W4 | |
| S71 | Write storied_launch_checklist.md — Aug 1 gate checklist | storied_launch_checklist.md | Services Kiro | W4 | |
| S72 | Write storied_rollback_plan.md — 3-tier rollback procedure | storied_rollback_plan.md | Services Kiro | W4 | |
| S73 | Write storied_monitoring_alerts.md — post-launch monitoring | storied_monitoring_alerts.md | Services Kiro | W4 | |
| S74 | Write API contract doc for new/changed endpoints | storied_api_contract.md | Services Kiro | W4 | |
| S75 | Load test: 10 concurrent Storied tours | tests/ | Services Kiro | W4 | |
| S76 | Security audit: verify no new auth bypasses | tests/ | Services Kiro | W4 | |
| S77 | DB migration: add spine_json column to audio_tours | migration/ | Services Kiro | W4 | |
| S78 | DB migration: add cost_usd column to audio_tours | migration/ | Services Kiro | W4 | |
| S79 | Flip STORIED_MODE=true in committed config | config | Services Kiro | W4 | |
| S80 | Tag Storied release commit + storied_handoff_for_mobile.md | tag + doc | Services Kiro | W4 | |

**Subtotal: 22 tasks**

---

## Group 7: Orchestrator & Operations (S81–S95)

| # | Name | Artifact | Owner | Week | Status |
|---|------|----------|-------|------|--------|
| S81 | Add /generate-storied-tour endpoint to orchestrator | tour_orchestrator_service.py | Services Kiro | W4 | |
| S82 | Add storied tour type to gateway routes | gateway_routes.yaml | Services Kiro | W4 | |
| S83 | Add deep-link resolution GET /resolve/tour/{share_id} | tour-id-resolution service | Services Kiro | W4 | |
| S84 | Write storied_deployment_runbook.md — deploy procedure | storied_deployment_runbook.md | Services Kiro | W4 | |
| S85 | Update killswitch to cover new Storied services | killswitch-function/main.py | Services Kiro | W4 | |
| S86 | Add Storied cost to billing budget alert | GCP budget | Michael | W4 | |
| S87 | Write storied_known_issues.md — known limitations | storied_known_issues.md | Services Kiro | W4 | |
| S88 | Update remind_Services_ai.md with Storied context | remind_Services_ai.md | Services Kiro | W4 | |
| S89 | Write agent coordination doc for Storied handoff | agent_coordination_storied.md | Services Kiro | W4 | |
| S90 | Pre-submission QA pass on all Storied endpoints | tests/ | Services Kiro | W4 | |
| S91 | Write storied_test_matrix.md — manual test cases | storied_test_matrix.md | Services Kiro | W4 | |
| S92 | Write storied_tasks_index.md — this file | storied_tasks_index.md | Services Kiro | W4 | |
| S93 | Final documentation review + link check | docs | Services Kiro | W4 | |
| S94 | Merge storied into main (when released) | git | Michael | W4 | |
| S95 | Final gate: run launch checklist, mark PASS, handoff | checklist | Services Kiro | W4 | |

**Subtotal: 15 tasks**

---

## Summary

| Group | Range | Tasks |
|-------|-------|-------|
| 1. Spine & Content | S1–S20 | 20 |
| 2. De-repetition & Directions | S21–S40 | 20 |
| 3. Personalization | S41–S46 | 6 |
| 4. Sharing & Referral | S47–S52 | 6 |
| 5. Attestation | S53–S58 | 6 |
| 6. Integration & QA | S59–S80 | 22 |
| 7. Orchestrator & Operations | S81–S95 | 15 |
| **Total** | **S1–S95** | **95** |
