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
    hours: List[Dict[str, str]] = field(default_factory=list)  # [{time: "10:00–18:00", period: "1 Apr–31 Oct"}]
    admission: str = ""                                         # e.g. "€10 / 48h pass; free for Métropole residents"
    source_url: str = ""

    def is_empty(self) -> bool:
        return not self.closed_days and not self.hours and not self.admission

    def format_en(self) -> str:
        """Format all fields into a single English-language Museum Information string."""
        parts = []

        # Closed days
        if self.closed_days:
            if len(self.closed_days) == 1:
                parts.append(f"Closed on {self.closed_days[0]}")
            else:
                parts.append(f"Closed on {', '.join(self.closed_days)}")

        # Hours
        if self.hours:
            if len(self.hours) == 1:
                h = self.hours[0]
                if h.get('period'):
                    parts.append(f"{h['time']} ({h['period']})")
                else:
                    parts.append(h['time'])
            else:
                # Multiple seasonal ranges — each paired with its period
                hour_parts = []
                for h in self.hours:
                    if h.get('period'):
                        hour_parts.append(f"{h['time']} ({h['period']})")
                    else:
                        hour_parts.append(h['time'])
                parts.append('; '.join(hour_parts))

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
# Structured extraction from page text
# ============================================================

def extract_visitor_facts_from_text(page_text: str, page_lang: str = "fr") -> VisitorFacts:
    """Extract structured visitor facts from a museum page's text content.

    Args:
        page_text: The stripped text content of a museum's visitor info page.
        page_lang: Language of the page ("fr" or "en").

    Returns:
        VisitorFacts with whatever fields could be reliably extracted.
    """
    facts = VisitorFacts()

    if not page_text or len(page_text) < 50:
        return facts

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
            r'(?:[Cc]losed|except)\s+(?:on\s+)?(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)s?',
            page_text
        )
        if closed_m:
            facts.closed_days.append(closed_m.group(1))
        # "open daily except Tuesdays"
        except_m = re.search(
            r'(?:daily|every\s+day)\s+except\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)s?',
            page_text, re.IGNORECASE
        )
        if except_m and not facts.closed_days:
            facts.closed_days.append(except_m.group(1))

    # --- 2. HOURS (with seasonal ranges) ---
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
            t1 = _normalize_time(hm.group(1))
            t2 = _normalize_time(hm.group(2))
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
                t1 = _normalize_time(simple_m.group(1))
                t2 = _normalize_time(simple_m.group(2))
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
        for sm in seasonal_en:
            period_start = sm.group(1)
            period_end = sm.group(2)
            t1 = _normalize_time(sm.group(3))
            t2 = _normalize_time(sm.group(4))
            time_range = f"{t1}–{t2}"
            # Simplify period
            period = _parse_date_range_en(f"from {period_start} to {period_end}")
            key = (time_range, period)
            if key not in seen_times:
                seen_times.add(key)
                facts.hours.append({'time': time_range, 'period': period})

        # Also try simpler single-range English patterns
        if not facts.hours:
            simple_en = re.search(
                r'(?:open\s+(?:from\s+)?)?(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*(?:to|[-–])\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)',
                page_text, re.IGNORECASE
            )
            if simple_en:
                t1 = _normalize_time(simple_en.group(1))
                t2 = _normalize_time(simple_en.group(2))
                facts.hours.append({'time': f"{t1}–{t2}", 'period': ''})

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
        _price_match = re.search(
            r'(?:[Tt]arif\s+(?:normal|plein|unique)|[Ee]ntr[eé]e\s+unique)\s*[:\s]*(\d+)\s*(?:€|EUR)',
            page_text
        )
        # Do NOT use the generic "X€" pattern if we already found "Entrée gratuite"
        # because the generic pattern would pick up guided tour prices.
        if not _price_match and not _libre_gratuit:
            # Fallback: look for standalone price near "tarif" or "billet"
            _price_match = re.search(
                r'(?:[Tt]arif|[Bb]illet)\s+[^.]{0,30}?(\d+)\s*(?:€|EUR)',
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
            _general_price = f"€{_price_match.group(1)}"
            _has_general_price = True
        if _metropole_free or _pass_free:
            _has_free_condition = True
            _free_condition = "free for Métropole residents"

    else:
        # English admission extraction
        # Look for individual entry price
        _price_match = re.search(
            r'(?:Mus[eé]e\s+\w+|single|entry|admission|ticket)\s*[-–:]\s*(?:€|£|\$)?(\d+)(?:\s*€)?',
            page_text, re.IGNORECASE
        )
        if not _price_match:
            _price_match = re.search(
                r'(\d+)\s*€\s*(?:per\s+person)?',
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
            _general_price = f"€{_price_match.group(1)}"
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
                # Extract text content
                _text = re.sub(r'<script[^>]*>.*?</script>', '', resp.text, flags=re.DOTALL)
                _text = re.sub(r'<style[^>]*>.*?</style>', '', _text, flags=re.DOTALL)
                _text = re.sub(r'<[^>]+>', ' ', _text)
                _text = re.sub(r'\s+', ' ', _text).strip()
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


def _extract_best_facts(fetched_pages: list) -> Optional[VisitorFacts]:
    """[LOCAL-35/39] Pick the best VisitorFacts from a list of fetched pages.

    Strategy: extract from each page independently, then MERGE the best fields
    across all results. This handles the common case where one page has better
    hours (e.g., seasonal ranges in FR) and another has better admission data
    (e.g., specific price on the EN page).
    """
    all_facts = []

    for _text, _lang, _url in fetched_pages:
        facts = extract_visitor_facts_from_text(_text, _lang)
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
            if re.search(r'€\d+|\d+€', f.admission):
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
        if other.admission and re.search(r'€\d+|\d+€', other.admission):
            if not best.admission or not re.search(r'€\d+|\d+€', best.admission):
                best.admission = other.admission
        # If best has no closed_days, take from other
        if not best.closed_days and other.closed_days:
            best.closed_days = other.closed_days

    return best


def fetch_visitor_info_structured(base_site_url: str, language: str = "en") -> str:
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

    _best_facts = _extract_best_facts(_fetched_pages)

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


def fetch_visitor_info_with_provenance(base_site_url: str, language: str = "en") -> VisitorInfoWithProvenance:
    """[LOCAL-39] Structured extraction + provenance for the practical facts gate.

    Composes LOCAL-35's structured extractor with LOCAL-36's provenance tracking:
    - Uses LOCAL-35's smart page discovery and structured field extraction
    - Returns the raw source text alongside the formatted result, so LOCAL-36's
      practical_facts_gate can verify every claim against the original source.

    This replaces both _fetch_visitor_info_from_site AND _fetch_visitor_info_raw_source
    with a single fetch that serves both purposes.
    """
    result = VisitorInfoWithProvenance()

    _fetched_pages = _fetch_visitor_pages(base_site_url)
    if not _fetched_pages:
        return result

    _best_facts = _extract_best_facts(_fetched_pages)

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
    _all_source_text = "\n\n".join(text for text, _, _ in _fetched_pages)

    result.formatted_info = formatted
    result.source_url = _best_facts.source_url
    result.source_text = _all_source_text[:10000]  # Cap at 10k for gate
    result.facts = _best_facts

    return result
