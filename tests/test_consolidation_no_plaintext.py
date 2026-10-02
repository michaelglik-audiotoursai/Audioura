"""
Tests for LOCAL-321: user_consolidation_service plaintext column removal.

Verifies:
1. get_user_credentials_by_device does NOT read decrypted_username/decrypted_password
2. find_matching_credentials uses blind index, not plaintext WHERE clause
3. Blind index computation is deterministic and non-reversible
4. Graceful degradation when CREDENTIAL_BLIND_INDEX_KEY is absent
"""
import os
import sys
import hmac
import hashlib
import unittest
from unittest.mock import patch, MagicMock

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from user_consolidation_service import (
    UserConsolidationService,
    _compute_credential_blind_index
)


class TestBlindIndex(unittest.TestCase):
    """Tests for the blind index computation."""

    def test_deterministic(self):
        """Same inputs produce the same HMAC."""
        with patch.dict(os.environ, {'CREDENTIAL_BLIND_INDEX_KEY': 'test-key-321'}):
            idx1 = _compute_credential_blind_index('nytimes.com', 'fake_user@example.com', 'F4k3P@ss!')
            idx2 = _compute_credential_blind_index('nytimes.com', 'fake_user@example.com', 'F4k3P@ss!')
            self.assertEqual(idx1, idx2)

    def test_different_password_different_index(self):
        """Different passwords produce different HMACs."""
        with patch.dict(os.environ, {'CREDENTIAL_BLIND_INDEX_KEY': 'test-key-321'}):
            idx1 = _compute_credential_blind_index('nytimes.com', 'fake_user@example.com', 'F4k3P@ss!')
            idx2 = _compute_credential_blind_index('nytimes.com', 'fake_user@example.com', 'DifferentF4k3!')
            self.assertNotEqual(idx1, idx2)

    def test_different_domain_different_index(self):
        """Different domains produce different HMACs."""
        with patch.dict(os.environ, {'CREDENTIAL_BLIND_INDEX_KEY': 'test-key-321'}):
            idx1 = _compute_credential_blind_index('nytimes.com', 'fake_user@example.com', 'F4k3P@ss!')
            idx2 = _compute_credential_blind_index('bostonglobe.com', 'fake_user@example.com', 'F4k3P@ss!')
            self.assertNotEqual(idx1, idx2)

    def test_returns_none_without_key(self):
        """Returns None when CREDENTIAL_BLIND_INDEX_KEY is not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove the key if it exists
            os.environ.pop('CREDENTIAL_BLIND_INDEX_KEY', None)
            idx = _compute_credential_blind_index('nytimes.com', 'fake_user@example.com', 'F4k3P@ss!')
            self.assertIsNone(idx)

    def test_output_is_32_bytes(self):
        """HMAC-SHA256 produces 32 bytes."""
        with patch.dict(os.environ, {'CREDENTIAL_BLIND_INDEX_KEY': 'test-key-321'}):
            idx = _compute_credential_blind_index('nytimes.com', 'fake_user@example.com', 'F4k3P@ss!')
            self.assertEqual(len(idx), 32)


class TestConsolidationNoPlaintext(unittest.TestCase):
    """Tests that consolidation service never reads plaintext columns."""

    def test_find_matching_credentials_no_key_returns_empty(self):
        """Without blind index key, find_matching_credentials returns []."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop('CREDENTIAL_BLIND_INDEX_KEY', None)
            svc = UserConsolidationService()
            result = svc.find_matching_credentials(
                'nytimes.com', 'fake_user@example.com', 'F4k3P@ss!'
            )
            self.assertEqual(result, [])

    @patch('user_consolidation_service.UserConsolidationService.get_db_connection')
    def test_find_matching_uses_blind_index_column(self, mock_conn):
        """find_matching_credentials queries credential_blind_index, not decrypted_*."""
        with patch.dict(os.environ, {'CREDENTIAL_BLIND_INDEX_KEY': 'test-key-321'}):
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_conn.return_value.__enter__ = MagicMock(return_value=mock_conn.return_value)
            mock_conn.return_value.__exit__ = MagicMock(return_value=False)
            mock_conn.return_value.cursor.return_value = mock_cursor

            svc = UserConsolidationService()
            svc.find_matching_credentials('nytimes.com', 'fake_user@example.com', 'F4k3P@ss!')

            # Get the SQL that was executed
            executed_sql = mock_cursor.execute.call_args[0][0]

            # Must NOT contain plaintext column names
            self.assertNotIn('decrypted_username', executed_sql)
            self.assertNotIn('decrypted_password', executed_sql)

            # Must contain blind index column
            self.assertIn('credential_blind_index', executed_sql)

    @patch('credential_store.get_credentials_for_device')
    @patch('user_consolidation_service.UserConsolidationService.get_db_connection')
    def test_get_user_credentials_no_plaintext_sql(self, mock_conn, mock_cred_store):
        """get_user_credentials_by_device does not SELECT decrypted_* columns."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.return_value.__enter__ = MagicMock(return_value=mock_conn.return_value)
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.return_value.cursor.return_value = mock_cursor

        svc = UserConsolidationService()
        svc.get_user_credentials_by_device('test-device-id')

        # Get the SQL that was executed
        executed_sql = mock_cursor.execute.call_args[0][0]

        # Must NOT contain plaintext column names
        self.assertNotIn('decrypted_username', executed_sql)
        self.assertNotIn('decrypted_password', executed_sql)

        # Should filter for encrypted rows
        self.assertIn('wrapped_dek IS NOT NULL', executed_sql)


if __name__ == '__main__':
    unittest.main()
