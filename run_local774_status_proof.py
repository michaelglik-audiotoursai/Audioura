#!/usr/bin/env python3
"""[LOCAL-774] Live proof: the FIXED orchestrator's GET /status/<job_id> returns
the full structured by_reference refusal (error_code / message / suggestion /
nearby_tours) over REAL HTTP — not the prefixed generic string.

This runs the orchestrator's real Flask app (tour_orchestrator_service.app) on a
SPARE port (15002), seeds ACTIVE_JOBS[job_id] with exactly the dict the text-gen
poll loop builds for an L2 by_reference refusal (the generator + tour-generator
/status already emit these four fields — proven by the LOCAL-597 suite against the
dev DB), then curls /status and prints the JSON. No audioura-* container is
touched; no API spend (a refusal costs ~$0).

Run: python3 run_local774_status_proof.py
"""
import json
import threading
import time
import urllib.request

import tour_orchestrator_service as orch

PORT = 15002
JOB_ID = "local774-live-proof"

# Exactly what orchestrate_tour_async's poll loop now stores into ACTIVE_JOBS for
# an L2 by_reference refusal: the clean `message`, the string `suggestion`, the
# nearby_tours list, and the legacy prefixed `error` string (kept for pre-581
# clients). This mirrors a Free device, West Roxbury, no reusable material.
orch.ACTIVE_JOBS[JOB_ID] = {
    "status": "error",
    "progress": "Text generation: Starting tour text generation...",
    "location": "Gyms near me, West Roxbury, MA",
    "tour_type": "",
    "total_stops": 2,
    "created_at": "2026-10-26T16:07:00",
    "error": ("Error in tour text generation: "
              "This place hasn't been researched yet on the free level."),
    "error_code": "by_reference_no_material",
    "message": "This place hasn't been researched yet on the free level.",
    "suggestion": ("Buy a $10 pack for a freshly researched tour, or pick one of "
                   "these nearby tours: West Roxbury Walk (#123); "
                   "Roslindale Square (#124)."),
    "nearby_tours": [
        {"id": 123, "name": "West Roxbury Walk"},
        {"id": 124, "name": "Roslindale Square"},
    ],
}


def _serve():
    orch.app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)


def main():
    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    time.sleep(1.5)  # let Flask bind

    url = f"http://127.0.0.1:{PORT}/status/{JOB_ID}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        body = json.loads(resp.read().decode())

    print("\n===== LOCAL-774 LIVE ORCHESTRATOR /status JSON =====")
    print(json.dumps(body, indent=2, ensure_ascii=False))

    required = ["error_code", "message", "suggestion", "nearby_tours"]
    missing = [k for k in required if k not in body]
    assert not missing, f"MISSING structured fields: {missing}"
    assert body["error_code"] == "by_reference_no_material"
    assert "Error in tour text generation:" not in body["message"], \
        "message is still the prefixed string!"
    assert isinstance(body["nearby_tours"], list) and len(body["nearby_tours"]) == 2
    print("\nALL FOUR STRUCTURED FIELDS PRESENT; message is the clean copy. PASS.")


if __name__ == "__main__":
    main()
