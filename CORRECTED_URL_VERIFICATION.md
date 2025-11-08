# CORRECTED URL Verification for ZIP Files

## Issues Found & Corrections

### 1. ❌ **Spotify "Show More" Expansion - NEEDS FIX**
**Browser URL**: `https://open.spotify.com/episode/3VJHfEUYl7tHUll4vfu1D3?si=e01TiIuARxqSIqVnaaaYVQ`
**ZIP Download**: 
```bash
curl -X GET "http://localhost:5012/download/1eb74f38-828b-407d-813f-92e368dd51be" -o "spotify_enhanced.zip"
```
**Status**: ❌ BROKEN - Content truncated at "...Show more", expansion not working
**Fix Applied**: Enhanced content expander with better Spotify selectors

### 2. ❌ **MailChimp URL Invalid - CORRECTED**
**OLD (Broken) URL**: `https://mailchi.mp/bostonglobe.com/todaysheadlines-6057237`
**NEW (Working) URLs**: 
- `https://mailchi.mp/cb820171cc62/newton-has-decided-election-night-2025-results?e=f2ed12d013`
- `https://mailchi.mp/cffaa0a1186b/friday-news-decoding-the-office-space-market-mystery-10346462`

**Working ZIP Downloads**:
```bash
curl -X GET "http://localhost:5012/download/4988fe45-7874-4c99-8d06-087d3dbfa56b" -o "mailchimp_newton_election.zip"
curl -X GET "http://localhost:5012/download/7273022f-6248-47ce-b3b4-c72653883db7" -o "mailchimp_newton_news.zip"
```
**Status**: ✅ WORKING - 2,511 and 3,877 chars respectively

### 3. ❌ **Apple Podcasts URL Mismatch - CORRECTED**
**Expected Episode**: "Advice Line with Tariq Farid of Edible Arrangements"
**Correct URL**: `https://podcasts.apple.com/us/podcast/advice-line-with-tariq-farid-of-edible-arrangements/id1150510297?i=1000734063821`
**Current ZIP**: Contains different episode content
**Action Needed**: Process the correct URL to get matching ZIP file

### 4. ❌ **Quora URL Mismatch - NEEDS INVESTIGATION**
**Provided URL**: `https://jokesfunnystories.quora.com/?__nsrc__=4&__snid3__=92061427717`
**ZIP Content**: Different Quora content, missing "(more)" expansion
**Action Needed**: Find the actual URL that matches the ZIP content

### 5. ✅ **Guy Raz Substack - WORKING PERFECTLY**
**Browser URL**: `https://guyraz.substack.com/p/the-babylist-playbook-how-one-mom`
**ZIP Download**: 
```bash
curl -X GET "http://localhost:5012/download/dbf1839a-841b-4fea-bf30-41cd7143c7d0" -o "guy_raz_babylist.zip"
```
**Status**: ✅ PERFECT MATCH - Full content preserved

## Immediate Actions Required

### 1. Deploy Spotify Content Expansion Fix
```bash
docker cp content_expander.py newsletter-processor-1:/app/
docker restart newsletter-processor-1
```

### 2. Test Spotify Expansion
```bash
# Test the problematic Spotify URL with enhanced expansion
curl -X POST http://localhost:5017/process_newsletter \
  -H "Content-Type: application/json" \
  -d '{"newsletter_url": "https://open.spotify.com/episode/3VJHfEUYl7tHUll4vfu1D3", "user_id": "test_user_spotify", "max_articles": 3}'
```

### 3. Process Correct Apple Podcasts URL
```bash
# Process the correct Tariq Farid episode
curl -X POST http://localhost:5012/process_article \
  -H "Content-Type: application/json" \
  -d '{"url": "https://podcasts.apple.com/us/podcast/advice-line-with-tariq-farid-of-edible-arrangements/id1150510297?i=1000734063821", "user_id": "test_user_apple"}'
```

### 4. Find Matching Quora URL
```bash
# Query database to find the actual URL for the Quora ZIP content
docker exec development-postgres-2-1 psql -U admin -d audiotours -c "
SELECT url, request_string FROM article_requests 
WHERE article_id = 'f5bdcc8d-55e3-403d-8536-790704ba6806';"
```

## Expected Results After Fixes

### Spotify (After Fix)
- **Before**: ~200 chars (truncated at "...Show more")
- **After**: 800+ chars (full episode description)
- **Expansion**: Multiple "Show more" buttons clicked automatically

### MailChimp (Corrected URLs)
- **Newton Election**: 2,511 chars of election results content
- **Newton News**: 3,877 chars of news content with multiple articles
- **Pattern Recognition**: Working with "Read full story" buttons

### Apple Podcasts (Correct URL)
- **Expected**: Tariq Farid Edible Arrangements episode content
- **Quality**: 1000+ chars of episode description

### Quora (To Be Corrected)
- **Expected**: Content matching the provided URL
- **Expansion**: "(more)" links clicked automatically

## Verification Commands

```bash
# Download corrected ZIP files
curl -X GET "http://localhost:5012/download/4988fe45-7874-4c99-8d06-087d3dbfa56b" -o "mailchimp_newton_election.zip"
curl -X GET "http://localhost:5012/download/7273022f-6248-47ce-b3b4-c72653883db7" -o "mailchimp_newton_news.zip"

# Extract and verify content
unzip mailchimp_newton_election.zip -d newton_election/
unzip mailchimp_newton_news.zip -d newton_news/

# Check content lengths
echo "Newton Election: $(wc -c < newton_election/audiotours_search_content.txt) chars"
echo "Newton News: $(wc -c < newton_news/audiotours_search_content.txt) chars"

# Verify no HTML entities
grep -c "&nbsp;\|&amp;\|&mdash;" newton_*/audiotours_search_content.txt || echo "Clean text confirmed"
```