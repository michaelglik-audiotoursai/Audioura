# Tour Download Endpoint Analysis Report

## Issue Summary
The mobile app fails when accessing tour info from search results but works with map results. The problem is **NOT** in the data structure - both endpoints return identical tour objects.

## Key Findings

### 1. `/tour-info/17` Endpoint ✅ WORKING
- **Status**: 200 OK
- **Content-Type**: application/json
- **Size**: 211 bytes (small JSON response)
- **Structure**: 
```json
{
  "downloads": 7,
  "has_audio": true,
  "id": 17,
  "lat": 42.3393,
  "lng": -71.0942,
  "name": "19 century art.at MFA Boston MA - museum Tour",
  "request_string": "19 century art.at MFA Boston MA"
}
```

### 2. `/download-tour/17` Endpoint ⚠️ LARGE BINARY
- **Status**: 200 OK
- **Content-Type**: application/zip
- **Size**: 5.8MB ZIP file
- **Contains**: Audio files and tour data
- **Note**: This was the endpoint that crashed the previous test due to memory usage

### 3. Data Structure Comparison

#### Tours from `/tours-near/` (WORKING):
```json
{
  "id": 17,
  "lat": 42.3393,
  "lng": -71.0942,
  "name": "19 century art.at MFA Boston MA - museum Tour",
  "popularity": 8,
  "request_string": "19 century art.at MFA Boston MA",
  "type": "walking_tour",
  "distance_km": 3.71
}
```

#### Tours from `/search-tours/` (FAILING):
```json
{
  "id": 17,
  "lat": 42.3393,
  "lng": -71.0942,
  "name": "19 century art.at MFA Boston MA - museum Tour",
  "popularity": 8,
  "request_string": "19 century art.at MFA Boston MA",
  "type": "walking_tour",
  "distance_km": 8466.71
}
```

## Critical Discovery: IDENTICAL DATA STRUCTURES ✅

**Both endpoints return tour objects with the same fields:**
- `id`, `lat`, `lng`, `name`, `popularity`, `request_string`, `type`, `distance_km`
- The `name` field exists in both responses
- All required fields for `tourInfo['name']` are present

## Real Issue Analysis

Since the data structures are identical, the problem is likely:

### 1. **Distance Calculation Bug** 🔍
- `/tours-near/`: distance_km = 3.71 (correct)
- `/search-tours/`: distance_km = 8466.71 (incorrect - seems like global distance)
- Search endpoint may be using wrong reference point for distance calculation

### 2. **Mobile App Processing Logic** 🔍
- The mobile app may be filtering or processing search results differently
- Could be related to how the app handles the `distance_km` values
- May have validation logic that rejects tours with large distances

### 3. **Endpoint Response Wrapper** 🔍
- `/tours-near/` wraps results in: `{"tours": [...], "center_lat": ..., "center_lng": ..., "count": ..., "radius_km": ...}`
- `/search-tours/` wraps results in: `{"tours": [...], "count": ..., "pattern": ""}`
- Missing `center_lat`, `center_lng`, `radius_km` in search response

## Recommendations

### Immediate Actions:
1. **Check mobile app distance filtering** - App may reject tours with distance > threshold
2. **Verify search endpoint distance calculation** - Fix the 8466km distances
3. **Add missing wrapper fields** - Include `center_lat`, `center_lng`, `radius_km` in search response
4. **Test with identical distance values** - Temporarily set same distances to isolate issue

### Debug Steps:
1. Test mobile app with search results that have small distance values
2. Check mobile app logs for distance-related filtering
3. Verify if app expects specific wrapper fields from search endpoint
4. Compare mobile app processing logic between map and search flows

## Conclusion
The issue is **NOT** missing `name` fields or different data structures. Both endpoints return valid tour objects with all required fields. The problem is likely in:
- Distance calculation in search endpoint
- Mobile app filtering based on distance values  
- Missing wrapper metadata in search response
- Different processing logic in mobile app for search vs map results