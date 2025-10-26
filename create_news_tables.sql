-- Create article_requests table
CREATE TABLE IF NOT EXISTS public.article_requests (
    id SERIAL PRIMARY KEY,
    secret_id VARCHAR(255),
    article_id VARCHAR(255) UNIQUE,
    request_string TEXT,
    article_topics INTEGER NOT NULL DEFAULT 0,
    article_text BYTEA,
    status VARCHAR(50) DEFAULT 'started',
    started_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (secret_id) REFERENCES users(secret_id)
);

-- Create news_audios table
CREATE TABLE IF NOT EXISTS public.news_audios (
    id SERIAL PRIMARY KEY,
    article_id VARCHAR(255) NOT NULL,
    article_name VARCHAR(255) NOT NULL,
    news_article BYTEA,
    number_requested INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (article_id) REFERENCES article_requests(article_id)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_article_requests_article_id ON article_requests(article_id);
CREATE INDEX IF NOT EXISTS idx_article_requests_secret_id ON article_requests(secret_id);
CREATE INDEX IF NOT EXISTS idx_news_audios_article_id ON news_audios(article_id);