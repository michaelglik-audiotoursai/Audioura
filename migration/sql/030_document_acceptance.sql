-- 030_document_acceptance.sql  (LOCAL-691 — legal pages)
--
-- Records that a user accepted a legal document (version-stamped), so the
-- required acceptances for selling a guide tour and creating a community are
-- captured and auditable. Also used for the lightweight "By buying you agree
-- to the Terms" acceptance line on the Buy / community-pass sheets.
--
--   user_id      the device's pseudonymous id (USER-NNNNNNNN), same identity
--                space as communities.owner_user_id / device_entitlement.
--   document     which document was accepted. A short slug, e.g.
--                'terms', 'guide_terms', 'organiser_terms', 'privacy',
--                'content_policy', 'refunds'. Not constrained to a fixed list
--                on purpose — a new document must not require a migration.
--   version      the document version the user accepted (e.g.
--                '2026-10-14-draft1'); lets us prove WHICH text was agreed to
--                and re-prompt when a new version ships.
--   accepted_at  when the acceptance was recorded (server time).
--
-- One row per (user, document, version): accepting the same version again is a
-- harmless no-op (ON CONFLICT DO NOTHING in the API). Re-accepting after a new
-- version ships inserts a new row, preserving the full history.
--
-- Additive & idempotent: CREATE TABLE / CREATE INDEX ... IF NOT EXISTS, wrapped
-- in one transaction. Applying twice is a no-op. No DROP, no DELETE, no retype.

BEGIN;

CREATE TABLE IF NOT EXISTS document_acceptance (
    id           SERIAL PRIMARY KEY,
    user_id      VARCHAR(255) NOT NULL,
    document     VARCHAR(64)  NOT NULL,
    version      VARCHAR(64)  NOT NULL,
    accepted_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    -- One acceptance row per (user, document, version). Re-accepting the same
    -- version is idempotent; a new version adds a new row (history kept).
    CONSTRAINT uq_document_acceptance UNIQUE (user_id, document, version)
);

-- The common lookup is "what has this user accepted?" (to decide whether to
-- re-prompt), so index by user then document.
CREATE INDEX IF NOT EXISTS idx_document_acceptance_user
    ON document_acceptance (user_id, document);

COMMIT;
