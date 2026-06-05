#!/bin/bash
export PGPASSWORD=$1
cat /tmp/news_audios_meta.csv | psql -h 34.27.121.203 -U admin -d audiotours -c "SET session_replication_role = replica; COPY news_audios(id, article_id, article_name, number_requested, created_at, article_type, language, original_article_id, news_blob_uri) FROM STDIN CSV HEADER"
psql -h 34.27.121.203 -U admin -d audiotours -c "SELECT setval('news_audios_id_seq', (SELECT MAX(id) FROM news_audios));"
echo "news_audios imported"
