#!/usr/bin/env python3
"""LOCAL-882 — a cached Wikipedia-evidence hit is RE-VALIDATED against the current
acceptance rules, and carries a RULES_VERSION so a rule change retires old rows
without any DELETE. Fully offline: a tiny in-memory fake DB stands in for postgres.

The wave-40 leak this guards: the Gia Long Palace article, cached for the "City
Hall" pin in waves 36-39 (before LOCAL-881's dense-centre rule), was returned on a
cache HIT without re-running _pick, so the City Hall stop shipped the Gia Long
Palace again. Here the stale row is ignored (version mismatch) AND its payload is
rejected by the current name rule (title shares no distinctive token with the
stop), so a repeat read re-fetches instead of serving the stale article.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import landmark_wikipedia_evidence as lw  # noqa: E402


# ── a minimal in-memory stand-in for the postgres connection ──────────────────
class _FakeCursor:
    def __init__(self, store):
        self._store = store
        self._result = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        s = " ".join(sql.split()).lower()
        if s.startswith("create table") or s.startswith("alter table"):
            self._result = None
            return
        if s.startswith("select"):
            key = params[0]
            row = self._store.get(key)
            # row is (payload, found, expires_at, rules_version); honour expiry
            if row and row[2] > 0:
                self._result = (row[0], row[1], row[3])
            else:
                self._result = None
            return
        if s.startswith("insert into"):
            # (cache_key, name, language, payload, found, expires_at, rules_version)
            key = params[0]
            payload, found, rules_version = params[3], params[4], params[6]
            self._store[key] = (payload, found, 1, rules_version)
            return

    def fetchone(self):
        return self._result


class _FakeConn:
    def __init__(self, store):
        self._store = store

    def cursor(self):
        return _FakeCursor(self._store)

    def commit(self):
        pass


def _install_fake_db(monkeypatch_store):
    lw._TABLE_OK = False
    lw._conn = lambda: _FakeConn(monkeypatch_store)  # type: ignore


def _seed_row(store, name, lang, pin, art, rules_version):
    """Write a row the way an OLD/other run would have (direct, bypassing _cache_put)."""
    key = lw._key(name, lang, pin)
    import json
    store[key] = (json.dumps(art) if art else None, bool(art), 1, rules_version)


CITY = "Ho Chi Minh City"
CITY_HALL_PIN = (10.776470, 106.700970)


def test_stale_version_row_is_a_miss():
    store = {}
    _install_fake_db(store)
    # a GOOD article for City Hall, but stamped with an OLD rules_version.
    good = {"title": "Ho Chi Minh City Hall", "lead": "...", "infobox": ""}
    _seed_row(store, "City Hall", "en", CITY_HALL_PIN, good, "pre-local882")
    got = lw._cache_get("City Hall", "en", CITY_HALL_PIN, city=CITY, match_name="City Hall")
    assert got is None, "a row from an older rule set must be treated as a miss"


def test_current_version_valid_row_is_a_hit():
    store = {}
    _install_fake_db(store)
    good = {"title": "Ho Chi Minh City Hall", "lead": "The Ho Chi Minh City Hall ...",
            "infobox": ""}
    _seed_row(store, "City Hall", "en", CITY_HALL_PIN, good, lw.RULES_VERSION)
    got = lw._cache_get("City Hall", "en", CITY_HALL_PIN, city=CITY, match_name="City Hall")
    assert got == (True, good), "a current-version, still-valid row must be served"


def test_gia_long_palace_payload_rejected_for_city_hall():
    store = {}
    _install_fake_db(store)
    # the wave-40 poison: Gia Long Palace cached for the City Hall pin, even if it
    # somehow carried the CURRENT version — the payload re-check must reject it
    # because its title shares no distinctive token with the City Hall stop.
    poison = {"title": "Gia Long Palace", "lead": "The Gia Long Palace is a building "
              "in Ho Chi Minh City ...", "infobox": ""}
    _seed_row(store, "City Hall", "en", CITY_HALL_PIN, poison, lw.RULES_VERSION)
    got = lw._cache_get("City Hall", "en", CITY_HALL_PIN, city=CITY,
                        match_name="Ho Chi Minh City Hall")
    assert got is None, "a cached article the current rules would not pick must be a miss"


def test_revalidate_payload_direct():
    # name-matching title: accepted.
    assert lw._revalidate_payload(
        {"title": "Saigon Opera House", "lead": "", "infobox": ""},
        "Saigon Opera House", pin=(10.77639, 106.70278), city=CITY,
        match_name="Opera House")
    # Gia Long Palace for a City Hall stop in a dense centre: rejected (no shared
    # distinctive token, and the 300 m half needs a coordinate the payload lacks).
    assert not lw._revalidate_payload(
        {"title": "Gia Long Palace", "lead": "The Gia Long Palace ...", "infobox": ""},
        "Ho Chi Minh City Hall", pin=CITY_HALL_PIN, city=CITY,
        match_name="Ho Chi Minh City Hall")
    # a lead alias counts as a name match, and when the stop name has NO
    # distinctive token of its own (bare "Opera House" after city + kind words are
    # dropped) the shared-token sub-condition is vacuous, so the stored coord's
    # 300 m check alone decides — exactly as _pick does on the city-qualified
    # retry. Here the coord is at the Opera House pin, so it is accepted.
    assert lw._revalidate_payload(
        {"title": "Municipal Theatre", "lead": "The Municipal Theatre, also the "
         "Saigon Opera House, is ...", "infobox": "", "coord": [10.77639, 106.70278]},
        "Opera House", pin=(10.77639, 106.70278), city=CITY,
        match_name="Opera House")
    # the SAME lead-alias article but pinned 5 km away (a different-city namesake):
    # the stored coord makes the 300 m check fail, so it is rejected.
    assert not lw._revalidate_payload(
        {"title": "Municipal Theatre", "lead": "The Municipal Theatre, also the "
         "Saigon Opera House, is ...", "infobox": "", "coord": [10.82, 106.75]},
        "Opera House", pin=(10.77639, 106.70278), city=CITY,
        match_name="Opera House")
    # an empty/negative payload is trivially valid.
    assert lw._revalidate_payload(None, "anything")


def test_put_then_get_roundtrip_stamps_current_version():
    store = {}
    _install_fake_db(store)
    art = {"title": "War Remnants Museum", "lead": "The War Remnants Museum ...",
           "infobox": ""}
    lw._cache_put("War Remnants Museum", "en", art, (10.7795, 106.692))
    got = lw._cache_get("War Remnants Museum", "en", (10.7795, 106.692),
                        city=CITY, match_name="War Remnants Museum")
    assert got == (True, art)
    # the stored row carries the current RULES_VERSION.
    key = lw._key("War Remnants Museum", "en", (10.7795, 106.692))
    assert store[key][3] == lw.RULES_VERSION


if __name__ == "__main__":
    _p = _f = 0
    for _n, _fn in sorted(globals().items()):
        if _n.startswith("test_") and callable(_fn):
            try:
                _fn()
                print(f"PASS {_n}")
                _p += 1
            except Exception as e:
                import traceback
                print(f"FAIL {_n}: {e}")
                traceback.print_exc()
                _f += 1
    print(f"\n{_p} passed, {_f} failed")
    sys.exit(1 if _f else 0)
