# Claude Review Request — REQ-PROMOTE: Custom Tour Promote Endpoint
**Date**: 2026-05-22  
**File**: `tour_editing_phase2.py` (container `tour-editing-phase2-1`, port 5022)  
**Branch**: `Newsletters`

---

## 1. Background & Requirements

### Problem
The tour editing service (`bulk-save`) creates a new ZIP on the container filesystem but never
writes to the shared PostgreSQL `audio_tours` table. This means:
- Edited tours are invisible to all other devices (map, download, translation services)
- Edited tours cannot be translated (translation service works from `audio_tours` rows only)
- No name uniqueness is enforced — two users could create identically-named custom tours

### Design Decisions (agreed with user)
1. **Mobile app sets the custom tour name** — services store it as-is, no auto-naming
2. **Name uniqueness enforced server-side** — case-insensitive, among original tours only
   (`original_tour_id IS NULL`). Translations of the same name are fine (they have
   `original_tour_id` set and are excluded from the check)
3. **`creator_type = 'Custom'`** — uses existing column, no schema change needed
4. **`original_tour_id = NULL`** — custom tours are independent originals, not translations
5. **Once promoted, the tour is treated identically to any generated tour** — translation
   service, map delivery, and download all work without modification

### Existing DB schema (relevant columns)
```sql
audio_tours (
  id               serial PRIMARY KEY,
  tour_name        varchar(255) NOT NULL,
  request_string   text NOT NULL,
  audio_tour       bytea,
  lat              double precision,
  lng              double precision,
  content_language varchar(10) DEFAULT 'en',
  original_tour_id integer REFERENCES audio_tours(id),
  creator_type     varchar(50) DEFAULT 'Official',
  stops_count      integer DEFAULT 0,
  tour_content     text,
  number_requested integer DEFAULT 0
)
```

---

## 2. Implementation

New endpoint added to `tour_editing_phase2.py` before `if __name__`:

```python
@app.route('/tour/<tour_id>/promote', methods=['POST'])
def promote_custom_tour(tour_id):
    data = request.json or {}
    custom_name  = (data.get('custom_name') or '').strip()
    zip_b64      = data.get('zip_base64', '')
    lat          = data.get('lat')
    lng          = data.get('lng')
    stops_count  = data.get('stops_count')
    tour_content = data.get('tour_content', '')

    # --- input validation ---
    if not custom_name:
        return jsonify({'status': 'error', 'error_code': 'MISSING_NAME',
                        'message': 'custom_name is required'}), 400
    if len(custom_name) > 255:
        return jsonify({'status': 'error', 'error_code': 'NAME_TOO_LONG',
                        'message': 'custom_name must be 255 characters or fewer'}), 400
    if not zip_b64:
        return jsonify({'status': 'error', 'error_code': 'MISSING_ZIP',
                        'message': 'zip_base64 is required'}), 400
    if lat is None or lng is None:
        return jsonify({'status': 'error', 'error_code': 'MISSING_COORDS',
                        'message': 'lat and lng are required'}), 400
    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return jsonify({'status': 'error', 'error_code': 'INVALID_COORDS',
                        'message': 'lat and lng must be numeric'}), 400
    try:
        zip_bytes = base64.b64decode(zip_b64)
    except Exception:
        return jsonify({'status': 'error', 'error_code': 'INVALID_ZIP',
                        'message': 'zip_base64 could not be decoded'}), 400

    print(f"[PROMOTE] tour_id={tour_id} custom_name={custom_name!r} "
          f"lat={lat} lng={lng} stops={stops_count} zip={len(zip_bytes)}B")

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # --- uniqueness check (original tours only, case-insensitive) ---
        cur.execute(
            "SELECT id FROM audio_tours "
            "WHERE LOWER(tour_name) = LOWER(%s) AND original_tour_id IS NULL",
            (custom_name,)
        )
        existing = cur.fetchone()
        if existing:
            print(f"[PROMOTE] NAME_EXISTS: {custom_name!r} -> existing id={existing[0]}")
            return jsonify({
                'status': 'conflict',
                'error_code': 'NAME_EXISTS',
                'existing_tour_id': existing[0],
                'message': f'A tour named "{custom_name}" already exists. '
                           f'Please choose a different name.'
            }), 409

        # --- insert new row ---
        cur.execute("""
            INSERT INTO audio_tours
                (tour_name, request_string, audio_tour, lat, lng,
                 content_language, creator_type, stops_count, tour_content,
                 original_tour_id, number_requested)
            VALUES (%s, %s, %s, %s, %s, 'en', 'Custom', %s, %s, NULL, 0)
            RETURNING id
        """, (
            custom_name,
            custom_name,
            zip_bytes,
            lat, lng,
            stops_count,
            tour_content or None,
        ))
        new_id = cur.fetchone()[0]
        conn.commit()
        print(f"[PROMOTE] Created audio_tours id={new_id} name={custom_name!r}")
        return jsonify({'status': 'created', 'tour_id': new_id}), 201

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[PROMOTE] ERROR: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        if conn:
            conn.close()
```

---

## 3. API Contract

**Endpoint**: `POST /tour/<tour_id>/promote`  
**Port**: 5022 (`tour-editing-phase2-1`)

The `tour_id` path parameter is the editing-service UUID from `bulk-save`. It is logged
for traceability but not used in the DB insert (the new integer ID is auto-assigned).

### Request body
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `custom_name` | string | ✅ | User-chosen name. Max 255 chars. Must be unique (case-insensitive) among original tours |
| `zip_base64` | string | ✅ | Base64-encoded ZIP bytes from `bulk-save` download |
| `lat` | float | ✅ | Tour centre latitude |
| `lng` | float | ✅ | Tour centre longitude |
| `stops_count` | int | ✅ | Number of stops |
| `tour_content` | string | ❌ | Plain-text stop content for future re-translation |

### Responses
| HTTP | Body | When |
|------|------|------|
| 201 | `{"status":"created","tour_id":<int>}` | Success — new DB row created |
| 409 | `{"status":"conflict","error_code":"NAME_EXISTS","existing_tour_id":<int>,"message":"..."}` | Name already taken |
| 400 | `{"status":"error","error_code":"<code>","message":"..."}` | Validation failure |
| 500 | `{"status":"error","message":"..."}` | DB or unexpected error |

### Error codes (400)
- `MISSING_NAME` — `custom_name` absent or blank
- `NAME_TOO_LONG` — exceeds 255 chars
- `MISSING_ZIP` — `zip_base64` absent or blank
- `MISSING_COORDS` — `lat` or `lng` absent
- `INVALID_COORDS` — `lat`/`lng` not numeric
- `INVALID_ZIP` — base64 decode failed

---

## 4. Mobile App Integration (for Mobile Amazon-Q)

After `bulk-save` completes and the user confirms the custom name:

```
POST /tour/<uuid>/promote
  custom_name  = user-entered name (e.g. "Walking on Dedham St, Newton MA (edited)")
  zip_base64   = base64( GET /tour/<uuid>/download response bytes )
  lat          = original tour's lat
  lng          = original tour's lng
  stops_count  = number of stops after editing
  tour_content = concatenated stop text (optional, enables future re-translation)

→ 201: store tour_id (integer) — use for translation and map display
→ 409: prompt user to choose a different name, retry
→ 400/500: show error, allow retry
```

After receiving `tour_id`, the mobile app calls translation service identically to any
generated tour:
```
POST localhost:5030/translate-with-audio
  { "content_id": <tour_id>, "content_type": "tour", "languages": ["ru"] }
```

---

## 5. Test Results

All three smoke tests passed against live container:

| Test | Input | Expected | Result |
|------|-------|----------|--------|
| Missing name | `custom_name: ""` | 400 MISSING_NAME | ✅ |
| New unique name | `"Walking on Dedham St, Newton MA (edited)"` | 201 + tour_id=303 | ✅ |
| Duplicate name | Same name again | 409 NAME_EXISTS + existing_tour_id=303 | ✅ |
| DB row | `SELECT` on id=303 | creator_type=Custom, content_language=en, original_tour_id=NULL | ✅ |

Test row (id=303) deleted after verification.

---

## 6. Questions for Claude

**Q1**: The `tour_id` path parameter (editing UUID) is logged but not stored in the DB.
Should it be stored in a separate column (e.g. `edit_source_id`) for audit/traceability,
or is logging sufficient?

**Q2**: `request_string` is set equal to `custom_name`. For generated tours,
`request_string` is the raw user input (e.g. `"walking tour in Newton Center, MA"`) and
`tour_name` is the formatted title. For custom tours they are the same. Is this acceptable,
or should the mobile app send a separate `request_string`?

**Q3**: The uniqueness check is case-insensitive (`LOWER(tour_name) = LOWER(%s)`).
Should it also normalize whitespace (e.g. trim multiple spaces) before comparing,
or is the current `.strip()` on input sufficient?

**Q4**: `zip_bytes` is stored directly in `audio_tour` (bytea). For large edited tours
(many stops, custom audio), this could be several MB. Is there a size guard needed here,
or is the existing DB column sufficient?

**Q5**: The endpoint accepts any `tour_id` in the path — it does not verify that the
editing UUID actually exists in the container filesystem. Should it validate that
`/app/tours/<tour_id>` exists before proceeding, or is this unnecessary given the mobile
app always calls promote immediately after bulk-save?
