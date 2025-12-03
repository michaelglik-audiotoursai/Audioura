# Boston Globe Email Newsletter Investigation Commands

## 1. Check Recent Newsletters (find the Boston Globe email newsletter)
```bash
curl -X GET "http://localhost:5017/newsletters_v2" | jq '.newsletters[] | select(.name | contains("Boston Globe")) | {newsletter_id, name, url, date, article_count}'
```

## 2. Get Articles for Boston Globe Email Newsletter (use newsletter_id from above)
```bash
# Replace 232 with actual newsletter_id from step 1
curl -X POST "http://localhost:5017/get_articles_by_newsletter_id" \
  -H "Content-Type: application/json" \
  -d '{"newsletter_id": 232, "user_id": "USER-281301397"}' | jq '.'
```

## 3. Check Individual Article Content (use article_ids from step 2)
```bash
# Replace with actual article_id from step 2
curl -X GET "http://localhost:5012/download/ARTICLE_ID_HERE?user_id=USER-281301397" -I
```

## 4. Download and Examine Article ZIP Files
```bash
# Replace with actual article_id
curl -X GET "http://localhost:5012/download/ARTICLE_ID_HERE?user_id=USER-281301397" -o "boston_globe_article.zip"
```

## 5. Check Database for Boston Globe Newsletter Details
```bash
docker exec development-postgres-2-1 psql -U admin -d audiotours -c "
SELECT n.id, n.url, n.created_at, COUNT(nal.article_requests_id) as article_count
FROM newsletters n 
LEFT JOIN newsletters_article_link nal ON n.id = nal.newsletters_id
WHERE n.url LIKE '%bostonglobe%' OR n.url LIKE '%view.email.bostonglobe%'
GROUP BY n.id, n.url, n.created_at 
ORDER BY n.created_at DESC 
LIMIT 5;"
```

## 6. Check Article Details for Boston Globe Newsletter
```bash
# Replace 232 with actual newsletter_id
docker exec development-postgres-2-1 psql -U admin -d audiotours -c "
SELECT ar.article_id, ar.request_string, ar.url, ar.status, 
       LENGTH(ar.article_text) as content_length,
       ar.subscription_required, ar.subscription_domain
FROM article_requests ar
JOIN newsletters_article_link nal ON ar.article_id = nal.article_requests_id
WHERE nal.newsletters_id = 232
ORDER BY ar.created_at DESC;"
```

## 7. Check for Advertising URLs in Articles
```bash
# Replace 232 with actual newsletter_id
docker exec development-postgres-2-1 psql -U admin -d audiotours -c "
SELECT ar.article_id, ar.request_string, ar.url
FROM article_requests ar
JOIN newsletters_article_link nal ON ar.article_id = nal.article_requests_id
WHERE nal.newsletters_id = 232
AND (ar.url LIKE '%booking.com%' 
     OR ar.url LIKE '%liadm.com%' 
     OR ar.url LIKE '%expedia.com%'
     OR ar.url LIKE '%amazon.com%'
     OR ar.url LIKE '%doubleclick%'
     OR ar.url LIKE '%googleadservices%');"
```

## 8. Test Boston Globe Email Newsletter Processing (if needed)
```bash
# Use the actual Boston Globe email newsletter URL
curl -X POST "http://localhost:5017/process_newsletter" \
  -H "Content-Type: application/json" \
  -d '{
    "newsletter_url": "https://view.email.bostonglobe.com/?qs=35122857753d2cefdaa89964b24ace416ecb0bc5f22ab441bc0691e160f6d5b9d91fd124744eef9b60aea26a24cf5bd432716fed1db202483f823a4ad5089d216693735fff73e863ada546b0a914a84f32c4730c06aaf9a17165b8e96b471121",
    "user_id": "USER-281301397",
    "max_articles": 10,
    "test_mode": true
  }'
```

## Expected Results:
- **Main Newsletter Article**: Should be the Boston Globe email newsletter content itself
- **Subscription Articles**: Should be actual Boston Globe news articles, NOT advertising sites
- **Failed Articles**: Should show which tracking URLs are redirecting to advertising sites
- **Success Rate**: Currently 5/10 articles (50%), should improve with enhanced filtering

## Investigation Focus:
1. Identify which article_ids are the main newsletter vs individual articles
2. Check which URLs are redirecting to advertising sites (booking.com, liadm.com, etc.)
3. Verify that Boston Globe authentication is working for legitimate articles
4. Confirm content quality for successfully processed articles