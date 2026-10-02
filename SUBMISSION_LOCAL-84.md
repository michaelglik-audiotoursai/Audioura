##### READY FOR REVIEW

# LOCAL-84 · Watch a real tour request debit a real wallet

**Branch:** `kiro/local84-http-charging-proof`  
**Base:** `subscribed`

---

## Summary

Proved that a real HTTP tour generation request through the orchestrator
actually debits a real wallet. This was the "last inch" that LOCAL-83
explicitly left unproven. **It works. The billing pipeline is end-to-end
functional.**

---

## Evidence: Full HTTP Request/Response Cycle

### Test 1: PPU Fresh Generation

```
POST /generate-complete-tour
  user_id: local84-ppu-b05f273c
  location: "Larz Anderson Park, Brookline MA"
  tour_type: "nature"
  total_stops: 5

Response 200:
  {"job_id": "44c81564-d1a4-478d-a35f-e04eaf5e976b", "language": "en", "status": "queued"}

Poll /status/44c81564... → completed after 50s
```

### Test 2: PPU Cache Hit

```
POST /generate-complete-tour (same params as Test 1)

Response 200:
  {"job_id": "a8dbc1d1-2241-460d-bd99-dcc414a34daa", "language": "en", "status": "queued"}

Poll /status/a8dbc1d1... → completed after 20s (faster — cache hit)
```

### Test 3: Unlimited User

```
POST /generate-complete-tour
  user_id: local84-unlimited-b05f273c
  location: "Arnold Arboretum, Jamaica Plain, Boston MA"
  tour_type: "nature"
  total_stops: 5

Response 200:
  {"job_id": "1995d783-79d8-4905-9efa-96e67b058e15", "language": "en", "status": "queued"}

Poll /status/1995d783... → completed after 75s
```

---

## Database Assertions (Step 4) — Actual Numbers

### 4a. cost_ledger row

| Field | Value |
|-------|-------|
| operation_type | `tour_generate` |
| our_cost_usd | `$0.028026` |
| cache_hit | `false` |
| job_id | `9a89d921-521e-4479-9ab7-82b666d56065` |

### 4b. wallet_ledger charge = cost × 5

```
our_cost:       $0.028026
× multiplier:  5.0
= user_charge: $0.14013 → rounds to $0.14 (banker's rounding)
actual charge: -14¢ ✓
```

### 4c. Balance decreased by charge amount

```
Initial balance:  500¢ ($5.00)
Charge:          -14¢ ($0.14)
Expected balance: 486¢ ($4.86)
Actual balance:   486¢ ✓
```

### 4d. GET /wallet/<user> reports same balance

```json
{
  "balance_usd": 4.86,
  "plan": "ppu",
  "period_spend_usd": 0.14,
  "low_balance": false,
  "cost_stop_progress": null
}
```

Balance from API (486¢) = Balance from DB (486¢) ✓

### 4e. Transaction description is human-readable

```
"Tour: Larz Anderson Park, Brookline MA — $0.14"
```

---

## Step 5: Cache Hit — Balance Unchanged to the Cent

```
Balance before cache-hit request: 486¢
POST same request → completed (20s, cache hit)

cost_ledger:
  operation_type: tour_cache_hit
  our_cost_usd:  $0.000000
  cache_hit:     true

Balance after:  486¢
Difference:     0¢ ✓

GET /wallet reports: 486¢ ✓
```

**Cache hit confirmed: $0.00 charge, zero balance movement.**

---

## Step 6: Unlimited User

```
monthly_cost_spent_cents before: 0

POST /generate-complete-tour → completed (75s)

cost_ledger:
  operation_type: tour_generate
  our_cost_usd:  $0.029662
  cache_hit:     false

monthly_cost_spent_cents after: 3 (rise = 3¢)
wallet_ledger charge:          None (no wallet charge for unlimited) ✓
cost rise matches our_cost:    3¢ = round($0.029662 × 100) ✓
```

---

## API Spend Report

| Tour | Our Cost | User Charged | Type |
|------|----------|-------------|------|
| PPU fresh (Larz Anderson) | $0.028026 | $0.14 | Fresh generation |
| PPU cached (same) | $0.000000 | $0.00 | Cache hit |
| Unlimited (Arnold Arboretum) | $0.029662 | N/A (tracked) | Fresh generation |

**Total API spend: $0.058** (ceiling: $1.30/tour × 2 fresh = $2.60 budget → well under)

---

## Test Results

```
23/23 passed, 0 failed

✓ wallet API shows initial balance
✓ POST /generate-complete-tour returns 200
✓ Tour generation completed
✓ cost_ledger row exists
✓ cost_ledger cache_hit=false
✓ cost_ledger our_cost under ceiling
✓ wallet_ledger charge row exists
✓ wallet_ledger charge = cost × 5
✓ balance decreased by charge amount
✓ GET /wallet reports correct balance
✓ transaction description is human-readable
✓ POST returns 200 for cached request
✓ Cached tour generation completed
✓ cost_ledger shows cache_hit=true
✓ balance UNCHANGED after cache hit
✓ GET /wallet unchanged after cache hit
✓ POST returns 200 for unlimited user
✓ Unlimited tour generation completed
✓ cost_ledger row exists for unlimited
✓ cost under ceiling
✓ monthly_cost_spent_cents increased
✓ cost rise matches our_cost
✓ NO wallet_ledger charge for unlimited
```

---

## Infrastructure Note

The existing Docker containers had two issues that prevented the test from
working out-of-the-box:

1. **Tour-generator container was built from pre-LOCAL-83 code** — the
   LOCAL-83 charging wire (`wallet_ledger.charge()`, `record_unlimited_cost()`)
   was not present in the running container image. Rebuilt from the current
   branch to include the charging code.

2. **Orchestrator DNS misconfiguration** — `TOUR_GENERATOR_URL` defaulted to
   `http://development-tour-generator-1:5000` but the actual container name
   on the Docker network is `audioura-tour-generator-1`. Fixed by restarting
   with correct env vars.

3. **Tour cache required `DATABASE_URL`** — without it, the cache check was
   silently skipped (`[S20] DATABASE_URL not set — cache skipped`).

These are deployment/configuration issues, not code bugs. The billing code
itself is correct once the containers are properly configured.

---

## Limitations

1. **Real IAP remains stubbed by design.** Apple/Google In-App Purchase
   integration uses a `PaymentProvider` interface with a working fake.
   Real IAP validation requires App Store credentials and live devices.
   This is architecturally correct and intentional (per SUBSCRIBED_DESIGN.md).

2. **Tour cache is shared across users.** The cache is keyed on
   `(location, tour_type, total_stops)` — not on user_id. A PPU user's
   generation populates the cache for all subsequent users. This is correct
   behavior (cache hits are free for everyone), but means the "unlimited
   fresh generation" test required a different location than the PPU test.

3. **Job ID mismatch between orchestrator and tour-generator.** The
   orchestrator creates its own job_id for tracking, and the tour-generator
   creates a separate internal job_id. The cost_ledger and wallet_ledger
   use the tour-generator's job_id. This doesn't affect correctness but
   means correlating billing rows to client-visible job_ids requires a
   join through the orchestrator's job state.

4. **Container image rebuild required.** The charging code from LOCAL-83
   must be in the running container image. If the containers are rebuilt
   from the `subscribed` branch (which includes LOCAL-83), this works
   automatically. The current deployed images were from a pre-LOCAL-83 build.

---

## Files Changed

| File | Change |
|------|--------|
| `tests/test_local84_http_charging_proof.py` | +283 lines — end-to-end HTTP charging proof test |
| `SUBMISSION_LOCAL-84.md` | This file |
