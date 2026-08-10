"""exhibition_checklist.py — LOCAL-364/368: Retrieve exhibition checklists from venue sites.

When a user requests a tour of a NAMED EXHIBITION at a venue, the correct answer
is the works in THAT exhibition — not all works by the headline artists. This
module discovers the exhibition page, extracts the works on display, and checks
whether the show is still running.

Design choices:
- Exhibition data uses a 3-day TTL (not the 30-day venue_cache TTL) because
  exhibitions rotate. A stale checklist is actively harmful.
- Crawl paths are discovered, not hardcoded: tries /exhibitions, /exhibition,
  /whats-on, /on-view, /en/exhibitions, and any link from the base page
  whose text/href matches exhibition patterns.
- Title matching is fuzzy: handles punctuation, subtitle, and word-order
  differences between what the user typed and what the venue publishes.
- LOCAL-368: When the exhibition page publishes only prose (not structured
  Title/Artist/Year rows), an LLM extracts works from the prose. This is the
  `prose_llm` path — cheaper than a headless browser and correct for pages
  like the MFA's "Picasso, Miró, Dalí: Unbound" which names works in flowing
  paragraphs and image captions.
- LOCAL-368: Non-venue sources require a phrase-uniqueness gate: the exact
  exhibition phrase in order + exhibition-context words nearby. The venue's own
  domain is top tier and needs no corroboration.
"""

import json
import os
import re
import logging
import unicodedata
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests

logger = logging.getLogger(__name__)

# ─── TTL ──────────────────────────────────────────────────────────────────────
# Exhibition data must NOT use the 30-day venue_cache TTL.  Exhibitions rotate
# every few weeks/months.  A 3-day TTL means we re-check the venue site at most
# every 3 days, which is conservative enough for travelling shows.
EXHIBITION_CACHE_TTL_DAYS = 3

# ─── Exhibition URL path patterns to discover ─────────────────────────────────
_EXHIBITION_PATH_SEEDS = [
    '/exhibitions',
    '/exhibition',
    '/whats-on',
    '/on-view',
    '/en/exhibitions',
    '/en/whats-on',
    '/art/exhibitions',
    '/visit/exhibitions',
    '/programs/exhibitions',
]

_EXHIBITION_LINK_PATTERNS = re.compile(
    r'(?:exhibition|whats.on|on.view|expositions?|current.shows?|now.on.view)',
    re.IGNORECASE
)

# ─── Date extraction patterns ─────────────────────────────────────────────────
_DATE_RANGE_PATTERNS = [
    # "October 5, 2024 – March 9, 2025" / "Oct 5, 2024—Mar 9, 2025"
    re.compile(
        r'(\w+\.?\s+\d{1,2},?\s+\d{4})\s*[–—-]\s*(\w+\.?\s+\d{1,2},?\s+\d{4})',
        re.IGNORECASE
    ),
    # "5 October 2024 – 9 March 2025" (European format)
    re.compile(
        r'(\d{1,2}\s+\w+\s+\d{4})\s*[–—-]\s*(\d{1,2}\s+\w+\s+\d{4})',
        re.IGNORECASE
    ),
    # "Through March 9, 2025" / "Closes March 9, 2025"
    re.compile(
        r'(?:through|closes?|closing|until|ends?)\s+(\w+\.?\s+\d{1,2},?\s+\d{4})',
        re.IGNORECASE
    ),
    # "2024-10-05 to 2025-03-09"
    re.compile(
        r'(\d{4}-\d{2}-\d{2})\s*(?:to|–|—|-)\s*(\d{4}-\d{2}-\d{2})'
    ),
]

_DATE_FORMATS = [
    '%B %d, %Y',      # October 5, 2024
    '%B %d %Y',       # October 5 2024
    '%b %d, %Y',      # Oct 5, 2024
    '%b %d %Y',       # Oct 5 2024
    '%d %B %Y',       # 5 October 2024
    '%d %b %Y',       # 5 Oct 2024
    '%Y-%m-%d',       # 2024-10-05
]


def _parse_date_flexible(text: str) -> Optional[date]:
    """Try multiple date formats, return date or None."""
    text = text.strip().replace(',', ', ').replace('  ', ' ').strip()
    # Normalize dots in abbreviated months: "Oct." → "Oct"
    text = re.sub(r'(\w{3})\.', r'\1', text)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _fetch_page(url: str, timeout: int = 15) -> Tuple[str, List[Tuple[str, str]]]:
    """Fetch a page and return (text, links). Reuses story_miner pattern."""
    try:
        resp = requests.get(
            url,
            headers={'User-Agent': 'Audioura/2.2 ExhibitionChecker'},
            timeout=timeout,
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return '', []
    except Exception as e:
        logger.debug(f"exhibition_checklist: fetch failed for {url}: {e}")
        return '', []

    html = resp.text

    # Extract links (filter out very long hrefs which are likely JS artifacts)
    links = []
    for m in re.finditer(r'<a\s+[^>]*href=["\']([^"\']{1,300})["\'][^>]*>(.*?)</a>', html, re.DOTALL):
        href = m.group(1)
        link_text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        if link_text and len(link_text) < 200:
            links.append((link_text, href))

    # Extract paragraph text
    paragraphs = []
    for p_match in re.finditer(r'<p[^>]*>(.*?)</p>', html, re.DOTALL):
        clean = re.sub(r'<[^>]+>', '', p_match.group(1)).strip()
        clean = re.sub(r'&nbsp;', ' ', clean)
        clean = re.sub(r'&[a-z]+;', ' ', clean)
        if len(clean) > 20:
            paragraphs.append(clean)

    # Extract headings (h1-h4)
    headings = []
    for h_match in re.finditer(r'<h[1-4][^>]*>(.*?)</h[1-4]>', html, re.DOTALL):
        clean = re.sub(r'<[^>]+>', '', h_match.group(1)).strip()
        if clean and len(clean) < 200:
            headings.append(clean)

    # Extract figure captions
    figcaptions = []
    for fig_match in re.finditer(r'<figcaption[^>]*>(.*?)</figcaption>', html, re.DOTALL):
        clean = re.sub(r'<[^>]+>', '', fig_match.group(1)).strip()
        if clean and len(clean) > 5:
            figcaptions.append(clean)

    # Extract image alt text that looks like artwork descriptions
    img_alts = []
    for img_match in re.finditer(r'<img[^>]*alt="([^"]{10,200})"', html):
        alt = img_match.group(1).strip()
        # Keep alts that look like artwork descriptions (contain comma or "by")
        if ',' in alt or ' by ' in alt.lower():
            img_alts.append(alt)

    # Also extract list items (some exhibitions list works in <li> or <ul>)
    list_items = []
    for li_match in re.finditer(r'<li[^>]*>(.*?)</li>', html, re.DOTALL):
        clean = re.sub(r'<[^>]+>', '', li_match.group(1)).strip()
        if len(clean) > 5 and len(clean) < 200:
            list_items.append(clean)

    # Combine: headings first, then figure captions, img alts, paragraphs, list items
    full_text = '\n'.join(headings + figcaptions + img_alts + paragraphs + list_items)
    return full_text, links


def _normalize_for_match(text: str) -> str:
    """Normalize text for fuzzy title matching: lowercase, strip punct, collapse space."""
    # Decompose accents
    nfkd = unicodedata.normalize('NFKD', text.lower())
    stripped = ''.join(c for c in nfkd if not unicodedata.combining(c))
    # Remove punctuation except spaces
    stripped = re.sub(r'[^\w\s]', ' ', stripped)
    # Collapse whitespace
    return re.sub(r'\s+', ' ', stripped).strip()


def _title_similarity(requested: str, published: str) -> float:
    """Compute word-overlap similarity between requested and published exhibition titles.
    
    Returns a score between 0 and 1. Handles:
    - Word-order differences
    - Subtitles/colons
    - Extra punctuation
    - Partial matches (user might omit the subtitle)
    """
    req_norm = _normalize_for_match(requested)
    pub_norm = _normalize_for_match(published)

    if req_norm == pub_norm:
        return 1.0

    # Check if one contains the other (user typed a prefix/suffix)
    if req_norm in pub_norm or pub_norm in req_norm:
        shorter = min(len(req_norm.split()), len(pub_norm.split()))
        longer = max(len(req_norm.split()), len(pub_norm.split()))
        return shorter / longer if longer > 0 else 0.0

    # Word-level Jaccard with prefix matching
    req_words = set(req_norm.split())
    pub_words = set(pub_norm.split())

    # Remove very short words and common stop words
    _stop = {'the', 'a', 'an', 'at', 'in', 'of', 'and', 'or', 'to', 'for'}
    req_words = {w for w in req_words if len(w) > 2 and w not in _stop}
    pub_words = {w for w in pub_words if len(w) > 2 and w not in _stop}

    if not req_words or not pub_words:
        return 0.0

    # Count matches (allowing prefix matching for truncated words)
    matches = 0
    for rw in req_words:
        for pw in pub_words:
            if rw == pw or rw.startswith(pw) or pw.startswith(rw):
                matches += 1
                break

    # Jaccard-like: matches / union size
    union_size = len(req_words | pub_words)
    return matches / union_size if union_size > 0 else 0.0


# ─── Work extraction from exhibition pages ───────────────────────────────────

_WORK_TITLE_PATTERN = re.compile(
    r'^(?:'
    r'[A-Z\u00C0-\u024F][\w\s\-\u00C0-\u024F]{2,60}'  # Proper-noun-like title
    r')'
)

# Patterns that indicate a line is a work title (with optional artist attribution)
_WORK_LINE_PATTERNS = [
    # "Title, Artist Name, YYYY" or "Title (YYYY)"
    re.compile(r'^(.+?),\s+([A-Z][\w\s\-]+),\s*(\d{4})', re.UNICODE),
    # "Artist Name. Title. YYYY." or "Artist Name, Title, medium"
    re.compile(r'^([A-Z][\w\s\-\.]+)\.\s+(.+?)\.?\s*(?:\d{4}|$)', re.UNICODE),
    # "Title by Artist" 
    re.compile(r'^(.+?)\s+by\s+([A-Z][\w\s\-]+)', re.UNICODE),
    # Plain heading (h2/h3 content) — likely a work title on exhibition pages
    re.compile(r'^([A-Z\u00C0-\u024F][\w\s\-\u00C0-\u024F,\'\"]{3,80})$', re.UNICODE),
]

# Lines to skip (navigation, calls to action, etc.)
_SKIP_LINE_PATTERNS = re.compile(
    r'(?:^(?:back\s+to|view\s+all|see\s+(?:all|more)|load\s+more|'
    r'buy\s+tickets?|plan\s+your\s+visit|share\s+this|'
    r'image\s+credit|photo|©|copyright|'
    r'related\s+exhibitions?|you\s+may\s+also|'
    r'sponsored\s+by|presented\s+by|organized\s+by|'
    r'press\s+release|media\s+contact))',
    re.IGNORECASE
)


def extract_works_from_exhibition_page(text: str, links: List[Tuple[str, str]]) -> List[Dict]:
    """Extract artwork titles/artists from an exhibition page's content.
    
    Handles multiple page shapes:
    1. Structured checklist: works listed as Title, Artist, Date
    2. Highlights list: selected works with descriptions
    3. Embedded captions: "Artist, Title, Date" in figure/img captions
    4. Prose-only: no extractable individual works (returns empty)
    
    Returns list of dicts with 'title' and optionally 'artist', 'date'.
    """
    works = []
    seen_titles_norm = set()
    lines = text.split('\n')

    # Additional navigation/noise patterns specific to exhibition pages
    _NOISE_PATTERNS = re.compile(
        r'(?:^(?:back\s+to|view\s+all|see\s+(?:all|more)|load\s+more|'
        r'buy\s+tickets?|plan\s+your\s+visit|share\s+this|'
        r'image\s+credit|photo|©|copyright|'
        r'related\s+exhibitions?|you\s+may\s+also|'
        r'sponsored\s+by|presented\s+by|organized\s+by|'
        r'press\s+release|media\s+contact|'
        r'sign\s+up|subscribe|newsletter|connect\s+with|'
        r'visit\s+us|footer|main\s+navigation|extras|'
        r'collections?\s*$|collections?\s+search|'
        r'step\s+inside|view\s+this\s+post|a\s+post\s+shared|'
        r'lead\s+support|fund\s+by|provided\s+by|'
        r'gallery\s*\(\s*gallery\s+\d)|'
        # Museum department/section names
        r'(?:libraries|archives|provenance|conservation|publications|'
        r'membership|research|education|learning|mfa\s+images|'
        r'center\s+for|collections?\s+management|institutional|'
        r'employment|internships?|volunteer|'
        r'(?:africa|americas|asia|europe|ancient|contemporary|'
        r'photography|jewelry|judaica|prints|textile|musical|'
        r'near\s+east|nubia|egypt|greece|rome|oceania|netherlandish)'
        r'(?:\s+and\s+|\s*$)))',
        re.IGNORECASE
    )

    # Pattern for geographic addresses that should not be treated as works
    _ADDRESS_PATTERN = re.compile(
        r'\b(?:\d{5}|avenue|street|boulevard|road|drive|lane|'
        r'massachusetts|boston|new\s+york|california)\b',
        re.IGNORECASE
    )

    # Pattern for "Artist Name, Work Title, Date/medium" OR "Title, Artist, Date"
    # Both are common. Disambiguation: the one that looks more like a person name is the artist.
    _COMMA_SEPARATED_WORK = re.compile(
        r'^([A-Z\u00C0-\u024F][\w\s\-\u00C0-\u024F\'\".]{2,60}?),\s+'  # First part
        r'([A-Z\u00C0-\u024F][\w\s\-\u00C0-\u024F\'\",()]{2,80}?)'  # Second part
        r'(?:,\s*(\d{4})\b)?$',  # Optional year
        re.UNICODE
    )

    def _looks_like_person_name(text: str) -> bool:
        """Heuristic: does this text look like a person's name?"""
        words = text.strip().split()
        if not (1 <= len(words) <= 4):
            return False
        # All words should start with uppercase
        if not all(w[0].isupper() for w in words if w):
            return False
        # Should not contain articles, prepositions
        _NAME_STOP = {'the', 'a', 'an', 'of', 'in', 'on', 'at', 'for', 'with', 'and', 'or'}
        lowered = [w.lower() for w in words]
        if any(w in _NAME_STOP for w in lowered):
            return False
        # Words that indicate this is NOT a person name but an artwork title:
        _TITLE_INDICATORS = {
            'study', 'portrait', 'self-portrait', 'landscape', 'still',
            'composition', 'untitled', 'view', 'scene', 'figure', 'figures',
            'abstract', 'night', 'morning', 'evening', 'blue', 'red', 'green',
            'period', 'dance', 'dream', 'memory', 'persistence', 'carnival',
            'reflecting', 'swans', 'elephants', 'farm', 'guitar', 'violin',
            'woman', 'man', 'girl', 'boy', 'child', 'mother', 'father',
            'head', 'seated', 'standing', 'reclining', 'sleeping', 'weeping',
        }
        if any(w.lower() in _TITLE_INDICATORS for w in words):
            return False
        # If it has exactly 2-3 words and all are simple capitalized words
        # (no special characters), it's likely a name
        return True

    # Pattern for italic titles: commonly "Artist, *Title*, date"
    _ITALIC_TITLE = re.compile(
        r'([A-Z\u00C0-\u024F][\w\s\-\.]+),\s+'  # Artist
        r'(?:\*|_|<em>|<i>)(.+?)(?:\*|_|</em>|</i>)'  # Italic title
        r'(?:,?\s*(\d{4}))?',  # Optional date
        re.UNICODE
    )

    for line in lines:
        line = line.strip()
        if not line or len(line) < 4 or len(line) > 300:
            continue
        if _NOISE_PATTERNS.search(line):
            continue
        if _SKIP_LINE_PATTERNS.search(line):
            continue
        if _ADDRESS_PATTERN.search(line):
            continue

        work = None

        # Try comma-separated pattern: "Part1, Part2, Year"
        # Could be "Title, Artist, Year" or "Artist, Title, Year"
        m = _COMMA_SEPARATED_WORK.match(line)
        if m:
            part1 = m.group(1).strip()
            part2 = m.group(2).strip().rstrip(',')
            year = m.group(3) if m.group(3) else ''
            
            # Disambiguate: which part is the artist?
            p1_is_name = _looks_like_person_name(part1)
            p2_is_name = _looks_like_person_name(part2)
            
            if p1_is_name and not p2_is_name:
                # "Artist, Title, Year"
                work = {'title': part2, 'artist': part1}
            elif p2_is_name and not p1_is_name:
                # "Title, Artist, Year"
                work = {'title': part1, 'artist': part2}
            elif p1_is_name and p2_is_name:
                # Both look like names — shorter one is more likely the artist
                if len(part1.split()) <= len(part2.split()):
                    work = {'title': part2, 'artist': part1}
                else:
                    work = {'title': part1, 'artist': part2}
            else:
                # Neither looks like a name — take the first as title
                work = {'title': part1, 'artist': part2}
            
            if year:
                work['date'] = year

        # Try other structured patterns if inline didn't match
        if not work:
            for pattern in _WORK_LINE_PATTERNS:
                m_pat = pattern.match(line)
                if m_pat:
                    groups = m_pat.groups()
                    if len(groups) >= 2:
                        if len(groups) == 3:
                            work = {'title': groups[0].strip(), 'artist': groups[1].strip(),
                                    'date': groups[2].strip()}
                        elif len(groups) == 2:
                            work = {'title': groups[1].strip() if '.' in groups[0] else groups[0].strip(),
                                    'artist': groups[0].strip() if '.' in groups[0] else groups[1].strip()}
                        elif len(groups) == 1:
                            work = {'title': groups[0].strip()}
                    break

        if work:
            title_norm = _normalize_for_match(work['title'])
            # Reject if too short, too long, or a duplicate
            if len(title_norm) < 3 or len(title_norm) > 100:
                continue
            if title_norm in seen_titles_norm:
                continue
            # Reject if it looks like a collection/department name
            if re.match(r'^(?:Africa|Americas|Asia|Europe|Photography|Jewelry|Judaica|'
                       r'Contemporary\s+Art|Musical\s+Instruments|Prints\s+and|'
                       r'Textile|Ancient)\b', work['title']):
                continue
            # Reject if it looks like a sentence (has verb-like patterns) and is long
            if (re.search(r'\b(?:is|are|was|were|has|have|will|can|the museum|visitors can)\b',
                         work['title'].lower()) and len(work['title'].split()) > 6):
                continue
            # Reject sponsor/credit patterns
            if re.search(r'\b(?:fund|support|provided|gallery\s*\(|sharf|torf)\b',
                        work['title'].lower()):
                continue
            seen_titles_norm.add(title_norm)
            works.append(work)

    # Also try to extract from linked sub-pages (exhibition detail pages often
    # link to individual work pages with descriptive link text)
    for link_text, href in links:
        if not link_text or len(link_text) < 4 or len(link_text) > 120:
            continue
        if _SKIP_LINE_PATTERNS.search(link_text):
            continue
        if _NOISE_PATTERNS.search(link_text):
            continue
        if _ADDRESS_PATTERN.search(link_text):
            continue
        # Link text that looks like a work title (proper-noun-like, not a nav label)
        lt_stripped = link_text.strip()
        href_lower = href.lower()
        if (lt_stripped[0].isupper() and
            not re.match(r'^(?:View|See|Read|Learn|Back|Home|About|Visit|Buy|Get|'
                        r'Sign|Subscribe|Connect|Collections|Africa|Americas|Asia|'
                        r'Europe|Ancient|Contemporary|Photography|Jewelry|'
                        r'Judaica|Prints|Textile|Musical)\b', lt_stripped) and
            ('/collection' in href_lower or '/object' in href_lower or
             '/art/' in href_lower or '/artwork' in href_lower)):
            title_norm = _normalize_for_match(lt_stripped)
            if title_norm not in seen_titles_norm and len(title_norm) > 3:
                seen_titles_norm.add(title_norm)
                works.append({'title': lt_stripped, 'source': 'link'})

    return works


def _extract_closing_date(text: str) -> Optional[date]:
    """Extract the exhibition closing date from page text."""
    for pattern in _DATE_RANGE_PATTERNS:
        m = pattern.search(text)
        if m:
            groups = m.groups()
            if len(groups) == 2:
                # Range: opening - closing
                closing = _parse_date_flexible(groups[1])
                if closing:
                    return closing
            elif len(groups) == 1:
                # "Through date" pattern
                closing = _parse_date_flexible(groups[0])
                if closing:
                    return closing
    return None


def _extract_opening_date(text: str) -> Optional[date]:
    """Extract the exhibition opening date from page text."""
    for pattern in _DATE_RANGE_PATTERNS:
        m = pattern.search(text)
        if m:
            groups = m.groups()
            if len(groups) == 2:
                opening = _parse_date_flexible(groups[0])
                if opening:
                    return opening
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# LOCAL-368: LLM prose extraction — extract works from exhibition page prose
# ═══════════════════════════════════════════════════════════════════════════════

_PROSE_LLM_SYSTEM_PROMPT = """\
You are an exhibition checklist extractor. Given the visible text from a museum \
exhibition page, extract every artwork/work mentioned with its metadata. Return \
ONLY a JSON array. Each element has these fields (omit any not stated on the page):
- "title": the work's title (string, required)
- "artist": the artist who created the work (string)
- "date": date or year of creation (string)
- "medium": materials or technique (string)
- "publisher": publisher name if stated (string)
- "credit_line": provenance/gift/bequest (string)

Rules:
- Extract ONLY what the page text explicitly states. Do NOT complete from your own knowledge.
- An artist named without a specific work title is NOT a work — skip it.
- Titles in italics (marked with * or _) are work titles.
- Do not invent titles, dates, or media not present in the text.
- Return [] if no specific works are identifiable.
"""


def prose_llm_extract_works(page_text: str, exhibition_name: str = '') -> List[Dict]:
    """Use an LLM to extract works from exhibition page prose/captions.

    LOCAL-368: When _WORK_LINE_PATTERNS fail (prose-only pages), this function
    sends the page text to GPT to extract structured work metadata. The input
    is typically 1-3K characters — no chunking needed.

    Returns list of dicts with at minimum 'title' and optionally artist/date/medium/etc.
    Returns empty list on failure (network error, no API key, empty extraction).
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning("prose_llm_extract_works: OPENAI_API_KEY not set")
        return []

    # Trim to essential content — strip navigation/footer noise
    # The page_text from _fetch_page already has headings + captions + paragraphs
    # but may include nav. Keep only the core (first 4000 chars after any
    # "About" section or the exhibition title).
    text_for_llm = page_text.strip()
    if len(text_for_llm) > 5000:
        text_for_llm = text_for_llm[:5000]

    if not text_for_llm or len(text_for_llm) < 50:
        return []

    user_prompt = (
        f"Exhibition: {exhibition_name}\n\n"
        f"Page text:\n{text_for_llm}\n\n"
        "Extract all artworks/works mentioned with their metadata. "
        "Return ONLY a JSON array."
    )

    try:
        model = os.environ.get("PROSE_LLM_MODEL", os.environ.get("TOUR_LLM_MODEL", "gpt-4o-mini"))
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": _PROSE_LLM_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.0,
                "max_tokens": 1500,
            },
            timeout=30,
        )
        if response.status_code != 200:
            logger.warning(f"prose_llm_extract_works: API returned {response.status_code}")
            return []

        content = response.json()['choices'][0]['message']['content'].strip()
        # Strip markdown code fences if present
        if content.startswith('```'):
            content = re.sub(r'^```(?:json)?\s*', '', content)
            content = re.sub(r'\s*```$', '', content)

        works = json.loads(content)
        if not isinstance(works, list):
            return []

        # Validate: each entry must have at least a title
        valid_works = []
        for w in works:
            if isinstance(w, dict) and w.get('title') and len(w['title'].strip()) > 2:
                clean = {'title': w['title'].strip()}
                if w.get('artist'):
                    clean['artist'] = w['artist'].strip()
                if w.get('date'):
                    clean['date'] = str(w['date']).strip()
                if w.get('medium'):
                    clean['medium'] = w['medium'].strip()
                if w.get('publisher'):
                    clean['publisher'] = w['publisher'].strip()
                if w.get('credit_line'):
                    clean['credit_line'] = w['credit_line'].strip()
                valid_works.append(clean)

        logger.info(f"prose_llm_extract_works: extracted {len(valid_works)} works from prose")
        return valid_works

    except (requests.RequestException, json.JSONDecodeError, KeyError, IndexError) as e:
        logger.warning(f"prose_llm_extract_works: failed: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# LOCAL-368: Phrase-uniqueness gate for non-venue sources
# ═══════════════════════════════════════════════════════════════════════════════

# Exhibition-context words that must appear near the matched phrase.
# Window: the phrase and these context words must co-occur within 500 characters.
# These words MUST be specific to exhibition/display contexts — generic words
# like "through" or "show" (which also means "demonstrate") cause false positives.
_EXHIBITION_CONTEXT_WORDS = re.compile(
    r'\b(?:exhibition|exhibit(?:ed|ing)?|on\s+view|on\s+display|'
    r'gallery\s+\d|retrospective|'
    r'curator|curated\s+by|currently\s+showing|featured\s+in|'
    r'installed\s+in|opens?\s+(?:on|in|this)|closes?\s+(?:on|in|this)|'
    r'runs?\s+through|on\s+view\s+through|'
    r'now\s+(?:on\s+view|showing|open))\b',
    re.IGNORECASE
)

_PHRASE_GATE_WINDOW = 500  # characters — used only to slice the inspection window

# [LEAD 2026-08-10] The gate requires a grammatical relationship, not proximity.
# Within this many characters of the phrase, either an exhibition noun must
# introduce it or an exhibition verb must take it as subject.
_PHRASE_GATE_ADJACENCY = 60  # characters

# "<phrase> opens August 1" / "<phrase> runs through January" / "<phrase> is on view"
_EXHIBITION_VERB_FOLLOWS = re.compile(
    r'^\W{0,3}(?:will\s+)?(?:opens?|opened|runs?|ran|closes?|closed|'
    r'continues?|features?|showcases?|presents?|brings?\s+together|'
    r'is\s+(?:on\s+view|open|showing)|remains?\s+on\s+view|'
    r'goes?\s+on\s+view)\b',
    re.IGNORECASE
)

# "the exhibition <phrase>" / "a show titled <phrase>" / "exhibition: <phrase>"
_EXHIBITION_NOUN_PRECEDES = re.compile(
    r'\b(?:exhibition|exhibit|show|retrospective|installation)\b'
    r'(?:\s+(?:titled|called|named|entitled))?\s*[:,\-—]?\s*'
    r'(?:the\s+|a\s+|an\s+)?\W{0,3}$',
    re.IGNORECASE
)


def _fold_accents_preserving_length(text: str) -> str:
    """
    Lowercase and fold accents WITHOUT changing string length.

    [LEAD 2026-08-10] The phrase gate needs offsets that are valid in the original
    text so it can inspect what immediately precedes and follows a match. The
    ordinary normalizer strips punctuation and so shifts every subsequent offset.
    Here each character maps to exactly one character: 'é' -> 'e', 'ó' -> 'o'.
    Characters that decompose to nothing usable are left as-is.
    """
    out = []
    for ch in text.lower():
        decomposed = unicodedata.normalize('NFKD', ch)
        base = ''.join(c for c in decomposed if not unicodedata.combining(c))
        out.append(base[0] if len(base) >= 1 else ch)
    return ''.join(out)


def _normalize_for_phrase_gate(text: str) -> str:
    """Normalize text for phrase matching: fold accents, lowercase, strip punctuation."""
    nfkd = unicodedata.normalize('NFKD', text.lower())
    stripped = ''.join(c for c in nfkd if not unicodedata.combining(c))
    # Remove punctuation, keep spaces
    stripped = re.sub(r'[^\w\s]', ' ', stripped)
    return re.sub(r'\s+', ' ', stripped).strip()


def phrase_uniqueness_gate(
    source_text: str,
    exhibition_phrase: str,
    is_venue_domain: bool = False,
) -> Tuple[bool, str]:
    """LOCAL-368: Michael's phrase-uniqueness test for non-venue sources.

    Rules:
    - The venue's own domain is top tier and always passes (is_venue_domain=True).
    - For any other source, BOTH conditions must hold:
      1. The exact requested phrase appears in the source text (word order preserved,
         accents folded, punctuation ignored).
      2. The phrase appears in exhibition context — within 500 characters of words
         like exhibition/exhibit/on view/show/gallery/retrospective/collection/etc.,
         or the phrase itself is in a heading.

    Co-occurrence of the same artists in prose WITHOUT that context is a coincidence
    and must NOT be accepted.

    Args:
        source_text: The text content of the external source
        exhibition_phrase: The exhibition name as typed by the user
        is_venue_domain: True if this source is on the venue's own website

    Returns:
        (passes, reason): bool and explanation string
    """
    if is_venue_domain:
        return True, "venue domain — top tier, no corroboration needed"

    if not source_text or not exhibition_phrase:
        return False, "empty source text or empty exhibition phrase"

    # Normalize both
    source_norm = _normalize_for_phrase_gate(source_text)
    phrase_norm = _normalize_for_phrase_gate(exhibition_phrase)

    if not phrase_norm:
        return False, "exhibition phrase is empty after normalization"

    # Condition 1: exact phrase (order-preserved) appears in source
    if phrase_norm not in source_norm:
        return False, (f"phrase '{exhibition_phrase}' not found in source "
                      f"(order-preserved, accent-folded)")

    # Condition 2: phrase appears in exhibition context
    # Find all occurrences of the phrase in the ORIGINAL source text
    # (not normalized — we need positions for the context window)
    source_lower = source_text.lower()
    phrase_lower = _normalize_for_phrase_gate(exhibition_phrase)

    # Search in normalized source for position, then check context in original
    phrase_pos = source_norm.find(phrase_norm)
    if phrase_pos == -1:
        return False, "phrase position not found (unexpected)"

    # [LEAD 2026-08-10] Locate the phrase in the ORIGINAL text, not by reusing the
    # normalized offset. Normalization strips punctuation and folds accents, so the
    # two strings have different lengths — "Picasso, Miró, Dalí: Unbound" loses four
    # characters — and the original code's "map back approximately" silently sliced
    # the wrong span. That misalignment made the adjacency checks read the wrong text.
    _tokens = [t for t in phrase_norm.split() if t]
    _phrase_re = re.compile(
        r'\W*'.join(re.escape(t) for t in _tokens),
        re.IGNORECASE | re.UNICODE
    )
    _m = _phrase_re.search(_fold_accents_preserving_length(source_text))
    if not _m:
        return False, "phrase position not found in original text (unexpected)"

    _p_start, _p_end = _m.start(), _m.end()
    orig_window_start = max(0, _p_start - _PHRASE_GATE_WINDOW)
    orig_window_end = min(len(source_text), _p_end + _PHRASE_GATE_WINDOW)
    orig_window = source_text[orig_window_start:orig_window_end]

    # [LEAD 2026-08-10] Proximity alone is too weak. A 500-character window is
    # roughly a paragraph, and almost any art-history text about these painters
    # mentions "exhibition" somewhere in it. The measured false positive:
    #
    #   "Picasso, Miro, Dali: Unbound by convention, these three revolutionized
    #    modern art. Each later received a major museum exhibition in Paris..."
    #
    # The phrase is running prose there ("Unbound by convention"), and
    # "exhibition" is incidental. Michael's point was that the source must treat
    # the phrase as the NAME OF A THING, so require a grammatical relationship,
    # not mere co-presence: an exhibition noun immediately before the phrase, or
    # an exhibition verb immediately after it.
    _tail = source_text[_p_end:_p_end + _PHRASE_GATE_ADJACENCY]
    _head = source_text[max(0, _p_start - _PHRASE_GATE_ADJACENCY):_p_start]

    if _EXHIBITION_VERB_FOLLOWS.match(_tail):
        return True, "phrase is the subject of an exhibition verb — treated as a name"
    if _EXHIBITION_NOUN_PRECEDES.search(_head):
        return True, "phrase is introduced by an exhibition noun — treated as a name"

    # A heading is a name by position: a short line with no sentence punctuation.
    for line in source_text.split('\n'):
        line_stripped = line.strip()
        if (len(line_stripped) < 150 and
            '.' not in line_stripped and
            _normalize_for_phrase_gate(line_stripped).find(phrase_norm) != -1):
            return True, "phrase found in heading-like context"

    return False, (f"phrase '{exhibition_phrase}' appears in the source but is not "
                  f"used as an exhibition name (no exhibition noun within "
                  f"{_PHRASE_GATE_ADJACENCY} chars before it, no exhibition verb "
                  f"after it, not a heading) — likely coincidental co-occurrence")


# ═══════════════════════════════════════════════════════════════════════════════
# Main API
# ═══════════════════════════════════════════════════════════════════════════════

class ExhibitionChecklistResult:
    """Result of an exhibition checklist retrieval attempt."""

    def __init__(self):
        self.works: List[Dict] = []           # Extracted works [{title, artist?, date?}]
        self.exhibition_title: str = ''       # Official title as published
        self.exhibition_url: str = ''         # URL where checklist was found
        self.opening_date: Optional[date] = None
        self.closing_date: Optional[date] = None
        self.is_closed: bool = False          # True if show has closed
        self.path: str = 'none'               # 'checklist', 'partial', 'prose_llm', 'fallback', 'closed', 'none'
        self.reason: str = ''                 # Human-readable explanation
        self.page_shape: str = ''             # Which extraction shape was used

    @property
    def has_works(self) -> bool:
        return len(self.works) > 0

    def __repr__(self):
        return (f"ExhibitionChecklistResult(path={self.path}, works={len(self.works)}, "
                f"title='{self.exhibition_title}', url='{self.exhibition_url}')")


def find_exhibition_checklist(
    venue_base_url: str,
    exhibition_name: str,
    venue_name: str = '',
) -> ExhibitionChecklistResult:
    """Find and extract the checklist for a named exhibition at a venue.
    
    Strategy:
    1. Try known exhibition path seeds on the venue domain
    2. Find the exhibition listing page
    3. Match the requested exhibition name (fuzzy)
    4. Navigate to the exhibition detail page
    5. Extract works and dates
    6. Check if the show is still open
    
    Args:
        venue_base_url: The venue's website base URL (from Wikidata P856)
        exhibition_name: The exhibition name as typed by the user
        venue_name: Optional venue name for better logging
        
    Returns:
        ExhibitionChecklistResult with works (if found) and metadata
    """
    result = ExhibitionChecklistResult()

    if not venue_base_url:
        result.path = 'fallback'
        result.reason = 'No venue website URL available'
        print(f"  [LOCAL-364] No venue URL — cannot search for exhibition page")
        return result

    parsed_base = urlparse(venue_base_url)
    base_domain = f"{parsed_base.scheme}://{parsed_base.netloc}"

    print(f"  [LOCAL-364] Searching for exhibition '{exhibition_name}' on {base_domain}")

    # ─── Step 1: Find exhibition listing pages ───────────────────────────────
    exhibition_listing_pages = []

    # Try seed paths
    for seed_path in _EXHIBITION_PATH_SEEDS:
        seed_url = f"{base_domain}{seed_path}"
        text, links = _fetch_page(seed_url)
        if text and len(text) > 100:
            exhibition_listing_pages.append({
                'url': seed_url, 'text': text, 'links': links
            })
            print(f"  [LOCAL-364] Found exhibition listing: {seed_url} ({len(text)} chars)")
            break  # Use the first hit

    # If no seed worked, try to find exhibition links from the venue home page
    if not exhibition_listing_pages:
        home_text, home_links = _fetch_page(venue_base_url)
        if home_links:
            for link_text, href in home_links:
                if _EXHIBITION_LINK_PATTERNS.search(link_text) or _EXHIBITION_LINK_PATTERNS.search(href):
                    full_url = urljoin(venue_base_url, href)
                    # Must be same domain
                    if urlparse(full_url).netloc == parsed_base.netloc:
                        text, links = _fetch_page(full_url)
                        if text and len(text) > 100:
                            exhibition_listing_pages.append({
                                'url': full_url, 'text': text, 'links': links
                            })
                            print(f"  [LOCAL-364] Found exhibition listing via home link: {full_url}")
                            break

    if not exhibition_listing_pages:
        result.path = 'fallback'
        result.reason = f'No exhibition section found on {base_domain}'
        print(f"  [LOCAL-364] No exhibition listing found on venue site")
        return result

    # ─── Step 2: Find the matching exhibition ─────────────────────────────────
    best_match_url = ''
    best_match_score = 0.0
    best_match_title = ''

    for listing in exhibition_listing_pages:
        # Check the listing page text for exhibition titles
        # Look in links first (they often have the exhibition name as link text)
        for link_text, href in listing['links']:
            if not link_text or len(link_text) < 4:
                continue
            score = _title_similarity(exhibition_name, link_text)
            if score > best_match_score and score >= 0.35:
                full_url = urljoin(listing['url'], href)
                if urlparse(full_url).netloc == parsed_base.netloc:
                    best_match_score = score
                    best_match_url = full_url
                    best_match_title = link_text

        # Also check headings in the listing text
        for line in listing['text'].split('\n'):
            line = line.strip()
            if not line or len(line) < 4 or len(line) > 200:
                continue
            score = _title_similarity(exhibition_name, line)
            if score > best_match_score and score >= 0.35:
                best_match_score = score
                best_match_title = line
                # We don't have a separate URL for this — it's on the listing page
                if not best_match_url:
                    best_match_url = listing['url']

    if not best_match_url:
        result.path = 'fallback'
        result.reason = (f'Exhibition "{exhibition_name}" not found in venue exhibition listings '
                        f'(best similarity score: {best_match_score:.2f})')
        print(f"  [LOCAL-364] No matching exhibition found (best score: {best_match_score:.2f})")
        return result

    print(f"  [LOCAL-364] Matched exhibition: '{best_match_title}' (score: {best_match_score:.2f})")
    print(f"  [LOCAL-364] Exhibition URL: {best_match_url}")
    result.exhibition_title = best_match_title
    result.exhibition_url = best_match_url

    # ─── Step 3: Fetch the exhibition detail page ─────────────────────────────
    detail_text, detail_links = _fetch_page(best_match_url)
    if not detail_text:
        result.path = 'fallback'
        result.reason = f'Exhibition page at {best_match_url} returned no content'
        return result

    # ─── Step 4: Check dates — is the exhibition still open? ──────────────────
    closing_date = _extract_closing_date(detail_text)
    opening_date = _extract_opening_date(detail_text)
    result.closing_date = closing_date
    result.opening_date = opening_date

    if closing_date:
        print(f"  [LOCAL-364] Exhibition dates: opens={opening_date}, closes={closing_date}")
        if closing_date < date.today():
            result.is_closed = True
            result.path = 'closed'
            result.reason = (f'Exhibition "{best_match_title}" closed on {closing_date}. '
                           f'A tour of a dismounted exhibition is not useful.')
            print(f"  [LOCAL-364] ⚠️  Exhibition CLOSED on {closing_date} — will not tour it")
            return result
    else:
        print(f"  [LOCAL-364] No closing date found — assuming exhibition is current")

    # ─── Step 5: Extract works from the exhibition page ───────────────────────
    works = extract_works_from_exhibition_page(detail_text, detail_links)

    if works:
        result.works = works
        if len(works) >= 3:
            result.path = 'checklist'
            result.page_shape = 'structured_checklist'
            result.reason = f'Extracted {len(works)} works from exhibition page'
        else:
            result.path = 'partial'
            result.page_shape = 'highlights_only'
            result.reason = f'Only {len(works)} works extractable (exhibition page shows highlights only)'
        print(f"  [LOCAL-364] Extracted {len(works)} works from exhibition page (shape: {result.page_shape})")
        for w in works[:10]:
            _artist_info = f" by {w['artist']}" if w.get('artist') else ''
            print(f"    - {w['title']}{_artist_info}")
        if len(works) > 10:
            print(f"    ... and {len(works) - 10} more")
    else:
        # ─── LOCAL-368: Prose-only page — try LLM extraction before fallback ──
        print(f"  [LOCAL-368] Line-pattern extraction found no works — trying LLM prose extraction")
        llm_works = prose_llm_extract_works(detail_text, exhibition_name)

        if llm_works:
            result.works = llm_works
            result.path = 'prose_llm'
            result.page_shape = 'prose_llm_extraction'
            result.reason = (f'Extracted {len(llm_works)} works from exhibition prose via LLM '
                           f'(page at {best_match_url} has no structured checklist)')
            print(f"  [LOCAL-368] ✓ PROSE LLM PATH: {len(llm_works)} works extracted from prose")
            print(f"    Source: {result.exhibition_url}")
            for w in llm_works[:10]:
                _artist_info = f" by {w['artist']}" if w.get('artist') else ''
                _date_info = f" ({w['date']})" if w.get('date') else ''
                print(f"    - {w['title']}{_artist_info}{_date_info}")
            if len(llm_works) > 10:
                print(f"    ... and {len(llm_works) - 10} more")
        else:
            # True prose-only: even LLM found nothing extractable
            result.path = 'fallback'
            result.page_shape = 'prose_only'
            result.reason = (f'Exhibition page at {best_match_url} contains only prose — '
                            f'no individual works could be extracted (regex and LLM both failed)')
            print(f"  [LOCAL-364] Exhibition page is prose-only — no checklist extractable "
                  f"(LLM extraction also returned empty)")

    return result
