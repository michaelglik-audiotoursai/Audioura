#!/usr/bin/env python3
"""LOCAL-325: Prove per-module DB target isolation within a single pytest session.

This test would have caught the bug where module-scope os.environ assignments
leaked AUDIOURA_DB_TARGET across test files. Two classes simulate two modules
requesting different targets — each must get its own database, regardless of
collection order.

The fix: db_connection resolves AUDIOURA_DB_TARGET at connection time (lazy),
not at import time. Combined with autouse fixtures, this makes monkeypatch
effective per-module.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_connection import get_db_config, get_database_url


class TestModuleWantsTest:
    """Simulates a test module that targets the test database."""

    @pytest.fixture(autouse=True)
    def _target_test(self, monkeypatch):
        monkeypatch.setenv('AUDIOURA_DB_TARGET', 'test')
        yield

    def test_resolves_to_test_db(self):
        config = get_db_config()
        assert config['dbname'] == 'audiotours_test', (
            f"Expected audiotours_test, got {config['dbname']}"
        )

    def test_url_contains_test_db(self):
        url = get_database_url()
        assert '/audiotours_test' in url, (
            f"Expected audiotours_test in URL, got: {url}"
        )


class TestModuleWantsProduction:
    """Simulates a test module that targets production (read-only)."""

    @pytest.fixture(autouse=True)
    def _target_production(self, monkeypatch):
        monkeypatch.setenv('AUDIOURA_DB_TARGET', 'production')
        yield

    def test_resolves_to_production_db(self):
        config = get_db_config()
        assert config['dbname'] == 'audiotours', (
            f"Expected audiotours, got {config['dbname']}"
        )

    def test_url_contains_production_db(self):
        url = get_database_url()
        assert url.endswith('/audiotours'), (
            f"Expected URL ending with /audiotours, got: {url}"
        )
        assert '/audiotours_test' not in url, (
            f"Got test DB unexpectedly: {url}"
        )


class TestIsolationWithinSession:
    """Prove that switching targets within one session works correctly.

    Each test sets a different target and verifies the resolved database.
    If resolution were import-time (the old bug), one of these would fail.
    """

    def test_first_test_targets_test(self, monkeypatch):
        monkeypatch.setenv('AUDIOURA_DB_TARGET', 'test')
        config = get_db_config()
        assert config['dbname'] == 'audiotours_test'

    def test_second_test_targets_production(self, monkeypatch):
        monkeypatch.setenv('AUDIOURA_DB_TARGET', 'production')
        config = get_db_config()
        assert config['dbname'] == 'audiotours'

    def test_third_test_targets_test_again(self, monkeypatch):
        monkeypatch.setenv('AUDIOURA_DB_TARGET', 'test')
        config = get_db_config()
        assert config['dbname'] == 'audiotours_test'

    def test_fourth_unset_defaults_to_test_under_pytest(self, monkeypatch):
        monkeypatch.delenv('AUDIOURA_DB_TARGET', raising=False)
        monkeypatch.delenv('DB_NAME', raising=False)
        config = get_db_config()
        # Under pytest with no explicit target, _is_pytest() routes to test DB
        assert config['dbname'] == 'audiotours_test'


class TestInvalidTargetStillFatal:
    """Invalid AUDIOURA_DB_TARGET must still cause a fatal exit at resolution time."""

    def test_invalid_target_exits(self, monkeypatch):
        monkeypatch.setenv('AUDIOURA_DB_TARGET', 'bogus')
        with pytest.raises(SystemExit) as exc_info:
            get_database_url()
        assert exc_info.value.code == 1

    def test_empty_target_exits(self, monkeypatch):
        monkeypatch.setenv('AUDIOURA_DB_TARGET', '')
        with pytest.raises(SystemExit) as exc_info:
            get_database_url()
        assert exc_info.value.code == 1


class TestPrecedencePreserved:
    """D214: AUDIOURA_DB_TARGET outranks DATABASE_URL and DB_NAME."""

    def test_target_overrides_database_url(self, monkeypatch):
        monkeypatch.setenv('AUDIOURA_DB_TARGET', 'test')
        monkeypatch.setenv('DATABASE_URL', 'postgresql://x:y@h:1/wrong_db')
        url = get_database_url()
        assert '/audiotours_test' in url, (
            f"AUDIOURA_DB_TARGET=test should override DATABASE_URL, got: {url}"
        )

    def test_target_overrides_db_name(self, monkeypatch):
        monkeypatch.setenv('AUDIOURA_DB_TARGET', 'test')
        monkeypatch.setenv('DB_NAME', 'wrong_db')
        config = get_db_config()
        # get_db_config uses DB_NAME directly, but get_database_url overrides it.
        # The precedence is in get_database_url, not get_db_config.
        url = get_database_url()
        assert '/audiotours_test' in url, (
            f"AUDIOURA_DB_TARGET=test should override DB_NAME, got: {url}"
        )
