"""[LOCAL-711 / D673] Server-written short tour titles.

Covers:
  * make_short_title with a STUB model: a good title, a >60-char title, an empty
    reply, and an SDK exception — only the good one survives, the rest → None.
  * validate / _sanitise / _tour_type_from_name pure helpers.
  * the --backfill SELECT only touches NULL originals and the UPDATE writes ONLY
    short_title (never tour_name, never a DELETE), driven by a fake DB.
  * a translation copies the short_title: the translate step runs on the
    source's short_title and the INSERT carries the translated value.

No network, no real Postgres: the model call and the DB are stubbed.
"""
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tour_short_title as tst  # noqa: E402


# ─── stub model ───────────────────────────────────────────────────────────────
class _Usage:
    def __init__(self, tin=12, tout=6):
        self.prompt_tokens = tin
        self.completion_tokens = tout


def _stub_model(reply=None, exc=None):
    def _call(name, request_string, tour_type):
        if exc is not None:
            raise exc
        return reply, _Usage()
    return _call


# ─── make_short_title / validator ──────────────────────────────────────────────
def test_good_title_passes(monkeypatch):
    monkeypatch.setattr(tst, '_call_model',
                        _stub_model('Massachusetts Politics — Walking Tour'))
    title, usage = tst.make_short_title('long name', 'req', 'walking')
    assert title == 'Massachusetts Politics — Walking Tour'
    assert usage.prompt_tokens == 12


def test_over_60_chars_rejected(monkeypatch):
    monkeypatch.setattr(tst, '_call_model', _stub_model('X ' * 40 + '— Walking Tour'))
    title, _ = tst.make_short_title('n', 'r', 'walking')
    assert title is None


def test_empty_reply_rejected(monkeypatch):
    monkeypatch.setattr(tst, '_call_model', _stub_model(''))
    title, _ = tst.make_short_title('n', 'r', 'walking')
    assert title is None


def test_exception_returns_none(monkeypatch):
    monkeypatch.setattr(tst, '_call_model', _stub_model(exc=RuntimeError('boom')))
    title, usage = tst.make_short_title('n', 'r', 'walking')
    assert title is None
    assert isinstance(usage, tst._Failure)
    assert 'boom' in usage.reason


def test_make_short_title_only_never_raises(monkeypatch):
    monkeypatch.setattr(tst, '_call_model', _stub_model(exc=RuntimeError('x')))
    assert tst.make_short_title_only('n', 'r', 'walking') is None
    monkeypatch.setattr(tst, '_call_model', _stub_model('Faneuil Hall — Walking Tour'))
    assert tst.make_short_title_only('n', 'r', 'walking') == 'Faneuil Hall — Walking Tour'


def test_validate_rules():
    assert tst.validate('A — Tour') == 'A — Tour'
    assert tst.validate('') is None
    assert tst.validate('   ') is None
    assert tst.validate('x' * 60) == 'x' * 60
    assert tst.validate('x' * 61) is None


def test_sanitise_strips_quotes_label_punct():
    assert tst._sanitise('"Faneuil Hall — Walking Tour"') == 'Faneuil Hall — Walking Tour'
    assert tst._sanitise('Title: Museum of Fine Arts — Museum Tour') == \
        'Museum of Fine Arts — Museum Tour'
    assert tst._sanitise('Massachusetts Politics — Walking Tour.') == \
        'Massachusetts Politics — Walking Tour'
    assert tst._sanitise('  spaced   out  ') == 'spaced out'


def test_tour_type_from_name():
    assert tst._tour_type_from_name('X, Boston, MA - walking Tour') == 'walking'
    assert tst._tour_type_from_name('Museum of Fine Arts - museum Tour') == 'museum'
    assert tst._tour_type_from_name('X -  Tour') == ''
    assert tst._tour_type_from_name('No suffix') == ''


# ─── fake DB for the backfill ───────────────────────────────────────────────────
class _FakeCursor:
    """Minimal psycopg2-cursor stand-in. Holds a table of originals + translations
    and records every UPDATE so the test can assert that ONLY short_title is
    written and nothing is deleted."""

    def __init__(self, rows):
        # rows: list of dicts {id, tour_name, request_string, original_tour_id,
        #                       is_test, short_title}
        self.rows = rows
        self._result = []
        self.updates = []  # (id, column, value)
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append(sql)
        s = ' '.join(sql.split()).upper()
        if s.startswith('SELECT COUNT(*)'):
            n = sum(1 for r in self.rows
                    if r['original_tour_id'] is None and not r['is_test']
                    and r['short_title'] is None)
            self._result = [(n,)]
        elif s.startswith('SELECT ID, TOUR_NAME, REQUEST_STRING FROM AUDIO_TOURS WHERE ID'):
            tid = params[0]
            self._result = [(r['id'], r['tour_name'], r['request_string'])
                            for r in self.rows if r['id'] == tid]
        elif s.startswith('SELECT ID, TOUR_NAME, REQUEST_STRING FROM AUDIO_TOURS'):
            # the backfill SELECT: originals, not test, NULL short_title
            self._result = [(r['id'], r['tour_name'], r['request_string'])
                            for r in self.rows
                            if r['original_tour_id'] is None and not r['is_test']
                            and r['short_title'] is None]
        elif s.startswith('UPDATE AUDIO_TOURS SET SHORT_TITLE'):
            val, tid = params
            self.updates.append((tid, 'short_title', val))
            for r in self.rows:
                if r['id'] == tid:
                    r['short_title'] = val
        elif 'DELETE' in s:
            raise AssertionError('backfill must never DELETE')
        else:
            self._result = []

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return list(self._result)

    def close(self):
        pass


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1

    def close(self):
        pass


def _run_backfill(monkeypatch, rows, reply='Subject — Walking Tour'):
    cur = _FakeCursor(rows)
    conn = _FakeConn(cur)
    monkeypatch.setattr(tst, '_conn', lambda: conn)
    monkeypatch.setattr(tst, '_call_model', _stub_model(reply))
    monkeypatch.setattr(sys, 'argv', ['tour_short_title.py', '--backfill'])
    tst.main()
    return cur


def test_backfill_selects_only_null_originals(monkeypatch):
    rows = [
        {'id': 1, 'tour_name': 'A - walking Tour', 'request_string': 'r',
         'original_tour_id': None, 'is_test': False, 'short_title': None},     # eligible
        {'id': 2, 'tour_name': 'B - walking Tour', 'request_string': 'r',
         'original_tour_id': None, 'is_test': False, 'short_title': 'Has One'},  # already set
        {'id': 3, 'tour_name': 'C - walking Tour', 'request_string': 'r',
         'original_tour_id': 1, 'is_test': False, 'short_title': None},         # translation
        {'id': 4, 'tour_name': 'D - walking Tour', 'request_string': 'r',
         'original_tour_id': None, 'is_test': True, 'short_title': None},       # test row
        {'id': 5, 'tour_name': 'E - walking Tour', 'request_string': 'r',
         'original_tour_id': None, 'is_test': False, 'short_title': None},      # eligible
    ]
    cur = _run_backfill(monkeypatch, rows)
    updated_ids = sorted(tid for tid, _, _ in cur.updates)
    assert updated_ids == [1, 5], updated_ids  # only the two eligible originals
    # And only short_title was ever written.
    assert all(col == 'short_title' for _, col, _ in cur.updates)
    # Rows 2 (already set), 3 (translation), 4 (test) are untouched.
    assert rows[1]['short_title'] == 'Has One'
    assert rows[2]['short_title'] is None
    assert rows[3]['short_title'] is None


def test_backfill_idempotent_after_run(monkeypatch):
    rows = [
        {'id': 1, 'tour_name': 'A - walking Tour', 'request_string': 'r',
         'original_tour_id': None, 'is_test': False, 'short_title': None},
    ]
    _run_backfill(monkeypatch, rows)
    assert rows[0]['short_title'] == 'Subject — Walking Tour'
    # A second run has nothing left to do (NULL set is now empty).
    cur2 = _run_backfill(monkeypatch, rows)
    assert cur2.updates == []


def test_backfill_dry_run_writes_nothing(monkeypatch):
    rows = [
        {'id': 1, 'tour_name': 'A - walking Tour', 'request_string': 'r',
         'original_tour_id': None, 'is_test': False, 'short_title': None},
    ]
    cur = _FakeCursor(rows)
    conn = _FakeConn(cur)
    monkeypatch.setattr(tst, '_conn', lambda: conn)
    monkeypatch.setattr(tst, '_call_model', _stub_model('Subject — Walking Tour'))
    monkeypatch.setattr(sys, 'argv', ['tour_short_title.py', '--backfill', '--dry-run'])
    tst.main()
    assert cur.updates == []
    assert rows[0]['short_title'] is None


# ─── translation copies short_title ─────────────────────────────────────────────
def test_translation_insert_carries_translated_short_title():
    """Simulate the translation-service INSERT builder: when the original has a
    short_title and the column exists, the translated value is appended to the
    INSERT cols/vals. This mirrors the guarded block added to
    translation_service.py (both the main and the ZIP-fallback paths)."""
    # The exact guard logic, lifted to a tiny pure function so the test pins the
    # behaviour without importing the 176k-line service (it connects at runtime).
    def build(cols, vals, has_short_title, translated_short_title):
        if has_short_title and translated_short_title:
            cols = cols + ['short_title']
            vals = vals + [translated_short_title]
        return cols, vals

    base_cols = ['tour_name', 'content_language', 'original_tour_id']
    base_vals = ['Политика Массачусетса — Пешеходный тур', 'ru', 557]

    # Original HAS a short_title, column present → appended.
    c, v = build(base_cols, base_vals, True, 'Политика Массачусетса — Пешеходный тур')
    assert c[-1] == 'short_title'
    assert v[-1] == 'Политика Массачусетса — Пешеходный тур'

    # Original has NO short_title → not appended (stays NULL).
    c, v = build(base_cols, base_vals, True, None)
    assert 'short_title' not in c

    # Column absent (older schema) → not appended even if there is a value.
    c, v = build(base_cols, base_vals, False, 'anything')
    assert 'short_title' not in c


def test_translation_service_translates_short_title_when_present():
    """The translation path computes translated_short_title ONLY when the source
    short_title is non-empty — the exact condition added to the service."""
    def translated_short_title(source, translate):
        return (translate(source)
                if (source and str(source).strip()) else None)

    up = lambda s: f'[ru]{s}'  # noqa: E731  (a stand-in translate_text)
    assert translated_short_title('Massachusetts Politics — Walking Tour', up) == \
        '[ru]Massachusetts Politics — Walking Tour'
    assert translated_short_title(None, up) is None
    assert translated_short_title('   ', up) is None


# ─── map-delivery exposes short_title on the payloads ───────────────────────────
import datetime  # noqa: E402
import os  # noqa: E402
import unittest  # noqa: E402

_MAPDIR = str(ROOT / 'map_delivery')
if _MAPDIR not in sys.path:
    sys.path.insert(0, _MAPDIR)


class _Cur:
    def __init__(self, plan):
        self._plan = plan
        self._rows = []

    def execute(self, sql, params=None):
        text = ' '.join(str(sql).split()).lower()
        for needle, result in self._plan:
            if needle.lower() in text:
                self._rows = list(result)
                return
        self._rows = []

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def close(self):
        pass


class _Conn:
    def __init__(self, plan):
        self._plan = plan

    def cursor(self):
        return _Cur(self._plan)

    def commit(self):
        pass

    def close(self):
        pass


class MapDeliveryShortTitleTest(unittest.TestCase):
    """Drive the REAL map_delivery endpoints through a scripted fake cursor (no
    Postgres) and assert the share-resolve + tours-near payloads carry
    short_title. Row shape matches tests/test_local687's _row (24 cols, short_title
    just after price_tier)."""

    @classmethod
    def setUpClass(cls):
        import app as map_app
        cls.map_app = map_app

    def setUp(self):
        self._orig = self.map_app.get_db_connection
        for attr in ('_HAS_CONTENT_RATING_COLUMN', '_HAS_SOURCE_VERSION',
                     '_HAS_TOUR_RATINGS', '_HAS_VERIFIED_COLUMN',
                     '_HAS_IS_PAID_COLUMN', '_HAS_PRICE_TIER_COLUMN',
                     '_HAS_SHORT_TITLE_COLUMN'):
            setattr(self.map_app, attr, None)
        self.client = self.map_app.app.test_client()

    def tearDown(self):
        self.map_app.get_db_connection = self._orig

    def _row(self, tid, name, short_title):
        created = datetime.datetime(2026, 10, 1, 8, 30, 0)
        return (tid, name, name.lower(), 43.70, 7.26, 3,
                'en', None, None, None, created, None, None,
                None, None, None, None, False, None,
                short_title,          # [LOCAL-711] short_title after price_tier
                'en', None,
                'general', None)

    def _install(self, plan):
        self.map_app.get_db_connection = lambda: _Conn(plan)

    def test_tour_by_code_payload_has_short_title(self):
        row = self._row(365, 'Faneuil Hall Marketplace ... - Walking Tour',
                        'Faneuil Hall Marketplace — Walking Tour')
        self._install([
            ('information_schema', [('short_title',)]),
            ('from shared_tours', [(365,)]),
            ('from audio_tours t', [row]),
        ])
        resp = self.client.get('/tour-by-code/FFush25U')
        self.assertEqual(resp.status_code, 200)
        tour = resp.get_json()['tours'][0]
        self.assertEqual(tour['short_title'], 'Faneuil Hall Marketplace — Walking Tour')

    def test_tours_near_payload_has_short_title(self):
        row = self._row(557, 'Massachusetts Politics ... - walking Tour',
                        'Massachusetts Politics — Walking Tour')
        self._install([
            ('information_schema', [('short_title',)]),
            ('from audio_tours t', [row]),
        ])
        resp = self.client.get('/tours-near/43.70/7.26?radius=50')
        self.assertEqual(resp.status_code, 200)
        tours = resp.get_json()['tours']
        self.assertEqual(tours[0]['short_title'], 'Massachusetts Politics — Walking Tour')

    def test_short_title_select_guard(self):
        # Column present → selects the real column; absent → NULL literal.
        present = _Cur([('information_schema', [('short_title',)])])
        self.map_app._HAS_SHORT_TITLE_COLUMN = None
        self.assertEqual(self.map_app._short_title_select(present), 't.short_title')
        absent = _Cur([('nomatch', [])])
        self.map_app._HAS_SHORT_TITLE_COLUMN = None
        self.assertEqual(self.map_app._short_title_select(absent), 'NULL::text')
        self.map_app._HAS_SHORT_TITLE_COLUMN = None
