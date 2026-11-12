# SUBMISSION — LOCAL-899 (proof is_test on the Subscribed orchestrator)

Branch: `LOCAL-899-proof-is-test` (base subscribed 1cbbcb83; `git merge-base --is-ancestor 1cbbcb83 HEAD` = 0). Cost: $0 (no tour generation, no paid API).

## Change (`tour_orchestrator_service.py`, `/generate-complete-tour`)
- New `_is_proof_test_user(user_id)`: true when user_id is in env `TOUR_TEST_PROOF_USER_IDS` (comma-separated, whitespace-trimmed, default empty).
- New `_is_test_truthy(raw)`: strict parse for the proof path (True, or 'true'/'1'/'yes'); `"false"`/`"0"`/None/False never count.
- is_test is now honored when (a) the existing `TOUR_TEST_MODE` / `TOUR_TEST_MODE_ALLOW_REQUEST` path applies (unchanged), OR (b) the caller is allow-listed AND sent a truthy is_test. Otherwise `None` (server default), so is_test=false stays false and unlisted users still cannot set it (LOCAL-103 trust boundary).
- Log line: `is_test: <v> (raw=…, server_mode=…, allow_request=…, proof_user=…)`.
- The resolved flag already flows to the store paths (LOCAL-856), so the ~line 1752 test-vs-real overwrite guard now fires for proofs.

## Tests — `python3 tests/test_local899_proof_is_test.py` → 7 tests OK
Flask test client against `/generate-complete-tour` (stops at the language gate, no generation): listed user true → True; listed among many; unlisted → None/false; env unset → None; listed + false/None/"false"/"0" → None; TOUR_TEST_MODE / ALLOW_REQUEST paths unchanged; empty user never listed.

## ENV CHANGE FOR GCLOUD (needs Michael's OK; LEAD handles)
Set on tour-orchestrator-subscribed:

    TOUR_TEST_PROOF_USER_IDS=USER-1073427300

Not verified: a live cloud run (out of scope, $0).
