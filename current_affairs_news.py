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


def derive_theme_queries(request_text: str) -> List[str]:
    """Theme-level news queries from the request. Deterministic."""
    theme = _theme_phrase(request_text)
    region = _region_phrase(request_text)
    out: List[str] = []
    if theme:
        out.append(theme if region and region.lower() in theme.lower()
                   else (f"{theme} {region}".strip() if region else theme))
    # a tighter "<region> politics current affairs" style query as a second angle
    if region:
        out.append(f"{region} latest news")
    seen, uniq = set(), []
    for q in out:
        q = re.sub(r'\s+', ' ', q).strip()
        if q and q.lower() not in seen:
            seen.add(q.lower())
            uniq.append(q)
    return uniq


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
    """Run one news query at qdr:m, widening to qdr:y when the month is empty.

    Returns (items, tbs_used). `serp` is injectable for tests."""
    serp = serp or _serp_news
    items = serp(query, 'qdr:m')
    if items:
        return items, 'qdr:m'
    items = serp(query, 'qdr:y')
    return items, 'qdr:y'


def _fetch_article(url: str) -> str:
    """Fetch an article page's clean text via the shared polite/cached helper."""
    try:
        from exhibition_checklist import _fetch_page
    except Exception:
        return ''
    try:
        text, _links = _fetch_page(url)
    except Exception:
        return ''
    text = text or ''
    if '<' in text[:200] and ('</' in text or '<p' in text.lower()):
        try:
            from robust_text_extractor import extract_clean_text
            text = extract_clean_text(text) or text
        except Exception:
            pass
    return text


def _rank_items(items: List[Dict]) -> List[Dict]:
    """Prefer items that carry a date, de-dupe by link, keep order otherwise."""
    seen, dated, undated = set(), [], []
    for it in items:
        link = it.get('link')
        if not link or link in seen:
            continue
        seen.add(link)
        (dated if it.get('date') else undated).append(it)
    return dated + undated


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

import datetime as _dt

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
_THEME_WORDS = {
    'politic', 'political', 'government', 'governor', 'gubernatorial', 'mayor',
    'mayoral', 'council', 'councillor', 'councilmember', 'councilwoman',
    'councilman', 'election', 'ballot', 'vote', 'voting', 'campaign', 'candidate',
    'legislature', 'legislative', 'legislator', 'senate', 'senator', 'house',
    'representative', 'congress', 'congressional', 'bill', 'law', 'statute',
    'policy', 'referendum', 'protest', 'rally', 'demonstration', 'march',
    'activist', 'civic', 'democrat', 'democratic', 'republican', 'gop',
    'statehouse', 'city hall', 'town hall', 'debate', 'primary', 'caucus',
    'commissioner', 'alderman', 'selectboard', 'veto', 'budget', 'hearing',
    'lawsuit', 'court', 'ruling', 'reform', 'measure', 'ordinance',
}

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


def parse_news_date(raw: str, now: Optional[_dt.date] = None) -> Optional[_dt.date]:
    """Parse a Serper-news date into a real calendar date, or None if undated.

    Serper returns either a relative string ("Six days ago", "4 days ago",
    "2 hours ago", "yesterday") or an absolute one ("Oct 8, 2026", "October 8,
    2026", "2026-10-08"). Returns the resolved date, or None when nothing parses —
    which the gate treats as UNDATED and drops."""
    s = (raw or '').strip()
    if not s:
        return None
    today = now or _dt.date.today()
    # relative
    m = _REL_RE.search(s)
    if m:
        low = s.lower()
        if 'today' in low:
            return today
        if 'yesterday' in low:
            return today - _dt.timedelta(days=1)
        qty_raw, unit = m.group(1), (m.group(2) or '').lower()
        qty = _WORD_NUM.get((qty_raw or '').lower(), None)
        if qty is None:
            try:
                qty = int(qty_raw)
            except (TypeError, ValueError):
                qty = None
        if qty is not None:
            if unit in ('second', 'minute', 'hour'):
                return today
            if unit == 'day':
                return today - _dt.timedelta(days=qty)
            if unit == 'week':
                return today - _dt.timedelta(days=7 * qty)
            if unit == 'month':
                return today - _dt.timedelta(days=30 * qty)
            if unit == 'year':
                return today - _dt.timedelta(days=365 * qty)
    # ISO
    mi = re.search(r'\b(\d{4})-(\d{2})-(\d{2})\b', s)
    if mi:
        try:
            return _dt.date(int(mi.group(1)), int(mi.group(2)), int(mi.group(3)))
        except ValueError:
            return None
    # "Month D, YYYY" or "D Month YYYY"
    mo = re.search(r'(?i)\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b', s)
    if mo and mo.group(1).lower() in _MONTHS:
        try:
            return _dt.date(int(mo.group(3)), _MONTHS[mo.group(1).lower()],
                            int(mo.group(2)))
        except ValueError:
            return None
    md = re.search(r'(?i)\b(\d{1,2})\s+([A-Za-z]{3,9})\.?\s+(\d{4})\b', s)
    if md and md.group(2).lower() in _MONTHS:
        try:
            return _dt.date(int(md.group(3)), _MONTHS[md.group(2).lower()],
                            int(md.group(1)))
        except ValueError:
            return None
    return None


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
    audit log) or 'ok: place+theme+date' on acceptance. Order: date, place, theme
    — date first so an undated item is reported as 'undated' regardless of place.

    fresh_days bounds how old a dated item may be. Serper is queried at qdr:m then
    widened to qdr:y, so the gate's window is the generous one-year bound by
    default (the caller passes 365 for a widened query, fewer for a tight one); the
    point of the gate is to KILL undated and clearly-stale items, not to re-impose
    the search tbs."""
    today = now or _dt.date.today()
    blob = _item_text_blob(item)

    # (c) DATE — must parse AND be inside the window. Undated -> drop.
    d = parse_news_date(item.get('date', ''), now=today)
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

    # (b) THEME — names at least one civic/politics theme word.
    if not any(w in blob for w in _THEME_WORDS):
        return False, 'off-theme (no politics/government/civic term)'

    # stash the resolved date on the item so the composer can state it exactly
    # (never a bare "Recently" when the gate has confirmed a real date).
    item['_parsed_date'] = d.isoformat()
    return True, f"ok: place({'city' if names_city else 'state'})+theme+dated({d.isoformat()})"


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
ONLY the numbered ARTICLES below, write {max_items} short, DATED sentence(s) about \
recent developments connected to "{subject}" in {locale}. Rules you must follow \
exactly:

- RELEVANCE: write only about the "{subject}" that is in {locale}. If an article \
is about a same-named place or person somewhere ELSE, or is unrelated, IGNORE it.
- Ground every statement in the articles. Do NOT use any outside knowledge, and \
do NOT invent any quote, number, name or date that is not in an article.
- Begin each sentence with the EXACT DATE of the development. Every article below \
is pre-verified to carry a real date, printed as "DATE: YYYY-MM-DD" in its header; \
use that date, written out (e.g. "On October 8, 2026, ..."). NEVER write "Recently" \
— every item here has a known date, so state it.
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
        # Prefer the gate-resolved ISO date (parse_news_date); fall back to the
        # raw Serper date string. The gate guarantees _parsed_date on accepted
        # items, so the composer always has an exact date to state.
        iso = a.get('_parsed_date') or ''
        if iso:
            head += f"  DATE: {iso}"
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
        text = fetch(link) if link else ''
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
                                    'reason': reason})

    # 5. compose per stop.
    for stop, articles in per_stop_articles.items():
        if not articles:
            continue
        composed = compose_news_sentences(stop, articles, answer=answer,
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
