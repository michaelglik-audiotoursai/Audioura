#!/usr/bin/env python3
"""run_local591_live.py — LOCAL-591 live acceptance, ISOLATED container.

Runs the TWO field cases through the REAL generation path with the LOCAL-591
fixes in place:

  CASE A (the defect): "Art and Architectual tour in Boston Athenaeum, boston, ma"
     5 stops  →  a tour INSIDE the Athenaeum (contained-venue / museum category),
     5 stops, every stop with coordinates.

  CASE B (the control): "walking tour of Beacon Hill, Boston, MA"
     4 stops  →  still a WALKING tour (not flipped to museum).

OpenAI hard cap $3.00 (ticket). Tour-output cache OFF so the fixed code runs,
not a cached pre-fix tour. audio_tours is only COUNTED, never written or deleted
(generate_tour_text does not insert tour rows; the orchestrator does).

Prints, per case: tour_category / tour_kind, delivered stop count, and the
coordinate of every delivered stop, so "5 stops INSIDE with coordinates" and
"still walking" are both auditable from the log.
"""
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ['COST_HARD_LIMIT_USD'] = '3.00'   # OpenAI hard cap $3 (ticket)

import generate_tour_text as g
from generate_tour_text import generate_tour_text


_COORD = re.compile(r'(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)')


def _audio_tours_count():
    try:
        import psycopg2
        url = os.environ.get('DATABASE_URL') or (
            f"postgresql://{os.environ.get('DB_USER','admin')}:"
            f"{os.environ.get('DB_PASSWORD','password123')}@"
            f"{os.environ.get('DB_HOST','localhost')}:{os.environ.get('DB_PORT','5432')}/"
            f"{os.environ.get('DB_NAME','audiotours')}")
        c = psycopg2.connect(url, connect_timeout=5)
        cur = c.cursor(); cur.execute("SELECT COUNT(*) FROM audio_tours")
        n = cur.fetchone()[0]; cur.close(); c.close()
        return n
    except Exception as e:
        return f"(count unavailable: {type(e).__name__}: {e})"


def _parse_stops(text):
    """Return [(name, coord_or_None), ...] from the assembled tour text."""
    stops = []
    # Stop headers look like 'Stop N: Name'
    headers = list(re.finditer(r'(?mi)^\s*Stop\s+(\d+)\s*[:\-]\s*(.+?)\s*$', text))
    for i, m in enumerate(headers):
        name = m.group(2).strip()
        seg = text[m.end(): headers[i + 1].start() if i + 1 < len(headers) else len(text)]
        cm = _COORD.search(seg)
        coord = f"{cm.group(1)}, {cm.group(2)}" if cm else None
        stops.append((name, coord))
    return stops


def run_case(tag, location, tour_type, stops):
    out = os.path.join('/app/tours', f'LOCAL591_{tag}.txt')
    print(f"\n{'='*72}\nCASE {tag}: {location!r}  ({stops} stops requested)\n{'='*72}")
    before = _audio_tours_count()
    t0 = time.time()
    text, out_file, coords = generate_tour_text(location, tour_type, out, stops)
    elapsed = time.time() - t0
    after = _audio_tours_count()

    cat = getattr(g, '_LAST_TOUR_KIND', None)
    cost = getattr(g, '_LAST_GENERATION_COST', {})
    print(f"\n--- CASE {tag} RESULT ({elapsed:.1f}s) ---")
    print(f"tour_kind / category : {cat}")
    print(f"generation cost      : {cost}")
    print(f"audio_tours BEFORE/AFTER (never DELETE): {before} / {after}")

    if not text:
        print(f"CASE {tag}: NO TEXT — clean fail. evidence="
              f"{getattr(g, '_LAST_CLEAN_FAIL_EVIDENCE', {})}")
        return {'tag': tag, 'text': False}

    parsed = _parse_stops(text)
    print(f"CASE {tag}: delivered {len(parsed)} stop(s):")
    all_have = True
    for name, coord in parsed:
        ok = 'OK' if coord else 'NO-COORD'
        if not coord:
            all_have = False
        print(f"   [{ok}] {name[:60]:<60} coord={coord}")
    print(f"CASE {tag}: every stop has coordinates = {all_have}")
    return {'tag': tag, 'text': True, 'n': len(parsed), 'all_coords': all_have, 'category': cat}


def main():
    print("=== LOCAL-591 ISOLATED LIVE RUN ===")
    print(f"model={os.environ['TOUR_LLM_MODEL']} cap=${os.environ['COST_HARD_LIMIT_USD']} "
          f"cache=OFF storied={os.environ['STORIED_MODE']}")
    results = []
    # CASE A — the exact field request (verbatim, including the typo).
    results.append(run_case('A_ATHENAEUM',
                            'Art and Architectual tour in Boston Athenaeum, boston, ma',
                            '', 5))
    # CASE B — the control: a city walking tour must stay walking.
    results.append(run_case('B_BEACON_HILL',
                            'walking tour of Beacon Hill, Boston, MA',
                            '', 4))

    print(f"\n{'#'*72}\nSUMMARY\n{'#'*72}")
    for r in results:
        print(f"  {r}")


if __name__ == '__main__':
    main()
