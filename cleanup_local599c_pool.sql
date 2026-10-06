-- LOCAL-599C r3 — pool hygiene.
--
-- r2 seeded 7 MassArt stop_pool rows, 4 of them PAST exhibitions. r3 never ships
-- a past show as a stop, so those 4 rows must go. Removed by EXACT pool_key +
-- title, guarded so the transaction aborts unless EXACTLY 4 rows match (never a
-- broad delete). The next run reseeds the pool with the on-view works/rooms.
--
-- DB: postgresql://admin:password123@postgres-2:5432/audiotours
-- Container: development-postgres-2-1  (NOT any audioura-* container).
-- Run: docker exec -i development-postgres-2-1 psql -U admin -d audiotours \
--        -v ON_ERROR_STOP=1 < cleanup_local599c_pool.sql
--
-- Observed counts (2026-10-06):
--   BEFORE: massart rows = 7, total stop_pool rows = 909
--   DELETE 4 (Nicholas Galanin, Ghost of a Dream, Masako Miki, Press & Pull)
--   AFTER : massart rows = 3 (Banu Cennetoğlu, Baseera Khan, Robert Lazzarini),
--           total stop_pool rows = 905

\echo === BEFORE ===
SELECT count(*) AS massart_before FROM stop_pool
  WHERE pool_key = 'v2|loc:massart art museum boston ma|museum';
SELECT count(*) AS total_before FROM stop_pool;

BEGIN;
DO $$
DECLARE n int;
BEGIN
  SELECT count(*) INTO n FROM stop_pool
    WHERE pool_key = 'v2|loc:massart art museum boston ma|museum'
      AND title IN ('Nicholas Galanin','Ghost of a Dream','Masako Miki','Press & Pull');
  IF n <> 4 THEN
    RAISE EXCEPTION 'expected exactly 4 past rows, found %, aborting', n;
  END IF;
END $$;

DELETE FROM stop_pool
  WHERE pool_key = 'v2|loc:massart art museum boston ma|museum'
    AND title IN ('Nicholas Galanin','Ghost of a Dream','Masako Miki','Press & Pull');
COMMIT;

\echo === AFTER ===
SELECT count(*) AS massart_after FROM stop_pool
  WHERE pool_key = 'v2|loc:massart art museum boston ma|museum';
SELECT count(*) AS total_after FROM stop_pool;
SELECT title FROM stop_pool
  WHERE pool_key = 'v2|loc:massart art museum boston ma|museum' ORDER BY title;
