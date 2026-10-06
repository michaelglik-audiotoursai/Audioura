"""[LOCAL-35] Structured visitor facts extraction from museum web pages.

Extracts structured fields: closed_days, hours (with seasonal ranges),
admission (with conditions), and formats them unambiguously for presentation.

Design principles:
- NEVER generates data — only returns what is literally found on the page.
- Conditional admission (e.g. "free for residents, €X otherwise") MUST be
  represented with the condition, never flattened to just "Free".
- Seasonal hours MUST be paired with their applicable period.
- If parsing fails, returns empty rather than emitting fragments.
"""

import re
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field


@dataclass
class VisitorFacts:
    """Structured visitor information extracted from a museum website."""
    closed_days: List[str] = field(default_factory=list)      # e.g. ["Tuesday"]
    # [LOCAL-592 r4] Each hours entry carries the DAY range the page bound to the
    # time range — hours without their days is a misleading half-fact (a Saturday
    # listener hears "9 AM–8 PM" as every day). 'days' is the spoken weekday range
    # ("Tuesday through Sunday", "Monday to Thursday"); '' only when the page truly
    # gives none, in which case the time is NOT stored (see extraction below).
    hours: List[Dict[str, str]] = field(default_factory=list)  # [{time: "10:00–18:00", period: "1 Apr–31 Oct", days: "Tuesday through Sunday"}]
    admission: str = ""                                         # e.g. "€10 / 48h pass; free for Métropole residents"
    source_url: str = ""

    def is_empty(self) -> bool:
        return not self.closed_days and not self.hours and not self.admission

    @staticmethod
    def _format_one_hours(h: Dict[str, str]) -> str:
        """Render one hours entry as 'Days, time (period)'.

        The day range (LOCAL-592 r4) leads the time range when the page bound one,
        so the fact is never a day-less half-truth. The seasonal period, when any,
        trails in parentheses exactly as before.
        """
        time = (h.get('time') or '').strip()
        if not time:
            return ''
        days = (h.get('days') or '').strip()
        period = (h.get('period') or '').strip()
        body = f"{days}, {time}" if days else time
        return f"{body} ({period})" if period else body

    def format_en(self) -> str:
        """Format all fields into a single English-language Museum Information string."""
        parts = []

        # Closed days
        if self.closed_days:
            if len(self.closed_days) == 1:
                parts.append(f"Closed on {self.closed_days[0]}")
            else:
                parts.append(f"Closed on {', '.join(self.closed_days)}")

        # Hours — each time range is spoken WITH the day range the page bound to
        # it (LOCAL-592 r4). "Tuesday through Sunday, Noon–4 PM" — never a bare
        # "Noon–4 PM" that a listener hears as every day.
        if self.hours:
            hour_parts = [self._format_one_hours(h) for h in self.hours]
            parts.append('; '.join(p for p in hour_parts if p))

        # Admission
        if self.admission:
            parts.append(self.admission)

        return '. '.join(parts) if parts else ""


# ============================================================
# FR → EN day/month translations
# ============================================================

_FR_TO_EN_DAYS = {
    'lundi': 'Monday', 'mardi': 'Tuesday', 'mercredi': 'Wednesday',
    'jeudi': 'Thursday', 'vendredi': 'Friday', 'samedi': 'Saturday',
    'dimanche': 'Sunday',
}

_FR_TO_EN_MONTHS = {
    'janvier': 'January', 'février': 'February', 'fevrier': 'February',
    'mars': 'March', 'avril': 'April', 'mai': 'May', 'juin': 'June',
    'juillet': 'July', 'août': 'August', 'aout': 'August',
    'septembre': 'September', 'octobre': 'October',
    'novembre': 'November', 'décembre': 'December', 'decembre': 'December',
}


def _translate_day(fr_day: str) -> str:
    """Translate a French day name to English."""
    return _FR_TO_EN_DAYS.get(fr_day.lower(), fr_day)


def _translate_month(fr_month: str) -> str:
    """Translate a French month name to English."""
    return _FR_TO_EN_MONTHS.get(fr_month.lower(), fr_month)


def _normalize_time(time_str: str) -> str:
    """Normalize French time formats to HH:MM.
    10h → 10:00, 10h30 → 10:30, 10:00 → 10:00, 10 am → 10:00
    """
    time_str = time_str.strip()
    # "10h30" or "10h"
    m = re.match(r'(\d{1,2})h(\d{2})?', time_str)
    if m:
        h = m.group(1).zfill(2)
        mi = m.group(2) or '00'
        return f"{h}:{mi}"
    # "10:30" or "10:00"
    m = re.match(r'(\d{1,2}):(\d{2})', time_str)
    if m:
        return f"{m.group(1).zfill(2)}:{m.group(2)}"
    # "10 am" / "5 pm"
    m = re.match(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', time_str, re.IGNORECASE)
    if m:
        h = int(m.group(1))
        mi = m.group(2) or '00'
        if m.group(3).lower() == 'pm' and h < 12:
            h += 12
        elif m.group(3).lower() == 'am' and h == 12:
            h = 0
        return f"{h:02d}:{mi}"
    return time_str


def _page_literal_time(raw: str) -> str:
    """Tidy a raw time token into a page-faithful display form (no 24h synthesis).

    "8 PM" -> "8 PM", "8 pm" -> "8 PM", "10am" -> "10 AM", "Noon" -> "Noon".
    This is used when a 24h normalisation would introduce a token (e.g. "20:00")
    that does NOT appear on the page — in that case we keep what the page says.
    """
    s = raw.strip()
    # "Noon" / "Midnight" are page-literal time words — keep them as the page says.
    if re.fullmatch(r'noon', s, re.IGNORECASE):
        return 'Noon'
    if re.fullmatch(r'midnight', s, re.IGNORECASE):
        return 'Midnight'
    m = re.match(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b', s, re.IGNORECASE)
    if m:
        hh = m.group(1)
        mm = m.group(2)
        mer = m.group(3).upper()
        return f"{hh}:{mm} {mer}" if mm else f"{hh} {mer}"
    return s


def _normalize_time_sourced(raw: str, source_lower: str) -> str:
    """[LOCAL-584] Normalise a time to 24h ONLY if the result maps to a page token.

    The LOCAL-35 extractor blindly rewrote "8 PM" to "20:00". For the Griffin
    Museum that produced "08:00–20:00" — a 24h schedule that appears NOWHERE on a
    page whose times are all AM/PM ("8 AM – 8 PM"). Rule (ticket #2): a normalised
    time is allowed only if every token it introduces maps back to a time token on
    the page; otherwise keep the page-literal form.

    We treat a normalised value "HH:MM" as page-supported when the source contains
    that exact 24h token (either "HH:MM" or the French "HHhMM"/"HHh"), i.e. the page
    really is a 24h page. If it is not, we fall back to _page_literal_time(raw) so
    the emitted hours use only tokens the reader can find on the page.
    """
    norm = _normalize_time(raw)
    m = re.match(r'(\d{1,2}):(\d{2})$', norm)
    if not m:
        # Not a clean 24h value (e.g. "Noon") — present the page-literal token.
        return _page_literal_time(raw)
    hh, mm = m.group(1), m.group(2)
    h_int = str(int(hh))
    # Does the SOURCE actually contain this 24h token? Accept "20:00", "20h00",
    # "20h", or (am/pm pages) the morning hour "8:00"/"08:00" when < 13.
    candidates = [f"{hh}:{mm}", f"{h_int}:{mm}", f"{h_int}h{mm}", f"{h_int}h", f"{hh}h{mm}"]
    if any(c in source_lower for c in candidates):
        return norm
    # The 24h token is NOT on the page. If the raw token itself is am/pm, keep that
    # (its tokens — "8 pm" — ARE on the page). Only synthesise 24h for pages that
    # are themselves 24h.
    if re.search(r'am|pm', raw, re.IGNORECASE):
        return _page_literal_time(raw)
    # Raw had no am/pm and no 24h support in source — safest is the page-literal raw.
    return _page_literal_time(raw)


# ============================================================
# [LOCAL-584] Currency is what the page says — never a default
# ============================================================

# Symbols/codes we recognise, mapped to the display symbol we emit. The € default
# that LOCAL-35 baked in rewrote a US museum's "$12" to "€12" (tour 391, Griffin
# Museum of Photography). Currency MUST be derived from the matched text itself —
# from the venue's language or a hard-coded default, NEVER.
_CURRENCY_SYMBOLS = ['€', '£', '$', '¥', '₩', '₹', '₽', 'CHF', 'kr', 'zł']
_CURRENCY_CODE_TO_SYMBOL = {
    'EUR': '€', 'GBP': '£', 'USD': '$', 'JPY': '¥', 'CNY': '¥',
    'CHF': 'CHF', 'SEK': 'kr', 'NOK': 'kr', 'DKK': 'kr', 'PLN': 'zł',
}


def _format_price(symbol: str, amount: str) -> str:
    """Render a price using the currency the page actually used.

    `symbol` is whatever was captured next to the amount (a symbol like '$'/'€',
    an ISO code like 'USD', or ''). An empty/None symbol means the page gave a
    bare number with no currency marker — we must NOT invent one, so we return the
    amount alone rather than guessing €. Codes are mapped to their symbol; a
    code/word currency (e.g. CHF) is written before the amount with a space.
    """
    s = (symbol or '').strip()
    if not s:
        # No currency marker on the page → state the number without a symbol.
        # Downstream the literal-token gate still requires the digits in source.
        return amount
    up = s.upper()
    if up in _CURRENCY_CODE_TO_SYMBOL:
        sym = _CURRENCY_CODE_TO_SYMBOL[up]
    else:
        sym = s
    # Multi-char/code currencies read better before the number with a space.
    if len(sym) > 1 or sym.isalpha():
        return f"{sym} {amount}"
    return f"{sym}{amount}"


# A price in ANY currency, used for scoring/merging (not just €). "$12", "€5",
# "£8", "12€", "CHF 10", or a bare "12" preceded by an admission context all count.
_ANY_PRICE_RE = re.compile(r'(?:€|£|\$|¥|₩|₹|₽|CHF|USD|GBP|EUR)\s*\d+|\d+\s*(?:€|£|\$|¥|EUR|USD|GBP|CHF)')


def _has_price(admission: str) -> bool:
    """True iff an admission string carries a numeric price in some currency."""
    return bool(_ANY_PRICE_RE.search(admission or ''))


# ============================================================
# [LOCAL-584 r2] Hours/closed-days belong to the VENUE, not a satellite gallery
# ============================================================
# Tour 391 told a listener the Griffin Museum opens "8 AM–8 PM"; that line is the
# Lafayette City Center *satellite* gallery's hours. The museum opens Tue–Sun,
# Noon–4 PM. The fix is structural: a visitor page that lists several places'
# hours is split into sections by its headings, and we read ONLY the section that
# belongs to the venue (its own name/address, or the venue-level "Hours"/"Admission"
# heading) — never a section under a heading that names a different place.

# A section boundary sentinel. Inserted ahead of every heading-like element while
# flattening HTML (h1..h6 and the emphasised sub-labels <strong>/<em>/<b>/<th>/
# <dt>/<summary> that WordPress-style pages use as sub-headings). Survives the
# whitespace collapse so the extractor can see where one place's block ends and
# the next begins, which a fully flattened page cannot show.
_SECTION_SENTINEL = '\x1e'

_HEADING_TAGS = ('h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                 'strong', 'b', 'em', 'th', 'dt', 'summary', 'figcaption')


def _html_to_sectioned_text(html: str) -> str:
    """Flatten HTML to text, but mark heading/sub-heading boundaries with a sentinel.

    The sentinel lets later code treat the page as an ordered list of sections
    ("Location", "Hours", "Satellite Galleries", "Admission", …) instead of one
    undifferentiated string. Non-heading markup is still dropped; whitespace is
    collapsed except that the sentinel is preserved.
    """
    if not html:
        return ''
    s = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    s = re.sub(r'<style[^>]*>.*?</style>', ' ', s, flags=re.DOTALL | re.IGNORECASE)
    # Mark the START of each heading-like element with a sentinel so the heading
    # text itself opens a new section.
    for tag in _HEADING_TAGS:
        s = re.sub(rf'<{tag}\b[^>]*>', _SECTION_SENTINEL, s, flags=re.IGNORECASE)
    # Drop every remaining tag.
    s = re.sub(r'<[^>]+>', ' ', s)
    # Collapse whitespace but keep the sentinel.
    s = re.sub(r'[^\S\x1e]+', ' ', s)
    s = re.sub(r'\s*\x1e\s*', _SECTION_SENTINEL, s)
    return s.strip()


# A heading is a FOREIGN-PLACE boundary when it names a place other than the venue.
# Structurally (not a stop-word list) a heading opens another place's block when it
# looks like a venue/building label — a proper-noun phrase ending in a place word
# (Gallery, Galleries, Center/Centre, Building, Museum, Annex, Pavilion, Wing, Hall,
# Site, Location, Branch) — AND it is not the venue's own name. "Satellite Galleries"
# matches via "Galleries"; "Lafayette City Center Gallery" via "Gallery"; the word
# "satellite" is never special-cased.
_PLACE_WORD_RE = re.compile(
    r'\b(galler(?:y|ies)|cent(?:er|re)|building|museum|annex(?:e)?|pavilion|'
    r'wing|hall|site|location|branch|house)\b',
    re.IGNORECASE,
)

# Venue-level (place-agnostic) section headings whose block DOES belong to the venue.
_VENUE_SECTION_HEADINGS = (
    'hours', 'opening hours', 'opening times', 'admission', 'tickets', 'prices',
    'pricing', 'fees', 'visit', 'visitor information', 'plan your visit',
    'getting here', 'location', 'address', 'contact',
    # FR
    'horaires', 'tarifs', 'informations pratiques', 'infos pratiques',
    'adresse', 'accès', 'acces', 'visite',
)


def _norm(s: str) -> str:
    return re.sub(r'\s+', ' ', (s or '')).strip().lower()


def _heading_names_other_place(heading: str, venue_name: str, venue_address: str) -> bool:
    """True if a section heading opens a DIFFERENT place's block (not the venue).

    Returns False for venue-level headings (Hours/Admission/…), for a heading that
    repeats the venue's own name, and for a heading carrying the venue's street
    address. Returns True only for a proper place label (ends/contains a place word
    like Gallery/Center/Building) that is not the venue.
    """
    h = _norm(heading)
    if not h:
        return False
    # Venue-level section labels keep the block with the venue.
    for vs in _VENUE_SECTION_HEADINGS:
        if h == vs or h.startswith(vs + ' ') or h == vs + ':':
            return False
    # The venue's own name / address never bounds the venue out of its own block.
    vn = _norm(venue_name)
    if vn:
        # Share a distinctive token (>=4 chars) with the venue name → same place.
        v_tokens = {t for t in re.findall(r'[a-zàâäéèêëîïôöùûüç]{4,}', vn)}
        h_tokens = {t for t in re.findall(r'[a-zàâäéèêëîïôöùûüç]{4,}', h)}
        if v_tokens & h_tokens:
            return False
    va = _norm(venue_address)
    if va:
        # A street-number token shared with the venue address → the venue's block.
        v_addr_nums = set(re.findall(r'\d+', va))
        if v_addr_nums & set(re.findall(r'\d+', h)):
            return False
    # Otherwise: a proper place label (ends in a place word) opens another place.
    return bool(_PLACE_WORD_RE.search(h))


def _scope_text_to_venue(page_text: str, venue_name: str = "", venue_address: str = "") -> str:
    """Return only the venue's own sections from sectioned page text.

    Splits on the section sentinel and walks the sections in order. A section that
    is introduced by a heading naming ANOTHER place (and everything under it, until
    the next venue-level or venue-named heading) is dropped. If the text carries no
    sentinels (a plain, non-sectioned string), it is returned unchanged — callers
    that never flattened with _html_to_sectioned_text keep today's behaviour.
    """
    if _SECTION_SENTINEL not in (page_text or ''):
        return page_text or ''

    sections = [s for s in page_text.split(_SECTION_SENTINEL)]
    kept: List[str] = []
    skipping = False
    for sec in sections:
        sec_stripped = sec.strip()
        if not sec_stripped:
            continue
        # The heading of this section is its leading phrase (up to ~8 words / a
        # terminator). Used only to decide ownership.
        heading = re.split(r'[.:•\n]|\s{2,}', sec_stripped, maxsplit=1)[0]
        heading = ' '.join(heading.split()[:8])
        if _heading_names_other_place(heading, venue_name, venue_address):
            skipping = True
            continue
        # A venue-level or venue-named heading re-opens the venue's own content.
        if skipping:
            h = _norm(heading)
            is_venue_level = any(
                h == vs or h.startswith(vs + ' ') or h == vs + ':'
                for vs in _VENUE_SECTION_HEADINGS
            )
            vn = _norm(venue_name)
            shares_name = bool(vn) and bool(
                {t for t in re.findall(r'[a-z]{4,}', vn)}
                & {t for t in re.findall(r'[a-z]{4,}', h)}
            )
            if is_venue_level or shares_name:
                skipping = False
            else:
                continue
        kept.append(sec_stripped)
    scoped = ' '.join(kept).strip()
    return scoped if scoped else page_text


def _parse_date_range_fr(text: str) -> str:
    """Parse a French date range like 'du 1er septembre au 30 juin' → '1 Sep–30 Jun'."""
    # Pattern: du Xer/X month au Y month
    m = re.search(
        r'(?:du\s+)?(\d{1,2})(?:\s*(?:er|ère))?\s*'
        r'(janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre)\s+'
        r'au\s+(\d{1,2})(?:\s*(?:er|ère))?\s*'
        r'(janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre)',
        text, re.IGNORECASE
    )
    if m:
        d1, m1, d2, m2 = m.group(1), m.group(2), m.group(3), m.group(4)
        m1_en = _translate_month(m1)[:3]
        m2_en = _translate_month(m2)[:3]
        return f"{d1} {m1_en}–{d2} {m2_en}"
    return ""


def _parse_date_range_en(text: str) -> str:
    """Parse English date ranges like 'From November 1st to March 31th' → '1 Nov–31 Mar'."""
    m = re.search(
        r'(?:from\s+)?'
        r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+'
        r'(\d{1,2})(?:st|nd|rd|th)?\s+'
        r'to\s+'
        r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+'
        r'(\d{1,2})(?:st|nd|rd|th)?',
        text, re.IGNORECASE
    )
    if m:
        m1, d1, m2, d2 = m.group(1), m.group(2), m.group(3), m.group(4)
        m1_short = m1[:3].capitalize()
        m2_short = m2[:3].capitalize()
        return f"{d1} {m1_short}–{d2} {m2_short}"
    return ""


# ============================================================
# [LOCAL-592 r4] Day-range binding for English hours
# ============================================================

_EN_DAY_FULL = {
    'mon': 'Monday', 'tue': 'Tuesday', 'tues': 'Tuesday', 'wed': 'Wednesday',
    'wednes': 'Wednesday', 'thu': 'Thursday', 'thur': 'Thursday', 'thurs': 'Thursday',
    'fri': 'Friday', 'sat': 'Saturday', 'satur': 'Saturday', 'sun': 'Sunday',
}

# One English weekday token (abbrev or full), used to read a day group off the page.
_EN_DAY_TOKEN_RE = re.compile(
    r'\b(mon|tues?|wed(?:nes)?|thur?s?|fri|sat(?:ur)?|sun)(?:day)?\b', re.IGNORECASE)


def _canon_en_day(token: str) -> str:
    """Map a weekday token ('Tues', 'thursday', 'Mon') to its full name."""
    t = token.strip().lower()
    t = t[:-3] if t.endswith('day') else t
    return _EN_DAY_FULL.get(t, token.strip().capitalize())


def _normalize_day_range_en(raw: str) -> str:
    """Render a captured day group as a spoken range, e.g.:

        "Tuesday through Sunday", "Monday to Thursday", "Friday and Saturday".

    The connector the page used (through / to / – / & / and) is preserved as a
    natural spoken word; a single day stays a single day. Returns '' if no weekday
    token is present (so the caller never binds an empty day range).
    """
    if not raw:
        return ''
    tokens = _EN_DAY_TOKEN_RE.findall(raw)
    if not tokens:
        return ''
    days = [_canon_en_day(t) for t in tokens]
    if len(days) == 1:
        return days[0]
    # Which connector did the page use between the first two day tokens?
    connector = 'through'
    if re.search(r'\b(?:and|&)\b', raw) and not re.search(r'through|thru|to|[-–—]', raw):
        connector = 'and'
    elif re.search(r'\bto\b', raw) and not re.search(r'through|thru', raw):
        connector = 'to'
    return f"{days[0]} {connector} {days[-1]}"


def _day_context_en(page_text: str, around: Optional[int] = None, window: int = 60) -> str:
    """Return a spoken day binding for a time range that has no explicit day group.

    A time range is only the VENUE'S hours when the page binds it to days. Two
    honest bindings exist without an explicit weekday range:
      * "daily" / "every day" / "open daily"  → "Daily" (optionally "… except <day>").
      * a weekday token on the same stretch of text near the time.
    Returns '' when neither is present — the caller then does NOT store the time
    (a day-less time is a misleading half-fact, D611/r4).
    """
    if around is not None:
        seg = page_text[max(0, around - window): around + window]
    else:
        seg = page_text
    low = seg.lower()
    if re.search(r'\b(?:open\s+)?daily\b|\bevery\s*day\b', low):
        exc = re.search(
            r'except\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?',
            low)
        if exc:
            return f"Daily except {exc.group(1).capitalize()}s"
        return "Daily"
    m = _EN_DAY_TOKEN_RE.search(seg)
    if m:
        return _canon_en_day(m.group(0))
    return ''


# ============================================================
# Structured extraction from page text
# ============================================================

def extract_visitor_facts_from_text(page_text: str, page_lang: str = "fr",
                                    venue_name: str = "", venue_address: str = "") -> VisitorFacts:
    """Extract structured visitor facts from a museum page's text content.

    Args:
        page_text: The stripped text content of a museum's visitor info page.
        page_lang: Language of the page ("fr" or "en").
        venue_name: The venue the listener is visiting (e.g. "Griffin Museum of
            Photography"). Used to bind hours/closed-days to the venue's own
            section when the page lists several places (LOCAL-584 r2).
        venue_address: The venue's street address (from Wikidata/the site). Also
            used to recognise the venue's own section.

    Returns:
        VisitorFacts with whatever fields could be reliably extracted.
    """
    facts = VisitorFacts()

    if not page_text or len(page_text) < 50:
        return facts

    # [LOCAL-584 r2] Bind to the venue: when a page lists several places' hours,
    # keep only the sections that belong to the venue (its own name/address or a
    # venue-level Hours/Admission heading), never a block under another place's
    # heading ("Satellite Galleries", "… Gallery", "… Center"). On a page with no
    # section sentinels this is a no-op, so single-venue pages are unchanged.
    page_text = _scope_text_to_venue(page_text, venue_name, venue_address)
    # The downstream regexes expect clean prose — drop the sentinels now that
    # scoping is done.
    page_text = page_text.replace(_SECTION_SENTINEL, ' ')
    page_text = re.sub(r'[^\S\n]+', ' ', page_text).strip()

    # --- 1. CLOSED DAYS ---
    if page_lang == "fr":
        # "Fermé le mardi" / "Fermé le mardi, le 1er janvier..."
        closed_m = re.search(
            r'[Ff]erm[eé]\s+(?:le\s+)?(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)',
            page_text
        )
        if closed_m:
            facts.closed_days.append(_translate_day(closed_m.group(1)))
        else:
            # Alternative: "du mercredi au lundi" implies Tuesday closed
            range_m = re.search(
                r'[Dd]u\s+(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+'
                r'au\s+(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)',
                page_text
            )
            if range_m:
                _day_order = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche']
                start_idx = _day_order.index(range_m.group(1).lower())
                end_idx = _day_order.index(range_m.group(2).lower())
                # Days NOT in the range are the closed days
                if start_idx <= end_idx:
                    open_days = set(_day_order[start_idx:end_idx + 1])
                else:
                    open_days = set(_day_order[start_idx:] + _day_order[:end_idx + 1])
                closed = [d for d in _day_order if d not in open_days]
                facts.closed_days = [_translate_day(d) for d in closed]
        # Also check per-day schedules: "Mardi : Fermé"
        if not facts.closed_days:
            day_closed_m = re.findall(
                r'(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s*:\s*[Ff]erm[eé]',
                page_text, re.IGNORECASE
            )
            if day_closed_m:
                facts.closed_days = [_translate_day(d) for d in day_closed_m]
    else:
        # English
        closed_m = re.search(
            r'(?:[Cc]losed|except)\s*:?\s+(?:on\s+|every\s+)?(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)s?',
            page_text, re.IGNORECASE
        )
        if closed_m:
            facts.closed_days.append(closed_m.group(1).capitalize())
        # "open daily except Tuesdays"
        except_m = re.search(
            r'(?:daily|every\s+day)\s+except\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)s?',
            page_text, re.IGNORECASE
        )
        if except_m and not facts.closed_days:
            facts.closed_days.append(except_m.group(1))

    # --- 2. HOURS (with seasonal ranges) ---
    # [LOCAL-584] Normalisation to 24h is allowed ONLY when the result maps back to
    # a time token on the page. _normalize_time_sourced keeps page-literal AM/PM
    # otherwise, so a page that says "8 AM – 8 PM" is never stated as "08:00–20:00".
    _src_lower = page_text.lower()
    if page_lang == "fr":
        # Pattern: "de 10h à 17h du 1er septembre au 30 juin"
        # Can appear multiple times for different seasons
        hour_matches = re.finditer(
            r'(?:de\s+)?(\d{1,2}h?\d{0,2})\s*(?:[àa]|[-–])\s*(\d{1,2}h?\d{0,2})'
            r'(?:\s+(?:du|de|le)\s+(.{10,60}?))?'
            r'(?=\s*[.•\n]|\s*(?:du|de|ferm|Du|De|Ferm|\Z))',
            page_text
        )
        seen_times = set()
        for hm in hour_matches:
            t1 = _normalize_time_sourced(hm.group(1), _src_lower)
            t2 = _normalize_time_sourced(hm.group(2), _src_lower)
            time_range = f"{t1}–{t2}"
            period_text = (hm.group(3) or "").strip().rstrip('.')
            period = _parse_date_range_fr(period_text) if period_text else ""
            # Avoid duplicates
            key = (time_range, period)
            if key not in seen_times:
                seen_times.add(key)
                facts.hours.append({'time': time_range, 'period': period})

        # If no structured matches, try broader pattern for single time range
        if not facts.hours:
            simple_m = re.search(
                r'(\d{1,2}h?\d{0,2})\s*(?:[àa]|[-–])\s*(\d{1,2}h?\d{0,2})',
                page_text
            )
            if simple_m:
                t1 = _normalize_time_sourced(simple_m.group(1), _src_lower)
                t2 = _normalize_time_sourced(simple_m.group(2), _src_lower)
                facts.hours.append({'time': f"{t1}–{t2}", 'period': ''})

    else:
        # English: "open from 10 am to 5 pm" / "10:00 to 18:00"
        # Look for seasonal English patterns first
        # "From November 1st to March 31th: open from 10 am to 5 pm"
        seasonal_en = re.finditer(
            r'(?:from\s+)?'
            r'((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?)'
            r'\s+to\s+'
            r'((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?)'
            r'\s*[:\*]*\s*'
            r'(?:open\s+(?:from\s+)?)?'
            r'(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*(?:to|[-–])\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)',
            page_text, re.IGNORECASE
        )
        seen_times = set()
        # The season sentence may still carry a day qualifier ("daily", "every day
        # except Tuesdays") — bind it so a seasonal line is never day-less either.
        _season_days = _day_context_en(page_text)
        for sm in seasonal_en:
            period_start = sm.group(1)
            period_end = sm.group(2)
            t1 = _normalize_time_sourced(sm.group(3), _src_lower)
            t2 = _normalize_time_sourced(sm.group(4), _src_lower)
            time_range = f"{t1}–{t2}"
            # Simplify period
            period = _parse_date_range_en(f"from {period_start} to {period_end}")
            key = (time_range, period)
            if key not in seen_times:
                seen_times.add(key)
                facts.hours.append({'time': time_range, 'period': period,
                                    'days': _season_days})

        # [LOCAL-592 r3/r4] Day-schedule hours: "Monday-Thursday: 9 am – 8 pm",
        # "Monday through Friday 9 AM — 4 PM". The venue lists its hours as a
        # weekday range followed by a time range (the Boston Athenaeum, the Griffin
        # satellite rows). The time sides MUST carry an am/pm (or noon/midnight)
        # marker, so a phone number ("720-7604") or a year ("2026") can never be
        # mistaken for hours. Venue-scoping already dropped other places' sections.
        #
        # r4 — BIND THE DAYS. r3 captured the time but discarded the weekday range,
        # so "Tuesday through Sunday: Noon to 4 PM" was stated as the day-less
        # "Noon–4 PM" (a Saturday listener hears every day). Now every match keeps
        # its day range, and the page's SEVERAL day groups are each stated (Mon–Thu
        # 9–8; Fri–Sat 9–5), in page order.
        if not facts.hours:
            _day = (r'(?:mon|tues?|wed(?:nes)?|thur?s?|fri|sat(?:ur)?|sun)(?:day)?')
            _en_time_m = r'(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)|noon|midnight)'
            day_sched_re = re.compile(
                r'\b(' + _day + r'(?:\s*(?:through|thru|to|[-–—&]|and)\s*' + _day + r')?)'
                r'\s*[:\s]\s*(' + _en_time_m + r')\s*(?:to|[-–—])\s*(' + _en_time_m + r')',
                re.IGNORECASE,
            )
            seen_dayslot = set()
            for dm in day_sched_re.finditer(page_text):
                days = _normalize_day_range_en(dm.group(1))
                t1 = _normalize_time_sourced(dm.group(2), _src_lower)
                t2 = _normalize_time_sourced(dm.group(3), _src_lower)
                time_range = f"{t1}–{t2}"
                key = (days, time_range)
                if not days or key in seen_dayslot:
                    continue
                seen_dayslot.add(key)
                facts.hours.append({'time': time_range, 'period': '', 'days': days})

        # Also try simpler single-range English patterns. At least ONE side must
        # carry a time marker (am/pm/colon/noon/midnight) so bare digit ranges in
        # phone numbers / ZIPs / years are never read as hours (r3). r4: the match
        # must ALSO have a bindable day context ("daily", "every day", or a weekday
        # on the same line) — a day-less time (a café's lunch window) is a
        # misleading half-fact and is NOT stored as the venue's hours.
        if not facts.hours:
            _en_time = r'(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)?|noon|midnight)'
            _en_time_marked = r'(?:\d{1,2}:\d{2}\s*(?:am|pm)?|\d{1,2}\s*(?:am|pm)|noon|midnight)'
            simple_en = re.search(
                r'(?:open\s+(?:from\s+)?)?(' + _en_time_marked + r')\s*(?:to|[-–—])\s*(' + _en_time + r')',
                page_text, re.IGNORECASE
            )
            if not simple_en:
                simple_en = re.search(
                    r'(?:open\s+(?:from\s+)?)?(' + _en_time + r')\s*(?:to|[-–—])\s*(' + _en_time_marked + r')',
                    page_text, re.IGNORECASE
                )
            if simple_en:
                days = _day_context_en(page_text, around=simple_en.start())
                if days:   # r4: never store a day-less time as the venue's hours
                    t1 = _normalize_time_sourced(simple_en.group(1), _src_lower)
                    t2 = _normalize_time_sourced(simple_en.group(2), _src_lower)
                    facts.hours.append({'time': f"{t1}–{t2}", 'period': '', 'days': days})

    # --- 3. ADMISSION (with conditions) ---
    # This is the critical part: we must distinguish unconditional free from conditional.
    # Strategy: look for BOTH a price AND a free-for-residents/pass condition.
    # Key rule: "Visite libre: Entrée gratuite" means general entry is FREE —
    # do NOT let "5€ par adulte" from guided tours override it.

    _has_general_price = False
    _general_price = ""
    _has_free_condition = False
    _free_condition = ""
    _is_unconditionally_free = False

    if page_lang == "fr":
        # Check for unconditional free admission first
        # "Entrée gratuite" / "Visite libre : Entrée gratuite" / "Visite libre Entrée gratuite"
        _libre_gratuit = re.search(
            r'(?:[Vv]isite\s+libre|[Ee]ntr[eé]e)\s*[:\s.]*\s*(?:[Gg]ratuit(?:e)?|[Ll]ibre)',
            page_text
        )

        # Check for a GENERAL ENTRY price — must be near keywords that indicate
        # it's the main ticket, not a guided tour or workshop.
        # "Tarif normal/plein/unique" or "Entrée unique" are the key markers.
        # [LOCAL-584] Capture the currency symbol/code the page used — never assume €.
        _price_match = re.search(
            r'(?:[Tt]arif\s+(?:normal|plein|unique)|[Ee]ntr[eé]e\s+unique)\s*[:\s]*'
            r'(?:(€|£|\$|¥|CHF)\s*)?(\d+)\s*(€|£|\$|¥|EUR|CHF)?',
            page_text
        )
        # Do NOT use the generic "X€" pattern if we already found "Entrée gratuite"
        # because the generic pattern would pick up guided tour prices.
        if not _price_match and not _libre_gratuit:
            # Fallback: look for standalone price near "tarif" or "billet"
            _price_match = re.search(
                r'(?:[Tt]arif|[Bb]illet)\s+[^.]{0,30}?'
                r'(?:(€|£|\$|¥|CHF)\s*)?(\d+)\s*(€|£|\$|¥|EUR|CHF)?',
                page_text
            )

        # Check for Métropole/residents free condition
        _metropole_free = re.search(
            r'(?:[Gg]ratuit|[Ll]ibre|acc[eè]s\s+gratuit)[\s\S]{0,200}?(?:[Mm][eé]tropole|[Rr][eé]sident|[Hh]abitant)',
            page_text
        )
        if not _metropole_free:
            _metropole_free = re.search(
                r'(?:[Mm][eé]tropole|[Rr][eé]sident|[Hh]abitant)[\s\S]{0,200}?(?:[Gg]ratuit|[Ll]ibre|acc[eè]s\s+gratuit)',
                page_text
            )
        # Also check for "Pass Musées" free for residents
        _pass_free = re.search(
            r'[Pp]ass\s+[Mm]us[eé]es?[\s\S]{0,300}?gratuit[\s\S]{0,200}?(?:[Mm][eé]tropole|[Rr][eé]sident|[Hh]abitant)',
            page_text
        )
        if not _pass_free:
            _pass_free = re.search(
                r'(?:[Mm][eé]tropole|[Rr][eé]sident|[Hh]abitant)[\s\S]{0,200}?[Pp]ass\s+[Mm]us[eé]es?[\s\S]{0,200}?gratuit',
                page_text
            )

        if _libre_gratuit and not _price_match:
            # Truly free general entry (like Asian Arts Museum départemental)
            _is_unconditionally_free = True
        elif _price_match:
            # [LOCAL-584] Symbol comes from the page: a leading symbol (group 1) or a
            # trailing symbol/code (group 3). The amount is group 2. If the page gave
            # no currency marker at all, _format_price emits the bare number — we do
            # NOT substitute €.
            _sym = _price_match.group(1) or _price_match.group(3) or ''
            _general_price = _format_price(_sym, _price_match.group(2))
            _has_general_price = True
        if _metropole_free or _pass_free:
            _has_free_condition = True
            _free_condition = "free for Métropole residents"

    else:
        # English admission extraction
        # Look for individual entry price.
        # [LOCAL-584] Capture the currency symbol/code from the page — never assume €.
        # Griffin Museum (Winchester, MA) writes "General Admission: $12 for adults",
        # and the old pattern discarded the '$' then re-stamped '€' → "€12".
        _price_match = re.search(
            r'(?:Mus[eé]e\s+\w+|single|entry|admission|ticket)\s*[-–:]\s*'
            r'(?:(€|£|\$|¥|CHF|USD|GBP|EUR)\s*)?(\d+)\s*(€|£|\$|¥|EUR|USD|GBP|CHF)?',
            page_text, re.IGNORECASE
        )
        if not _price_match:
            _price_match = re.search(
                r'(?:(€|£|\$|¥|CHF)\s*)?(\d+)\s*(€|£|\$|¥|EUR|USD|GBP|CHF)\s*(?:per\s+person)?',
                page_text, re.IGNORECASE
            )

        # Check for free admission
        _free_match = re.search(
            r'(?:free\s+(?:admission|entry)|admission\s+free|no\s+(?:admission|entry)\s+(?:fee|charge))',
            page_text, re.IGNORECASE
        )

        # Check for conditional free (Métropole residents)
        _metropole_free = re.search(
            r'(?:free|gratuit).*?(?:M[eé]tropole|resident|Métropole Nice)',
            page_text, re.IGNORECASE | re.DOTALL
        )
        if not _metropole_free:
            _metropole_free = re.search(
                r'(?:M[eé]tropole|resident).*?(?:free|gratuit)',
                page_text, re.IGNORECASE | re.DOTALL
            )
        # "The pass is free for residents of Nice and the towns located within the Métropole"
        _pass_free_en = re.search(
            r'pass\s+is\s+free\s+for\s+residents',
            page_text, re.IGNORECASE
        )
        if _pass_free_en:
            _metropole_free = _pass_free_en

        # Check for pass pricing
        _pass_price = re.search(
            r'(?:\d+)[- –]*day.*?(?:Pass|pass)\s*[-–:]\s*(?:€)?(\d+)(?:\s*€)?',
            page_text, re.IGNORECASE
        )

        if _free_match and not _price_match:
            _is_unconditionally_free = True
        elif _price_match:
            # [LOCAL-584] Symbol from the page (leading group 1 or trailing group 3);
            # amount is group 2. No marker ⇒ bare number, never a € default.
            _sym = _price_match.group(1) or _price_match.group(3) or ''
            _general_price = _format_price(_sym, _price_match.group(2))
            _has_general_price = True
        if _metropole_free:
            _has_free_condition = True
            _free_condition = "free for Métropole residents"

    # Build admission string
    if _is_unconditionally_free and not _has_free_condition:
        facts.admission = "FREE"
    elif _has_general_price and _has_free_condition:
        facts.admission = f"{_general_price}; {_free_condition}"
    elif _has_general_price:
        facts.admission = _general_price
    elif _has_free_condition:
        # Free for residents mentioned but no general price found — state the condition
        facts.admission = f"Free for Métropole residents"

    return facts


def _fetch_visitor_pages(base_site_url: str) -> list:
    """[LOCAL-35/39] Fetch candidate visitor-info pages from a museum site.

    Returns list of (text, detected_lang, url) tuples for successfully fetched pages.
    Shared by both the structured extractor and the provenance pipeline.
    """
    import requests
    from urllib.parse import urljoin, urlparse

    if not base_site_url:
        return []

    # Known URL patterns for visitor info pages across museum sites
    _VISITOR_INFO_PATHS = [
        'tarifs-et-horaires', 'horaires-et-tarifs', 'infos-pratiques',
        'informations-pratiques', 'plan-your-visit', 'visit',
        'visitor-information', 'hours-admission', 'hours-and-admission',
        'opening-hours', 'practical-information',
        'tarifs', 'horaires', 'visite',
        # English variants for bilingual sites
        'en/practical-information', 'en/visit', 'en/hours',
    ]

    _parsed_url = urlparse(base_site_url)
    _path_segments = [s for s in _parsed_url.path.rstrip('/').split('/') if s]
    _is_deep_path = len(_path_segments) > 1

    _urls_to_try = []
    if _is_deep_path:
        # Deep path (portal site): also try the venue page itself first,
        # as portal sites often embed all visitor info on the main venue page.
        _venue_base = base_site_url.rstrip('/')
        _urls_to_try.append(_venue_base)  # The page itself
        for slug in _VISITOR_INFO_PATHS:
            _urls_to_try.append(_venue_base + '/' + slug)
        print(f"  [LOCAL-35] Visitor info scoped to venue section (deep path: {_venue_base})")
    else:
        # Bare domain: try as root-level paths
        for slug in _VISITOR_INFO_PATHS:
            _urls_to_try.append(urljoin(base_site_url, '/' + slug))

    # Try fetching pages — try both FR and EN pages for best extraction
    _fetched_pages = []  # (text, detected_lang, url)

    for _url in _urls_to_try:
        try:
            resp = requests.get(_url, headers={'User-Agent': 'Audioura/2.2'},
                              timeout=10, allow_redirects=True)
            if resp.status_code == 200 and len(resp.text) > 200:
                # [LOCAL-584 r2] Flatten with section sentinels at heading boundaries
                # so hours/closed-days can be bound to the venue's own section (not a
                # satellite gallery's). _scope_text_to_venue consumes the sentinels;
                # extract_visitor_facts_from_text strips any that remain.
                _text = _html_to_sectioned_text(resp.text)
                if len(_text) > 100:
                    # Detect language based on content
                    _lower = _text.lower()
                    _fr_signals = sum(1 for w in ['fermé', 'horaires', 'tarifs', 'ouvert', 'gratuit', 'mardi']
                                     if w in _lower)
                    _en_signals = sum(1 for w in ['closed', 'hours', 'admission', 'open', 'free', 'tuesday']
                                     if w in _lower)
                    _lang = "en" if _en_signals > _fr_signals else "fr"
                    _fetched_pages.append((_text[:8000], _lang, _url))
                    print(f"  [LOCAL-35] Visitor info page found ({_lang}): {_url}")
                    # Get at most 2 pages (FR + EN) for cross-validation
                    if len(_fetched_pages) >= 2:
                        break
        except Exception:
            continue

    if not _fetched_pages:
        print(f"  [LOCAL-35] No visitor info page found for {base_site_url}")

    return _fetched_pages


def _extract_best_facts(fetched_pages: list, venue_name: str = "",
                        venue_address: str = "") -> Optional[VisitorFacts]:
    """[LOCAL-35/39] Pick the best VisitorFacts from a list of fetched pages.

    Strategy: extract from each page independently, then MERGE the best fields
    across all results. This handles the common case where one page has better
    hours (e.g., seasonal ranges in FR) and another has better admission data
    (e.g., specific price on the EN page). venue_name/venue_address are passed to
    the extractor so hours/closed-days are bound to the venue (LOCAL-584 r2).
    """
    all_facts = []

    for _text, _lang, _url in fetched_pages:
        facts = extract_visitor_facts_from_text(_text, _lang, venue_name, venue_address)
        facts.source_url = _url
        print(f"  [LOCAL-35] Extracted from {_url}: closed={facts.closed_days}, "
              f"hours={len(facts.hours)}, admission='{facts.admission}'")
        all_facts.append(facts)

    if not all_facts:
        return None

    # Start with the best single result (by completeness score)
    def _score(f):
        s = 0
        s += min(len(f.hours), 2) * 2
        if f.admission:
            s += 3
            if _has_price(f.admission):
                s += 2
        if f.closed_days:
            s += 1
        return s

    all_facts.sort(key=_score, reverse=True)
    best = all_facts[0]

    # Merge: fill in gaps from other results if the best is missing fields
    for other in all_facts[1:]:
        # If best has fewer hours, take hours from other (only if other has more)
        if len(other.hours) > len(best.hours):
            best.hours = other.hours
        # If best has no admission or no price, prefer other's admission if it has a price
        if other.admission and _has_price(other.admission):
            if not best.admission or not _has_price(best.admission):
                best.admission = other.admission
        # If best has no closed_days, take from other
        if not best.closed_days and other.closed_days:
            best.closed_days = other.closed_days

    return best


def fetch_visitor_info_structured(base_site_url: str, language: str = "en",
                                  venue_name: str = "", venue_address: str = "") -> str:
    """[LOCAL-35] Fetch and extract structured visitor information from a museum's official site.

    Replaces the old _fetch_visitor_info_from_site with structured field extraction.
    Returns a formatted English-language string for the Museum Information field,
    or empty string if extraction fails.

    Key improvements over LOCAL-27/29/33:
    - Extracts closed_days, hours (seasonal), admission (conditional) as structured fields
    - Never flattens conditional pricing to just "Free"
    - Hours are required whenever published — omitting is only valid if truly absent
    - Seasonal ranges are paired with their applicable period
    """
    _fetched_pages = _fetch_visitor_pages(base_site_url)
    if not _fetched_pages:
        return ""

    _best_facts = _extract_best_facts(_fetched_pages, venue_name, venue_address)

    if _best_facts is None or _best_facts.is_empty():
        print(f"  [LOCAL-35] Could not extract structured visitor facts from any page")
        return ""

    # Format the result
    result = _best_facts.format_en()

    # Final validity check — must contain at least one concrete fact
    if not result or len(result) < 10:
        print(f"  [LOCAL-35] Formatted result too short — omitting")
        return ""

    print(f"  [LOCAL-35] Final Museum Information: {result}")
    return result


@dataclass
class VisitorInfoWithProvenance:
    """[LOCAL-39] Result of structured extraction with provenance data for the QA gate."""
    formatted_info: str = ""        # The formatted Museum Information string
    source_url: str = ""            # URL the facts were extracted from
    source_text: str = ""           # Raw page text for gate verification
    facts: Optional['VisitorFacts'] = None  # Structured facts object


def fetch_visitor_info_with_provenance(base_site_url: str, language: str = "en",
                                       venue_name: str = "", venue_address: str = "") -> VisitorInfoWithProvenance:
    """[LOCAL-39] Structured extraction + provenance for the practical facts gate.

    Composes LOCAL-35's structured extractor with LOCAL-36's provenance tracking:
    - Uses LOCAL-35's smart page discovery and structured field extraction
    - Returns the raw source text alongside the formatted result, so LOCAL-36's
      practical_facts_gate can verify every claim against the original source.
    - venue_name/venue_address bind hours/closed-days to the venue (LOCAL-584 r2).

    This replaces both _fetch_visitor_info_from_site AND _fetch_visitor_info_raw_source
    with a single fetch that serves both purposes.
    """
    result = VisitorInfoWithProvenance()

    _fetched_pages = _fetch_visitor_pages(base_site_url)
    if not _fetched_pages:
        return result

    _best_facts = _extract_best_facts(_fetched_pages, venue_name, venue_address)

    if _best_facts is None or _best_facts.is_empty():
        print(f"  [LOCAL-35] Could not extract structured visitor facts from any page")
        return result

    # Format the result
    formatted = _best_facts.format_en()

    # Final validity check — must contain at least one concrete fact
    if not formatted or len(formatted) < 10:
        print(f"  [LOCAL-35] Formatted result too short — omitting")
        return result

    print(f"  [LOCAL-35] Final Museum Information: {formatted}")

    # Provenance: collect raw source text from ALL fetched pages (gives gate
    # maximum evidence to verify against). The source_url is the best-match page.
    # Strip the section sentinels so the gate's literal-token checks see clean prose.
    _all_source_text = "\n\n".join(
        text.replace(_SECTION_SENTINEL, ' ') for text, _, _ in _fetched_pages)
    _all_source_text = re.sub(r'[^\S\n]+', ' ', _all_source_text)

    result.formatted_info = formatted
    result.source_url = _best_facts.source_url
    result.source_text = _all_source_text[:10000]  # Cap at 10k for gate
    result.facts = _best_facts

    return result
