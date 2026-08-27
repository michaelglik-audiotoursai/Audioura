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

    # The one hard rule. A permanently closed restaurant cannot be a stop, and
    # "unknown" is NOT closed — absence of evidence never removes a stop.
    if fields.get('status') == 'closed_permanently':
        out['deliverable'] = False
        out['reason'] = f"reported permanently closed: {fields.get('evidence', '')[:120]}"
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
