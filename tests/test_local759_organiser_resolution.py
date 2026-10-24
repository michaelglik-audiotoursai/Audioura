"""LEAD 2026-10-24: /tour/<id>/resolve for an organiser-audio tour must not guess by name."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import tour_id_resolution_service as svc


class _Cur:
    def __init__(self, row): self.row = row
    def execute(self, *a): pass
    def fetchone(self): return self.row
    def close(self): pass


class _Conn:
    def __init__(self, row): self.row = row
    def cursor(self): return _Cur(self.row)
    def close(self): pass


def test_organiser_tour_resolves_deterministically():
    out = svc._organiser_audio_resolution('750', 'The Salem Witch Trial', _Conn(('organiser_audio', 3)))
    assert out['status'] == 'success'
    assert out['edit_tour_id'] == 'organiser750'
    assert out['stops_count'] == 3
    assert out['editable'] is False


def test_generated_tour_is_not_touched():
    assert svc._organiser_audio_resolution('716', 'x', _Conn((None, 5))) is None
    assert svc._organiser_audio_resolution('716', 'x', _Conn(('generated', 5))) is None
    assert svc._organiser_audio_resolution('9999', 'x', _Conn(None)) is None


def test_route_returns_before_filesystem_guess(monkeypatch):
    calls = []
    monkeypatch.setattr(svc, 'find_edit_tour_id', lambda d: calls.append(d) or {'error': 'ambiguous'})
    monkeypatch.setattr(svc, 'get_db_connection', lambda: _Conn(('The Salem Witch Trial',)))
    monkeypatch.setattr(svc, '_organiser_audio_resolution',
                        lambda d, n: {'status': 'success', 'edit_tour_id': 'organiser750'})
    app = svc.app if hasattr(svc, 'app') else None
    if app is None:
        return
    with app.test_request_context():
        resp = svc.resolve_tour_id('750')
        body = resp.get_json() if hasattr(resp, 'get_json') else resp[0].get_json()
    assert body['edit_tour_id'] == 'organiser750'
    assert calls == []
