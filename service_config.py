"""
Audioura Service Configuration Module
Centralizes environment-variable-driven configuration for all services.
Used by all Docker services for DB connections and inter-service URLs.

Local dev: env vars not set → defaults point to Docker container names.
Cloud Run: env vars injected via Secret Manager / service config.
"""
import os

# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================
DB_HOST = os.getenv('DB_HOST', 'postgres-2')
DB_NAME = os.getenv('DB_NAME', 'audiotours')
DB_USER = os.getenv('DB_USER', 'admin')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'password123')
DB_PORT = os.getenv('DB_PORT', '5432')


def get_db_connection():
    """Get a PostgreSQL database connection using environment-driven config."""
    import psycopg2
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT
    )


# =============================================================================
# INTER-SERVICE URLs (defaults = Docker container hostnames for local dev)
# =============================================================================
TOUR_GENERATOR_URL = os.getenv('TOUR_GENERATOR_URL', 'http://development-tour-generator-1:5000')
MODERNIZED_URL = os.getenv('MODERNIZED_URL', 'http://tour-generation-modernized-1:5021')
TRANSLATION_URL = os.getenv('TRANSLATION_URL', 'http://translation-service-1:5030')
TOUR_UPDATE_URL = os.getenv('TOUR_UPDATE_URL', 'http://development-tour-update-1:5001')
USER_API_URL = os.getenv('USER_API_URL', 'http://user-api-2:5000')
COORDINATES_URL = os.getenv('COORDINATES_URL', 'http://coordinates-fromai:5004')
POLLY_TTS_URL = os.getenv('POLLY_TTS_URL', 'http://polly-tts-1:5018')
NEWS_GENERATOR_URL = os.getenv('NEWS_GENERATOR_URL', 'http://news-generator-1:5010')
NEWS_PROCESSOR_URL = os.getenv('NEWS_PROCESSOR_URL', 'http://news-processor-1:5011')
NEWS_ORCHESTRATOR_URL = os.getenv('NEWS_ORCHESTRATOR_URL', 'http://news-orchestrator-1:5012')
NEWSLETTER_PROCESSOR_URL = os.getenv('NEWSLETTER_PROCESSOR_URL', 'http://newsletter-processor-1:5017')
VOICE_CONTROL_URL = os.getenv('VOICE_CONTROL_URL', 'http://development-voice-control-1:5008')
MAP_DELIVERY_URL = os.getenv('MAP_DELIVERY_URL', 'http://development-map-delivery-1:5005')


# =============================================================================
# AWS CONFIGURATION
# =============================================================================
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID', '')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY', '')
AWS_REGION = os.getenv('AWS_DEFAULT_REGION', os.getenv('AWS_REGION', 'us-east-1'))


# =============================================================================
# STORAGE MODE (for Phase B cloud-ready refactoring)
# =============================================================================
# 'volume' = use shared /app/tours/ volume (local Docker dev)
# 'cloud'  = use HTTP content passing + /tmp/ (Cloud Run)
TOUR_STORAGE_MODE = os.getenv('TOUR_STORAGE_MODE', 'volume')


# =============================================================================
# OPENAI CONFIGURATION
# =============================================================================
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
