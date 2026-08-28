"""restaurant_practicals.py — D538: for a restaurant, the practicals ARE the content.

**Michael, 2026-08-27**, agreeing with the Monaco tour's judgement:

  "For museums, it is nice to have but most listeners would check hours and days
   before visiting, but for the restaurants the tour stop can not be a stop if the
   restaurant is closed or the menu is overpriced. If the information does not come
   from the first request to OpenAI.API, we should be querying this from Gemini and
   SERP."

The Monaco tour printed `[LOCAL-36] PRACTICAL FACTS GATE: PASSED (0 verified)` and
contained no hours, no prices and no booking requirement — for three restaurants.
**It passed because it verified nothing, not because everything checked out.**

`practical_facts_gate` is SUBTRACTIVE by design: it takes claims the narration
already made and drops the ones it cannot trace to a source. That is correct for a
museum, where a wrong opening time is an inconvenience. It cannot help when the
narration made no claims at all, and for a restaurant that silence is the failure:
a stop the listener cannot enter is not a stop.

This module is the ACQUISITION half, and it escalates in Michael's order:

    1. SERP        — a real search for hours/prices/status. Grounded, cheap, first.
    2. OpenAI      — extracts structured facts FROM those results, not from memory.
    3. Gemini      — only if 1+2 came back thin, and only when GEMINI_API_KEY is set.

**On dropping stops.** A PERMANENTLY CLOSED restaurant is dropped: it cannot be
visited, and that is not a judgement call. **Price is deliberately NOT a drop
criterion** — Le Louis XV is one of the most expensive restaurants in Europe and
was the best stop in the Monaco tour. Michael's "overpriced" is a real concern, but
the honest remedy is to TELL the listener the price band before they walk in, not
to have the system quietly decide what they can afford. The band is captured,
surfaced, and left to the listener.
"""
import json
import os
import re

# What a restaurant stop must be able to answer before it is deliverable.
_REQUIRED_ANY = ('hours', 'closed_days', 'reservation', 'price_band')

_EXTRACT_SYSTEM = (
    "You extract PRACTICAL VISITOR FACTS about one restaurant from web search results. A "
    "listener is standing outside and needs to know whether they can go in.\n"
    "\n"
    "Use ONLY the search results provided. Do not fill gaps from memory — an invented opening "
    "time sends someone to a locked door, which is the exact harm this exists to prevent. Leave "
    "a field empty rather than guess.\n"
    "\n"
    "Fields:\n"
    '  status       — "open" | "closed_permanently" | "unknown". Say closed_permanently ONLY if '
    "the results state the restaurant has closed, shut down, or been replaced. Absence of "
    "evidence is \"unknown\", never \"closed_permanently\".\n"
    "  hours        — opening hours as stated, e.g. \"12:00-14:00, 19:30-22:00\"\n"
    "  closed_days  — days it is shut, e.g. \"Monday, Tuesday\"\n"
    "  reservation  — booking requirement, e.g. \"reservation essential, often weeks ahead\"\n"
    "  price_band   — what a meal costs, as concretely as the results allow, e.g. "
    "\"tasting menu around 390 EUR\" or \"main courses 45-70 EUR\"\n"
    "  michelin     — stars or other rating if stated\n"
    "  evidence     — one short quote from the results supporting status\n"
    "\n"
    'Return ONLY JSON with exactly those keys, using "" for anything the results do not state.'
)


def _serp(query, max_results=8):
    try:
        from work_story_searcher import _serp_search
    except Exception:
        return []
    try:
        results, _ = _serp_search(query)
    except Exception:
        return []
    out = []
    for r in (results or [])[:max_results]:
        sn = (r.get('snippet') or '').strip()
        if sn:
            out.append({'snippet': sn, 'url': r.get('url', ''), 'title': r.get('title', '')})
    return out


def _search_evidence(name, city):
    """Step 1 — SERP. Three angles, because one query does not cover all fields."""
    bare = re.sub(r'\s*\([^)]*\)\s*', ' ', name or '').strip()
    place = (city or '').split(',')[0].strip()
    # Restaurant names arrive as compounds — "Le Louis XV - Alain Ducasse à
    # l'Hôtel de Paris". Quoted whole, that returns almost nothing (measured: 3
    # snippets, versus 21 for a plain name). The house name before the dash or
    # the "à l'Hôtel" is what the web indexes, so search both forms.
    core = re.split(r'\s+[-–—]\s+|\s+à\s+l', bare)[0].strip()
    names = [bare] if core == bare else [core, bare]
    queries = []
    for n in names:
        queries += [f'"{n}" {place} opening hours reservation',
                    f'"{n}" {place} menu price']
    queries.append(f'"{names[0]}" {place} closed permanently')
    seen, ev = set(), []
    for q in queries:
        for item in _serp(q):
            if item['snippet'] not in seen:
                seen.add(item['snippet'])
                ev.append(item)
    return ev


def _extract(name, city, evidence, api_key, model=None, timeout=45):
    """Step 2 — OpenAI, reading the SERP results rather than its own memory."""
    if not evidence or not api_key:
        return None
    import requests
    ev = "\n".join(f"- {e['snippet']}  [{e.get('url','')}]" for e in evidence[:14])
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            data=json.dumps({
                "model": model or os.environ.get("TOUR_PRACTICALS_MODEL", "gpt-4o"),
                "messages": [
                    {"role": "system", "content": _EXTRACT_SYSTEM},
                    {"role": "user",
                     "content": f"Restaurant: {name}\nCity: {city}\n\nSEARCH RESULTS:\n{ev}"},
                ],
                "temperature": 0.0, "seed": 7, "max_tokens": 600,
                "response_format": {"type": "json_object"},
            }),
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None
        return json.loads(resp.json()["choices"][0]["message"]["content"])
    except Exception:
        return None


def _gemini(name, city, timeout=45):
    """Step 3 — Gemini with sources, only when the first two came back thin."""
    if not os.environ.get('GEMINI_API_KEY'):
        return None
    try:
        from story_leads import gemini_with_sources
    except Exception:
        return None
    try:
        res = gemini_with_sources(
            f"{_EXTRACT_SYSTEM}\n\nRestaurant: {name}\nCity: {city}\n\n"
            f"Search the web for its current opening hours, closed days, reservation policy, "
            f"price band, and whether it is still open. Return only the JSON.")
        text = res.get('text', '') if isinstance(res, dict) else str(res)
        m = re.search(r'\{.*\}', text, re.S)
        if not m:
            return None
        parsed = json.loads(m.group(0))
        if isinstance(res, dict) and res.get('sources'):
            parsed['_sources'] = res['sources']
        return parsed
    except Exception:
        return None


# [D539] CLOSURE IS ASYMMETRIC, AND THE FIRST VERSION TREATED IT AS SYMMETRIC.
#
# La Marée Monaco closed on 30 September 2020. D538 cleared it and it shipped as a
# stop. Michael found it. The diagnosis is not "the model was wrong" — it is that
# the SAME restaurant returns OPPOSITE verdicts depending on the spelling searched:
#
#   "La Maree"  -> closed_permanently   "La Marée Monaco. Permanently closed."
#   "La Marée"  -> open                 "Don't miss La Marée ... open 7 days a week"
#
# Both kinds of page exist at once. Aggregators keep stale listings with plausible
# hours long after a closure, and marketing copy outlives the business. So a
# verdict formed by weighing "evidence of closure" against "evidence of operation"
# is decided by whichever snippets SERP happens to return.
#
# The two costs are not equal. Skipping a restaurant that is actually open costs
# the listener one stop. Sending them to a locked door is the harm this exists to
# prevent. So closure evidence is DECISIVE: a credible "permanently closed" signal
# ends the question, whatever else the page set contains.
_CLOSED_MARKERS = (
    'permanently closed', 'closed permanently', 'now closed', 'has closed',
    'closed down', 'définitivement fermé', 'fermé définitivement',
    'ferme definitivement', 'closed its doors', 'ceased trading',
    'no longer in business', 'no longer open', 'out of business',
)


# [D540] A REBRAND IS NOT A CLOSURE, AND THE CHECK ONLY KNEW THE WORD "CLOSED".
#
# Michael, 2026-08-28: "Le Vistamar no longer exists under that name ... The space
# is now home to Pavyllon Monte-Carlo." Second live miss he has found, and it got
# past D539 because a rebrand has a different linguistic signature:
#
#   closure  "La Marée Monaco. Permanently closed."
#   rebrand  "now home to Pavyllon Monte-Carlo"     <- no closure words at all
#
# Verified: closure_scan('Le Vistamar', 'Monaco') -> (False, '').
#
# **And we already had the evidence and misread it.** The delivered tour said:
#   "It was recently announced that Michelin-starred chef Yannick Alléno will be
#    taking the helm, promising a fresh chapter for Le Vistamar."
# Retrieval found the right chef and the right event, then concluded "new chef at
# the same restaurant" rather than "this restaurant was replaced". The failure was
# interpretation, not access.
_REBRAND_MARKERS = (
    # Deliberately narrow. The first version included 'renamed', 'has become',
    # 'in its place' and 'took over the space', and with those the check reported
    # Le Louis XV and Cipriani as gone — on a snippet about Ducasse's stars and one
    # about the Grand Prix. Ordinary restaurant prose is full of near-miss phrasing;
    # only wording that can ONLY mean "this venue trades under a different name now"
    # belongs here.
    'now home to', 'is now called', 'now known as', 'was rebranded',
    'rebranded as', 'was replaced by', 'reopened as', 'transformed into',
    'no longer exists under', 'no longer operates under',
)

_OPERATING_SYSTEM = (
    "You answer ONE question about a restaurant: is it still operating under the name given?\n"
    "\n"
    "A restaurant fails this if it has closed, OR if the venue was rebranded, replaced or taken "
    "over and now trades under a different name. Both cases mean the same thing to a listener "
    "standing outside: the place they were told to visit is not there.\n"
    "\n"
    "Search the web before answering. Be current — a change of chef is NOT a change of "
    "restaurant, but a change of NAME is.\n"
    "\n"
    'Return ONLY JSON: {"still_operating": true|false, "successor": "<the name it trades under '
    'now, or \\"\\">", "changed_on": "<year or date, or \\"\\">", "reason": "<one sentence>"}'
)


def _fold_name(s):
    import unicodedata
    n = unicodedata.normalize('NFKD', (s or '').lower())
    n = ''.join(c for c in n if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', re.sub(r"[^\w\s]", ' ', n)).strip()


_KNOWN_CACHE = None


def known_bad_venue(name, city):
    """[D542] Consult the known-closed corpus IN PRODUCTION, not only in tests.

    `tests/known_closed_venues.json` was built as the answer to Michael's question
    about a mechanism for learning from a miss. It was a test fixture only — and
    on 2026-08-28 **Le Vistamar shipped in a tour again while sitting in that
    file**, because the Gemini rebrand verdict is probabilistic and came back
    "operating" that run.

    A venue a human has already confirmed dead should never depend on a model
    answering the same way twice. This lookup is deterministic, costs nothing, and
    closes the loop between the learning mechanism and the thing it was meant to
    protect.

    Only `expect: "closed"` entries drop. `verify` entries are suspicions and must
    not remove a stop.
    """
    global _KNOWN_CACHE
    if _KNOWN_CACHE is None:
        _KNOWN_CACHE = []
        for cand in (os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  'tests', 'known_closed_venues.json'),
                     '/app/tests/known_closed_venues.json'):
            try:
                with open(cand, encoding='utf-8') as fh:
                    _KNOWN_CACHE = json.load(fh).get('venues', [])
                break
            except Exception:
                continue
    if not _KNOWN_CACHE:
        return False, ''
    n, c = _fold_name(name), _fold_name(city)
    for v in _KNOWN_CACHE:
        if v.get('expect') != 'closed':
            continue
        # [D542] CONTAINMENT, NOT EQUALITY. The caller passes the tour's location
        # string, which is the user's whole request — "Restaurant tour in Monaco",
        # not "Monaco". Exact comparison made this lookup skip every entry, so the
        # corpus worked when called directly and did nothing inside a tour, and
        # Le Vistamar shipped a third time. Verified: k('Le Vistamar','Monaco')
        # was True while k('Le Vistamar','Restaurant tour in Monaco') was False.
        vc = _fold_name(v.get('city', ''))
        if c and vc and vc not in c and c not in vc:
            continue
        for cand in [v.get('name', '')] + list(v.get('aliases', [])):
            f = _fold_name(cand)
            if f and (f == n or f in n or n in f):
                return True, (f"recorded in known_closed_venues.json: "
                              f"{v.get('ground_truth', '')[:150]}")
    return False, ''


def venue_still_operating(name, city, timeout=45):
    """[D540] Is this venue still trading under THIS name?

    Gemini FIRST, not as a last resort. That ordering is the direct answer to
    Michael's question — "how is it that I can get info from Gemini and you can
    not?" We hold a working GEMINI_API_KEY; the D538 chain only consulted it when
    SERP and OpenAI returned nothing actionable, and Le Vistamar returned hours,
    a price band and closed days, so it looked healthy and Gemini was never asked.
    He asked it directly and got the right answer in one sentence.

    Returns (still_operating: bool, detail: str). Unknown answers return True —
    absence of evidence must never delete a stop.
    """
    if os.environ.get('GEMINI_API_KEY'):
        try:
            from story_leads import gemini_with_sources
            # Normalised name: the D539 suite caught 'Le Vistamar Monaco' and
            # 'Vistamar Hotel Hermitage' getting a different verdict from
            # 'Le Vistamar'. Strip the city and any trailing venue qualifier so
            # every phrasing of the same restaurant asks the same question.
            _q = re.sub(r'\s*\([^)]*\)\s*', ' ', name or '').strip()
            _q = re.split(r'\s+[-–—]\s+|\s+à\s+l', _q)[0].strip()
            _city_word = (city or '').split(',')[0].strip()
            if _city_word:
                _q = re.sub(rf'\s+{re.escape(_city_word)}$', '', _q, flags=re.I).strip()
            res = gemini_with_sources(
                f"{_OPERATING_SYSTEM}\n\nRestaurant: {_q}\nCity: {city}\n\n"
                f"Is it still open under this exact name today? Return only the JSON.")
            text = res.get('text', '') if isinstance(res, dict) else str(res)
            m = re.search(r'\{.*\}', text, re.S)
            if m:
                d = json.loads(m.group(0))
                if d.get('still_operating') is False:
                    succ = str(d.get('successor', '') or '').strip()
                    when = str(d.get('changed_on', '') or '').strip()
                    detail = str(d.get('reason', '') or '').strip()
                    bits = [b for b in (detail, f"now: {succ}" if succ else '',
                                        f"changed {when}" if when else '') if b]
                    return False, ' — '.join(bits)[:220]
                if d.get('still_operating') is True:
                    return True, ''
        except Exception:
            pass  # fall through to the search-marker path

    # [D541] THE SEARCH-MARKER FALLBACK IS REMOVED. It emptied a tour.
    #
    # On its first live run it dropped ALL THREE Monaco restaurants and the tour
    # crashed with `max_workers must be greater than 0`. The evidence it acted on:
    #
    #   Le Louis XV  "Built by Louis XIII back in 1623, the estate is now home to
    #                 ... Le Louis XV is a French rest..."
    #   Le Grill     "... now home to Lebanese restaurant concept, Em Sherif.
    #                 The menu at Omer ... Le Grill on the ..."
    #
    # The name-containment guard I added was not enough: a single snippet holds
    # several unrelated clauses, so the venue name and "now home to" can both be
    # present and be about different things. There is no reliable way to bind a
    # marker to a subject with substring matching, and the cost of getting it
    # wrong is deleting a restaurant that is open.
    #
    # Gemini answers this question correctly and cheaply. When it does not answer,
    # the honest result is "unknown", and unknown never removes a stop. The marker
    # list is kept only as documentation of the phrasings observed, and is used by
    # the D539 regression suite to test the CLOSURE path, which matches far more
    # specific wording ("permanently closed") and has not misfired.
    return True, ''


def closure_scan(name, city):
    """A dedicated closure probe, run across spelling variants.

    Deterministic string matching over search snippets — not an LLM judgement.
    The LLM half already proved it will believe whichever page it is shown; this
    asks one narrow question of the raw text instead.

    Returns (is_closed: bool, evidence: str).
    """
    import unicodedata
    bare = re.sub(r'\s*\([^)]*\)\s*', ' ', name or '').strip()
    core = re.split(r'\s+[-–—]\s+|\s+à\s+l', bare)[0].strip()
    # Accent-folded AND accented: they return different result sets, which is the
    # whole reason this defect reached a listener.
    folded = ''.join(c for c in unicodedata.normalize('NFKD', core)
                     if not unicodedata.combining(c))
    place = (city or '').split(',')[0].strip()
    variants = [v for v in dict.fromkeys([core, folded, bare]) if v]
    for v in variants:
        for q in (f'"{v}" {place} permanently closed',
                  f'"{v}" {place} closed down'):
            for item in _serp(q, max_results=8):
                low = item['snippet'].lower()
                if any(m in low for m in _CLOSED_MARKERS):
                    return True, f"{item['snippet'][:160]} [{item.get('url','')}]"
    return False, ''


def _fields(d):
    return {k: str((d or {}).get(k, '') or '').strip()
            for k in ('status', 'hours', 'closed_days', 'reservation',
                      'price_band', 'michelin', 'evidence')}


def _thin(f):
    """True when nothing a listener could act on was found."""
    return not any(f.get(k) for k in _REQUIRED_ANY)


def fetch_practicals(name, city, api_key, timeout=45):
    """SERP -> OpenAI -> Gemini, stopping as soon as the answer is usable.

    Returns {status, hours, closed_days, reservation, price_band, michelin,
             evidence, sources, provider, usable, deliverable, reason}.

    Never raises. A failed lookup returns usable=False and the caller decides —
    it must not be able to break a tour.
    """
    out = {'status': 'unknown', 'hours': '', 'closed_days': '', 'reservation': '',
           'price_band': '', 'michelin': '', 'evidence': '', 'sources': [],
           'provider': '', 'usable': False, 'deliverable': True, 'reason': ''}
    if not name:
        out['reason'] = 'no name'
        return out

    evidence = _search_evidence(name, city)
    out['sources'] = [e['url'] for e in evidence if e.get('url')][:6]
    parsed = _extract(name, city, evidence, api_key, timeout=timeout)
    provider = f"serp({len(evidence)})+openai" if parsed else ''

    fields = _fields(parsed)
    if _thin(fields):
        # Step 3 only when the cheap grounded path produced nothing actionable.
        g = _gemini(name, city, timeout=timeout)
        if g:
            gf = _fields(g)
            if not _thin(gf):
                fields = gf
                provider = (provider + '+gemini') if provider else 'gemini'
                if g.get('_sources'):
                    out['sources'] = list(g['_sources'])[:6]

    out.update(fields)
    out['provider'] = provider or 'none'
    out['usable'] = not _thin(fields)

    # [D539] The closure probe runs ALWAYS and OVERRIDES, including when the
    # extractor confidently reported hours. That combination is exactly what
    # shipped La Marée: stale aggregator hours outvoted a closure notice.
    # [D542] The corpus first — deterministic, and it cannot flip between runs.
    _known, _known_ev = known_bad_venue(name, city)
    if _known:
        out['status'] = 'closed_permanently'
        out['evidence'] = _known_ev
        out['deliverable'] = False
        out['reason'] = _known_ev
        out['provider'] = (out['provider'] or '') + '+known_corpus'
        return out

    _closed, _closed_ev = closure_scan(name, city)
    if _closed:
        out['status'] = 'closed_permanently'
        out['evidence'] = _closed_ev or fields.get('evidence', '')

    # [D540] And the rebrand case, which carries no closure words at all. Runs
    # even when everything above looked healthy — Le Vistamar had hours, a price
    # band and closed days, and had not existed under that name since 2021.
    if out['status'] != 'closed_permanently':
        _open_now, _op_detail = venue_still_operating(name, city, timeout=timeout)
        if not _open_now:
            out['status'] = 'closed_permanently'
            out['evidence'] = _op_detail
            out['successor_note'] = _op_detail

    # The one hard rule. A permanently closed restaurant cannot be a stop, and
    # "unknown" is NOT closed — absence of evidence never removes a stop.
    if out.get('status') == 'closed_permanently':
        out['deliverable'] = False
        out['reason'] = f"reported permanently closed: {out.get('evidence', '')[:150]}"
    elif not out['usable']:
        out['reason'] = 'no actionable practical facts found (SERP, OpenAI, Gemini)'
    return out


def practicals_prompt_block(p):
    """The facts, shaped for the stop prompt, with the disclosure rule attached."""
    if not p or not p.get('usable'):
        return ""
    lines = []
    for label, key in (('Opening hours', 'hours'), ('Closed', 'closed_days'),
                       ('Booking', 'reservation'), ('Price', 'price_band'),
                       ('Rating', 'michelin')):
        if p.get(key):
            lines.append(f"  - {label}: {p[key]}")
    if not lines:
        return ""
    return (
        "\nPRACTICAL FACTS FOR THIS RESTAURANT — VERIFIED FROM PUBLISHED SOURCES.\n"
        + "\n".join(lines) + "\n"
        "You MUST tell the listener the booking requirement and the price band if they appear "
        "above, in plain words, before the stop ends. They are standing outside deciding whether "
        "to go in; a story about the chef that omits 'you will not get a table without booking' "
        "has failed them. State these as fact — they are sourced. Do NOT invent any practical "
        "detail that is not listed above.\n"
    )
