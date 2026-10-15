#!/usr/bin/env python3
"""LOCAL-705 replay harness (bounce of LOCAL-694B for the CURRENT app, D661).

Replays every server call the CURRENT Subscribed app makes (local705_tooling/
inventory.md, 84 rows) against a LOCAL Storied stack built STRICTLY from
`origin/storied`, in its OWN compose project on spare 53xx ports:

    export STORIED=/Volumes/AudiouraSSD/audioura-worktrees/local705-storied
    export STORIED_SHA=$(git -C "$STORIED" rev-parse HEAD)
    docker compose -p local705 -f storied-stack.compose.yml up -d --build
    python3 replay_harness.py

Same method as LOCAL-694B: a 404 is reported with its body kind — `json-404`
(the service's OWN not-found — NORMAL), `html-404` (Flask's missing-route page
— MISSING), or the gateway envelope `{endpoint not found, api-gateway}`
(MISSING). The app's Endpoints.isRouteMissing(status, body) makes the same
distinction; getOrFeatureUnavailable / postOrFeatureUnavailable turn MISSING and
connection-refused into the Preview-only message, while a NORMAL not-found keeps
its own handling.

SAFETY: own `-p local705` containers only (never `-p audioura`). No GCloud, no
tour generation, no paid work; cost-bearing POSTs carry empty/invalid bodies to
draw a free validation refusal. Reads are harmless.

Storied host ports (host->container): orchestrator 5302, tour-processor 5301,
map-delivery 5305, treats 5307, news-orch 5312, newsletter 5317,
tour-editing-phase2 5322, translation 5330. Services Storied's GCloud does NOT
host (userDb, voice, generator, customAudio, tourIdResolution) are pointed at an
unused 53xx port so the probe records a connection refusal == "service absent".
"""
import json
import os
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.request

HOST = "127.0.0.1"

STORIED = os.environ.get(
    "STORIED", "/Volumes/AudiouraSSD/audioura-worktrees/local705-storied")

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

SERVICE_SRC = {
    "orchestrator": ["tour_orchestrator_service.py"],
    "mapDelivery": ["map_delivery/app.py"],
    "treats": ["treats_service.py"],
    "news": ["news_orchestrator_service.py"],
    "newsletter": ["newsletter_processor_service.py"],
    "tourEditing": ["tour_editing_phase2.py"],
    "translation": ["translation-service/translation_service.py"],
    "userDb": ["user_api_service.py"],
    "voice": ["voice_control_service.py"],
    "generator": ["generate_tour_text_service.py", "sharing_endpoints.py"],
    "customAudio": ["custom_audio_service.py"],
    "tourIdResolution": ["tour_id_resolution_service.py"],
}

TID = "686"
CODE = "L687MATA"
JOB = "nonexistent-job"
USER = "local705-probe-user"

# Each entry: (num, service, method, path, body-or-None, grep_regex, note)
CALLS = [
    (1, "orchestrator", "POST", "/generate-complete-tour", {}, r"/generate-complete-tour", "empty body -> validation refusal, no job"),
    (2, "orchestrator", "GET", f"/status/{JOB}", None, r"/status/<", "REAL route; unknown-job 404 (NORMAL)"),
    (3, "orchestrator", "GET", f"/download/{JOB}", None, r"/download/<", "REAL route; unknown-job 404 (NORMAL)"),
    (4, "orchestrator", "GET", "/health", None, r"/health", ""),
    (5, "orchestrator", "GET", f"/delete-account/{USER}", None, r"/delete-account", "GET probe (no delete body)"),
    (6, "orchestrator", "POST", "/tour-status", {}, r"/tour-status", "empty body"),
    (7, "orchestrator", "GET", f"/tour/{TID}/unlock-state?user_id={USER}", None, r"/unlock-state", ""),
    (8, "orchestrator", "GET", f"/tour/{TID}/price", None, r"<[^>]*>/price|/price'", ""),
    (9, "orchestrator", "POST", f"/tour/{TID}/price", {}, r"/price", "empty body"),
    (10, "orchestrator", "GET", f"/tour/{TID}/sales", None, r"/sales", ""),
    (11, "orchestrator", "GET", "/price-tiers", None, r"/price-tiers", ""),
    (12, "orchestrator", "GET", f"/tour/{TID}/reviews?sort=top", None, r"/reviews", ""),
    (13, "orchestrator", "GET", f"/tour/{TID}/distribution", None, r"/distribution", ""),
    (14, "orchestrator", "POST", f"/tour/{TID}/review", {}, r"/review'|/review\"", "empty body"),
    (15, "orchestrator", "POST", "/review/1/helpful", {}, r"/helpful", "empty body"),
    (16, "orchestrator", "POST", "/review/1/reply", {}, r"/reply", "empty body"),
    (17, "orchestrator", "POST", f"/tour/{TID}/rating", {}, r"/rating", "empty body"),
    (18, "orchestrator", "GET", f"/tour/{TID}/rating", None, r"/rating", ""),
    (19, "orchestrator", "GET", f"/wallet/{USER}", None, r"/wallet/<", ""),
    (20, "orchestrator", "GET", f"/wallet/{USER}/transactions?limit=50", None, r"/transactions", ""),
    (21, "orchestrator", "GET", "/plans/available", None, r"/plans/available", ""),
    (22, "orchestrator", "POST", f"/wallet/{USER}/topup", {}, r"/topup", "empty body (no purchase)"),
    (23, "orchestrator", "POST", "/sync", {}, r"@app.route\('/sync'", "empty body"),
    (24, "mapDelivery", "GET", "/tours-near/48.8584/2.2945?radius=5.0", None, r"/tours-near", "Paris"),
    (25, "mapDelivery", "GET", f"/download-tour/{TID}", None, r"/download-tour", "REAL tour id 686"),
    (26, "mapDelivery", "GET", "/search-tours?pattern=museum&lat=48.8584&lng=2.2945", None, r"/search-tours", ""),
    (27, "mapDelivery", "GET", f"/tour-by-code/{CODE}", None, r"/tour-by-code", "REAL share code -> 200"),
    (28, "mapDelivery", "GET", f"/tour/{TID}/preview-audio", None, r"/preview-audio", ""),
    (29, "mapDelivery", "GET", f"/tour/{TID}/score-explanation", None, r"/score-explanation", ""),
    (30, "mapDelivery", "POST", f"/tour/{TID}/rescore-request", {}, r"/rescore-request", "empty body"),
    (31, "mapDelivery", "GET", "/how-we-score", None, r"/how-we-score", ""),
    (32, "tourIdResolution", "GET", f"/tour/{TID}/resolve", None, r"/resolve", "ABSENT on Storied"),
    (33, "userDb", "GET", "/user", None, r"@app.route\('/user'", "ABSENT on Storied"),
    (34, "userDb", "GET", "/health", None, r"/health", "ABSENT on Storied"),
    (35, "userDb", "GET", f"/entitlements/me?user_id={USER}", None, r"/entitlements/me", "ABSENT on Storied"),
    (36, "userDb", "POST", "/entitlements/app-open", {}, r"/entitlements/app-open", "ABSENT on Storied"),
    (37, "userDb", "POST", "/entitlements/lapse", {}, r"/entitlements/lapse", "ABSENT on Storied"),
    (38, "userDb", "POST", "/l2/queue/join", {}, r"/l2/queue/join", "ABSENT on Storied"),
    (39, "userDb", "POST", "/l2/claim", {}, r"/l2/claim", "ABSENT on Storied"),
    (40, "userDb", "POST", "/purchases/verify", {}, r"/purchases/verify", "ABSENT on Storied"),
    (41, "userDb", "POST", "/document-acceptance", {}, r"/document-acceptance", "ABSENT on Storied"),
    (42, "userDb", "GET", f"/document-acceptance?user_id={USER}", None, r"/document-acceptance", "ABSENT on Storied"),
    (43, "userDb", "POST", "/communities", {}, r"@app.route\('/communities'", "ABSENT on Storied"),
    (44, "userDb", "GET", f"/communities/by-code/{CODE}", None, r"/communities/by-code", "ABSENT on Storied"),
    (45, "userDb", "GET", "/communities/1", None, r"/communities/<", "ABSENT on Storied"),
    (46, "userDb", "POST", "/communities/1/join", {}, r"/communities/<[^>]*>/join|/join", "ABSENT on Storied"),
    (47, "userDb", "GET", "/communities/map", None, r"/communities/map", "ABSENT on Storied"),
    (48, "treats", "GET", "/treats-near/48.8584/2.2945", None, r"/treats-near", ""),
    (50, "voice", "POST", "/parse_voice_search", {}, r"/parse_voice_search", "ABSENT on Storied"),
    (51, "voice", "POST", "/process-voice-command", {}, r"/process-voice-command", "ABSENT on Storied"),
    (52, "translation", "POST", "/translate-with-audio", {}, r"/translate-with-audio", "empty body -> refusal, no paid translate"),
    (53, "generator", "POST", "/tour/share", {}, r"/tour/share|/share", "ABSENT on Storied (generator not hosted)"),
    (54, "news", "POST", "/generate-news", {}, r"/generate-news", "empty body"),
    (55, "news", "GET", "/status/nonexistent", None, r"@app.route\('/status/<", "direct service path"),
    (56, "news", "GET", "/download/nonexistent?user_id=" + USER, None, r"@app.route\('/download/<", "direct service path"),
    (57, "newsletter", "GET", "/newsletters_v2", None, r"/newsletters_v2", ""),
    (58, "newsletter", "POST", "/process_newsletter", {}, r"/process_newsletter", "empty body"),
    (59, "newsletter", "POST", "/submit_credentials", {}, r"/submit_credentials", "empty body"),
    (60, "newsletter", "POST", "/key_exchange", {}, r"/key_exchange", "empty body"),
    (61, "tourEditing", "POST", f"/tour/{TID}/update-stop", {}, r"/update-stop", "empty body"),
    (62, "tourEditing", "POST", f"/tour/{TID}/update-multiple-stops", {}, r"/update-multiple-stops", "empty body"),
    (63, "tourEditing", "GET", f"/tour/{TID}/job-status/{JOB}", None, r"/job-status", ""),
    (64, "customAudio", "POST", f"/tour/{TID}/stop/1/custom-audio", {}, r"/custom-audio", "ABSENT on Storied"),
    (65, "customAudio", "DELETE", f"/tour/{TID}/stop/1/custom-audio", None, r"/custom-audio", "ABSENT on Storied"),
    (66, "customAudio", "GET", f"/tour/{TID}/stop/1/audio-versions", None, r"/audio-versions", "ABSENT on Storied"),
    (67, "customAudio", "GET", f"/tour/{TID}/audio-metadata", None, r"/audio-metadata", "ABSENT on Storied"),

    # ── [NEW in LOCAL-705] rows 68..84: the calls 695..704 added ──────────────
    (68, "userDb", "GET", f"/communities/mine?user_id={USER}", None, r"/communities/mine'|/communities/mine\"|/communities/mine<", "ABSENT on Storied [NEW 690]"),
    (69, "userDb", "GET", f"/communities/mine-owned?user_id={USER}", None, r"/communities/mine-owned", "ABSENT on Storied [NEW 701]"),
    (70, "orchestrator", "GET", f"/communities/1/tours?user_id={USER}", None, r"/communities/<[^>]*>/tours|/tours", "orchestrator community tours [NEW 701]"),
    (71, "orchestrator", "GET", f"/tour/{TID}/community", None, r"/tour/<[^>]*>/community|/community", "orchestrator tour tag [NEW 701]"),
    (72, "userDb", "GET", "/communities/name-available?name=Test", None, r"/communities/name-available", "ABSENT on Storied [NEW 700]"),
    (73, "userDb", "POST", "/communities/1/regenerate-code", {}, r"/regenerate-code", "ABSENT on Storied [NEW 700]"),
    (74, "userDb", "POST", "/communities/1/episodes", {}, r"/communities/<[^>]*>/episodes|/episodes", "ABSENT on Storied [NEW 690]"),
    (75, "userDb", "POST", "/communities/1/import-feed", {}, r"/import-feed", "ABSENT on Storied [NEW 690]"),
    (76, "userDb", "POST", "/communities/1/step-down", {}, r"/step-down", "ABSENT on Storied [NEW 702]"),
    (77, "userDb", "POST", "/communities/1/offer-organiser", {}, r"/offer-organiser", "ABSENT on Storied [NEW 702]"),
    (78, "userDb", "POST", "/communities/1/withdraw-offer", {}, r"/withdraw-offer", "ABSENT on Storied [NEW 702]"),
    (79, "userDb", "POST", "/communities/1/pick-organiser", {}, r"/pick-organiser", "ABSENT on Storied [NEW 702]"),
    (80, "userDb", "POST", "/communities/1/accept-organiser", {}, r"/accept-organiser", "ABSENT on Storied [NEW 702]"),
    (81, "userDb", "DELETE", "/communities/1", None, r"/communities/<", "ABSENT on Storied [NEW 702]"),
    (82, "userDb", "GET", "/purchases/mode", None, r"/purchases/mode", "ABSENT on Storied [NEW 699]"),
    (83, "orchestrator", "POST", "/recovery-code/generate", {}, r"/recovery-code/generate", "empty body [NEW 695]"),
    (84, "orchestrator", "POST", "/recovery-code/restore", {}, r"/recovery-code/restore", "empty body [NEW 695]"),
]


def route_exists_grep(service, grep_regex):
    srcs = SERVICE_SRC.get(service, [])
    any_file = False
    for rel in srcs:
        path = os.path.join(STORIED, rel)
        if not os.path.isfile(path):
            continue
        any_file = True
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        if re.search(grep_regex, text):
            return "yes"
    if not any_file:
        return "src-missing"
    return "no"


def shape(body_bytes):
    if not body_bytes:
        return "empty"
    text = body_bytes.decode("utf-8", "replace")
    try:
        obj = json.loads(text)
    except Exception:
        snippet = text.strip().replace("\n", " ")[:50]
        return f"non-json(html): {snippet!r}"
    if isinstance(obj, dict):
        keys = ",".join(sorted(obj.keys())[:8])
        return f"json-object{{{keys}}}"
    if isinstance(obj, list):
        if obj and isinstance(obj[0], dict):
            return f"json-array[{len(obj)}] of obj{{{','.join(sorted(obj[0].keys())[:6])}}}"
        return f"json-array[{len(obj)}]"
    return f"json-{type(obj).__name__}"


def body_kind(status, sh):
    if status != 404:
        return ""
    if sh.startswith("non-json"):
        return "html-404 (MISSING)"
    if "endpoint not found" in sh or "api-gateway" in sh:
        return "gateway-404 (MISSING)"
    if sh.startswith("json"):
        return "json-404 (NORMAL not-found)"
    return "404"


def replay(service, method, path, body):
    url = f"http://{HOST}:{PORT[service]}{path}"
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, shape(r.read())
    except urllib.error.HTTPError as e:
        return e.code, shape(e.read())
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError) as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, (ConnectionRefusedError,)) or "refused" in str(reason).lower():
            return "CONN_REFUSED", "service absent on Storied"
        return "ERR", f"{reason}".replace("\n", " ")[:60]


def classify(status, sh):
    if status == "CONN_REFUSED":
        return "ABSENT (no service on Storied)"
    if status == "ERR":
        return "ERROR (transport)"
    if isinstance(status, int):
        if status == 200:
            return "OK"
        if status == 404:
            if sh.startswith("non-json") or "endpoint not found" in sh:
                return "MISSING ROUTE (html/gateway 404)"
            return "NORMAL not-found (json 404)"
        if status in (405, 501):
            return "MISSING ROUTE (405/501)"
        if 400 <= status < 500:
            return "4xx (handled refusal/validation)"
        if status >= 500:
            return "5xx (server error)"
    return "?"


def app_handling(service, cls):
    """How the CURRENT app renders this outcome (the D661 contract). Keyed by
    the classification + the service's known Dart handler."""
    if cls.startswith("ABSENT") or cls.startswith("MISSING"):
        if service in ("userDb", "voice", "generator", "customAudio",
                       "tourIdResolution"):
            return "Preview-only / empty state (service absent)"
        return "Preview-only / empty state (route missing)"
    if cls.startswith("NORMAL not-found"):
        return "normal not-found (keeps its own message)"
    if cls == "OK":
        return "feature works (200)"
    if cls.startswith("4xx"):
        return "handled refusal/validation message"
    if cls.startswith("5xx"):
        return "offline/try-again message"
    if cls.startswith("ERROR"):
        return "offline message"
    return "handled"


def print_stack_stamps():
    print("### STORIED STACK PROVENANCE (built from origin/storied)\n")
    sha = subprocess.run(
        ["git", "-C", STORIED, "rev-parse", "HEAD"],
        capture_output=True, text=True).stdout.strip()
    print(f"- STORIED worktree: {STORIED}")
    print(f"- git rev-parse HEAD: {sha}")
    print("- per-container stamp (/app/.git_sha or RELEASE/GIT_SHA env):\n")
    ps = subprocess.run(
        ["docker", "ps", "--filter", "name=local705", "--format", "{{.Names}}"],
        capture_output=True, text=True).stdout.split()
    for name in sorted(ps):
        stamp = subprocess.run(
            ["docker", "exec", name, "sh", "-c",
             "cat /app/.git_sha 2>/dev/null || echo $GIT_SHA"],
            capture_output=True, text=True).stdout.strip()
        print(f"  - {name}: {stamp or '(no stamp)'}")
    print()


def main():
    print_stack_stamps()
    rows = []
    for num, service, method, path, body, grep_rx, note in CALLS:
        status, sh = replay(service, method, path, body)
        cls = classify(status, sh)
        grep = route_exists_grep(service, grep_rx)
        bk = body_kind(status, sh)
        handling = app_handling(service, cls)
        rows.append((num, service, method, path, status, cls, grep, bk, sh,
                     handling, note))
        print(f"[{num:>2}] {service:<16} {method:<6} {status!s:<13} "
              f"grep={grep:<11} {cls:<34} {handling}")

    print("\n### STACK-SANITY: grep=yes but html/gateway 404 on a hosted service\n")
    hosted = {"orchestrator", "mapDelivery", "treats", "news", "newsletter",
              "tourEditing", "translation"}
    bad = [r for r in rows
           if r[1] in hosted and r[6] == "yes"
           and isinstance(r[4], int) and r[4] == 404
           and (r[8].startswith("non-json") or "endpoint not found" in r[8])]
    if bad:
        for r in bad:
            print(f"  !! #{r[0]} {r[1]} {r[3]} -> {r[4]} {r[8]} (FIX THE STACK)")
    else:
        print("  none — every grep-present route on a hosted service returns "
              "JSON/200, never an HTML 404.")

    print("\n\n### REPLAY TABLE (markdown)\n")
    print("| # | Service | Method | Path | Storied status | Classification | "
          "route exists on storied (grep) | 404 body kind | Body shape | "
          "How the app handles it | Note |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for (num, service, method, path, status, cls, grep, bk, sh, handling,
         note) in rows:
        p = path.replace("|", "\\|")
        s = sh.replace("|", "\\|")
        print(f"| {num} | {service} | {method} | `{p}` | {status} | {cls} | "
              f"{grep} | {bk} | {s} | {handling} | {note} |")

    print("\n### SUMMARY\n")
    from collections import Counter
    c = Counter(r[5] for r in rows)
    for k, v in sorted(c.items()):
        print(f"- {k}: {v}")
    print(f"\nTotal calls replayed: {len(rows)}")


if __name__ == "__main__":
    main()
