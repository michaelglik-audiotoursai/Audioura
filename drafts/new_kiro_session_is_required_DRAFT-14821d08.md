# DRAFT (unpromoted) — our_bug `14821d0841704007` — proposed fix

> **This is a DRAFT emitted by failure_triage.py (LOCAL-804, D723).** It is NOT a released task: the filename is `new_kiro_session_is_required_DRAFT-…`, deliberately outside the dispatcher glob (`new_kiro_session_is_required_LOCAL-*.md`), and it is never added to RELEASED.txt. LEAD reviews the evidence below and, if it is real, renames this to a LOCAL ticket to promote it.

## Evidence

- signature: `14821d0841704007`
- class: our_bug (severity 3)
- occurrences: **1** in the last 7 days (score 3.0)
- first seen 2026-10-28 15:10 UTC · last seen 2026-10-28 15:10 UTC
- sources: failure_events
- services: orchestrator
- surfaces: generate
- error_code: `—`
- exception_type: `Exception`
- example message (redacted): Text-generation abandoned after 241 polls — absolute 40-minute cap. The generator job was asked to stop. (ran 40.1 min, last progress 0.2 min ago.)

## Proposed fix area

An unhandled `Exception` reached the failure recorder for service `orchestrator` on surface `generate`. Find the raising call site from the recorded frames and add handling + a test.

## Suggested next steps for the promoted session

1. Reproduce from the evidence above (group by this signature in `failure_events` / `generator_jobs`).
2. Write a red test that captures the failure, then fix it.
3. On merge, set `resolved_by` for this signature via `failure_report.py --mark <signature> our_bug LOCAL-NNN`.

