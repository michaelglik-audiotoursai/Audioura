-- Safe cleanup of news data linked through newsletters_article_link
-- This script removes ONLY records that are actually linked in newsletters_article_link

BEGIN;

-- Show current sizes before cleanup
SELECT 'Before cleanup:' as status;
SELECT 
    'article_requests' as table_name,
    COUNT(*) as row_count,
    pg_size_pretty(pg_total_relation_size('article_requests')) as size
FROM article_requests
UNION ALL
SELECT 
    'news_audios' as table_name,
    COUNT(*) as row_count,
    pg_size_pretty(pg_total_relation_size('news_audios')) as size
FROM news_audios
UNION ALL
SELECT 
    'newsletters_article_link' as table_name,
    COUNT(*) as row_count,
    pg_size_pretty(pg_total_relation_size('newsletters_article_link')) as size
FROM newsletters_article_link
UNION ALL
SELECT 
    'newsletters' as table_name,
    COUNT(*) as row_count,
    pg_size_pretty(pg_total_relation_size('newsletters')) as size
FROM newsletters;

-- Show what will be deleted (for verification)
SELECT 'Records to be deleted:' as status;
SELECT 
    COUNT(DISTINCT nal.article_requests_id) as articles_to_delete,
    COUNT(DISTINCT na.article_id) as news_audios_to_delete,
    COUNT(DISTINCT nal.newsletters_id) as newsletters_to_delete,
    COUNT(*) as link_records_to_delete
FROM newsletters_article_link nal
LEFT JOIN news_audios na ON na.article_id = nal.article_requests_id;

-- Delete in proper order (respecting foreign key constraints)
-- Only delete records that are actually linked in newsletters_article_link

-- Store the article IDs to delete
CREATE TEMP TABLE articles_to_delete AS
SELECT DISTINCT article_requests_id as article_id
FROM newsletters_article_link 
WHERE article_requests_id IS NOT NULL;

-- 1. Delete from news_audios where article_id is in the link table
DELETE FROM news_audios 
WHERE article_id IN (SELECT article_id FROM articles_to_delete);

-- 2. Delete from article_requests where article_id is in the link table
DELETE FROM article_requests 
WHERE article_id IN (SELECT article_id FROM articles_to_delete);

-- 3. Delete from newsletters that are referenced in the link table
DELETE FROM newsletters 
WHERE id IN (
    SELECT DISTINCT newsletters_id 
    FROM newsletters_article_link 
    WHERE newsletters_id IS NOT NULL
);

-- 4. Finally delete the link records themselves
DELETE FROM newsletters_article_link;

-- Show results after deletion
SELECT 'After deletion:' as status;
SELECT 
    'article_requests' as table_name,
    COUNT(*) as row_count,
    pg_size_pretty(pg_total_relation_size('article_requests')) as size
FROM article_requests
UNION ALL
SELECT 
    'news_audios' as table_name,
    COUNT(*) as row_count,
    pg_size_pretty(pg_total_relation_size('news_audios')) as size
FROM news_audios
UNION ALL
SELECT 
    'newsletters_article_link' as table_name,
    COUNT(*) as row_count,
    pg_size_pretty(pg_total_relation_size('newsletters_article_link')) as size
FROM newsletters_article_link
UNION ALL
SELECT 
    'newsletters' as table_name,
    COUNT(*) as row_count,
    pg_size_pretty(pg_total_relation_size('newsletters')) as size
FROM newsletters;

-- Reclaim disk space
VACUUM FULL article_requests;
VACUUM FULL news_audios;
VACUUM FULL newsletters_article_link;
VACUUM FULL newsletters;

-- Show final sizes after vacuum
SELECT 'After VACUUM FULL:' as status;
SELECT 
    'article_requests' as table_name,
    COUNT(*) as row_count,
    pg_size_pretty(pg_total_relation_size('article_requests')) as size
FROM article_requests
UNION ALL
SELECT 
    'news_audios' as table_name,
    COUNT(*) as row_count,
    pg_size_pretty(pg_total_relation_size('news_audios')) as size
FROM news_audios
UNION ALL
SELECT 
    'Database total size' as table_name,
    0 as row_count,
    pg_size_pretty(pg_database_size('audiotours')) as size;

COMMIT;

-- Final message
SELECT 'Cleanup completed successfully!' as status;