-- Phase 3 Database Migration: User Consolidation Schema
-- Date: 2025-11-13
-- Purpose: Add user consolidation and device merging capabilities

-- Add consolidated_user_id column to existing credentials table
ALTER TABLE user_subscription_credentials 
ADD COLUMN IF NOT EXISTS consolidated_user_id VARCHAR(255);

-- Create index for consolidated user lookups
CREATE INDEX IF NOT EXISTS idx_consolidated_user 
ON user_subscription_credentials(consolidated_user_id);

-- User consolidation mapping table
CREATE TABLE IF NOT EXISTS user_consolidation_map (
    consolidated_user_id VARCHAR(255) PRIMARY KEY,
    primary_device_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    last_merged_at TIMESTAMP DEFAULT NOW()
);

-- Device consolidation history table
CREATE TABLE IF NOT EXISTS device_consolidation_history (
    id SERIAL PRIMARY KEY,
    consolidated_user_id VARCHAR(255) NOT NULL,
    merged_device_id VARCHAR(255) NOT NULL,
    domain VARCHAR(255) NOT NULL,
    merged_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (consolidated_user_id) REFERENCES user_consolidation_map(consolidated_user_id)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_consolidation_history_user 
ON device_consolidation_history(consolidated_user_id);

CREATE INDEX IF NOT EXISTS idx_consolidation_history_device 
ON device_consolidation_history(merged_device_id);

-- Add comments for documentation
COMMENT ON TABLE user_consolidation_map IS 'Maps consolidated user IDs to primary devices for device merging';
COMMENT ON TABLE device_consolidation_history IS 'Tracks history of device merging operations';
COMMENT ON COLUMN user_subscription_credentials.consolidated_user_id IS 'Links credentials to consolidated user for device merging';