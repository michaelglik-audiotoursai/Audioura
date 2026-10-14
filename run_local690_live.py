#!/usr/bin/env python3
"""
LOCAL-690 live driver — exercises the Communities flow against the ISOLATED DB
audiotours_local690 (own container development-postgres-2-1, host port 5433) and
reports row counts per table. Never touches the shared `audiotours` DB.

Flow: create a paid Listed community with passes + a free community → import a
feed (mock HTTP) → owner adds a link → a member buys a pass (stub) → the SAME
$5 product buys a 1-day pass in a second community (LOCAL-690C: one product per
PRICE, length per community) → a member joins the free community → report → map
list → reminders tick. Prints row counts for every community table at the end.
"""
import os
import sys

os.environ["DATABASE_URL"] = "postgresql://admin:password123@localhost:5433/audiotours_local690"
os.environ["IAP_VERIFY_MODE"] = "stub"
os.environ["ALLOW_UNAUTHENTICATED_ENTITLEMENTS"] = "true"

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "user-tracking"))

import importlib.util


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


ut = os.path.join(ROOT, "user-tracking")
_load("communities_rss", os.path.join(ut, "communities_rss.py"))
ca = _load("communities_api", os.path.join(ut, "communities_api.py"))
ea = _load("entitlements_api", os.path.join(ut, "entitlements_api.py"))

from flask import Flask
app = Flask(__name__)
app.register_blueprint(ca.communities_bp)
app.register_blueprint(ea.entitlements_bp)
app.testing = True
c = app.test_client()

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>F</title>
<item><title>Ep1</title><guid>g1</guid><enclosure url="https://h/ep1.mp3" type="audio/mpeg"/></item>
<item><title>Ep2</title><guid>g2</guid><enclosure url="https://h/ep2.mp3" type="audio/mpeg"/></item>
</channel></rss>"""

owner = "LIVE-690-owner"

# 1. Paid, Listed community with passes + a feed.
r = c.post("/communities", json={
    "owner_user_id": owner, "name": "LIVE Paid Walking Club",
    "description": "A paid community", "organiser_name": "Jane Owner",
    "organiser_bio": "Local guide", "organiser_contact": "jane@example.com",
    "rules_text": "Be kind.", "is_paid": True, "visibility": "listed",
    "latitude": 42.36, "longitude": -71.06,
    "feed_url": "https://h/feed.xml",
    "pass_products": [
        {"product_id": "audioura.pass.usd5", "length": "month"},
        {"product_id": "audioura.pass.usd5", "length": "day"},
    ]})
print("create paid:", r.status_code)
paid = r.get_json()
cid = paid["id"]
print("  join_code:", paid["join_code"])
print("  invite_message:", paid["invite_message"])
print("  passes offered:", [(p["product_id"], p["length"], p["label"]) for p in paid["passes"]])

# 2. Free community (book club).
rf = c.post("/communities", json={"owner_user_id": owner, "name": "LIVE Book Club"})
free_id = rf.get_json()["id"]
print("create free:", rf.status_code)

# 3. Import the feed (mock HTTP).
ca._feed_http_get = lambda url, timeout=10: RSS
ri = c.post(f"/communities/{cid}/import-feed", json={"owner_user_id": owner})
print("import-feed:", ri.status_code, ri.get_json())
ca._feed_http_get = None

# 4. Owner adds a hand link.
ra = c.post(f"/communities/{cid}/episodes", json={
    "owner_user_id": owner, "episodes": [{"title": "Live Stop", "audio_url": "https://h/live.mp3"}]})
print("add episode:", ra.status_code, ra.get_json())

# 5. Member buys a pass (stub) — ONE store product per PRICE; the length rides
#    on the request. Here the SAME audioura.pass.usd5 buys a MONTH in this
#    community.
member = "LIVE-690-member"
rp = c.post("/purchases/verify", json={
    "store": "stub", "transaction_id": "LIVE-690-txn-1",
    "product": "audioura.pass.usd5", "length": "month",
    "user_id": member, "community_id": cid})
print("buy pass ($5/month):", rp.status_code, rp.get_json().get("membership"))

# 5b. [LOCAL-690C] The SAME store product audioura.pass.usd5 buys a 1-DAY pass in
#     a SECOND community — one product per price serves every community AND every
#     length (D658 LEAD review). Two memberships, different durations.
r2 = c.post("/communities", json={
    "owner_user_id": owner, "name": "LIVE Day-pass Club", "is_paid": True,
    "pass_products": [{"product_id": "audioura.pass.usd5", "length": "day"}]})
cid2 = r2.get_json()["id"]
rp2 = c.post("/purchases/verify", json={
    "store": "stub", "transaction_id": "LIVE-690-txn-2",
    "product": "audioura.pass.usd5", "length": "day",
    "user_id": member, "community_id": cid2})
print("buy pass ($5/day, 2nd community, SAME product):", rp2.status_code,
      rp2.get_json().get("membership"))

# 6. Member lists episodes (active).
rl = c.get(f"/communities/{cid}/episodes?user_id={member}")
print("list episodes (active member):", rl.status_code, "count=", len(rl.get_json().get("episodes", [])))

# 7. Free join.
rj = c.post(f"/communities/{free_id}/join", json={"user_id": member})
print("free join:", rj.status_code)

# 8. Report → owner.
rr = c.post(f"/communities/{cid}/report", json={"user_id": member, "reason": "test"})
print("report:", rr.status_code, "owner=", rr.get_json().get("owner_user_id"))

# 9. Map list.
rm = c.get("/communities/map")
print("map:", rm.status_code, "listed=", [x["name"] for x in rm.get_json()["communities"]])

# 10. Reminders tick.
rt = c.post("/communities/reminders/run")
print("reminders:", rt.status_code, rt.get_json())

# Row counts.
import psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
print("\n=== ROW COUNTS (audiotours_local690) ===")
for t in ("communities", "community_pass_products", "community_passes",
          "community_memberships", "community_episodes", "community_reports",
          "purchases"):
    cur.execute(f"SELECT COUNT(*) FROM {t}")
    print(f"  {t}: {cur.fetchone()[0]}")
cur.close()
conn.close()
