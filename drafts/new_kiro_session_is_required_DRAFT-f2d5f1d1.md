# DRAFT (unpromoted) — our_bug `f2d5f1d16dae778c` — proposed fix

> **This is a DRAFT emitted by failure_triage.py (LOCAL-804, D723).** It is NOT a released task: the filename is `new_kiro_session_is_required_DRAFT-…`, deliberately outside the dispatcher glob (`new_kiro_session_is_required_LOCAL-*.md`), and it is never added to RELEASED.txt. LEAD reviews the evidence below and, if it is real, renames this to a LOCAL ticket to promote it.

## Evidence

- signature: `f2d5f1d16dae778c`
- class: our_bug (severity 3)
- occurrences: **1** in the last 7 days (score 3.0)
- first seen 2026-10-28 14:29 UTC · last seen 2026-10-28 14:29 UTC
- sources: failure_events
- services: orchestrator
- surfaces: generate
- error_code: `generation_failed`
- exception_type: `Exception`
- example message (redacted): Tour generation failed for […] — no stops could be generated (all filtered or knowledge insufficient).

## Proposed fix area

The tour-generator produced no tour for these requests (`generation_failed` / generator job error). Start in `generate_tour_text_service.py` (job lifecycle / clean-fail path) and the orchestrator's generation call; confirm the structured refusal is recorded and the job's `error` JSONB is populated so the next triage has a reason, not just 'failed'.

## Suggested next steps for the promoted session

1. Reproduce from the evidence above (group by this signature in `failure_events` / `generator_jobs`).
2. Write a red test that captures the failure, then fix it.
3. On merge, set `resolved_by` for this signature via `failure_report.py --mark <signature> our_bug LOCAL-NNN`.

