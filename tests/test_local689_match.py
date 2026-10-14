#!/usr/bin/env python3
"""
LOCAL-689 — Personal Match % tests.

Three things the brief asks to be proven:
  1. The formula: known preference + character + score vectors → a known %.
  2. The <5-swipe cold-start case: match_percent null + the "swipe a few" line.
  3. A translation uses its ORIGINAL tour's metrics (and score), not its own.

The formula (personal_match.compute_match) is a pure function, so (1) and (2)
are exact-value unit tests with no database. (3) exercises the map-delivery
resolution path (_single_tour_match / _attach_match) against a tiny in-memory
fake cursor, so it is deterministic and runs anywhere — it proves the
translation→original mapping without needing a live Postgres.

Run:  pytest tests/test_local689_match.py -q
   or: python3 tests/test_local689_match.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'map_delivery'))

import personal_match as pm  # noqa: E402


# ─── 1. The formula — known vectors → known % ────────────────────────────────

def _match(prefs, swipes, char, score):
    return pm.compute_match(prefs, swipes, char, score)


def test_formula_history_lover_history_tour_high():
    """A listener who likes history, a history-heavy tour, top score (8.0).

    align = 0.5 + Σ c_k*(pref_k-0.5)
          = 0.5 + [0.2*(0.5-0.5) + 0.7*(0.9-0.5) + 0.1*(0.2-0.5)]
          = 0.5 + [0 + 0.28 - 0.03] = 0.75
    q     = (8.0-5.0)/3.0 = 1.0
    match = round(100*(0.75*0.75 + 0.25*1.0)) = round(100*(0.5625+0.25))
          = round(81.25) = 81
    """
    r = _match({'details': 0.5, 'historic': 0.9, 'social': 0.2}, 20,
               {'details': 0.2, 'historic': 0.7, 'social': 0.1}, 8.0)
    assert r['match_percent'] == 81, r
    assert r['cold_start'] is False
    assert r['reasons'][0] == 'strong on history, which you like'
    assert r['reasons'][1] == 'light on details'


def test_formula_neutral_listener_is_pure_quality():
    """All prefs 0.5 → align = 0.5 for every tour (personalisation off). With a
    missing score the fallback 7.5 gives q = (7.5-5)/3 = 0.83333.
    match = round(100*(0.75*0.5 + 0.25*0.83333)) = round(37.5 + 20.833)
          = round(58.33) = 58."""
    r = _match({'details': 0.5, 'historic': 0.5, 'social': 0.5}, 10,
               {'details': 0.2, 'historic': 0.7, 'social': 0.1}, None)
    assert r['match_percent'] == 58, r


def test_formula_social_lover_history_tour_low():
    """Likes social, dislikes nothing strongly, but the tour is history-heavy
    and light on social; mid score 6.5.
    align = 0.5 + [0.2*(0.3-0.5) + 0.7*(0.3-0.5) + 0.1*(0.9-0.5)]
          = 0.5 + [-0.04 - 0.14 + 0.04] = 0.5 - 0.14 = 0.36
    q     = (6.5-5)/3 = 0.5
    match = round(100*(0.75*0.36 + 0.25*0.5)) = round(27 + 12.5) = round(39.5) = 40
    Reason 1 is honest: the tour is HEAVY on history, which this listener swipes
    past (pref 0.3 < 0.5)."""
    r = _match({'details': 0.3, 'historic': 0.3, 'social': 0.9}, 10,
               {'details': 0.2, 'historic': 0.7, 'social': 0.1}, 6.5)
    assert r['match_percent'] == 40, r
    assert r['reasons'][0] == 'heavy on history, which you swipe past'
    assert 'light on people stories' in r['reasons']


def test_formula_bounds_perfect_and_worst():
    """Alignment is bounded to [0,1] and the blend to [0,100]."""
    # Perfectly aligned: tour is 100% a liked class (pref 1.0), score 8.0.
    best = _match({'details': 1.0, 'historic': 0.5, 'social': 0.5}, 30,
                  {'details': 1.0, 'historic': 0.0, 'social': 0.0}, 8.0)
    # align = 0.5 + 1.0*(1.0-0.5) = 1.0 ; q = 1.0 → 100
    assert best['match_percent'] == 100, best
    # Worst: tour is 100% a disliked class (pref 0.0), score 5.0.
    worst = _match({'details': 0.0, 'historic': 0.5, 'social': 0.5}, 30,
                   {'details': 1.0, 'historic': 0.0, 'social': 0.0}, 5.0)
    # align = 0.5 + 1.0*(0.0-0.5) = 0.0 ; q = 0.0 → 0
    assert worst['match_percent'] == 0, worst


def test_formula_is_deterministic():
    """Same inputs → identical output every call (no randomness, no I/O)."""
    args = ({'details': 0.4, 'historic': 0.8, 'social': 0.3}, 12,
            {'details': 0.3, 'historic': 0.5, 'social': 0.2}, 7.1)
    first = _match(*args)
    for _ in range(5):
        assert _match(*args) == first


# ─── 2. The <5-swipe cold-start case ─────────────────────────────────────────

def test_cold_start_below_min_swipes():
    """A listener with 4 swipes (MIN_SWIPES is 5) gets no match."""
    r = _match({'details': 0.9, 'historic': 0.9, 'social': 0.1}, 4,
               {'details': 0.2, 'historic': 0.7, 'social': 0.1}, 8.0)
    assert r['match_percent'] is None
    assert r['reasons'] == []
    assert r['cold_start'] is True
    assert pm.NO_MATCH_REASON == "Swipe a few stops to get matches"


def test_cold_start_exactly_at_threshold_is_matched():
    """Exactly MIN_SWIPES (5) swipes IS enough — the boundary is inclusive."""
    r = _match({'details': 0.5, 'historic': 0.9, 'social': 0.2}, pm.MIN_SWIPES,
               {'details': 0.2, 'historic': 0.7, 'social': 0.1}, 8.0)
    assert r['match_percent'] is not None
    assert r['cold_start'] is False


def test_cold_start_no_prefs_row():
    """No preference row at all (None) → cold start regardless of swipe count."""
    r = _match(None, 50, {'details': 0.33, 'historic': 0.34, 'social': 0.33}, 7.5)
    assert r['match_percent'] is None
    assert r['cold_start'] is True


# ─── aggregate_tour_character ────────────────────────────────────────────────

def test_aggregate_character_mean_over_stops():
    """Per-stop class vectors → their mean, renormalised to sum 1."""
    stops = [
        (0.2, 0.7, 0.1),
        (0.4, 0.5, 0.1),
        (0.3, 0.6, 0.1),
    ]
    c = pm.aggregate_tour_character(stops)
    assert abs(c['details'] - 0.3) < 1e-9
    assert abs(c['historic'] - 0.6) < 1e-9
    assert abs(c['social'] - 0.1) < 1e-9
    assert abs(sum(c.values()) - 1.0) < 1e-9


def test_aggregate_character_no_stops_is_even_split():
    c = pm.aggregate_tour_character([])
    assert abs(c['details'] - 1 / 3) < 1e-9
    assert abs(c['historic'] - 1 / 3) < 1e-9
    assert abs(c['social'] - 1 / 3) < 1e-9


# ─── 3. A translation uses its ORIGINAL's metrics and score ──────────────────
#
# Exercises the map-delivery resolution path against a tiny fake cursor so the
# test is deterministic and DB-free. The fake answers exactly the queries
# _single_tour_match issues: resolve original, read prefs, read editor scores,
# aggregate stop_metrics.

class _FakeCursor:
    """Minimal psycopg2-cursor stand-in. Routes each SQL string to canned data.

    The world: tour 100 is an ORIGINAL with history-heavy stops and score 8.0;
    tour 200 is its French TRANSLATION (original_tour_id = 100) with NO stops of
    its own. A correct implementation must score tour 200 using tour 100's
    metrics and score — so 200's match must equal 100's."""

    def __init__(self, user_prefs, swipe_count):
        self._user_prefs = user_prefs
        self._swipe_count = swipe_count
        self._result = None

    class _Conn:
        def rollback(self):
            pass

    connection = _Conn()

    def execute(self, sql, params=None):
        s = ' '.join(sql.split()).lower()
        if 'from audio_tours where id' in s and 'original_tour_id' in s:
            tour_id = int(params[0])
            # 200 is a translation of 100; 100 is its own original.
            self._result = [(100,)] if tour_id == 200 else [(None,)]
        elif 'from user_class_prefs' in s:
            if self._user_prefs is None:
                self._result = []
            else:
                p = self._user_prefs
                self._result = [(p['details'], p['historic'], p['social'],
                                 self._swipe_count)]
        elif 'editor_score from audio_tours' in s:
            # Only the original (100) is scored; the translation row is not.
            self._result = [(100, 8.0)]
        elif 'from stop_metrics' in s:
            # Only tour 100 has stops. The translation (200) has none, so if the
            # implementation queried 200 it would get an empty character.
            ids = params[0]
            if 100 in ids:
                # mean history-heavy character for tour 100
                self._result = [(100, 0.2, 0.7, 0.1)]
            else:
                self._result = []
        else:
            self._result = []

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return list(self._result or [])

    def close(self):
        pass


def _load_app_module():
    """Import map_delivery/app.py as a module WITHOUT running its Flask app.
    Only the pure helpers (_single_tour_match etc.) are exercised."""
    import importlib.util
    app_path = os.path.join(os.path.dirname(__file__), '..', 'map_delivery', 'app.py')
    spec = importlib.util.spec_from_file_location('map_delivery_app', app_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_translation_uses_originals_metrics_and_score():
    """The translation (tour 200) scores identically to its original (tour 100),
    because the original's stop_metrics and editor_score govern both."""
    app = _load_app_module()
    prefs = {'details': 0.5, 'historic': 0.9, 'social': 0.2}

    original = app._single_tour_match(_FakeCursor(prefs, 20), 'u-hist', 100)
    translation = app._single_tour_match(_FakeCursor(prefs, 20), 'u-hist', 200)

    # Same number, same reasons — the translation inherited the original's story.
    assert original['match_percent'] == translation['match_percent']
    assert original['match_reasons'] == translation['match_reasons']
    # And it is the expected history-lover value (see formula test above).
    assert translation['match_percent'] == 81, translation
    # The translation reports that it was scored on the ORIGINAL tour.
    assert translation['scored_tour_id'] == 100
    assert translation['tour_id'] == 200


def test_translation_cold_start_matches_original():
    """With <5 swipes, both the original and its translation are cold — proving
    the resolution path does not accidentally differ on the null case."""
    app = _load_app_module()
    prefs = {'details': 0.5, 'historic': 0.9, 'social': 0.2}
    original = app._single_tour_match(_FakeCursor(prefs, 3), 'u', 100)
    translation = app._single_tour_match(_FakeCursor(prefs, 3), 'u', 200)
    assert original['match_percent'] is None
    assert translation['match_percent'] is None
    assert translation['match_reason'] == pm.NO_MATCH_REASON


def test_batched_attach_match_no_per_tour_query():
    """_attach_match adds the block to every item with ONE prefs query and ONE
    batched stop_metrics aggregate — proven by counting execute() calls."""
    app = _load_app_module()
    prefs = {'details': 0.5, 'historic': 0.9, 'social': 0.2}

    class _CountingCursor(_FakeCursor):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.stop_metrics_queries = 0
            self.prefs_queries = 0

        def execute(self, sql, params=None):
            s = ' '.join(sql.split()).lower()
            if 'from stop_metrics' in s:
                self.stop_metrics_queries += 1
            if 'from user_class_prefs' in s:
                self.prefs_queries += 1
            super().execute(sql, params)

    cur = _CountingCursor(prefs, 20)
    # Two originals + one translation of 100, as list-endpoint items.
    tours = [
        {'id': 100, 'original_tour_id': None, 'distance_km': 1.0},
        {'id': 200, 'parent_tour_id': 100, 'distance_km': 2.0},   # translation
        {'id': 100, 'original_tour_id': None, 'distance_km': 3.0},
    ]
    editor = {100: 8.0}
    app._attach_match(cur, 'u-hist', tours, editor)

    assert cur.prefs_queries == 1, "prefs must be read exactly once"
    assert cur.stop_metrics_queries == 1, "stop_metrics must be one batched query"
    for t in tours:
        assert t['match_percent'] == 81, t
        assert t['match_reasons']


# ─── script entry point ──────────────────────────────────────────────────────

if __name__ == '__main__':
    import traceback
    tests = [v for k, v in sorted(globals().items())
             if k.startswith('test_') and callable(v)]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception:  # noqa: BLE001
            print(f"  FAIL  {t.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed, {len(tests)} total")
    sys.exit(1 if failed else 0)
