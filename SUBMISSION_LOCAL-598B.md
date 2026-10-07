# SUBMISSION — LOCAL-598B — levels r2

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-598B-levels-hardening` (from `subscribed` @ `2f69541`)
**Base:** subscribed — verified `git merge-base --is-ancestor 2f69541 HEAD` exits 0.

Addresses the two LEAD review findings on the merged LOCAL-598:
1. the Apple JWS verifier pinned Root CA G3 but did not check Apple's IAP
   purpose OIDs (so any cert chaining to G3 would verify);
2. the entitlements/queue API returned 503 `service_misconfigured` on the
   LOCAL Mac Mini stack, where there is no `GATEWAY_API_KEY` and the app sends
   no `X-API-Key`.

---

## 1. Apple JWS verifier hardening — `user-tracking/apple_jws_verifier.py`

Pinning Apple Root CA G3 is necessary but **not** sufficient: Apple issues many
certificate kinds that all chain to Root CA G3 (e.g. Apple Pay merchant certs
held by any developer). A JWS signed with such a cert previously verified. The
verifier now additionally enforces, matching Apple's App Store Server Library:

| Check | Where | Error `.code` |
|---|---|---|
| **leaf** carries OID `1.2.840.113635.100.6.11.1` | `_verify_chain` | `leaf_oid_missing` |
| **intermediate** carries OID `1.2.840.113635.100.6.2.1` | `_verify_chain` | `intermediate_oid_missing` |
| chain is **exactly 3** certs (leaf, intermediate, root) | `_verify_chain` | `chain_length_invalid` |
| every cert valid **at `signedDate`** (fallback: now) | `_verify_chain` | `cert_expired` |
| payload `environment` == expected (when supplied) | entry point | `environment_mismatch` |
| payload has **no** `revocationDate` | entry point | `transaction_revoked` |

Details:
- New module constants `APPLE_LEAF_OID`, `APPLE_INTERMEDIATE_OID`,
  `APPLE_CHAIN_LENGTH = 3`.
- New helpers: `_has_extension_oid` (presence check for Apple's private
  extension OIDs via `extensions.get_extension_for_oid`), `_cert_valid_at`
  (tz-aware, works across `cryptography` versions), `_parse_signed_date`
  (`signedDate` is epoch **milliseconds**).
- `signedDate` is read once *before* signature verification **only** to choose
  the cert-validity reference time; it is never trusted for a grant decision
  (any tampering fails the ES256 signature check that follows). Using the
  signing time means a cert valid when Apple signed is still accepted after it
  later expires — the same behaviour as Apple's library.
- `verify_signed_transaction` gained `expected_environment: Optional[str]`;
  `VerifiedTransaction` gained an `environment` field.
- The HTTP layer (`entitlements_api.verify_purchase`) passes
  `expected_environment=(APPLE_IAP_ENVIRONMENT or None)` — empty env disables
  the environment check (keeps stub-mode tests working).

### Tests — `user-tracking/test_local598_apple_jws.py`
Test PKI helpers now stamp the Apple purpose OIDs on the leaf/intermediate by
default (so the happy path still passes), with knobs to omit an OID, forge an
expired leaf, or present a wrong-length `x5c`. New cases, each breaking exactly
one requirement under a correctly-pinned test root:

- `test_leaf_missing_oid_rejected` → `leaf_oid_missing`
- `test_intermediate_missing_oid_rejected` → `intermediate_oid_missing`
- `test_expired_leaf_rejected` → `cert_expired`
- `test_leaf_valid_at_signeddate_accepted` → verifies (expired *now* but valid
  at `signedDate`; proves the reference time is honoured)
- `test_chain_length_two_rejected` / `test_chain_length_four_rejected` →
  `chain_length_invalid`
- `test_wrong_environment_rejected` → `environment_mismatch`
- `test_matching_environment_accepted` → verifies
- `test_revoked_transaction_rejected` → `transaction_revoked`

```
cd user-tracking && python3 -m pytest test_local598_apple_jws.py -q
17 passed in 0.04s
```
(Also passes under the bare runner: `python3 test_local598_apple_jws.py` → `17/17 passed`.)

---

## 2. Local-only unauthenticated bypass — `user-tracking/entitlements_api.py`

Follows the ST-4 `ALLOW_UNAUTHENTICATED_SHARING` precedent
(`sharing_endpoints.py`) **exactly**:

- New `_unauthenticated_entitlements_allowed()` reads
  `ALLOW_UNAUTHENTICATED_ENTITLEMENTS` **live** (truthy = `true`/`1`/`yes`).
- `_require_api_key()`: when — and **only when** — `GATEWAY_API_KEY` is empty,
  the flag opens the gate; otherwise the fail-closed **503**
  `service_misconfigured` remains. When a key *is* configured the flag is never
  consulted, so it can never weaken real auth.
- A **loud startup warning** is logged at import when (no key **and** flag on),
  naming the flag and stating it is LOCAL DEVELOPMENT ONLY.
- Never defaults on. Cloud has a real `GATEWAY_API_KEY`, so this branch is
  unreachable there.

### Tests — `user-tracking/test_local598b_entitlements_auth.py`
Flask test-client against the real `_require_api_key` (no Postgres needed):

- `test_key_set_requires_header` — key set: no/blank/wrong header → **401**,
  correct header → **200**.
- `test_key_set_flag_on_still_requires_header` — key set + flag on → still
  **401** (flag ignored when a key exists).
- `test_key_empty_flag_off_is_503` / `test_key_empty_flag_explicit_false_is_503`
  — key empty, flag off/`false` → **503**, no warning.
- `test_key_empty_flag_on_allows_and_warns` — key empty + flag on → **200** and
  a startup WARNING naming the flag was logged.

```
cd user-tracking && python3 -m pytest test_local598b_entitlements_auth.py -q
5 passed in 0.06s
```
(Also passes under the bare runner → `5/5 passed`. Combined
`test_local598_apple_jws.py + test_local598b_entitlements_auth.py` → 22 passed.)

---

## 3. Env lines LEAD must add — **do NOT** edit `docker-compose.subscribed-local.yml`

Per the task I did not edit the compose override. The base
`docker-compose-master.yml` `user-api-2` service sets no `GATEWAY_API_KEY`
(hence the empty-key path), and the current `docker-compose.subscribed-local.yml`
has **no** `user-api-2` block at all. LEAD must add a `user-api-2` override with
these two env entries so the LOCAL stack serves the entitlements/queue API and
pins the Sandbox environment:

```yaml
# docker-compose.subscribed-local.yml  (under services:)
  user-api-2:
    environment:
      - ALLOW_UNAUTHENTICATED_ENTITLEMENTS=true
      - APPLE_IAP_ENVIRONMENT=Sandbox
```

Notes for LEAD:
- The base block uses the mapping form (`DATABASE_URL: ...`); the list form
  above merges fine, but either style works — the two keys are what matter.
- `ALLOW_UNAUTHENTICATED_ENTITLEMENTS=true` is honoured **only** because the
  LOCAL `user-api-2` has no `GATEWAY_API_KEY`. **LOCAL ONLY** — never set it
  anywhere the API is reachable from untrusted networks. On a build that *does*
  set `GATEWAY_API_KEY`, this flag is inert and the header stays required.
- `APPLE_IAP_ENVIRONMENT=Sandbox` locally; set it to `Production` for the live
  App Store. Leave it unset to skip the environment check (e.g. stub mode).

---

## 4. `tests/test_local59[5-7]_*` — exits (pytest `-q`, this branch)

```
EXIT=0  tests/test_local595_anniversary.py       ::  18 passed in 0.12s
EXIT=0  tests/test_local595_api.py               ::  10 passed in 0.31s
EXIT=0  tests/test_local595_edit_gate.py         ::   8 passed in 0.22s
EXIT=0  tests/test_local595_enforcement.py       ::  31 passed in 1.34s
EXIT=0  tests/test_local596_api.py               ::  11 passed in 0.43s
EXIT=5  tests/test_local596_mirror_in_sync.py    ::  no tests ran in 0.11s
EXIT=0  tests/test_local596_referral.py          ::   9 passed in 0.44s
EXIT=0  tests/test_local596_seats.py             ::  12 passed in 0.33s
EXIT=0  tests/test_local597_by_reference.py      ::   9 passed, 1 warning in 2.52s
EXIT=0  tests/test_local597_guard.py             ::  13 passed, 1 warning in 3.01s
```

`test_local596_mirror_in_sync.py` is a plain script (no `test_` functions), so
pytest collects nothing → exit **5** ("no tests collected"), not a failure. Run
directly it passes (I did not touch either `l2_seats.py`):

```
python3 tests/test_local596_mirror_in_sync.py
PASS: l2_seats.py mirror in sync   (EXIT=0)
```

All suites green.

---

## Live run
Not performed in this session: the LOCAL stack's `user-api-2`/`postgres-2`
containers are owned by Michael's `audioura-*` project, which the task forbids
touching (no `audioura-*` containers, no DELETE, no GCloud). The auth-gate and
verifier behaviour is fully covered by the unit/integration tests above, which
run with no Postgres. A self-contained `docker run --rm --name local598b-userapi …`
smoke test can be added if LEAD wants an on-container check before enabling the
flag in the override.

## Files changed
- `user-tracking/apple_jws_verifier.py` — OID/chain-length/validity/environment/
  revocation checks.
- `user-tracking/entitlements_api.py` — `APPLE_IAP_ENVIRONMENT` wiring + the
  `ALLOW_UNAUTHENTICATED_ENTITLEMENTS` bypass and startup warning.
- `user-tracking/test_local598_apple_jws.py` — hardening test matrix (17 tests).
- `user-tracking/test_local598b_entitlements_auth.py` — auth-gate/bypass tests
  (5 tests).

No edits to `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`,
`SUBSCRIPTION_LEVELS.md`, `.continuous_dev/STATUS.md`, or
`docker-compose.subscribed-local.yml`.
