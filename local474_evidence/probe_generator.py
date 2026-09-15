import urllib.request, urllib.error, json, sys

BASE = "http://localhost:5000"

def probe(name, path, payload, timeout=180):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        body = r.read().decode("utf-8", "replace")
        code = r.status
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        code = e.code
    except Exception as e:
        body = "EXC: %r" % (e,)
        code = "ERR"
    snip = body if len(body) <= 300 else body[:300]
    print("[%s] %s -> HTTP %s | %s" % (name, path, code, snip.replace(chr(10), " ")))
    return code, body

mode = sys.argv[1] if len(sys.argv) > 1 else "gate"

if mode == "gate":
    # Quick gate checks — use short timeout so a passed gate (which would start
    # full generation) doesn't burn an OpenAI call; we only need the status code.
    probe("empty_tour_type",   "/generate",
          {"location": "Bread Thyme restaurant tour in West Roxbury, MA", "tour_type": "", "total_stops": 1, "user_id": 1},
          timeout=8)
    probe("missing_tour_type", "/generate",
          {"location": "Bread Thyme restaurant tour in West Roxbury, MA", "total_stops": 1, "user_id": 1},
          timeout=8)
    probe("empty_location",    "/generate",
          {"location": "", "tour_type": "", "total_stops": 1, "user_id": 1},
          timeout=8)
elif mode == "live":
    # The ONE authorized live 1-stop tour: empty tour_type must produce 200.
    probe("LIVE_empty_tour_type", "/generate",
          {"location": "Bread Thyme restaurant tour in West Roxbury, MA", "tour_type": "", "total_stops": 1, "user_id": 1},
          timeout=600)
