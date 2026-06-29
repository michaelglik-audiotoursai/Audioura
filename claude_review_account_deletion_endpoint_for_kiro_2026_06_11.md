# FOR KIRO (Amazon-Q) — Server-Side Account-Deletion Endpoint (2026-06-11)

**Lane:** Cloud services (gateway + DB) — services only. **Author:** Claude.
**Why:** Apple/Google require in-app account & data deletion. The app calls one endpoint; the server must erase
**all** personal data for a `secret_id` and the route must be exposed through the gateway. Companion app doc:
`REVIEW_FOR_MOBILE_AQ_launch_gating_2026_06_11.md`.

## Current state
- A partial `delete_user(secret_id)` exists in the user-tracking service (`user-tracking/app.py:139`,
  `user_api_with_cors.py:160`) — but it lives in the tracking service and (a) is **not exposed in
  `gateway_routes.yaml`**, and (b) almost certainly deletes only tracking rows, not the user's tours, news,
  subscription credentials, or audio.
- So an app "Delete Account" tap has no single, complete, gateway-reachable endpoint to call.

## What to build
A single endpoint that **fully erases** everything tied to a `secret_id`, exposed via the gateway with `auth: api_key`.

### 1. Endpoint
`DELETE /delete-account/<secret_id>` on a service that already has DB access (the orchestrator is fine, or the
user-tracking service if you prefer — but it MUST be gateway-routed). Behavior: delete every personal-data row for
that `secret_id`, in one transaction, return `200 {"deleted": true}` (idempotent — deleting a non-existent user
also returns 200). Fail-closed: on DB error return 500 and delete nothing (no partial wipe).

### 2. Tables to purge (audit the schema and include every one keyed on `secret_id`/`device_id`)
At minimum:
```sql
BEGIN;
DELETE FROM user_subscription_credentials WHERE device_id = %(sid)s;   -- third-party logins (most sensitive)
DELETE FROM tour_requests              WHERE secret_id = %(sid)s;
DELETE FROM article_requests           WHERE secret_id = %(sid)s;
DELETE FROM coordinates                WHERE secret_id = %(sid)s;
DELETE FROM map_requests               WHERE secret_id = %(sid)s;
-- audio_tours / news_audios / newsletters: delete rows linked to this user's tours/articles
--   (follow the FKs; delete children before parents)
DELETE FROM users                      WHERE secret_id = %(sid)s;
COMMIT;
```
> Action: grep the schema for **every** table with `secret_id` or `device_id` and include it. Don't miss
> `user_subscription_credentials` — leaving a user's newspaper password behind after "delete account" is the worst
> possible miss for review and privacy.

### 3. Also delete blob/object storage
If tours/audio are stored in R2/GCS (not just DB), delete those objects for the user too, or document why they
expire. The privacy policy promises deletion — make it true end-to-end.

### 4. Gateway route
Add to `api-gateway/gateway_routes.yaml` (root path, `auth: api_key`, fail-closed):
```yaml
  - public_path: /delete-account/<secret_id>
    backend: <orchestrator-or-tracking>
    upstream: /delete-account/<secret_id>
    methods: [DELETE]
    auth: api_key
```
Confirm the backend service actually serves the method/path (remember: reachable locally ≠ on cloud unless it's in the YAML).

## Tests / acceptance
- `DELETE /delete-account/<sid>` for a user with data across all tables → `200 {"deleted":true}`, and a follow-up
  `SELECT COUNT(*)` on every listed table for that `sid` returns **0** (including `user_subscription_credentials`).
- Deleting a non-existent `sid` → still `200` (idempotent), nothing else affected.
- DB error mid-delete → 500 and **transaction rolled back** (no partial deletion).
- Endpoint reachable through `api.audioura.com` with the API key (gateway route works), 401 without/with wrong key.
- Object storage: the user's stored audio/tour blobs are gone (or documented as auto-expiring).

## Out of scope
App UI/flow is Mobile-AQ. This doc is the server endpoint + gateway route + full-erase SQL only.
