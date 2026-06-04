--
-- PostgreSQL database dump
--

-- Dumped from database version 15.13
-- Dumped by pg_dump version 15.13

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
-- Name: article_requests; Type: TABLE; Schema: public; Owner: admin
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


ALTER TABLE public.article_requests OWNER TO admin;

--
-- Name: article_requests_id_seq; Type: SEQUENCE; Schema: public; Owner: admin
--

CREATE SEQUENCE public.article_requests_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.article_requests_id_seq OWNER TO admin;

--
-- Name: article_requests_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: admin
--

ALTER SEQUENCE public.article_requests_id_seq OWNED BY public.article_requests.id;


--
-- Name: audio_tours; Type: TABLE; Schema: public; Owner: admin
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
    tour_blob_uri character varying(512)
);


ALTER TABLE public.audio_tours OWNER TO admin;

--
-- Name: COLUMN audio_tours.original_tour_id; Type: COMMENT; Schema: public; Owner: admin
--

COMMENT ON COLUMN public.audio_tours.original_tour_id IS 'Reference to original tour for translations';


--
-- Name: COLUMN audio_tours.tour_content; Type: COMMENT; Schema: public; Owner: admin
--

COMMENT ON COLUMN public.audio_tours.tour_content IS 'Original ChatGPT-generated tour narration text for translation purposes';


--
-- Name: COLUMN audio_tours.content_language; Type: COMMENT; Schema: public; Owner: admin
--

COMMENT ON COLUMN public.audio_tours.content_language IS 'Language code (en, es, fr, de, ru, zh) for tour content';


--
-- Name: audio_tours_id_seq; Type: SEQUENCE; Schema: public; Owner: admin
--

CREATE SEQUENCE public.audio_tours_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.audio_tours_id_seq OWNER TO admin;

--
-- Name: audio_tours_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: admin
--

ALTER SEQUENCE public.audio_tours_id_seq OWNED BY public.audio_tours.id;


--
-- Name: coordinates; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.coordinates (
    id integer NOT NULL,
    secret_id character varying(255),
    lat double precision,
    lng double precision,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.coordinates OWNER TO admin;

--
-- Name: coordinates_id_seq; Type: SEQUENCE; Schema: public; Owner: admin
--

CREATE SEQUENCE public.coordinates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.coordinates_id_seq OWNER TO admin;

--
-- Name: coordinates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: admin
--

ALTER SEQUENCE public.coordinates_id_seq OWNED BY public.coordinates.id;


--
-- Name: device_consolidation_history; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.device_consolidation_history (
    id integer NOT NULL,
    consolidated_user_id character varying(255) NOT NULL,
    merged_device_id character varying(255) NOT NULL,
    domain character varying(255) NOT NULL,
    merged_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.device_consolidation_history OWNER TO admin;

--
-- Name: device_consolidation_history_id_seq; Type: SEQUENCE; Schema: public; Owner: admin
--

CREATE SEQUENCE public.device_consolidation_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.device_consolidation_history_id_seq OWNER TO admin;

--
-- Name: device_consolidation_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: admin
--

ALTER SEQUENCE public.device_consolidation_history_id_seq OWNED BY public.device_consolidation_history.id;


--
-- Name: device_encryption_keys; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.device_encryption_keys (
    device_id character varying(255) NOT NULL,
    encryption_key character varying(255) NOT NULL,
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.device_encryption_keys OWNER TO admin;

--
-- Name: dh_aes_keys; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.dh_aes_keys (
    device_id character varying(255) NOT NULL,
    aes_key character varying(32) NOT NULL,
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.dh_aes_keys OWNER TO admin;

--
-- Name: dh_server_keys; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.dh_server_keys (
    device_id character varying(255) NOT NULL,
    private_key text NOT NULL,
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.dh_server_keys OWNER TO admin;

--
-- Name: job_status; Type: TABLE; Schema: public; Owner: admin
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


ALTER TABLE public.job_status OWNER TO admin;

--
-- Name: map_requests; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.map_requests (
    id integer NOT NULL,
    secret_id character varying(255),
    lat double precision,
    lng double precision,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.map_requests OWNER TO admin;

--
-- Name: map_requests_id_seq; Type: SEQUENCE; Schema: public; Owner: admin
--

CREATE SEQUENCE public.map_requests_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.map_requests_id_seq OWNER TO admin;

--
-- Name: map_requests_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: admin
--

ALTER SEQUENCE public.map_requests_id_seq OWNED BY public.map_requests.id;


--
-- Name: news_audios; Type: TABLE; Schema: public; Owner: admin
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


ALTER TABLE public.news_audios OWNER TO admin;

--
-- Name: news_audios_id_seq; Type: SEQUENCE; Schema: public; Owner: admin
--

CREATE SEQUENCE public.news_audios_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.news_audios_id_seq OWNER TO admin;

--
-- Name: news_audios_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: admin
--

ALTER SEQUENCE public.news_audios_id_seq OWNED BY public.news_audios.id;


--
-- Name: newsletter_server_keys; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.newsletter_server_keys (
    newsletter_id integer NOT NULL,
    private_key text NOT NULL,
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.newsletter_server_keys OWNER TO admin;

--
-- Name: newsletters; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.newsletters (
    id integer NOT NULL,
    url character varying(1000) NOT NULL,
    type character varying(50) NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.newsletters OWNER TO admin;

--
-- Name: newsletters_article_link; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.newsletters_article_link (
    id integer NOT NULL,
    newsletters_id integer,
    article_requests_id character varying(36),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.newsletters_article_link OWNER TO admin;

--
-- Name: newsletters_article_link_id_seq; Type: SEQUENCE; Schema: public; Owner: admin
--

CREATE SEQUENCE public.newsletters_article_link_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.newsletters_article_link_id_seq OWNER TO admin;

--
-- Name: newsletters_article_link_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: admin
--

ALTER SEQUENCE public.newsletters_article_link_id_seq OWNED BY public.newsletters_article_link.id;


--
-- Name: newsletters_id_seq; Type: SEQUENCE; Schema: public; Owner: admin
--

CREATE SEQUENCE public.newsletters_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.newsletters_id_seq OWNER TO admin;

--
-- Name: newsletters_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: admin
--

ALTER SEQUENCE public.newsletters_id_seq OWNED BY public.newsletters.id;


--
-- Name: supported_languages; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.supported_languages (
    language_code character varying(10) NOT NULL,
    language_name character varying(50) NOT NULL,
    polly_voice_id character varying(50),
    enabled boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.supported_languages OWNER TO admin;

--
-- Name: test_content_storage; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.test_content_storage (
    id integer NOT NULL,
    article_text bytea,
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.test_content_storage OWNER TO admin;

--
-- Name: test_content_storage_id_seq; Type: SEQUENCE; Schema: public; Owner: admin
--

CREATE SEQUENCE public.test_content_storage_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.test_content_storage_id_seq OWNER TO admin;

--
-- Name: test_content_storage_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: admin
--

ALTER SEQUENCE public.test_content_storage_id_seq OWNED BY public.test_content_storage.id;


--
-- Name: tour_requests; Type: TABLE; Schema: public; Owner: admin
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
    language character varying(10) DEFAULT 'en'::character varying
);


ALTER TABLE public.tour_requests OWNER TO admin;

--
-- Name: tour_requests_id_seq; Type: SEQUENCE; Schema: public; Owner: admin
--

CREATE SEQUENCE public.tour_requests_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.tour_requests_id_seq OWNER TO admin;

--
-- Name: tour_requests_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: admin
--

ALTER SEQUENCE public.tour_requests_id_seq OWNED BY public.tour_requests.id;


--
-- Name: treats; Type: TABLE; Schema: public; Owner: admin
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


ALTER TABLE public.treats OWNER TO admin;

--
-- Name: treats_id_seq; Type: SEQUENCE; Schema: public; Owner: admin
--

CREATE SEQUENCE public.treats_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.treats_id_seq OWNER TO admin;

--
-- Name: treats_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: admin
--

ALTER SEQUENCE public.treats_id_seq OWNED BY public.treats.id;


--
-- Name: user_consolidation_map; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.user_consolidation_map (
    consolidated_user_id character varying(255) NOT NULL,
    primary_device_id character varying(255) NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    last_merged_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.user_consolidation_map OWNER TO admin;

--
-- Name: user_subscription_credentials; Type: TABLE; Schema: public; Owner: admin
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


ALTER TABLE public.user_subscription_credentials OWNER TO admin;

--
-- Name: user_subscription_credentials_id_seq; Type: SEQUENCE; Schema: public; Owner: admin
--

CREATE SEQUENCE public.user_subscription_credentials_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.user_subscription_credentials_id_seq OWNER TO admin;

--
-- Name: user_subscription_credentials_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: admin
--

ALTER SEQUENCE public.user_subscription_credentials_id_seq OWNED BY public.user_subscription_credentials.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.users (
    secret_id character varying(255) NOT NULL,
    app_version character varying(50) DEFAULT 'unknown'::character varying,
    is_deleted boolean DEFAULT false,
    app_uninstalled boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone
);


ALTER TABLE public.users OWNER TO admin;

--
-- Name: article_requests id; Type: DEFAULT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.article_requests ALTER COLUMN id SET DEFAULT nextval('public.article_requests_id_seq'::regclass);


--
-- Name: audio_tours id; Type: DEFAULT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.audio_tours ALTER COLUMN id SET DEFAULT nextval('public.audio_tours_id_seq'::regclass);


--
-- Name: coordinates id; Type: DEFAULT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.coordinates ALTER COLUMN id SET DEFAULT nextval('public.coordinates_id_seq'::regclass);


--
-- Name: device_consolidation_history id; Type: DEFAULT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.device_consolidation_history ALTER COLUMN id SET DEFAULT nextval('public.device_consolidation_history_id_seq'::regclass);


--
-- Name: map_requests id; Type: DEFAULT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.map_requests ALTER COLUMN id SET DEFAULT nextval('public.map_requests_id_seq'::regclass);


--
-- Name: news_audios id; Type: DEFAULT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.news_audios ALTER COLUMN id SET DEFAULT nextval('public.news_audios_id_seq'::regclass);


--
-- Name: newsletters id; Type: DEFAULT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.newsletters ALTER COLUMN id SET DEFAULT nextval('public.newsletters_id_seq'::regclass);


--
-- Name: newsletters_article_link id; Type: DEFAULT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.newsletters_article_link ALTER COLUMN id SET DEFAULT nextval('public.newsletters_article_link_id_seq'::regclass);


--
-- Name: test_content_storage id; Type: DEFAULT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.test_content_storage ALTER COLUMN id SET DEFAULT nextval('public.test_content_storage_id_seq'::regclass);


--
-- Name: tour_requests id; Type: DEFAULT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.tour_requests ALTER COLUMN id SET DEFAULT nextval('public.tour_requests_id_seq'::regclass);


--
-- Name: treats id; Type: DEFAULT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.treats ALTER COLUMN id SET DEFAULT nextval('public.treats_id_seq'::regclass);


--
-- Name: user_subscription_credentials id; Type: DEFAULT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.user_subscription_credentials ALTER COLUMN id SET DEFAULT nextval('public.user_subscription_credentials_id_seq'::regclass);


--
-- Name: article_requests article_requests_article_id_key; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.article_requests
    ADD CONSTRAINT article_requests_article_id_key UNIQUE (article_id);


--
-- Name: article_requests article_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.article_requests
    ADD CONSTRAINT article_requests_pkey PRIMARY KEY (id);


--
-- Name: article_requests article_requests_url_key; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.article_requests
    ADD CONSTRAINT article_requests_url_key UNIQUE (url);


--
-- Name: audio_tours audio_tours_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.audio_tours
    ADD CONSTRAINT audio_tours_pkey PRIMARY KEY (id);


--
-- Name: coordinates coordinates_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.coordinates
    ADD CONSTRAINT coordinates_pkey PRIMARY KEY (id);


--
-- Name: device_consolidation_history device_consolidation_history_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.device_consolidation_history
    ADD CONSTRAINT device_consolidation_history_pkey PRIMARY KEY (id);


--
-- Name: device_encryption_keys device_encryption_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.device_encryption_keys
    ADD CONSTRAINT device_encryption_keys_pkey PRIMARY KEY (device_id);


--
-- Name: dh_aes_keys dh_aes_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.dh_aes_keys
    ADD CONSTRAINT dh_aes_keys_pkey PRIMARY KEY (device_id);


--
-- Name: dh_server_keys dh_server_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.dh_server_keys
    ADD CONSTRAINT dh_server_keys_pkey PRIMARY KEY (device_id);


--
-- Name: job_status job_status_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.job_status
    ADD CONSTRAINT job_status_pkey PRIMARY KEY (job_id);


--
-- Name: map_requests map_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.map_requests
    ADD CONSTRAINT map_requests_pkey PRIMARY KEY (id);


--
-- Name: news_audios news_audios_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.news_audios
    ADD CONSTRAINT news_audios_pkey PRIMARY KEY (id);


--
-- Name: newsletter_server_keys newsletter_server_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.newsletter_server_keys
    ADD CONSTRAINT newsletter_server_keys_pkey PRIMARY KEY (newsletter_id);


--
-- Name: newsletters_article_link newsletters_article_link_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.newsletters_article_link
    ADD CONSTRAINT newsletters_article_link_pkey PRIMARY KEY (id);


--
-- Name: newsletters newsletters_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.newsletters
    ADD CONSTRAINT newsletters_pkey PRIMARY KEY (id);


--
-- Name: supported_languages supported_languages_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.supported_languages
    ADD CONSTRAINT supported_languages_pkey PRIMARY KEY (language_code);


--
-- Name: test_content_storage test_content_storage_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.test_content_storage
    ADD CONSTRAINT test_content_storage_pkey PRIMARY KEY (id);


--
-- Name: tour_requests tour_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.tour_requests
    ADD CONSTRAINT tour_requests_pkey PRIMARY KEY (id);


--
-- Name: treats treats_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.treats
    ADD CONSTRAINT treats_pkey PRIMARY KEY (id);


--
-- Name: user_subscription_credentials unique_device_domain; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.user_subscription_credentials
    ADD CONSTRAINT unique_device_domain UNIQUE (device_id, domain);


--
-- Name: user_consolidation_map user_consolidation_map_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.user_consolidation_map
    ADD CONSTRAINT user_consolidation_map_pkey PRIMARY KEY (consolidated_user_id);


--
-- Name: user_subscription_credentials user_subscription_credentials_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.user_subscription_credentials
    ADD CONSTRAINT user_subscription_credentials_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (secret_id);


--
-- Name: idx_article_requests_article_id; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_article_requests_article_id ON public.article_requests USING btree (article_id);


--
-- Name: idx_article_requests_language; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_article_requests_language ON public.article_requests USING btree (language);


--
-- Name: idx_article_requests_secret_id; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_article_requests_secret_id ON public.article_requests USING btree (secret_id);


--
-- Name: idx_article_subscription; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_article_subscription ON public.article_requests USING btree (subscription_required, subscription_domain);


--
-- Name: idx_audio_tours_language; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_audio_tours_language ON public.audio_tours USING btree (language);


--
-- Name: idx_audio_tours_location; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_audio_tours_location ON public.audio_tours USING btree (lat, lng);


--
-- Name: idx_audio_tours_original; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_audio_tours_original ON public.audio_tours USING btree (original_tour_id);


--
-- Name: idx_audio_tours_request_string; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_audio_tours_request_string ON public.audio_tours USING btree (request_string);


--
-- Name: idx_audio_tours_tour_name; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_audio_tours_tour_name ON public.audio_tours USING btree (tour_name);


--
-- Name: idx_consolidated_user; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_consolidated_user ON public.user_subscription_credentials USING btree (consolidated_user_id);


--
-- Name: idx_consolidation_history_user; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_consolidation_history_user ON public.device_consolidation_history USING btree (consolidated_user_id);


--
-- Name: idx_credentials_device_domain; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_credentials_device_domain ON public.user_subscription_credentials USING btree (device_id, domain);


--
-- Name: idx_job_status_created; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_job_status_created ON public.job_status USING btree (created_at);


--
-- Name: idx_job_status_service_created; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_job_status_service_created ON public.job_status USING btree (service_name, created_at DESC);


--
-- Name: idx_news_audios_article_id; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_news_audios_article_id ON public.news_audios USING btree (article_id);


--
-- Name: idx_news_audios_language; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_news_audios_language ON public.news_audios USING btree (language);


--
-- Name: idx_newsletters_created_at; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_newsletters_created_at ON public.newsletters USING btree (created_at);


--
-- Name: idx_newsletters_url; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_newsletters_url ON public.newsletters USING btree (url);


--
-- Name: idx_tour_requests_language; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_tour_requests_language ON public.tour_requests USING btree (language);


--
-- Name: idx_treats_location; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX idx_treats_location ON public.treats USING btree (lat, lng);


--
-- Name: uq_audio_tours_original_name; Type: INDEX; Schema: public; Owner: admin
--

CREATE UNIQUE INDEX uq_audio_tours_original_name ON public.audio_tours USING btree (lower((tour_name)::text)) WHERE (original_tour_id IS NULL);


--
-- Name: article_requests article_requests_original_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.article_requests
    ADD CONSTRAINT article_requests_original_article_id_fkey FOREIGN KEY (original_article_id) REFERENCES public.article_requests(article_id);


--
-- Name: article_requests article_requests_secret_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.article_requests
    ADD CONSTRAINT article_requests_secret_id_fkey FOREIGN KEY (secret_id) REFERENCES public.users(secret_id);


--
-- Name: audio_tours audio_tours_derived_from_tour_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.audio_tours
    ADD CONSTRAINT audio_tours_derived_from_tour_id_fkey FOREIGN KEY (derived_from_tour_id) REFERENCES public.audio_tours(id);


--
-- Name: audio_tours audio_tours_original_tour_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.audio_tours
    ADD CONSTRAINT audio_tours_original_tour_id_fkey FOREIGN KEY (original_tour_id) REFERENCES public.audio_tours(id);


--
-- Name: coordinates coordinates_secret_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.coordinates
    ADD CONSTRAINT coordinates_secret_id_fkey FOREIGN KEY (secret_id) REFERENCES public.users(secret_id);


--
-- Name: map_requests map_requests_secret_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.map_requests
    ADD CONSTRAINT map_requests_secret_id_fkey FOREIGN KEY (secret_id) REFERENCES public.users(secret_id);


--
-- Name: news_audios news_audios_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.news_audios
    ADD CONSTRAINT news_audios_article_id_fkey FOREIGN KEY (article_id) REFERENCES public.article_requests(article_id);


--
-- Name: tour_requests tour_requests_secret_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.tour_requests
    ADD CONSTRAINT tour_requests_secret_id_fkey FOREIGN KEY (secret_id) REFERENCES public.users(secret_id);


--
-- Name: user_subscription_credentials user_subscription_credentials_article_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.user_subscription_credentials
    ADD CONSTRAINT user_subscription_credentials_article_id_fkey FOREIGN KEY (article_id) REFERENCES public.article_requests(article_id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

