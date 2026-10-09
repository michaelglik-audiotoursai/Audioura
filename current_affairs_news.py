"""current_affairs_news.py — dated NEWS research for a current-affairs tour.

LOCAL-655. Tour 557 ("Walking tour in Boston dedicated to Massachusetts politics
and current affairs") ended with "we found no verified developments from the past
five years" — a gap the pipeline *created itself*: no code searched news at all
(the research backends are Wikipedia/Wikidata/venue corpus + Gemini grounding on
HISTORY questions). Current affairs happen every day the legislature sits; the
honest-note is only honest if a news search actually ran and returned nothing.

This module adds exactly that search, for a current-affairs request only:

    1. DETECT   wants_current_affairs(request) — a current-affairs intent gate.
    2. QUERY    the Serper NEWS endpoint (https://google.serper.dev/news) for the
                tour theme and for each stop, tbs=qdr:m (past month), widening to
                qdr:y (past year) when the month is empty. $0.001/query (metered at
                the network layer like every other serper.dev call).
    3. FETCH    the 2-3 best article pages (the existing polite, cached, robots-
                aware exhibition_checklist._fetch_page helper).
    4. NARRATE  1-3 DATED, attributed, politically-BALANCED sentences per stop,
                grounded ONLY in the fetched article text — no invented quotes or
                numbers, no adjectives taking a side. A cheap model (gpt-4.1-mini)
                constrained to the sources writes them.
    5. HONEST   when the search ran AND returned nothing usable, an honest note is
                produced (and the queries + counts are logged) — not a fabricated
                "nothing happened".

It mirrors serper_research.py exactly: deterministic query derivation, the project
Serper key (SERP_API_KEY), the shared page-fetch helper, and a source-constrained
cheap model. The injection pass is additive, idempotent and parses stops from the
DELIVERED text, so it is independent of which generation path produced the tour.

NOTHING here runs unless wants_current_affairs(request) is true AND the tour is not
a museum tour — so the museum path and any non-current-affairs tour are byte-for-
byte unchanged.
"""
import datetime as _dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Callable, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# ── tunables (env-overridable) ────────────────────────────────────────────────
NEWS_MODEL = os.environ.get('CA_NEWS_MODEL', 'gpt-4.1-mini')
NEWS_PER_QUERY_RESULTS = int(os.environ.get('CA_NEWS_NUM', '8'))
NEWS_MAX_ARTICLES_PER_STOP = int(os.environ.get('CA_NEWS_MAX_ARTICLES', '3'))
NEWS_MAX_STOP_QUERIES = int(os.environ.get('CA_NEWS_MAX_STOP_QUERIES', '2'))
NEWS_PER_PAGE_CHARS = int(os.environ.get('CA_NEWS_PER_PAGE_CHARS', '2500'))
NEWS_ANSWER_MAX_TOKENS = int(os.environ.get('CA_NEWS_MAX_TOKENS', '320'))
NEWS_FRESH_DAYS = int(os.environ.get('CA_NEWS_FRESH_DAYS', '7'))

SERP_NEWS_URL = 'https://google.serper.dev/news'

# The honest note — used ONLY when a search ran and returned nothing usable.
HONEST_NOTE = (
    "We searched the news for recent developments connected to this tour but "
    "could not confirm any from reliable, dated reporting at the time of writing."
)


# ── 1. intent gate ────────────────────────────────────────────────────────────

# Phrases/words that mark a request as wanting CURRENT AFFAIRS (recent, ongoing,
# dated public events) as opposed to a history / art / architecture tour. The
# detector is deliberately narrow: a plain "history of Boston" tour must NOT
# trip it (history is handled by the existing grounded-research path, unchanged).
_CA_PHRASES = (
    'current affairs', 'current events', 'in the news', 'recent news',
    'latest news', 'todays news', "today's news", 'breaking news',
    'current political', 'present-day politics', 'contemporary politics',
    'recent developments', 'latest developments',
)
_CA_WORDS = {
    'politics', 'political', 'election', 'elections', 'campaign',
    'legislature', 'legislative', 'senate', 'congress', 'parliament',
    'governor', 'mayor', 'councillor', 'councilmember', 'referendum',
    'ballot', 'policy', 'protest', 'protests', 'debate', 'debates',
    'bill', 'statehouse', 'state house', 'city hall',
}
# Words that, if the ONLY signal, indicate a HISTORY tour and must not alone
# trigger current affairs (so "history of the Senate chamber" is not news).
_HISTORY_ONLY = {'history', 'historic', 'historical', 'heritage', 'colonial',
                 'revolution', 'founding', 'ancient', 'medieval'}


def wants_current_affairs(request_text: str) -> bool:
    """True when the request asks for CURRENT AFFAIRS / recent dated public events.

    Deterministic and free. A multi-word phrase ("current affairs", "in the news")
    is decisive. A single political word ("politics", "election", "governor",
    "legislature", …) also qualifies — those requests are about what is happening
    now, which is exactly what the LOCAL-655 search must cover. A request whose
    only signal is a history word does NOT qualify.
    """
    t = (request_text or '').lower()
    if not t:
        return False
    for p in _CA_PHRASES:
        if p in t:
            return True
    words = set(re.findall(r"[a-z]+", t))
    # multi-word markers that survive the word-split ("state house" -> state,house)
    if 'state' in words and 'house' in words:
        return True
    if 'city' in words and 'hall' in words:
        return True
    return bool(words & _CA_WORDS)


# ── 2. query derivation ───────────────────────────────────────────────────────

_STOP_HEADER_RE = re.compile(r"(?m)^Stop\s+(\d+):\s*(.+?)\s*$")
# a trailing ", City, STATE" or ", City, Country" tail on the request/theme
_LOC_TAIL_RE = re.compile(r",\s*[^,]+,\s*[^,]+$")


def _theme_phrase(request_text: str) -> str:
    """A compact theme phrase from the request, stripped of tour boilerplate and
    the trailing ", City, Country" tail. When the request names its topic with
    "dedicated to / about / on <topic>", that topic is the theme."""
    t = (request_text or '').strip()
    t = _LOC_TAIL_RE.sub('', t).strip()
    # Prefer the explicit topic marker: "... dedicated to|about|on|focused on X".
    mt = re.search(r'(?i)\b(?:dedicated to|focus(?:ed|ing)? on|about|on the subject of|on)\s+(.+)$', t)
    if mt:
        topic = mt.group(1).strip()
        if len(topic) >= 4:
            return topic
    # drop leading "Walking/driving/… tour (in|of|around|dedicated to)" scaffolding
    t = re.sub(r'(?i)^\s*(?:a\s+)?(?:walking|driving|cycling|biking|self[- ]guided|'
               r'audio)?\s*tour\s+(?:in|of|around|through|dedicated to|about|on)?\s*',
               '', t).strip()
    return t or (request_text or '').strip()


def _region_phrase(request_text: str) -> str:
    """The place/region hint for scoping a stop query (e.g. 'Boston, MA')."""
    m = re.search(r",\s*([^,]+,\s*[^,]+)$", request_text or '')
    if m:
        return m.group(1).strip()
    return ''


# Boilerplate stripped from a theme phrase to leave a short, searchable subject.
# "Massachusetts politics and current affairs" -> "Massachusetts politics".
_THEME_BOILERPLATE_RE = re.compile(
    r'(?i)\b(?:and\s+)?(?:current\s+affairs|current\s+events|recent\s+'
    r'developments|latest\s+developments|in\s+the\s+news|news|today|'
    r'present[- ]day|contemporary|recent|latest|ongoing)\b')


def _theme_subject(request_text: str) -> str:
    """The SHORT subject of the theme, stripped of 'current affairs'/'news' tails
    and the trailing address. 'Massachusetts politics and current affairs,
    Boston, MA' -> 'Massachusetts politics' (Defect 3)."""
    t = _theme_phrase(request_text)
    t = _THEME_BOILERPLATE_RE.sub(' ', t)
    t = re.sub(r'\s*&\s*', ' ', t)
    t = re.sub(r'[,;]+', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip(' -')
    # trim a dangling 'and'/'of' left by the strip
    t = re.sub(r'(?i)\s+(?:and|of|the)\s*$', '', t).strip()
    return t


# Government facets a politics subject expands into. Each is combined with the
# subject's PLACE word so the queries stay short and local, e.g.
# "Massachusetts governor", "Massachusetts legislature", "Boston city council".
_POLITICS_FACETS = ('politics', 'governor', 'legislature', 'election')
_CITY_FACETS = ('city council', 'mayor')


def derive_theme_queries(request_text: str) -> List[str]:
    """Short, derived theme-level news queries (LOCAL-659 Defect 3).

    The raw theme phrase ('Massachusetts politics and current affairs Boston, MA')
    returned 0 items — too long. We derive SHORT queries instead: the stripped
    subject itself, then a handful of government facets anchored to the subject's
    place and the tour city:
        'Massachusetts politics', 'Massachusetts governor',
        'Massachusetts legislature', 'Boston city council'.
    Deterministic; de-duplicated; capped so the paid-query budget stays small."""
    subject = _theme_subject(request_text)
    city = _city_token(request_text)
    out: List[str] = []

    # the stripped subject on its own (short) — e.g. 'Massachusetts politics'.
    if subject:
        out.append(subject)

    # the "place" word that anchors facets: prefer a state/region named in the
    # subject (e.g. 'Massachusetts'); else fall back to the tour city.
    place = ''
    msub = re.match(r'\s*([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)', subject or '')
    if msub:
        cand = msub.group(1).strip()
        # keep it only if it looks like a place (a known US state) — otherwise the
        # first word of the subject is itself the topic (e.g. 'politics').
        if cand.lower() in _US_STATES:
            place = cand
    if not place:
        place = city

    is_politics = wants_current_affairs(request_text) and (
        'politic' in (subject or '').lower()
        or any(_word_in((subject or '').lower(), w) for w in _STRONG_POLITICS)
        or any(_word_in((request_text or '').lower(), w) for w in _STRONG_POLITICS))

    if is_politics and place:
        for facet in _POLITICS_FACETS:
            out.append(f"{place} {facet}")
        # city-government facets anchored to the tour city (e.g. 'Boston city council')
        if city:
            for facet in _CITY_FACETS:
                out.append(f"{city} {facet}")
    elif place:
        out.append(f"{place} latest news")

    # de-dupe, keep order, cap to keep the paid-query budget small.
    seen, uniq = set(), []
    for q in out:
        q = re.sub(r'\s+', ' ', q).strip()
        if q and q.lower() not in seen:
            seen.add(q.lower())
            uniq.append(q)
    return uniq[:6]


def _city_token(request_text: str) -> str:
    """A short city/region token for anchoring a stop query (e.g. 'Boston').

    The request tail is usually ", City, STATE/Country"; the city is the first
    component of that tail. Falls back to the whole region phrase."""
    region = _region_phrase(request_text)
    if region:
        first = region.split(',')[0].strip()
        if first:
            return first
    return region


def derive_stop_queries(stop_name: str, request_text: str,
                        max_queries: int = NEWS_MAX_STOP_QUERIES) -> List[str]:
    """Per-stop news queries: the stop + its CITY, and the stop + a theme word.

    Every query is anchored to the tour's city so a generic landmark name does not
    pull a same-named place elsewhere (the LOCAL-655 live run matched an "Old State
    House" in Arkansas without the anchor). e.g. for a Boston tour:
    "Massachusetts State House" ->
        ["Massachusetts State House Boston news",
         "Massachusetts State House legislature"].
    """
    name = (stop_name or '').strip()
    if not name:
        return []
    region = _region_phrase(request_text)
    city = _city_token(request_text)
    theme = _theme_phrase(request_text)
    # Primary query: the stop, anchored to its city, scoped to news. Only add the
    # city when the stop name does not already contain it.
    if city and city.lower() not in name.lower():
        out = [f"{name} {city} news"]
    else:
        out = [f"{name} news"]
    # a topical second query: pick the strongest theme word present, still city-
    # anchored so it stays local.
    topical = ''
    for w in ('legislature', 'senate', 'governor', 'election', 'politics',
              'policy', 'council', 'mayor'):
        if w in (theme or '').lower() or w in (request_text or '').lower():
            topical = w
            break
    if topical:
        _tail = f"{name} {topical}"
        if city and city.lower() not in _tail.lower():
            _tail = f"{_tail} {city}"
        out.append(_tail)
    elif region:
        out.append(f"{name} {region}")
    seen, uniq = set(), []
    for q in out:
        q = re.sub(r'\s+', ' ', q).strip()
        if q and q.lower() not in seen:
            seen.add(q.lower())
            uniq.append(q)
        if len(uniq) >= max_queries:
            break
    return uniq


# ── 3. Serper NEWS endpoint ───────────────────────────────────────────────────

def _serp_news(query: str, tbs: str = 'qdr:m',
               num: int = NEWS_PER_QUERY_RESULTS) -> List[Dict]:
    """One Serper NEWS query. Returns [{title, source, date, link, snippet}].

    POSTs to https://google.serper.dev/news with the project SERP_API_KEY. The
    network meter prices every serper.dev call at $0.001/query automatically
    (_meter/paid_api_meter.py), so no explicit metering is needed here. Returns []
    on any failure (never raises)."""
    key = os.environ.get('SERP_API_KEY', '')
    if not key:
        print("  [LOCAL-655] No SERP_API_KEY — news query skipped")
        return []
    payload = {"q": query, "num": num}
    if tbs:
        payload["tbs"] = tbs
    try:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(
            SERP_NEWS_URL, data=data,
            headers={"X-API-KEY": key, "Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            rb = e.read().decode('utf-8', errors='replace')[:300]
        except Exception:
            rb = '<unreadable>'
        print(f"  [LOCAL-655] NEWS HTTP {e.code}: {e.reason}; body={rb}")
        return []
    except Exception as e:
        print(f"  [LOCAL-655] NEWS query failed: {type(e).__name__}: {e}")
        return []
    out = []
    for r in body.get("news", []) or []:
        out.append({
            'title': (r.get('title') or '').strip(),
            'source': (r.get('source') or '').strip(),
            'date': (r.get('date') or '').strip(),
            'link': (r.get('link') or '').strip(),
            'snippet': (r.get('snippet') or '').strip(),
        })
    return out


def news_for_query(query: str, serp: Optional[Callable] = None) -> Tuple[List[Dict], str]:
    """Run one news query, widening the time window ONLY when a tighter one is
    empty: past WEEK first, then past MONTH, then past YEAR (LOCAL-659 Defect 2).

    A current-affairs tour must lead with this week's news when there is any, so
    we ask Serper for qdr:w first and stop at the first non-empty window.
    Returns (items, tbs_used). `serp` is injectable for tests."""
    serp = serp or _serp_news
    for tbs in ('qdr:w', 'qdr:m', 'qdr:y'):
        items = serp(query, tbs)
        if items:
            return items, tbs
    return [], 'qdr:y'


def _rank_items(items: List[Dict]) -> List[Dict]:
    """De-dupe by link and order NEWEST FIRST (LOCAL-659 Defect 2).

    Tour 557 v5 led with month-old items while the Oct 8 governor debate and an
    Oct 8 story were present but lost placement. A current-affairs tour must lead
    with the freshest news, so items are sorted by their resolved date descending
    (today's news first), dated ahead of undated, original order breaking ties."""
    seen, kept = set(), []
    for i, it in enumerate(items):
        link = it.get('link')
        if not link or link in seen:
            continue
        seen.add(link)
        d = parse_news_date(it.get('date', ''))
        # sort key: has-a-date first (1/0), then the date itself, then input order.
        kept.append((1 if d else 0, d or _dt.date.min, -i, it))
    kept.sort(key=lambda t: (t[0], t[1], t[2]), reverse=True)
    return [t[3] for t in kept]


# Published-date metadata patterns, in order of trust: an explicit article
# publication meta tag, JSON-LD datePublished, then OpenGraph/other time tags.
# A hit here gives an EXACT day (unlike a relative Serper string), so when the
# fetched page carries one we use it as the authoritative date (Defect 1).
_META_DATE_RES = (
    re.compile(r'(?is)<meta[^>]+property=["\']article:published_time["\'][^>]*\bcontent=["\']([^"\']+)["\']'),
    re.compile(r'(?is)<meta[^>]+\bcontent=["\']([^"\']+)["\'][^>]*property=["\']article:published_time["\']'),
    re.compile(r'(?is)<meta[^>]+itemprop=["\']datePublished["\'][^>]*\bcontent=["\']([^"\']+)["\']'),
    re.compile(r'(?is)<meta[^>]+name=["\'](?:date|pubdate|publishdate|publish-date|article:published_time|sailthru\.date)["\'][^>]*\bcontent=["\']([^"\']+)["\']'),
    re.compile(r'(?is)"datePublished"\s*:\s*"([^"]+)"'),
    re.compile(r'(?is)<time[^>]+datetime=["\']([^"\']+)["\'][^>]*>'),
)


def extract_published_date(html: str, now: Optional[_dt.date] = None
                           ) -> Optional[_dt.date]:
    """Extract an EXACT publication date from an article page's RAW HTML.

    Looks (in trust order) at <meta property="article:published_time">, JSON-LD
    "datePublished", common name=date meta variants, and <time datetime=...>.
    Returns the parsed date (exact), or None when the page carries no usable
    publication metadata. This is how the composer gets a real DAY for an item
    whose Serper date was only relative ("1 month ago") — the article's own
    metadata, not an arithmetic guess (LOCAL-659 Defect 1)."""
    if not html:
        return None
    today = now or _dt.date.today()
    for rx in _META_DATE_RES:
        m = rx.search(html)
        if not m:
            continue
        d = _parse_absolute_date(m.group(1))
        if d is not None and _dt.date(2000, 1, 1) <= d <= today:
            return d
    return None


def _fetch_article(url: str) -> Tuple[str, Optional[_dt.date]]:
    """Fetch an article page's clean text AND its exact published date (if any).

    Returns (clean_text, published_date). The published date is parsed from the
    raw HTML head (meta/JSON-LD/time) BEFORE the HTML is reduced to paragraph
    text, so an item whose Serper date was only relative can still be stated with
    a real day when the article itself declares one (LOCAL-659 Defect 1)."""
    pub_date = None
    try:
        from exhibition_checklist import _fetch_raw_html
    except Exception:
        _fetch_raw_html = None
    if _fetch_raw_html is not None:
        try:
            html = _fetch_raw_html(url)
            pub_date = extract_published_date(html)
        except Exception:
            pub_date = None
    try:
        from exhibition_checklist import _fetch_page
    except Exception:
        return '', pub_date
    try:
        text, _links = _fetch_page(url)
    except Exception:
        return '', pub_date
    text = text or ''
    if '<' in text[:200] and ('</' in text or '<p' in text.lower()):
        try:
            from robust_text_extractor import extract_clean_text
            text = extract_clean_text(text) or text
        except Exception:
            pass
    return text, pub_date


# ── 3b. relevance gate — place / theme / dated-in-window ──────────────────────
#
# WHY DETERMINISTIC, NOT A MODEL CALL. The LOCAL-655 live run (tour 618) proved
# the model-only approach leaks: the cheap composer was the ONLY filter, and it
# happily wrote dated, attributed sentences about the Arkansas "Old State House
# Museum" (Arkansas Times, KARK) on a Boston stop, and about a burger restaurant
# ("Smashed by BRED") on a politics tour, and presented an undated "2022 strategy"
# item as "Recently". A gate must run BEFORE composition and must not itself be a
# fallible generative step. These three checks are cheap, free, auditable, and
# their rejection reasons are logged for the ticket:
#   (a) PLACE  — the article (title+snippet+fetched text) names the request's city
#                or its state/region. A bare same-named building elsewhere, whose
#                text names a DIFFERENT US state and never the request's place,
#                fails. (Arkansas item: names "Arkansas"/"Hot Springs", never
#                "Boston"/"Massachusetts" -> rejected.)
#   (b) THEME  — the article names at least one civic/politics theme word
#                (government, election, legislation, protest, …). A restaurant
#                opening names none -> rejected. (burger item -> rejected.)
#   (c) DATE   — a real date parses from the item AND falls inside the freshness
#                window. Undated -> dropped (never "Recently" without a date).

# US state names + common abbreviations, so a wrong-state article (Arkansas) is
# detected even when the request's own state is absent. Kept lowercase.
_US_STATES = {
    'alabama', 'alaska', 'arizona', 'arkansas', 'california', 'colorado',
    'connecticut', 'delaware', 'florida', 'georgia', 'hawaii', 'idaho',
    'illinois', 'indiana', 'iowa', 'kansas', 'kentucky', 'louisiana', 'maine',
    'maryland', 'massachusetts', 'michigan', 'minnesota', 'mississippi',
    'missouri', 'montana', 'nebraska', 'nevada', 'new hampshire', 'new jersey',
    'new mexico', 'new york', 'north carolina', 'north dakota', 'ohio',
    'oklahoma', 'oregon', 'pennsylvania', 'rhode island', 'south carolina',
    'south dakota', 'tennessee', 'texas', 'utah', 'vermont', 'virginia',
    'washington', 'west virginia', 'wisconsin', 'wyoming',
}
_STATE_ABBR = {
    'al': 'alabama', 'ak': 'alaska', 'az': 'arizona', 'ar': 'arkansas',
    'ca': 'california', 'co': 'colorado', 'ct': 'connecticut', 'de': 'delaware',
    'fl': 'florida', 'ga': 'georgia', 'hi': 'hawaii', 'id': 'idaho',
    'il': 'illinois', 'in': 'indiana', 'ia': 'iowa', 'ks': 'kansas',
    'ky': 'kentucky', 'la': 'louisiana', 'me': 'maine', 'md': 'maryland',
    'ma': 'massachusetts', 'mi': 'michigan', 'mn': 'minnesota', 'ms': 'mississippi',
    'mo': 'missouri', 'mt': 'montana', 'ne': 'nebraska', 'nv': 'nevada',
    'nh': 'new hampshire', 'nj': 'new jersey', 'nm': 'new mexico', 'ny': 'new york',
    'nc': 'north carolina', 'nd': 'north dakota', 'oh': 'ohio', 'ok': 'oklahoma',
    'or': 'oregon', 'pa': 'pennsylvania', 'ri': 'rhode island', 'sc': 'south carolina',
    'sd': 'south dakota', 'tn': 'tennessee', 'tx': 'texas', 'ut': 'utah',
    'vt': 'vermont', 'va': 'virginia', 'wa': 'washington', 'wv': 'west virginia',
    'wi': 'wisconsin', 'wy': 'wyoming',
}

# Theme vocabulary for (b). Civic / politics / government / elections /
# legislation / civic protest. A restaurant/food/sport item names none of these.
#
# LOCAL-659 Defect 4: this is now split and matched on WORD BOUNDARIES.
#   _STRONG_POLITICS — unambiguous government/elections/legislation/official/
#       civic-protest terms. A single one is decisive and overrides a cultural
#       word (a protest AT a festival is still news; a "budget vote" is politics).
#   _THEME_WORDS — the broader civic vocabulary. A hit here passes the theme test
#       ON ITS OWN only when the item is not ALSO a pure cultural-event listing.
# Ambiguous words that leaked cultural/weather/crime items in the tour-557 run
# ('house', 'march', 'measure', 'court', 'budget', 'hearing', 'primary', 'rally')
# are kept OUT of the bare theme set; their politics senses live in the strong
# set as multi-word anchors ('state house', 'city council', 'ballot question').
_STRONG_POLITICS = {
    'governor', 'gubernatorial', 'mayor', 'mayoral', 'legislature',
    'legislative', 'legislator', 'lawmaker', 'senate', 'senator',
    'congress', 'congressional', 'congressman', 'congresswoman',
    'representative', 'statehouse', 'election', 'elections', 'electoral',
    'ballot', 'referendum', 'primary election', 'caucus', 'candidate',
    'campaign', 'incumbent', 'city council', 'city councillor',
    'city councilor', 'town council', 'councilmember', 'councilwoman',
    'councilman', 'alderman', 'selectboard', 'select board', 'commissioner',
    'legislation', 'ordinance', 'statute', 'veto', 'filibuster',
    'attorney general', 'secretary of state', 'state house', 'town hall meeting',
    'city hall', 'beacon hill', 'general court', 'house speaker',
    'ballot question', 'ballot measure', 'voters', 'constituents',
    'democrat', 'democrats', 'republican', 'republicans', 'gop',
    'political party', 'governance', 'gerrymander', 'impeach', 'impeachment',
}
_THEME_WORDS = {
    'politic', 'political', 'politics', 'government', 'governmental', 'policy',
    'policies', 'vote', 'votes', 'voting', 'protest', 'protests', 'demonstration',
    'activist', 'activism', 'civic', 'bill', 'law', 'lawsuit', 'reform',
    'official', 'officials', 'administration', 'cabinet', 'agency', 'budget',
    'taxpayer', 'constituency', 'municipal', 'federal', 'statewide',
} | _STRONG_POLITICS

# Cultural / lifestyle / arts / events vocabulary. An item that is ONLY one of
# these (an open house, festival, concert, exhibit, weekend-things-to-do round-up)
# is NOT current affairs for a politics tour, even if a stray civic word appears.
_CULTURAL_WORDS = {
    'open house', 'festival', 'concert', 'recital', 'exhibit', 'exhibition',
    'gallery', 'museum', 'art show', 'artwork', 'performance', 'theater',
    'theatre', 'screening', 'film festival', 'book event', 'reading',
    'things to do', 'this weekend', 'open studios', 'tour of', 'workshop',
    'fair', 'parade', 'fireworks', 'tasting', 'brunch', 'pop-up', 'popup',
    'restaurant', 'menu', 'cuisine', 'cocktail', 'brewery', 'market opening',
    'historic objects', 'artifacts', 'collection on view', 'celebration',
    'anniversary celebration', 'gala', 'fundraiser gala',
}


def _word_in(blob: str, term: str) -> bool:
    """True if `term` occurs in `blob` as a whole word / phrase (boundaries),
    so 'house' does not match 'warehouse' and 'march' does not match the month."""
    return re.search(r'(?<![a-z])' + re.escape(term) + r'(?![a-z])', blob) is not None


def _theme_term_in(blob: str) -> str:
    """First genuine politics/government theme term present (word-boundary), or ''."""
    # strong terms first so the reason names the most specific match
    for w in sorted(_STRONG_POLITICS, key=len, reverse=True):
        if _word_in(blob, w):
            return w
    for w in sorted(_THEME_WORDS - _STRONG_POLITICS, key=len, reverse=True):
        if _word_in(blob, w):
            return w
    return ''


def _cultural_term_in(blob: str) -> str:
    """First cultural-event term present (word-boundary), or ''."""
    for w in sorted(_CULTURAL_WORDS, key=len, reverse=True):
        if _word_in(blob, w):
            return w
    return ''


def _has_strong_politics(blob: str) -> bool:
    """True if the blob names an unambiguous government/elections/official term —
    enough to keep an item that ALSO mentions a cultural event (e.g. a protest at
    a festival, a governor speaking at a gala)."""
    return any(_word_in(blob, w) for w in _STRONG_POLITICS)


_MONTHS = {m.lower(): i for i, m in enumerate(
    ['', 'January', 'February', 'March', 'April', 'May', 'June', 'July',
     'August', 'September', 'October', 'November', 'December'], 0)}
for _i, _ab in enumerate(['', 'jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul',
                          'aug', 'sep', 'oct', 'nov', 'dec'], 0):
    if _ab:
        _MONTHS[_ab] = _i

_REL_RE = re.compile(
    r'(?i)\b(?:(a|an|one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+'
    r'(second|minute|hour|day|week|month|year)s?\s+ago|yesterday|today)\b')
_WORD_NUM = {'a': 1, 'an': 1, 'one': 1, 'two': 2, 'three': 3, 'four': 4,
             'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10}


# precision of a resolved news date:
#   'exact'  — a specific calendar day is KNOWN (an absolute string with a day,
#              or article meta/JSON-LD/dateline). The composer may print the day.
#   'approx' — only a relative string ("1 month ago") was available; we know the
#              rough age but NOT the day. The composer must speak approximately
#              ("last month", "about three weeks ago") and never print a day.
DATE_EXACT = 'exact'
DATE_APPROX = 'approx'


def _parse_absolute_date(s: str) -> Optional[_dt.date]:
    """Parse an ABSOLUTE date string ("Oct 8, 2026", "8 October 2026",
    "2026-10-08", or an ISO datetime) into a date. None if it is not absolute.

    Absolute strings always name a specific day, so a hit here is EXACT."""
    s = (s or '').strip()
    if not s:
        return None
    # ISO date or datetime (meta/JSON-LD give "2026-09-11T08:46:00-04:00").
    # No trailing \b: an ISO datetime has 'T' right after the day (…-11T08…),
    # which is a word char, so a \b there would fail the match.
    mi = re.search(r'(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)', s)
    if mi:
        try:
            return _dt.date(int(mi.group(1)), int(mi.group(2)), int(mi.group(3)))
        except ValueError:
            return None
    # "Month D, YYYY"
    mo = re.search(r'(?i)\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b', s)
    if mo and mo.group(1).lower() in _MONTHS:
        try:
            return _dt.date(int(mo.group(3)), _MONTHS[mo.group(1).lower()],
                            int(mo.group(2)))
        except ValueError:
            return None
    # "D Month YYYY"
    md = re.search(r'(?i)\b(\d{1,2})\s+([A-Za-z]{3,9})\.?\s+(\d{4})\b', s)
    if md and md.group(2).lower() in _MONTHS:
        try:
            return _dt.date(int(md.group(3)), _MONTHS[md.group(2).lower()],
                            int(md.group(1)))
        except ValueError:
            return None
    return None


def _approx_phrase_for(raw: str, unit: str, qty: int) -> str:
    """A human approximate phrase for a relative age, relative to TODAY, that
    never commits to a day. e.g. 'last month', 'about three weeks ago'."""
    low = (raw or '').lower()
    if 'today' in low:
        return 'earlier today'
    if 'yesterday' in low:
        return 'yesterday'
    if unit in ('second', 'minute', 'hour'):
        return 'earlier today'
    names = {1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six',
             7: 'seven', 8: 'eight', 9: 'nine', 10: 'ten'}
    if unit == 'day':
        if qty == 1:
            return 'yesterday'
        return f"about {names.get(qty, qty)} days ago"
    if unit == 'week':
        if qty == 1:
            return 'last week'
        return f"about {names.get(qty, qty)} weeks ago"
    if unit == 'month':
        if qty == 1:
            return 'last month'
        return f"about {names.get(qty, qty)} months ago"
    if unit == 'year':
        if qty == 1:
            return 'last year'
        return f"about {names.get(qty, qty)} years ago"
    return 'recently'


def resolve_news_date(raw: str, now: Optional[_dt.date] = None
                      ) -> Tuple[Optional[_dt.date], Optional[str], str]:
    """Resolve a Serper-news date string into (date, precision, approx_phrase).

    Serper returns either an ABSOLUTE string ("Oct 8, 2026", "2026-10-08") or a
    RELATIVE one ("Six days ago", "1 month ago", "yesterday"). The two carry very
    different information and LOCAL-659 keeps them apart:

      * ABSOLUTE  -> (the_day, 'exact', ''). We know the day; the composer may
                     print it. ("Oct 8, 2026" -> 2026-10-08, exact.)
      * RELATIVE  -> (approx_day, 'approx', phrase). We can estimate the age for
                     the freshness window (approx_day = today - N units) but we do
                     NOT know the calendar day — a relative "1 month ago" is NOT
                     September 9th. The composer must use `phrase` ("last month")
                     and never print a day. (This is Defect 1: parse_news_date used
                     to turn "1 month ago" into an exact day and the composer stated
                     it as fact — "On September 9, 2026 … led a 9/11 ceremony".)
      * NEITHER   -> (None, None, ''). Undated; the gate drops it.
    """
    s = (raw or '').strip()
    if not s:
        return None, None, ''
    today = now or _dt.date.today()
    # ABSOLUTE first — a specific day is always exact.
    d = _parse_absolute_date(s)
    if d is not None:
        return d, DATE_EXACT, ''
    # RELATIVE — estimate the age for the window, but mark it approximate.
    m = _REL_RE.search(s)
    if m:
        low = s.lower()
        if 'today' in low:
            return today, DATE_APPROX, _approx_phrase_for(s, 'day', 0)
        if 'yesterday' in low:
            return today - _dt.timedelta(days=1), DATE_APPROX, 'yesterday'
        qty_raw, unit = m.group(1), (m.group(2) or '').lower()
        qty = _WORD_NUM.get((qty_raw or '').lower(), None)
        if qty is None:
            try:
                qty = int(qty_raw)
            except (TypeError, ValueError):
                qty = None
        if qty is not None:
            delta_days = {'second': 0, 'minute': 0, 'hour': 0, 'day': qty,
                          'week': 7 * qty, 'month': 30 * qty,
                          'year': 365 * qty}.get(unit)
            if delta_days is not None:
                approx = today - _dt.timedelta(days=delta_days)
                return approx, DATE_APPROX, _approx_phrase_for(s, unit, qty)
    return None, None, ''


def parse_news_date(raw: str, now: Optional[_dt.date] = None) -> Optional[_dt.date]:
    """Resolve a Serper-news date into a calendar date for the freshness window
    (or None if undated). This is the age estimate ONLY — it does NOT tell the
    caller whether the day is known. Use `resolve_news_date` when the precision
    (exact vs approximate) matters, as the gate and composer now do (LOCAL-659)."""
    d, _precision, _phrase = resolve_news_date(raw, now=now)
    return d


def _place_tokens(request_text: str) -> Tuple[str, str]:
    """(city_lower, state_lower) parsed from the request's region tail.

    'Boston, MA' -> ('boston', 'massachusetts'); the state abbreviation is
    expanded to its full name so an article that writes 'Massachusetts' matches."""
    region = _region_phrase(request_text)
    city, state = '', ''
    if region:
        parts = [p.strip() for p in region.split(',') if p.strip()]
        if parts:
            city = parts[0].lower()
        if len(parts) >= 2:
            st = parts[1].lower().strip('.')
            state = _STATE_ABBR.get(st, st if st in _US_STATES else st)
    return city, state


def _item_text_blob(item: Dict) -> str:
    """All available text for an item, lowercased, for gate matching."""
    return ' '.join(str(item.get(k, '') or '') for k in
                    ('title', 'snippet', 'text')).lower()


def gate_item(item: Dict, request_text: str, *,
              fresh_days: int, now: Optional[_dt.date] = None) -> Tuple[bool, str]:
    """Deterministic relevance gate for ONE news item.

    Returns (accepted, reason). `reason` names the first failed check (for the
    audit log) or an 'ok: …' string on acceptance. Order: date, place, theme —
    date first so an undated item is reported as 'undated' regardless of place.

    DATE PRECISION (LOCAL-659 Defect 1): the item's Serper date is resolved to an
    age estimate for the freshness window AND a precision flag. An ABSOLUTE string
    ("Oct 8, 2026") is EXACT — the day is stashed in `_exact_date`. A RELATIVE
    string ("1 month ago") is APPROXIMATE — only `_approx_phrase` ("last month")
    is stashed and `_exact_date` is left empty, so the composer never prints an
    invented day. (An exact day may still be recovered later from the fetched
    article's own metadata; see research_news_for_stops.)

    THEME (LOCAL-659 Defect 4): for a politics/current-affairs request the item
    must name a GENUINE government / elections / legislation / official / civic-
    protest term AND must not be a pure cultural-event listing (open house,
    festival, concert, exhibit). A building open house fails."""
    today = now or _dt.date.today()
    blob = _item_text_blob(item)

    # (c) DATE — must resolve AND be inside the window. Undated -> drop.
    d, precision, approx_phrase = resolve_news_date(item.get('date', ''), now=today)
    if d is None:
        return False, 'undated (no real date in item -> dropped)'
    age = (today - d).days
    if age < 0:
        # a future date is a parse artefact; treat as undated
        return False, f'date in the future ({d.isoformat()}) -> dropped'
    if age > fresh_days:
        return False, f'stale ({d.isoformat()}, {age}d old > {fresh_days}d window)'

    # (a) PLACE — names the request's city or state. If it names a DIFFERENT state
    # and NOT the request's place, reject (the Arkansas Old State House case).
    city, state = _place_tokens(request_text)
    names_city = bool(city) and city in blob
    names_state = bool(state) and re.search(r'\b' + re.escape(state) + r'\b', blob) is not None
    if not (names_city or names_state):
        other = sorted({s for s in _US_STATES
                        if s != state and re.search(r'\b' + re.escape(s) + r'\b', blob)})
        if other:
            return False, (f"wrong place (names {other[0]}, not "
                           f"{city or state or 'the request place'})")
        return False, (f"place not confirmed (article never names "
                       f"{city or state or 'the request place'})")

    # (b) THEME — must name a genuine politics/government term, and must not be a
    # pure cultural-event listing. (Defect 4: "the Boston Athenaeum hosted an open
    # house … historic objects" and weekend-festival round-ups slipped through.)
    cultural_hit = _cultural_term_in(blob)
    strong = _has_strong_politics(blob)
    if cultural_hit and not strong:
        return False, (f"off-theme (cultural event: '{cultural_hit}', no governing "
                       f"action)")
    theme_hit = _theme_term_in(blob)
    if not theme_hit:
        return False, 'off-theme (no government/elections/legislation/official/protest term)'

    # stash the resolved date + precision so the composer states it correctly:
    # an exact day only when known, else an approximate phrase (never a guessed day).
    item['_parsed_date'] = d.isoformat()
    item['_date_precision'] = precision
    item['_approx_phrase'] = approx_phrase or ''
    if precision == DATE_EXACT:
        item['_exact_date'] = d.isoformat()
    else:
        item.pop('_exact_date', None)
    date_desc = (f"exact({d.isoformat()})" if precision == DATE_EXACT
                 else f"approx({approx_phrase or 'recent'})")
    return True, f"ok: place({'city' if names_city else 'state'})+theme({theme_hit})+{date_desc}"


def gate_items(items: List[Dict], request_text: str, *, fresh_days: int,
               now: Optional[_dt.date] = None) -> Tuple[List[Dict], List[Dict]]:
    """Apply gate_item to a list. Returns (accepted, rejected); each rejected item
    carries a '_reject_reason' key for the audit log."""
    accepted, rejected = [], []
    for it in items:
        ok, reason = gate_item(it, request_text, fresh_days=fresh_days, now=now)
        if ok:
            accepted.append(it)
        else:
            r = dict(it)
            r['_reject_reason'] = reason
            rejected.append(r)
    return accepted, rejected


# ── 4. compose dated, attributed, balanced sentences ──────────────────────────

_NEWS_PROMPT = """\
You are a careful news writer for a walking-tour audio guide in {locale}. Using \
ONLY the numbered ARTICLES below, write {max_items} short sentence(s) about \
recent developments connected to "{subject}" in {locale}. Rules you must follow \
exactly:

- RELEVANCE: write only about the "{subject}" that is in {locale}. If an article \
is about a same-named place or person somewhere ELSE, or is unrelated, IGNORE it.
- Ground every statement in the articles. Do NOT use any outside knowledge, and \
do NOT invent any quote, number, name or date that is not in an article.
- DATES — follow each article's WHEN line EXACTLY, and never invent a day:
  * If the header says 'DATE: YYYY-MM-DD (exact)', that calendar day is known. \
Begin the sentence with it written out, e.g. "On October 8, 2026, ...".
  * If the header says 'WHEN: <phrase> (approximate)', the exact day is NOT known. \
Begin the sentence with that approximate phrase EXACTLY as given, e.g. "Last \
month, ..." or "About three weeks ago, ...". You MUST NOT state or guess a \
specific day, date number or month name for these — doing so is a factual error.
  * Never write a specific date that is not printed in the header.
- POLITICAL BALANCE IS MANDATORY. If the item concerns a dispute or an election, \
report what EACH side said or did, attributed by name/party, with no editorialising \
and no adjective that favours a side.
- Attribute claims ("Governor Healey said ...", "according to the State House \
News Service ..."). End each sentence with its source number in brackets, like [2].
- If the articles contain nothing of substance about the subject in {locale}, \
reply with exactly: NO MATERIAL FOUND

ARTICLES:
{sources}
"""

_CITE = re.compile(r'\[(\d+)\]')
_NO_MATERIAL = 'NO MATERIAL FOUND'


def _openai_chat(prompt: str, model: str = NEWS_MODEL,
                 max_tokens: int = NEWS_ANSWER_MAX_TOKENS) -> Dict:
    """One OpenAI chat completion -> {'text','error'}. Metered at the network
    layer from the response body (model+usage)."""
    import requests
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        return {'text': '', 'error': 'no OPENAI_API_KEY'}
    try:
        r = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {key}',
                     'Content-Type': 'application/json'},
            json={'model': model, 'temperature': 0.1, 'max_tokens': max_tokens,
                  'messages': [{'role': 'user', 'content': prompt}]},
            timeout=60)
        r.raise_for_status()
        d = r.json()
        return {'text': d['choices'][0]['message']['content'] or '', 'error': ''}
    except Exception as e:
        return {'text': '', 'error': f'{type(e).__name__}: {e}'}


def _strip_cites(s: str) -> str:
    s = _CITE.sub('', s or '')
    s = re.sub(r'\s+([.,;:!?])', r'\1', s)
    s = re.sub(r'\s{2,}', ' ', s)
    return s.strip()


def compose_news_sentences(subject: str, articles: List[Dict],
                           max_items: int = 2,
                           answer: Optional[Callable] = None,
                           locale: str = '') -> Dict:
    """Write dated, attributed, balanced sentences grounded in `articles`.

    `articles` is [{title, source, date, snippet, text, link}]. `locale` is the
    tour's city/region, used to reject same-named places elsewhere. Returns
    {text, sources:[{source,url,date}], error}. `answer` injectable for tests.
    An empty/`NO MATERIAL FOUND` result returns text=''.
    """
    answer = answer or _openai_chat
    out = {'text': '', 'sources': [], 'error': ''}
    if not articles:
        return out
    blocks = []
    for i, a in enumerate(articles, 1):
        body = (a.get('text') or a.get('snippet') or '').strip()[:NEWS_PER_PAGE_CHARS]
        head = f"[{i}] {a.get('title','')} — {a.get('source','')}"
        # LOCAL-659 Defect 1: tell the composer EXACTLY what it may say about time.
        # An exact day is printed as 'DATE: YYYY-MM-DD (exact)'; a relative-only
        # item is printed as 'WHEN: <phrase> (approximate)' and the composer is
        # forbidden (in the prompt) from inventing a day for it.
        exact = a.get('_exact_date') or ''
        precision = a.get('_date_precision') or ''
        if exact and precision == DATE_EXACT:
            head += f"  DATE: {exact} (exact)"
        elif precision == DATE_APPROX:
            phrase = (a.get('_approx_phrase') or 'recently').strip()
            # capitalise for sentence-start use ("Last month", "About three weeks ago")
            phrase_cap = phrase[:1].upper() + phrase[1:] if phrase else 'Recently'
            head += f"  WHEN: {phrase_cap} (approximate — do NOT state a specific day)"
        elif a.get('_parsed_date'):
            # a bare resolved date with unknown precision — treat as exact day known
            head += f"  DATE: {a['_parsed_date']} (exact)"
        elif a.get('date'):
            head += f" ({a['date']})"
        blocks.append(f"{head}\n{body}")
    prompt = _NEWS_PROMPT.format(
        subject=subject, max_items=max_items,
        locale=(locale or 'the tour city'), sources="\n\n".join(blocks))
    ans = answer(prompt, model=NEWS_MODEL)
    if ans.get('error'):
        out['error'] = ans['error']
        return out
    text = (ans.get('text') or '').strip()
    if not text or (_NO_MATERIAL.lower() in text.lower()
                    and len(text) < len(_NO_MATERIAL) + 12):
        return out
    out['text'] = _strip_cites(text)
    # Record which numbered sources were actually cited.
    cited = sorted({int(n) for n in _CITE.findall(text)})
    for n in cited:
        if 1 <= n <= len(articles):
            a = articles[n - 1]
            out['sources'].append({'source': a.get('source', ''),
                                    'url': a.get('link', ''),
                                    'date': a.get('date', '')})
    if not out['sources']:  # no [n] markers — attribute to all used articles
        for a in articles:
            out['sources'].append({'source': a.get('source', ''),
                                   'url': a.get('link', ''),
                                   'date': a.get('date', '')})
    return out


# ── 5. research per stop ──────────────────────────────────────────────────────

# ── 4b. assign a news item to the stop it belongs to ──────────────────────────

# Signals that an item is STATE government (-> a "State House"/capitol stop) vs
# CITY government (-> a "City Hall" stop). Checked against the item text blob.
_STATE_GOV_WORDS = ('state house', 'statehouse', 'legislature', 'legislative',
                    'state senate', 'state house of representatives', 'governor',
                    'gubernatorial', 'state capitol', 'beacon hill', 'state rep',
                    'state representative', 'general court', 'house speaker')
_CITY_GOV_WORDS = ('city hall', 'city council', 'city councillor', 'councilmember',
                   'councilwoman', 'councilman', 'mayor', 'mayoral', 'alderman',
                   'board of selectmen', 'town hall', 'municipal')

_STOPWORDS = {'the', 'a', 'an', 'of', 'and', 'in', 'at', 'on', 'to', 'for',
              'house', 'hall', 'news', 'city', 'state', 'old', 'new'}


def _norm_name(s: str) -> str:
    return re.sub(r'[^a-z0-9 ]', ' ', (s or '').lower())


def _name_tokens(s: str) -> set:
    return {w for w in _norm_name(s).split() if w and w not in _STOPWORDS}


def _find_stop(stop_names: List[str], *keywords: str) -> Optional[str]:
    """First stop whose name contains any of the keywords (case-insensitive)."""
    for name in stop_names:
        nl = name.lower()
        if any(k in nl for k in keywords):
            return name
    return None


def _find_capitol_stop(stop_names: List[str]) -> Optional[str]:
    """The working STATE capitol stop, preferring it over the historical
    'Old State House'.

    Tour 618's duplicate came from treating both 'Old State House' (a Revolutionary
    museum/landmark) and 'State House' (the live Beacon Hill capitol) as the state
    stop. State-government news belongs ONLY at the live capitol. Preference:
      1. a stop named 'capitol',
      2. a 'state house'/'statehouse' stop that is NOT 'old state house',
      3. 'legislature'.
    'Old State House' alone is NOT returned here — it is a historical landmark, not
    the seat of state government."""
    for name in stop_names:
        if 'capitol' in name.lower():
            return name
    for name in stop_names:
        nl = name.lower()
        if ('state house' in nl or 'statehouse' in nl) and 'old state house' not in nl:
            return name
    for name in stop_names:
        if 'legislature' in name.lower():
            return name
    return None


def assign_item_to_stop(item: Dict, stop_names: List[str]) -> Optional[str]:
    """Pick the ONE stop a theme/news item belongs to.

    Rule (ticket): state government -> the 'State House'/capitol stop; city
    government -> the 'City Hall' stop. Otherwise fall back to the stop whose
    NAME shares the most meaningful tokens with the item's text; ties and
    no-overlap resolve to None (the item is theme-level and will be placed on the
    best government stop by the caller, or dropped if none fits)."""
    if not stop_names:
        return None
    blob = _item_text_blob(item)

    is_state = any(w in blob for w in _STATE_GOV_WORDS)
    is_city = any(w in blob for w in _CITY_GOV_WORDS)
    # When both fire, prefer the more specific "city hall"/"city council" only if
    # the state capitol words are absent as the dominant signal.
    if is_state and not is_city:
        s = _find_capitol_stop(stop_names)
        if s:
            return s
    if is_city and not is_state:
        s = _find_stop(stop_names, 'city hall', 'town hall', 'city council')
        if s:
            return s

    # Fallback: most NAME-token overlap with the item text words.
    item_words = set(_norm_name(blob).split())
    best, best_overlap = None, 0
    for name in stop_names:
        toks = _name_tokens(name)
        overlap = len(toks & item_words)
        if overlap > best_overlap:
            best, best_overlap = name, overlap
    if best_overlap > 0:
        return best
    # Still nothing: if exactly one of state/city fired but its canonical stop was
    # missing, hand it to the other government stop if present (capitol preferred).
    if is_state:
        return (_find_capitol_stop(stop_names)
                or _find_stop(stop_names, 'city hall', 'town hall', 'council'))
    if is_city:
        return (_find_stop(stop_names, 'city hall', 'town hall', 'city council')
                or _find_capitol_stop(stop_names))
    return None


# ── 5. research per stop ──────────────────────────────────────────────────────

def research_news_for_stops(request_text: str, stop_names: List[str],
                            *, serp: Optional[Callable] = None,
                            fetch: Optional[Callable] = None,
                            answer: Optional[Callable] = None,
                            max_articles: int = NEWS_MAX_ARTICLES_PER_STOP,
                            fresh_days: int = 365,
                            now: Optional["_dt.date"] = None) -> Dict:
    """Run the whole news research for a current-affairs tour.

    Pipeline (LOCAL-655B):
      1. Query Serper news for the THEME (derive_theme_queries) and for each STOP
         (derive_stop_queries), qdr:m widening to qdr:y.
      2. GATE every returned item deterministically (place / theme / dated-in-
         window) BEFORE any article is fetched or composed. Rejections are logged
         with a reason. Undated and wrong-place/off-theme items are dropped here.
      3. For accepted items, fetch the article page, then re-GATE on the fuller
         text (an item that passed on a thin snippet but whose full text names a
         different state is dropped).
      4. ASSIGN each surviving item to exactly ONE stop (state gov -> State House,
         city gov -> City Hall, else most name-overlap). An item (by link) is
         placed on one stop only — no duplicate across stops.
      5. COMPOSE dated/attributed/balanced sentences per stop from its items.

    Returns:
        {
          'by_stop': {stop_name: {text, sources, articles}},
          'queries': [str],              # every query actually issued
          'result_counts': {query: n},   # items returned per query
          'accepted': [{title,source,date,link,stop,reason}],
          'rejected': [{title,source,date,link,reason}],
          'articles_fetched': int,
          'items_total': int,
          'searched': bool,
        }
    `serp`/`fetch`/`answer` are injectable for tests (default to metered helpers).
    """
    serp = serp or _serp_news
    fetch = fetch or _fetch_article
    answer = answer or _openai_chat
    today = now or _dt.date.today()

    log = {'by_stop': {}, 'queries': [], 'result_counts': {},
           'accepted': [], 'rejected': [],
           'articles_fetched': 0, 'items_total': 0, 'searched': False}

    def _run_queries(queries: List[str]) -> List[Dict]:
        items: List[Dict] = []
        for q in queries:
            if q in log['result_counts']:
                continue  # don't re-issue an identical query
            log['queries'].append(q)
            log['searched'] = True
            got, _tbs = news_for_query(q, serp=serp)
            log['result_counts'][q] = len(got)
            log['items_total'] += len(got)
            items.extend(got)
        return _rank_items(items)

    # 1. gather candidates from BOTH the theme queries and every stop query.
    theme_queries = derive_theme_queries(request_text)
    all_queries = list(theme_queries)
    for name in stop_names:
        all_queries.extend(derive_stop_queries(name, request_text))
    candidates = _run_queries(all_queries)

    # 2. gate on title+snippet (pre-fetch).
    accepted0, rejected0 = gate_items(candidates, request_text,
                                      fresh_days=fresh_days, now=today)
    for r in rejected0:
        log['rejected'].append({'title': r.get('title', ''),
                                 'source': r.get('source', ''),
                                 'date': r.get('date', ''),
                                 'link': r.get('link', ''),
                                 'reason': r.get('_reject_reason', '')})

    # 3. fetch + re-gate on fuller text; 4. assign to exactly one stop (dedup).
    seen_links = set()
    per_stop_articles: Dict[str, List[Dict]] = {}
    for it in accepted0:
        link = it.get('link', '')
        if link and link in seen_links:
            continue
        # fetch() may return either clean text (test fakes) or (text, pub_date)
        # (the real _fetch_article, which also reads the article's exact published
        # date from the page metadata — LOCAL-659 Defect 1).
        fetched = fetch(link) if link else ''
        pub_date = None
        if isinstance(fetched, tuple):
            text = fetched[0] or ''
            pub_date = fetched[1] if len(fetched) > 1 else None
        else:
            text = fetched or ''
        a = dict(it)
        a['text'] = text if (text and len(text) >= 120) else it.get('snippet', '')
        # re-gate with the fuller text so a thin-snippet pass is re-checked.
        ok, reason = gate_item(a, request_text, fresh_days=fresh_days, now=today)
        if not ok:
            log['rejected'].append({'title': a.get('title', ''),
                                     'source': a.get('source', ''),
                                     'date': a.get('date', ''),
                                     'link': link,
                                     'reason': f'post-fetch: {reason}'})
            continue
        # LOCAL-659 Defect 1: if the article's own metadata gave an EXACT published
        # date, upgrade the item from approximate ("last month") to exact — a day
        # we can state because the ARTICLE declares it, never arithmetic from a
        # relative Serper string. Only accept a meta date inside the window.
        if pub_date is not None:
            age = (today - pub_date).days
            if 0 <= age <= fresh_days:
                a['_parsed_date'] = pub_date.isoformat()
                a['_exact_date'] = pub_date.isoformat()
                a['_date_precision'] = DATE_EXACT
                a['_approx_phrase'] = ''
                a['_date_source'] = 'article meta'
        else:
            a.setdefault('_date_source',
                         'approximate (relative Serper date)'
                         if a.get('_date_precision') == DATE_APPROX
                         else 'Serper date')
        stop = assign_item_to_stop(a, stop_names)
        if not stop:
            log['rejected'].append({'title': a.get('title', ''),
                                     'source': a.get('source', ''),
                                     'date': a.get('date', ''),
                                     'link': link,
                                     'reason': 'no stop to assign (no government '
                                               'stop / no name overlap)'})
            continue
        if link:
            seen_links.add(link)
        bucket = per_stop_articles.setdefault(stop, [])
        if len(bucket) < max_articles:
            bucket.append(a)
            log['articles_fetched'] += 1
            log['accepted'].append({'title': a.get('title', ''),
                                    'source': a.get('source', ''),
                                    'date': a.get('date', ''),
                                    'link': link, 'stop': stop,
                                    'reason': reason,
                                    'date_precision': a.get('_date_precision', ''),
                                    'resolved_date': a.get('_parsed_date', ''),
                                    'date_source': a.get('_date_source', '')})

    # 5. compose per stop. The composer writes about the tour's THEME SUBJECT
    # (e.g. "Massachusetts politics"), NOT the narrow stop building name — an
    # article about the governor's debate is current affairs for the State House
    # stop even though it never names the building. Passing the building name as
    # the subject made the cheap model answer NO MATERIAL FOUND for clearly
    # on-theme items (observed in the LOCAL-659 live run). The item is still
    # PLACED at its assigned stop; only the composer's framing uses the theme.
    theme_subject = _theme_subject(request_text) or request_text
    for stop, articles in per_stop_articles.items():
        if not articles:
            continue
        composed = compose_news_sentences(theme_subject, articles, answer=answer,
                                          locale=_region_phrase(request_text))
        if composed.get('text'):
            log['by_stop'][stop] = {
                'text': composed['text'],
                'sources': composed['sources'],
                'articles': articles,
            }
    return log


# ── 6. inject into the delivered tour text (additive, idempotent) ─────────────

_NEWS_MARK = "In recent news:"


def _split_stops(text: str) -> List[Tuple[int, int, str]]:
    """Return [(start, end, stop_name)] spans for each 'Stop N:' block."""
    spans = []
    matches = list(_STOP_HEADER_RE.finditer(text or ''))
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        spans.append((start, end, m.group(2).strip()))
    return spans


def _match_stop_key(delivered_name: str, keys: List[str]) -> Optional[str]:
    """Best-effort match a delivered stop header to a researched stop key."""
    dn = (delivered_name or '').lower().strip()
    for k in keys:
        kl = k.lower().strip()
        if kl == dn or kl in dn or dn in kl:
            return k
    return None


def inject_news_into_text(text: str, by_stop: Dict[str, Dict]) -> Tuple[str, int]:
    """Add each stop's dated news sentences to the end of that stop's narration.

    Additive and idempotent: a stop that already carries the news marker is left
    untouched. The news paragraph is placed as the last narration paragraph of the
    stop, before any trailing 'Directions:'/'Sources:' line. Returns (text, n_added).
    """
    if not text or not by_stop:
        return text, 0
    spans = _split_stops(text)
    if not spans:
        return text, 0
    keys = list(by_stop.keys())
    # Build the new text by walking spans in order.
    out_parts = []
    cursor = 0
    n_added = 0
    for (start, end, name) in spans:
        out_parts.append(text[cursor:start])
        block = text[start:end]
        key = _match_stop_key(name, keys)
        if key and _NEWS_MARK not in block:
            news_text = by_stop[key]['text'].strip()
            if news_text:
                srcs = by_stop[key].get('sources') or []
                src_names = []
                for s in srcs:
                    sn = (s.get('source') or '').strip()
                    if sn and sn not in src_names:
                        src_names.append(sn)
                attrib = _attribution_suffix(news_text, src_names)
                para = f"{_NEWS_MARK} {news_text}{attrib}"
                block = _insert_news_paragraph(block, para)
                n_added += 1
        out_parts.append(block)
        cursor = end
    out_parts.append(text[cursor:])
    return "".join(out_parts), n_added


def _attribution_suffix(news_text: str, src_names: List[str]) -> str:
    """Return the trailing '(Reported by …)' parenthetical, OMITTING any source
    the sentences already name in-text, and dropping the parenthetical entirely
    when every source is already attributed there (ticket item 3).

    The composer is instructed to attribute each claim in prose ("according to the
    State House News Service", "Governor Healey said"). When it does, repeating
    the same outlet in a trailing "(Reported by X, Y.)" is redundant and reads
    poorly aloud. So we keep in the parenthetical only the outlets NOT yet named in
    the sentences; if that leaves nothing, there is no parenthetical."""
    tl = (news_text or '').lower()
    missing = [sn for sn in src_names if sn.lower() not in tl]
    if not missing:
        return ""
    return f" (Reported by {', '.join(missing)}.)"


def _insert_news_paragraph(block: str, para: str) -> str:
    """Insert `para` as a new paragraph before a trailing Directions:/Sources:
    line in a stop block, else at the end of the block."""
    # find a trailing "Directions:" or "Sources:" paragraph
    m = re.search(r"(?m)^(Directions:|Sources:)", block)
    if m:
        head = block[:m.start()].rstrip()
        tail = block[m.start():]
        return f"{head}\n\n{para}\n\n{tail}"
    return f"{block.rstrip()}\n\n{para}\n"


def append_honest_note(text: str, log: Dict) -> Tuple[str, bool]:
    """Append the honest note ONCE, only when a search ran and yielded nothing
    usable. Idempotent. Returns (text, appended)."""
    if not log.get('searched'):
        return text, False
    if log.get('by_stop'):
        return text, False
    if HONEST_NOTE in (text or ''):
        return text, False
    sep = '' if (text or '').endswith('\n') else '\n'
    return f"{text}{sep}\n{HONEST_NOTE}\n", True


# ── CLI spot check ────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='Current-affairs news research (LOCAL-655)')
    ap.add_argument('request', help='the tour request string')
    ap.add_argument('--stop', action='append', default=[], help='a stop name (repeatable)')
    a = ap.parse_args()
    print(f"wants_current_affairs={wants_current_affairs(a.request)}")
    print(f"theme queries={derive_theme_queries(a.request)}")
    for s in a.stop:
        print(f"stop '{s}' queries={derive_stop_queries(s, a.request)}")
    if a.stop:
        t0 = time.time()
        res = research_news_for_stops(a.request, a.stop)
        print(json.dumps(res['by_stop'], indent=2, ensure_ascii=False))
        print(f"[{time.time()-t0:.1f}s] queries={res['queries']} "
              f"counts={res['result_counts']} articles={res['articles_fetched']} "
              f"searched={res['searched']}")
