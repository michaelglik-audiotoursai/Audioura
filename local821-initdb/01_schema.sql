--
-- PostgreSQL database dump
--

\restrict SANd35HksrowddKfViiQj4npco9fLHK6SrdqLNeHyO8QCiGeLxSVVBV4doAbdGi

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
-- Name: admin_actions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.admin_actions (
    id integer NOT NULL,
    action character varying(32) NOT NULL,
    actor character varying(255),
    target_user_id character varying(255),
    target_community_id integer,
    reason text,
    report_id integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    amount_usd numeric(10,2),
    transaction_id character varying(255),
    store character varying(20),
    target_tour_id integer,
    CONSTRAINT chk_admin_actions_action CHECK (((action)::text = ANY ((ARRAY['bar'::character varying, 'unbar'::character varying, 'ban'::character varying, 'unban'::character varying, 'disable_community'::character varying, 'enable_community'::character varying, 'refund_google'::character varying, 'apple_refund_support'::character varying, 'grant_tour'::character varying, 'extend_pass'::character varying, 'grant_pass'::character varying, 'add_plan_units'::character varying, 'extend_plan'::character varying])::text[])))
);


--
-- Name: TABLE admin_actions; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.admin_actions IS 'LOCAL-728/D691: append-only audit ledger of every administrator moderation action (bar/unbar a member from a community, ban/unban from the service, disable/enable a community). Records who, when, target, reason and the answered report id. Never updated or deleted.';


--
-- Name: COLUMN admin_actions.amount_usd; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.admin_actions.amount_usd IS 'LOCAL-729: the USD amount of a MONEY refund (refund_google full/partial). NULL for a make-good-in-kind or moderation row.';


--
-- Name: COLUMN admin_actions.transaction_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.admin_actions.transaction_id IS 'LOCAL-729: the store order/transaction id a reimbursement answers (Google orderId / Apple Order ID), for the paper trail. NULL for a plain grant.';


--
-- Name: COLUMN admin_actions.store; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.admin_actions.store IS 'LOCAL-729: the store of the reimbursed purchase (apple|google|stub) when a reimbursement targets one. NULL otherwise.';


--
-- Name: COLUMN admin_actions.target_tour_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.admin_actions.target_tour_id IS 'LOCAL-729: the tour a grant_tour re-granted (an audio_tours.id). NULL for non-tour actions.';


--
-- Name: admin_actions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.admin_actions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: admin_actions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.admin_actions_id_seq OWNED BY public.admin_actions.id;


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
-- Name: artist_life_research_cache; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.artist_life_research_cache (
    cache_key text NOT NULL,
    artist text NOT NULL,
    local_code text NOT NULL,
    result_json text NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: audio_tour_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audio_tour_versions (
    id integer NOT NULL,
    tour_id integer NOT NULL,
    version_no integer NOT NULL,
    tour_content text,
    zip_filename character varying(512),
    stops_count integer,
    lat double precision,
    lng double precision,
    replaced_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    replaced_by_job character varying(128)
);


--
-- Name: TABLE audio_tour_versions; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.audio_tour_versions IS 'LOCAL-606/D622: append-only archive of superseded audio_tours original-row content (text, zip, stops, lat/lng) kept before a regenerated tour replaces it. Reversible via restore_tour_version.py. Never deleted.';


--
-- Name: audio_tour_versions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.audio_tour_versions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: audio_tour_versions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.audio_tour_versions_id_seq OWNED BY public.audio_tour_versions.id;


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
    is_test boolean DEFAULT false,
    track character varying(16) DEFAULT 'beta'::character varying NOT NULL,
    tour_kind character varying(16) DEFAULT 'full'::character varying NOT NULL,
    translation_stale boolean DEFAULT false NOT NULL,
    price_tier smallint,
    is_paid boolean GENERATED ALWAYS AS ((price_tier IS NOT NULL)) STORED,
    source_version integer,
    editor_score numeric(3,1),
    editor_score_detail jsonb,
    editor_scored_at timestamp with time zone,
    content_rating character varying(16),
    content_rating_reason text,
    review_status character varying(16),
    content_rated_at timestamp with time zone,
    rescore_requested_version integer,
    community_id integer,
    community_visibility character varying(16),
    short_title text,
    creator_user_id text,
    source_kind character varying(32),
    rights_accepted_by character varying(128),
    rights_accepted_at timestamp without time zone,
    CONSTRAINT audio_tours_community_visibility_check CHECK (((community_visibility IS NULL) OR ((community_visibility)::text = ANY ((ARRAY['members'::character varying, 'public'::character varying])::text[])))),
    CONSTRAINT audio_tours_content_rating_check CHECK (((content_rating IS NULL) OR ((content_rating)::text = ANY ((ARRAY['general'::character varying, 'mature'::character varying, 'not_allowed'::character varying])::text[])))),
    CONSTRAINT audio_tours_editor_score_check CHECK (((editor_score IS NULL) OR ((editor_score >= 5.0) AND (editor_score <= 8.0)))),
    CONSTRAINT audio_tours_review_status_check CHECK (((review_status IS NULL) OR ((review_status)::text = ANY ((ARRAY['pending'::character varying, 'approved'::character varying, 'rejected'::character varying])::text[])))),
    CONSTRAINT chk_audio_tours_price_tier CHECK (((price_tier IS NULL) OR ((price_tier >= 1) AND (price_tier <= 41))))
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
-- Name: COLUMN audio_tours.translation_stale; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.audio_tours.translation_stale IS 'LOCAL-606/D622: TRUE when this translation''s original was replaced; the next translation request regenerates it. The row is not deleted.';


--
-- Name: COLUMN audio_tours.price_tier; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.audio_tours.price_tier IS 'LOCAL-677/D624: the price TIER a curator set on their own tour (1..5, a row in price_tiers). NULL = FREE (the default). The dollar amount lives in price_tiers, never hard-coded in code or the app (D652: Michael sets them).';


--
-- Name: COLUMN audio_tours.is_paid; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.audio_tours.is_paid IS 'LOCAL-677: GENERATED from price_tier (price_tier IS NOT NULL). Kept in sync by the database — a priced tour is paid, a NULL-tier tour is free. Read by map_delivery._is_paid_select and tour_reviews_service.is_paid_tour.';


--
-- Name: COLUMN audio_tours.community_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.audio_tours.community_id IS 'LOCAL-701/D663 §3: the community this tour was generated FOR (NULL = an ordinary public tour). The organiser was charged from their plan allowance.';


--
-- Name: COLUMN audio_tours.community_visibility; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.audio_tours.community_visibility IS 'LOCAL-701/D663 §3: members (default — community page only, members download) or public (on the map with the community badge; download needs a membership).';


--
-- Name: COLUMN audio_tours.source_kind; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.audio_tours.source_kind IS 'LOCAL-754B/D658 addendum 2: NULL = generated/ordinary tour; ''organiser_audio'' = built from the organiser''s hosted audio (package has remote_audio.json, no MP3; translation not offered, D708).';


--
-- Name: COLUMN audio_tours.rights_accepted_by; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.audio_tours.rights_accepted_by IS 'LOCAL-754B/D754: the organiser who accepted "I have the right to publish this audio to my members" for an organiser-audio tour (required per tour).';


--
-- Name: COLUMN audio_tours.rights_accepted_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.audio_tours.rights_accepted_at IS 'LOCAL-754B/D754: when the organiser accepted the per-tour publish rights.';


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
-- Name: author_edit_scores; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.author_edit_scores (
    id integer NOT NULL,
    secret_id character varying(255) NOT NULL,
    tour_id integer,
    score real NOT NULL,
    delta jsonb,
    recorded_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: author_edit_scores_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.author_edit_scores_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: author_edit_scores_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.author_edit_scores_id_seq OWNED BY public.author_edit_scores.id;


--
-- Name: communities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.communities (
    id integer NOT NULL,
    owner_user_id character varying(255) NOT NULL,
    name character varying(200) NOT NULL,
    description text,
    organiser_name character varying(200),
    organiser_photo_url text,
    organiser_bio text,
    organiser_contact character varying(300),
    rules_text text,
    waiver_text text,
    has_waiver boolean DEFAULT false NOT NULL,
    is_paid boolean DEFAULT false NOT NULL,
    visibility character varying(16) DEFAULT 'private'::character varying NOT NULL,
    latitude double precision,
    longitude double precision,
    join_code character varying(16),
    feed_url text,
    disabled boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    status character varying(16) DEFAULT 'active'::character varying NOT NULL,
    stepped_down_at timestamp without time zone,
    archived_at timestamp without time zone,
    launch_deadline timestamp with time zone,
    launched_at timestamp with time zone,
    archived_reason character varying(32),
    launch_reminded_48h_at timestamp with time zone,
    launch_reminded_12h_at timestamp with time zone,
    low_members_since timestamp with time zone,
    last_low_warning_at timestamp with time zone,
    zero_members_since timestamp with time zone,
    release_cadence character varying(10) DEFAULT 'week'::character varying NOT NULL,
    CONSTRAINT chk_communities_archived_reason CHECK (((archived_reason IS NULL) OR ((archived_reason)::text = ANY ((ARRAY['launch_window_missed'::character varying, 'handover_expired'::character varying, 'no_members'::character varying])::text[])))),
    CONSTRAINT chk_communities_listed_has_location CHECK ((((visibility)::text <> 'listed'::text) OR ((latitude IS NOT NULL) AND (longitude IS NOT NULL)))),
    CONSTRAINT chk_communities_release_cadence CHECK (((release_cadence)::text = ANY ((ARRAY['day'::character varying, 'week'::character varying, 'month'::character varying, 'year'::character varying])::text[]))),
    CONSTRAINT chk_communities_status CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'handover'::character varying, 'archived'::character varying])::text[]))),
    CONSTRAINT chk_communities_waiver_private CHECK ((NOT (has_waiver AND ((visibility)::text = 'listed'::text)))),
    CONSTRAINT communities_visibility_check CHECK (((visibility)::text = ANY ((ARRAY['listed'::character varying, 'private'::character varying])::text[])))
);


--
-- Name: TABLE communities; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.communities IS 'LOCAL-690/D657-D658: one owner-published community of owner-hosted audio. Audioura stores metadata only. disabled = per-community off-switch. A waiver community is always Private; a Listed community needs a location.';


--
-- Name: COLUMN communities.status; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.communities.status IS 'LOCAL-702/D663 §1: active (normal), handover (owner stepped down — closed to new members, looking for a new organiser), or archived (no new organiser within 30 days; members keep downloads, nothing new).';


--
-- Name: COLUMN communities.stepped_down_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.communities.stepped_down_at IS 'LOCAL-702/D663 §1: when the owner stepped down. The 30-day archive clock is measured from here; cleared when a new organiser accepts (community reopens).';


--
-- Name: COLUMN communities.archived_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.communities.archived_at IS 'LOCAL-702/D663 §1: when the daily job archived the community (NULL until then).';


--
-- Name: COLUMN communities.launch_deadline; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.communities.launch_deadline IS 'LOCAL-703/D664: created_at + COMMUNITY_LAUNCH_HOURS (168 h). By this time the community needs 2 qualifying members (excluding the owner) or the launch-window job archives it. Pre-rule communities got NOW()+window at migration.';


--
-- Name: COLUMN communities.launched_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.communities.launched_at IS 'LOCAL-703/D664: when the community won its first 2 qualifying members (excluding the owner). Stamped once, never reverted. NULL = not yet launched; a launched community is never archived by the launch-window job.';


--
-- Name: COLUMN communities.archived_reason; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.communities.archived_reason IS 'LOCAL-703/704 / D664/D666: why a community was archived — launch_window_missed (missed the first-two-members bar), handover_expired (LOCAL-702 30-day hand-over path), or no_members (7 days at 0 active members after launch). NULL when not archived.';


--
-- Name: COLUMN communities.launch_reminded_48h_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.communities.launch_reminded_48h_at IS 'LOCAL-703/D664: when the organiser 48 h-left launch reminder was sent (NULL until then). Guards against double-sending.';


--
-- Name: COLUMN communities.launch_reminded_12h_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.communities.launch_reminded_12h_at IS 'LOCAL-703/D664: when the organiser 12 h-left launch reminder was sent (NULL until then). Guards against double-sending.';


--
-- Name: COLUMN communities.low_members_since; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.communities.low_members_since IS 'LOCAL-704/D666: when the active member count (unexpired paid passes, owner excluded) last dropped below 2. NULL while >= 2. Drives the day-0-then-weekly low-members warnings.';


--
-- Name: COLUMN communities.last_low_warning_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.communities.last_low_warning_at IS 'LOCAL-704/D666: when the last low-members warning was sent. NULL = none yet. Guards the weekly cadence so a warning fires at most once per 7 days.';


--
-- Name: COLUMN communities.zero_members_since; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.communities.zero_members_since IS 'LOCAL-704/D666: when the active member count last hit 0. NULL while >= 1. At 7 consecutive days the launch-window job archives the community with reason no_members.';


--
-- Name: COLUMN communities.release_cadence; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.communities.release_cadence IS 'LOCAL-738 (C2c): how often members get new tours — day | week | month | year. Chosen on the create form (required, default week), returned by the community page payload and shown as "New tours: weekly".';


--
-- Name: communities_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.communities_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: communities_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.communities_id_seq OWNED BY public.communities.id;


--
-- Name: community_blocks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.community_blocks (
    id integer NOT NULL,
    community_id integer NOT NULL,
    blocker_user_id character varying(255) NOT NULL,
    blocked_user_id character varying(255) NOT NULL,
    kind character varying(16) NOT NULL,
    reason text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT chk_community_blocks_kind CHECK (((kind)::text = ANY ((ARRAY['member_block'::character varying, 'organiser_bar'::character varying, 'admin_bar'::character varying])::text[]))),
    CONSTRAINT chk_community_blocks_not_self CHECK (((blocker_user_id)::text <> (blocked_user_id)::text))
);


--
-- Name: TABLE community_blocks; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.community_blocks IS 'LOCAL-726 / Apple Guideline 1.2: community block function. kind=member_block: a member hides a blocked user''s communities/tours from their OWN view. kind=organiser_bar: an organiser removes and bars a member from their community (no new content, cannot rejoin by code; downloaded audio stays, D658). Unblock = DELETE the row (member from Settings, organiser from the member list).';


--
-- Name: community_blocks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.community_blocks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: community_blocks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.community_blocks_id_seq OWNED BY public.community_blocks.id;


--
-- Name: community_episodes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.community_episodes (
    id integer NOT NULL,
    community_id integer NOT NULL,
    "position" integer NOT NULL,
    title character varying(500) NOT NULL,
    audio_url text NOT NULL,
    guid character varying(500),
    source character varying(8) DEFAULT 'link'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    size_bytes bigint,
    duration character varying(32),
    episode_date character varying(64),
    CONSTRAINT community_episodes_source_check CHECK (((source)::text = ANY ((ARRAY['link'::character varying, 'feed'::character varying])::text[])))
);


--
-- Name: TABLE community_episodes; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.community_episodes IS 'LOCAL-690/D657-D658: episode METADATA only (title, order, owner-hosted URL). A feed item or a typed link becomes an episode; Audioura never stores the MP3. NO content check on owner audio (D657 addendum).';


--
-- Name: COLUMN community_episodes.size_bytes; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.community_episodes.size_bytes IS 'LOCAL-759 C: enclosure byte length from the feed (NULL when absent). The organiser-audio builder sums ticked episodes into "N episodes · X MB".';


--
-- Name: COLUMN community_episodes.duration; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.community_episodes.duration IS 'LOCAL-759 C: episode duration as the feed gave it (raw text, NULL absent).';


--
-- Name: COLUMN community_episodes.episode_date; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.community_episodes.episode_date IS 'LOCAL-759 C: episode publish date as the feed gave it (raw text, NULL absent).';


--
-- Name: community_episodes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.community_episodes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: community_episodes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.community_episodes_id_seq OWNED BY public.community_episodes.id;


--
-- Name: community_memberships; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.community_memberships (
    id integer NOT NULL,
    user_id character varying(255) NOT NULL,
    community_id integer NOT NULL,
    expires_at timestamp without time zone,
    transaction_id character varying(255),
    store character varying(20),
    product_id character varying(64),
    price_usd numeric(10,2),
    reminded_before_at timestamp without time zone,
    reminded_expiry_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: TABLE community_memberships; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.community_memberships IS 'LOCAL-690/D657-D658: one row per (member, community). expires_at enforced by the server for NEW content only (downloaded audio stays playable). One row per pair — buying again extends the expiry. NULL expiry = free community.';


--
-- Name: community_memberships_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.community_memberships_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: community_memberships_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.community_memberships_id_seq OWNED BY public.community_memberships.id;


--
-- Name: community_organiser_offers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.community_organiser_offers (
    id integer NOT NULL,
    community_id integer NOT NULL,
    member_user_id character varying(255) NOT NULL,
    status character varying(16) DEFAULT 'offered'::character varying NOT NULL,
    picked_at timestamp without time zone,
    accepted_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT community_organiser_offers_status_check CHECK (((status)::text = ANY ((ARRAY['offered'::character varying, 'picked'::character varying, 'accepted'::character varying, 'withdrawn'::character varying])::text[])))
);


--
-- Name: TABLE community_organiser_offers; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.community_organiser_offers IS 'LOCAL-702/D663 §1: hand-over offers. A member volunteers (offered); the stepping-down owner picks one (picked); the picked member accepts (accepted) → ownership transfers and the community reopens. One offer per (community, member); at most one picked offer per community.';


--
-- Name: community_organiser_offers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.community_organiser_offers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: community_organiser_offers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.community_organiser_offers_id_seq OWNED BY public.community_organiser_offers.id;


--
-- Name: community_pass_products; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.community_pass_products (
    product_id character varying(64) NOT NULL,
    price_usd numeric(10,2) NOT NULL,
    label character varying(48) NOT NULL,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: TABLE community_pass_products; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.community_pass_products IS 'LOCAL-690/D658 (LEAD review): the fixed catalogue of NON-RENEWING pass store products — ONE product per PRICE (the 34 ladder prices, LOCAL-686). Apple''s non-renewing product carries no length, so one product serves every community and every length; the LENGTH lives on the community''s option (community_passes).';


--
-- Name: community_passes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.community_passes (
    id integer NOT NULL,
    community_id integer NOT NULL,
    product_id character varying(64) NOT NULL,
    length character varying(8) NOT NULL,
    duration_days integer NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT community_passes_duration_days_check CHECK ((duration_days > 0)),
    CONSTRAINT community_passes_length_check CHECK (((length)::text = ANY ((ARRAY['day'::character varying, 'week'::character varying, 'month'::character varying, 'year'::character varying])::text[])))
);


--
-- Name: TABLE community_passes; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.community_passes IS 'LOCAL-690/D658 (LEAD review): which pass OPTIONS a community offers — a (price product, length) pair with its duration_days. The LENGTH lives here, not the catalogue. unique (community, product, length). Free community: none.';


--
-- Name: community_passes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.community_passes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: community_passes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.community_passes_id_seq OWNED BY public.community_passes.id;


--
-- Name: community_reports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.community_reports (
    id integer NOT NULL,
    community_id integer NOT NULL,
    reporter_user_id character varying(255),
    reason text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    detail text,
    status character varying(16) DEFAULT 'open'::character varying NOT NULL,
    CONSTRAINT chk_community_reports_status CHECK (((status)::text = ANY ((ARRAY['open'::character varying, 'reviewed'::character varying, 'dismissed'::character varying])::text[])))
);


--
-- Name: TABLE community_reports; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.community_reports IS 'LOCAL-728/D691: a report on a community, organiser or community tour goes to AUDIOURA (not the owner). reason = the chosen reason code, detail = the reporter''s optional free text, status = open|reviewed|dismissed (triaged with moderation.py). Supersedes the 029 "routes to the OWNER" note.';


--
-- Name: community_reports_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.community_reports_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: community_reports_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.community_reports_id_seq OWNED BY public.community_reports.id;


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
    description character varying(256),
    ceiling_breach character varying(32)
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
-- Name: custom_tours; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.custom_tours (
    id integer NOT NULL,
    custom_tour_id character varying(255) NOT NULL,
    original_tour_id integer,
    user_id character varying(255),
    tour_name character varying(255) NOT NULL,
    request_string text NOT NULL,
    audio_tour bytea,
    lat double precision,
    lng double precision,
    number_requested integer DEFAULT 0,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: custom_tours_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.custom_tours_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: custom_tours_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.custom_tours_id_seq OWNED BY public.custom_tours.id;


--
-- Name: device_consolidation_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_consolidation_history (
    id integer NOT NULL,
    consolidated_user_id character varying(255) NOT NULL,
    merged_device_id character varying(255) NOT NULL,
    domain character varying(255) NOT NULL,
    merged_at timestamp without time zone DEFAULT now(),
    unlinked_at timestamp with time zone
);


--
-- Name: COLUMN device_consolidation_history.unlinked_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.device_consolidation_history.unlinked_at IS 'LOCAL-695: when this device was UNLINKED from the profile by a later restore (the old phone moved away). NULL = still linked. The map_delivery abuse guard refuses re-download grants to a device whose latest history row is unlinked; tours already on that phone keep playing (D654).';


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
-- Name: device_entitlement; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_entitlement (
    user_id character varying(255) NOT NULL,
    level character varying(20) DEFAULT 'l1'::character varying NOT NULL,
    pack_started_at timestamp without time zone,
    anniversary_at timestamp without time zone,
    fresh_used integer DEFAULT 0 NOT NULL,
    edits_used integer DEFAULT 0 NOT NULL,
    ops_used integer DEFAULT 0 NOT NULL,
    last_activity_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
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
-- Name: document_acceptance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_acceptance (
    id integer NOT NULL,
    user_id character varying(255) NOT NULL,
    document character varying(64) NOT NULL,
    version character varying(64) NOT NULL,
    accepted_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: document_acceptance_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.document_acceptance_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: document_acceptance_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.document_acceptance_id_seq OWNED BY public.document_acceptance.id;


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
-- Name: failure_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.failure_events (
    id bigint NOT NULL,
    ts timestamp with time zone DEFAULT now() NOT NULL,
    user_id text,
    app_version text,
    platform text,
    track text,
    surface text,
    error_code text,
    message text,
    request_text text,
    tour_id text,
    job_id text,
    exception_type text,
    frames text,
    http_status integer,
    service text,
    signature character(16) NOT NULL,
    triage text DEFAULT 'unknown'::text NOT NULL,
    triage_source text DEFAULT 'auto'::text NOT NULL,
    resolved_by text,
    CONSTRAINT chk_failure_events_triage CHECK ((triage = ANY (ARRAY['our_bug'::text, 'ux'::text, 'external'::text, 'absence'::text, 'unknown'::text]))),
    CONSTRAINT chk_failure_events_triage_source CHECK ((triage_source = ANY (ARRAY['auto'::text, 'lead'::text])))
);


--
-- Name: TABLE failure_events; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.failure_events IS 'LOCAL-785/D723: one row per recorded failure (server job failure/refusal/clean-fail/5xx via failure_log.record, and app failures via POST /client-failure). signature groups like failures (sha1 of service+error_code+exception_type+normalised message, [:16]); triage = whose fault (our_bug|ux|external|absence|unknown), seeded auto and overridden by LEAD with failure_report.py --mark; resolved_by = the fixing ticket. Read by failure_report.py. 90-day retention is out of scope.';


--
-- Name: failure_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.failure_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: failure_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.failure_events_id_seq OWNED BY public.failure_events.id;


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
-- Name: l2_offers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.l2_offers (
    id integer NOT NULL,
    user_id character varying(255) NOT NULL,
    code character varying(32) NOT NULL,
    offered_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    claimed_at timestamp without time zone,
    status character varying(16) DEFAULT 'offered'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: l2_offers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.l2_offers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: l2_offers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.l2_offers_id_seq OWNED BY public.l2_offers.id;


--
-- Name: l2_queue; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.l2_queue (
    user_id character varying(255) NOT NULL,
    joined_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    status character varying(16) DEFAULT 'waiting'::character varying NOT NULL,
    offer_misses integer DEFAULT 0 NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    email character varying(320)
);


--
-- Name: l2_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.l2_settings (
    id boolean DEFAULT true NOT NULL,
    auto_grant_threshold integer NOT NULL,
    offer_expiry_hours integer NOT NULL,
    max_offer_misses integer DEFAULT 2 NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    offer_ttl_minutes integer DEFAULT 10 NOT NULL,
    CONSTRAINT l2_settings_singleton CHECK ((id = true))
);


--
-- Name: level_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.level_codes (
    code_hash character(64) NOT NULL,
    level character varying(20) NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    revoked_at timestamp without time zone,
    uses integer DEFAULT 0 NOT NULL
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
-- Name: paid_api_calls; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.paid_api_calls (
    id bigint NOT NULL,
    ts timestamp with time zone DEFAULT now(),
    kind text,
    status integer,
    service text,
    caller text,
    url text,
    model text,
    usd numeric(12,6),
    detail jsonb,
    host text,
    role text
);


--
-- Name: paid_api_calls_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.paid_api_calls_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: paid_api_calls_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.paid_api_calls_id_seq OWNED BY public.paid_api_calls.id;


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
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    tours_per_month integer,
    fresh_per_pack integer,
    edits_per_pack integer,
    ops_per_pack integer,
    max_stops integer,
    max_new_stops_per_edit integer,
    by_reference_only boolean DEFAULT false,
    referrals_allowed integer DEFAULT 0,
    referral_period character varying(10),
    seat_cap integer,
    can_sell boolean DEFAULT false,
    price_usd numeric(10,2) DEFAULT 0,
    inactivity_days integer,
    display_name character varying(64),
    hidden boolean DEFAULT false NOT NULL,
    article_char_limit integer
);


--
-- Name: price_tiers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.price_tiers (
    tier smallint NOT NULL,
    product_id character varying(64) NOT NULL,
    price_usd numeric(10,2) NOT NULL,
    label character varying(32) NOT NULL,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    in_picker boolean DEFAULT true NOT NULL,
    CONSTRAINT price_tiers_tier_check CHECK (((tier >= 1) AND (tier <= 41)))
);


--
-- Name: COLUMN price_tiers.in_picker; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.price_tiers.in_picker IS 'LOCAL-686: TRUE if the guide''s price picker offers this tier. The 34 ladder tiers (8..41) are TRUE; the seven legacy .99 tiers (1..7) are FALSE — still ACTIVE so tours already priced with them keep their price, but off the picker.';


--
-- Name: profile_restores; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.profile_restores (
    id integer NOT NULL,
    consolidated_user_id character varying(255) NOT NULL,
    new_device_id character varying(255) NOT NULL,
    unlinked_device_id character varying(255),
    grants_issued integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE profile_restores; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.profile_restores IS 'LOCAL-695: append-only log of each successful profile restore (recovery code accepted). The abuse guard refuses a restore when a profile has more than 2 rows here in the last 30 days (→ "Contact support", D654).';


--
-- Name: profile_restores_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.profile_restores_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: profile_restores_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.profile_restores_id_seq OWNED BY public.profile_restores.id;


--
-- Name: purchases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.purchases (
    id integer NOT NULL,
    transaction_id character varying(255) NOT NULL,
    store character varying(20) NOT NULL,
    product character varying(50) NOT NULL,
    user_id character varying(255) NOT NULL,
    amount numeric(10,2),
    verified_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    raw_status text,
    refund_supported boolean DEFAULT false NOT NULL
);


--
-- Name: COLUMN purchases.refund_supported; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.purchases.refund_supported IS 'LOCAL-729/D692: TRUE when the admin ran apple-refund-message for this purchase — Audioura supports the buyer''s Apple refund. The consumption answer (App Store Server Notifications, wdvrdaz2zf) reads this. Grants/refunds nothing by itself; default FALSE for every existing row.';


--
-- Name: purchases_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.purchases_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: purchases_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.purchases_id_seq OWNED BY public.purchases.id;


--
-- Name: recovery_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.recovery_codes (
    consolidated_user_id character varying(255) NOT NULL,
    code_hash bytea NOT NULL,
    code_salt bytea NOT NULL,
    hash_algo character varying(32) DEFAULT 'pbkdf2_sha256'::character varying NOT NULL,
    hash_iterations integer DEFAULT 200000 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    rotated_at timestamp with time zone,
    code_lookup character varying(64)
);


--
-- Name: TABLE recovery_codes; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.recovery_codes IS 'LOCAL-695: one anonymous recovery code per profile (consolidated_user_id), stored ONLY as a salted PBKDF2-HMAC-SHA256 hash — never plaintext. Offered once after the first purchase; entering it on a new phone restores the Listen page. Re-generating rotates the hash in place.';


--
-- Name: COLUMN recovery_codes.code_hash; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.recovery_codes.code_hash IS 'PBKDF2-HMAC-SHA256 of the recovery code with code_salt and hash_iterations. The database alone never reveals the code.';


--
-- Name: COLUMN recovery_codes.code_lookup; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.recovery_codes.code_lookup IS 'LOCAL-695B: hex HMAC-SHA256(RECOVERY_CODE_PEPPER, normalized_code) — a fast deterministic SELECTOR that makes restore an O(1) single-row lookup instead of scanning every PBKDF2 hash. The pepper lives in env (not the DB); the PBKDF2 code_hash + code_salt remain the verifier. NULL on legacy rows until their next generate/rotate.';


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
-- Name: restore_attempts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.restore_attempts (
    id integer NOT NULL,
    device_id character varying(255) NOT NULL,
    outcome character varying(32) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE restore_attempts; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.restore_attempts IS 'LOCAL-695: append-only log of every restore ATTEMPT (success or failure) keyed by requesting device, for the per-device rate limit (default 5 attempts / hour / device). A wrong code counts here even though it never touches a profile.';


--
-- Name: restore_attempts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.restore_attempts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: restore_attempts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.restore_attempts_id_seq OWNED BY public.restore_attempts.id;


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
-- Name: service_bans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_bans (
    id integer NOT NULL,
    user_id character varying(255) NOT NULL,
    reason text,
    report_id integer,
    banned_by character varying(255),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    lifted_at timestamp with time zone,
    lifted_by character varying(255)
);


--
-- Name: TABLE service_bans; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.service_bans IS 'LOCAL-728/D691/D658: a user banned from the service by the administrator — no purchases, generation, community joins or creation. Downloaded audio stays on the device (D658: a ban blocks NEW access only). lifted_at IS NULL = active; a lifted ban keeps its row as history (never deleted).';


--
-- Name: service_bans_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.service_bans_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: service_bans_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.service_bans_id_seq OWNED BY public.service_bans.id;


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
    share_count integer DEFAULT 0,
    audio_tour_id integer
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
    verified boolean DEFAULT true,
    score_historic integer,
    score_detail integer,
    score_social integer,
    valuation_index integer
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
-- Name: stop_pool; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.stop_pool (
    pool_key text NOT NULL,
    title_norm text NOT NULL,
    venue_identity text NOT NULL,
    tour_type text NOT NULL,
    pool_version integer NOT NULL,
    title text NOT NULL,
    artist text DEFAULT ''::text,
    year text DEFAULT ''::text,
    narration text NOT NULL,
    raw_block text,
    address text DEFAULT ''::text,
    coordinates text DEFAULT ''::text,
    type_specialty text DEFAULT ''::text,
    specific_examples text DEFAULT ''::text,
    operational_details text DEFAULT ''::text,
    sources_json text,
    story_elements_json text,
    generated_at timestamp with time zone DEFAULT now() NOT NULL,
    hit_count integer DEFAULT 0,
    order_seq integer DEFAULT 0,
    research_cost_usd numeric(12,6) DEFAULT 0,
    stop_record_json text,
    news_generated_at timestamp with time zone
);


--
-- Name: stop_pool_sources; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.stop_pool_sources (
    pool_key text NOT NULL,
    title_norm text NOT NULL,
    audio_tour_id integer NOT NULL,
    recorded_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE stop_pool_sources; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.stop_pool_sources IS 'LOCAL-766/D713: provenance for the stop pool — one row per (pooled stop, source audio_tour). A pooled stop is skipped at delivery for a non-creator when ANY source tour is community (community_id NOT NULL) or priced (price_tier > 0). A pooled stop with no row here is unproven and stays shareable. Additive; never DELETEs.';


--
-- Name: stop_pool_zz_backup_20261006; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.stop_pool_zz_backup_20261006 (
    pool_key text,
    title_norm text,
    venue_identity text,
    tour_type text,
    pool_version integer,
    title text,
    artist text,
    year text,
    narration text,
    raw_block text,
    address text,
    coordinates text,
    type_specialty text,
    specific_examples text,
    operational_details text,
    sources_json text,
    story_elements_json text,
    generated_at timestamp with time zone,
    hit_count integer,
    order_seq integer
);


--
-- Name: stop_pool_zz_backup_20261024_danvers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.stop_pool_zz_backup_20261024_danvers (
    pool_key text,
    title_norm text,
    venue_identity text,
    tour_type text,
    pool_version integer,
    title text,
    artist text,
    year text,
    narration text,
    raw_block text,
    address text,
    coordinates text,
    type_specialty text,
    specific_examples text,
    operational_details text,
    sources_json text,
    story_elements_json text,
    generated_at timestamp with time zone,
    hit_count integer,
    order_seq integer,
    research_cost_usd numeric(12,6),
    stop_record_json text,
    news_generated_at timestamp with time zone
);


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
-- Name: support_ids; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.support_ids (
    support_id character varying(16) NOT NULL,
    user_id character varying(255) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE support_ids; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.support_ids IS 'LOCAL-729/D692: the public Support ID (e.g. AU-7K3Q), a short alias of a device shown in About with a Copy button and resolvable by the admin reimbursement tools. NEVER the secret device id. One alias per device (user_id UNIQUE), unique across devices (support_id PK). Additive, collision-safe generation (support_id.py).';


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
-- Name: sync_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sync_items (
    client_uuid character varying(64) NOT NULL,
    user_id character varying(255) NOT NULL,
    item_type character varying(32) NOT NULL,
    processed_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
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
-- Name: thin_verify_cache; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.thin_verify_cache (
    cache_key text NOT NULL,
    venue text NOT NULL,
    city text NOT NULL,
    result_json text NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL
);


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
    hit_count integer DEFAULT 0,
    has_news boolean DEFAULT false
);


--
-- Name: tour_downloads; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tour_downloads (
    id integer NOT NULL,
    user_id character varying(255) NOT NULL,
    tour_id integer NOT NULL,
    was_free boolean NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: tour_downloads_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tour_downloads_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tour_downloads_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tour_downloads_id_seq OWNED BY public.tour_downloads.id;


--
-- Name: tour_edit_blobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tour_edit_blobs (
    new_tour_id text NOT NULL,
    source_tour_id text,
    blob_uri text NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: tour_listens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tour_listens (
    id integer NOT NULL,
    tour_id integer NOT NULL,
    user_id character varying(255) NOT NULL,
    stop_index integer NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT tour_listens_stop_index_check CHECK ((stop_index >= 0))
);


--
-- Name: tour_listens_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tour_listens_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tour_listens_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tour_listens_id_seq OWNED BY public.tour_listens.id;


--
-- Name: tour_ratings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tour_ratings (
    id integer NOT NULL,
    tour_id integer NOT NULL,
    user_id character varying(255) NOT NULL,
    rating smallint NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT tour_ratings_rating_check CHECK (((rating >= 1) AND (rating <= 10)))
);


--
-- Name: tour_ratings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tour_ratings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tour_ratings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tour_ratings_id_seq OWNED BY public.tour_ratings.id;


--
-- Name: tour_reports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tour_reports (
    id integer NOT NULL,
    tour_id integer,
    tour_name text,
    reason text,
    reporter_user_id text,
    status character varying(16) DEFAULT 'open'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT tour_reports_status_check CHECK (((status)::text = ANY ((ARRAY['open'::character varying, 'reviewed'::character varying, 'dismissed'::character varying])::text[])))
);


--
-- Name: tour_reports_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tour_reports_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tour_reports_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tour_reports_id_seq OWNED BY public.tour_reports.id;


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
-- Name: tour_review_sync; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tour_review_sync (
    id integer NOT NULL,
    tour_id integer NOT NULL,
    user_id character varying(255) NOT NULL,
    review text NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: tour_review_sync_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tour_review_sync_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tour_review_sync_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tour_review_sync_id_seq OWNED BY public.tour_review_sync.id;


--
-- Name: tour_scores; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tour_scores (
    id integer NOT NULL,
    tour_id integer,
    tour_name text,
    scored_at timestamp with time zone DEFAULT now() NOT NULL,
    code_sha character varying(12),
    n_requested integer NOT NULL,
    n_delivered integer NOT NULL,
    base_score real NOT NULL,
    structural real NOT NULL,
    correlation real NOT NULL,
    venue_identity real NOT NULL,
    total real NOT NULL,
    per_stop jsonb NOT NULL,
    scorer_version character varying(64) NOT NULL,
    scoring_ms real,
    is_rescore boolean DEFAULT false NOT NULL,
    previous_score_id integer,
    delta jsonb
);


--
-- Name: tour_scores_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tour_scores_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tour_scores_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tour_scores_id_seq OWNED BY public.tour_scores.id;


--
-- Name: tour_unlocks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tour_unlocks (
    id integer NOT NULL,
    user_id character varying(255) NOT NULL,
    tour_id integer NOT NULL,
    transaction_id character varying(255),
    store character varying(20),
    price_usd numeric(10,2),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    consumed_at timestamp with time zone,
    consumed_by_download_id character varying(255),
    restored_at timestamp with time zone
);


--
-- Name: TABLE tour_unlocks; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.tour_unlocks IS 'LOCAL-677/D624: one row per (buyer, tour) unlocked by a verified purchase. UNIQUE(user_id,tour_id) → a replayed transaction never unlocks twice. tour_id is an ORIGINAL audio_tours.id (a translation shares its source tour''s unlock).';


--
-- Name: COLUMN tour_unlocks.consumed_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.tour_unlocks.consumed_at IS 'LOCAL-693/D660: when this purchase was spent by a SUCCESSFUL download. NULL = unconsumed (an active entitlement to exactly one download). A failed or cut-off download never sets this; the listener retries for free until a download completes.';


--
-- Name: COLUMN tour_unlocks.consumed_by_download_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.tour_unlocks.consumed_by_download_id IS 'LOCAL-693/D660: the download event id that consumed this unlock (audit). NULL while unconsumed.';


--
-- Name: COLUMN tour_unlocks.restored_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.tour_unlocks.restored_at IS 'LOCAL-693B/D660: when a consumed unlock was restored once by a download-failed report (within 24h of consumption). NULL = never restored. A row with restored_at set cannot be restored again (download-failed → 409), so a failed-download loop cannot grant unlimited downloads.';


--
-- Name: tour_unlocks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tour_unlocks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tour_unlocks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tour_unlocks_id_seq OWNED BY public.tour_unlocks.id;


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
-- Name: user_quality_index; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_quality_index (
    secret_id character varying(255) NOT NULL,
    mean_score real NOT NULL,
    tour_count integer DEFAULT 0 NOT NULL,
    last_scored_at timestamp with time zone DEFAULT now() NOT NULL
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
-- Name: venue_preflight_cache; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.venue_preflight_cache (
    cache_key text NOT NULL,
    venue text NOT NULL,
    city text NOT NULL,
    result_json text NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL
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
-- Name: admin_actions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_actions ALTER COLUMN id SET DEFAULT nextval('public.admin_actions_id_seq'::regclass);


--
-- Name: article_requests id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.article_requests ALTER COLUMN id SET DEFAULT nextval('public.article_requests_id_seq'::regclass);


--
-- Name: audio_tour_versions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audio_tour_versions ALTER COLUMN id SET DEFAULT nextval('public.audio_tour_versions_id_seq'::regclass);


--
-- Name: audio_tours id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audio_tours ALTER COLUMN id SET DEFAULT nextval('public.audio_tours_id_seq'::regclass);


--
-- Name: author_edit_scores id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.author_edit_scores ALTER COLUMN id SET DEFAULT nextval('public.author_edit_scores_id_seq'::regclass);


--
-- Name: communities id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.communities ALTER COLUMN id SET DEFAULT nextval('public.communities_id_seq'::regclass);


--
-- Name: community_blocks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_blocks ALTER COLUMN id SET DEFAULT nextval('public.community_blocks_id_seq'::regclass);


--
-- Name: community_episodes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_episodes ALTER COLUMN id SET DEFAULT nextval('public.community_episodes_id_seq'::regclass);


--
-- Name: community_memberships id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_memberships ALTER COLUMN id SET DEFAULT nextval('public.community_memberships_id_seq'::regclass);


--
-- Name: community_organiser_offers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_organiser_offers ALTER COLUMN id SET DEFAULT nextval('public.community_organiser_offers_id_seq'::regclass);


--
-- Name: community_passes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_passes ALTER COLUMN id SET DEFAULT nextval('public.community_passes_id_seq'::regclass);


--
-- Name: community_reports id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_reports ALTER COLUMN id SET DEFAULT nextval('public.community_reports_id_seq'::regclass);


--
-- Name: coordinates id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coordinates ALTER COLUMN id SET DEFAULT nextval('public.coordinates_id_seq'::regclass);


--
-- Name: custom_tours id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.custom_tours ALTER COLUMN id SET DEFAULT nextval('public.custom_tours_id_seq'::regclass);


--
-- Name: device_consolidation_history id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_consolidation_history ALTER COLUMN id SET DEFAULT nextval('public.device_consolidation_history_id_seq'::regclass);


--
-- Name: document_acceptance id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_acceptance ALTER COLUMN id SET DEFAULT nextval('public.document_acceptance_id_seq'::regclass);


--
-- Name: failure_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.failure_events ALTER COLUMN id SET DEFAULT nextval('public.failure_events_id_seq'::regclass);


--
-- Name: l2_offers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.l2_offers ALTER COLUMN id SET DEFAULT nextval('public.l2_offers_id_seq'::regclass);


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
-- Name: paid_api_calls id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.paid_api_calls ALTER COLUMN id SET DEFAULT nextval('public.paid_api_calls_id_seq'::regclass);


--
-- Name: profile_restores id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.profile_restores ALTER COLUMN id SET DEFAULT nextval('public.profile_restores_id_seq'::regclass);


--
-- Name: purchases id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchases ALTER COLUMN id SET DEFAULT nextval('public.purchases_id_seq'::regclass);


--
-- Name: referral_redemptions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_redemptions ALTER COLUMN id SET DEFAULT nextval('public.referral_redemptions_id_seq'::regclass);


--
-- Name: restore_attempts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.restore_attempts ALTER COLUMN id SET DEFAULT nextval('public.restore_attempts_id_seq'::regclass);


--
-- Name: service_bans id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_bans ALTER COLUMN id SET DEFAULT nextval('public.service_bans_id_seq'::regclass);


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
-- Name: tour_downloads id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_downloads ALTER COLUMN id SET DEFAULT nextval('public.tour_downloads_id_seq'::regclass);


--
-- Name: tour_listens id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_listens ALTER COLUMN id SET DEFAULT nextval('public.tour_listens_id_seq'::regclass);


--
-- Name: tour_ratings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_ratings ALTER COLUMN id SET DEFAULT nextval('public.tour_ratings_id_seq'::regclass);


--
-- Name: tour_reports id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_reports ALTER COLUMN id SET DEFAULT nextval('public.tour_reports_id_seq'::regclass);


--
-- Name: tour_requests id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_requests ALTER COLUMN id SET DEFAULT nextval('public.tour_requests_id_seq'::regclass);


--
-- Name: tour_review_sync id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_review_sync ALTER COLUMN id SET DEFAULT nextval('public.tour_review_sync_id_seq'::regclass);


--
-- Name: tour_scores id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_scores ALTER COLUMN id SET DEFAULT nextval('public.tour_scores_id_seq'::regclass);


--
-- Name: tour_unlocks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_unlocks ALTER COLUMN id SET DEFAULT nextval('public.tour_unlocks_id_seq'::regclass);


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
-- Name: admin_actions admin_actions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_actions
    ADD CONSTRAINT admin_actions_pkey PRIMARY KEY (id);


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
-- Name: artist_life_research_cache artist_life_research_cache_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.artist_life_research_cache
    ADD CONSTRAINT artist_life_research_cache_pkey PRIMARY KEY (cache_key);


--
-- Name: audio_tour_versions audio_tour_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audio_tour_versions
    ADD CONSTRAINT audio_tour_versions_pkey PRIMARY KEY (id);


--
-- Name: audio_tours audio_tours_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audio_tours
    ADD CONSTRAINT audio_tours_pkey PRIMARY KEY (id);


--
-- Name: author_edit_scores author_edit_scores_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.author_edit_scores
    ADD CONSTRAINT author_edit_scores_pkey PRIMARY KEY (id);


--
-- Name: communities communities_join_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.communities
    ADD CONSTRAINT communities_join_code_key UNIQUE (join_code);


--
-- Name: communities communities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.communities
    ADD CONSTRAINT communities_pkey PRIMARY KEY (id);


--
-- Name: community_blocks community_blocks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_blocks
    ADD CONSTRAINT community_blocks_pkey PRIMARY KEY (id);


--
-- Name: community_episodes community_episodes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_episodes
    ADD CONSTRAINT community_episodes_pkey PRIMARY KEY (id);


--
-- Name: community_memberships community_memberships_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_memberships
    ADD CONSTRAINT community_memberships_pkey PRIMARY KEY (id);


--
-- Name: community_organiser_offers community_organiser_offers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_organiser_offers
    ADD CONSTRAINT community_organiser_offers_pkey PRIMARY KEY (id);


--
-- Name: community_pass_products community_pass_products_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_pass_products
    ADD CONSTRAINT community_pass_products_pkey PRIMARY KEY (product_id);


--
-- Name: community_passes community_passes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_passes
    ADD CONSTRAINT community_passes_pkey PRIMARY KEY (id);


--
-- Name: community_reports community_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_reports
    ADD CONSTRAINT community_reports_pkey PRIMARY KEY (id);


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
-- Name: custom_tours custom_tours_custom_tour_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.custom_tours
    ADD CONSTRAINT custom_tours_custom_tour_id_key UNIQUE (custom_tour_id);


--
-- Name: custom_tours custom_tours_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.custom_tours
    ADD CONSTRAINT custom_tours_pkey PRIMARY KEY (id);


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
-- Name: device_entitlement device_entitlement_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_entitlement
    ADD CONSTRAINT device_entitlement_pkey PRIMARY KEY (user_id);


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
-- Name: document_acceptance document_acceptance_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_acceptance
    ADD CONSTRAINT document_acceptance_pkey PRIMARY KEY (id);


--
-- Name: domain_tier_cache domain_tier_cache_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_tier_cache
    ADD CONSTRAINT domain_tier_cache_pkey PRIMARY KEY (domain);


--
-- Name: failure_events failure_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.failure_events
    ADD CONSTRAINT failure_events_pkey PRIMARY KEY (id);


--
-- Name: job_status job_status_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_status
    ADD CONSTRAINT job_status_pkey PRIMARY KEY (job_id);


--
-- Name: l2_offers l2_offers_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.l2_offers
    ADD CONSTRAINT l2_offers_code_key UNIQUE (code);


--
-- Name: l2_offers l2_offers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.l2_offers
    ADD CONSTRAINT l2_offers_pkey PRIMARY KEY (id);


--
-- Name: l2_queue l2_queue_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.l2_queue
    ADD CONSTRAINT l2_queue_pkey PRIMARY KEY (user_id);


--
-- Name: l2_settings l2_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.l2_settings
    ADD CONSTRAINT l2_settings_pkey PRIMARY KEY (id);


--
-- Name: level_codes level_codes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.level_codes
    ADD CONSTRAINT level_codes_pkey PRIMARY KEY (code_hash);


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
-- Name: paid_api_calls paid_api_calls_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.paid_api_calls
    ADD CONSTRAINT paid_api_calls_pkey PRIMARY KEY (id);


--
-- Name: plans plans_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plans
    ADD CONSTRAINT plans_pkey PRIMARY KEY (plan_id);


--
-- Name: price_tiers price_tiers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.price_tiers
    ADD CONSTRAINT price_tiers_pkey PRIMARY KEY (tier);


--
-- Name: profile_restores profile_restores_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.profile_restores
    ADD CONSTRAINT profile_restores_pkey PRIMARY KEY (id);


--
-- Name: purchases purchases_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchases
    ADD CONSTRAINT purchases_pkey PRIMARY KEY (id);


--
-- Name: purchases purchases_transaction_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchases
    ADD CONSTRAINT purchases_transaction_id_key UNIQUE (transaction_id);


--
-- Name: recovery_codes recovery_codes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recovery_codes
    ADD CONSTRAINT recovery_codes_pkey PRIMARY KEY (consolidated_user_id);


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
-- Name: restore_attempts restore_attempts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.restore_attempts
    ADD CONSTRAINT restore_attempts_pkey PRIMARY KEY (id);


--
-- Name: revenuecat_webhook_events revenuecat_webhook_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.revenuecat_webhook_events
    ADD CONSTRAINT revenuecat_webhook_events_pkey PRIMARY KEY (event_id);


--
-- Name: service_bans service_bans_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_bans
    ADD CONSTRAINT service_bans_pkey PRIMARY KEY (id);


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
-- Name: stop_pool stop_pool_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stop_pool
    ADD CONSTRAINT stop_pool_pkey PRIMARY KEY (pool_key, title_norm);


--
-- Name: stop_pool_sources stop_pool_sources_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stop_pool_sources
    ADD CONSTRAINT stop_pool_sources_pkey PRIMARY KEY (pool_key, title_norm, audio_tour_id);


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
-- Name: support_ids support_ids_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_ids
    ADD CONSTRAINT support_ids_pkey PRIMARY KEY (support_id);


--
-- Name: support_ids support_ids_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_ids
    ADD CONSTRAINT support_ids_user_id_key UNIQUE (user_id);


--
-- Name: supported_languages supported_languages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supported_languages
    ADD CONSTRAINT supported_languages_pkey PRIMARY KEY (language_code);


--
-- Name: sync_items sync_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sync_items
    ADD CONSTRAINT sync_items_pkey PRIMARY KEY (client_uuid);


--
-- Name: test_content_storage test_content_storage_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.test_content_storage
    ADD CONSTRAINT test_content_storage_pkey PRIMARY KEY (id);


--
-- Name: thin_verify_cache thin_verify_cache_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.thin_verify_cache
    ADD CONSTRAINT thin_verify_cache_pkey PRIMARY KEY (cache_key);


--
-- Name: tour_cache tour_cache_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_cache
    ADD CONSTRAINT tour_cache_pkey PRIMARY KEY (cache_key);


--
-- Name: tour_downloads tour_downloads_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_downloads
    ADD CONSTRAINT tour_downloads_pkey PRIMARY KEY (id);


--
-- Name: tour_edit_blobs tour_edit_blobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_edit_blobs
    ADD CONSTRAINT tour_edit_blobs_pkey PRIMARY KEY (new_tour_id);


--
-- Name: tour_listens tour_listens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_listens
    ADD CONSTRAINT tour_listens_pkey PRIMARY KEY (id);


--
-- Name: tour_ratings tour_ratings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_ratings
    ADD CONSTRAINT tour_ratings_pkey PRIMARY KEY (id);


--
-- Name: tour_reports tour_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_reports
    ADD CONSTRAINT tour_reports_pkey PRIMARY KEY (id);


--
-- Name: tour_requests tour_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_requests
    ADD CONSTRAINT tour_requests_pkey PRIMARY KEY (id);


--
-- Name: tour_review_sync tour_review_sync_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_review_sync
    ADD CONSTRAINT tour_review_sync_pkey PRIMARY KEY (id);


--
-- Name: tour_scores tour_scores_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_scores
    ADD CONSTRAINT tour_scores_pkey PRIMARY KEY (id);


--
-- Name: tour_unlocks tour_unlocks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_unlocks
    ADD CONSTRAINT tour_unlocks_pkey PRIMARY KEY (id);


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
-- Name: audio_tour_versions uq_audio_tour_versions_tour_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audio_tour_versions
    ADD CONSTRAINT uq_audio_tour_versions_tour_version UNIQUE (tour_id, version_no);


--
-- Name: community_blocks uq_community_blocks; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_blocks
    ADD CONSTRAINT uq_community_blocks UNIQUE (community_id, blocker_user_id, blocked_user_id, kind);


--
-- Name: community_episodes uq_community_episodes_pos; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_episodes
    ADD CONSTRAINT uq_community_episodes_pos UNIQUE (community_id, "position");


--
-- Name: community_memberships uq_community_memberships; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_memberships
    ADD CONSTRAINT uq_community_memberships UNIQUE (user_id, community_id);


--
-- Name: community_passes uq_community_passes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_passes
    ADD CONSTRAINT uq_community_passes UNIQUE (community_id, product_id, length);


--
-- Name: document_acceptance uq_document_acceptance; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_acceptance
    ADD CONSTRAINT uq_document_acceptance UNIQUE (user_id, document, version);


--
-- Name: community_organiser_offers uq_organiser_offers; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_organiser_offers
    ADD CONSTRAINT uq_organiser_offers UNIQUE (community_id, member_user_id);


--
-- Name: referral_redemptions uq_referral_redemptions_code_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_redemptions
    ADD CONSTRAINT uq_referral_redemptions_code_user UNIQUE (referral_code, new_user_id);


--
-- Name: tour_downloads uq_tour_downloads_user_tour; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_downloads
    ADD CONSTRAINT uq_tour_downloads_user_tour UNIQUE (user_id, tour_id);


--
-- Name: tour_listens uq_tour_listens_tour_user_stop; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_listens
    ADD CONSTRAINT uq_tour_listens_tour_user_stop UNIQUE (tour_id, user_id, stop_index);


--
-- Name: tour_ratings uq_tour_ratings_tour_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_ratings
    ADD CONSTRAINT uq_tour_ratings_tour_user UNIQUE (tour_id, user_id);


--
-- Name: tour_review_sync uq_tour_review_sync_tour_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_review_sync
    ADD CONSTRAINT uq_tour_review_sync_tour_user UNIQUE (tour_id, user_id);


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
-- Name: user_quality_index user_quality_index_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_quality_index
    ADD CONSTRAINT user_quality_index_pkey PRIMARY KEY (secret_id);


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
-- Name: venue_preflight_cache venue_preflight_cache_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.venue_preflight_cache
    ADD CONSTRAINT venue_preflight_cache_pkey PRIMARY KEY (cache_key);


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
-- Name: idx_admin_actions_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_admin_actions_created ON public.admin_actions USING btree (created_at DESC);


--
-- Name: idx_admin_actions_target_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_admin_actions_target_user ON public.admin_actions USING btree (target_user_id);


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
-- Name: idx_audio_tours_community; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audio_tours_community ON public.audio_tours USING btree (community_id) WHERE (community_id IS NOT NULL);


--
-- Name: idx_audio_tours_community_public; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audio_tours_community_public ON public.audio_tours USING btree (community_id) WHERE ((community_id IS NOT NULL) AND ((community_visibility)::text = 'public'::text));


--
-- Name: idx_audio_tours_content_rating; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audio_tours_content_rating ON public.audio_tours USING btree (content_rating, review_status) WHERE (content_rating IS NOT NULL);


--
-- Name: idx_audio_tours_language; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audio_tours_language ON public.audio_tours USING btree (language);


--
-- Name: idx_audio_tours_location; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audio_tours_location ON public.audio_tours USING btree (lat, lng);


--
-- Name: idx_audio_tours_name_creator_track; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audio_tours_name_creator_track ON public.audio_tours USING btree (lower((tour_name)::text), creator_user_id, track) WHERE (original_tour_id IS NULL);


--
-- Name: idx_audio_tours_original; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audio_tours_original ON public.audio_tours USING btree (original_tour_id);


--
-- Name: idx_audio_tours_price_tier; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audio_tours_price_tier ON public.audio_tours USING btree (price_tier);


--
-- Name: idx_audio_tours_request_string; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audio_tours_request_string ON public.audio_tours USING btree (request_string);


--
-- Name: idx_audio_tours_source_kind; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audio_tours_source_kind ON public.audio_tours USING btree (source_kind) WHERE (source_kind IS NOT NULL);


--
-- Name: idx_audio_tours_tour_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audio_tours_tour_name ON public.audio_tours USING btree (tour_name);


--
-- Name: idx_audio_tours_zip_filename; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audio_tours_zip_filename ON public.audio_tours USING btree (zip_filename) WHERE (zip_filename IS NOT NULL);


--
-- Name: idx_author_edit_scores_secret_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_author_edit_scores_secret_id ON public.author_edit_scores USING btree (secret_id);


--
-- Name: idx_communities_handover; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_communities_handover ON public.communities USING btree (stepped_down_at) WHERE ((status)::text = 'handover'::text);


--
-- Name: idx_communities_join_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_communities_join_code ON public.communities USING btree (join_code);


--
-- Name: idx_communities_launch_window; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_communities_launch_window ON public.communities USING btree (launch_deadline) WHERE (((status)::text = 'active'::text) AND (launched_at IS NULL));


--
-- Name: idx_communities_listed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_communities_listed ON public.communities USING btree (visibility) WHERE (((visibility)::text = 'listed'::text) AND (disabled = false));


--
-- Name: idx_communities_low_members; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_communities_low_members ON public.communities USING btree (low_members_since) WHERE (low_members_since IS NOT NULL);


--
-- Name: idx_communities_owner; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_communities_owner ON public.communities USING btree (owner_user_id);


--
-- Name: idx_community_blocks_blocked; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_community_blocks_blocked ON public.community_blocks USING btree (community_id, blocked_user_id, kind);


--
-- Name: idx_community_blocks_blocker; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_community_blocks_blocker ON public.community_blocks USING btree (blocker_user_id, kind);


--
-- Name: idx_community_passes_community; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_community_passes_community ON public.community_passes USING btree (community_id);


--
-- Name: idx_community_reports_status_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_community_reports_status_created ON public.community_reports USING btree (status, created_at DESC);


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
-- Name: idx_device_entitlement_activity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_device_entitlement_activity ON public.device_entitlement USING btree (last_activity_at);


--
-- Name: idx_device_entitlement_anniversary; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_device_entitlement_anniversary ON public.device_entitlement USING btree (anniversary_at);


--
-- Name: idx_device_entitlement_level; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_device_entitlement_level ON public.device_entitlement USING btree (level);


--
-- Name: idx_document_acceptance_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_document_acceptance_user ON public.document_acceptance USING btree (user_id, document);


--
-- Name: idx_domain_tier_expires; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domain_tier_expires ON public.domain_tier_cache USING btree (expires_at);


--
-- Name: idx_episodes_community; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_episodes_community ON public.community_episodes USING btree (community_id);


--
-- Name: idx_failure_events_signature_ts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_failure_events_signature_ts ON public.failure_events USING btree (signature, ts DESC);


--
-- Name: idx_failure_events_ts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_failure_events_ts ON public.failure_events USING btree (ts DESC);


--
-- Name: idx_job_status_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_status_created ON public.job_status USING btree (created_at);


--
-- Name: idx_job_status_service_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_status_service_created ON public.job_status USING btree (service_name, created_at DESC);


--
-- Name: idx_l2_offers_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_l2_offers_status ON public.l2_offers USING btree (status);


--
-- Name: idx_l2_offers_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_l2_offers_user ON public.l2_offers USING btree (user_id);


--
-- Name: idx_l2_queue_status_joined; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_l2_queue_status_joined ON public.l2_queue USING btree (status, joined_at);


--
-- Name: idx_level_codes_level; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_level_codes_level ON public.level_codes USING btree (level);


--
-- Name: idx_low_balance_pending; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_low_balance_pending ON public.low_balance_events USING btree (user_id, acknowledged) WHERE (acknowledged = false);


--
-- Name: idx_memberships_community; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memberships_community ON public.community_memberships USING btree (community_id);


--
-- Name: idx_memberships_expires; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memberships_expires ON public.community_memberships USING btree (expires_at) WHERE (expires_at IS NOT NULL);


--
-- Name: idx_memberships_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memberships_user ON public.community_memberships USING btree (user_id);


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
-- Name: idx_organiser_offers_community; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_organiser_offers_community ON public.community_organiser_offers USING btree (community_id);


--
-- Name: idx_paid_api_calls_listener; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_paid_api_calls_listener ON public.paid_api_calls USING btree (ts) WHERE ((status = 200) AND (role = 'listener'::text));


--
-- Name: idx_profile_restores_profile_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_profile_restores_profile_time ON public.profile_restores USING btree (consolidated_user_id, created_at);


--
-- Name: idx_purchases_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_purchases_user ON public.purchases USING btree (user_id);


--
-- Name: idx_reports_community; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_reports_community ON public.community_reports USING btree (community_id);


--
-- Name: idx_restore_attempts_device_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_restore_attempts_device_time ON public.restore_attempts USING btree (device_id, created_at);


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
-- Name: idx_stop_pool_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stop_pool_key ON public.stop_pool USING btree (pool_key);


--
-- Name: idx_stop_pool_sources_stop; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stop_pool_sources_stop ON public.stop_pool_sources USING btree (pool_key, title_norm);


--
-- Name: idx_stop_pool_sources_tour; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stop_pool_sources_tour ON public.stop_pool_sources USING btree (audio_tour_id);


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
-- Name: idx_tour_downloads_user_tour; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tour_downloads_user_tour ON public.tour_downloads USING btree (user_id, tour_id);


--
-- Name: idx_tour_ratings_tour_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tour_ratings_tour_id ON public.tour_ratings USING btree (tour_id);


--
-- Name: idx_tour_ratings_tour_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tour_ratings_tour_user ON public.tour_ratings USING btree (tour_id, user_id);


--
-- Name: idx_tour_reports_status_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tour_reports_status_created ON public.tour_reports USING btree (status, created_at DESC);


--
-- Name: idx_tour_reports_tour_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tour_reports_tour_id ON public.tour_reports USING btree (tour_id);


--
-- Name: idx_tour_requests_language; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tour_requests_language ON public.tour_requests USING btree (language);


--
-- Name: idx_tour_scores_tour_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tour_scores_tour_id ON public.tour_scores USING btree (tour_id);


--
-- Name: idx_tour_unlocks_tour; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tour_unlocks_tour ON public.tour_unlocks USING btree (tour_id);


--
-- Name: idx_tour_unlocks_unconsumed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tour_unlocks_unconsumed ON public.tour_unlocks USING btree (user_id, tour_id, created_at) WHERE (consumed_at IS NULL);


--
-- Name: idx_tour_unlocks_user_tour; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tour_unlocks_user_tour ON public.tour_unlocks USING btree (user_id, tour_id);


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
-- Name: uq_episodes_community_guid; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_episodes_community_guid ON public.community_episodes USING btree (community_id, guid) WHERE (guid IS NOT NULL);


--
-- Name: uq_organiser_offers_one_picked; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_organiser_offers_one_picked ON public.community_organiser_offers USING btree (community_id) WHERE ((status)::text = 'picked'::text);


--
-- Name: uq_recovery_codes_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_recovery_codes_lookup ON public.recovery_codes USING btree (code_lookup) WHERE (code_lookup IS NOT NULL);


--
-- Name: uq_service_bans_active; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_service_bans_active ON public.service_bans USING btree (user_id) WHERE (lifted_at IS NULL);


--
-- Name: uq_tour_unlocks_active; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_tour_unlocks_active ON public.tour_unlocks USING btree (user_id, tour_id) WHERE (consumed_at IS NULL);


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
-- Name: community_blocks community_blocks_community_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_blocks
    ADD CONSTRAINT community_blocks_community_id_fkey FOREIGN KEY (community_id) REFERENCES public.communities(id) ON DELETE CASCADE;


--
-- Name: community_episodes community_episodes_community_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_episodes
    ADD CONSTRAINT community_episodes_community_id_fkey FOREIGN KEY (community_id) REFERENCES public.communities(id) ON DELETE CASCADE;


--
-- Name: community_memberships community_memberships_community_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_memberships
    ADD CONSTRAINT community_memberships_community_id_fkey FOREIGN KEY (community_id) REFERENCES public.communities(id) ON DELETE CASCADE;


--
-- Name: community_organiser_offers community_organiser_offers_community_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_organiser_offers
    ADD CONSTRAINT community_organiser_offers_community_id_fkey FOREIGN KEY (community_id) REFERENCES public.communities(id) ON DELETE CASCADE;


--
-- Name: community_passes community_passes_community_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_passes
    ADD CONSTRAINT community_passes_community_id_fkey FOREIGN KEY (community_id) REFERENCES public.communities(id) ON DELETE CASCADE;


--
-- Name: community_passes community_passes_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_passes
    ADD CONSTRAINT community_passes_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.community_pass_products(product_id);


--
-- Name: community_reports community_reports_community_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.community_reports
    ADD CONSTRAINT community_reports_community_id_fkey FOREIGN KEY (community_id) REFERENCES public.communities(id) ON DELETE CASCADE;


--
-- Name: coordinates coordinates_secret_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coordinates
    ADD CONSTRAINT coordinates_secret_id_fkey FOREIGN KEY (secret_id) REFERENCES public.users(secret_id);


--
-- Name: custom_tours custom_tours_original_tour_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.custom_tours
    ADD CONSTRAINT custom_tours_original_tour_id_fkey FOREIGN KEY (original_tour_id) REFERENCES public.audio_tours(id);


--
-- Name: device_entitlement device_entitlement_level_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_entitlement
    ADD CONSTRAINT device_entitlement_level_fkey FOREIGN KEY (level) REFERENCES public.plans(plan_id);


--
-- Name: audio_tours fk_audio_tours_community; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audio_tours
    ADD CONSTRAINT fk_audio_tours_community FOREIGN KEY (community_id) REFERENCES public.communities(id) ON DELETE SET NULL;


--
-- Name: stop_pool_sources fk_stop_pool_sources_tour; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stop_pool_sources
    ADD CONSTRAINT fk_stop_pool_sources_tour FOREIGN KEY (audio_tour_id) REFERENCES public.audio_tours(id) ON DELETE CASCADE;


--
-- Name: level_codes level_codes_level_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.level_codes
    ADD CONSTRAINT level_codes_level_fkey FOREIGN KEY (level) REFERENCES public.plans(plan_id);


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
-- Name: tour_reports tour_reports_tour_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tour_reports
    ADD CONSTRAINT tour_reports_tour_id_fkey FOREIGN KEY (tour_id) REFERENCES public.audio_tours(id) ON DELETE SET NULL;


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

\unrestrict SANd35HksrowddKfViiQj4npco9fLHK6SrdqLNeHyO8QCiGeLxSVVBV4doAbdGi

