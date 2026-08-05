#!/bin/zsh
# Health check that does NOT depend on the docker CLI.
#
# WHY: on 2026-08-03 07:40 the Docker management API wedged — `docker ps`
# timed out at 60s — while every container kept serving normally (5002,
# 5005, 5022, 5102 all returned 200). Every existing guard shells out to
# `docker exec ... psql`, so they all hung too, and a 5-minute status check
# timed out having told us nothing.
#
# The containers are reachable over their published ports and Postgres is
# reachable on localhost:5433. Neither needs the docker CLI. Check the
# system the way its users do, not the way its operator usually does.

cd "$HOME/Audioura" || exit 1

echo "--- services (as the app sees them) ---"
for p in 5002 5005 5022 5102; do
  code=$(curl -s -m 8 -o /dev/null -w '%{http_code}' "http://localhost:$p/health" 2>/dev/null)
  echo "  port $p -> ${code:-unreachable}"
done

echo "--- database (direct, no docker exec) ---"
/usr/bin/python3 - <<'PY'
import psycopg2
try:
    c = psycopg2.connect(host='localhost', port=5433, dbname='audiotours',
                         user='admin', password='password123', connect_timeout=10)
    cur = c.cursor()
    for q, label in [("SELECT count(*) FROM audio_tours", "audio_tours"),
                     ("SELECT count(*) FROM user_subscription_credentials", "credentials"),
                     ("SELECT count(*) FROM wallet_ledger", "wallet_ledger")]:
        cur.execute(q); print(f"  {label}: {cur.fetchone()[0]}")
    cur.execute("""SELECT count(*) FROM audio_tours
                   WHERE tour_name ~ '(LOCAL[0-9]+|Regression Test|Acceptance Test|Selective Test|NoFlag Test)'
                     AND is_test IS NOT TRUE""")
    n = cur.fetchone()[0]
    print(f"  unflagged test tours: {n}" + ("  *** USER-VISIBLE DRIFT ***" if n else "  (clean)"))
    c.close()
except Exception as e:
    print("  DB UNREACHABLE:", e)
PY

echo "--- docker CLI responsiveness (informational only) ---"
/usr/bin/python3 -c "
import subprocess
try:
    subprocess.run(['docker','ps','-q'],capture_output=True,timeout=15)
    print('  docker CLI: responsive')
except subprocess.TimeoutExpired:
    print('  docker CLI: WEDGED (containers may still be fine — see ports above)')
"
