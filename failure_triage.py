#!/usr/bin/env python3
"""failure_triage.py — LOCAL-804 / D723: nightly failure triage → ranked report
→ draft task files (the self-improvement loop).

Michael (D723): "1) record, 2) analyze, 3) prioritize, 4) fix". LOCAL-785 built
(1) record — `failure_events` (migration 054), `failure_log.record`, the client
FailureReporter — and `failure_report.py` prints the raw groups for LEAD. This
tool is (2) analyze + (3) prioritize + the SEED of (4) fix: it reads the last N
days of recorded failures ACROSS the four places a failure lands, groups them by
a normalised signature, classifies each group (whose fault / what kind), ranks
them, and writes:

  * reports/failure_triage_<date>.md — the top 15 groups with count, first/last
    seen, a REDACTED example, class and suggested owner, plus a dedicated
    "User confusion" section (the screens/actions involved) so Michael gets UI
    fixes from these, not just bug tickets; and
  * drafts/new_kiro_session_is_required_DRAFT-<sig8>.md — a DRAFT task file for
    each of the top 3 `our_bug` groups, with the evidence and a proposed fix
    area. These are DRAFTS: the filename is deliberately NOT the dispatcher glob
    (`new_kiro_session_is_required_LOCAL-*.md`) and they are never added to
    RELEASED.txt. LEAD reviews each, renames the strong ones to a real LOCAL
    ticket, and promotes them.

WHAT IT READS (all four, the complete picture of a night's failures):
  1. failure_events                     — the durable recorder (every surface).
  2. lookup_escalations WHERE tier_found='none'
                                         — genuine "nothing found" absences that
                                           even the dearer tiers could not rescue
                                           (LOCAL-784); a user-confusion signal.
  3. generator_jobs WHERE status IN ('error','failed')
                                         — generator jobs that died (LOCAL-775).
  4. tour_requests WHERE status='failed' — user-visible request failures.

Each source row is normalised to a common shape and grouped by
    signature = sha1(source + service + error_code + exception_type +
                     normalise(message))[:16]
reusing failure_log.normalise_message / compute_signature so "tour 445 failed"
and "tour 446 failed" share one group across ids, numbers and quoted strings.

CLASSIFICATION (rule-based first; D723's five classes):
  our_bug        — an exception/stack, a 5xx, generation_failed, or a generator
                   job that errored: OUR defect, WE fix it.
  external       — an upstream provider failure (Overpass / Wikimedia / OpenAI /
                   Gemini 4xx–5xx, a 402 "out of credit"): handle it, don't own
                   the root cause.
  user_confusion — a client-side error right after a UI action, or an honest
                   refusal the user retried, or a lookup that found nothing:
                   the FIX is a clearer interface (Michael's point).
  expected       — a by-design refusal (e.g. a Free-tier gate): working as
                   intended, no action.
  unknown        — nothing matched; a human should look.
The stored `triage` column (failure_log's own auto/LEAD triage, vocabulary
our_bug|ux|external|absence|unknown) is honoured as the STRONGEST signal when
present and mapped into D723's five classes (ux→user_confusion, absence→
user_confusion, a Free/entitlement refusal→expected). A LEAD override
(triage_source='lead') always wins.

OPTIONAL --llm: one cheap classify call (gpt-4.1-mini) per NEW group only (a
group whose signature is not in reports/.triage_seen.json), to label the
`unknown` leftovers a human would otherwise read. Hard-capped: ≤ $0.02/night and
a $0.05 absolute paid-API ceiling, both enforced before any call; without --llm
NO network call is made and the tool is pure stdlib + psycopg2.

RANK: score = count × severity × recency, with NEW groups floated to the top.
  severity:  our_bug 3 · external 2 · user_confusion 1 · expected 0 · unknown 1
             (a failed-tour event is weighted above a degraded one via the
              source: a tour_requests/generator failure carries severity ≥ its
              class because the user got no tour.)
  recency:   last seen ≤ 1 day → 1.0 · ≤ 7 days → 0.6 · older → 0.3

READ-ONLY: the DB session is set READ ONLY and only SELECTs are issued. No DB
writes, ever. Connection matches every other tool: DATABASE_URL if set, else the
discrete DB_* env; `--db-url` overrides both (GCloud_Storied passes Cloud SQL).

    python3 failure_triage.py                 # last 7 days, Mac DB
    python3 failure_triage.py --days 1
    python3 failure_triage.py --db-url postgresql://… --llm
    python3 failure_triage.py --out-dir /tmp/triage --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

# Reuse the recorder's normalisation so the triage groups exactly match the way
# failures are already signed at record time (one source of truth for "same
# failure"). Fall back to local copies if imported somewhere failure_log is not
# on the path — the logic is identical.
try:
    from failure_log import normalise_message as _normalise_message
except Exception:  # pragma: no cover - defensive import fallback
    _DIGITS_RE = re.compile(r"\d+")
    _HEXID_RE = re.compile(r"\b[0-9a-fA-F]{8}(?:-?[0-9a-fA-F]{4,}){0,4}\b")
    _QUOTED_RE = re.compile(r"""(['"])(?:\\.|(?!\1).)*\1""")
    _WS_RE = re.compile(r"\s+")

    def _normalise_message(message):
        if not message:
            return ""
        s = str(message)
        s = _QUOTED_RE.sub(" ", s)
        s = _HEXID_RE.sub(" ", s)
        s = _DIGITS_RE.sub(" ", s)
        s = s.lower()
        s = _WS_RE.sub(" ", s).strip()
        return s


# ---------------------------------------------------------------------------
# Classes, severity, owners (D723's five-class vocabulary).
# ---------------------------------------------------------------------------

# LOCAL-804B adds `budget` to D723's five classes: a failure whose real root
# cause is the shared stack refusing a paid call because the daily paid-API
# budget / credit ran out (DAILY_PAID_LIMIT_USD, a provider 402 "out of
# credit"). It LOOKS like our_bug ("no stops could be generated") but WE did not
# break — the generator was starved of its paid dependency. Owner is budget/ops,
# not engineering, so it must not float to the top as a defect to code-fix.
CLASSES = ("our_bug", "external", "budget", "user_confusion", "expected",
           "unknown")

_SEVERITY = {
    "our_bug": 3,
    "external": 2,
    "budget": 2,
    "user_confusion": 1,
    "expected": 0,
    "unknown": 1,
}

# Suggested owner per class, for the report's "suggested owner" column.
_OWNER = {
    "our_bug": "LEAD → engineering (fix the defect)",
    "external": "LEAD → resilience (retry/fallback/budget on the provider)",
    "budget": "LEAD → ops/budget (raise or reset DAILY_PAID_LIMIT_USD / top up "
              "the provider credit — NOT an engineering defect)",
    "user_confusion": "LEAD → product/UI (make the interface guide the user)",
    "expected": "none (working as intended)",
    "unknown": "LEAD (triage by hand)",
}

# Map failure_log's stored triage vocabulary into D723's five classes. A stored
# triage is the strongest rule-based signal (it was seeded at record time from
# the LOCAL-774 error_code contract, or set by LEAD).
_STORED_TRIAGE_TO_CLASS = {
    "our_bug": "our_bug",
    "external": "external",
    "ux": "user_confusion",
    "absence": "user_confusion",
    "unknown": "unknown",
}

# error_codes that are a by-design refusal (expected), not a confusion to fix.
_EXPECTED_ERROR_CODES = {
    "free_tier_limit", "free_level_refusal", "tier_limit", "quota_exceeded_free",
    "subscription_required_free", "upgrade_required",
}

# Substrings that name an external provider (used on message/exception/service
# when no stored triage already decided it).
_EXTERNAL_HINTS = (
    "overpass", "wikimedia", "wikipedia", "wikidata", "openai", "gemini",
    "google-search", "polly", "serper", "mapbox", "nominatim", "out of credit",
    "insufficient_quota", "rate limit", "ratelimit", "429", "402",
    "upstream", "provider",
)

# Exception-type substrings that mean a network/provider failure.
_EXTERNAL_EXC_HINTS = (
    "timeout", "connectionerror", "connectionrefused", "socket", "readtimeout",
    "connecttimeout", "sslerror", "httperror", "clientexception", "gaierror",
)

# Substrings that name the daily paid-budget / credit refusal specifically (the
# `budget` class). These sit INSIDE the external family but get their own owner:
# the fix is to top up / raise the cap, not to retry harder or to code a
# fallback. DAILY_PAID_LIMIT_USD is the shared stack's own cap; a provider 402
# "out of credit" is the account running dry.
_BUDGET_HINTS = (
    "daily_paid_limit", "daily_paid_limit_usd", "paid limit", "paid-api limit",
    "budget reached", "budget exceeded", "over budget", "out of credit",
    "insufficient_quota", "insufficient quota", "quota exhausted",
    "payment required",
)


# ---------------------------------------------------------------------------
# Test-traffic detection (LOCAL-804B). The live Mac DB is also where the test
# suites (LOCAL-NNN run_* harnesses, p1-* probes) write their failures — and in
# the first report those DOMINATED (74 of 91 events were `exhibition_closed`
# from tour `test-local365-type`). They are not production failures and must be
# excluded by default; `--include-tests` keeps them for a deliberate audit.
#
# A row is test traffic when its user_id / tour_id / job_id looks synthetic:
#   * a `test` / `TEST` / `test_` / `test-` prefix (test-local365-type,
#     test_local156_fe633157),
#   * a `p1-` prefix (the p1 probe ids),
#   * a bare LOCAL-NNN / local-NNN / localNNN harness id anywhere in it (the
#     run_localNNN_* harnesses tag their traffic with their ticket).
# ---------------------------------------------------------------------------

_TEST_ID_PREFIXES = ("test", "p1-")
# A LOCAL-NNN harness id embedded anywhere (local365, local-156, LOCAL_804, …).
_HARNESS_ID_RE = re.compile(r"\blocal[-_]?\d{2,}\b", re.IGNORECASE)


def _looks_like_test_id(value):
    """True if one id string is a synthetic test/harness id."""
    if not value:
        return False
    s = str(value).strip()
    if not s:
        return False
    low = s.lower()
    for p in _TEST_ID_PREFIXES:
        if low.startswith(p):
            return True
    if _HARNESS_ID_RE.search(low):
        return True
    return False


def is_test_event(ev):
    """True if a normalised event is test / harness traffic, not a real user
    failure. Checks the user_id, tour_id and job_id (any one matching is
    enough), plus an explicit `is_test` flag if a source ever carries one."""
    if ev.get("is_test"):
        return True
    for key in ("user_id", "tour_id", "job_id"):
        if _looks_like_test_id(ev.get(key)):
            return True
    return False


def filter_test_events(events, include_tests=False):
    """Return (kept_events, excluded_count). With include_tests=True nothing is
    dropped (the count is still reported for transparency)."""
    excluded = sum(1 for ev in events if is_test_event(ev))
    if include_tests:
        return list(events), excluded
    return [ev for ev in events if not is_test_event(ev)], excluded


# ---------------------------------------------------------------------------
# Signature.
# ---------------------------------------------------------------------------

def triage_signature(source, service, error_code, exception_type, message):
    """Stable 16-hex group key, scoped by source so a generator job failure and
    a failure_events row for the same message stay distinguishable where it
    matters, yet like messages within a source collapse together."""
    basis = "|".join([
        (source or "").strip().lower(),
        (service or "").strip().lower(),
        (error_code or "").strip().lower(),
        (exception_type or "").strip(),
        _normalise_message(message),
    ])
    return hashlib.sha1(basis.encode("utf-8", "replace")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Redaction — the report must carry NO user text and NO ids beyond tour ids.
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_LONGHEX_RE = re.compile(r"\b[0-9a-fA-F]{8}(?:-?[0-9a-fA-F]{4,}){1,}\b")
_SECRETID_RE = re.compile(r"\b[0-9a-fA-F]{16,}\b")
_QUOTED_RE2 = re.compile(r"""(['"])(?:\\.|(?!\1).)*\1""")


def redact(text, keep_len=200):
    """Make an example string safe to print: strip quoted user text, emails,
    uuids/secret ids and long hex tokens; keep short, tour-id-only context.

    A tour id (tour_123, or a short numeric id attached to 'tour') is allowed —
    the spec permits tour ids. Everything else that looks like a user string or
    an opaque id is removed. The result is truncated so one giant line cannot
    bloat the report.
    """
    if not text:
        return ""
    s = str(text)
    # 1. Remove quoted literals (these are where free-form user text hides).
    s = _QUOTED_RE2.sub("[…]", s)
    # 2. Emails and secret-id/uuid tokens.
    s = _EMAIL_RE.sub("[email]", s)
    s = _LONGHEX_RE.sub("[id]", s)
    s = _SECRETID_RE.sub("[id]", s)
    # 3. Collapse whitespace and truncate.
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > keep_len:
        s = s[:keep_len].rstrip() + "…"
    return s


# ---------------------------------------------------------------------------
# DB connection (read-only intent).
# ---------------------------------------------------------------------------

def _connect(db_url=None):
    import psycopg2
    if db_url:
        conn = psycopg2.connect(db_url, connect_timeout=5)
    else:
        database_url = os.environ.get("DATABASE_URL")
        if database_url:
            conn = psycopg2.connect(database_url, connect_timeout=5)
        else:
            conn = psycopg2.connect(
                host=os.environ.get("DB_HOST", "postgres-2"),
                dbname=os.environ.get("DB_NAME", "audiotours"),
                user=os.environ.get("DB_USER", "admin"),
                password=os.environ.get("DB_PASSWORD", "password123"),
                port=os.environ.get("DB_PORT", "5432"),
                connect_timeout=5,
            )
    # Belt-and-braces: a read-only session so this tool can never mutate the DB,
    # even via a future edit. Harmless if the server ignores it; the queries are
    # SELECT-only regardless.
    try:
        conn.set_session(readonly=True)
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
    return conn


# ---------------------------------------------------------------------------
# Readers — one per source. Each returns a list of normalised event dicts:
#   {source, service, surface, error_code, exception_type, http_status,
#    message, request_text, tour_id, user_id, triage, triage_source, ts}
# request_text/user_id are carried ONLY for grouping/redaction; they are never
# printed raw.
# ---------------------------------------------------------------------------

def _rows_to_dicts(cur, rows):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]


def read_failure_events(conn, since_dt):
    sql = """
        SELECT ts, service, surface, error_code, exception_type, http_status,
               message, request_text, tour_id, user_id, job_id, platform,
               triage, triage_source
        FROM failure_events
        WHERE ts >= %(since)s
    """
    cur = conn.cursor()
    cur.execute(sql, {"since": since_dt})
    out = []
    for r in _rows_to_dicts(cur, cur.fetchall()):
        r["source"] = "failure_events"
        out.append(r)
    cur.close()
    return out


def read_lookup_escalations(conn, since_dt):
    """Only the genuine absences (tier_found='none') — the honest "nothing
    found" that even the dearer tiers could not rescue. A user-confusion signal:
    the user asked for something we could not satisfy as phrased."""
    sql = """
        SELECT ts, kind, category, scope, request, user_id
        FROM lookup_escalations
        WHERE ts >= %(since)s AND tier_found = 'none'
    """
    cur = conn.cursor()
    cur.execute(sql, {"since": since_dt})
    out = []
    for r in _rows_to_dicts(cur, cur.fetchall()):
        out.append({
            "source": "lookup_escalations",
            "service": "lookup",
            "surface": (r.get("kind") or "lookup"),
            "error_code": "no_results_found",
            "exception_type": None,
            "http_status": None,
            # message describes the KIND/category, not the user's text.
            "message": f"no results found for {r.get('kind') or 'lookup'}"
                       f"/{r.get('category') or '?'}",
            "request_text": r.get("request"),
            "tour_id": None,
            "user_id": r.get("user_id"),
            "job_id": None,
            "platform": "server",
            "triage": "absence",
            "triage_source": "auto",
            "ts": r.get("ts"),
        })
    cur.close()
    return out


def read_generator_jobs(conn, since_dt):
    """Generator jobs that died (status error/failed). The error JSONB carries a
    structured refusal (error_code/error_type/message)."""
    sql = """
        SELECT created_at AS ts, status,
               error->>'error_code'  AS error_code,
               error->>'error_type'  AS exception_type,
               error->>'message'     AS message,
               location, tour_type, job_id
        FROM generator_jobs
        WHERE status IN ('error', 'failed')
          AND created_at >= %(since)s
    """
    cur = conn.cursor()
    cur.execute(sql, {"since": since_dt})
    out = []
    for r in _rows_to_dicts(cur, cur.fetchall()):
        out.append({
            "source": "generator_jobs",
            "service": "generator",
            "surface": "generate",
            "error_code": r.get("error_code") or r.get("status"),
            "exception_type": r.get("exception_type"),
            "http_status": None,
            "message": r.get("message") or f"generator job {r.get('status')}",
            "request_text": r.get("location"),
            "tour_id": None,
            "user_id": None,
            "job_id": (str(r["job_id"]) if r.get("job_id") else None),
            "platform": "server",
            "triage": None,  # classify from error_code/status below
            "triage_source": "auto",
            "ts": r.get("ts"),
        })
    cur.close()
    return out


def read_tour_requests(conn, since_dt):
    """User-visible request failures. tour_requests carries only 'failed' with
    no reason (that was the whole point of 054) — so these group as one 'tour
    request failed' signal unless failure_events already has the detail."""
    sql = """
        SELECT COALESCE(finished_at, started_at, created_at) AS ts,
               status, request_string, tour_id
        FROM tour_requests
        WHERE status = 'failed'
          AND COALESCE(finished_at, started_at, created_at) >= %(since)s
    """
    cur = conn.cursor()
    cur.execute(sql, {"since": since_dt})
    out = []
    for r in _rows_to_dicts(cur, cur.fetchall()):
        out.append({
            "source": "tour_requests",
            "service": "orchestrator",
            "surface": "generate",
            "error_code": "tour_request_failed",
            "exception_type": None,
            "http_status": None,
            "message": "tour request failed",
            "request_text": r.get("request_string"),
            "tour_id": (str(r["tour_id"]) if r.get("tour_id") else None),
            "user_id": None,
            "job_id": (str(r["tour_id"]) if r.get("tour_id") else None),
            "platform": "server",
            "triage": None,
            "triage_source": "auto",
            "ts": r.get("ts"),
        })
    cur.close()
    return out


# ---------------------------------------------------------------------------
# Root-cause lookup (LOCAL-804B). A `failure_events` / `generator_jobs` /
# `tour_requests` row often records only the SYMPTOM ("no stops could be
# generated", a reasonless "failed") while the real cause sat in a sibling
# table: the shared stack refused the paid calls because DAILY_PAID_LIMIT_USD
# was reached, or a provider returned 402 "out of credit". The first report
# mis-filed those as `our_bug`. Here we read the paid-API ledger for budget /
# credit refusals and correlate them to reasonless failures by time, so the
# generation failures that were really a starved budget are classed `budget`,
# not a defect for engineering.
#
# These reads stay READ-ONLY and make NO paid call (they only read the ledger
# the meters already wrote).
# ---------------------------------------------------------------------------

# How close (in seconds) a reasonless failure must sit to a budget-refusal
# paid_api_call to be attributed to it. A generation attempt spans a few
# minutes; a window of 15 min on each side links the refusal to the failure it
# caused without reaching across unrelated runs.
_BUDGET_CORRELATION_WINDOW_S = 15 * 60


def read_paid_budget_refusals(conn, since_dt):
    """Budget / credit refusals from the paid-API ledger: a 402 (payment
    required / out of credit) or any row whose detail names the daily paid
    limit. Returns a sorted list of {ts, kind, status, detail_text}. A refusal
    is the durable DB trace of DAILY_PAID_LIMIT_USD / a provider 402 — the thing
    that actually stopped the tour. Best-effort: if the table is missing or the
    query errors, returns []."""
    sql = """
        SELECT ts, kind, status, service, caller, COALESCE(detail::text, '')
        FROM paid_api_calls
        WHERE ts >= %(since)s
          AND (status = 402
               OR status = 429
               OR detail::text ILIKE '%%daily_paid_limit%%'
               OR detail::text ILIKE '%%out of credit%%'
               OR detail::text ILIKE '%%insufficient_quota%%'
               OR detail::text ILIKE '%%payment required%%')
        ORDER BY ts
    """
    out = []
    try:
        cur = conn.cursor()
        cur.execute(sql, {"since": since_dt})
        for ts, kind, status, service, caller, detail_text in cur.fetchall():
            out.append({
                "ts": _as_utc(ts),
                "kind": kind,
                "status": status,
                "service": service,
                "caller": caller,
                "detail_text": detail_text or "",
            })
        cur.close()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return []
    return out


def _is_reasonless_failure(ev):
    """True for a failure whose recorded detail does not itself explain WHY —
    the ones worth a root-cause lookup. A generation_failed / reasonless tour
    request / a generator job error with only 'failed'. We never override a row
    that already names an exception type or an explicit external/expected code;
    those speak for themselves."""
    src = ev.get("source")
    code = (ev.get("error_code") or "").strip().lower()
    if ev.get("exception_type"):
        return False
    if src in ("generator_jobs", "tour_requests"):
        return True
    if src == "failure_events" and code in ("generation_failed", ""):
        return True
    return False


def _nearest_budget_refusal(ts, refusals):
    """Return the budget-refusal dict within the correlation window of ts, or
    None. refusals must be sorted by ts."""
    if ts is None or not refusals:
        return None
    best = None
    best_gap = None
    for r in refusals:
        rts = r.get("ts")
        if rts is None:
            continue
        gap = abs((ts - rts).total_seconds())
        if gap <= _BUDGET_CORRELATION_WINDOW_S and (best_gap is None
                                                    or gap < best_gap):
            best, best_gap = r, gap
    return best


def enrich_root_causes(events, refusals):
    """Annotate reasonless failures with a budget root cause when a paid-API
    budget/credit refusal sits within the correlation window. Adds
    ev['root_cause']='budget' and a short ev['root_cause_detail'] used by the
    classifier and the report. Mutates and returns the list. No-op when there
    are no refusals."""
    if not refusals:
        return events
    for ev in events:
        if ev.get("root_cause"):
            continue
        if not _is_reasonless_failure(ev):
            continue
        hit = _nearest_budget_refusal(_as_utc(ev.get("ts")), refusals)
        if hit is not None:
            ev["root_cause"] = "budget"
            prov = hit.get("kind") or "provider"
            st = hit.get("status")
            ev["root_cause_detail"] = (
                f"paid-API budget/credit refusal ({prov}"
                f"{' ' + str(st) if st else ''}) within "
                f"{_BUDGET_CORRELATION_WINDOW_S // 60} min — "
                f"DAILY_PAID_LIMIT_USD / out-of-credit, not a code defect")
    return events


def read_all(conn, since_dt):
    events = []
    events += read_failure_events(conn, since_dt)
    events += read_lookup_escalations(conn, since_dt)
    events += read_generator_jobs(conn, since_dt)
    events += read_tour_requests(conn, since_dt)
    # Root-cause enrichment: attribute reasonless failures to a budget/credit
    # refusal recorded in the paid-API ledger, so they are not mis-filed as
    # our_bug.
    refusals = read_paid_budget_refusals(conn, since_dt)
    enrich_root_causes(events, refusals)
    return events


# ---------------------------------------------------------------------------
# Classification (rule-based).
# ---------------------------------------------------------------------------

def _is_client_signal(ev):
    """True if an event is a CLIENT-side failure report, not a server trace. The
    app's FailureReporter records with service='app' (user-tracking
    /client-failure), and client rows carry a real device platform
    (android/ios), never 'server'. Either marks genuine client evidence."""
    service = (ev.get("service") or "").strip().lower()
    platform = (ev.get("platform") or "").strip().lower()
    if service == "app":
        return True
    if platform and platform not in ("server", "", "unknown"):
        return True
    return False


def build_confusion_evidence(events):
    """Pre-scan all events for the CLIENT-SIDE evidence that LOCAL-804B requires
    before a reasonless `tour_request_failed` may be called user_confusion:

      * a client FailureReporter event (service='app' / a device platform) for
        the same tour/user — the user actually saw and reported a failure, or
      * a RETRY of the same request — the same request_text or tour_id appears
        more than once, i.e. the user tried again (a confusion signal), not a
        one-off server death.

    Returns a dict of sets used by classify_event:
      {'client_tours', 'client_users', 'retry_requests', 'retry_tours'}.
    Without one of these a `tour_request_failed` is `unknown`, never a guessed
    user_confusion."""
    client_tours, client_users = set(), set()
    req_counts, tour_counts = {}, {}
    for ev in events:
        if _is_client_signal(ev):
            if ev.get("tour_id"):
                client_tours.add(str(ev["tour_id"]))
            if ev.get("user_id"):
                client_users.add(str(ev["user_id"]))
        # Count request-string / tour recurrence to detect a user retry. Only
        # the user-facing request sources count toward a "retry".
        if ev.get("source") in ("tour_requests", "generator_jobs",
                                 "failure_events"):
            rt = _normalise_message(ev.get("request_text")) if ev.get(
                "request_text") else None
            if rt:
                req_counts[rt] = req_counts.get(rt, 0) + 1
            tid = str(ev["tour_id"]) if ev.get("tour_id") else None
            if tid:
                tour_counts[tid] = tour_counts.get(tid, 0) + 1
    return {
        "client_tours": client_tours,
        "client_users": client_users,
        "retry_requests": {k for k, c in req_counts.items() if c >= 2},
        "retry_tours": {k for k, c in tour_counts.items() if c >= 2},
    }


def _has_confusion_evidence(ev, evidence):
    """True if there is client-side evidence that this reasonless request
    failure was a user confusion (a client report for it, or a retry of it)."""
    if not evidence:
        return False
    tid = str(ev["tour_id"]) if ev.get("tour_id") else None
    uid = str(ev["user_id"]) if ev.get("user_id") else None
    if tid and tid in evidence.get("client_tours", ()):
        return True
    if uid and uid in evidence.get("client_users", ()):
        return True
    if tid and tid in evidence.get("retry_tours", ()):
        return True
    rt = _normalise_message(ev.get("request_text")) if ev.get(
        "request_text") else None
    if rt and rt in evidence.get("retry_requests", ()):
        return True
    return False


def classify_event(ev, evidence=None):
    """Return a D723 class for one normalised event. First matching rule wins;
    the order encodes precedence (budget root-cause > LEAD override > stored
    triage > error_code > http/exception > source default).

    `evidence` is the optional dict from build_confusion_evidence; when given it
    gates a reasonless `tour_request_failed` to user_confusion ONLY with a
    client-side signal, else `unknown`."""
    error_code = (ev.get("error_code") or "").strip().lower()
    exc = (ev.get("exception_type") or "").strip().lower()
    message = (ev.get("message") or "").lower()
    service = (ev.get("service") or "").lower()
    http = ev.get("http_status")
    stored = (ev.get("triage") or "").strip().lower()
    stored_source = (ev.get("triage_source") or "").strip().lower()

    # 0. A by-design refusal is EXPECTED regardless of anything else.
    if error_code in _EXPECTED_ERROR_CODES:
        return "expected"
    if "free" in error_code and ("tier" in error_code or "level" in error_code
                                 or "limit" in error_code):
        return "expected"

    # 0b. A budget / credit refusal is the REAL root cause (LOCAL-804B): a row
    #     the ledger-lookup attributed to DAILY_PAID_LIMIT_USD / a provider 402,
    #     or whose own message names the paid-budget refusal. This beats the
    #     generation_failed → our_bug rule so a starved budget is not mis-filed
    #     as a defect for engineering.
    if ev.get("root_cause") == "budget":
        return "budget"
    hay_budget = " ".join([error_code, message, service])
    if any(h in hay_budget for h in _BUDGET_HINTS):
        return "budget"

    # 1. A LEAD override is authoritative.
    if stored_source == "lead" and stored in _STORED_TRIAGE_TO_CLASS:
        return _STORED_TRIAGE_TO_CLASS[stored]

    # 2. Strongest content signals: explicit codes.
    if error_code in ("generation_failed",):
        return "our_bug"
    if error_code == "tour_request_failed":
        # LOCAL-804B: a reasonless "tour request failed" is only user_confusion
        # with a client-side signal (a FailureReporter event for it, or a user
        # retry). Without evidence it is `unknown` — a guess is not a class.
        if _has_confusion_evidence(ev, evidence):
            return "user_confusion"
        return "unknown"
    if error_code in ("no_results_found", "no_matching_places_in_area",
                      "exhibition_not_found", "by_reference_no_material"):
        # The user asked for something we could not satisfy as phrased / that is
        # genuinely not there — a clearer interface is the fix.
        return "user_confusion"

    # 3. An external provider named anywhere in the signal.
    hay = " ".join([error_code, exc, message, service])
    if any(h in hay for h in _EXTERNAL_HINTS):
        return "external"

    # 4. HTTP status: 5xx is our server erring; a 4xx we raised toward a
    #    provider is external (covered by hints above); otherwise skip.
    try:
        status = int(http) if http is not None else None
    except (TypeError, ValueError):
        status = None
    if status is not None and 500 <= status <= 599:
        return "our_bug"

    # 5. A network/timeout-ish exception is external; any OTHER concrete
    #    exception type is a crash in our code (our_bug).
    if exc:
        if any(h in exc for h in _EXTERNAL_EXC_HINTS):
            return "external"
        return "our_bug"

    # 6. Honour a stored auto-triage if it decided something.
    if stored in _STORED_TRIAGE_TO_CLASS and stored != "unknown":
        return _STORED_TRIAGE_TO_CLASS[stored]

    # 7. Source defaults: a reasonless generator job failure with no detail
    #    still means the user got no tour (our_bug). A reasonless tour_request
    #    is handled above (evidence-gated); do not double-default it here.
    if ev.get("source") == "generator_jobs":
        return "our_bug"
    if ev.get("source") == "tour_requests":
        return "unknown"

    return "unknown"


# ---------------------------------------------------------------------------
# Grouping + ranking.
# ---------------------------------------------------------------------------

def recency_weight(last_seen, now):
    if last_seen is None:
        return 0.3
    age = now - last_seen
    if age <= timedelta(days=1):
        return 1.0
    if age <= timedelta(days=7):
        return 0.6
    return 0.3


def _as_utc(dt):
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def group_events(events, evidence=None):
    """Group normalised events by triage_signature. Each group carries count,
    first/last seen, the newest example, the set of surfaces/sources, and a
    per-group class (the mode of its events' classes, our_bug-biased).

    `evidence` is the optional client-confusion evidence dict; when not given it
    is computed from `events` so a reasonless tour_request_failed is still
    gated. Pass a prepared dict to control it in tests."""
    if evidence is None:
        evidence = build_confusion_evidence(events)
    groups = {}
    for ev in events:
        ev = dict(ev)
        ev["ts"] = _as_utc(ev.get("ts"))
        ev["_class"] = classify_event(ev, evidence)
        sig = triage_signature(ev.get("source"), ev.get("service"),
                               ev.get("error_code"), ev.get("exception_type"),
                               ev.get("message"))
        g = groups.get(sig)
        if g is None:
            g = {
                "signature": sig,
                "count": 0,
                "first_seen": ev["ts"],
                "last_seen": ev["ts"],
                "example": ev,
                "surfaces": set(),
                "sources": set(),
                "services": set(),
                "class_votes": {},
            }
            groups[sig] = g
        g["count"] += 1
        if ev["ts"] is not None:
            if g["first_seen"] is None or ev["ts"] < g["first_seen"]:
                g["first_seen"] = ev["ts"]
            if g["last_seen"] is None or ev["ts"] > g["last_seen"]:
                g["last_seen"] = ev["ts"]
                g["example"] = ev  # newest example
        if ev.get("surface"):
            g["surfaces"].add(ev["surface"])
        if ev.get("source"):
            g["sources"].add(ev["source"])
        if ev.get("service"):
            g["services"].add(ev["service"])
        g["class_votes"][ev["_class"]] = g["class_votes"].get(ev["_class"], 0) + 1

    # Resolve each group's class. A budget root cause wins first: the whole
    # point of LOCAL-804B is that a starved-budget failure must NOT be filed as
    # an engineering defect. After that our_bug wins any tie (a real defect
    # hiding in a mixed group must not be masked), then by vote count, then
    # severity.
    for g in groups.values():
        votes = g["class_votes"]
        if votes.get("budget"):
            g["class"] = "budget"
        elif votes.get("our_bug"):
            g["class"] = "our_bug"
        else:
            g["class"] = max(votes.items(),
                             key=lambda kv: (kv[1], _SEVERITY.get(kv[0], 0)))[0]
    return list(groups.values())


def score_group(g, now):
    sev = _SEVERITY.get(g["class"], 1)
    return g["count"] * sev * recency_weight(g["last_seen"], now)


def rank_groups(groups, now, seen_signatures):
    """NEW groups (not in seen_signatures) float to the top; within new and
    within known, sort by score then count. Returns the list sorted in place."""
    for g in groups:
        g["score"] = score_group(g, now)
        g["is_new"] = g["signature"] not in seen_signatures
    groups.sort(key=lambda g: (g["is_new"], g["score"], g["count"]),
                reverse=True)
    return groups


# ---------------------------------------------------------------------------
# Optional LLM classify (one cheap call per NEW group; hard cost cap).
# ---------------------------------------------------------------------------

# gpt-4.1-mini pricing (USD per token) — small, and we send <400 tokens total
# per call, so one call is well under a tenth of a cent. The caps below are the
# real guard; the estimate only has to be in the right ballpark.
_LLM_MODEL = "gpt-4.1-mini"
_LLM_COST_IN = 0.40 / 1_000_000
_LLM_COST_OUT = 1.60 / 1_000_000
_LLM_NIGHT_CAP = 0.02   # ≤ $0.02/night (spec)
_LLM_ABS_CAP = 0.05     # absolute paid-API ceiling (spec)


def _estimate_call_cost(prompt_chars):
    # ~4 chars/token; assume ≤ 40 output tokens for a one-word class.
    in_tokens = max(1, prompt_chars // 4)
    return in_tokens * _LLM_COST_IN + 40 * _LLM_COST_OUT


def llm_classify_unknowns(groups, budget_night=_LLM_NIGHT_CAP,
                          abs_cap=_LLM_ABS_CAP, caller=None):
    """For each NEW group currently classed 'unknown', spend one cheap call to
    label it. Pure best-effort: any failure leaves the rule-based class. Returns
    the total estimated USD spent. `caller(prompt)->str` is injectable for
    tests; by default it calls OpenAI if OPENAI_API_KEY is set."""
    spent = 0.0
    cap = min(budget_night, abs_cap)
    call = caller or _default_llm_caller()
    if call is None:
        return 0.0
    for g in groups:
        if not g.get("is_new") or g["class"] != "unknown":
            continue
        ex = g["example"]
        prompt = _classify_prompt(ex)
        est = _estimate_call_cost(len(prompt))
        if spent + est > cap:
            break  # stop BEFORE exceeding the cap
        try:
            label = (call(prompt) or "").strip().lower()
        except Exception:
            continue
        spent += est
        if label in CLASSES:
            g["class"] = label
            g["llm_labelled"] = True
    return spent


def _classify_prompt(ex):
    # Redacted inputs only — never the user's raw text.
    return (
        "Classify this software failure into exactly one of: our_bug, external, "
        "user_confusion, expected, unknown. Reply with the single word only.\n"
        f"service={ex.get('service')}\nsurface={ex.get('surface')}\n"
        f"error_code={ex.get('error_code')}\n"
        f"exception_type={ex.get('exception_type')}\n"
        f"message={redact(ex.get('message'), 160)}\n"
    )


def _default_llm_caller():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    def _call(prompt):
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            resp = client.chat.completions.create(
                model=_LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=5, temperature=0,
            )
            return resp.choices[0].message.content
        except Exception:
            return None

    return _call


# ---------------------------------------------------------------------------
# Report + draft rendering.
# ---------------------------------------------------------------------------

def _fmt_ts(dt):
    if dt is None:
        return "?"
    try:
        return _as_utc(dt).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(dt)


def _example_line(g):
    ex = g["example"]
    code = ex.get("error_code") or (f"HTTP {ex['http_status']}"
                                    if ex.get("http_status") else "—")
    exc = f" · exc={ex['exception_type']}" if ex.get("exception_type") else ""
    msg = redact(ex.get("message"), 200)
    tour = f" · tour={ex['tour_id']}" if ex.get("tour_id") else ""
    rc = (f"\n      root cause: {ex['root_cause_detail']}"
          if ex.get("root_cause_detail") else "")
    return f"error_code={code}{exc}{tour}\n      message: {msg or '—'}{rc}"


def render_report(groups, now, days, top=15, excluded_tests=0,
                  include_tests=False):
    ranked = groups[:top]
    total_events = sum(g["count"] for g in groups)
    lines = []
    date_str = now.strftime("%Y-%m-%d")
    lines.append(f"# Failure triage — {date_str} (last {days} day"
                 f"{'s' if days != 1 else ''})")
    lines.append("")
    lines.append(f"_Generated {now.strftime('%Y-%m-%d %H:%M UTC')} by "
                 f"failure_triage.py (LOCAL-804/804B, D723). Read-only; no DB "
                 f"writes._")
    lines.append("")
    lines.append(f"- **{len(groups)}** distinct failure signatures, "
                 f"**{total_events}** events total.")
    by_class = {}
    for g in groups:
        by_class[g["class"]] = by_class.get(g["class"], 0) + g["count"]
    cls_summary = ", ".join(f"{c}={by_class.get(c, 0)}" for c in CLASSES)
    lines.append(f"- By class: {cls_summary}.")
    new_ct = sum(1 for g in groups if g.get("is_new"))
    lines.append(f"- **{new_ct}** signatures are new since the last run "
                 f"(floated to the top).")
    # LOCAL-804B: be explicit about test traffic so the reader knows the counts
    # above are production, not the test-suite noise that dominated the first
    # report.
    if include_tests:
        lines.append(f"- **test traffic INCLUDED** (--include-tests): "
                     f"{excluded_tests} test/harness events are part of the "
                     f"counts above.")
    else:
        lines.append(f"- {excluded_tests} test/harness events excluded "
                     f"(test/TEST/p1- ids, LOCAL-NNN harnesses); run with "
                     f"`--include-tests` to audit them.")
    lines.append("")
    lines.append("## Top failure groups")
    lines.append("")
    if not ranked:
        lines.append("_No failures recorded in this window._")
    for i, g in enumerate(ranked, 1):
        new = " **[NEW]**" if g.get("is_new") else ""
        llm = " _(llm-labelled)_" if g.get("llm_labelled") else ""
        lines.append(f"### {i}. `{g['signature']}` — {g['class']}{new}{llm}")
        lines.append("")
        lines.append(f"- score **{g['score']:.1f}** · count **{g['count']}** · "
                     f"severity {_SEVERITY.get(g['class'], 1)}")
        lines.append(f"- first seen {_fmt_ts(g['first_seen'])} · "
                     f"last seen {_fmt_ts(g['last_seen'])}")
        lines.append(f"- sources: {', '.join(sorted(g['sources'])) or '—'} · "
                     f"surfaces: {', '.join(sorted(s for s in g['surfaces'] if s)) or '—'}")
        lines.append(f"- suggested owner: {_OWNER.get(g['class'], 'LEAD')}")
        lines.append(f"- example: {_example_line(g)}")
        lines.append("")

    # Budget section (LOCAL-804B) — failures whose real root cause was the daily
    # paid-API budget / credit running out, NOT a defect. Surfaced separately so
    # LEAD routes them to ops/budget, not engineering.
    budget = [g for g in groups if g["class"] == "budget"]
    budget.sort(key=lambda g: (g["score"], g["count"]), reverse=True)
    lines.append("## Budget / credit — paid-API cap, not a defect")
    lines.append("")
    if not budget:
        lines.append("_No budget/credit-caused failures in this window._")
    else:
        lines.append("These failures looked like defects but the root-cause "
                     "lookup tied them to a paid-API budget/credit refusal "
                     "(`DAILY_PAID_LIMIT_USD` / a provider 402 in "
                     "`paid_api_calls`). The fix is to raise/reset the cap or "
                     "top up credit — do NOT open an engineering defect.")
        lines.append("")
        lines.append("| signature | count | surface | root cause |")
        lines.append("| --- | --- | --- | --- |")
        for g in budget[:15]:
            surfaces = ", ".join(sorted(s for s in g["surfaces"] if s)) or "—"
            rc = g["example"].get("root_cause_detail") or "budget/credit refusal"
            lines.append(f"| `{g['signature']}` | {g['count']} | {surfaces} | "
                         f"{rc} |")
    lines.append("")

    # User-confusion section — the screens/actions, for UI fixes (Michael).
    uc = [g for g in groups if g["class"] == "user_confusion"]
    uc.sort(key=lambda g: (g["score"], g["count"]), reverse=True)
    lines.append("## User confusion — screens & actions for UI fixes")
    lines.append("")
    if not uc:
        lines.append("_No user-confusion groups in this window._")
    else:
        lines.append("Michael (D723): turn these into interface fixes, not just "
                     "bug tickets. Each row is a place the product asked the user "
                     "for something it could not then deliver.")
        lines.append("")
        lines.append("| signature | count | surface/action | example (redacted) |")
        lines.append("| --- | --- | --- | --- |")
        for g in uc[:15]:
            surfaces = ", ".join(sorted(s for s in g["surfaces"] if s)) or "—"
            msg = redact(g["example"].get("message"), 80) or "—"
            lines.append(f"| `{g['signature']}` | {g['count']} | {surfaces} | "
                         f"{msg} |")
    lines.append("")
    return "\n".join(lines) + "\n"


_DRAFT_PREFIX = "new_kiro_session_is_required_DRAFT-"


def render_draft(g, now, days):
    """A DRAFT task file for an our_bug group. NOT the dispatcher glob
    (new_kiro_session_is_required_LOCAL-*.md); LEAD reviews & promotes."""
    ex = g["example"]
    sig = g["signature"]
    lines = []
    lines.append(f"# DRAFT (unpromoted) — our_bug `{sig}` — proposed fix")
    lines.append("")
    lines.append("> **This is a DRAFT emitted by failure_triage.py (LOCAL-804, "
                 "D723).** It is NOT a released task: the filename is "
                 "`new_kiro_session_is_required_DRAFT-…`, deliberately outside "
                 "the dispatcher glob (`new_kiro_session_is_required_LOCAL-*.md`), "
                 "and it is never added to RELEASED.txt. LEAD reviews the "
                 "evidence below and, if it is real, renames this to a LOCAL "
                 "ticket to promote it.")
    lines.append("")
    lines.append("## Evidence")
    lines.append("")
    lines.append(f"- signature: `{sig}`")
    lines.append(f"- class: our_bug (severity {_SEVERITY['our_bug']})")
    lines.append(f"- occurrences: **{g['count']}** in the last {days} day"
                 f"{'s' if days != 1 else ''} "
                 f"(score {g['score']:.1f})")
    lines.append(f"- first seen {_fmt_ts(g['first_seen'])} · "
                 f"last seen {_fmt_ts(g['last_seen'])}")
    lines.append(f"- sources: {', '.join(sorted(g['sources'])) or '—'}")
    lines.append(f"- services: {', '.join(sorted(g['services'])) or '—'}")
    lines.append(f"- surfaces: {', '.join(sorted(s for s in g['surfaces'] if s)) or '—'}")
    code = ex.get("error_code") or (f"HTTP {ex['http_status']}"
                                    if ex.get("http_status") else "—")
    lines.append(f"- error_code: `{code}`")
    if ex.get("exception_type"):
        lines.append(f"- exception_type: `{ex['exception_type']}`")
    lines.append(f"- example message (redacted): {redact(ex.get('message'), 300) or '—'}")
    lines.append("")
    lines.append("## Proposed fix area")
    lines.append("")
    lines.append(_proposed_fix_area(g))
    lines.append("")
    lines.append("## Suggested next steps for the promoted session")
    lines.append("")
    lines.append("1. Reproduce from the evidence above (group by this signature "
                 "in `failure_events` / `generator_jobs`).")
    lines.append("2. Write a red test that captures the failure, then fix it.")
    lines.append("3. On merge, set `resolved_by` for this signature via "
                 "`failure_report.py --mark <signature> our_bug LOCAL-NNN`.")
    lines.append("")
    return "\n".join(lines) + "\n"


def _proposed_fix_area(g):
    ex = g["example"]
    src = g["sources"]
    code = (ex.get("error_code") or "").lower()
    if "generator_jobs" in src or code == "generation_failed":
        return ("The tour-generator produced no tour for these requests "
                "(`generation_failed` / generator job error). Start in "
                "`generate_tour_text_service.py` (job lifecycle / clean-fail "
                "path) and the orchestrator's generation call; confirm the "
                "structured refusal is recorded and the job's `error` JSONB is "
                "populated so the next triage has a reason, not just 'failed'.")
    if "tour_requests" in src:
        return ("`tour_requests` rows went to `status='failed'` with no reason "
                "attached. Trace the orchestrator path that marks a request "
                "failed (`tour_orchestrator_service.py`) and ensure every such "
                "path also calls `failure_log.record(...)` with an error_code, "
                "so the failure stops being a reasonless 'failed'.")
    if ex.get("exception_type"):
        return (f"An unhandled `{ex['exception_type']}` reached the failure "
                f"recorder for service `{ex.get('service')}` on surface "
                f"`{ex.get('surface')}`. Find the raising call site from the "
                f"recorded frames and add handling + a test.")
    return (f"Recorded as our_bug on service `{ex.get('service')}` / surface "
            f"`{ex.get('surface')}`. Inspect the grouped rows for the common "
            f"call site and add handling + a regression test.")


# ---------------------------------------------------------------------------
# Seen-signatures memory (so "new groups" means new, run-to-run).
# ---------------------------------------------------------------------------

def load_seen(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("signatures", []))
    except Exception:
        return set()


def save_seen(path, seen, groups):
    sigs = set(seen) | {g["signature"] for g in groups}
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"signatures": sorted(sigs),
                       "updated": datetime.now(timezone.utc).isoformat()}, f,
                      indent=0)
    except Exception:
        pass
    return sigs


# ---------------------------------------------------------------------------
# Orchestration.
# ---------------------------------------------------------------------------

def run(days=7, db_url=None, out_dir=".", use_llm=False, dry_run=False,
        top=15, now=None, events=None, include_tests=False):
    """Produce the report + drafts. Returns a result dict (paths, counts, cost).
    `events` can be injected (tests) to bypass the DB entirely.

    LOCAL-804B: test / harness traffic is excluded by default (the Mac DB is
    shared with the test suites); `include_tests=True` keeps it for an audit."""
    now = now or datetime.now(timezone.utc)
    since_dt = now - timedelta(days=days)

    if events is None:
        conn = _connect(db_url)
        try:
            events = read_all(conn, since_dt)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # Exclude test / harness traffic by default (LOCAL-804B). The evidence for
    # user_confusion is built from the KEPT events only, so a test row cannot
    # vouch for a production failure.
    events, excluded_tests = filter_test_events(events,
                                                 include_tests=include_tests)

    groups = group_events(events)

    reports_dir = os.path.join(out_dir, "reports")
    drafts_dir = os.path.join(out_dir, "drafts")
    seen_path = os.path.join(reports_dir, ".triage_seen.json")
    seen = load_seen(seen_path)

    rank_groups(groups, now, seen)

    llm_cost = 0.0
    if use_llm:
        llm_cost = llm_classify_unknowns(groups)
        # Re-rank: an LLM relabel can change severity/score.
        rank_groups(groups, now, seen)

    report_md = render_report(groups, now, days, top=top,
                              excluded_tests=excluded_tests,
                              include_tests=include_tests)

    # Top-3 our_bug groups → draft files.
    our_bugs = [g for g in groups if g["class"] == "our_bug"][:3]
    drafts = {}
    for g in our_bugs:
        name = f"{_DRAFT_PREFIX}{g['signature'][:8]}.md"
        drafts[name] = render_draft(g, now, days)

    report_name = f"failure_triage_{now.strftime('%Y-%m-%d')}.md"
    report_path = os.path.join(reports_dir, report_name)

    written = []
    if not dry_run:
        os.makedirs(reports_dir, exist_ok=True)
        os.makedirs(drafts_dir, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_md)
        written.append(report_path)
        for name, body in drafts.items():
            p = os.path.join(drafts_dir, name)
            with open(p, "w", encoding="utf-8") as f:
                f.write(body)
            written.append(p)
        save_seen(seen_path, seen, groups)

    return {
        "now": now,
        "days": days,
        "event_count": len(events),
        "excluded_tests": excluded_tests,
        "include_tests": include_tests,
        "group_count": len(groups),
        "new_count": sum(1 for g in groups if g.get("is_new")),
        "report_path": report_path,
        "report_md": report_md,
        "drafts": drafts,
        "written": written,
        "llm_cost_usd": llm_cost,
        "groups": groups,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="LOCAL-804/D723 nightly failure triage → ranked report + "
                    "draft task files. Read-only on the DB.")
    ap.add_argument("--days", type=int, default=7,
                    help="window in days (default 7).")
    ap.add_argument("--db-url", default=None,
                    help="explicit DB URL (overrides DATABASE_URL / DB_* env). "
                         "GCloud_Storied passes the Cloud SQL URL here.")
    ap.add_argument("--out-dir", default=".",
                    help="base dir for reports/ and drafts/ (default: cwd).")
    ap.add_argument("--top", type=int, default=15,
                    help="how many groups to list in the report (default 15).")
    ap.add_argument("--llm", action="store_true",
                    help="one cheap gpt-4.1-mini classify per NEW unknown group "
                         "(≤ $0.02/night, $0.05 absolute cap). Off by default; "
                         "with it off NO network call is made.")
    ap.add_argument("--include-tests", action="store_true",
                    help="include test / harness traffic (test/TEST/p1- ids, "
                         "LOCAL-NNN run_* harnesses). Off by default: the shared "
                         "Mac DB is also where the test suites write, and that "
                         "noise dominated the first report.")
    ap.add_argument("--dry-run", action="store_true",
                    help="compute and print the report to stdout; write nothing.")
    args = ap.parse_args(argv)

    try:
        res = run(days=args.days, db_url=args.db_url, out_dir=args.out_dir,
                  use_llm=args.llm, dry_run=args.dry_run, top=args.top,
                  include_tests=args.include_tests)
    except Exception as e:
        print(f"[D723] failure_triage: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(res["report_md"])
    print(f"[D723] failure_triage: {res['event_count']} events "
          f"({res['excluded_tests']} test/harness "
          f"{'kept' if res['include_tests'] else 'excluded'}) → "
          f"{res['group_count']} groups ({res['new_count']} new). "
          f"report={res['report_path']} drafts={len(res['drafts'])} "
          f"llm_cost=${res['llm_cost_usd']:.4f}"
          + ("  (dry-run: nothing written)" if args.dry_run else ""),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
