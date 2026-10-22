# SUBMISSION: LOCAL-734 per_store purchase verification (finished by LEAD)

Kiro wrote the design and most of the code. Its route test hung three times, so LEAD took over on 2026-10-22.

**Root cause of the hang:** `tests/conftest.py` `_GuardedConnection` forwarded attribute reads (`__getattr__`) but not writes, so
`conn.autocommit = True` landed on the wrapper. The real connection stayed in a transaction holding a lock on `tour_unlocks`, and the app's
`ALTER TABLE tour_unlocks ADD COLUMN IF NOT EXISTS` (`_ensure_unlock_consumption_schema`) waited forever. Fixed with a `__setattr__` that
forwards public attributes. This affects every test that sets autocommit through the guard.

**What changed**
- `entitlements_api._verifier_for(store)`: one selector for every purchase path (level, tour; passes delegate to it from communities_api).
  In `per_store` mode: apple → JWS verifier; google → only with a Play service account, else refused; stub → only with
  `IAP_ALLOW_STUB_STORE=true` (default off; GCloud never sets it). The other modes are unchanged.
- `/purchases/mode` adds `platforms` ({ios, android}); the legacy `stub` field is true only in plain stub mode.
- App: `IapService.stubFromModeResponse` decides per platform. LEAD also switched the tour buy sheet and the community pass purchase from the
  device-side `isLocalStubMode()` to the server answer, otherwise the iPhone would still have used TEST PURCHASE on a local server.
- Price pickers: tours offer only the products that exist on the stores (usd3/5/10/20/50); passes only usd1/5/10/20. Existing priced tours
  keep their price.
- Override: user-api-2 `IAP_VERIFY_MODE: per_store`, `IAP_ALLOW_STUB_STORE: "true"`.
- LEAD: the route test inserts its throwaway tour with is_test=TRUE and deletes it only if it created it and is_test is confirmed (D141).

**Tests:** 25 pytest pass (route, verify, price ladder). Red test: with the stub gate removed, 3 tests fail. 93 Flutter purchase/plan tests
pass; analyze is clean on the touched files.
