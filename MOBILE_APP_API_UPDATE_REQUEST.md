# Mobile App API Update Request

## Issue
The current mobile app API logic is flawed because it only uses newsletter URLs to retrieve articles, but the same newsletter URL can be processed on different dates with different articles.

## Problem Example
- **API Security Issue-279** processed on **Sept 17** = 1 article
- **API Security Issue-279** processed on **Sept 18** = 10 articles
- Current API only uses URL, so it's ambiguous which newsletter the user wants

## Solution: New API Endpoints

### 1. Replace `/newsletters` with `/newsletters_v2`

**Old Endpoint:** `GET /newsletters`
**New Endpoint:** `GET /newsletters_v2`

**New Response Format:**
```json
{
  "status": "success",
  "newsletters": [
    {
      "newsletter_id": 38,
      "url": "https://apisecurity.io/issue-279-...",
      "name": "apisecurity.io Issue-279",
      "date": "September 18, 2025",
      "created_at": "2025-09-18T15:51:38.100436",
      "type": "News and Politics",
      "article_count": 10
    },
    {
      "newsletter_id": 34,
      "url": "https://apisecurity.io/issue-279-...",
      "name": "apisecurity.io Issue-279", 
      "date": "September 17, 2025",
      "created_at": "2025-09-17T22:11:57.153955",
      "type": "News and Politics",
      "article_count": 1
    }
  ]
}
```

### 2. Replace `/get_newsletter_articles` with `/get_articles_by_newsletter_id`

**Old Endpoint:** `POST /get_newsletter_articles`
```json
{
  "newsletter_url": "https://apisecurity.io/issue-279-..."
}
```

**New Endpoint:** `POST /get_articles_by_newsletter_id`
```json
{
  "newsletter_id": 38
}
```

**Response Format:** (Same as before)
```json
{
  "status": "success",
  "articles": [
    {
      "article_id": "42cee7f5-2e74-47bb-8954-5f4946285ed1",
      "title": "API Security Article Title",
      "author": "Author Name",
      "date": "September 18, 2025",
      "url": "https://example.com/article",
      "status": "finished",
      "article_type": "Technology"
    }
  ]
}
```

## Mobile App Changes Required

### 1. Newsletter List Screen
- **Before:** Show newsletter by URL only
- **After:** Show newsletter with date and article count
  - "API Security Issue-279 (Sept 18) - 10 articles"
  - "API Security Issue-279 (Sept 17) - 1 article"

### 2. Article Retrieval
- **Before:** Send `newsletter_url` to get articles
- **After:** Send `newsletter_id` to get articles

### 3. User Experience
- User can now choose which date's processing they want
- Clear indication of how many articles each newsletter edition has
- No more ambiguity about which newsletter is being accessed

## Benefits
1. **Precise Control:** User picks exact newsletter edition they want
2. **Clear Information:** Shows date and article count upfront
3. **No Ambiguity:** Each newsletter edition has unique ID
4. **Better UX:** User knows what they're getting before selecting

## Testing
Both new endpoints are tested and working:
- `/newsletters_v2` returns all newsletters with dates and article counts
- `/get_articles_by_newsletter_id` returns articles for specific newsletter ID

## Implementation Priority
**HIGH** - This fixes a fundamental logic flaw in newsletter article retrieval.

---
**Docker Services Team**
Newsletter Processor Service - Port 5017