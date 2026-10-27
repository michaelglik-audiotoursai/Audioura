#!/usr/bin/env python3
"""
LOCAL-781 live demo (zero-cost, no containers, no real R2):

Run the REAL tour_id_resolution_service Flask app against
  * an EMPTY /app/tours (TOURS_DIR points at a fresh empty temp dir), and
  * a fake blob store that reports the tour's object present,
with BLOB_STORAGE_TYPE=r2 — exactly the Cloud Run shape — and show
GET /tour/445/resolve -> 200 with the right edit id.

This exercises the same code path a MinIO-backed container would, without
spending anything or touching real R2 credentials. Then it shows the missing-
object case -> clean 404, and the Mac (no BLOB env, disk) case still works.
"""
import os
import sys
import json
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FakeBlob:
    def __init__(self, keys):
        self._keys = set(keys)

    def exists(self, key):
        present = key in self._keys
        print(f"    [fake blob] exists({key!r}) -> {present}")
        return present


class Cur:
    def __init__(self, rows):
        self._rows = list(rows)
        self._i = 0

    def execute(self, *a):
        pass

    def fetchone(self):
        r = self._rows[self._i] if self._i < len(self._rows) else None
        self._i += 1
        return r

    def close(self):
        pass


class Conn:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self):
        return Cur(self._rows)

    def close(self):
        pass

    def commit(self):
        pass


def conn_queue(seq):
    seq = list(seq)
    i = {'n': 0}

    def make():
        n = i['n']
        i['n'] += 1
        return Conn(seq[n] if n < len(seq) else [])
    return make


def show(label, resp):
    print(f"  {label}: HTTP {resp.status_code}")
    print("  body:", json.dumps(resp.get_json(), indent=2))


def main():
    import tour_id_resolution_service as svc

    zip_name = "trinity_church_boston_ma_landmark_a956ce11.zip"

    print("=" * 70)
    print("CASE 1 — Cloud shape: BLOB_STORAGE_TYPE=r2, EMPTY /app/tours, object present")
    print("=" * 70)
    svc._blob_storage = None
    fake = FakeBlob({"tours/445.zip"})
    rows = conn_queue([
        [("Trinity Church",)],                                   # resolve_tour_id tour_name
        [(None, 7)],                                             # organiser check (not organiser)
        [("Trinity Church", zip_name, "tours/445.zip", 7)],      # _resolve_from_column (blob)
    ])
    with tempfile.TemporaryDirectory() as empty_dir:
        print(f"  TOURS_DIR = {empty_dir} (empty: {list(Path(empty_dir).iterdir())})")
        with patch.dict(os.environ, {'BLOB_STORAGE_TYPE': 'r2'}):
            with patch.object(svc, 'get_db_connection', side_effect=rows):
                with patch.object(svc, 'TOURS_DIR', empty_dir):
                    with patch.object(svc, '_get_blob_storage', return_value=fake):
                        resp = svc.app.test_client().get('/tour/445/resolve')
        show("/tour/445/resolve", resp)
        assert resp.status_code == 200 and resp.get_json()['edit_tour_id'] == 'a956ce11'
        print("  => PASS: 200 with edit id a956ce11 from an EMPTY disk\n")

    print("=" * 70)
    print("CASE 2 — Cloud shape, object MISSING from the store -> clean 404")
    print("=" * 70)
    svc._blob_storage = None
    fake_empty = FakeBlob(set())
    rows = conn_queue([
        [("Trinity Church",)],
        [(None, 7)],
        [("Trinity Church", zip_name, "tours/445.zip", 7)],
    ])
    with tempfile.TemporaryDirectory() as empty_dir:
        with patch.dict(os.environ, {'BLOB_STORAGE_TYPE': 'r2'}):
            with patch.object(svc, 'get_db_connection', side_effect=rows):
                with patch.object(svc, 'TOURS_DIR', empty_dir):
                    with patch.object(svc, '_get_blob_storage', return_value=fake_empty):
                        resp = svc.app.test_client().get('/tour/445/resolve')
        show("/tour/445/resolve", resp)
        assert resp.status_code == 404
        print("  => PASS: clean 404 (no misleading name-scan)\n")

    print("=" * 70)
    print("CASE 3 — Mac shape: no BLOB env, ZIP on local disk -> unchanged 200")
    print("=" * 70)
    svc._blob_storage = None
    rows = conn_queue([
        [("Asian Arts Museum, Nice",)],
        [(None, 6)],
        [("Asian Arts Museum, Nice", "asian_arts_museum_nice_a1b2c3d4.zip")],
    ])
    with tempfile.TemporaryDirectory() as tmpdir:
        zp = Path(tmpdir) / "asian_arts_museum_nice_a1b2c3d4.zip"
        with zipfile.ZipFile(zp, 'w') as zf:
            zf.writestr('index.html', '<html></html>')
            for i in range(1, 7):
                zf.writestr(f'audio_{i}.mp3', b'\x00' * (250 * 1024))
        env_no_blob = {k: v for k, v in os.environ.items() if k != 'BLOB_STORAGE_TYPE'}
        with patch.dict(os.environ, env_no_blob, clear=True):
            with patch.object(svc, 'get_db_connection', side_effect=rows):
                with patch.object(svc, 'TOURS_DIR', tmpdir):
                    with patch.object(svc, '_get_blob_storage', return_value=None):
                        resp = svc.app.test_client().get('/tour/100/resolve')
        show("/tour/100/resolve", resp)
        assert resp.status_code == 200 and resp.get_json()['edit_tour_id'] == 'a1b2c3d4'
        print("  => PASS: Mac disk path unchanged\n")

    print("ALL LIVE CASES PASSED")
    return 0


if __name__ == '__main__':
    sys.exit(main())
