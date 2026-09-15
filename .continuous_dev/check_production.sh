#!/bin/zsh
# Watch PRODUCTION — the hosts testers actually use.
#
# WHY THIS EXISTS: on 2026-09-11 audioura.com lapsed. Network Solutions moved
# the nameservers to NS1.PENDINGRENEWALDELETION.COM, every hostname resolved to
# a parking IP, and BOTH tracks went dark for every tester on both platforms.
# Nobody noticed for THREE DAYS — Michael found it by trying to use the app in
# Nice.
#
# Nothing here was watching production. check_user_visible.sh polls
# http://localhost:5005 — this machine's own container. It would have stayed
# green through the entire outage, and did.
#
# Two failures, deliberately separate:
#   1. REACHABILITY — is the gateway answering right now? (minutes of warning)
#   2. EXPIRY       — is the domain about to lapse?       (weeks of warning)
# The second is the one that would have prevented this outage entirely.

CD="$HOME/Audioura/.continuous_dev"
ALERTS="$CD/ALERTS.md"
STAMP="$CD/.last_expiry_check"

alert() { echo "$(date -u +%FT%TZ) | *** $1 ***" >> "$ALERTS"; }

# ---------- 1. REACHABILITY, both tracks ----------
# Health only. No API key, no tour data, nothing that costs money or writes.
for HOST in api.audioura.com storied-api.audioura.com; do
  IP=$(dig +short "$HOST" @8.8.8.8 2>/dev/null | grep -E '^[0-9]+\.' | head -1)

  if [ -z "$IP" ]; then
    alert "PRODUCTION DNS DEAD: $HOST does not resolve"
    continue
  fi

  # 208.91.197.* is Confluence Networks — the parking range this domain landed
  # in. Checked by name, not by IP: a parked host still answers, so a bare
  # connectivity test looks healthy while the API is gone.
  case "$IP" in
    208.91.197.*) alert "PRODUCTION PARKED: $HOST -> $IP (registrar parking; domain likely lapsed)" ;;
  esac

  CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "https://$HOST/health" 2>/dev/null)
  if [ "$CODE" != "200" ]; then
    alert "PRODUCTION DOWN: $HOST/health returned HTTP ${CODE:-no-response}"
  fi
done

# ---------- 2. NAMESERVERS ----------
# The outage's actual mechanism. The registry still said ACTIVE with an expiry a
# YEAR AWAY while this was true, so expiry alone would not have caught it.
NS=$(whois audioura.com 2>/dev/null | grep -i "Name Server" | head -1 | tr '[:upper:]' '[:lower:]')
case "$NS" in
  *pendingrenewaldeletion*|*parking*|*sedo*)
    alert "DOMAIN PARKED AT REGISTRAR: nameservers are $NS — pay the registrar, DNS returns on payment" ;;
esac

# ---------- 3. EXPIRY, once a day ----------
# whois is rate-limited and the answer changes at most daily.
TODAY=$(date -u +%F)
if [ "$(cat "$STAMP" 2>/dev/null)" != "$TODAY" ]; then
  echo "$TODAY" > "$STAMP"
  EXP=$(whois audioura.com 2>/dev/null | grep -i "Registry Expiry Date:" | head -1 | sed 's/.*: *//' | cut -dT -f1)
  if [ -n "$EXP" ]; then
    EXP_S=$(date -j -f "%Y-%m-%d" "$EXP" "+%s" 2>/dev/null)
    NOW_S=$(date "+%s")
    if [ -n "$EXP_S" ]; then
      DAYS=$(( (EXP_S - NOW_S) / 86400 ))
      # Escalating, so a single ignored warning is not the only one.
      if   [ "$DAYS" -lt 0 ]  ; then alert "DOMAIN EXPIRED $((0-DAYS)) DAYS AGO — audioura.com"
      elif [ "$DAYS" -le 7 ]  ; then alert "DOMAIN EXPIRES IN $DAYS DAYS — audioura.com ($EXP)"
      elif [ "$DAYS" -le 14 ] ; then alert "Domain expires in $DAYS days — audioura.com ($EXP)"
      elif [ "$DAYS" -le 30 ] ; then alert "Domain expires in $DAYS days — audioura.com ($EXP)"
      elif [ "$DAYS" -le 60 ] ; then alert "Domain expires in $DAYS days — audioura.com ($EXP)"
      fi
    fi
  else
    alert "DOMAIN EXPIRY UNKNOWN: whois returned no expiry for audioura.com"
  fi
fi
