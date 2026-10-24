"""
communities_rss.py — LOCAL-690 (D657 addendum / D658 addendum 2).

Parse an owner's ONE RSS feed into episode METADATA ONLY: (title, order, URL).
Audioura never uploads or stores the files — it keeps only what it needs to
SHOW and PLAY each item as a tour stop (D657 addendum: "stores nothing" beyond
metadata). There is NO content check on owner audio.

Design for testability:
  * `parse_feed(xml_text)` is a pure function over the feed body — no network,
    so a unit test feeds it a fixture string and asserts the episodes.
  * `fetch_and_parse(feed_url, http_get=...)` takes the HTTP getter as a
    parameter so a test injects a mock and no real request is ever made. The
    default getter uses urllib (standard library — no new dependency in the
    user-api container).

Only the standard library is used (xml.etree, urllib) so the self-contained
user-api container needs nothing extra.
"""

import logging
import xml.etree.ElementTree as ET
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# RSS/Atom namespaces we may meet. We read the common ones; anything else is
# ignored (we only need title + the enclosed audio URL).
_ATOM_NS = '{http://www.w3.org/2005/Atom}'


class FeedParseError(Exception):
    """The feed body could not be parsed as RSS or Atom."""


def _text(el):
    return (el.text or '').strip() if el is not None else ''


def _episode_url_from_item(item):
    """The owner-hosted audio URL for one RSS <item>.

    Preference order (podcast convention):
      1. <enclosure url="..."> — the standard podcast audio link.
      2. <media:content url="..."> — some feeds use Media RSS.
      3. <link> — last resort.
    Returns '' when the item carries no usable URL (such an item is skipped).
    """
    enclosure = item.find('enclosure')
    if enclosure is not None:
        url = enclosure.attrib.get('url', '').strip()
        if url:
            return url
    # Media RSS <media:content url="...">
    for child in item:
        if child.tag.endswith('}content') or child.tag == 'content':
            url = child.attrib.get('url', '').strip()
            if url:
                return url
    link = item.find('link')
    if link is not None:
        url = _text(link) or link.attrib.get('href', '').strip()
        if url:
            return url
    return ''


# [LOCAL-759 C] The iTunes podcast namespace — where <itunes:duration> lives.
_ITUNES_NS = '{http://www.itunes.com/dtds/podcast-1.0.dtd}'


def _episode_size_from_item(item):
    """The episode's byte SIZE from the <enclosure length="..."> attribute, or
    None when the feed omits it (not every feed sets length). Only a positive
    integer counts — a '0' or non-numeric length is treated as absent so the UI
    never shows a wrong "0 MB". This is the number the organiser-audio builder
    sums into "3 episodes · 285 MB" (LOCAL-759 C)."""
    enclosure = item.find('enclosure')
    if enclosure is not None:
        raw = enclosure.attrib.get('length', '').strip()
        try:
            n = int(raw)
            if n > 0:
                return n
        except (TypeError, ValueError):
            pass
    # Media RSS <media:content fileSize="..."> is the other common carrier.
    for child in item:
        if child.tag.endswith('}content') or child.tag == 'content':
            raw = (child.attrib.get('fileSize')
                   or child.attrib.get('length') or '').strip()
            try:
                n = int(raw)
                if n > 0:
                    return n
            except (TypeError, ValueError):
                pass
    return None


def _episode_duration_from_item(item):
    """The episode's DURATION as the feed gave it (e.g. '48:12' or '3600'),
    from <itunes:duration>, or None. Kept as the raw string — the app formats
    it; the server never converts (a feed may give HH:MM:SS or seconds)."""
    for tag in (f'{_ITUNES_NS}duration', 'duration'):
        el = item.find(tag)
        if el is not None:
            d = _text(el)
            if d:
                return d
    return None


def _episode_date_from_item(item):
    """The episode's publish DATE as the feed gave it (<pubDate>), or None.
    Raw string — the app shows it; the server does not reformat."""
    for tag in ('pubDate', f'{_ATOM_NS}published', 'published', 'updated'):
        el = item.find(tag)
        if el is not None:
            d = _text(el)
            if d:
                return d
    return None


def parse_feed(xml_text):
    """Parse an RSS (or Atom) feed body into a list of episode dicts.

    Each dict: {position (1-based), title, audio_url, guid, size, duration,
    date}. `size` is the enclosure byte length (int) or None; `duration` and
    `date` are the feed's raw strings or None (LOCAL-759 C — the builder
    checklist shows these and sums `size` into a running total). Items appear in
    FEED ORDER (position 1 = the first item in the document). Items with no
    audio URL are skipped (nothing to play). Items with no title get a stable
    fallback 'Episode N'. METADATA ONLY — no audio is fetched.

    Raises FeedParseError on malformed XML.
    """
    if not xml_text or not xml_text.strip():
        raise FeedParseError('empty feed body')
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise FeedParseError(f'xml parse error: {e}') from e

    episodes = []

    # RSS: <rss><channel><item>...  — the common podcast shape.
    channel = root.find('channel')
    items = channel.findall('item') if channel is not None else []

    if items:
        for idx, item in enumerate(items, start=1):
            url = _episode_url_from_item(item)
            if not url:
                continue  # nothing playable — skip
            title = _text(item.find('title')) or f'Episode {idx}'
            guid = _text(item.find('guid')) or None
            episodes.append({
                'position': len(episodes) + 1,
                'title': title,
                'audio_url': url,
                'guid': guid,
                # [LOCAL-759 C] Feed metadata for the builder checklist. Any may
                # be None when the feed omits it; the app's metaLine drops blanks.
                'size': _episode_size_from_item(item),
                'duration': _episode_duration_from_item(item),
                'date': _episode_date_from_item(item),
            })
        return episodes

    # Atom: <feed><entry>... with <link rel="enclosure" href="...">.
    entries = root.findall(f'{_ATOM_NS}entry') or root.findall('entry')
    if entries:
        for idx, entry in enumerate(entries, start=1):
            url = ''
            # Prefer an enclosure link; else any audio link.
            for link in entry.findall(f'{_ATOM_NS}link') + entry.findall('link'):
                href = link.attrib.get('href', '').strip()
                rel = link.attrib.get('rel', '')
                typ = link.attrib.get('type', '')
                if href and (rel == 'enclosure' or typ.startswith('audio')):
                    url = href
                    break
            if not url:
                # fall back to the first link with an href
                for link in entry.findall(f'{_ATOM_NS}link') + entry.findall('link'):
                    href = link.attrib.get('href', '').strip()
                    if href:
                        url = href
                        break
            if not url:
                continue
            title = (_text(entry.find(f'{_ATOM_NS}title'))
                     or _text(entry.find('title')) or f'Episode {idx}')
            guid = (_text(entry.find(f'{_ATOM_NS}id'))
                    or _text(entry.find('id')) or None)
            # [LOCAL-759 C] Atom carries the byte size on the enclosure link's
            # `length` attribute; duration/date reuse the shared item helpers
            # (they also read the Atom <published>/<updated> dates).
            size = None
            for link in entry.findall(f'{_ATOM_NS}link') + entry.findall('link'):
                if link.attrib.get('href', '').strip() == url:
                    raw = link.attrib.get('length', '').strip()
                    try:
                        n = int(raw)
                        if n > 0:
                            size = n
                    except (TypeError, ValueError):
                        pass
                    break
            episodes.append({
                'position': len(episodes) + 1,
                'title': title,
                'audio_url': url,
                'guid': guid,
                'size': size,
                'duration': _episode_duration_from_item(entry),
                'date': _episode_date_from_item(entry),
            })
        return episodes

    # Neither RSS items nor Atom entries — a valid XML doc with no episodes.
    return episodes


def _default_http_get(url, timeout=10):
    """Fetch a URL body as text using only the standard library.

    Kept tiny and injectable: tests pass their own getter to fetch_and_parse so
    no network request is ever made in a test.
    """
    req = Request(url, headers={'User-Agent': 'Audioura-Communities/1.0'})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — owner-supplied URL by design
        charset = resp.headers.get_content_charset() or 'utf-8'
        return resp.read().decode(charset, errors='replace')


def fetch_and_parse(feed_url, http_get=None, timeout=10):
    """Fetch `feed_url` and parse it into episodes.

    `http_get` is the fetcher (url, timeout) -> body text; it defaults to the
    stdlib getter but a test ALWAYS injects a mock so no real request is made.
    Returns the same list of episode dicts as `parse_feed`. Raises
    FeedParseError on a bad body; lets a transport error from http_get
    propagate so the caller can report it.
    """
    getter = http_get or _default_http_get
    body = getter(feed_url, timeout)
    return parse_feed(body)
