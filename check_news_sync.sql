-- Check news data sync between database and expected files

-- Show articles in database
SELECT 'Articles in database:' as status;
SELECT 
    article_id,
    LEFT(article_name, 50) as article_name_preview,
    status,
    created_at
FROM news_audios 
ORDER BY created_at DESC 
LIMIT 10;

-- Show article requests
SELECT 'Article requests:' as status;
SELECT 
    article_id,
    LEFT(request_string, 50) as request_preview,
    status,
    created_at
FROM article_requests 
ORDER BY created_at DESC 
LIMIT 10;

-- Check for orphaned records (articles without audio files)
SELECT 'Orphaned articles (no audio):' as status;
SELECT 
    ar.article_id,
    LEFT(ar.request_string, 50) as request_preview,
    ar.status as request_status,
    na.article_id as has_audio
FROM article_requests ar
LEFT JOIN news_audios na ON ar.article_id = na.article_id
WHERE na.article_id IS NULL
ORDER BY ar.created_at DESC
LIMIT 10;