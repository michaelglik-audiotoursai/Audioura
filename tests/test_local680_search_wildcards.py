"""[LOCAL-680] '*' anchors the tour-name search; no '*' means contains."""
import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parent.parent / 'map_delivery' / 'app.py'


def _load():
    # app.py connects to Postgres at import; lift just the pure helper out of it.
    tree = ast.parse(SRC.read_text())
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == '_search_like_pattern')
    ns = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(SRC), 'exec'), ns)
    return ns['_search_like_pattern']


f = _load()


def test_no_star_is_contains():
    assert f('Boston') == '%Boston%'


def test_trailing_star_is_starts_with():
    assert f('Boston*') == 'Boston%'
    assert f('Boston.*') == 'Boston%'   # the app sends '*' as '.*'


def test_leading_star_is_ends_with():
    assert f('*Tour') == '%Tour'


def test_both_stars_is_contains():
    assert f('*Boston*') == '%Boston%'
    assert f('.*Boston.*') == '%Boston%'


def test_inner_star():
    assert f('walking*tour') == 'walking%tour'


def test_sql_wildcards_are_literal():
    assert f('100%') == '%100\\%%'
    assert f('a_b*') == 'a\\_b%'


def test_dot_without_star_is_literal():
    assert f('St. Louis') == '%St. Louis%'
