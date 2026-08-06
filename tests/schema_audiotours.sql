--
-- PostgreSQL database dump
--

\restrict 0QjI6CA1OUUREbEad88ByvHns5NtGDn0kQlpPNMXq8C8yCeGqhmQKOxzyiInvsC

-- Dumped from database version 15.18
-- Dumped by pg_dump version 15.18

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: article_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.article_requests (
    id integer NOT NULL,
    secret_id text,
    article_id character varying(500),
    request_string text,
    article_topics integer DEFAULT 0 NOT NULL,
    article_text bytea,
    status character varying(50) DEFAULT 'started'::character varying,
    started_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    finished_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    major_points jsonb,
    url text DEFAULT NULL::character varying,
    article_type character varying(50) DEFAULT 'Others'::character varying,
    subscription_required boolean DEFAULT false,
    subscription_domain text,
    language character varying(10) DEFAULT 'en'::character varying,
    original_article_id character varying(500),
    content_language character varying(10) DEFAULT 'en'::character varying
);


--
-- Name: article_requests_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.article_requests_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: article_requests_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.article_requests_id_seq OWNED BY public.article_requests.id;


--
-- Name: audio_tours; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audio_tours (
    id integer NOT NULL,
    tour_name character varying(255) NOT NULL,
    request_string text NOT NULL,
    audio_tour bytea,
    number_requested integer DEFAULT 0 NOT NULL,
    lat double precision,
    lng double precision,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    language character varying(10) DEFAULT 'en'::character varying,
    original_tour_id integer,
    tour_content text,
    content_language character varying(10) DEFAULT 'en'::character varying,
    stops_count integer DEFAULT 0,
    creator_type character varying(50) DEFAULT 'Official'::character varying,
    description text,
    derived_from_tour_id integer,
    draft boolean DEFAULT false,
    tour_blob_uri character varying(512),
    storied_mode boolean DEFAULT false,
    i_con_avg numeric(3,2),
    i_con_min numeric(3,2),
    zip_filename character varying(512),
    is_test boolean DEFAULT false
);


--
-- Name: COLUMN audio_tours.original_tour_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.audio_tours.original_tour_id IS 'Reference to original tour for translations';


--
-- Name: COLUMN audio_tours.tour_content; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.audio_tours.tour_content IS 'Original ChatGPT-generated tour narration text for translation purposes';


--
-- Name: COLUMN audio_tours.content_language; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.audio_tours.content_language IS 'Language code (en, es, fr, de, ru, zh) for tour content';


--
-- Name: audio_tours_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.audio_tours_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: audio_tours_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.audio_tours_id_seq OWNED BY public.audio_tours.id;


--
-- Name: coordinates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.coordinates (
    id integer NOT NULL,
    secret_id character varying(255),
    lat double precision,
    lng double precision,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: coordinates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.coordinates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: coordinates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.coordinates_id_seq OWNED BY public.coordinates.id;


--
-- Name: cost_ledger; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cost_ledger (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    operation_type character varying(64) NOT NULL,
    user_id character varying(128),
    our_cost_usd numeric(12,6) NOT NULL,
    cache_hit boolean DEFAULT false NOT NULL,
    job_id character varying(128),
    breakdown jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    description character varying(256)
);


--
-- Name: TABLE cost_ledger; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.cost_ledger IS 'Per-operation cost ledger for Subscribed billing. One row per billable operation.';


--
-- Name: COLUMN cost_ledger.operation_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.cost_ledger.operation_type IS 'Enum-like: tour_generate, tour_cache_hit, translation_generate, translation_cache_hit, news_generate, photo_extension';


--
-- Name: COLUMN cost_ledger.our_cost_usd; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.cost_ledger.our_cost_usd IS 'True cost to us in USD. Cache hits = 0.00.';


--
-- Name: COLUMN cost_ledger.cache_hit; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.cost_ledger.cache_hit IS 'TRUE when served from cache (cost should be ~0).';


--
-- Name: COLUMN cost_ledger.breakdown; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.cost_ledger.breakdown IS 'JSON breakdown of cost components: {"llm": ..., "tts": ..., "search": ...}';


--
-- Name: device_consolidation_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_consolidation_history (
    id integer NOT NULL,
    consolidated_user_id character varying(255) NOT NULL,
    merged_device_id character varying(255) NOT NULL,
    domain character varying(255) NOT NULL,
    merged_at timestamp without time zone DEFAULT now()
);


--
-- Name: device_consolidation_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.device_consolidation_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: device_consolidation_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.device_consolidation_history_id_seq OWNED BY public.device_consolidation_history.id;


--
-- Name: device_encryption_keys; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_encryption_keys (
    device_id character varying(255) NOT NULL,
    encryption_key character varying(255) NOT NULL,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: dh_aes_keys; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dh_aes_keys (
    device_id character varying(255) NOT NULL,
    aes_key character varying(32) NOT NULL,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: dh_server_keys; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dh_server_keys (
    device_id character varying(255) NOT NULL,
    private_key text NOT NULL,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: domain_tier_cache; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.domain_tier_cache (
    domain character varying(255) NOT NULL,
    tier character varying(10) NOT NULL,
    checked_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamp without time zone NOT NULL
);


--
-- Name: job_status; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.job_status (
    job_id character varying(64) NOT NULL,
    service_name character varying(50) NOT NULL,
    status character varying(20) DEFAULT 'queued'::character varying NOT NULL,
    progress text,
    location text,
    tour_type character varying(50),
    total_stops integer,
    output_data jsonb,
    error text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: low_balance_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.low_balance_events (
    id integer NOT NULL,
    user_id character varying(255) NOT NULL,
    current_balance_usd numeric(10,4) NOT NULL,
    threshold_usd numeric(10,4) NOT NULL,
    acknowledged boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: low_balance_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.low_balance_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: low_balance_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.low_balance_events_id_seq OWNED BY public.low_balance_events.id;


--
-- Name: map_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.map_requests (
    id integer NOT NULL,
    secret_id character varying(255),
    lat double precision,
    lng double precision,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: map_requests_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.map_requests_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: map_requests_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.map_requests_id_seq OWNED BY public.map_requests.id;


--
-- Name: news_audios; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.news_audios (
    id integer NOT NULL,
    article_id text NOT NULL,
    article_name text NOT NULL,
    news_article bytea,
    number_requested integer NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    article_type character varying(50) DEFAULT 'Others'::character varying,
    language character varying(10) DEFAULT 'en'::character varying,
    original_article_id text,
    news_blob_uri character varying(512)
);


--
-- Name: news_audios_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.news_audios_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: news_audios_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.news_audios_id_seq OWNED BY public.news_audios.id;


--
-- Name: news_cache; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.news_cache (
    cache_key character varying(64) NOT NULL,
    article_id character varying(255) NOT NULL,
    article_text_hash character varying(64) NOT NULL,
    major_points_count integer DEFAULT 0 NOT NULL,
    request_string text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    hit_count integer DEFAULT 0,
    content_length integer DEFAULT 0
);


--
-- Name: TABLE news_cache; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.news_cache IS 'Content-addressed cache for news audio. Maps article text hash to existing news_audios row.';


--
-- Name: COLUMN news_cache.cache_key; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.news_cache.cache_key IS 'SHA256 of normalized_text + "|" + major_points_count';


--
-- Name: COLUMN news_cache.article_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.news_cache.article_id IS 'FK to article_requests.article_id / news_audios.article_id';


--
-- Name: COLUMN news_cache.article_text_hash; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.news_cache.article_text_hash IS 'SHA256 of raw article_text (for audit/debugging)';


--
-- Name: COLUMN news_cache.created_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.news_cache.created_at IS 'When the cache entry was created/refreshed. Used for TTL.';


--
-- Name: COLUMN news_cache.hit_count; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.news_cache.hit_count IS 'Number of cache hits (incremented atomically on each hit)';


--
-- Name: newsletter_server_keys; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.newsletter_server_keys (
    newsletter_id integer NOT NULL,
    private_key text NOT NULL,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: newsletters; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.newsletters (
    id integer NOT NULL,
    url character varying(1000) NOT NULL,
    type character varying(50) NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: newsletters_article_link; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.newsletters_article_link (
    id integer NOT NULL,
    newsletters_id integer,
    article_requests_id character varying(36),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: newsletters_article_link_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.newsletters_article_link_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: newsletters_article_link_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.newsletters_article_link_id_seq OWNED BY public.newsletters_article_link.id;


--
-- Name: newsletters_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.newsletters_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: newsletters_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.newsletters_id_seq OWNED BY public.newsletters.id;


--
-- Name: plans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.plans (
    plan_id character varying(20) NOT NULL,
    tours_per_day integer DEFAULT 1 NOT NULL,
    tour_max_poi integer DEFAULT 30 NOT NULL,
    tour_max_minutes integer DEFAULT 120 NOT NULL,
    news_per_period integer DEFAULT 10 NOT NULL,
    news_period character varying(10) DEFAULT 'day'::character varying NOT NULL,
    news_max_minutes integer DEFAULT 10 NOT NULL,
    downloads_unlimited boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: referral_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.referral_codes (
    code character varying(6) NOT NULL,
    referrer_user_id text NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    redemption_count integer DEFAULT 0
);


--
-- Name: referral_redemptions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.referral_redemptions (
    id integer NOT NULL,
    referral_code character varying(6) NOT NULL,
    new_user_id text NOT NULL,
    redeemed_at timestamp without time zone DEFAULT now()
);


--
-- Name: referral_redemptions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.referral_redemptions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: referral_redemptions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.referral_redemptions_id_seq OWNED BY public.referral_redemptions.id;


--
-- Name: revenuecat_webhook_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.revenuecat_webhook_events (
    event_id character varying(256) NOT NULL,
    event_type character varying(64) NOT NULL,
    user_id character varying(256) NOT NULL,
    product_id character varying(256),
    processed_at timestamp with time zone DEFAULT now() NOT NULL,
    payload_hash character varying(64) NOT NULL
);


--
-- Name: shared_tours; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.shared_tours (
    tour_id character varying(8) NOT NULL,
    tour_text text NOT NULL,
    location text NOT NULL,
    tour_type text NOT NULL,
    total_stops integer NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    share_count integer DEFAULT 0
);


--
-- Name: stop_corpus; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.stop_corpus (
    id integer NOT NULL,
    venue_name text NOT NULL,
    stop_title text NOT NULL,
    passages_json jsonb DEFAULT '[]'::jsonb NOT NULL,
    source_pages jsonb DEFAULT '[]'::jsonb NOT NULL,
    passage_count integer DEFAULT 0 NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    passage_roles jsonb
);


--
-- Name: stop_corpus_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.stop_corpus_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: stop_corpus_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.stop_corpus_id_seq OWNED BY public.stop_corpus.id;


--
-- Name: stop_metrics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.stop_metrics (
    id integer NOT NULL,
    job_id character varying(50),
    tour_id integer,
    stop_index integer NOT NULL,
    stop_title character varying(255),
    i_con numeric(3,2),
    class_details numeric(4,3),
    class_historic numeric(4,3),
    class_social numeric(4,3),
    paragraphs jsonb,
    evaluator_version character varying(20) DEFAULT '1.0.0'::character varying,
    prompt_hash character varying(12),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    verified boolean DEFAULT true
);


--
-- Name: stop_metrics_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.stop_metrics_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: stop_metrics_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.stop_metrics_id_seq OWNED BY public.stop_metrics.id;


--
-- Name: subscription_transactions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.subscription_transactions (
    id integer NOT NULL,
    user_id character varying(255) NOT NULL,
    transaction_type character varying(30) NOT NULL,
    transaction_id character varying(100),
    operation_type character varying(50),
    our_cost_usd numeric(10,6),
    user_charge_usd numeric(10,4),
    resulting_balance_usd numeric(10,4),
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: subscription_transactions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.subscription_transactions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: subscription_transactions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.subscription_transactions_id_seq OWNED BY public.subscription_transactions.id;


--
-- Name: subscriptions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.subscriptions (
    id integer NOT NULL,
    user_id character varying(255) NOT NULL,
    tier character varying(20) NOT NULL,
    state character varying(20) DEFAULT 'active'::character varying NOT NULL,
    period_start timestamp without time zone NOT NULL,
    period_end timestamp without time zone NOT NULL,
    provider_subscription_id character varying(255),
    credit_balance_usd numeric(10,4) DEFAULT 0.0,
    cost_used_this_period_usd numeric(10,4) DEFAULT 0.0,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT subscriptions_state_check CHECK (((state)::text = ANY ((ARRAY['active'::character varying, 'lapsed'::character varying, 'cancelled'::character varying, 'billing_retry'::character varying])::text[]))),
    CONSTRAINT subscriptions_tier_check CHECK (((tier)::text = ANY ((ARRAY['ppu'::character varying, 'unlimited'::character varying])::text[])))
);


--
-- Name: subscriptions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.subscriptions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: subscriptions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.subscriptions_id_seq OWNED BY public.subscriptions.id;


--
-- Name: supported_languages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.supported_languages (
    language_code character varying(10) NOT NULL,
    language_name character varying(50) NOT NULL,
    polly_voice_id character varying(50),
    enabled boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: test_content_storage; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.test_content_storage (
    id integer NOT NULL,
    article_text bytea,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: test_content_storage_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.test_content_storage_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: test_content_storage_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.test_content_storage_id_seq OWNED BY public.test_content_storage.id;


--
-- Name: tour_cache; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tour_cache (
    cache_key character varying(64) NOT NULL,
    location text NOT NULL,
    tour_type text NOT NULL,
    total_stops integer NOT NULL,
    tour_content text NOT NULL,
    spine_json text,
    created_at timestamp without time zone DEFAULT now(),
    hit_count integer DEFAULT 0
);


--
-- Name: tour_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tour_requests (
    id integer NOT NULL,
    secret_id character varying(255),
    tour_id character varying(255),
    request_string text,
    status character varying(50) DEFAULT 'started'::character varying,
    started_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    finished_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    language character varying(10) DEFAULT 'en'::character varying,
    source character varying(50) DEFAULT 'orchestrator'::character varying
);


--
-- Name: tour_requests_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tour_requests_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tour_requests_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tour_requests_id_seq OWNED BY public.tour_requests.id;


--
-- Name: treats; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.treats (
    id integer NOT NULL,
    ad_name character varying(255) NOT NULL,
    ad_image bytea,
    ad_text text,
    lat double precision,
    lng double precision,
    distance_in_feet integer DEFAULT 0 NOT NULL,
    link_to_vendor character varying(1001)
);


--
-- Name: treats_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.treats_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: treats_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.treats_id_seq OWNED BY public.treats.id;


--
-- Name: usage_counters; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.usage_counters (
    id integer NOT NULL,
    user_id character varying(64) NOT NULL,
    period_key character varying(20) NOT NULL,
    kind character varying(20) NOT NULL,
    count integer DEFAULT 0 NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: usage_counters_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.usage_counters_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: usage_counters_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.usage_counters_id_seq OWNED BY public.usage_counters.id;


--
-- Name: user_class_prefs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_class_prefs (
    user_id character varying(255) NOT NULL,
    alpha_details numeric(8,4) DEFAULT 1.0 NOT NULL,
    beta_details numeric(8,4) DEFAULT 1.0 NOT NULL,
    alpha_historic numeric(8,4) DEFAULT 1.0 NOT NULL,
    beta_historic numeric(8,4) DEFAULT 1.0 NOT NULL,
    alpha_social numeric(8,4) DEFAULT 1.0 NOT NULL,
    beta_social numeric(8,4) DEFAULT 1.0 NOT NULL,
    pref_details numeric(5,4) DEFAULT 0.5000 NOT NULL,
    pref_historic numeric(5,4) DEFAULT 0.5000 NOT NULL,
    pref_social numeric(5,4) DEFAULT 0.5000 NOT NULL,
    swipe_count integer DEFAULT 0 NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: user_consolidation_map; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_consolidation_map (
    consolidated_user_id character varying(255) NOT NULL,
    primary_device_id character varying(255) NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    last_merged_at timestamp without time zone DEFAULT now()
);


--
-- Name: user_preferences; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_preferences (
    user_id text NOT NULL,
    persona text NOT NULL,
    updated_at timestamp without time zone DEFAULT now()
);


--
-- Name: user_stop_feedback; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_stop_feedback (
    id integer NOT NULL,
    user_id character varying(255) NOT NULL,
    tour_id integer,
    job_id character varying(255),
    stop_index integer NOT NULL,
    swipe smallint NOT NULL,
    class_details numeric(4,3) NOT NULL,
    class_historic numeric(4,3) NOT NULL,
    class_social numeric(4,3) NOT NULL,
    i_con numeric(3,2) DEFAULT 0.00 NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT user_stop_feedback_swipe_check CHECK ((swipe = ANY (ARRAY['-1'::integer, 1])))
);


--
-- Name: user_stop_feedback_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_stop_feedback_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_stop_feedback_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_stop_feedback_id_seq OWNED BY public.user_stop_feedback.id;


--
-- Name: user_subscription_credentials; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_subscription_credentials (
    id integer NOT NULL,
    device_id character varying(255) NOT NULL,
    article_id character varying(255) NOT NULL,
    domain character varying(255) NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    decrypted_username character varying(255),
    decrypted_password character varying(255),
    consolidated_user_id character varying(255),
    verified_at timestamp without time zone
);


--
-- Name: user_subscription_credentials_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_subscription_credentials_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_subscription_credentials_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_subscription_credentials_id_seq OWNED BY public.user_subscription_credentials.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    secret_id character varying(255) NOT NULL,
    app_version character varying(50) DEFAULT 'unknown'::character varying,
    is_deleted boolean DEFAULT false,
    app_uninstalled boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone,
    plan character varying(20) DEFAULT 'free'::character varying,
    tours_per_day_override integer
);


--
-- Name: venue_corpus; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.venue_corpus (
    qid character varying(20) NOT NULL,
    venue_name text NOT NULL,
    official_url text,
    canonical_titles_json jsonb NOT NULL,
    story_elements_json jsonb,
    sparql_works_json jsonb,
    pages_json jsonb,
    language character varying(10),
    tier character varying(20) NOT NULL,
    corpus_version integer NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamp without time zone NOT NULL
);


--
-- Name: wallet_balance_cache; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.wallet_balance_cache (
    user_id character varying(128) NOT NULL,
    balance_cents integer DEFAULT 0 NOT NULL,
    last_ledger_id uuid,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE wallet_balance_cache; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.wallet_balance_cache IS 'Cached balance for fast reads. Rebuildable from wallet_ledger at any time.';


--
-- Name: wallet_ledger; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.wallet_ledger (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id character varying(128) NOT NULL,
    movement_type character varying(64) NOT NULL,
    amount_cents integer NOT NULL,
    balance_after_cents integer NOT NULL,
    idempotency_key character varying(256) NOT NULL,
    description text,
    reference_id character varying(256),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE wallet_ledger; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.wallet_ledger IS 'Append-only user wallet ledger. One row per money movement. Never mutate rows.';


--
-- Name: COLUMN wallet_ledger.movement_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.wallet_ledger.movement_type IS 'topup, charge, refund_clawback, monthly_fee, monthly_fee_unlimited';


--
-- Name: COLUMN wallet_ledger.amount_cents; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.wallet_ledger.amount_cents IS 'Positive = credit to user (topup, refund). Negative = debit (charge, fee, clawback).';


--
-- Name: COLUMN wallet_ledger.balance_after_cents; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.wallet_ledger.balance_after_cents IS 'Running balance snapshot after this movement. Matches SUM(amount_cents) up to this row.';


--
-- Name: COLUMN wallet_ledger.idempotency_key; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.wallet_ledger.idempotency_key IS 'Caller-supplied. Duplicate key = reject (idempotent retry safety).';


--
-- Name: wallet_subscription; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.wallet_subscription (
    user_id character varying(128) NOT NULL,
    tier character varying(32) DEFAULT 'free'::character varying NOT NULL,
    period_start timestamp with time zone,
    period_end timestamp with time zone,
    monthly_cost_spent_cents integer DEFAULT 0 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE wallet_subscription; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.wallet_subscription IS 'User subscription tier. Minimal — full lifecycle in LOCAL-61.';


--
-- Name: work_stories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.work_stories (
    id integer NOT NULL,
    work_key character varying(512) NOT NULL,
    work_qid character varying(20),
    title text NOT NULL,
    artist text,
    core_data jsonb NOT NULL,
    elements_json jsonb,
    sources_json jsonb,
    query_log jsonb,
    core_expires_at timestamp without time zone NOT NULL,
    elements_expires_at timestamp without time zone NOT NULL,
    corpus_version integer DEFAULT 1 NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: work_stories_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.work_stories_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: work_stories_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.work_stories_id_seq OWNED BY public.work_stories.id;


--
-- Name: article_requests id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.article_requests ALTER COLUMN id SET DEFAULT nextval('public.article_requests_id_seq'::regclass);


--
-- Name: audio_tours id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audio_tours ALTER COLUMN id SET DEFAULT nextval('public.audio_tours_id_seq'::regclass);


--
-- Name: coordinates id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coordinates ALTER COLUMN id SET DEFAULT nextval('public.coordinates_id_seq'::regclass);


--
-- Name: device_consolidation_history id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_consolidation_history ALTER COLUMN id SET DEFAULT nextval('public.device_consolidation_history_id_seq'::regclass);


--
-- Name: low_balance_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.low_balance_events ALTER COLUMN id SET DEFAULT nextval('public.low_balance_events_id_seq'::regclass);


--
-- Name: map_requests id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.map_requests ALTER COLUMN id SET DEFAULT nextval('public.map_requests_id_seq'::regclass);


--
-- Name: news_audios id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.news_audios ALTER COLUMN id SET DEFAULT nextval('public.news_audios_id_seq'::regclass);


--
-- Name: newsletters id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.newsletters ALTER COLUMN id SET DEFAULT nextval('public.newsletters_id_seq'::regclass);


--
-- Name: newsletters_article_link id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.newsletters_article_link ALTER COLUMN id SET DEFAULT nextval('public.newsletters_article_link_id_seq'::regclass);


--
-- Name: referral_redemptions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_redemptions ALTER COLUMN id SET DEFAULT nextval('public.referral_redemptions_id_seq'::regclass);


--
-- Name: stop_corpus id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stop_corpus ALTER COLUMN id SET DEFAULT nextval('public.stop_corpus_id_seq'::regclass);


--
-- Name: stop_metrics id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stop_metrics ALTER COLUMN id SET DEFAULT nextval('public.stop_metrics_id_seq'::regclass);


--
-- Name: subscription_transactions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subscription_transactions ALTER COLUMN id SET DEFAULT nextval('public.subscription_transactions_id_seq'::regclass);


--
-- Name: subscriptions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subscriptions ALTER COLUMN id SET DEFAULT nextval('public.subscriptions_id_seq'::regclass);


--
-- Name: test_content_storage id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.test_content_storage ALTER COLUMN id SET DEFAULT nextval('public.test_content_storage_id_seq'::regclass);


--
-- Name: tour_requests id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_requests ALTER COLUMN id SET DEFAULT nextval('public.tour_requests_id_seq'::regclass);


--
-- Name: treats id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treats ALTER COLUMN id SET DEFAULT nextval('public.treats_id_seq'::regclass);


--
-- Name: usage_counters id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usage_counters ALTER COLUMN id SET DEFAULT nextval('public.usage_counters_id_seq'::regclass);


--
-- Name: user_stop_feedback id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_stop_feedback ALTER COLUMN id SET DEFAULT nextval('public.user_stop_feedback_id_seq'::regclass);


--
-- Name: user_subscription_credentials id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_subscription_credentials ALTER COLUMN id SET DEFAULT nextval('public.user_subscription_credentials_id_seq'::regclass);


--
-- Name: work_stories id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.work_stories ALTER COLUMN id SET DEFAULT nextval('public.work_stories_id_seq'::regclass);


--
-- Name: article_requests article_requests_article_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.article_requests
    ADD CONSTRAINT article_requests_article_id_key UNIQUE (article_id);


--
-- Name: article_requests article_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.article_requests
    ADD CONSTRAINT article_requests_pkey PRIMARY KEY (id);


--
-- Name: article_requests article_requests_url_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.article_requests
    ADD CONSTRAINT article_requests_url_key UNIQUE (url);


--
-- Name: audio_tours audio_tours_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audio_tours
    ADD CONSTRAINT audio_tours_pkey PRIMARY KEY (id);


--
-- Name: coordinates coordinates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coordinates
    ADD CONSTRAINT coordinates_pkey PRIMARY KEY (id);


--
-- Name: cost_ledger cost_ledger_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_ledger
    ADD CONSTRAINT cost_ledger_pkey PRIMARY KEY (id);


--
-- Name: device_consolidation_history device_consolidation_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_consolidation_history
    ADD CONSTRAINT device_consolidation_history_pkey PRIMARY KEY (id);


--
-- Name: device_encryption_keys device_encryption_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_encryption_keys
    ADD CONSTRAINT device_encryption_keys_pkey PRIMARY KEY (device_id);


--
-- Name: dh_aes_keys dh_aes_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dh_aes_keys
    ADD CONSTRAINT dh_aes_keys_pkey PRIMARY KEY (device_id);


--
-- Name: dh_server_keys dh_server_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dh_server_keys
    ADD CONSTRAINT dh_server_keys_pkey PRIMARY KEY (device_id);


--
-- Name: domain_tier_cache domain_tier_cache_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_tier_cache
    ADD CONSTRAINT domain_tier_cache_pkey PRIMARY KEY (domain);


--
-- Name: job_status job_status_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_status
    ADD CONSTRAINT job_status_pkey PRIMARY KEY (job_id);


--
-- Name: low_balance_events low_balance_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.low_balance_events
    ADD CONSTRAINT low_balance_events_pkey PRIMARY KEY (id);


--
-- Name: map_requests map_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.map_requests
    ADD CONSTRAINT map_requests_pkey PRIMARY KEY (id);


--
-- Name: news_audios news_audios_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.news_audios
    ADD CONSTRAINT news_audios_pkey PRIMARY KEY (id);


--
-- Name: news_cache news_cache_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.news_cache
    ADD CONSTRAINT news_cache_pkey PRIMARY KEY (cache_key);


--
-- Name: newsletter_server_keys newsletter_server_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.newsletter_server_keys
    ADD CONSTRAINT newsletter_server_keys_pkey PRIMARY KEY (newsletter_id);


--
-- Name: newsletters_article_link newsletters_article_link_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.newsletters_article_link
    ADD CONSTRAINT newsletters_article_link_pkey PRIMARY KEY (id);


--
-- Name: newsletters newsletters_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.newsletters
    ADD CONSTRAINT newsletters_pkey PRIMARY KEY (id);


--
-- Name: plans plans_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plans
    ADD CONSTRAINT plans_pkey PRIMARY KEY (plan_id);


--
-- Name: referral_codes referral_codes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_codes
    ADD CONSTRAINT referral_codes_pkey PRIMARY KEY (code);


--
-- Name: referral_redemptions referral_redemptions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_redemptions
    ADD CONSTRAINT referral_redemptions_pkey PRIMARY KEY (id);


--
-- Name: revenuecat_webhook_events revenuecat_webhook_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.revenuecat_webhook_events
    ADD CONSTRAINT revenuecat_webhook_events_pkey PRIMARY KEY (event_id);


--
-- Name: shared_tours shared_tours_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shared_tours
    ADD CONSTRAINT shared_tours_pkey PRIMARY KEY (tour_id);


--
-- Name: stop_corpus stop_corpus_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stop_corpus
    ADD CONSTRAINT stop_corpus_pkey PRIMARY KEY (id);


--
-- Name: stop_corpus stop_corpus_venue_name_stop_title_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stop_corpus
    ADD CONSTRAINT stop_corpus_venue_name_stop_title_key UNIQUE (venue_name, stop_title);


--
-- Name: stop_metrics stop_metrics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stop_metrics
    ADD CONSTRAINT stop_metrics_pkey PRIMARY KEY (id);


--
-- Name: subscription_transactions subscription_transactions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subscription_transactions
    ADD CONSTRAINT subscription_transactions_pkey PRIMARY KEY (id);


--
-- Name: subscriptions subscriptions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_pkey PRIMARY KEY (id);


--
-- Name: supported_languages supported_languages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supported_languages
    ADD CONSTRAINT supported_languages_pkey PRIMARY KEY (language_code);


--
-- Name: test_content_storage test_content_storage_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.test_content_storage
    ADD CONSTRAINT test_content_storage_pkey PRIMARY KEY (id);


--
-- Name: tour_cache tour_cache_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_cache
    ADD CONSTRAINT tour_cache_pkey PRIMARY KEY (cache_key);


--
-- Name: tour_requests tour_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_requests
    ADD CONSTRAINT tour_requests_pkey PRIMARY KEY (id);


--
-- Name: treats treats_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treats
    ADD CONSTRAINT treats_pkey PRIMARY KEY (id);


--
-- Name: user_subscription_credentials unique_device_domain; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_subscription_credentials
    ADD CONSTRAINT unique_device_domain UNIQUE (device_id, domain);


--
-- Name: referral_redemptions uq_referral_redemptions_code_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_redemptions
    ADD CONSTRAINT uq_referral_redemptions_code_user UNIQUE (referral_code, new_user_id);


--
-- Name: usage_counters usage_counters_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usage_counters
    ADD CONSTRAINT usage_counters_pkey PRIMARY KEY (id);


--
-- Name: usage_counters usage_counters_user_id_period_key_kind_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usage_counters
    ADD CONSTRAINT usage_counters_user_id_period_key_kind_key UNIQUE (user_id, period_key, kind);


--
-- Name: user_class_prefs user_class_prefs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_class_prefs
    ADD CONSTRAINT user_class_prefs_pkey PRIMARY KEY (user_id);


--
-- Name: user_consolidation_map user_consolidation_map_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_consolidation_map
    ADD CONSTRAINT user_consolidation_map_pkey PRIMARY KEY (consolidated_user_id);


--
-- Name: user_preferences user_preferences_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_preferences
    ADD CONSTRAINT user_preferences_pkey PRIMARY KEY (user_id);


--
-- Name: user_stop_feedback user_stop_feedback_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_stop_feedback
    ADD CONSTRAINT user_stop_feedback_pkey PRIMARY KEY (id);


--
-- Name: user_subscription_credentials user_subscription_credentials_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_subscription_credentials
    ADD CONSTRAINT user_subscription_credentials_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (secret_id);


--
-- Name: venue_corpus venue_corpus_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.venue_corpus
    ADD CONSTRAINT venue_corpus_pkey PRIMARY KEY (qid);


--
-- Name: wallet_balance_cache wallet_balance_cache_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_balance_cache
    ADD CONSTRAINT wallet_balance_cache_pkey PRIMARY KEY (user_id);


--
-- Name: wallet_ledger wallet_ledger_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_ledger
    ADD CONSTRAINT wallet_ledger_pkey PRIMARY KEY (id);


--
-- Name: wallet_subscription wallet_subscription_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_subscription
    ADD CONSTRAINT wallet_subscription_pkey PRIMARY KEY (user_id);


--
-- Name: work_stories work_stories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.work_stories
    ADD CONSTRAINT work_stories_pkey PRIMARY KEY (id);


--
-- Name: work_stories work_stories_work_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.work_stories
    ADD CONSTRAINT work_stories_work_key_key UNIQUE (work_key);


--
-- Name: idx_article_requests_article_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_article_requests_article_id ON public.article_requests USING btree (article_id);


--
-- Name: idx_article_requests_language; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_article_requests_language ON public.article_requests USING btree (language);


--
-- Name: idx_article_requests_secret_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_article_requests_secret_id ON public.article_requests USING btree (secret_id);


--
-- Name: idx_article_subscription; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_article_subscription ON public.article_requests USING btree (subscription_required, subscription_domain);


--
-- Name: idx_audio_tours_language; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audio_tours_language ON public.audio_tours USING btree (language);


--
-- Name: idx_audio_tours_location; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audio_tours_location ON public.audio_tours USING btree (lat, lng);


--
-- Name: idx_audio_tours_original; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audio_tours_original ON public.audio_tours USING btree (original_tour_id);


--
-- Name: idx_audio_tours_request_string; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audio_tours_request_string ON public.audio_tours USING btree (request_string);


--
-- Name: idx_audio_tours_tour_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audio_tours_tour_name ON public.audio_tours USING btree (tour_name);


--
-- Name: idx_audio_tours_zip_filename; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audio_tours_zip_filename ON public.audio_tours USING btree (zip_filename) WHERE (zip_filename IS NOT NULL);


--
-- Name: idx_consolidated_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_consolidated_user ON public.user_subscription_credentials USING btree (consolidated_user_id);


--
-- Name: idx_consolidation_history_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_consolidation_history_user ON public.device_consolidation_history USING btree (consolidated_user_id);


--
-- Name: idx_cost_ledger_job; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cost_ledger_job ON public.cost_ledger USING btree (job_id);


--
-- Name: idx_cost_ledger_operation_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cost_ledger_operation_type ON public.cost_ledger USING btree (operation_type, created_at);


--
-- Name: idx_cost_ledger_user_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cost_ledger_user_time ON public.cost_ledger USING btree (user_id, created_at);


--
-- Name: idx_credentials_device_domain; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_credentials_device_domain ON public.user_subscription_credentials USING btree (device_id, domain);


--
-- Name: idx_domain_tier_expires; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domain_tier_expires ON public.domain_tier_cache USING btree (expires_at);


--
-- Name: idx_job_status_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_status_created ON public.job_status USING btree (created_at);


--
-- Name: idx_job_status_service_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_status_service_created ON public.job_status USING btree (service_name, created_at DESC);


--
-- Name: idx_low_balance_pending; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_low_balance_pending ON public.low_balance_events USING btree (user_id, acknowledged) WHERE (acknowledged = false);


--
-- Name: idx_news_audios_article_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_news_audios_article_id ON public.news_audios USING btree (article_id);


--
-- Name: idx_news_audios_language; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_news_audios_language ON public.news_audios USING btree (language);


--
-- Name: idx_news_cache_article_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_news_cache_article_id ON public.news_cache USING btree (article_id);


--
-- Name: idx_news_cache_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_news_cache_created_at ON public.news_cache USING btree (created_at);


--
-- Name: idx_newsletters_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_newsletters_created_at ON public.newsletters USING btree (created_at);


--
-- Name: idx_newsletters_url; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_newsletters_url ON public.newsletters USING btree (url);


--
-- Name: idx_stop_corpus_stop; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stop_corpus_stop ON public.stop_corpus USING btree (stop_title);


--
-- Name: idx_stop_corpus_venue; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stop_corpus_venue ON public.stop_corpus USING btree (venue_name);


--
-- Name: idx_stop_metrics_job_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stop_metrics_job_id ON public.stop_metrics USING btree (job_id);


--
-- Name: idx_stop_metrics_tour_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stop_metrics_tour_id ON public.stop_metrics USING btree (tour_id);


--
-- Name: idx_sub_txn_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sub_txn_type ON public.subscription_transactions USING btree (transaction_type);


--
-- Name: idx_sub_txn_user_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sub_txn_user_created ON public.subscription_transactions USING btree (user_id, created_at DESC);


--
-- Name: idx_subscriptions_active_user; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_subscriptions_active_user ON public.subscriptions USING btree (user_id) WHERE ((state)::text = ANY ((ARRAY['active'::character varying, 'billing_retry'::character varying])::text[]));


--
-- Name: idx_subscriptions_provider_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_subscriptions_provider_id ON public.subscriptions USING btree (provider_subscription_id);


--
-- Name: idx_tour_requests_language; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tour_requests_language ON public.tour_requests USING btree (language);


--
-- Name: idx_treats_location; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_treats_location ON public.treats USING btree (lat, lng);


--
-- Name: idx_usage_counters_user_period; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_usage_counters_user_period ON public.usage_counters USING btree (user_id, period_key);


--
-- Name: idx_usf_tour_stop; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_usf_tour_stop ON public.user_stop_feedback USING btree (tour_id, stop_index);


--
-- Name: idx_usf_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_usf_user_id ON public.user_stop_feedback USING btree (user_id);


--
-- Name: idx_venue_corpus_expires; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_venue_corpus_expires ON public.venue_corpus USING btree (expires_at);


--
-- Name: idx_venue_corpus_tier; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_venue_corpus_tier ON public.venue_corpus USING btree (tier);


--
-- Name: idx_wallet_ledger_idempotency; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_wallet_ledger_idempotency ON public.wallet_ledger USING btree (idempotency_key);


--
-- Name: idx_wallet_ledger_reference; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wallet_ledger_reference ON public.wallet_ledger USING btree (reference_id);


--
-- Name: idx_wallet_ledger_user_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wallet_ledger_user_time ON public.wallet_ledger USING btree (user_id, created_at DESC);


--
-- Name: idx_work_stories_expires; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_work_stories_expires ON public.work_stories USING btree (elements_expires_at);


--
-- Name: idx_work_stories_qid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_work_stories_qid ON public.work_stories USING btree (work_qid) WHERE (work_qid IS NOT NULL);


--
-- Name: uq_audio_tours_original_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_audio_tours_original_name ON public.audio_tours USING btree (lower((tour_name)::text)) WHERE (original_tour_id IS NULL);


--
-- Name: article_requests article_requests_original_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.article_requests
    ADD CONSTRAINT article_requests_original_article_id_fkey FOREIGN KEY (original_article_id) REFERENCES public.article_requests(article_id);


--
-- Name: article_requests article_requests_secret_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.article_requests
    ADD CONSTRAINT article_requests_secret_id_fkey FOREIGN KEY (secret_id) REFERENCES public.users(secret_id);


--
-- Name: audio_tours audio_tours_derived_from_tour_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audio_tours
    ADD CONSTRAINT audio_tours_derived_from_tour_id_fkey FOREIGN KEY (derived_from_tour_id) REFERENCES public.audio_tours(id);


--
-- Name: audio_tours audio_tours_original_tour_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audio_tours
    ADD CONSTRAINT audio_tours_original_tour_id_fkey FOREIGN KEY (original_tour_id) REFERENCES public.audio_tours(id);


--
-- Name: coordinates coordinates_secret_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coordinates
    ADD CONSTRAINT coordinates_secret_id_fkey FOREIGN KEY (secret_id) REFERENCES public.users(secret_id);


--
-- Name: low_balance_events low_balance_events_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.low_balance_events
    ADD CONSTRAINT low_balance_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(secret_id) ON DELETE CASCADE;


--
-- Name: map_requests map_requests_secret_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.map_requests
    ADD CONSTRAINT map_requests_secret_id_fkey FOREIGN KEY (secret_id) REFERENCES public.users(secret_id);


--
-- Name: news_audios news_audios_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.news_audios
    ADD CONSTRAINT news_audios_article_id_fkey FOREIGN KEY (article_id) REFERENCES public.article_requests(article_id);


--
-- Name: referral_redemptions referral_redemptions_referral_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_redemptions
    ADD CONSTRAINT referral_redemptions_referral_code_fkey FOREIGN KEY (referral_code) REFERENCES public.referral_codes(code);


--
-- Name: stop_metrics stop_metrics_tour_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stop_metrics
    ADD CONSTRAINT stop_metrics_tour_id_fkey FOREIGN KEY (tour_id) REFERENCES public.audio_tours(id) ON DELETE CASCADE;


--
-- Name: subscription_transactions subscription_transactions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subscription_transactions
    ADD CONSTRAINT subscription_transactions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(secret_id) ON DELETE CASCADE;


--
-- Name: subscriptions subscriptions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(secret_id) ON DELETE CASCADE;


--
-- Name: tour_requests tour_requests_secret_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_requests
    ADD CONSTRAINT tour_requests_secret_id_fkey FOREIGN KEY (secret_id) REFERENCES public.users(secret_id);


--
-- Name: user_subscription_credentials user_subscription_credentials_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_subscription_credentials
    ADD CONSTRAINT user_subscription_credentials_article_id_fkey FOREIGN KEY (article_id) REFERENCES public.article_requests(article_id) ON DELETE CASCADE;


--
-- Name: users users_plan_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_plan_fkey FOREIGN KEY (plan) REFERENCES public.plans(plan_id);


--
-- PostgreSQL database dump complete
--

\unrestrict 0QjI6CA1OUUREbEad88ByvHns5NtGDn0kQlpPNMXq8C8yCeGqhmQKOxzyiInvsC

