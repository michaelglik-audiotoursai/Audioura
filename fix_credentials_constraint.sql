-- Fix credentials table constraint for Stage 1
-- Add unique constraint on device_id and article_id to prevent duplicates

ALTER TABLE user_subscription_credentials 
ADD CONSTRAINT unique_device_article 
UNIQUE (device_id, article_id);