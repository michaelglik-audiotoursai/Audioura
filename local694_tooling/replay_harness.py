#!/usr/bin/env python3
"""LOCAL-694 replay harness.

Replays every server call the Subscribed app makes (see inventory.md) against
the LOCAL Storied stack brought up under `docker compose -p local694`.

Records, per call: HTTP status (or connection error), and the SHAPE of the
response body (top-level JSON keys / list / non-JSON), so we can classify each
as OK / 404 missing / 4xx-5xx / shape-differs / service-absent.

SAFETY: no GCloud, no tour generation, no paid work. Cost-bearing POSTs are
sent with an empty/invalid body on purpose — we want the server's validation
refusal (fast, free), never a real job. Reads are harmless.

Storied host ports (host->container), from docker-compose.local694.yml:
  orchestrator 5302, map-delivery 5305, treats 5307, news-orch 5312,
  newsletter 5317, tour-editing-phase2 5322, translation 5330.
Services Storied does NOT host are pointed at an unused 53xx port so the probe
records a connection refusal == "service absent on Storied".
"""
import json
import socket
import sys
import urllib.error
import urllib.request

HOST = "127.0.0.1"

# Service -> replay port. Hosted services use their real mapped 53xx port.
# Absent-on-Storied services use a 53xx port with no listener on purpose.
PORT = {
    "orchestrator": 5302,
    "mapDelivery": 5305,
    "treats": 5307,
    "news": 5312,
    "newsletter": 5317,
    "tourEditing": 5322,
    "translation": 5330,
    # absent on Storied (no container) -> no listener here:
    "userDb": 5303,
    "voice": 5308,
    "generator": 5300,
    "customAudio": 5323,
    "tourIdResolution": 5325,
}

# A benign existing-ish tour id for read probes. Shape is what we care about,
# not whether the id exists (a 404 for a made-up id is still a real route).
TID = "1"
JOB = "nonexistent-job"
CODE = "ABC123"
USER = "local694-probe-user"

# Each entry: (num, service, method, path, body-or-None, note)
# body None => GET/DELETE. body {} or dict => POST (json). Cost-bearing POSTs
# intentionally carry empty/invalid bodies to draw a free validation refusal.
CALLS = [
    (1, "orchestrator", "POST", "/generate-complete-tour", {}, "empty body -> validation refusal, no job"),
    (2, "orchestrator", "GET", f"/status/{JOB}", None, ""),
    (3, "orchestrator", "GET", f"/download/{JOB}", None, ""),
    (4, "orchestrator", "GET", "/health", None, ""),
    (5, "orchestrator", "GET", f"/delete-account/{USER}", None, "GET probe (no delete body)"),
    (6, "orchestrator", "POST", "/tour-status", {}, "empty body"),
    (7, "orchestrator", "GET", f"/tour/{TID}/unlock-state?user_id={USER}", None, ""),
    (8, "orchestrator", "GET", f"/tour/{TID}/price", None, ""),
    (9, "orchestrator", "POST", f"/tour/{TID}/price", {}, "empty body"),
    (10, "orchestrator", "GET", f"/tour/{TID}/sales", None, ""),
    (11, "orchestrator", "GET", "/price-tiers", None, ""),
    (12, "orchestrator", "GET", f"/tour/{TID}/reviews?sort=top", None, ""),
    (13, "orchestrator", "GET", f"/tour/{TID}/distribution", None, ""),
    (14, "orchestrator", "POST", f"/tour/{TID}/review", {}, "empty body"),
    (15, "orchestrator", "POST", "/review/1/helpful", {}, "empty body"),
    (16, "orchestrator", "POST", "/review/1/reply", {}, "empty body"),
    (17, "orchestrator", "POST", f"/tour/{TID}/rating", {}, "empty body"),
    (18, "orchestrator", "GET", f"/tour/{TID}/rating", None, ""),
    (19, "orchestrator", "GET", f"/wallet/{USER}", None, ""),
    (20, "orchestrator", "GET", f"/wallet/{USER}/transactions?limit=50", None, ""),
    (21, "orchestrator", "GET", "/plans/available", None, ""),
    (22, "orchestrator", "POST", f"/wallet/{USER}/topup", {}, "empty body (no purchase)"),
    (23, "orchestrator", "POST", "/sync", {}, "empty body"),
    (24, "mapDelivery", "GET", "/tours-near/48.8584/2.2945?radius=5.0", None, "Paris"),
    (25, "mapDelivery", "GET", f"/download-tour/{TID}", None, ""),
    (26, "mapDelivery", "GET", "/search-tours?pattern=museum&lat=48.8584&lng=2.2945", None, ""),
    (27, "mapDelivery", "GET", f"/tour-by-code/{CODE}", None, ""),
    (28, "mapDelivery", "GET", f"/tour/{TID}/preview-audio", None, ""),
    (29, "mapDelivery", "GET", f"/tour/{TID}/score-explanation", None, ""),
    (30, "mapDelivery", "POST", f"/tour/{TID}/rescore-request", {}, "empty body"),
    (31, "mapDelivery", "GET", "/how-we-score", None, ""),
    (32, "tourIdResolution", "GET", f"/tour/{TID}/resolve", None, "ABSENT on Storied"),
    (33, "userDb", "GET", "/user", None, "ABSENT on Storied"),
    (34, "userDb", "GET", "/health", None, "ABSENT on Storied"),
    (35, "userDb", "GET", f"/entitlements/me?user_id={USER}", None, "ABSENT on Storied"),
    (36, "userDb", "POST", "/entitlements/app-open", {}, "ABSENT on Storied"),
    (37, "userDb", "POST", "/entitlements/lapse", {}, "ABSENT on Storied"),
    (38, "userDb", "POST", "/l2/queue/join", {}, "ABSENT on Storied"),
    (39, "userDb", "POST", "/l2/claim", {}, "ABSENT on Storied"),
    (40, "userDb", "POST", "/purchases/verify", {}, "ABSENT on Storied"),
    (41, "userDb", "POST", "/document-acceptance", {}, "ABSENT on Storied"),
    (42, "userDb", "GET", f"/document-acceptance?user_id={USER}", None, "ABSENT on Storied"),
    (43, "userDb", "POST", "/communities", {}, "ABSENT on Storied"),
    (44, "userDb", "GET", f"/communities/by-code/{CODE}", None, "ABSENT on Storied"),
    (45, "userDb", "GET", "/communities/1", None, "ABSENT on Storied"),
    (46, "userDb", "POST", "/communities/1/join", {}, "ABSENT on Storied"),
    (47, "userDb", "GET", "/communities/map", None, "ABSENT on Storied"),
    (48, "treats", "GET", "/treats-near/48.8584/2.2945", None, ""),
    (50, "voice", "POST", "/parse_voice_search", {}, "ABSENT on Storied"),
    (51, "voice", "POST", "/process-voice-command", {}, "ABSENT on Storied"),
    (52, "translation", "POST", "/translate-with-audio", {}, "empty body -> refusal, no paid translate"),
    (53, "generator", "POST", "/tour/share", {}, "ABSENT on Storied"),
    (54, "news", "POST", "/generate-news", {}, "empty body"),
    (55, "news", "GET", "/news-status/nonexistent", None, ""),
    (56, "news", "GET", "/news-download/nonexistent?user_id=" + USER, None, ""),
    (57, "newsletter", "GET", "/newsletters_v2", None, ""),
    (58, "newsletter", "POST", "/process_newsletter", {}, "empty body"),
    (59, "newsletter", "POST", "/submit_credentials", {}, "empty body"),
    (60, "newsletter", "POST", "/key_exchange", {}, "empty body"),
    (61, "tourEditing", "POST", f"/tour/{TID}/update-stop", {}, "empty body"),
    (62, "tourEditing", "POST", f"/tour/{TID}/update-multiple-stops", {}, "empty body"),
    (63, "tourEditing", "GET", f"/tour/{TID}/job-status/{JOB}", None, ""),
    (64, "customAudio", "POST", f"/tour/{TID}/stop/1/custom-audio", {}, "ABSENT on Storied"),
    (65, "customAudio", "DELETE", f"/tour/{TID}/stop/1/custom-audio", None, "ABSENT on Storied"),
    (66, "customAudio", "GET", f"/tour/{TID}/stop/1/audio-versions", None, "ABSENT on Storied"),
    (67, "customAudio", "GET", f"/tour/{TID}/audio-metadata", None, "ABSENT on Storied"),
]


def shape(body_bytes):
    """Describe the body shape without dumping full content."""
    if not body_bytes:
        return "empty"
    text = body_bytes.decode("utf-8", "replace")
    try:
        obj = json.loads(text)
    except Exception:
        snippet = text.strip().replace("\n", " ")[:60]
        return f"non-json: {snippet!r}"
    if isinstance(obj, dict):
        keys = ",".join(sorted(obj.keys())[:8])
        return f"json-object{{{keys}}}"
    if isinstance(obj, list):
        if obj and isinstance(obj[0], dict):
            return f"json-array[{len(obj)}] of obj{{{','.join(sorted(obj[0].keys())[:6])}}}"
        return f"json-array[{len(obj)}]"
    return f"json-{type(obj).__name__}"


def replay(service, method, path, body):
    url = f"http://{HOST}:{PORT[service]}{path}"
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return r.status, shape(r.read())
    except urllib.error.HTTPError as e:
        return e.code, shape(e.read())
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError) as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, (ConnectionRefusedError,)) or "refused" in str(reason).lower():
            return "CONN_REFUSED", "service absent on Storied"
        return "ERR", f"{reason}".replace("\n", " ")[:60]


def classify(status, service, path):
    if status in ("CONN_REFUSED",):
        return "ABSENT (no service on Storied)"
    if status == "ERR":
        return "ERROR (transport)"
    if isinstance(status, int):
        if status == 200:
            return "OK"
        if status in (404, 405, 501):
            return "MISSING ROUTE (404/405/501)"
        if 400 <= status < 500:
            return "4xx (handled refusal/validation)"
        if status >= 500:
            return "5xx (server error)"
    return "?"


def main():
    rows = []
    for num, service, method, path, body, note in CALLS:
        status, sh = replay(service, method, path, body)
        cls = classify(status, service, path)
        rows.append((num, service, method, path, status, cls, sh, note))
        print(f"[{num:>2}] {service:<16} {method:<6} {status!s:<13} {cls:<32} {path}")
    # Emit a markdown table to stdout after the live log.
    print("\n\n### REPLAY TABLE (markdown)\n")
    print("| # | Service | Method | Path | Status | Classification | Body shape | Note |")
    print("|---|---|---|---|---|---|---|---|")
    for num, service, method, path, status, cls, sh, note in rows:
        p = path.replace("|", "\\|")
        print(f"| {num} | {service} | {method} | `{p}` | {status} | {cls} | {sh} | {note} |")
    # Summary
    print("\n### SUMMARY\n")
    from collections import Counter
    c = Counter(cls for *_, cls, _, _ in rows)
    for k, v in sorted(c.items()):
        print(f"- {k}: {v}")


if __name__ == "__main__":
    main()
