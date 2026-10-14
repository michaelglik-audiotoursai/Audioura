"""[LOCAL-685] A tour's evaluated score replaces the flat 7.5 prior."""
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tour_rating_service as trs  # noqa: E402
from tour_editor_score import map_to_range  # noqa: E402


def _md():
    """Pull the pure rating helpers out of map_delivery/app.py (it connects to
    Postgres at import)."""
    src = (ROOT / 'map_delivery' / 'app.py').read_text()
    tree = ast.parse(src)
    want = {'_rating_round_1dp', '_rating_median', 'compute_rating', 'rank_score',
            '_is_stale', '_prior_for'}
    consts = {'RATING_DEFAULT_SCORE', 'RATING_MEDIAN_SWITCH_COUNT', 'RANK_PRIOR_COUNT',
              'RANK_PRIOR_SCORE', 'WEIGHT_VERIFIED', 'WEIGHT_UNVERIFIED', 'WEIGHT_STALE',
              'STALE_AFTER_DAYS'}
    body = [n for n in tree.body if
            (isinstance(n, ast.FunctionDef) and n.name in want) or
            (isinstance(n, ast.Assign) and any(getattr(t, 'id', None) in consts for t in n.targets))]
    ns = {'math': __import__('math')}
    exec(compile(ast.Module(body=body, type_ignores=[]), 'app.py', 'exec'), ns)
    return ns


md = _md()


def test_unrated_shows_evaluated_score():
    r = md['compute_rating']([], prior=6.3)
    assert r == {'score': 6.3, 'count': 0, 'label': 'Audioura score'}


def test_unscored_tour_keeps_old_default():
    assert md['compute_rating']([]) == {'score': 7.5, 'count': 0, 'label': 'New'}


def test_first_ratings_blend_with_evaluated_score():
    # mean(6.0, 9) = 7.5
    assert md['compute_rating']([9], prior=6.0)['score'] == 7.5


def test_four_ratings_ignore_prior():
    assert md['compute_rating']([8, 8, 9, 9], prior=5.0)['score'] == 8.5


def test_rank_uses_prior():
    assert md['rank_score']([], prior=5.5) == 5.5
    assert md['rank_score']([]) == 7.5


def test_translation_uses_original_score():
    assert md['_prior_for']({557: 7.8}, 683, 557) == 7.8
    assert md['_prior_for']({557: 7.8}, 557, None) == 7.8
    assert md['_prior_for']({}, 1, None) is None


def test_orchestrator_rule_matches():
    for ratings in ([], [9], [3, 10], [8, 8, 9, 9]):
        a = trs.compute_score(ratings, prior=6.2)
        b = md['compute_rating'](ratings, prior=6.2)
        assert a == b


def test_map_to_range_bounds():
    assert map_to_range(1) == 5.0
    assert map_to_range(10) == 8.0
    assert 5.0 < map_to_range(6.5) < 8.0
