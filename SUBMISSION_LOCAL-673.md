# SUBMISSION — LOCAL-673

**A daily paid-API spend STOP on the Mac: refuse paid calls once today's spend passes `$DAILY_PAID_LIMIT_USD`, and push-alert once.**

Agent: Mac Mini Kiro · Branch: `LOCAL-673-daily-limit` · Base: `subscribed` @ `09ca36b2`

---

## Why

Michael, 2026-10-10: *"Alerts would not do much if I am not at the desk."* An
email is not enough — a **stop** is needed. The network meter
(`_meter/paid_api_meter.py`, loaded in every process through `sitecustomize`)
already logs every paid call with its computed `$` into `paid_api_calls` and the
cost card now matches the bill (r5). LOCAL-673 turns that same ledger into a
hard daily cap: once today's billed spend reaches the limit, the next paid
request is refused **before it leaves the box**, and a single alert line is
written for LEAD's loop to push.

---

## What this does

`DAILY_PAID_LIMIT_USD` — **default unset = OFF** (LEAD sets `8`). When set to a
positive number, before any paid request (OpenAI, Gemini, Serper, and the
metered boto3 paths — AWS Translate, Polly) the meter reads today's
**America/New_York** total of billed (`status = 200`) `usd` in `paid_api_calls`
through a **60-second cached** query. If that total is **≥ the limit** it raises
`DailyPaidLimitExceeded` **without sending**. Callers already treat API failures
as failures, so the tour fails cleanly with an honest error rather than shipping
a half tour.

### The guarantee, step by step
1. **The STOP is before the send.** For OpenAI/Gemini/Serper the check sits
   inside the existing `requests.Session.send` / `urllib.urlopen` patches, in
   front of the real send — a test asserts the underlying send is **never
   reached** when over the limit. For AWS Translate and Polly (boto3, its own
   HTTP stack, which the network patch does **not** intercept) the check is
   called explicitly right before each boto3 paid call.
2. **Alert once per day.** When the limit trips, the meter writes
   `*** DAILY PAID LIMIT $X reached at HH:MM ***` to `ALERTS.md` (default
   `~/Audioura/.continuous_dev/ALERTS.md`; override with `ALERTS_MD`) **at most
   once per NY day**. A non-empty `ALERTS.md` is the signal LEAD's loop turns
   into a push.
3. **Same check in translation + polly-tts.** The translation service's AWS
   Translate and direct-Polly paths and `polly_tts_service`'s Polly synthesize
   path all call the check. `DailyPaidLimitExceeded` is a hard STOP, not a
   translation error: the translation AWS/LLM helpers now **re-raise** it instead
   of swallowing it into the original (untranslated) text, and the polly-tts
   endpoint surfaces it as an honest `500`.
4. **Fail-open on a meter error.** Any problem reading the limit or the DB → the
   check returns (allow) and logs to stderr. A meter bug or a DB outage must
   never block a tour. The limit is also OFF for `unset`, `""`, `<= 0`, and
   unparseable values.

Nothing is blocked that was not about to spend money: non-paid hosts are never
checked, and in polly-tts the free local Kokoro path is reached before the
check, so only an actual Polly bill is gated.

---

## Files

| File | Change |
|------|--------|
| `_meter/paid_api_meter.py` | **core.** New `DailyPaidLimitExceeded`; `_limit_usd()` (off unless a positive `DAILY_PAID_LIMIT_USD`); `_ny_now()` (zoneinfo `America/New_York`); `_query_today_total_usd(day)` = `SUM(usd) WHERE status=200 AND (ts AT TIME ZONE 'America/New_York')::date = day`; `_today_total_usd()` — a 60 s cache keyed on the NY day (re-queries at the day boundary even inside the TTL); `_write_alert_once()` — the once-per-NY-day `ALERTS.md` writer; `check_daily_limit()` — the public STOP, fail-open. The `send`/`urlopen` patches call it before any paid host. |
| `translation-service/translation_service.py` | Soft-import `check_daily_limit` + `DailyPaidLimitExceeded` (no-op fallback so a missing meter never breaks a translation). Check in `_aws_translate_call` (AWS Translate), `generate_audio` (direct Polly, before the `try` so the STOP propagates), and `_openai_chat` (belt-and-braces; the OpenAI path also hits the requests patch). `_translate_text_aws` / `_translate_text_llm` re-raise `DailyPaidLimitExceeded` instead of returning the untranslated original. |
| `polly_tts_service.py` | Same soft import. Check in `_render_chunk`, right before `polly_client.synthesize_speech` and only on the paid path (after the Kokoro fallback), so the free local engine is never blocked. The endpoint's trailing handler returns the STOP as a `500`. |
| `tests/test_local673_daily_paid_limit.py` | **new** — 20 hermetic tests (no DB, no paid call). |

---

## Design notes

- **Why read the ledger instead of counting in-process.** Spend is spread across
  many short-lived processes and containers; only the shared `paid_api_calls`
  table sees the whole day. The 60 s cache keeps the cost of the check at one
  small `SUM` per minute per process, not one per call.
- **Why `>=` and `status = 200`.** The cost card only bills successful (200)
  calls, so the cap counts exactly what the invoice counts. Reaching the limit
  (not strictly exceeding it) is the stop — `$8.00` of spend against an `$8`
  limit refuses the next call.
- **Why the NY day in SQL.** `ts` is `timestamptz`; converting it with
  `AT TIME ZONE 'America/New_York'` inside the query keeps the midnight boundary
  correct regardless of the DB session timezone, and the cache key is the same NY
  day string so the first check after midnight re-reads automatically.
- **Why fail-open.** The guard protects the wallet, but a false block would stop
  all production work on a meter hiccup. Michael's rule for the meter has always
  been "never raise into the caller"; the STOP is the one deliberate raise, and
  only when the ledger clearly says the cap is reached.

---

## Verification

```
$ python3 -m py_compile _meter/paid_api_meter.py \
      polly_tts_service.py translation-service/translation_service.py
COMPILE OK

$ python3 -m pytest tests/test_local673_daily_paid_limit.py -q
20 passed

$ python3 -m pytest tests/test_local578_translation_metering.py \
      tests/test_local60_cost_metering.py tests/test_local323_tts_metering.py -q
19 passed   # existing metering tests — no regressions
```

The 20 tests cover: limit OFF (unset / `0` / `-5` / `""` / unparseable);
under → allow; at/over → raise with a clear message; the `requests` patch
refusing an over-limit OpenAI call **before the real send** (and letting non-paid
hosts through); the 60 s cache reading the DB once and re-querying after the TTL;
the NY day-boundary re-query inside the TTL; fail-open on a DB error; the
once-per-day alert in the exact `*** DAILY PAID LIMIT $X reached at HH:MM ***`
format (and a fresh line on a new day); and the service wiring — translation's
AWS Translate and Polly paths refuse **without calling the boto3 client** and
propagate the STOP, while an under-limit call still goes through.

All tests are offline: the DB layer is monkeypatched, so no DB connection and
**no paid API call of any kind** is made.

---

## Scope / safety

Own containers only; no `audioura-*` container replaced. No GCloud. No `DELETE`.
`DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md` and
`.continuous_dev/STATUS.md` are untouched. The feature is OFF by default
(`DAILY_PAID_LIMIT_USD` unset), so nothing deployed changes until LEAD sets the
limit.

## Commits
- `0b6c795c` — meter: `DailyPaidLimitExceeded`, `check_daily_limit()`, 60 s NY-day cache, send/urlopen enforcement, once-per-day alert.
- `54e417d9` — enforce the limit on the boto3 paid paths (translation AWS Translate + Polly; polly-tts synthesize), re-raise the STOP cleanly.
- `38cb20c3` — 20 hermetic tests.
