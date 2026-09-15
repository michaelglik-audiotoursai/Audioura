import urllib.request, urllib.error, json, sys

BASE = "http://localhost:5002"

def probe(name, payload, timeout=8):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BASE + "/generate-complete-tour", data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        body = r.read().decode("utf-8", "replace"); code = r.status
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace"); code = e.code
    except Exception as e:
        body = "EXC:%r" % (e,); code = "ERR/timeout(gate passed)"
    snip = body if len(body) <= 260 else body[:260]
    print("[%s] -> HTTP %s | %s" % (name, code, snip.replace(chr(10), " ")))

# No user_id -> gate for location/tour_type is evaluated first; the 401 entitlements
# check comes AFTER, so these isolate the location/tour_type gate cleanly.
probe("empty_tour_type_no_user",
      {"location": "Bread Thyme restaurant tour in West Roxbury, MA", "tour_type": "", "total_stops": 1})
probe("missing_tour_type_no_user",
      {"location": "Bread Thyme restaurant tour in West Roxbury, MA", "total_stops": 1})
probe("empty_location_no_user",
      {"location": "", "tour_type": "", "total_stops": 1})
probe("explicit_museum_no_user",
      {"location": "Museum of Fine Arts, Boston", "tour_type": "museum", "total_stops": 1})
