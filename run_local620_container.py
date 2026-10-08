#!/usr/bin/env python3
"""run_local620_container.py — LOCAL-620 (D634) live acceptance (ISOLATED container).

Runs TWO museums through the REAL generation path with the LOCAL-620 branch code
mounted over /app, metered + hard-capped at $2.50 COMBINED (TEST_GEMINI_MAX_USD /
COST_HARD_LIMIT_USD, all providers, via tests/live_run_meter.py):

    1. McMullen Museum of Art, Boston, USA              (5 stops)
    2. Musée des Beaux-Arts de Lille, Lille, France     (4 stops)

Each museum is generated TWICE:
  PASS A — a user with NO prefs (balanced default; STORY_PREFS on but cold start);
  PASS B — a TEST user seeded with user_class_prefs strongly favouring SOCIAL.

For every delivered tour it prints the CLASS MIX PER STOP (the deterministic
story_type_classes vector over the delivered stop body — the same tags written to
stop_metrics.class_*), the tour-level class coverage, and the thematic conclusion.
It then stores each delivered tour_content as an additive is_test row in
development-postgres-2-1 ``audio_tours`` (creator_type='Test') so ``critique.sh
<id>`` scores the SAME spoken text.

The social-seeded test user and its user_class_prefs row are the ONLY rows this
run writes besides the is_test tours; the seeded user_id is a unique
``local620_social_<ts>`` so it collides with nothing. No DELETE.

Usage (inside the isolated container):
    python3 run_local620_container.py
"""
# [LOCAL-613] Meter + cap this isolated run (install BEFORE importing generators).
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-620')
except Exception as _meter_err:
    print(f"[LOCAL-613] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import os
import re
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'            # force FRESH tours
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('TEST_GEMINI_MAX_USD', '2.50')
os.environ['COST_HARD_LIMIT_USD'] = '2.50'        # ticket cap (two venues)
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
os.environ.setdefault('STORY_PREFS', '1')         # per-listener tuning ON

VENUES = [
    ('McMullen Museum of Art, Boston, USA', 5, 'MCMULLEN'),
    ('Mus\u00e9e des Beaux-Arts de Lille, Lille, France', 4, 'LILLE'),
]

print("=== LOCAL-620 isolated live run (two museums; no-prefs then social-seeded) ===",
      flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}   combined cap: "
      f"${os.environ['COST_HARD_LIMIT_USD']}", flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402
import story_type_classes as _stc  # noqa: E402
import story_balance as _sbal  # noqa: E402

_THEMATIC_RE = re.compile(
    r"(?im)^(?:This tour|Across these stops|Across the stops|Taken together|"
    r"Together,? these|What connects|The works on this tour|"
    r"The stops on this tour|On this tour)\b")
_RESTAURANT_RE = re.compile(r"we can build you a restaurant tour", re.IGNORECASE)


def _conn():
    import psycopg2
    dburl = os.environ.get('DATABASE_URL')
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=os.environ.get('DB_HOST', 'development-postgres-2-1'),
        port=os.environ.get('DB_PORT', '5432'),
        dbname=os.environ.get('DB_NAME', 'audiotours'),
        user=os.environ.get('DB_USER', 'admin'),
        password=os.environ.get('DB_PASSWORD', 'password123'))


def _seed_social_user():
    """Create a unique test user with user_class_prefs strongly favouring SOCIAL.

    Returns the user_id, or None if seeding failed (then PASS B runs as cold
    start and the harness says so). Only INSERTs; no DELETE.
    """
    uid = f"local620_social_{int(time.time())}"
    try:
        conn = _conn()
        conn.autocommit = True
        with conn.cursor() as cur:
            # users row (FK target for prefs in some schemas)
            try:
                cur.execute(
                    "INSERT INTO users (secret_id) VALUES (%s) "
                    "ON CONFLICT (secret_id) DO NOTHING", (uid,))
            except Exception:
                pass
            # Strong SOCIAL lean: high alpha_social, modest others. pref = a/(a+b).
            cur.execute(
                """
                INSERT INTO user_class_prefs
                    (user_id, alpha_details, beta_details,
                     alpha_historic, beta_historic,
                     alpha_social, beta_social,
                     pref_details, pref_historic, pref_social, swipe_count)
                VALUES (%s, 1.2, 2.0, 1.4, 2.0, 6.0, 1.0, 0.375, 0.412, 0.857, 10)
                ON CONFLICT (user_id) DO UPDATE SET
                    alpha_social = EXCLUDED.alpha_social,
                    pref_social = EXCLUDED.pref_social,
                    swipe_count = EXCLUDED.swipe_count
                """, (uid,))
        conn.close()
        print(f"  [seed] social-seeded test user = {uid} "
              f"(pref_social=0.857, swipes=10)", flush=True)
        return uid
    except Exception as e:
        print(f"  [seed] user_class_prefs seed failed ({e}); PASS B = cold start",
              flush=True)
        return None


def _stop_bodies(text):
    """Return [(title, body)] for each delivered stop (body = narration region)."""
    try:
        import stop_pool_store as sps
        stops = sps.parse_delivered_stops(_tc.normalise_stop_headers(text))
        return [((s.get('title') or '').strip(), (s.get('narration') or '').strip())
                for s in stops]
    except Exception:
        # fallback: split on headers
        out = []
        parts = re.split(r'(?m)^Stop\s+\d+:\s*(.+?)\s*$', text)
        return out


def _print_class_mix(location, text):
    """Print the per-stop class mix (deterministic story_type_classes vector) and
    the tour-level coverage — the D634 item-3 tags, shown for the live tour."""
    pairs = _stop_bodies(text)
    print(f"\n[CLASS MIX PER STOP] — {location}", flush=True)
    bodies = []
    for i, (title, body) in enumerate(pairs, 1):
        bodies.append(body)
        v = _stc.stop_class_vector(body)
        seg = _stc.classify_segment_class(body)
        print(f"  Stop {i}: {title[:60]:<60} "
              f"details {v['details']:.2f} / historic {v['historic']:.2f} "
              f"/ social {v['social']:.2f}  (dominant: {seg})", flush=True)
    cov = _sbal.ensure_tour_class_coverage(bodies)
    print(f"  tour coverage: classes_present={cov['classes_present']} "
          f"missing={cov['missing']} covered={cov['covered']}", flush=True)
    return pairs


def _store_tour(location, text, n_stops, pass_label, user_id):
    try:
        conn = _conn()
    except Exception as e:
        print(f"  [store] db connect failed: {e}", flush=True)
        return None
    try:
        conn.autocommit = True
        name = f"LOCAL-620 {location.split(',')[0]} [{pass_label}] {int(time.time())}"
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audio_tours
                    (tour_name, request_string, number_requested,
                     tour_content, stops_count, creator_type, storied_mode,
                     is_test, track, tour_kind, description)
                VALUES (%s, %s, %s, %s, %s, 'Test', true, true, 'beta', 'full', %s)
                RETURNING id
                """,
                (name, location, n_stops, text, n_stops,
                 f"LOCAL-620 live ({pass_label}; user={user_id or 'none'})"))
            new_id = cur.fetchone()[0]
        conn.close()
        return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True)
        return None


def _run_one(location, stops, out_file, pass_label, user_id):
    print(f"\n=== [{pass_label}] generating: {location} ({stops} stops, "
          f"user={user_id or 'none'}) ===", flush=True)
    t0 = time.time()
    try:
        text, out_path, _coords = generate_tour_text(
            location, 'museum', out_file, stops, user_id=user_id)
    except Exception as e:
        print(f"RUN ERROR for {location} [{pass_label}]: {e}", flush=True)
        return None
    elapsed = time.time() - t0

    if not text:
        print(f"OUTCOME [{pass_label}]: NO TOUR TEXT after {elapsed:.1f}s",
              flush=True)
        return None

    delivered = _tc.count_delivered_stops(text)
    print(f"OUTCOME [{pass_label}]: DELIVERED — {len(text)} chars, "
          f"{delivered} stops, wall {elapsed:.1f}s", flush=True)

    _print_class_mix(location, text)

    # conclusion
    body = re.split(r'(?mi)^\s*Sources:', text)[0]
    m = _THEMATIC_RE.search(body)
    concl = body[m.start():].strip() if m else "(no thematic conclusion found)"
    print(f"\n---------------- CONCLUSION — {location} [{pass_label}] ----------------",
          flush=True)
    print(concl, flush=True)

    try:
        from generate_tour_text import _LAST_GENERATION_COST
        _c = dict(_LAST_GENERATION_COST or {})
        _tot = float(_c.get('tour_total_cost', _c.get('total_cost', 0.0)) or 0.0)
        print(f"[cost] tour_total=${_tot:.4f}", flush=True)
    except Exception:
        pass

    new_id = _store_tour(location, text, delivered, pass_label, user_id)
    if new_id:
        print(f"STORED audio_tours id = {new_id}  (is_test=true, {pass_label})",
              flush=True)
        print(f"LOCAL620_TOUR_ID={new_id}", flush=True)
    return new_id


# PASS A: no-prefs user (cold start). PASS B: social-seeded test user.
social_uid = _seed_social_user()

ids = []
for location, stops, slug in VENUES:
    a_id = _run_one(location, stops, f"/app/tours/LOCAL620_{slug}_A.txt",
                    "A no-prefs", None)
    if a_id:
        ids.append(a_id)
    b_id = _run_one(location, stops, f"/app/tours/LOCAL620_{slug}_B.txt",
                    "B social-seeded", social_uid)
    if b_id:
        ids.append(b_id)

print("\n=== LOCAL-620 run complete ===", flush=True)
print(f"LOCAL620_TOUR_IDS={','.join(str(i) for i in ids)}", flush=True)
print(f"LOCAL620_SOCIAL_USER={social_uid or 'none'}", flush=True)
