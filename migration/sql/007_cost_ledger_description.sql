-- Migration 007: Add description column to cost_ledger for human-readable display
-- Part of LOCAL-69 (Subscribed #8 — meter the news path)
--
-- The Wallet shows transactions like "Article: How I Built This" or
-- "Tour: French Riviera biking" — not raw operation_type strings.
-- Storing this at write time means the wallet query is a simple SELECT,
-- no joins to article_requests or tour_requests needed.

BEGIN;

ALTER TABLE cost_ledger ADD COLUMN IF NOT EXISTS description VARCHAR(256);

COMMENT ON COLUMN cost_ledger.description IS 'Human-readable label for Wallet display, e.g. "Article: How I Built This" or "Tour: French Riviera"';

COMMIT;
