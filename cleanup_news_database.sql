-- =====================================================
-- AudioTours Database Cleanup - News & Newsletter Data
-- =====================================================
-- This procedure removes all newsletter and news article data
-- to provide a clean slate for testing enhanced features
-- =====================================================

CREATE OR REPLACE FUNCTION cleanup_news_database()
RETURNS TABLE(
    operation TEXT,
    records_deleted INTEGER,
    status TEXT
) AS $$
DECLARE
    newsletter_count INTEGER;
    article_count INTEGER;
    audio_count INTEGER;
    link_count INTEGER;
BEGIN
    -- Start transaction
    BEGIN
        -- Get counts before deletion for reporting
        SELECT COUNT(*) INTO newsletter_count FROM newsletters;
        SELECT COUNT(*) INTO article_count FROM article_requests;
        SELECT COUNT(*) INTO audio_count FROM news_audios;
        SELECT COUNT(*) INTO link_count FROM newsletters_article_link;
        
        -- Log initial state
        RAISE NOTICE 'Starting cleanup - Newsletters: %, Articles: %, Audio: %, Links: %', 
                     newsletter_count, article_count, audio_count, link_count;
        
        -- 1. Delete newsletter-article links (foreign key dependencies)
        DELETE FROM newsletters_article_link;
        RETURN QUERY SELECT 'newsletters_article_link'::TEXT, link_count, 'DELETED'::TEXT;
        
        -- 2. Delete news audio files
        DELETE FROM news_audios;
        RETURN QUERY SELECT 'news_audios'::TEXT, audio_count, 'DELETED'::TEXT;
        
        -- 3. Delete article requests
        DELETE FROM article_requests;
        RETURN QUERY SELECT 'article_requests'::TEXT, article_count, 'DELETED'::TEXT;
        
        -- 4. Delete newsletters
        DELETE FROM newsletters;
        RETURN QUERY SELECT 'newsletters'::TEXT, newsletter_count, 'DELETED'::TEXT;
        
        -- 5. Reset sequences to start fresh
        ALTER SEQUENCE IF EXISTS newsletters_id_seq RESTART WITH 1;
        RETURN QUERY SELECT 'newsletters_id_seq'::TEXT, 0, 'RESET'::TEXT;
        
        -- 6. Vacuum tables to reclaim space
        VACUUM ANALYZE newsletters;
        VACUUM ANALYZE article_requests;
        VACUUM ANALYZE news_audios;
        VACUUM ANALYZE newsletters_article_link;
        
        RETURN QUERY SELECT 'database_vacuum'::TEXT, 0, 'COMPLETED'::TEXT;
        
        -- Final summary
        RETURN QUERY SELECT 'CLEANUP_SUMMARY'::TEXT, 
                           (newsletter_count + article_count + audio_count + link_count), 
                           'SUCCESS'::TEXT;
        
        RAISE NOTICE 'Cleanup completed successfully!';
        
    EXCEPTION
        WHEN OTHERS THEN
            -- Rollback on error
            RAISE EXCEPTION 'Cleanup failed: %', SQLERRM;
    END;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- Quick Cleanup Script (Alternative to stored procedure)
-- =====================================================
-- If stored procedures are not preferred, use this script:

/*
-- Step 1: Show current counts
SELECT 'newsletters' as table_name, COUNT(*) as record_count FROM newsletters
UNION ALL
SELECT 'article_requests', COUNT(*) FROM article_requests
UNION ALL
SELECT 'news_audios', COUNT(*) FROM news_audios
UNION ALL
SELECT 'newsletters_article_link', COUNT(*) FROM newsletters_article_link;

-- Step 2: Delete all data (order matters for foreign keys)
DELETE FROM newsletters_article_link;
DELETE FROM news_audios;
DELETE FROM article_requests;
DELETE FROM newsletters;

-- Step 3: Reset sequences
ALTER SEQUENCE IF EXISTS newsletters_id_seq RESTART WITH 1;

-- Step 4: Verify cleanup
SELECT 'newsletters' as table_name, COUNT(*) as remaining_records FROM newsletters
UNION ALL
SELECT 'article_requests', COUNT(*) FROM article_requests
UNION ALL
SELECT 'news_audios', COUNT(*) FROM news_audios
UNION ALL
SELECT 'newsletters_article_link', COUNT(*) FROM newsletters_article_link;

-- Step 5: Vacuum to reclaim space
VACUUM ANALYZE newsletters;
VACUUM ANALYZE article_requests;
VACUUM ANALYZE news_audios;
VACUUM ANALYZE newsletters_article_link;
*/

-- =====================================================
-- Usage Instructions:
-- =====================================================
-- 
-- Method 1: Run the stored procedure
-- SELECT * FROM cleanup_news_database();
--
-- Method 2: Run the commented script above line by line
--
-- Method 3: Quick one-liner (DANGEROUS - no rollback)
-- DELETE FROM newsletters_article_link; DELETE FROM news_audios; DELETE FROM article_requests; DELETE FROM newsletters;
-- =====================================================