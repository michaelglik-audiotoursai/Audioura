# Contract: POST /tour-status — For Mobile Amazon-Q

**Date:** 2026-06-03  
**Service:** tour-orchestrator (via api-gateway)  
**Replaces:** Direct SQL updates to `tour_requests` table via `:5003/execute_sql`

---

## Endpoint

```
POST https://<gateway-url>/tour-status
Content-Type: application/json
```

## Request Body

```json
{
    "tour_id": "tour_19837aeeb8a",
    "status": "started|completed|failed|processing"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tour_id` | string | Yes | The `tour_id` value from `tour_requests` table. This is the ID the app generates locally (format: `tour_XXXXXXXXXXX`). |
| `status` | string | Yes | One of: `started`, `processing`, `completed`, `failed` |

## Response (Success)

```json
{
    "status": "success",
    "tour_id": "tour_19837aeeb8a",
    "rows_affected": 1
}
```

## Response (Errors)

```json
// Missing fields:
{"status": "error", "message": "tour_id and status are required"}  // 400

// Invalid status value:
{"status": "error", "message": "status must be one of: ('started', 'processing', 'completed', 'failed')"}  // 400

// Server error:
{"status": "error", "message": "<error details>"}  // 500
```

## Behavior

- Updates the `tour_requests` row matching `WHERE tour_id = <tour_id>`
- When `status = "completed"`: also sets `finished_at = NOW()`
- Returns `rows_affected: 0` if no matching row (not an error — HTTP 200 still)
- Returns `rows_affected: 1` on successful update

## Key Difference from Old Path

The **old** client-side SQL path (`DirectDbUpdate` → `:5003`) matched on `request_string`. The **new** REST endpoint matches on `tour_id`. The app must send the `tour_id` value it generated when creating the `tour_requests` entry (the `tour_XXXXXXXXXXX` format string).

## Verified

```
POST /tour-status {"tour_id":"tour_19837aeeb8a","status":"completed"}
→ {"rows_affected":1,"status":"success","tour_id":"tour_19837aeeb8a"}
```

## Migration Steps for Mobile-AQ

1. Replace all `DirectDbUpdate` / `direct_db_update` / raw SQL calls with a single `POST /tour-status` call
2. Send `tour_id` (not `request_string`) as the identifier
3. Delete the 6 duplicate raw-SQL updater classes
4. Never deploy `:5003/execute_sql` publicly
