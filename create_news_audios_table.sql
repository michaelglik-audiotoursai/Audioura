-- News audios table similar to audio_tours
CREATE TABLE IF NOT EXISTS news_audios (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    newsletter_source VARCHAR(255) NOT NULL,
    article_title VARCHAR(500) NOT NULL,
    article_content TEXT NOT NULL,
    article_url VARCHAR(1000),
    audio_file_path VARCHAR(500) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    content_vector VECTOR(1536), -- For AI search
    INDEX idx_user_id (user_id),
    INDEX idx_newsletter_source (newsletter_source),
    INDEX idx_created_at (created_at)
);