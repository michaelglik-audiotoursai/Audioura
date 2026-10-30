"""LEAD 2026-10-30: PHASE 3A died on a live gpt-4.1-mini reply containing '"address":: "..."'
(Hoan Kiem walk on the Mac, 'no stops could be generated'). The loose parser must repair it."""
import json, os, re, textwrap

ROOT = os.path.join(os.path.dirname(__file__), '..')
SRC = open(os.path.join(ROOT, 'generate_tour_text.py'), encoding='utf-8').read()


def _load_parser():
    m = re.search(r"\n(    def _parse_json_array_loose\(text\):\n.*?)\n    def _normalize_name", SRC, re.DOTALL)
    assert m, "parser not found"
    ns = {'re': re, 'json': json}
    exec(textwrap.dedent(m.group(1)), ns)
    return ns['_parse_json_array_loose']


parse = _load_parser()


def test_live_double_colon_reply_parses():
    text = open(os.path.join(os.path.dirname(__file__), 'fixtures', 'lead_json', 'phase3a_double_colon.txt'), encoding='utf-8').read()
    assert '"address"::' in text
    out = parse(text)
    assert isinstance(out, list) and len(out) == 5
    assert out[0]['name'].startswith('Ng')


def test_trailing_comma_and_valid_input_unchanged():
    assert parse('[{"name": "A"}, {"name": "B"},]') == [{"name": "A"}, {"name": "B"}]
    assert parse('[{"name": "A"}]') == [{"name": "A"}]


def test_salvage_valid_objects_when_one_is_broken():
    out = parse('[{"name": "A"}, {"name": "B", "x": }, {"name": "C"}]')
    assert [o['name'] for o in out] == ['A', 'C']


def test_garbage_still_none():
    assert parse('I cannot help with that') is None
