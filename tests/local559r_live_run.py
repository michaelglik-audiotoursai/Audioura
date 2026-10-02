#!/usr/bin/env python3
"""
[LOCAL-559R] LIVE driver — translate tour 301 -> ru and -> es with the llm engine,
using the FIXED translation_service.py. Measures wall time and per-tour LLM cost.

Non-destructive cache bypass (nothing is ever DELETEd):
  * The original defective rows are 373 (ru) and 374 (es), original_tour_id=301.
  * Any prior LOCAL-559R test rows (ids passed in PRIOR_TEST_IDS) are moved to a
    sentinel original_tour_id = -1 so (a) they don't satisfy the "already translated
    for 301" cache query and (b) they don't collide on the unique (lower(tour_name),
    original_tour_id) constraint when 373/374 are detached.
  * 373/374 are detached to original_tour_id=NULL so the cache misses; a fresh
    translation then INSERTs brand-new rows. 373 is ru and 374 is es (distinct
    names), so NULL/NULL does not collide.
  * New rows are hidden (lat/lng NULL). Finally, 373/374 are restored to 301.
"""
import os, sys, time, logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')

sys.path.insert(0, '/app')
import translation_service as ts

PRIOR_TEST_IDS = [int(x) for x in os.getenv('PRIOR_TEST_IDS', '').split(',') if x.strip()]
PARK_SLOT = int(os.getenv('PARK_SLOT', '2'))  # a valid, non-301 audio_tours id (FK target)

svc = ts.TranslationService()
assert svc.translation_engine == 'llm', f"engine must be llm, got {svc.translation_engine}"

conn = svc.get_db_connection()
cur = conn.cursor()

cur.execute("SELECT id, content_language, original_tour_id FROM audio_tours WHERE original_tour_id = 301 ORDER BY id;")
print("rows with original_tour_id=301 BEFORE:", cur.fetchall())

# Original defective pair to re-translate against.
ORIG_IDS = [373, 374]
moved_prior, detached = [], []
try:
    # 1) Park any prior test rows on a VALID non-301 original_tour_id so they neither
    #    cache-hit (query filters original_tour_id=301) nor fall under the partial
    #    unique index on lower(tour_name) WHERE original_tour_id IS NULL.
    if PRIOR_TEST_IDS:
        cur.execute("UPDATE audio_tours SET original_tour_id = %s WHERE id = ANY(%s);",
                    (PARK_SLOT, PRIOR_TEST_IDS))
        conn.commit()
        moved_prior = PRIOR_TEST_IDS
        print(f"Parked prior test rows {moved_prior} at original_tour_id={PARK_SLOT}")

    # 2) Detach the original defective pair so the cache misses. 373(ru)/374(es) have
    #    distinct names, so NULL/NULL does not violate the partial unique index.
    cur.execute("UPDATE audio_tours SET original_tour_id = NULL WHERE id = ANY(%s);", (ORIG_IDS,))
    conn.commit()
    detached = ORIG_IDS
    print(f"Detached original rows {detached} from original_tour_id=301 (cache bypass)")

    new_ids, timings, costs = {}, {}, {}
    for lang in ('ru', 'es'):
        t0 = time.time()
        new_id, cache_hit = svc.translate_tour_with_audio(301, lang)
        dt = time.time() - t0
        timings[lang], costs[lang], new_ids[lang] = dt, svc._llm_tour_cost, new_id
        print(f"[RESULT] lang={lang} new_id={new_id} cache_hit={cache_hit} "
              f"wall={dt:.1f}s llm_tour_cost=${svc._llm_tour_cost:.6f}")

    # 3) Hide new rows (never DELETE).
    for lang, nid in new_ids.items():
        if nid:
            cur.execute("UPDATE audio_tours SET lat = NULL, lng = NULL WHERE id = %s;", (nid,))
    conn.commit()
    print("Hid new rows (lat/lng NULL):", new_ids)

    print("\n=== SUMMARY ===")
    for lang in ('ru', 'es'):
        print(f"{lang}: new_id={new_ids[lang]} wall={timings[lang]:.1f}s cost=${costs[lang]:.6f}")
    print("NEW_IDS=" + ",".join(str(new_ids[l]) for l in ('ru', 'es') if new_ids[l]))
except Exception as e:
    conn.rollback()
    print("ERROR during run:", e)
    raise
finally:
    # Restore the original defective pair AND any parked prior rows to original_tour_id=301.
    try:
        if detached:
            cur.execute("UPDATE audio_tours SET original_tour_id = 301 WHERE id = ANY(%s);", (detached,))
            conn.commit()
            print(f"Restored original_tour_id=301 on {detached}")
        if moved_prior:
            cur.execute("UPDATE audio_tours SET original_tour_id = 301 WHERE id = ANY(%s);", (moved_prior,))
            conn.commit()
            print(f"Restored original_tour_id=301 on parked rows {moved_prior}")
    except Exception as e:
        conn.rollback()
        print("WARN restore failed:", e)
    cur.close()
    conn.close()
