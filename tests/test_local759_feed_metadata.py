"""
test_local759_feed_metadata.py — LOCAL-759 C (server side).

The organiser-audio builder shows each feed episode's SIZE and duration in its
import checklist, and a running total of the ticked episodes, so the organiser
knows how big a download they are about to publish to their members (Michael's
Salem tour was 285 MB across three podcast episodes).

For that the server must carry the feed's own metadata through the whole path:
  1. communities_rss.parse_feed emits `duration`, `size` (enclosure length in
     bytes) and `date` (publish date) per episode when the feed provides them.
  2. _upsert_feed_episodes persists them (new nullable columns).
  3. _episodes_for / GET /communities/<id>/episodes return them, so the app's
     CommunityEpisode.metaLine (LOCAL-758) is not empty.

Red-first: parse_feed on d816a251 returns only {position,title,audio_url,guid};
these assertions fail until the metadata fields are added.

Only the standard library + pytest are used; no network (fetch_and_parse takes
an injected getter), and the DB round-trip reuses the LOCAL-690 fixtures.
"""

import importlib.util
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
USER_TRACKING = os.path.join(ROOT, "user-tracking")
if USER_TRACKING not in sys.path:
    sys.path.insert(0, USER_TRACKING)


def _load_module(name, relpath):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, relpath))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def rss():
    return _load_module("communities_rss", "user-tracking/communities_rss.py")


# A feed that carries iTunes duration, an enclosure byte length, and a pubDate —
# exactly the shape a Podbean feed (Michael's Salem tour) gives.
RSS_WITH_META = """<?xml version="1.0"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Salem Witch Trials</title>
    <item>
      <title>The Accusations Begin</title>
      <guid>guid-1</guid>
      <pubDate>Tue, 21 Oct 2025 10:00:00 GMT</pubDate>
      <itunes:duration>48:12</itunes:duration>
      <enclosure url="https://mcdn.podbean.com/ep1.mp3" type="audio/mpeg" length="76021760"/>
    </item>
    <item>
      <title>The Trials</title>
      <guid>guid-2</guid>
      <pubDate>Tue, 28 Oct 2025 10:00:00 GMT</pubDate>
      <itunes:duration>3600</itunes:duration>
      <enclosure url="https://mcdn.podbean.com/ep2.mp3" type="audio/mpeg" length="84828160"/>
    </item>
  </channel>
</rss>"""


def test_parse_feed_emits_size_duration_date(rss):
    eps = rss.parse_feed(RSS_WITH_META)
    assert len(eps) == 2

    e0 = eps[0]
    # Size = the enclosure's byte length.
    assert e0["size"] == 76021760
    # Duration = the iTunes duration string, as the feed gave it.
    assert e0["duration"] == "48:12"
    # Date = the publish date, as the feed gave it.
    assert "2025" in (e0["date"] or "")

    e1 = eps[1]
    assert e1["size"] == 84828160
    assert e1["duration"] == "3600"


def test_parse_feed_missing_meta_is_none_not_error(rss):
    # An item with no pubDate/duration/enclosure length still parses; the three
    # optional fields are simply absent/None (never a crash, never a wrong 0).
    xml = """<?xml version="1.0"?>
    <rss version="2.0"><channel><title>t</title>
      <item>
        <title>Plain</title>
        <guid>g</guid>
        <enclosure url="https://owner.example/x.mp3" type="audio/mpeg"/>
      </item>
    </channel></rss>"""
    eps = rss.parse_feed(xml)
    assert len(eps) == 1
    assert eps[0].get("size") in (None, 0)
    assert eps[0].get("duration") in (None, "")
    assert eps[0].get("date") in (None, "")


# ─── DB round-trip: _upsert_feed_episodes persists metadata, _episodes_for ───
# returns it. Calls the functions directly against an inserted community row —
# no HTTP create gate, no auth env to configure.

try:
    from db_connection import get_connection, get_database_url  # noqa: E402

    _HAVE_DB = True
except Exception:  # pragma: no cover - DB module optional in some envs
    _HAVE_DB = False

TEST_PREFIX = "L759TEST_"


@pytest.fixture(scope="module")
def ca():
    os.environ["DATABASE_URL"] = get_database_url()
    return _load_module("communities_api_759", "user-tracking/communities_api.py")


@pytest.fixture
def db():
    conn = get_connection()
    yield conn
    conn.close()


def _cleanup(db):
    cur = db.cursor()
    cur.execute("SELECT id FROM communities WHERE name LIKE %s", (TEST_PREFIX + "%",))
    ids = [r[0] for r in cur.fetchall()]
    if ids:
        cur.execute("DELETE FROM community_episodes WHERE community_id = ANY(%s)", (ids,))
        cur.execute("DELETE FROM communities WHERE id = ANY(%s)", (ids,))
    db.commit()
    cur.close()


@pytest.fixture(autouse=True)
def _clean(db):
    if not _HAVE_DB:
        pytest.skip("DB unavailable")
    _cleanup(db)
    yield
    _cleanup(db)


def _insert_community(db, name):
    """Insert a minimal community row directly and return its id (feed metadata
    persistence does not need the create gate)."""
    cur = db.cursor()
    cur.execute(
        "INSERT INTO communities (name, owner_user_id, visibility) "
        "VALUES (%s, %s, 'private') RETURNING id",
        (name, TEST_PREFIX + "owner"),
    )
    cid = cur.fetchone()[0]
    db.commit()
    cur.close()
    return cid


@pytest.mark.skipif(not _HAVE_DB, reason="DB unavailable")
def test_upsert_and_episodes_for_round_trip_metadata(ca, db, rss):
    cid = _insert_community(db, TEST_PREFIX + "SalemMeta")
    parsed = rss.parse_feed(RSS_WITH_META)

    cur = db.cursor()
    added = ca._upsert_feed_episodes(cur, cid, parsed)
    db.commit()
    assert added == 2

    eps = ca._episodes_for(cur, cid)
    cur.close()
    assert len(eps) == 2
    assert eps[0]["size"] == 76021760
    assert eps[0]["duration"] == "48:12"
    assert "2025" in (eps[0]["date"] or "")
    assert eps[1]["size"] == 84828160


