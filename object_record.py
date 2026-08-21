#!/usr/bin/env python3
"""object_record.py — D501: the object record, where the facts actually live.

Michael, 2026-08-20: *"Are not artist, publisher, printed_by in catalog, and
credit_line from the Stop description sentences? ... These fields are important
to get our stories rich."*

They are in a catalogue. Not in the one we read.

**What production reads today.** `exhibition_checklist` fetches the exhibition's
own page — `mfa.org/exhibition/picasso-miro-dali-unbound` — and runs an LLM over
the prose. That page is marketing copy. It names three works and their artists;
whatever else it happens to mention is luck. On the 08-20 baseline stop 1 got a
publisher and a credit line because the page mentioned them, and stops 2 and 3
got `"Not specified"` in three slots each.

**What the object record has.** For the same work, `collections.mfa.org/objects/698625`:

    Medium/Technique   Illustrated book with forty color lithographs ...
    Credit Line        Gift of Boris Fridman
    Catalogue Raisonné Cramer, Miró livres illustrés,148; Mourlot 789 - 828
    Description        (Paris: Louis Broder, 1971)
    Provenance         Boris Fridman, Newton, MA; 2021, gift of Boris Fridman
                       to the MFA. (Accession Date: December 15, 2021)

**Mourlot is in there.** The printer — D500's `builder` role, empty in every
production run ever made — is sitting in the catalogue raisonné line. So is the
publisher with its city and year, and a provenance line with the donor's town and
the date he gave it. This is the difference between a stop with one agent and a
stop with three.

**Why this is generic and not an MFA scraper.** `collections.mfa.org` runs
eMuseum (Gallery Systems), whose object template emits

    <div class="detailField mediumField">
      <span class="detailFieldLabel">Medium/Technique</span>
      <span class="detailFieldValue">...</span>

and that markup is identical across the very many museums running eMuseum. We
parse the template, not the museum. `_try_aic_api` (LOCAL-366) is the existing
precedent for structured retrieval and is hardcoded to one venue — the same
hand-maintained-list mistake D495 removed from domain tiering, so this does not
repeat it: the collections host is DERIVED from the venue domain the venue
resolver already returns.

**Cost.** Two GETs per stop at most (one search, one record), no LLM, no SERP.
Both cached by `exhibition_checklist._fetch_page`'s per-host page cache.

**It never fails a tour.** Every function returns empty on any error. A stop with
no object record is exactly as well off as it was before this module existed.
"""
import re
from html import unescape as _unescape
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, urlparse

from text_fold import fold, is_placeholder

__all__ = ['collections_hosts_for', 'find_object_record', 'enrich_matrix',
           'parse_object_page', 'FIELD_MAP']

# eMuseum label → our matrix slot. Labels are matched case-insensitively and
# accent-folded, because the same install serves them localised.
FIELD_MAP = {
    'medium/technique': 'medium',
    'medium': 'medium',
    'credit line': 'credit_line',
    'creditline': 'credit_line',
    'provenance': 'provenance',
    'catalogue raisonne': 'catalogue_raisonne',
    'catalog raisonne': 'catalogue_raisonne',
    'description': 'record_description',
    'classifications': 'classification',
    'accession number': 'accession_number',
    'title': 'record_title',
    'artist': 'artist',
    'maker': 'artist',
    'culture': 'culture',
    'dimensions': 'dimensions',
    'copyright': 'copyright',
    'object type': 'classification',
    'publisher': 'publisher',
    'printer': 'printed_by',
}

# `(Paris: Louis Broder, 1971)` — the imprint, as eMuseum writes it into the
# Description field for a book. City, publisher, year.
_IMPRINT = re.compile(r'\(([^:()]{2,40}):\s*([^,()]{2,60}),\s*(\d{4})\)')

# `Cramer, Miró livres illustrés,148; Mourlot 789 - 828` — a catalogue raisonné
# line is a list of `<authority> <numbers>` references. The AUTHORITY is often
# the printer or the scholar of record: Mourlot printed for Miró, Picasso and
# Chagall, and "Mourlot 789-828" is how the trade cites his press numbers.
_CR_REF = re.compile(r'([A-ZÀ-Þ][A-Za-zÀ-ÿ\'’\-]{2,24})\s+\d')

# Printing houses that appear as catalogue-raisonné authorities. Used ONLY to
# decide whether a raisonné authority is a PRINTER rather than a scholar — never
# to assert a printer that is not in the record. An unknown authority is left
# alone rather than guessed at, because "Cramer" is a scholar and "Mourlot" is a
# press and nothing in the string itself distinguishes them.
_KNOWN_PRESSES = {
    'mourlot', 'lacouriere', 'crommelynck', 'roger lacouriere', 'imprimerie',
    'atelier', 'desjobert', 'clot', 'vollard', 'maeght', 'arte', 'fequet',
    'baudier', 'daragnes', 'leblanc', 'duval', 'rigal', 'visat', 'frelaut',
}


def collections_hosts_for(venue_url: str) -> List[str]:
    """Candidate collection hosts for a venue, derived — never hardcoded.

    `https://www.mfa.org/` -> ['collections.mfa.org', 'www.mfa.org', 'mfa.org']

    The `collections.` prefix is the eMuseum convention. The bare domain is kept
    as a fallback because some installs serve the catalogue from a path on the
    main site instead of a subdomain.
    """
    host = (urlparse(venue_url).netloc or venue_url or '').lower().strip()
    if not host:
        return []
    if host.startswith('www.'):
        host = host[4:]
    if not host or '.' not in host:
        return []
    return [f'collections.{host}', f'www.{host}', host]


def _fetch(url: str) -> str:
    """Raw HTML.

    NOT `exhibition_checklist._fetch_page` — that returns extracted TEXT, and an
    eMuseum object page is client-side rendered, so its text extraction yields
    the template literal `${pageClass}` and nothing else. The fields live in the
    server-rendered markup, so this needs the raw HTML.
    """
    try:
        import requests
        resp = requests.get(
            url, timeout=15,
            headers={'User-Agent': 'AudiouraBot/1.0 (story-quality-pipeline)'})
        return resp.text if resp.status_code == 200 else ''
    except Exception:
        return ''


def parse_object_page(html: str) -> Dict[str, str]:
    """Pull the eMuseum detail fields out of an object page.

    Returns {slot: value} using FIELD_MAP, plus any unmapped label under its own
    folded name so a record is never silently discarded for having a label we
    have not seen.
    """
    out: Dict[str, str] = {}
    if not html:
        return out
    # [D501] Entities FIRST. eMuseum serves the same field as `Catalogue
    # Raisonné` on one install and `Catalogue Raisonn&eacute;` on another, and
    # the undecoded form folds to `catalogue raisonn&eacute;`, which matches no
    # FIELD_MAP key — so the printer silently vanishes. Found by a test fixture
    # that happened to use the entity form; the live page used literals, so a
    # network test would have passed and shipped the bug.
    html = _unescape(html)
    pattern = re.compile(
        r'detailFieldLabel[^>]*>\s*([^<]+?)\s*</span>\s*'
        r'<span class="detailFieldValue">(.*?)</span>', re.S)
    for m in pattern.finditer(html):
        label = fold(m.group(1)).strip().rstrip(':')
        value = re.sub(r'<[^>]+>', ' ', m.group(2))
        value = re.sub(r'\s+', ' ', value).strip()
        if not value or is_placeholder(value):
            continue
        out[FIELD_MAP.get(label, label.replace(' ', '_'))] = value
    return out


# Function words carry no identifying power and inflate every score. Measured:
# "Moses and Monotheism" scored 0.67 against "Moses Telling the Israelites to
# Gather the Manna and Moses Striking the Rock" — a different work entirely —
# because `and` counted as a matching token. Multilingual, since these are
# French, Spanish and Italian titles as often as English.
_STOPWORDS = {
    'the', 'and', 'for', 'with', 'from', 'des', 'les', 'del', 'della', 'aux',
    'sur', 'dans', 'une', 'que', 'qui', 'por', 'con', 'para', 'nel', 'dei',
}


def _title_match_score(want: str, got: str) -> float:
    """Token overlap, accent-folded, function words removed.

    Precision matters more than recall here in a way that is worth stating: a
    MISS costs an empty matrix, which is where we already are. A FALSE MATCH
    supplies a real, checkable, museum-sourced credit line belonging to a
    DIFFERENT WORK, and every gate downstream passes it because it is genuinely
    grounded — just not in this object. Asymmetric, so the threshold is high and
    the scoring is symmetric (both directions must agree) rather than measuring
    only how much of the query is covered.
    """
    a = {t for t in re.findall(r'\w{3,}', fold(want)) if t not in _STOPWORDS}
    b = {t for t in re.findall(r'\w{3,}', fold(got)) if t not in _STOPWORDS}
    if not a or not b:
        return 0.0
    overlap = len(a & b)
    # Harmonic mean of coverage-of-query and coverage-of-result. A short query
    # buried in a long unrelated title scores low on the second term, which is
    # exactly the Moses case.
    p, r = overlap / len(a), overlap / len(b)
    return 0.0 if not (p and r) else 2 * p * r / (p + r)


def find_object_record(title: str, venue_url: str, artist: str = '',
                       min_score: float = 0.75) -> Tuple[Dict[str, str], str]:
    """Search a venue's collection for one work. Returns (fields, url).

    Returns ({}, '') on anything less than a confident title match. A WRONG
    object record is far worse than none: it would supply a real, checkable,
    grounded credit line belonging to a different work, and every gate
    downstream would pass it.
    """
    if not title or not venue_url:
        return {}, ''
    # The stop title often carries OUR English gloss — "Le Lézard aux plumes
    # d'or (The Lizard with Golden Feathers)" — and the museum record carries
    # only the French. Scoring the full string against the record gave 0.40 and
    # missed a record that was the top search hit, because five of its seven
    # content tokens are the gloss we added ourselves. So both forms are scored
    # and the better one wins: the record may legitimately match either.
    bare = re.sub(r'\s*\([^)]*\)\s*', ' ', title).strip() or title
    gloss = ''
    _g = re.search(r'\(([^)]{4,})\)', title)
    if _g:
        gloss = _g.group(1).strip()
    forms = [f for f in (bare, gloss, title) if f]
    query = quote(bare)
    for host in collections_hosts_for(venue_url):
        html = _fetch(f'https://{host}/search/Objects/*/{query}')
        if not html:
            continue
        best, best_score = '', 0.0
        seen = set()
        for m in re.finditer(r'href="(/objects/(\d+)[^"]*)"[^>]*>(.{0,200}?)</a>',
                             html, re.S):
            oid = m.group(2)
            if oid in seen:
                continue
            seen.add(oid)
            text = re.sub(r'<[^>]+>', ' ', m.group(3)).strip()
            if not text:
                continue
            score = max(_title_match_score(f, text) for f in forms)
            if score > best_score:
                best_score, best = score, f'https://{host}/objects/{oid}'
        if best and best_score >= min_score:
            fields = parse_object_page(_fetch(best))
            # [D501] ARTIST CONFIRMATION. The title score alone put "Moses and
            # Monotheism" onto a Rembrandt-school "Moses Striking the Rock" and
            # filled the matrix with another work's credit line and provenance —
            # grounded, checkable and about the wrong object, which every gate
            # downstream would have passed. When we know the artist, the record
            # must not contradict it.
            if fields and artist:
                surname = fold(artist).split()[-1] if artist.split() else ''
                blob = fold(' '.join(str(v) for v in fields.values()))
                if surname and len(surname) > 2 and surname not in blob:
                    print(f"    [D501] REJECTED {best} — title scored "
                          f"{best_score:.2f} but '{artist}' appears nowhere in "
                          f"the record; a wrong record is worse than none")
                    return {}, ''
            if fields:
                return fields, best
    return {}, ''


def _publisher_from_imprint(record: Dict[str, str]) -> Tuple[str, str]:
    """`(Paris: Louis Broder, 1971)` -> ('Louis Broder', '1971')."""
    m = _IMPRINT.search(record.get('record_description', '') or '')
    return (m.group(2).strip(), m.group(3)) if m else ('', '')


def _printer_from_raisonne(record: Dict[str, str]) -> str:
    """A catalogue-raisonné authority that is a KNOWN PRESS is the printer.

    `Cramer, Miró livres illustrés,148; Mourlot 789 - 828` -> `Mourlot`.

    Cramer is a scholar and Mourlot is a press; nothing in the string tells them
    apart, so an unrecognised authority is left alone rather than guessed at. A
    guessed printer is a fabricated agent, which is the whole class of defect the
    step-6 gates exist to catch — and one that would arrive pre-grounded, since
    it really is in the museum's own record.
    """
    line = record.get('catalogue_raisonne', '') or ''
    for m in _CR_REF.finditer(line):
        name = m.group(1).strip()
        if fold(name) in _KNOWN_PRESSES:
            return name
    return ''


def enrich_matrix(matrix: Dict, venue_url: str,
                  verbose: bool = True) -> Tuple[Dict, Dict]:
    """Fill empty matrix slots from the venue's object record.

    Returns (enriched_matrix, report). NEVER overwrites a slot that already
    carries a value — the exhibition checklist is the show's own statement about
    what is on display, and the object record is the museum's statement about the
    object. Where both speak, the show wins; the record fills silence.
    """
    report = {'found': False, 'url': '', 'filled': [], 'record_fields': 0}
    out = dict(matrix)
    title = (matrix.get('canonical_title') or '').strip()
    record, url = find_object_record(title, venue_url,
                                     artist=(matrix.get('artist') or ''))
    if not record:
        if verbose:
            print(f"    [D501] no object record for '{title[:44]}' "
                  f"— matrix unchanged")
        return out, report

    report.update(found=True, url=url, record_fields=len(record))

    publisher, year = _publisher_from_imprint(record)
    printer = _printer_from_raisonne(record)
    derived = {
        'medium': record.get('medium', ''),
        'credit_line': record.get('credit_line', ''),
        'publisher': publisher,
        'printed_by': printer,
        'provenance': record.get('provenance', ''),
        'publication_year': year,
        'accession_number': record.get('accession_number', ''),
        'catalogue_raisonne': record.get('catalogue_raisonne', ''),
    }
    for slot, value in derived.items():
        if not value or is_placeholder(value):
            continue
        existing = (out.get(slot) or '').strip()
        if existing:
            # [D501] ONE EXCEPTION to "the show wins": a credit line carrying a
            # copyright tail. The checklist gives
            #   "Gift of Boris Fridman. © Successió Miró / Artists Rights
            #    Society (ARS), New York / ADAGP, Paris 2026"
            # and the object record gives "Gift of Boris Fridman". D493 recorded
            # the tail as a live bug — it produced the focus fact "Boris Fridman.
            # © Successió Miró / Artists Rights Society (ARS) gave ... to the
            # museum", i.e. a donor named after a rights agency — and predicted
            # it would reappear. The museum's own record is the clean form.
            if slot == 'credit_line' and '©' in existing and '©' not in value:
                out[slot] = value
                report['filled'].append(f'{slot} (copyright tail removed)')
            continue
        out[slot] = value
        report['filled'].append(slot)

    if verbose:
        print(f"    [D501] object record {url}")
        print(f"           {len(record)} fields; filled {report['filled'] or 'nothing'}")
    return out, report
