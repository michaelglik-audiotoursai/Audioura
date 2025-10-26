# User Tracking API

This API tracks user interactions with the Audio Tour app.

## New Endpoints

### Execute SQL

```
POST /sql
```

Execute SQL directly on the database.

**Request Body:**
```json
{
  "sql": "UPDATE tour_requests SET status = 'completed', finished_at = '2025-07-17T22:00:24.781339' WHERE tour_id = 'tour_1981b2356dc'"
}
```

**Response:**
```json
{
  "status": "success",
  "rows_affected": 1
}
```

### Update Tour

```
POST /update_tour
```

Update tour status directly.

**Request Body:**
```json
{
  "tour_id": "tour_1981b2356dc",
  "status": "completed",
  "finished_at": "2025-07-17T22:00:24.781339"
}
```

**Response:**
```json
{
  "status": "success",
  "tour_id": "tour_1981b2356dc",
  "rows_affected": 1
}
```

## How to Deploy

1. Rebuild the Docker container:
   ```
   docker-compose build user-api-2
   ```

2. Restart the service:
   ```
   docker-compose restart user-api-2
   ```

3. Test the new endpoints:
   ```
   curl -X POST -H "Content-Type: application/json" -d '{"sql":"SELECT * FROM tour_requests LIMIT 5"}' http://localhost:5003/sql
   ```