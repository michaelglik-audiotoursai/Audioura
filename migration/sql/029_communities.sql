-- 029_communities.sql  (LOCAL-690, D657 / D658 + addenda)
--
-- Communities — phase 1. An owner publishes a community of owner-HOSTED audio
-- (MP3 links or ONE RSS feed; Audioura stores only episode METADATA, never the
-- files — D657 addendum / D658 addendum 2). Members join with an invite/share
-- code and buy NON-RENEWING passes (one price-ladder product serves every
-- community; our server stores the community + an expiry — D657/D658). Nothing
-- renews automatically; at expiry the member is reminded and may buy again.
-- Downloaded audio STAYS playable after expiry — expiry only blocks NEW content
-- (new codes / new episodes), checked by the server (D658 addendum §2).
--
-- WHAT THIS ADDS, PURELY ADDITIVELY (no DROP, no DELETE, no column retype):
--
--   1. communities              — one row per community (owner, name, desc,
--                                  organiser card, rules/waiver, free/paid,
--                                  Listed/Private, location, the invite code,
--                                  the per-community `disabled` off-switch, and
--                                  one optional feed_url).
--   2. community_pass_products   — the FIXED catalogue of non-renewing pass
--                                  store products: one product per PRICE (the
--                                  34-step ladder, LOCAL-686). D658/LEAD review
--                                  of LOCAL-690: Apple's non-renewing product
--                                  carries NO duration, so ONE product per price
--                                  serves every community AND every length — the
--                                  LENGTH belongs to the community's pass option
--                                  (table 3), not the catalogue. No length here.
--   3. community_passes          — the pass OPTIONS an owner offers on their
--                                  community: (community, product, length) →
--                                  shown as "$5 / month" on the community page.
--                                  The LENGTH + duration_days live HERE; the
--                                  server computes expiry = now + duration_days.
--                                  A free community has none.
--   4. community_memberships     — one row per (user, community) membership with
--                                  an expires_at the server enforces, the
--                                  verifying transaction, and the reminder
--                                  bookkeeping (3-days-before + at-expiry).
--   5. community_episodes        — owner audio METADATA only: (community, order,
--                                  title, audio_url, [guid]). A feed's items
--                                  become episodes; links become episodes. NO
--                                  content check on owner audio (D657 addendum).
--   6. community_reports         — a report on a community tour routes to the
--                                  OWNER (D658 addendum 2 §); Audioura keeps the
--                                  per-community `disabled` off-switch.
--
-- Idempotent: CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS / INSERT ...
-- ON CONFLICT, wrapped in one transaction. Applying twice is a no-op.
--
-- NOT in this migration (later task, D657 payouts §): owner payouts, tax forms,
-- statements. This is communities, passes, memberships, episodes, codes and the
-- off-switch only.

BEGIN;

-- ─── 1. communities ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS communities (
    id              SERIAL PRIMARY KEY,
    -- The OWNER: the publisher of record who accepts the terms (D657). An
    -- anonymous device secret_id, same identity space as device_entitlement.
    owner_user_id   VARCHAR(255) NOT NULL,
    name            VARCHAR(200) NOT NULL,
    description     TEXT,
    -- Organiser card shown on the community page (D658 (c)).
    organiser_name     VARCHAR(200),
    organiser_photo_url TEXT,
    organiser_bio       TEXT,
    organiser_contact   VARCHAR(300),
    -- Rules + waiver text. A community that carries a waiver is ALWAYS Private
    -- (D658 addendum 2 §4 / D656); has_waiver is the flag the join/listing path
    -- reads, and a CHECK below forbids a Listed waiver community.
    rules_text      TEXT,
    waiver_text     TEXT,
    has_waiver      BOOLEAN NOT NULL DEFAULT FALSE,
    -- Free (book club) vs paid. A free community skips passes (D658 addendum §).
    is_paid         BOOLEAN NOT NULL DEFAULT FALSE,
    -- Listed (on the Home map with a community badge) vs Private (invite only,
    -- never on the map). D658 addendum 2 §4.
    visibility      VARCHAR(16) NOT NULL DEFAULT 'private'
                    CHECK (visibility IN ('listed', 'private')),
    -- A Listed community needs a location (D657). Enforced in the CHECK below.
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    -- The invite/share code pasted into the Home search box (D658 addendum 2
    -- §3). Unique across communities; same 8-char base62 shape as a tour share
    -- code so classifySearchInput recognises it.
    join_code       VARCHAR(16) UNIQUE,
    -- ONE optional owner RSS feed. Episodes are parsed from it (metadata only).
    feed_url        TEXT,
    -- Audioura's per-community OFF SWITCH (D657 addendum / D658 addendum 2 §).
    -- A disabled community lists nothing, grants no new codes/episodes.
    disabled        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- A waiver community can never be Listed (always Private — D658/D656).
    CONSTRAINT chk_communities_waiver_private
        CHECK (NOT (has_waiver AND visibility = 'listed')),
    -- A Listed community must have a location.
    CONSTRAINT chk_communities_listed_has_location
        CHECK (visibility <> 'listed' OR (latitude IS NOT NULL AND longitude IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_communities_owner ON communities(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_communities_join_code ON communities(join_code);
-- Fast "which communities show on the map?" — Listed, not disabled, located.
CREATE INDEX IF NOT EXISTS idx_communities_listed
    ON communities(visibility) WHERE visibility = 'listed' AND disabled = FALSE;

COMMENT ON TABLE communities IS
    'LOCAL-690/D657-D658: one owner-published community of owner-hosted audio. '
    'Audioura stores metadata only. disabled = per-community off-switch. A '
    'waiver community is always Private; a Listed community needs a location.';


-- ─── 2. community_pass_products — the fixed non-renewing pass catalogue ──────
-- One row per PRICE — the 34-step round-dollar LADDER (LOCAL-686, price_tiers
-- tiers 8..41). LEAD review of LOCAL-690 (2026-10-14): Apple's non-renewing
-- product carries NO duration, so ONE product per price serves EVERY community
-- and EVERY length. Price × length would be 136 App Store products for Michael
-- to create; one-per-price is 34. The LENGTH is NOT here — it belongs to the
-- community's pass option (table 3). Product ids are 'audioura.pass.usd<N>',
-- the SAME 34 steps as the tour ladder's 'audioura.tour.usd<N>'. Michael owns
-- the prices (a row, changeable by SQL, like price_tiers).
CREATE TABLE IF NOT EXISTS community_pass_products (
    product_id      VARCHAR(64) PRIMARY KEY,       -- store product id, e.g. 'audioura.pass.usd5'
    price_usd       NUMERIC(10,2) NOT NULL,
    label           VARCHAR(48) NOT NULL,          -- the price only, e.g. '$5'
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- The 34 ladder prices (LOCAL-686): $2..$20 /$1, $25..$50 /$5, $60..$100 /$10,
-- $125..$200 /$25. One Apple non-renewing subscription product per price; the
-- community's option (table 3) picks the length. A new price is one more row
-- with no redeploy. ON CONFLICT re-asserts the canonical price/label so a
-- re-run restores them (idempotent).
INSERT INTO community_pass_products (product_id, price_usd, label) VALUES
    ('audioura.pass.usd2',   2.00,   '$2'),
    ('audioura.pass.usd3',   3.00,   '$3'),
    ('audioura.pass.usd4',   4.00,   '$4'),
    ('audioura.pass.usd5',   5.00,   '$5'),
    ('audioura.pass.usd6',   6.00,   '$6'),
    ('audioura.pass.usd7',   7.00,   '$7'),
    ('audioura.pass.usd8',   8.00,   '$8'),
    ('audioura.pass.usd9',   9.00,   '$9'),
    ('audioura.pass.usd10',  10.00,  '$10'),
    ('audioura.pass.usd11',  11.00,  '$11'),
    ('audioura.pass.usd12',  12.00,  '$12'),
    ('audioura.pass.usd13',  13.00,  '$13'),
    ('audioura.pass.usd14',  14.00,  '$14'),
    ('audioura.pass.usd15',  15.00,  '$15'),
    ('audioura.pass.usd16',  16.00,  '$16'),
    ('audioura.pass.usd17',  17.00,  '$17'),
    ('audioura.pass.usd18',  18.00,  '$18'),
    ('audioura.pass.usd19',  19.00,  '$19'),
    ('audioura.pass.usd20',  20.00,  '$20'),
    ('audioura.pass.usd25',  25.00,  '$25'),
    ('audioura.pass.usd30',  30.00,  '$30'),
    ('audioura.pass.usd35',  35.00,  '$35'),
    ('audioura.pass.usd40',  40.00,  '$40'),
    ('audioura.pass.usd45',  45.00,  '$45'),
    ('audioura.pass.usd50',  50.00,  '$50'),
    ('audioura.pass.usd60',  60.00,  '$60'),
    ('audioura.pass.usd70',  70.00,  '$70'),
    ('audioura.pass.usd80',  80.00,  '$80'),
    ('audioura.pass.usd90',  90.00,  '$90'),
    ('audioura.pass.usd100', 100.00, '$100'),
    ('audioura.pass.usd125', 125.00, '$125'),
    ('audioura.pass.usd150', 150.00, '$150'),
    ('audioura.pass.usd175', 175.00, '$175'),
    ('audioura.pass.usd200', 200.00, '$200')
ON CONFLICT (product_id) DO UPDATE SET
    price_usd = EXCLUDED.price_usd,
    label     = EXCLUDED.label,
    active    = TRUE;

COMMENT ON TABLE community_pass_products IS
    'LOCAL-690/D658 (LEAD review): the fixed catalogue of NON-RENEWING pass store '
    'products — ONE product per PRICE (the 34 ladder prices, LOCAL-686). Apple''s '
    'non-renewing product carries no length, so one product serves every community '
    'and every length; the LENGTH lives on the community''s option (community_passes).';


-- ─── 3. community_passes — the pass OPTIONS an owner offers (price × length) ─
-- The LENGTH lives HERE (not the catalogue): the owner offers "$5 / month" by
-- attaching product audioura.pass.usd5 with length='month'. One product + four
-- lengths = four possible options, all from the SAME store product. unique
-- (community, product, length). Lengths are EXACTLY four — day, week, month,
-- year; durations day=1, week=7, month=30, year=365 (calendar-free arithmetic
-- the server uses so a test can assert expiry = now + duration_days).
CREATE TABLE IF NOT EXISTS community_passes (
    id            SERIAL PRIMARY KEY,
    community_id  INTEGER NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    product_id    VARCHAR(64) NOT NULL REFERENCES community_pass_products(product_id),
    length        VARCHAR(8) NOT NULL
                  CHECK (length IN ('day', 'week', 'month', 'year')),
    duration_days INTEGER NOT NULL CHECK (duration_days > 0),
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_community_passes UNIQUE (community_id, product_id, length)
);
CREATE INDEX IF NOT EXISTS idx_community_passes_community ON community_passes(community_id);

COMMENT ON TABLE community_passes IS
    'LOCAL-690/D658 (LEAD review): which pass OPTIONS a community offers — a '
    '(price product, length) pair with its duration_days. The LENGTH lives here, '
    'not the catalogue. unique (community, product, length). Free community: none.';


-- ─── 4. community_memberships — the member''s access + expiry ─────────────────
CREATE TABLE IF NOT EXISTS community_memberships (
    id             SERIAL PRIMARY KEY,
    user_id        VARCHAR(255) NOT NULL,          -- the member device secret_id
    community_id   INTEGER NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    -- When the pass expires. The server enforces this: after it passes, NEW
    -- codes/episodes are refused, but downloaded audio stays playable (that
    -- lives on the device, D658 addendum §2). NULL = a FREE community membership
    -- (never expires).
    expires_at     TIMESTAMP,
    -- The verifying store transaction (NULL for a free join).
    transaction_id VARCHAR(255),
    store          VARCHAR(20),
    product_id     VARCHAR(64),
    price_usd      NUMERIC(10,2),
    -- Reminder bookkeeping (D657/D658): one reminder 3 days BEFORE expiry and
    -- one AT expiry. Timestamps record when each was sent so the reminder tick
    -- never double-sends and a test can assert the window.
    reminded_before_at TIMESTAMP,
    reminded_expiry_at TIMESTAMP,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- One membership row per (user, community): a renewal UPDATES the expiry,
    -- it does not stack rows. Buying again extends/replaces (D657: "buy again").
    CONSTRAINT uq_community_memberships UNIQUE (user_id, community_id)
);
CREATE INDEX IF NOT EXISTS idx_memberships_user ON community_memberships(user_id);
CREATE INDEX IF NOT EXISTS idx_memberships_community ON community_memberships(community_id);
-- Fast "which memberships are expiring soon / have expired?" for the reminder tick.
CREATE INDEX IF NOT EXISTS idx_memberships_expires ON community_memberships(expires_at)
    WHERE expires_at IS NOT NULL;

COMMENT ON TABLE community_memberships IS
    'LOCAL-690/D657-D658: one row per (member, community). expires_at enforced by '
    'the server for NEW content only (downloaded audio stays playable). One row '
    'per pair — buying again extends the expiry. NULL expiry = free community.';


-- ─── 5. community_episodes — owner audio METADATA only (no files) ────────────
CREATE TABLE IF NOT EXISTS community_episodes (
    id            SERIAL PRIMARY KEY,
    community_id  INTEGER NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    -- Episode order (a tour "stop" index). 1-based.
    position      INTEGER NOT NULL,
    title         VARCHAR(500) NOT NULL,
    -- The owner-HOSTED MP3 URL. Audioura streams/downloads from here and NEVER
    -- stores the file (D658 addendum 2 §2). NO content check (D657 addendum).
    audio_url     TEXT NOT NULL,
    -- RSS item guid when the episode came from a feed (lets a re-parse update in
    -- place rather than duplicate). NULL for a hand-entered link.
    guid          VARCHAR(500),
    -- 'link' (owner typed a link) or 'feed' (parsed from feed_url). Metadata
    -- provenance only; both are played identically.
    source        VARCHAR(8) NOT NULL DEFAULT 'link'
                  CHECK (source IN ('link', 'feed')),
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_community_episodes_pos UNIQUE (community_id, position)
);
CREATE INDEX IF NOT EXISTS idx_episodes_community ON community_episodes(community_id);
-- A feed re-parse upserts on (community, guid) when a guid is present.
CREATE UNIQUE INDEX IF NOT EXISTS uq_episodes_community_guid
    ON community_episodes(community_id, guid) WHERE guid IS NOT NULL;

COMMENT ON TABLE community_episodes IS
    'LOCAL-690/D657-D658: episode METADATA only (title, order, owner-hosted URL). '
    'A feed item or a typed link becomes an episode; Audioura never stores the '
    'MP3. NO content check on owner audio (D657 addendum).';


-- ─── 6. community_reports — a report routes to the OWNER ─────────────────────
CREATE TABLE IF NOT EXISTS community_reports (
    id             SERIAL PRIMARY KEY,
    community_id   INTEGER NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    reporter_user_id VARCHAR(255),
    reason         TEXT,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_reports_community ON community_reports(community_id);

COMMENT ON TABLE community_reports IS
    'LOCAL-690/D657-D658: a report on a community tour goes to the community '
    'OWNER. Audioura keeps the per-community disabled off-switch separately.';

COMMIT;
