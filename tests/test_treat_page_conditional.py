#!/usr/bin/env python3
"""D519 — the Treat Page is mentioned only when a treat is near a stop.

Michael, 2026-08-24: **only mention the Treat Page if it is genuinely near a stop
of the tour, any tour type, and it must not be the obligatory closing of every
tour.** Before this it closed every tour ever generated, including a three-stop
tour of the MFA in Boston whose nearest treat row does not exist at all.

Run: python3 tests/test_treat_page_conditional.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILURES = []


def check(name, condition, detail=''):
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}{(': ' + detail) if detail else ''}")
        FAILURES.append(name)


# Real coordinates. The MFA is the tour under test; the Gardner is 600 m away and
# stands in for a treat that is genuinely walkable; Fenway Park is 1.6 km away and
# stands for one that is not; Nice is the other side of the Atlantic.
MFA = (42.3394, -71.0942)
GARDNER = (42.3381, -71.0992)          # ~0.45 km from the MFA
FENWAY = (42.3467, -71.0972)           # ~0.83 km — inside 1 km
BU_BRIDGE = (42.3540, -71.1090)        # ~2.0 km — outside 1 km
NICE = (43.7102, 7.2620)

STOPS = [('Le Lézard aux plumes d’or', MFA),
         ('Au Soleil du Plafond', MFA),
         ('Moses and Monotheism', MFA)]


def test_no_treats_means_no_mention():
    from generate_tour_text import nearest_treat_to_any_stop as N
    check('empty treats table earns no mention', N([], STOPS, 1.0) is None)
    check('None rows earn no mention', N(None, STOPS, 1.0) is None)


def test_far_treat_earns_no_mention():
    from generate_tour_text import nearest_treat_to_any_stop as N
    rows = [('Café de Turin', NICE[0], NICE[1]),
            ('A bar by the BU Bridge', BU_BRIDGE[0], BU_BRIDGE[1])]
    check('a treat 2 km away is not "around here"', N(rows, STOPS, 1.0) is None)


def test_near_treat_earns_the_mention():
    from generate_tour_text import nearest_treat_to_any_stop as N
    rows = [('Café de Turin', NICE[0], NICE[1]),
            ('Gardner Café', GARDNER[0], GARDNER[1])]
    hit = N(rows, STOPS, 1.0)
    check('a treat 450 m from a stop earns it', hit is not None)
    check('and it is the near one that is named',
          hit and hit['treat'] == 'Gardner Café', str(hit))
    check('with a real distance', hit and 0.3 < hit['km'] < 0.6, str(hit))


def test_nearest_wins_and_any_stop_counts():
    """"Near a stop" — not near the last stop. A listener stands at all of them."""
    from generate_tour_text import nearest_treat_to_any_stop as N
    stops = [('First stop, in Nice', NICE), ('Last stop, at the MFA', MFA)]
    rows = [('Café de Turin', NICE[0], NICE[1]),
            ('Gardner Café', GARDNER[0], GARDNER[1])]
    hit = N(rows, stops, 1.0)
    check('the treat next to the FIRST stop is found', hit is not None, str(hit))
    check('the nearest of the two wins',
          hit and hit['km'] < 0.1, str(hit))


def test_bad_coordinates_are_skipped_not_guessed():
    from generate_tour_text import nearest_treat_to_any_stop as N
    rows = [('No coordinates', None, None),
            ('Text coordinates', 'north', 'east'),
            ('Gardner Café', GARDNER[0], GARDNER[1])]
    hit = N(rows, STOPS, 1.0)
    check('unparseable rows are skipped, the good one still found',
          hit and hit['treat'] == 'Gardner Café', str(hit))
    check('a tour whose stops have no coordinates earns nothing',
          N(rows, [('Nowhere', None)], 1.0) is None)


def test_radius_is_the_knob():
    from generate_tour_text import nearest_treat_to_any_stop as N
    rows = [('Fenway', FENWAY[0], FENWAY[1])]
    check('0.83 km is inside the 1.0 km default', N(rows, STOPS, 1.0) is not None)
    check('and outside a 0.5 km radius', N(rows, STOPS, 0.5) is None)


def test_the_live_database_earns_nothing_today():
    """The measurement that matters: on this machine's DB, is it earned?

    Not a fixture — the actual table the generator queries. If a treat is ever
    loaded near the MFA this flips, and the tour should start mentioning it.
    """
    try:
        import psycopg2
    except ImportError:
        print('  SKIP  psycopg2 not installed')
        return
    url = os.environ.get('VENUE_CACHE_DB_URL', os.environ.get('DATABASE_URL')) or (
        'postgresql://admin:password123@localhost:5433/audiotours')
    try:
        conn = psycopg2.connect(url, connect_timeout=5)
    except Exception as e:
        print(f'  SKIP  no database ({type(e).__name__})')
        return
    from generate_tour_text import nearest_treat_to_any_stop as N
    cur = conn.cursor()
    cur.execute('SELECT ad_name, lat, lng FROM treats '
                'WHERE lat IS NOT NULL AND lng IS NOT NULL')
    rows = cur.fetchall()
    hit = N(rows, STOPS, 1.0)
    print(f'  INFO  {len(rows)} treat(s) with coordinates in the live table; '
          f'nearest to an MFA stop: {hit}')
    check('the MFA tour does not currently earn a Treat Page mention',
          hit is None, str(hit))
    conn.close()


if __name__ == '__main__':
    print('D519 — the Treat Page must be earned\n')
    for fn in (test_no_treats_means_no_mention,
               test_far_treat_earns_no_mention,
               test_near_treat_earns_the_mention,
               test_nearest_wins_and_any_stop_counts,
               test_bad_coordinates_are_skipped_not_guessed,
               test_radius_is_the_knob,
               test_the_live_database_earns_nothing_today):
        print(f"\n{fn.__name__}")
        fn()
    print()
    if FAILURES:
        print(f"FAILED — {len(FAILURES)} check(s): {', '.join(FAILURES)}")
        sys.exit(1)
    print('ALL TESTS PASSED')
