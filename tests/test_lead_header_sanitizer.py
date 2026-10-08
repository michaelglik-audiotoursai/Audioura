"""LEAD 2026-10-08: the LOCAL-22 final header sanitizer must keep a real header whose spacing/quotes differ
(Courtauld: 'Stop 3: Manet’s  A Bar at the Folies-Bergère' was stripped as fake → 2 of 3 stops)."""
import re


def _hdr_norm(_x):
    _x = re.sub(r'^Stop\s+\d+:\s*', '', _x or '')
    _x = _x.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    _x = re.sub(r'\s+by\s+.+$', '', _x)
    _x = re.sub(r',\s*\d{3,4}.*$', '', _x)
    return re.sub(r'\s+', ' ', _x).strip().lower()


def test_source_uses_normalised_matching():
    src = open('generate_tour_text.py').read()
    assert '_is_real_header' in src and '_hdr_norm' in src


def test_double_space_curly_header_is_real():
    want = _hdr_norm("Manet's A Bar at the Folies-Bergère")
    got = _hdr_norm("Stop 3: Manet’s  A Bar at the Folies-Bergère")
    assert got == want


def test_fake_header_still_detected():
    want = _hdr_norm("Paul Cézanne")
    assert not _hdr_norm("Stop 2: As you continue on this tour").startswith(want)
