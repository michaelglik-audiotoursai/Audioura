#!/usr/bin/env python3
"""[LEAD] LOCAL-325: prove the DB target is resolved LAZILY, not at import.

LOCAL-325 shipped tests/test_local325_db_target_isolation.py, but that file
passes whether or not the fix is present: re-baking DEFAULT_DBNAME at import
(the pre-fix behaviour) still gives 12/12 green. A test that cannot fail is
not a test — the same defect LOCAL-322 shipped and LOCAL-324 is fixing.

This file runs the check in a SUBPROCESS, because the property under test is
about import-time versus access-time evaluation and cannot be observed once
db_connection is already imported into the running interpreter.

Verified to bite: with `DEFAULT_DBNAME = _default_dbname()` restored at module
scope, test_target_change_after_import_is_observed FAILS.
"""
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(REPO, 'tests')


def _probe(code: str) -> str:
    """Run a snippet in a clean interpreter and return its last stdout line."""
    r = subprocess.run([sys.executable, '-c', code],
                       capture_output=True, text=True, cwd=REPO, timeout=60)
    out = (r.stdout or '').strip()
    if not out:
        pytest.fail(f"probe produced no stdout; stderr tail:\n{(r.stderr or '')[-600:]}")
    return out.splitlines()[-1]


def test_target_change_after_import_is_observed():
    """Changing AUDIOURA_DB_TARGET AFTER import must change the resolved name.

    This is the regression that matters. Under the pre-fix code the value was
    frozen at first import, so a later change was silently ignored — which is
    how one test module's setting leaked into the whole session.
    """
    got = _probe(
        "import os, sys; sys.path.insert(0, %r);"
        "os.environ['AUDIOURA_DB_TARGET'] = 'test';"
        "import db_connection as d;"
        "assert d.DEFAULT_DBNAME == 'audiotours_test', d.DEFAULT_DBNAME;"
        "os.environ['AUDIOURA_DB_TARGET'] = 'production';"
        "print(d.DEFAULT_DBNAME)" % TESTS
    )
    assert got == 'audiotours', (
        f"DEFAULT_DBNAME stayed {got!r} after the target changed to 'production' "
        "— resolution is happening at import, not on access (LOCAL-325 regressed)"
    )


def test_reverse_direction_also_lazy():
    """Production -> test must be observed too, not just test -> production."""
    got = _probe(
        "import os, sys; sys.path.insert(0, %r);"
        "os.environ['AUDIOURA_DB_TARGET'] = 'production';"
        "import db_connection as d;"
        "assert d.DEFAULT_DBNAME == 'audiotours', d.DEFAULT_DBNAME;"
        "os.environ['AUDIOURA_DB_TARGET'] = 'test';"
        "print(d.DEFAULT_DBNAME)" % TESTS
    )
    assert got == 'audiotours_test', f"stale value {got!r} in the reverse direction"


def test_database_url_is_lazy_too():
    """DEFAULT_DATABASE_URL is built from the dbname and must track it."""
    got = _probe(
        "import os, sys; sys.path.insert(0, %r);"
        "os.environ['AUDIOURA_DB_TARGET'] = 'test';"
        "import db_connection as d;"
        "_ = d.DEFAULT_DATABASE_URL;"
        "os.environ['AUDIOURA_DB_TARGET'] = 'production';"
        "print(d.DEFAULT_DATABASE_URL.rsplit('/', 1)[-1])" % TESTS
    )
    assert got == 'audiotours', f"DEFAULT_DATABASE_URL kept a stale dbname: {got!r}"


def test_invalid_target_is_still_fatal():
    """LOCAL-296: an invalid value must abort, not fall back to a default."""
    r = subprocess.run(
        [sys.executable, '-c',
         "import os, sys; sys.path.insert(0, %r);"
         "os.environ['AUDIOURA_DB_TARGET'] = 'bogus';"
         "import db_connection as d; print(d.DEFAULT_DBNAME)" % TESTS],
        capture_output=True, text=True, cwd=REPO, timeout=60)
    assert r.returncode != 0, f"invalid target did not abort; stdout={r.stdout!r}"


def test_target_outranks_db_name_and_database_url():
    """D214 precedence: AUDIOURA_DB_TARGET wins over DB_NAME and DATABASE_URL."""
    got = _probe(
        "import os, sys; sys.path.insert(0, %r);"
        "os.environ['AUDIOURA_DB_TARGET'] = 'test';"
        "os.environ['DB_NAME'] = 'audiotours';"
        "os.environ['DATABASE_URL'] = 'postgresql://a:b@localhost:5433/audiotours';"
        "import db_connection as d; print(d.DEFAULT_DBNAME)" % TESTS
    )
    assert got == 'audiotours_test', f"precedence broken: got {got!r}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
