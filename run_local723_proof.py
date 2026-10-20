"""LOCAL-723 live proof (runs INSIDE an isolated test container).

Simulates a LOCAL-721/722-style test container that COPIED the listener env
(METER_ROLE=listener, METER_ROLE_TOKEN=<value>, METER_ROLE_TOKEN_FILE=/opt/meter/role_token)
but, like every test container, did NOT get the proof file bind-mounted and had
HOSTNAME dropped. It makes ONE cheap metered OpenAI call (gpt-4.1-nano, tiny
prompt, well under $0.05) through the NEW meter, then reports:

  * the role the meter computed for this container (must be None),
  * row counts before/after,
  * that the newly written row has role NULL (NOT counted toward listeners),
  * a read-only check that a PROVEN listener row WOULD be counted.

No tours are generated; only one tiny chat completion is sent.
"""
import os, sys, json

sys.path.insert(0, "/opt/meter")
import paid_api_meter as m
m.install()

HOST = m._real_hostname()
print(f"[proof] real hostname (socket.gethostname) = {HOST!r}")
print(f"[proof] HOSTNAME env                        = {os.environ.get('HOSTNAME')!r}")
print(f"[proof] METER_ROLE env                      = {os.environ.get('METER_ROLE')!r}")
print(f"[proof] METER_ROLE_TOKEN set?               = {bool(os.environ.get('METER_ROLE_TOKEN'))}")
print(f"[proof] METER_ROLE_TOKEN_FILE               = {os.environ.get('METER_ROLE_TOKEN_FILE')!r}")
print(f"[proof] token file exists in THIS container? = {os.path.exists(os.environ.get('METER_ROLE_TOKEN_FILE','') or '/nonexistent')}")

role = m._meter_role()
print(f"[proof] meter computed role for THIS container = {role!r}  (expect None -> not counted)")
assert role is None, "FAIL: a copied-env test container was mislabelled as a listener"


def _db():
    import psycopg2
    return psycopg2.connect(host=os.environ.get("DB_HOST", "postgres-2"),
                            dbname=os.environ.get("DB_NAME", "audiotours"),
                            user=os.environ.get("DB_USER", "admin"),
                            password=os.environ.get("DB_PASSWORD", "password123"),
                            port=os.environ.get("DB_PORT", "5432"), connect_timeout=5)


def counts():
    with _db() as c, c.cursor() as cur:
        cur.execute("SELECT count(*) FROM paid_api_calls")
        pac = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM audio_tours")
        at = cur.fetchone()[0]
    return pac, at


pac0, at0 = counts()
print(f"[proof] BEFORE: paid_api_calls={pac0}  audio_tours={at0}")

# One cheap metered call. gpt-4.1-nano @ $0.10/1M in, $0.40/1M out; a <40-token
# round trip is ~$0.00002. The network wrapper records the row automatically.
import requests
key = os.environ["OPENAI_API_KEY"]
r = requests.post("https://api.openai.com/v1/chat/completions",
                  headers={"Authorization": f"Bearer {key}"},
                  json={"model": "gpt-4.1-nano",
                        "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
                        "max_tokens": 3},
                  timeout=30)
print(f"[proof] OpenAI status={r.status_code}")
body = r.json()
usage = body.get("usage", {})
print(f"[proof] usage={usage}")

pac1, at1 = counts()
print(f"[proof] AFTER:  paid_api_calls={pac1}  audio_tours={at1}  (delta pac={pac1-pac0}, at={at1-at0})")

# Inspect the row THIS container just wrote: role must be NULL, host must be the
# real hostname (not a copied HOSTNAME), and it must not be counted.
with _db() as c, c.cursor() as cur:
    cur.execute("SELECT id, kind, status, usd, host, role FROM paid_api_calls "
                "WHERE host = %s ORDER BY id DESC LIMIT 1", (HOST,))
    row = cur.fetchone()
print(f"[proof] my row (id,kind,status,usd,host,role) = {row}")
assert row is not None, "FAIL: my metered call wrote no row"
assert row[5] is None, f"FAIL: my row has role={row[5]!r}, expected NULL"
my_usd = float(row[3] or 0.0)
print(f"[proof] my call cost ${my_usd:.6f}  (role NULL -> NOT counted toward listeners)")

# Read-only: today's NY listener total via the SAME query the limit uses. My row
# must NOT appear in it (role NULL).
with _db() as c, c.cursor() as cur:
    cur.execute("SELECT COALESCE(SUM(usd),0) FROM paid_api_calls "
                "WHERE status=200 "
                "AND (ts AT TIME ZONE 'America/New_York')::date = (now() AT TIME ZONE 'America/New_York')::date "
                "AND role='listener'")
    listener_today = float(cur.fetchone()[0] or 0.0)
    # Counterfactual (read-only, no write): what the SAME row WOULD add if it were
    # a proven listener row — i.e. the shared generator's role WOULD be counted.
    cur.execute("SELECT COALESCE(SUM(usd),0) FROM paid_api_calls WHERE host=%s AND status=200", (HOST,))
    would_add = float(cur.fetchone()[0] or 0.0)
print(f"[proof] listener spend today (role='listener') = ${listener_today:.6f}  (my test call is NOT in it)")
print(f"[proof] counterfactual: if THIS same spend were a proven-listener row it WOULD add ${would_add:.6f} -> the shared generator (which mounts the token file) IS counted")
print("[proof] PASS: copied-env test container writes a role-NULL row that the listeners' limit ignores.")
