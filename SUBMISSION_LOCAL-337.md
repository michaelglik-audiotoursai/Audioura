##### READY FOR REVIEW

**Task:** LOCAL-337 — Amenities Near Runtime Service  
**Branch:** `kiro/local337-amenities-near`  
**Commit:** `b74b156`  
**Base:** `storied`

---

## Per-file summary

| File | Purpose |
|------|---------|
| `amenities_near_service.py` | New Flask service (port 5009). Endpoint `/amenities-near/<lat>/<lng>?kind=...&tour_id=...`. Queries Overpass API for OSM amenities, returns distance + landmark hint. |
| `tests/test_local337_amenities_near.py` | 20 unit tests covering all acceptance criteria. Imports production module directly. |

---

## Design decisions

1. **Overpass API chosen** over Nominatim for amenity queries. Overpass is the standard OSM tag-query API (`amenity=drinking_water`, `amenity=toilets`). Nominatim is a geocoder — wrong tool for tag-based spatial queries. We reuse the User-Agent discipline from `stop_existence_gate.py`.

2. **Museum exclusion at the endpoint** — requires `tour_id` query parameter. The service checks `audio_tours.tour_name` for "museum" (case-insensitive). This makes the exclusion impossible to bypass from the app: no tour_id = no exclusion check (allows standalone use), but providing a museum tour_id = 403 refusal. Justification: GPS is useless indoors, there's nothing to route to, and the app will pass tour_id when it has context.

3. **Landmark hint via second Overpass query** — searches named features within 150m of the amenity. Prioritises landmarks that sound good spoken (churches, monuments, historic sites) but falls back to any named feature. Returns `null` if nothing close — never invents a landmark.

4. **Rate-limit: 2s minimum between Overpass calls** (thread-safe lock). Overpass's policy is stricter than Nominatim. User-Agent: `Audioura/2.2 (amenities-near; contact: support@audioura.com)`.

---

## Verification evidence

### Real call — central Nice (43.6961, 7.2758), drinking_water

```
FOUND: {
  "lat": 43.6960402,
  "lng": 7.2753164,
  "name": "drinking water",
  "distance_m": 39,
  "osm_id": 5043438421
}
Landmark hint: Plaque paroissiale Sainte-Réparate
```

### Real call — toilets near central Nice

```
FOUND: {
  "lat": 43.6953543,
  "lng": 7.2759763,
  "name": "toilets",
  "distance_m": 84,
  "osm_id": 4688964712
}
```

### None found — middle of Mediterranean (42.0, 6.0)

```
Result: None — this is the none_found state
```

### Service unavailable — Overpass 504/timeout (natural rate-limit during rapid testing)

```
SERVICE UNAVAILABLE: Overpass HTTP 504
```

### Side-by-side: the two non-found states

| State | HTTP | JSON status | User message |
|-------|------|-------------|--------------|
| Searched, nothing found | 200 | `none_found` | "I can't find water nearby" |
| Could not search | 503 | `service_unavailable` | "I can't check right now" |

### Museum exclusion — tour_id=1 (Palais Lascaris museum Tour)

```json
{
  "message": "Amenity lookup not available for museum tours (indoor, no GPS)",
  "reason": "museum_tour",
  "status": "excluded"
}
HTTP 403
```

### Rate-limit compliance

- `OVERPASS_MIN_INTERVAL = 2.0` seconds enforced via `_overpass_lock`
- `OVERPASS_HEADERS["User-Agent"] = "Audioura/2.2 (amenities-near; ...)"` 
- Test `TestRateLimit::test_interval_enforced` asserts `>=2.0s` between calls

### D162 regression — tests go red with the bug

```
FAILED test_429_is_service_unavailable_not_none_found
  AssertionError: assert 'none_found' == 'service_unavailable'

FAILED test_timeout_is_service_unavailable_not_none_found
  AssertionError: assert 'none_found' == 'service_unavailable'
```

After restoring fix: `20 passed`

### audio_tours count

```sql
SELECT count(*) FROM audio_tours WHERE is_test = false;
 count
-------
    29
```

---

## Test results

```
20 passed, 1 warning in 2.22s
```

---

## Limitations

1. **Landmark hint quality depends on OSM data density.** Sparse areas may return `null` or unhelpful names. The app must handle `landmark_hint: null` gracefully (say only distance).

2. **Overpass timeout under load.** The public Overpass API can 504 during peak hours. A retry with backoff could help but risks exceeding the $0.50 ceiling if we ever need a paid mirror. Currently: single attempt, surface as `service_unavailable`.

3. **No left/right directions.** Explicitly deferred per the phrasing contract — bearing from a phone at walking speed is unreliable.

4. **Museum detection is name-based.** A tour named "Walking Tour of Museum Quarter" would match even though it's outdoors. A future `tour_type` column would be more precise.

5. **Not containerised.** This task adds the service file but does not modify `docker-compose.yml` (D48: no container rebuilds). Deployment requires adding a container definition for port 5009.
