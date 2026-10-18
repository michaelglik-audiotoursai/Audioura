-- 040: a server-written SHORT tour title (LOCAL-711 / D673). Additive, idempotent.
-- short_title is a 2–6 word summary of what the tour IS, plus the type, e.g.
-- "Massachusetts Politics — Walking Tour". Written once, when an ORIGINAL tour
-- is created, by one cheap LLM call (tour_short_title.py, gpt-4o-mini class).
-- NULL = not generated yet (or generation failed) → the app falls back to its
-- own shortTourTitle(tour_name). The user-typed tour_name is never changed.
-- A TRANSLATION carries the translated short_title when its original has one.
ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS short_title TEXT;
