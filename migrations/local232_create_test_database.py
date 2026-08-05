#!/usr/bin/env python3
"""
LOCAL-232 Migration: Create audiotours_test database.

Creates a dedicated test database so test suites stop writing to the
production `audiotours` table. Schema is derived from production.
Reference tables (stop_corpus, venue_corpus) are copied with data since
tests read from them but never write to them.

Idempotent — safe to run multiple times. Second run is a no-op.

Pattern follows D109 (audiotours_subscribed): same Postgres instance,
separate database, schema derived from production.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tests'))
from db_connection import get_db_config

TEST_DB_NAME = "audiotours_test"


def migrate():
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

    config = get_db_config()

    # Connect to the default 'audiotours' database to issue CREATE DATABASE
    conn = psycopg2.connect(
        host=config["host"],
        port=config["port"],
        dbname="audiotours",  # Always connect to production for the migration
        user=config["user"],
        password=config["password"],
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    # Check if database already exists
    cur.execute(
        "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB_NAME,)
    )
    if cur.fetchone():
        print(f"[LOCAL-232] Database '{TEST_DB_NAME}' already exists — skipping creation.")
    else:
        cur.execute(f'CREATE DATABASE "{TEST_DB_NAME}" OWNER "{config["user"]}"')
        print(f"[LOCAL-232] Created database '{TEST_DB_NAME}'.")

    cur.close()
    conn.close()

    # Now connect to audiotours_test and create the schema
    conn_test = psycopg2.connect(
        host=config["host"],
        port=config["port"],
        dbname=TEST_DB_NAME,
        user=config["user"],
        password=config["password"],
    )
    cur_test = conn_test.cursor()

    # Check if audio_tours table already exists (idempotent)
    cur_test.execute("""
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'audio_tours' AND table_schema = 'public'
    """)
    if cur_test.fetchone():
        print(f"[LOCAL-232] Schema already exists in '{TEST_DB_NAME}' — skipping.")
        cur_test.close()
        conn_test.close()
        return

    # Create audio_tours table (schema derived from production)
    cur_test.execute("""
        CREATE SEQUENCE IF NOT EXISTS audio_tours_id_seq;

        CREATE TABLE audio_tours (
            id                   integer NOT NULL DEFAULT nextval('audio_tours_id_seq'),
            tour_name            varchar(255) NOT NULL,
            request_string       text NOT NULL,
            audio_tour           bytea,
            number_requested     integer NOT NULL DEFAULT 0,
            lat                  double precision,
            lng                  double precision,
            created_at           timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
            language             varchar(10) DEFAULT 'en',
            original_tour_id     integer,
            tour_content         text,
            content_language     varchar(10) DEFAULT 'en',
            stops_count          integer DEFAULT 0,
            creator_type         varchar(50) DEFAULT 'Official',
            description          text,
            derived_from_tour_id integer,
            draft                boolean DEFAULT false,
            tour_blob_uri        varchar(512),
            storied_mode         boolean DEFAULT false,
            i_con_avg            numeric(3,2),
            i_con_min            numeric(3,2),
            zip_filename         varchar(512),
            is_test              boolean DEFAULT false,
            CONSTRAINT audio_tours_pkey PRIMARY KEY (id)
        );

        ALTER SEQUENCE audio_tours_id_seq OWNED BY audio_tours.id;

        CREATE INDEX idx_audio_tours_language ON audio_tours (language);
        CREATE INDEX idx_audio_tours_location ON audio_tours (lat, lng);
        CREATE INDEX idx_audio_tours_original ON audio_tours (original_tour_id);
        CREATE INDEX idx_audio_tours_request_string ON audio_tours (request_string);
        CREATE INDEX idx_audio_tours_tour_name ON audio_tours (tour_name);
        CREATE INDEX idx_audio_tours_zip_filename ON audio_tours (zip_filename)
            WHERE zip_filename IS NOT NULL;
        CREATE UNIQUE INDEX uq_audio_tours_original_name
            ON audio_tours (lower(tour_name::text))
            WHERE original_tour_id IS NULL;

        ALTER TABLE audio_tours
            ADD CONSTRAINT audio_tours_original_tour_id_fkey
            FOREIGN KEY (original_tour_id) REFERENCES audio_tours(id);
        ALTER TABLE audio_tours
            ADD CONSTRAINT audio_tours_derived_from_tour_id_fkey
            FOREIGN KEY (derived_from_tour_id) REFERENCES audio_tours(id);
    """)

    # Create stop_metrics table (referenced by tests)
    cur_test.execute("""
        CREATE SEQUENCE IF NOT EXISTS stop_metrics_id_seq;

        CREATE TABLE stop_metrics (
            id                integer NOT NULL DEFAULT nextval('stop_metrics_id_seq'),
            job_id            varchar(50),
            tour_id           integer,
            stop_index        integer NOT NULL,
            stop_title        varchar(255),
            i_con             numeric(3,2),
            class_details     numeric(4,3),
            class_historic    numeric(4,3),
            class_social      numeric(4,3),
            paragraphs        jsonb,
            evaluator_version varchar(20) DEFAULT '1.0.0',
            prompt_hash       varchar(12),
            created_at        timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
            verified          boolean DEFAULT true,
            CONSTRAINT stop_metrics_pkey PRIMARY KEY (id)
        );

        ALTER SEQUENCE stop_metrics_id_seq OWNED BY stop_metrics.id;

        CREATE INDEX idx_stop_metrics_job_id ON stop_metrics (job_id);
        CREATE INDEX idx_stop_metrics_tour_id ON stop_metrics (tour_id);

        ALTER TABLE stop_metrics
            ADD CONSTRAINT stop_metrics_tour_id_fkey
            FOREIGN KEY (tour_id) REFERENCES audio_tours(id) ON DELETE CASCADE;
    """)

    # Create stop_corpus table (read-only reference data for tests)
    cur_test.execute("""
        CREATE SEQUENCE IF NOT EXISTS stop_corpus_id_seq;

        CREATE TABLE stop_corpus (
            id            integer NOT NULL DEFAULT nextval('stop_corpus_id_seq'),
            venue_name    text NOT NULL,
            stop_title    text NOT NULL,
            passages_json jsonb NOT NULL DEFAULT '[]',
            source_pages  jsonb NOT NULL DEFAULT '[]',
            passage_count integer NOT NULL DEFAULT 0,
            created_at    timestamp without time zone NOT NULL DEFAULT now(),
            passage_roles jsonb,
            CONSTRAINT stop_corpus_pkey PRIMARY KEY (id),
            CONSTRAINT stop_corpus_venue_name_stop_title_key UNIQUE (venue_name, stop_title)
        );

        ALTER SEQUENCE stop_corpus_id_seq OWNED BY stop_corpus.id;

        CREATE INDEX idx_stop_corpus_stop ON stop_corpus (stop_title);
        CREATE INDEX idx_stop_corpus_venue ON stop_corpus (venue_name);
    """)

    # Create venue_corpus table (read-only reference data for tests)
    cur_test.execute("""
        CREATE TABLE venue_corpus (
            qid                   varchar(20) NOT NULL,
            venue_name            text NOT NULL,
            official_url          text,
            canonical_titles_json jsonb NOT NULL,
            story_elements_json   jsonb,
            sparql_works_json     jsonb,
            pages_json            jsonb,
            language              varchar(10),
            tier                  varchar(20) NOT NULL,
            corpus_version        integer NOT NULL,
            created_at            timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
            expires_at            timestamp without time zone NOT NULL,
            CONSTRAINT venue_corpus_pkey PRIMARY KEY (qid)
        );

        CREATE INDEX idx_venue_corpus_expires ON venue_corpus (expires_at);
        CREATE INDEX idx_venue_corpus_tier ON venue_corpus (tier);
    """)

    conn_test.commit()
    print(f"[LOCAL-232] Schema created in '{TEST_DB_NAME}' (audio_tours, stop_metrics, stop_corpus, venue_corpus).")

    # ─── Copy reference data from production ────────────────────────────────
    import json
    from psycopg2.extras import execute_values, Json

    # Register Json adapter for jsonb columns
    psycopg2.extensions.register_adapter(dict, Json)
    psycopg2.extensions.register_adapter(list, Json)

    conn_prod = psycopg2.connect(
        host=config["host"],
        port=config["port"],
        dbname="audiotours",
        user=config["user"],
        password=config["password"],
    )
    cur_prod = conn_prod.cursor()

    # Copy stop_corpus data
    cur_prod.execute("SELECT id, venue_name, stop_title, passages_json, source_pages, passage_count, created_at, passage_roles FROM stop_corpus ORDER BY id")
    rows = cur_prod.fetchall()
    if rows:
        execute_values(
            cur_test,
            "INSERT INTO stop_corpus (id, venue_name, stop_title, passages_json, source_pages, passage_count, created_at, passage_roles) VALUES %s",
            rows,
        )
        # Reset sequence to max id
        cur_test.execute("SELECT setval('stop_corpus_id_seq', (SELECT COALESCE(MAX(id), 1) FROM stop_corpus))")
        conn_test.commit()
        print(f"[LOCAL-232] Copied {len(rows)} rows into stop_corpus.")

    # Copy venue_corpus data
    cur_prod.execute("SELECT qid, venue_name, official_url, canonical_titles_json, story_elements_json, sparql_works_json, pages_json, language, tier, corpus_version, created_at, expires_at FROM venue_corpus ORDER BY qid")
    rows = cur_prod.fetchall()
    if rows:
        from psycopg2.extras import execute_values
        execute_values(
            cur_test,
            "INSERT INTO venue_corpus (qid, venue_name, official_url, canonical_titles_json, story_elements_json, sparql_works_json, pages_json, language, tier, corpus_version, created_at, expires_at) VALUES %s",
            rows,
        )
        conn_test.commit()
        print(f"[LOCAL-232] Copied {len(rows)} rows into venue_corpus.")

    cur_prod.close()
    conn_prod.close()
    cur_test.close()
    conn_test.close()

    print(f"[LOCAL-232] Migration complete. Test database '{TEST_DB_NAME}' is ready.")


if __name__ == "__main__":
    migrate()
