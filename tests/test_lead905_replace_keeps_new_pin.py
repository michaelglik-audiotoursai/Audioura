"""[LEAD-905] A regenerated (replaced, D622) tour stores the NEW tour pin; the old one stays only when the new
generation has none. Before: ``lat = COALESCE(lat, %s)`` kept the first run's pin forever (LEAD proof of
a06c8b76: the corrected pin was logged as stored, the row kept the 108 km-off pin)."""
import pathlib
import re

SRC = (pathlib.Path(__file__).resolve().parents[1] / "tour_orchestrator_service.py").read_text()


def _replace_update():
    i = SRC.index("[LOCAL-606] Replaced tour id=")
    j = SRC.rindex("UPDATE audio_tours", 0, i)
    j = SRC.rindex("UPDATE audio_tours\n                        SET tour_content", 0, i)
    return SRC[j:SRC.index("WHERE id = %s", j)]


def test_replace_update_prefers_new_pin():
    sql = _replace_update()
    assert re.search(r"lat\s*=\s*COALESCE\(%s,\s*lat\)", sql)
    assert re.search(r"lng\s*=\s*COALESCE\(%s,\s*lng\)", sql)
    assert "COALESCE(lat, %s)" not in sql and "COALESCE(lng, %s)" not in sql
