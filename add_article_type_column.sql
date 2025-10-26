-- Add article_type column to news_audios table
ALTER TABLE news_audios 
ADD COLUMN article_type VARCHAR(50) DEFAULT 'Others';

-- Add article_type column to article_requests table as backup
ALTER TABLE article_requests 
ADD COLUMN article_type VARCHAR(50) DEFAULT 'Others';

-- Show current structure
\d news_audios;
\d article_requests;