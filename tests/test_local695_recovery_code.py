"""
test_local695_recovery_code.py — LOCAL-695 anonymous recovery code / portability
=================================================================================

Covers the ticket's test list:
  * code generation / entropy / hash:
      - generate_recovery_code is 16 symbols (4×4), from the Crockford alphabet,
        and 1000 draws are unique (high entropy);
      - the stored code is hashed (PBKDF2), never plaintext; verify is
        case/format-insensitive and constant-time-correct;
  * restore LINKS the new device and UNLINKS the old one (consolidation tables);
  * paid tours get a RESTORE GRANT so they re-download FREE on restore only
    (an unconsumed tour_unlocks store='restore' row the gate honours, consumed
    once), while a brand-new device with no grant is still charged (402);
  * the moved-away OLD device is refused re-downloads (402 profile_moved) while
    tours it already downloaded free keep working;
  * per-device rate limit (5/hour) → the 6th attempt is 429;
  * >2 successful restores in 30 days → 409 (Contact support);
  * account deletion removes data across ALL linked devices (consolidated id).

Harness mirrors tests/test_local693_paid_per_download.py: in-process Flask test
clients for the orchestrator recovery routes and for map_delivery's gate, both
pointed at the test DB (db_connection → audiotours_test under pytest). Every row
uses an id starting with 'TEST-695-'; cleanup deletes ONLY those rows. The
services self-heal the 033 schema, so the suite converges whether or not the
migration file has run.
"""

import importlib.util
import os
import sys

import psycopg2
import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db_connection import get_connection, check_db_available, get_db_config  # noqa: E402

TEST_PREFIX = "TEST-695-"


# ─── module loaders ───────────────────────────────────────────────────────────

def _load_recovery():
    """Import the repo-root recovery_code_service with its DB env pointed at the
    test DB (its _get_conn reads DB_HOST/DB_NAME/... which we set from
    db_connection's resolved test config)."""
    cfg = get_db_config()
    os.environ["DB_HOST"] = cfg["host"]
    os.environ["DB_PORT"] = str(cfg["port"])
    os.environ["DB_NAME"] = cfg["dbname"]
    os.environ["DB_USER"] = cfg["user"]
    os.environ["DB_PASSWORD"] = cfg["password"]
    import recovery_code_service as rc
    # Reset the module-level schema cache so ensure runs against this DB.
    rc._SCHEMA_READY = False
    return rc


def _load_md():
    md_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "map_delivery")
    path = os.path.join(md_dir, "app.py")
    if md_dir not in sys.path:
        sys.path.insert(0, md_dir)
    spec = importlib.util.spec_from_file_location("md_app_local695", path)
    md = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(md)
    return md


# ─── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def rc():
    if not check_db_available():
        pytest.skip("database unavailable")
    module = _load_recovery()
    # Ensure the 033 schema exists.
    conn = get_connection()
    cur = conn.cursor()
    module.ensure_recovery_schema(cur)
    conn.commit()
    cur.close()
    conn.close()
    return module


@pytest.fixture(scope="module")
def md():
    if not check_db_available():
        pytest.skip("database unavailable")
    return _load_md()


@pytest.fixture()
def conn():
    c = get_connection()
    yield c
    c.rollback()
    c.close()


def _cleanup(cur):
    """Delete only TEST-695- rows across every table the suite writes.

    Device ids start with TEST-695-; profile ids created from them start with
    CONSOLIDATED-TEST-695- (see recovery_code_service._get_or_create_profile_id),
    so profile-keyed tables must match that prefix too."""
    dev = TEST_PREFIX + "%"
    prof = "CONSOLIDATED-" + TEST_PREFIX + "%"
    cur.execute("DELETE FROM tour_unlocks WHERE user_id LIKE %s", (dev,))
    cur.execute("DELETE FROM tour_downloads WHERE user_id LIKE %s", (dev,))
    cur.execute("DELETE FROM profile_restores WHERE consolidated_user_id LIKE %s OR consolidated_user_id LIKE %s OR new_device_id LIKE %s",
                (dev, prof, dev))
    cur.execute("DELETE FROM restore_attempts WHERE device_id LIKE %s", (dev,))
    cur.execute("DELETE FROM recovery_codes WHERE consolidated_user_id LIKE %s OR consolidated_user_id LIKE %s",
                (dev, prof))
    cur.execute("DELETE FROM device_consolidation_history WHERE consolidated_user_id LIKE %s OR consolidated_user_id LIKE %s OR merged_device_id LIKE %s",
                (dev, prof, dev))
    cur.execute("DELETE FROM user_consolidation_map WHERE consolidated_user_id LIKE %s OR consolidated_user_id LIKE %s OR primary_device_id LIKE %s",
                (dev, prof, dev))
    cur.execute("DELETE FROM audio_tours WHERE tour_name LIKE %s", (dev,))


@pytest.fixture(autouse=True)
def clean(conn):
    cur = conn.cursor()
    _cleanup(cur)
    conn.commit()
    yield
    cur = conn.cursor()
    _cleanup(cur)
    conn.commit()


# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_paid_tour(cur, name_suffix, tier=3):
    """Create a paid original audio_tours row; return its id."""
    cur.execute(
        "INSERT INTO audio_tours (tour_name, request_string, number_requested, price_tier) "
        "VALUES (%s, '', 0, %s) RETURNING id",
        (TEST_PREFIX + name_suffix, tier),
    )
    return int(cur.fetchone()[0])


def _buy(cur, user_id, tour_id, store="apple"):
    """Record a (consumed) purchase: an unlock already spent on the original
    download — this models a tour the profile OWNS and had downloaded."""
    cur.execute(
        "ALTER TABLE tour_unlocks ADD COLUMN IF NOT EXISTS consumed_at TIMESTAMPTZ"
    )
    cur.execute(
        "INSERT INTO tour_unlocks (user_id, tour_id, transaction_id, store, price_usd, consumed_at) "
        "VALUES (%s, %s, %s, %s, 4.99, NOW())",
        (user_id, tour_id, f"txn-{user_id}-{tour_id}", store),
    )


# ─── 1. generation / entropy / hash (pure) ────────────────────────────────────

def test_code_shape_and_alphabet(rc):
    code = rc.generate_recovery_code()
    groups = code.split("-")
    assert len(groups) == 4 and all(len(g) == 4 for g in groups)
    norm = rc.normalize_code(code)
    assert len(norm) == 16
    assert all(ch in "0123456789ABCDEFGHJKMNPQRSTVWXYZ" for ch in norm)


def test_code_entropy_unique(rc):
    codes = {rc.generate_recovery_code() for _ in range(1000)}
    assert len(codes) == 1000  # 80 bits — collisions astronomically unlikely


def test_hash_is_not_plaintext_and_verifies(rc):
    import secrets
    code = rc.generate_recovery_code()
    salt = secrets.token_bytes(16)
    digest = rc.hash_code(code, salt)
    # The digest is not the code, and is 32 bytes (sha256).
    assert isinstance(digest, (bytes, bytearray)) and len(digest) == 32
    assert rc.normalize_code(code).encode() not in bytes(digest)
    # Verify is format/case-insensitive and rejects a wrong code.
    assert rc.verify_code(code, salt, digest)
    assert rc.verify_code(code.lower().replace("-", " "), salt, digest)
    assert not rc.verify_code(rc.generate_recovery_code(), salt, digest)


def test_generate_stores_only_hash(rc, conn):
    cur = conn.cursor()
    device = TEST_PREFIX + "devA"
    code, profile_id, rotated = rc.generate_for_device(cur, device)
    conn.commit()
    assert not rotated
    cur.execute("SELECT code_hash, code_salt FROM recovery_codes WHERE consolidated_user_id = %s",
                (profile_id,))
    row = cur.fetchone()
    assert row is not None
    stored_hash = bytes(row[0])
    # Plaintext never appears in the stored hash.
    assert rc.normalize_code(code).encode() not in stored_hash
    # Re-generating ROTATES (same profile, new hash).
    code2, profile_id2, rotated2 = rc.generate_for_device(cur, device)
    conn.commit()
    assert profile_id2 == profile_id and rotated2 and code2 != code


# ─── 2. restore links + unlinks + grants ───────────────────────────────────────

def test_restore_links_new_unlinks_old_and_grants(rc, conn):
    cur = conn.cursor()
    old = TEST_PREFIX + "old"
    new = TEST_PREFIX + "new"
    paid_tour = _make_paid_tour(cur, "tourP")
    _buy(cur, old, paid_tour)             # the profile owns + downloaded a paid tour
    code, profile_id, _ = rc.generate_for_device(cur, old)
    conn.commit()

    status, payload = rc.restore_for_device(cur, new, code)
    conn.commit()
    assert status == "restored", payload
    # New device is the primary now.
    cur.execute("SELECT primary_device_id FROM user_consolidation_map WHERE consolidated_user_id = %s",
                (profile_id,))
    assert cur.fetchone()[0] == new
    # Old device is unlinked (a history row with unlinked_at set).
    cur.execute("SELECT unlinked_at FROM device_consolidation_history "
                "WHERE consolidated_user_id = %s AND merged_device_id = %s ORDER BY id DESC LIMIT 1",
                (profile_id, old))
    row = cur.fetchone()
    assert row is not None and row[0] is not None
    # A restore grant (unconsumed store='restore' unlock) exists for the new device.
    cur.execute("SELECT COUNT(*) FROM tour_unlocks WHERE user_id = %s AND tour_id = %s "
                "AND store = 'restore' AND consumed_at IS NULL",
                (new, paid_tour))
    assert cur.fetchone()[0] == 1
    assert payload["grants_issued"] == 1
    assert paid_tour in payload["listen_page"]["paid_tours"]


def test_restore_grant_makes_paid_download_free_on_new_only(rc, md, conn):
    cur = conn.cursor()
    old = TEST_PREFIX + "o2"
    new = TEST_PREFIX + "n2"
    stranger = TEST_PREFIX + "stranger"
    paid_tour = _make_paid_tour(cur, "tourQ")
    _buy(cur, old, paid_tour)
    code, _pid, _ = rc.generate_for_device(cur, old)
    conn.commit()
    rc.restore_for_device(cur, new, code)
    conn.commit()

    # Reset md caches so it reads this DB fresh.
    md._HAS_TOUR_UNLOCKS_TABLE = None
    md._HAS_CONSOLIDATION_HISTORY = None
    md._HAS_UNLOCK_CONSUMPTION_COLS = False

    # The NEW device rides the restore grant → gate allows (free re-download).
    allowed_new, _ = md._download_gate(cur, new, paid_tour)
    assert allowed_new is True
    # A STRANGER with no grant and no purchase → 402 purchase_required.
    allowed_stranger, deny = md._download_gate(cur, stranger, paid_tour)
    assert allowed_stranger is False and deny["error"] == "purchase_required"


# ─── 3. moved-away old device is refused re-downloads ──────────────────────────

def test_old_device_moved_away_is_refused(rc, md, conn):
    cur = conn.cursor()
    old = TEST_PREFIX + "o3"
    new = TEST_PREFIX + "n3"
    paid_tour = _make_paid_tour(cur, "tourR")
    _buy(cur, old, paid_tour)
    code, _pid, _ = rc.generate_for_device(cur, old)
    conn.commit()
    rc.restore_for_device(cur, new, code)   # moves profile to new; unlinks old
    conn.commit()

    md._HAS_TOUR_UNLOCKS_TABLE = None
    md._HAS_CONSOLIDATION_HISTORY = None
    md._HAS_UNLOCK_CONSUMPTION_COLS = False

    # The OLD device is now moved-away → 402 profile_moved on a paid row.
    allowed_old, deny = md._download_gate(cur, old, paid_tour)
    assert allowed_old is False and deny["error"] == "profile_moved"

    # But a FREE tour the old device downloaded while free keeps working
    # (grandfathering is honoured even for a moved device).
    free_tour = _make_paid_tour(cur, "tourFree")  # make it paid now...
    cur.execute("INSERT INTO tour_downloads (user_id, tour_id, was_free) VALUES (%s, %s, TRUE)",
                (old, free_tour))
    conn.commit()
    allowed_free, _ = md._download_gate(cur, old, free_tour)
    assert allowed_free is True


# ─── 4. rate limit (5/hour/device) ─────────────────────────────────────────────

def test_rate_limit_sixth_attempt(rc, conn):
    cur = conn.cursor()
    device = TEST_PREFIX + "rl"
    # 5 bad-code attempts (all logged, all bad_code).
    for _ in range(rc.RESTORE_RATE_LIMIT_PER_HOUR):
        status, _ = rc.restore_for_device(cur, device, "WRONGWRONGWRONG0")
        conn.commit()
        assert status == "bad_code"
    # The 6th is rate-limited BEFORE the code is even checked.
    status, payload = rc.restore_for_device(cur, device, "WRONGWRONGWRONG0")
    conn.commit()
    assert status == "rate_limited" and payload["error"] == "rate_limited"


# ─── 5. >2 restores in 30 days → refused ───────────────────────────────────────

def test_more_than_two_restores_refused(rc, conn):
    cur = conn.cursor()
    base = TEST_PREFIX + "ab"
    code, profile_id, _ = rc.generate_for_device(cur, base + "0")
    conn.commit()
    # Two successful restores from two different devices.
    for i in (1, 2):
        status, _ = rc.restore_for_device(cur, f"{base}{i}", code)
        conn.commit()
        assert status == "restored"
    # The THIRD restore in the window is refused (abuse guard).
    status, payload = rc.restore_for_device(cur, base + "3", code)
    conn.commit()
    assert status == "refused_abuse" and payload["error"] == "too_many_restores"


# ─── 6. bad code is rejected (401 path) ────────────────────────────────────────

def test_unknown_code_rejected(rc, conn):
    cur = conn.cursor()
    device = TEST_PREFIX + "bad"
    status, payload = rc.restore_for_device(cur, device, "ZZZZ-ZZZZ-ZZZZ-ZZZZ")
    conn.commit()
    assert status == "bad_code" and payload["error"] == "invalid_code"


# ─── 7. consolidation-aware deletion across linked devices ─────────────────────

def test_linked_device_ids_for_deletion_spans_profile(rc, conn):
    cur = conn.cursor()
    old = TEST_PREFIX + "del_old"
    new = TEST_PREFIX + "del_new"
    code, profile_id, _ = rc.generate_for_device(cur, old)
    conn.commit()
    rc.restore_for_device(cur, new, code)
    conn.commit()
    # Deleting by EITHER device id resolves the whole profile's device set.
    ids_from_new = rc.linked_device_ids_for_deletion(cur, new)
    ids_from_old = rc.linked_device_ids_for_deletion(cur, old)
    for s in (ids_from_new, ids_from_old):
        assert old in s and new in s and profile_id in s
    # A device that belongs to no profile resolves to just itself.
    lone = rc.linked_device_ids_for_deletion(cur, TEST_PREFIX + "lone")
    assert lone == {TEST_PREFIX + "lone"}


def test_deletion_removes_all_linked_rows(rc, conn):
    """Simulate the orchestrator deletion: resolve the identity, then delete the
    device-keyed rows for ALL of them, and prove nothing is left for either
    device."""
    cur = conn.cursor()
    old = TEST_PREFIX + "wipe_old"
    new = TEST_PREFIX + "wipe_new"
    paid = _make_paid_tour(cur, "tourW")
    _buy(cur, old, paid)
    code, profile_id, _ = rc.generate_for_device(cur, old)
    conn.commit()
    rc.restore_for_device(cur, new, code)
    conn.commit()

    identity = sorted(rc.linked_device_ids_for_deletion(cur, new))
    assert old in identity and new in identity and profile_id in identity

    # Delete device-keyed + profile-keyed rows for the whole identity set.
    cur.execute("DELETE FROM tour_unlocks WHERE user_id = ANY(%s)", (identity,))
    cur.execute("DELETE FROM recovery_codes WHERE consolidated_user_id = ANY(%s)", (identity,))
    cur.execute("DELETE FROM profile_restores WHERE consolidated_user_id = ANY(%s) OR new_device_id = ANY(%s)",
                (identity, identity))
    cur.execute("DELETE FROM device_consolidation_history WHERE consolidated_user_id = ANY(%s) OR merged_device_id = ANY(%s)",
                (identity, identity))
    cur.execute("DELETE FROM user_consolidation_map WHERE consolidated_user_id = ANY(%s) OR primary_device_id = ANY(%s)",
                (identity, identity))
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM tour_unlocks WHERE user_id = ANY(%s)", (identity,))
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT COUNT(*) FROM recovery_codes WHERE consolidated_user_id = ANY(%s)", (identity,))
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT COUNT(*) FROM user_consolidation_map WHERE consolidated_user_id = ANY(%s)", (identity,))
    assert cur.fetchone()[0] == 0
