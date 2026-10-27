-- 03_local778_seed.sql — LOCAL-778 live-proof seed (runs after schema + plans data).
--
-- 1) Flip L2 to by_reference_only = FALSE so the gate returns mode='reuse_first'
--    (D719 amended — the whole point of this ticket).
-- 2) An L2 test device so the orchestrator's check_operation allows generation.
-- 3) A Salem Witch Museum tour with 4 stops as REUSABLE material (is_test FALSE so
--    the LOCAL-597 finder mines it; this is this stack's OWN postgres volume,
--    invisible to the shared dev DB, dropped with `down -v`).

UPDATE plans SET by_reference_only = FALSE WHERE plan_id = 'l2';

INSERT INTO users (secret_id, plan) VALUES ('local778-tester', 'l2')
    ON CONFLICT (secret_id) DO NOTHING;

INSERT INTO device_entitlement (user_id, level) VALUES ('local778-tester', 'l2')
    ON CONFLICT (user_id) DO UPDATE SET level = 'l2';

-- A delivered 4-stop Salem Witch Museum tour (museum), in the pool store's format.
INSERT INTO audio_tours (tour_name, request_string, tour_content, number_requested,
                         lat, lng, is_test, storied_mode)
VALUES (
  'Salem Witch Museum, Salem, MA',
  'Salem Witch Museum, Salem, MA',
  E'Step-by-Step Audio Guided Tour: Salem Witch Museum, Salem, MA\nTour-Category: museum\n\n' ||
  E'Stop 1: The Stage Presentation\n\nAddress: 19 1/2 Washington Square N, Salem, MA\n\nCoordinates: 42.5232, -70.8930\n\n' ||
  E'Orientation: Enter the main auditorium.\n\nThe Salem Witch Museum opens with its famous stage presentation, thirteen life-size scenes lit in sequence that retell the events of 1692. Already-researched narration body for the stage room.\n\nDirections: Proceed to the Dungeon Scene.\n\n' ||
  E'Stop 2: The Dungeon Scene\n\nAddress: 19 1/2 Washington Square N, Salem, MA\n\nCoordinates: 42.5232, -70.8930\n\n' ||
  E'Orientation: Look to the accused in the cells.\n\nThe dungeon tableau depicts the cramped conditions the accused endured while awaiting trial. Already-researched narration body for the dungeon.\n\nDirections: Proceed to the Trial Scene.\n\n' ||
  E'Stop 3: The Trial Scene\n\nAddress: 19 1/2 Washington Square N, Salem, MA\n\nCoordinates: 42.5232, -70.8930\n\n' ||
  E'Orientation: Face the magistrates'' bench.\n\nThe trial scene stages the spectral-evidence testimony that doomed so many. Already-researched narration body for the trial.\n\nDirections: Proceed to the Memorial.\n\n' ||
  E'Stop 4: The Witch Trials Memorial\n\nAddress: 24 Liberty St, Salem, MA\n\nCoordinates: 42.5215, -70.8942\n\n' ||
  E'Orientation: Step out to the stone benches.\n\nThe nearby memorial honours the twenty people executed in 1692. Already-researched narration body for the memorial.\n\n' ||
  E'From The Stage Presentation to The Witch Trials Memorial, you have followed the thread.\n\nThat''s 4 stops.\n\n' ||
  E'Sources: This tour draws on information from salemwitchmuseum.com.\n',
  4, 42.5232, -70.8930, FALSE, TRUE
)
ON CONFLICT DO NOTHING;
