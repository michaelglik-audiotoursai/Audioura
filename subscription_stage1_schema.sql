-- SUBSCRIPTION STAGE 1 DATABASE SCHEMA
-- Add subscription fields to existing tables and create new credential storage

-- Add subscription fields to article_requests table
ALTER TABLE article_requests ADD COLUMN IF NOT EXISTS subscription_required BOOLEAN DEFAULT FALSE;
ALTER TABLE article_requests ADD COLUMN IF NOT EXISTS subscription_domain VARCHAR(255);

-- Create device encryption keys table
CREATE TABLE IF NOT EXISTS device_encryption_keys (
    device_id VARCHAR(255) PRIMARY KEY,
    encryption_key VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create user subscription credentials table
CREATE TABLE IF NOT EXISTS user_subscription_credentials (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(255) NOT NULL,
    article_id VARCHAR(255) NOT NULL,
    domain VARCHAR(255) NOT NULL,
    encrypted_username VARCHAR(255) NOT NULL,
    encrypted_password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (article_id) REFERENCES article_requests(article_id) ON DELETE CASCADE
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_credentials_device_domain ON user_subscription_credentials(device_id, domain);
CREATE INDEX IF NOT EXISTS idx_article_subscription ON article_requests(subscription_required, subscription_domain);