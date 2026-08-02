**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-112
**Branch:** kiro/local112-preference-route-on-storied

# The swipe route is one line away from Michael's phone

Read `SUBMISSION_LOCAL-109.md`, `SUBMISSION_LOCAL-107.md`,
`DECISIONS.md` D24, `remind_Services_ai.md`.

## The situation

LOCAL-109 proved real Dart builds the swipe body correctly and the server
accepts it — then drew the line honestly:

> `Endpoints._localPorts[Service.orchestrator]` hardcodes 5002 … the
> preference route only exists on 5102.

Port 5002 is the shared orchestrator, built from `storied`. LEAD checked:

```
swipe_preference_service.py on storied              YES
register_preference_routes called on storied        0
register_preference_routes called on subscribed     2
```

So the service module is already on `storied`. Only the **registration
line** is missing, because LOCAL-107 was based on `subscribed`.

The consequence: **on Michael's phone every swipe 404s**, and LOCAL-105's
offline queue retries ten times and discards it.

## Scope

1. **Add the registration to `storied`'s `tour_orchestrator_service.py`.**
   Cherry-pick LOCAL-107's one-line change plus its guard test. Do not drag
   across unrelated `subscribed` work.
2. **Confirm it is additive.** These are new routes; nothing existing should
   change behaviour. Show that the orchestrator's existing endpoints respond
   identically before and after.
3. **The guard test must come with it.** LOCAL-107's asserts the route
   responds and fails when the registration is removed. Without it this
   silently unwires again on the next refactor — which is precisely how we
   got here.
4. **Do not rebuild the shared container.** D24: the compose-managed
   containers are the path Michael's phone uses, and he is away. Prove it on
   the tourquality stack built from your branch. LEAD will rebuild the shared
   orchestrator after review.

## Acceptance criteria — live evidence

- `POST /user/<id>/stop-feedback` returns 2xx on a stack built from your
  branch, using the Dart client's exact body shape (`stop_index`, `swipe`,
  `class_details`, `class_historic`, `class_social`, `i_con`).
- Existing orchestrator routes unchanged: pick three and show identical
  status before and after.
- The guard test fails when the registration line is commented out.
- `audioura-*` containers untouched — `docker ps` before and after.

## ⛔ Constraints

No `DELETE FROM audio_tours`. Row count before and after (88 now).
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `STATUS.md`.
Verify `tours-near/43.7009358/7.2683912?radius=50` returns
`[1,12,14,17,21,24,27,28,29]` when you finish.

## PROCESS

Work in YOUR worktree only. Use `tests/db_connection.py`.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` ≥ 1;
(2) `SUBMISSION_LOCAL-112.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file changes, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
