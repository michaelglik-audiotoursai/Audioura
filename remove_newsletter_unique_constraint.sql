-- Remove unique constraint on newsletters.url to allow daily processing
-- This allows the same newsletter URL to be processed on different days

-- Drop the unique constraint
ALTER TABLE newsletters DROP CONSTRAINT IF EXISTS newsletters_url_key;

-- Add index for performance (non-unique)
CREATE INDEX IF NOT EXISTS idx_newsletters_url ON newsletters(url);
CREATE INDEX IF NOT EXISTS idx_newsletters_created_at ON newsletters(created_at);

-- Show current newsletters to verify
SELECT url, created_at, COUNT(*) as editions 
FROM newsletters 
GROUP BY url, DATE(created_at) 
ORDER BY created_at DESC;