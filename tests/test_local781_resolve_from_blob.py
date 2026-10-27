#!/usr/bin/env python3
"""
LOCAL-781: /resolve must work when the ZIP is in R2 (blob storage), not on the
local disk.

Cloud Run mounts an EMPTY /app/tours; the tour ZIPs live in Cloudflare R2
(BLOB_STORAGE_TYPE=r2, blobstorage.py) — the same layer map_delivery_service.py
reads from. Before this fix, resolve_tour_id() checked Path(TOURS_DIR)/zip_filename,
found nothing on the cloud, fell through to the legacy filesystem scan, and
returned 404 for EVERY download of an existing Subscribed tour
(Michael, TestFlight 79, 2026-10-27; trinity 445 / BPL 446).

The fix: when BLOB_STORAGE_TYPE is set, the existence check uses
blobstorage.exists(tour_blob_uri) and stops_count/editability come from the DB
row — the ZIP is never needed on local disk. The deterministic edit id still
comes from the zip_filename column (LOCAL-50 rule, never guess by name). When
BLOB_STORAGE_TYPE is unset (the Mac stack) behaviour is unchanged: the disk is
the source of truth.

Tests:
1. Blob mode, empty TOURS_DIR, object present in fake store → 200 + right edit id.
2. Blob mode, object MISSING from the store → clear 404 (not an ambiguous-scan).
3. Mac mode (no BLOB env), ZIP on disk → unchanged 200, no blob call.
5. Blob mode carries stops_count / editability from the DB, not from a ZIP read.
"""
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def create_test_zip(directory, filename, num_stops=5):
    zip_path = Path(directory) / filename
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr('index.html', '<html></html>')
        for i in range(1, num_stops + 1):
            zf.writestr(f'audio_{i}.mp3', b'\x00' * (250 * 1024))
            zf.writestr(f'audio_{i}.txt', f'Stop {i} text content')
    return str(zip_path)


class FakeBlobStorage:
    """Stands in for R2BlobStorage. Holds a set of keys that 'exist'."""
    def __init__(self, keys):
        self._keys = set(keys)
        self.exists_calls = []

    def exists(self, key):
        self.exists_calls.append(key)
        return key in self._keys


class MockCursor:
    def __init__(self, results=None):
        self._results = results or []
        self._idx = 0

    def execute(self, *args):
        pass

    def fetchone(self):
        if self._idx < len(self._results):
            result = self._results[self._idx]
            self._idx += 1
            return result
        return None

    def close(self):
        pass


class MockConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def close(self):
        pass

    def commit(self):
        pass


def _conn_queue(rows_per_connection):
    """Return a get_db_connection side_effect that hands out one MockConnection
    per call, each pre-seeded with that call's single fetchone() result.

    resolve_tour_id opens three connections in order:
      1) SELECT tour_name
      2) _organiser_audio_resolution: SELECT source_kind, stops_count
      3) find_edit_tour_id -> _resolve_from_column: SELECT tour_name, zip_filename[, tour_blob_uri, stops_count]
    """
    seq = list(rows_per_connection)
    idx = {'i': 0}

    def _make():
        i = idx['i']
        idx['i'] += 1
        rows = seq[i] if i < len(seq) else []
        return MockConnection(MockCursor(results=rows))

    return _make


def _blob_env():
    """Context manager setting BLOB_STORAGE_TYPE=r2 for the duration."""
    return patch.dict(os.environ, {'BLOB_STORAGE_TYPE': 'r2'})


def _reset_blob_cache(svc):
    """The service caches its blob client in a module global; clear it so each
    test's patched env/mocks take effect cleanly."""
    svc._blob_storage = None


def test_blob_resolution_empty_toursdir():
    """Test 1: Blob mode, empty TOURS_DIR, object in the fake store → 200 + edit id."""
    print("\n=== TEST 1: Blob resolution with empty TOURS_DIR ===")
    zip_name = "trinity_church_boston_ma_landmark_a956ce11.zip"
    fake = FakeBlobStorage(keys={"tours/445.zip"})

    import tour_id_resolution_service as svc
    _reset_blob_cache(svc)

    conns = _conn_queue([
        [("Trinity Church",)],                                    # 1) tour_name
        [(None, 7)],                                              # 2) organiser check (not organiser)
        [("Trinity Church", zip_name, "tours/445.zip", 7)],       # 3) _resolve_from_column (blob)
    ])

    with tempfile.TemporaryDirectory() as empty_dir, _blob_env():
        with patch.object(svc, 'get_db_connection', side_effect=conns):
            with patch.object(svc, 'TOURS_DIR', empty_dir):
                with patch.object(svc, '_get_blob_storage', return_value=fake):
                    client = svc.app.test_client()
                    resp = client.get('/tour/445/resolve')

    data = resp.get_json()
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {data}"
    assert data['status'] == 'success'
    assert data['edit_tour_id'] == 'a956ce11', f"Got {data['edit_tour_id']}"
    assert "tours/445.zip" in fake.exists_calls, \
        f"Existence must be checked in blob store; calls={fake.exists_calls}"
    print(f"  OK 200 edit_tour_id={data['edit_tour_id']} via blob store (empty disk)")
    print("  PASSED")


def test_blob_resolution_missing_object_404():
    """Test 2: Blob mode, object MISSING from the store → clear 404."""
    print("\n=== TEST 2: Blob resolution, missing object -> 404 ===")
    zip_name = "trinity_church_boston_ma_landmark_a956ce11.zip"
    fake = FakeBlobStorage(keys=set())  # object absent

    import tour_id_resolution_service as svc
    _reset_blob_cache(svc)

    conns = _conn_queue([
        [("Trinity Church",)],                                    # 1) tour_name
        [(None, 7)],                                              # 2) organiser check
        [("Trinity Church", zip_name, "tours/445.zip", 7)],       # 3) _resolve_from_column (blob)
    ])

    with tempfile.TemporaryDirectory() as empty_dir, _blob_env():
        with patch.object(svc, 'get_db_connection', side_effect=conns):
            with patch.object(svc, 'TOURS_DIR', empty_dir):
                with patch.object(svc, '_get_blob_storage', return_value=fake):
                    client = svc.app.test_client()
                    resp = client.get('/tour/445/resolve')

    data = resp.get_json()
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {data}"
    assert data['status'] == 'error'
    assert "tours/445.zip" in fake.exists_calls
    print(f"  OK 404 error_code={data.get('error_code')} msg={data.get('message')}")
    print("  PASSED")


def test_mac_mode_disk_unchanged():
    """Test 3: Mac mode (no BLOB env), ZIP on disk → unchanged 200, no blob call."""
    print("\n=== TEST 3: Mac mode (disk) unchanged ===")
    import tour_id_resolution_service as svc
    _reset_blob_cache(svc)
    zip_name = "asian_arts_museum_nice_a1b2c3d4.zip"

    conns = _conn_queue([
        [("Asian Arts Museum, Nice",)],                 # 1) tour_name
        [(None, 6)],                                    # 2) organiser check
        [("Asian Arts Museum, Nice", zip_name)],        # 3) _resolve_from_column (disk, 2-col)
    ])

    sentinel = MagicMock(name="blob_should_not_be_used")
    with tempfile.TemporaryDirectory() as tmpdir:
        create_test_zip(tmpdir, zip_name, num_stops=6)
        env_no_blob = {k: v for k, v in os.environ.items() if k != 'BLOB_STORAGE_TYPE'}
        with patch.dict(os.environ, env_no_blob, clear=True):
            with patch.object(svc, 'get_db_connection', side_effect=conns):
                with patch.object(svc, 'TOURS_DIR', tmpdir):
                    with patch.object(svc, '_get_blob_storage', return_value=None):
                        client = svc.app.test_client()
                        resp = client.get('/tour/100/resolve')

    data = resp.get_json()
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {data}"
    assert data['edit_tour_id'] == 'a1b2c3d4'
    sentinel.exists.assert_not_called()
    print(f"  OK 200 edit_tour_id={data['edit_tour_id']} from disk; blob not touched")
    print("  PASSED")


def test_blob_mode_stops_and_editable_from_db():
    """Test 5: Blob mode carries stops_count and editable from the DB row."""
    print("\n=== TEST 5: stops_count / editable come from DB in blob mode ===")
    zip_name = "boston_public_library_bpl_7f00ba12.zip"
    fake = FakeBlobStorage(keys={"tours/446.zip"})

    import tour_id_resolution_service as svc
    _reset_blob_cache(svc)

    conns = _conn_queue([
        [("Boston Public Library",)],                                # 1) tour_name
        [(None, 9)],                                                 # 2) organiser check
        [("Boston Public Library", zip_name, "tours/446.zip", 9)],   # 3) column row w/ stops_count=9
    ])

    with tempfile.TemporaryDirectory() as empty_dir, _blob_env():
        with patch.object(svc, 'get_db_connection', side_effect=conns):
            with patch.object(svc, 'TOURS_DIR', empty_dir):
                with patch.object(svc, '_get_blob_storage', return_value=fake):
                    client = svc.app.test_client()
                    resp = client.get('/tour/446/resolve')

    data = resp.get_json()
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {data}"
    assert data.get('stops_count') == 9, f"Expected stops_count=9 from DB, got {data.get('stops_count')}"
    assert data['edit_tour_id'] == '7f00ba12'
    print(f"  OK stops_count={data['stops_count']} editable={data['editable']} from DB")
    print("  PASSED")


def run_all_tests():
    print("=" * 70)
    print("LOCAL-781: Resolve from blob storage (R2) tests")
    print("=" * 70)

    tests = [
        test_blob_resolution_empty_toursdir,
        test_blob_resolution_missing_object_404,
        test_mac_mode_disk_unchanged,
        test_blob_mode_stops_and_editable_from_db,
    ]

    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  FAILED: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed, {len(tests)} total")
    print("=" * 70)
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(run_all_tests())
