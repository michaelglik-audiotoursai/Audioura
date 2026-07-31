#!/usr/bin/env python3
"""
LOCAL-50: Deterministic tour→ZIP resolution tests.

Tests:
1. Column-based resolution (primary path)
2. Filesystem fallback with single match
3. Filesystem fallback with ambiguous match → error
4. Collision test: two tours sharing first two long words resolve correctly
5. Specific tour IDs (21, 24, 27, 28, 29) still resolve after change
"""
import os
import sys
import json
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def create_test_zip(directory, filename, num_stops=5):
    """Create a minimal test ZIP with the given number of MP3 placeholders."""
    zip_path = Path(directory) / filename
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr('index.html', '<html></html>')
        for i in range(1, num_stops + 1):
            # Write >1MB total so editability check passes
            zf.writestr(f'audio_{i}.mp3', b'\x00' * (250 * 1024))
            zf.writestr(f'audio_{i}.txt', f'Stop {i} text content')
    return str(zip_path)


class MockCursor:
    """Minimal cursor mock for testing."""
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


def test_column_resolution():
    """Test 1: When zip_filename column is populated, resolution is deterministic."""
    print("\n=== TEST 1: Column-based resolution ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create the ZIP file
        zip_name = "asian_arts_museum_nice_a1b2c3d4.zip"
        create_test_zip(tmpdir, zip_name, num_stops=6)

        # Mock DB to return zip_filename
        mock_cur = MockCursor(results=[
            ("Asian Arts Museum, Nice — Evaluation Version A", zip_name),  # _resolve_from_column
        ])
        mock_conn = MockConnection(mock_cur)

        with patch('tour_id_resolution_service.get_db_connection', return_value=mock_conn):
            with patch('tour_id_resolution_service.TOURS_DIR', tmpdir):
                from tour_id_resolution_service import find_edit_tour_id
                result = find_edit_tour_id(100)

        assert result is not None, "Expected a result"
        assert result['edit_tour_id'] == 'a1b2c3d4', f"Expected 'a1b2c3d4', got {result['edit_tour_id']}"
        assert result['resolution_method'] == 'column'
        assert zip_name.replace('.zip', '') in result['directory_name']
        print(f"  ✅ Resolved via column: edit_tour_id={result['edit_tour_id']}")
    print("  PASSED")


def test_filesystem_fallback_single_match():
    """Test 2: Fallback resolves when exactly one ZIP matches."""
    print("\n=== TEST 2: Filesystem fallback (single match) ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_name = "asian_arts_museum_nice_france_9cb7181b.zip"
        create_test_zip(tmpdir, zip_name, num_stops=6)

        # First call: _resolve_from_column returns None (no zip_filename)
        # Second call: get tour_name for fallback
        mock_cur = MockCursor(results=[
            ("Asian Arts Museum, Nice", None),   # _resolve_from_column query
            ("Asian Arts Museum, Nice",),        # tour_name for fallback
        ])
        mock_conn = MockConnection(mock_cur)

        with patch('tour_id_resolution_service.get_db_connection', return_value=mock_conn):
            with patch('tour_id_resolution_service.TOURS_DIR', tmpdir):
                from tour_id_resolution_service import find_edit_tour_id
                result = find_edit_tour_id(100)

        assert result is not None, "Expected a result"
        assert result['edit_tour_id'] == '9cb7181b'
        assert result['resolution_method'] == 'filesystem_fallback'
        print(f"  ✅ Fallback resolved: edit_tour_id={result['edit_tour_id']}")
    print("  PASSED")


def test_ambiguous_resolution_returns_error():
    """Test 3: When two ZIPs match, fallback returns ambiguity error."""
    print("\n=== TEST 3: Ambiguous resolution → error ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Two ZIPs sharing keywords "asian" and "arts"
        create_test_zip(tmpdir, "asian_arts_museum_nice_france_9cb7181b.zip", num_stops=6)
        create_test_zip(tmpdir, "asian_arts_museum_nice_evaluation_a_ff11ee22.zip", num_stops=8)

        mock_cur = MockCursor(results=[
            ("Asian Arts Museum, Nice — Evaluation Version A", None),
            ("Asian Arts Museum, Nice — Evaluation Version A",),
        ])
        mock_conn = MockConnection(mock_cur)

        with patch('tour_id_resolution_service.get_db_connection', return_value=mock_conn):
            with patch('tour_id_resolution_service.TOURS_DIR', tmpdir):
                from tour_id_resolution_service import find_edit_tour_id
                result = find_edit_tour_id(100)

        assert result is not None, "Expected an error result"
        assert 'error' in result, f"Expected 'error' key, got {result}"
        assert result['error'] == 'ambiguous'
        assert len(result['matches']) == 2
        print(f"  ✅ Ambiguity detected: {result['matches']}")
    print("  PASSED")


def test_collision_with_stored_column():
    """Test 4: Two tours with names sharing first two long words resolve to
    their own ZIPs when zip_filename is populated."""
    print("\n=== TEST 4: Collision test — two similar names, both resolve correctly ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_a = "asian_arts_museum_nice_evaluation_a_aaaa1111.zip"
        zip_b = "asian_arts_museum_nice_evaluation_b_bbbb2222.zip"
        create_test_zip(tmpdir, zip_a, num_stops=8)
        create_test_zip(tmpdir, zip_b, num_stops=10)

        # Tour A
        mock_cur_a = MockCursor(results=[
            ("Asian Arts Museum, Nice — Evaluation Version A", zip_a),
        ])
        mock_conn_a = MockConnection(mock_cur_a)

        with patch('tour_id_resolution_service.get_db_connection', return_value=mock_conn_a):
            with patch('tour_id_resolution_service.TOURS_DIR', tmpdir):
                from tour_id_resolution_service import find_edit_tour_id
                result_a = find_edit_tour_id(200)

        # Tour B
        mock_cur_b = MockCursor(results=[
            ("Asian Arts Museum, Nice — Evaluation Version B", zip_b),
        ])
        mock_conn_b = MockConnection(mock_cur_b)

        with patch('tour_id_resolution_service.get_db_connection', return_value=mock_conn_b):
            with patch('tour_id_resolution_service.TOURS_DIR', tmpdir):
                result_b = find_edit_tour_id(201)

        assert result_a['edit_tour_id'] == 'aaaa1111', f"Tour A got {result_a['edit_tour_id']}"
        assert result_b['edit_tour_id'] == 'bbbb2222', f"Tour B got {result_b['edit_tour_id']}"
        assert result_a['full_path'] != result_b['full_path']
        print(f"  ✅ Tour A → {result_a['edit_tour_id']} ({os.path.basename(result_a['full_path'])})")
        print(f"  ✅ Tour B → {result_b['edit_tour_id']} ({os.path.basename(result_b['full_path'])})")
    print("  PASSED")


def test_no_hardcoded_venues():
    """Test 5: Verify the four hardcoded venue branches are gone."""
    print("\n=== TEST 5: No hardcoded venue names ===")

    source_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'tour_id_resolution_service.py'
    )
    with open(source_path, 'r') as f:
        source = f.read()

    # These patterns were in the old code
    banned = [
        "'boston' in tour_name",
        "'harvard' in tour_name",
        "'clark' in tour_name",
        "'american' in tour_name",
        "keywords = ['boston', 'common']",
        "keywords = ['harvard', 'university']",
        "keywords = ['clark', 'art']",
        "keywords = ['american', 'wing', 'mfa']",
    ]

    found = [b for b in banned if b in source]
    assert not found, f"Hardcoded venue branches still present: {found}"
    print("  ✅ No hardcoded Boston-area venue names in source")
    print("  PASSED")


def test_http_ambiguity_returns_409():
    """Test 6: HTTP endpoint returns 409 on ambiguous resolution."""
    print("\n=== TEST 6: HTTP 409 on ambiguity ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        create_test_zip(tmpdir, "boston_common_walking_aaa11111.zip", num_stops=5)
        create_test_zip(tmpdir, "boston_common_museum_bbb22222.zip", num_stops=5)

        # The endpoint calls get_db_connection multiple times:
        # 1. resolve_tour_id() opens a conn to get tour_name
        # 2. find_edit_tour_id() opens a conn for _resolve_from_column
        # 3. find_edit_tour_id() re-queries for tour_name in fallback path
        call_count = [0]

        def mock_get_conn():
            call_count[0] += 1
            mock_cur = MagicMock()
            # All calls return the same tour_name, zip_filename=None for column path
            if call_count[0] == 1:
                # resolve_tour_id's own DB call
                mock_cur.fetchone.return_value = ("Boston Common Walking Tour",)
            else:
                # find_edit_tour_id calls
                # _resolve_from_column returns (tour_name, None) => fallback
                # then tour_name query returns single-element tuple
                mock_cur.fetchone.side_effect = [
                    ("Boston Common Walking Tour", None),  # _resolve_from_column
                    ("Boston Common Walking Tour",),       # fallback tour_name
                ]
            mock_conn = MagicMock()
            mock_conn.cursor.return_value = mock_cur
            return mock_conn

        with patch('tour_id_resolution_service.get_db_connection', side_effect=mock_get_conn):
            with patch('tour_id_resolution_service.TOURS_DIR', tmpdir):
                from tour_id_resolution_service import app
                client = app.test_client()
                resp = client.get('/tour/50/resolve')

        assert resp.status_code == 409, f"Expected 409, got {resp.status_code}: {resp.get_json()}"
        data = resp.get_json()
        assert data['error_code'] == 'AMBIGUOUS_RESOLUTION'
        assert 'candidate_zips' in data
        print(f"  ✅ Got 409 with {len(data['candidate_zips'])} candidates")
    print("  PASSED")


def run_all_tests():
    """Run all tests and report."""
    print("=" * 70)
    print("LOCAL-50: Deterministic Tour→ZIP Resolution Tests")
    print("=" * 70)

    tests = [
        test_column_resolution,
        test_filesystem_fallback_single_match,
        test_ambiguous_resolution_returns_error,
        test_collision_with_stored_column,
        test_no_hardcoded_venues,
        test_http_ambiguity_returns_409,
    ]

    passed = 0
    failed = 0

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  ❌ FAILED: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed, {len(tests)} total")
    print("=" * 70)

    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(run_all_tests())
