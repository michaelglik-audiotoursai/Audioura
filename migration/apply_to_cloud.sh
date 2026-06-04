#!/bin/bash
# Apply data to Cloud SQL from within the postgres container
export PGPASSWORD=audioura2026cloud
CLOUD_HOST=34.27.121.203

# Import audio_tours metadata
cat /tmp/audio_tours_meta.csv | psql -h $CLOUD_HOST -U admin -d audiotours -c "COPY audio_tours(id, tour_name, request_string, number_requested, lat, lng, created_at, language, original_tour_id, tour_content, content_language, stops_count, creator_type, description, derived_from_tour_id, draft, tour_blob_uri) FROM STDIN CSV HEADER"

echo "audio_tours imported"

# Import news_audios metadata
cat /tmp/news_audios_meta.csv | psql -h $CLOUD_HOST -U admin -d audiotours -c "COPY news_audios(id, article_id, article_name, number_requested, created_at, article_type, language, original_article_id, news_blob_uri) FROM STDIN CSV HEADER"

echo "news_audios imported"

# Fix sequences
psql -h $CLOUD_HOST -U admin -d audiotours -c "SELECT setval('audio_tours_id_seq', (SELECT MAX(id) FROM audio_tours));"
psql -h $CLOUD_HOST -U admin -d audiotours -c "SELECT setval('news_audios_id_seq', (SELECT MAX(id) FROM news_audios));"

echo "Sequences updated"
echo "Done!"
