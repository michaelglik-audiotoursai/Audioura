#!/usr/bin/env python3
"""user_stops_flag.py — GCS-KS1. A single env kill switch for user-chosen stops.

WHY THIS EXISTS (D591, Michael 2026-09-24)
------------------------------------------
`storied` HEAD carries two things that must ship separately:
  * the regex fix (19358ae) that stopped every large-museum generation hanging at
    100% CPU — this MUST reach Preview;
  * Igor's user-chosen-stops work (1bb087e and follow-ons) — this must NOT ship
    to any GCloud deploy until Michael approves Igor's test results:
    "only on local Docker before we approve the results of the Igor's test."

Reverting Igor's code to let the regex fix through would lose his work and be a
merge headache when it is finally approved. Instead this module is a runtime gate:
the feature CODE stays exactly as written, but a single environment flag decides
whether a request's user-chosen stops are honoured or ignored.

CONTRACT
--------
``USER_STOPS_ENABLED`` — read from the environment, case-insensitively:
    "true"  -> the feature is ON  (today's behaviour, unchanged)
    unset / anything else -> the feature is OFF (default)

DEFAULT OFF is the whole point: a GCloud service that sets nothing gets the safe
behaviour automatically, so an accidental deploy cannot ship the feature. Local
Docker turns it ON explicitly (USER_STOPS_ENABLED=true in the compose files).

The two callers use exactly two functions:

  user_stops_enabled()         -> bool. Is the feature on right now?

  neutralize_if_disabled(raw, *, request_id=None, field=None, log=print)
                               -> the stops value to actually use.
     When the feature is ON  : returns ``raw`` unchanged.
     When the feature is OFF : returns ``None`` (as if the field were never sent)
        and, IF ``raw`` was non-empty, logs ONE line recording that the field was
        present and ignored, with the count — so we can see whether any installed
        app is still sending it.

The flag is read fresh on every call (never cached at import) so tests can flip it
with ``monkeypatch.setenv`` / ``os.environ`` and a single process can be exercised
both ways. This is deliberate — see tests/test_gcs_ks1_user_stops_killswitch.py.
"""
from __future__ import annotations

import os

# The one and only environment variable that governs the feature. Named as a
# module constant so a test can assert against the name itself (a rename is a
# breaking change that must be caught).
ENV_VAR = "USER_STOPS_ENABLED"


def user_stops_enabled() -> bool:
    """Return True iff USER_STOPS_ENABLED is set to 'true' (case-insensitive).

    Default OFF: unset, empty, or any other value is False. Read fresh every call.
    """
    return os.getenv(ENV_VAR, "false").strip().lower() == "true"


def _count(raw) -> int:
    """Best-effort element count for logging; never raises."""
    try:
        return len(raw)
    except TypeError:
        return 0


def neutralize_if_disabled(raw, *, request_id=None, field=None, log=None):
    """Gate a user-supplied stops value behind the kill switch.

    Args:
        raw: the stops value as it arrived on the request (a list, or None, or
             whatever the client sent). This function does not validate it — that
             is the caller's existing job — it only decides whether it survives.
        request_id: optional id echoed into the log line, so a present-and-ignored
             event can be tied to a specific request.
        field: optional name of the field the value came from (e.g. 'user_stops'
             or 'stops'), recorded in the log line.
        log: the logging callable. Defaults to ``print`` (which the services route
             to stdout), resolved at CALL time so it stays patchable. Injectable so
             tests can capture the line.

    Returns:
        ``raw`` unchanged when the feature is ON.
        ``None`` when the feature is OFF (the request then behaves exactly as if
        no stops field had been sent). When OFF *and* ``raw`` was non-empty, emits
        exactly one log line first.
    """
    if user_stops_enabled():
        return raw

    # Feature OFF. If the client actually sent something, say so — once — so we can
    # tell whether any app in the field is still sending the field. An absent or
    # empty field is a no-op and is not worth a log line.
    if raw:
        emit = log if log is not None else print
        emit(
            f"[USER_STOPS_DISABLED] {ENV_VAR} is off — ignoring user-chosen stops "
            f"present on the request (field={field or 'user_stops'}, "
            f"count={_count(raw)}, request_id={request_id or 'unknown'}). "
            f"Stops will be chosen the normal way."
        )
    return None
