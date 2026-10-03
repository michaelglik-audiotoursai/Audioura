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
# [D546] Michael, 2026-08-29: a restaurant stop should tell the listener when it
# is open, whether a booking is needed, roughly what it costs, AND WHAT KIND OF
# FOOD IT SERVES. Stop 1 of the v3 tour did all four and he called it fabulous;
# stops 2 and 3 did not. `cuisine` was never acquired at all.
_REQUIRED_ANY = ('hours', 'closed_days', 'reservation', 'price_band', 'cuisine')

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
    "  cuisine      — the KIND of food, as a visitor would describe it: \"classic French "
    "brasserie with Mediterranean touches\", \"seafood\", \"Monegasque traditional\", "
    "\"something for every taste\". Name a signature dish if the results give one.\n"
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
                    f'"{n}" {place} menu price',
                    f'"{n}" {place} cuisine type of food signature dish']
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
            f"Search the web for its current opening days and hours, reservation policy, what a "
            f"visitor should expect to pay for lunch or dinner (or a typical main course), the "
            f"TYPE OF FOOD served, and whether it is still open. Leave a field empty rather than "
            f"guess. Return only the JSON.")
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
    # [LOCAL-570] A vocabulary gap that predates 564: "closing for good" and its
    # kin never bound, so "The Capital Grille Boston Is Closing For Good" kept the
    # venue live. These are PERMANENT-closure phrasings — each can only mean the
    # business is ending, so they go through the same 564 subject/place binding as
    # the markers above. Deliberately NOT here: bare "is closing", "closed", "to
    # close" — those are ambiguous (early close, closed-on-Monday, closing time)
    # and are handled by the temporary exclusion below.
    'closing for good', 'closed for good', 'shutting down for good',
    'has shut down', 'shut its doors', 'shuttered', 'will close permanently',
    'is closing permanently', 'closing its doors',
    'ferme ses portes', 'a fermé ses portes',
)


# [LOCAL-570] TEMPORARY closure phrasings must NEVER bind. A venue that is
# "temporarily closed", "closed for renovations" or "closed on Mondays" is still
# in business — sending the listener past it is correct, dropping it is the harm.
# These are checked against each clause BEFORE a closure marker can bind: a clause
# carrying any temporary phrasing is skipped. Some are regexes because the surface
# varies — "renovation" / "renovations", any weekday, the French forms. Matched
# case-insensitively, as phrases, against the lowercased clause.
_TEMPORARY_MARKERS = (
    re.compile(r'temporarily closed'),
    re.compile(r'closed for renovations?'),
    re.compile(r'closing early'),
    re.compile(r'closed on (?:monday|tuesday|wednesday|thursday|friday|'
               r'saturday|sunday)s?'),
    re.compile(r'closed for the season'),
    re.compile(r'closed for a private event'),
    re.compile(r'fermeture exceptionnelle'),
    re.compile(r'fermé temporairement'),
    # [LOCAL-570 r2] A time-limited closure is temporary. LEAD's r1 miss:
    # "Neptune Oyster is closing its doors for two weeks for repairs" bound as a
    # permanent closure because "closing its doors" was on the permanent list and
    # nothing in r1 recognised the bounded duration. A marker that sits in the
    # same clause as a BOUNDED DURATION or a RETURN names a venue that is coming
    # back — it must never bind. Deterministic and language-aware, as r1.
    #
    #   bounded duration: "for two weeks", "for a month", "for 3 days"
    re.compile(
        r'\bfor\s+(?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|'
        r'eleven|twelve|several|a few|a couple of)\s+'
        r'(?:day|days|week|weeks|month|months)\b'),
    #   dated reopening window: "until January 5", "until next Monday"
    re.compile(r'\buntil\s+(?:january|february|march|april|may|june|july|'
               r'august|september|october|november|december|monday|tuesday|'
               r'wednesday|thursday|friday|saturday|sunday|\d)'),
    #   "through <month>" — a window with an end
    re.compile(r'\bthrough\s+(?:january|february|march|april|may|june|july|'
               r'august|september|october|november|december)'),
    #   explicit return. "reopens in May", "reopening on the 5th", "will reopen",
    #   "back on Monday". NOTE: these are only consulted when the clause is NOT a
    #   NEGATED return ("will not reopen") — _negated_return guards that above.
    re.compile(r'\breopens?\s+(?:on|in|next|this)\b'),
    re.compile(r'\breopening\s+(?:on|in|next|this)\b'),
    re.compile(r'\bwill\s+reopen\b'),
    re.compile(r'\bback\s+(?:on|in|next)\b'),
    #   French temporary forms: "pour travaux", "jusqu'au <date>", "réouverture"
    re.compile(r'\bpour\s+travaux\b'),
    re.compile(r"\bjusqu'au\b"),
    re.compile(r'\bréouverture\b'),
)


# [LOCAL-570 r2] A NEGATED return is not a return — it confirms a permanent
# closure. "will not reopen" / "won't reopen" / "never reopen" each contain
# "reopen", so the return markers above would wrongly read them as temporary.
# This guard fires FIRST: when a clause negates the reopening, the temporary
# exclusion is suppressed and the closure marker is free to bind.
_NEGATED_RETURN = re.compile(
    r"\b(?:will\s+not|won't|wo\s*n't|never|not)\s+reopen", re.I)


def _negated_return(clause_low):
    """True when the clause explicitly says the venue will NOT reopen.

    A negated return means the closure is permanent, so the temporary exclusion
    must be suppressed. Pure, case-insensitive."""
    return bool(_NEGATED_RETURN.search(clause_low))


def _temporarily_closed(clause_low):
    """True when the clause carries a TEMPORARY-closure phrasing (LOCAL-570).

    A match means the venue is still operating, so the closure markers in the
    same clause must not bind. Pure, case-insensitive phrase match.

    [LOCAL-570 r2] A bounded duration ("for two weeks"), a dated reopening window
    ("until January 5", "through March"), or an explicit return ("reopens in May",
    "will reopen", "pour travaux", "réouverture") all make the closure temporary.
    But a NEGATED return ("will not reopen") is permanent — it is checked first
    and suppresses the exclusion so the closure marker can bind."""
    if _negated_return(clause_low):
        return False
    return any(p.search(clause_low) for p in _TEMPORARY_MARKERS)


# [LOCAL-564 r3] Tokens that begin or belong to a closure-marker phrase and so can
# never CONTINUE a venue name when they follow it. Closure headlines are routinely
# Title Case ("Neptune Oyster Has Permanently Closed"), so the capitalised word
# right after the venue ("Has") would otherwise be misread as part of the name and
# the whole-name match would fail. Derived from the existing closure markers so the
# two stay in lock-step, plus the grammatical auxiliaries that join a venue to a
# closure predicate (is/was/will/closes/closing) which are forms of the same verbs
# but do not appear verbatim in the marker phrases.
_CLOSURE_AUX_TOKENS = frozenset(
    w for m in _CLOSED_MARKERS for w in m.split()
) | {'is', 'was', 'will', 'closes', 'closing'}


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


# ---------------------------------------------------------------------------
# [LOCAL-564] A CLOSURE REPORTED FOR A DIFFERENT PLACE OR A DIFFERENT SUBJECT
# MUST NOT DROP A LIVE VENUE.
#
# D543 (city) and D544 (same sentence) each closed one leak and left the next.
# Two live Boston restaurants were still dropped (LOCAL-563 Gemini baseline):
#
#   Chart House, Boston     dropped on  "Chart House, a riverfront staple in
#                                         Weehawken, New Jersey, has closed as of
#                                         May 14. A Mastro's Steakhouse is planned
#                                         for the site."
#   Buttermilk & Bourbon,   dropped on  "BarLola in Boston's Back Bay Has Closed;
#   Boston                                Buttermilk & Bourbon to Replace It ..."
#
#   Chart House:  WRONG CITY. The notice is about Weehawken, New Jersey; the stop
#                 is Boston, Massachusetts. D543's city key was the LAST WORD of
#                 the location, and the location the pipeline passes is the whole
#                 request — "restaurant tour of Chart House, Boston, MA" — so the
#                 key became "house", which is in "Chart House". The guard checked
#                 the venue's own name, not its city.
#   Buttermilk:   WRONG SUBJECT. City matches (Boston) and the marker shares the
#                 sentence with the name (D544 satisfied), but the thing that
#                 closed is BarLola; "to Replace It" binds the closure to BarLola
#                 and names Buttermilk as its SUCCESSOR — the opposite of closed.
#
# Fix: accept a closure only when BOTH hold. The place must not be CONTRADICTED
# (a US state or country named in the snippet that is not the stop's), and the
# venue must be the SUBJECT that closed (before the marker in its clause, with no
# other business name between them, and no successor phrasing pointing elsewhere).
# The state/country vocabulary is taken from pycountry, not a hand list (D476).
# ---------------------------------------------------------------------------

# Successor/replacement phrasing. When the closure sentence carries any of these,
# the venue named AFTER it is the one taking over — "X has closed; Y to replace
# it" closes X, not Y. These bind the closure to the OTHER name.
_SUCCESSOR_MARKERS = (
    'to replace', 'will replace', 'replaces', 'replaced by', 'to take over',
    'taking over', 'takes over', 'took over', 'in the former', 'in the former home of',
    'in place of', 'will open in its place', 'open in its place', 'moving into',
    'moves into', 'set to open', 'opening in the space', 'in the space',
)

_GEO_CACHE = None


def _geo_vocab():
    """US states + countries from pycountry, lowercased, for place contradiction.

    Returns (states, countries) where each maps a lowercase surface form (full
    name and, for states, the two-letter abbreviation) to a canonical key. Built
    once. If pycountry is missing the maps are empty and place-match degrades to
    "no contradiction found", which keeps a stop rather than dropping it — the
    safe direction (D541: absence of evidence never deletes a stop).
    """
    global _GEO_CACHE
    if _GEO_CACHE is not None:
        return _GEO_CACHE
    states, countries = {}, {}
    try:
        import pycountry
        for sub in pycountry.subdivisions:
            if sub.country_code == 'US':
                name = sub.name.strip()
                states[name.lower()] = name
                # Code is like "US-NJ"; the 2-letter abbrev is what press uses.
                abbr = sub.code.split('-')[-1].lower()
                if len(abbr) == 2:
                    states[abbr] = name
        for c in pycountry.countries:
            countries[c.name.lower()] = c.name
            if getattr(c, 'official_name', None):
                countries[c.official_name.lower()] = c.name
            # "common_name" (e.g. names people actually type) when present.
            if getattr(c, 'common_name', None):
                countries[c.common_name.lower()] = c.name
    except Exception:
        pass
    _GEO_CACHE = (states, countries)
    return _GEO_CACHE


def _parse_stop_place(city):
    """Pull the stop's intended city + region (state/country) out of the location.

    The pipeline passes the user's whole request as `city` —
    "restaurant tour of Chart House, Boston, MA" — not a clean city. The region
    is the trailing comma-segment that pycountry recognises as a US state or a
    country; the city is the segment just before it. Returns
    (city_token, state_canonical, country_canonical), any of which may be ''.
    """
    states, countries = _geo_vocab()
    # Drop a leading "<something> tour of/in" framing and bracketed asides.
    raw = re.sub(r'\s*\([^)]*\)\s*', ' ', city or '').strip()
    raw = re.sub(r'^.*?\btour\s+(?:of|in|around|through)\s+', '', raw, flags=re.I).strip()
    segs = [s.strip() for s in raw.split(',') if s.strip()]
    state_c = country_c = ''
    city_tok = ''
    # Walk from the end: trailing segments are region, the first non-region is city.
    for i in range(len(segs) - 1, -1, -1):
        s_low = segs[i].lower()
        if not state_c and s_low in states:
            state_c = states[s_low]
            continue
        if not country_c and s_low in countries:
            country_c = countries[s_low]
            continue
        # First segment from the right that is not a region token is the city.
        # Strip a trailing venue descriptor after a dash ("… - Back Bay").
        city_tok = re.split(r'\s+[-–—]\s+', segs[i])[-1].strip()
        break
    # A bare "Monaco" is both a city and a country; keep it as the city token too.
    if not city_tok and country_c:
        city_tok = country_c
    return city_tok, state_c, country_c


def _place_contradicted(text, stop_city, stop_state, stop_country):
    """True if `text` names a US state or country that is NOT the stop's.

    This is the Chart House guard: a Weehawken / New Jersey notice names New
    Jersey, the stop is Massachusetts, so the places contradict and the closure
    does not apply here. A snippet that names no region, or only the stop's own
    region, is NOT contradicted.
    """
    states, countries = _geo_vocab()
    low = text.lower()
    found_states, found_countries = set(), set()
    for surface, canon in states.items():
        if len(surface) == 2:
            # A two-letter abbreviation only counts in PRESS FORM: uppercase and
            # standalone, as in "Boston, MA" or "Weehawken, NJ". Lowercase "or"
            # / "in" / "me" / "la" in ordinary prose is not Oregon / Indiana /
            # Maine / Louisiana, and matching them deletes live venues.
            if re.search(rf'(?<![A-Za-z]){surface.upper()}(?![A-Za-z])', text):
                found_states.add(canon)
        else:
            # Full state name: match as whole words, case-insensitive.
            if re.search(rf'(?<![a-z]){re.escape(surface)}(?![a-z])', low):
                found_states.add(canon)
    for surface, canon in countries.items():
        if re.search(rf'(?<![a-z]){re.escape(surface)}(?![a-z])', low):
            found_countries.add(canon)
    if stop_state and found_states and stop_state not in found_states:
        return True, f"names {sorted(found_states)[0]}, stop is in {stop_state}"
    if stop_country and found_countries and stop_country not in found_countries:
        # The stop's own city appearing is fine; only a different COUNTRY counts.
        return True, f"names {sorted(found_countries)[0]}, stop is in {stop_country}"
    return False, ''

# Articles that may lead a proper name and are not part of the "capitalised word
# joined to the name" test — "La Marée" stays allowed, as in r1.
_NAME_ARTICLES = ('the', 'le', 'la', 'les', 'el')


# [LOCAL-564 r3] Short connective words that a Title Case headline leaves in
# lowercase ("Del Toro Has Closed In Back Bay" keeps "in"/"of"/… lower). They do
# not count against the "most words are capitalised" test below.
_TITLE_CASE_MINOR = frozenset({
    'a', 'an', 'and', 'as', 'at', 'but', 'by', 'for', 'from', 'in', 'into',
    'nor', 'of', 'on', 'or', 'the', 'to', 'with', 'vs',
})


def _is_title_case(text_orig):
    """True when `text_orig` reads as a Title Case headline: most of its
    significant words (ignoring minor connectives) start with a capital letter.

    Closure headlines from Eater, the Boston Globe and Patch are Title Case, and
    in that register the capitalisation of the word AFTER a venue carries no name
    signal — every word is capitalised. When this holds, `_whole_name_spans`
    stops reading a capitalised FOLLOWING word as a name continuation (it keeps
    the preceding-word test, so "Del Toro ..." still rejects a bare "Toro").
    """
    words = re.findall(r"[A-Za-z][A-Za-z'’]*", text_orig or '')
    significant = [w for w in words if w.lower() not in _TITLE_CASE_MINOR]
    if len(significant) < 2:
        return False
    capped = sum(1 for w in significant if w[0].isupper())
    # "Most" = a clear majority; require at least ~70% so an ordinary sentence
    # with one or two proper nouns ("Del Toro has closed.") is NOT title case.
    return capped >= max(2, (len(significant) * 7 + 9) // 10)


def _whole_name_spans(text_low, text_orig, venue_low, allow_after=()):
    """Yield (start, end) spans where `venue_low` occurs as the COMPLETE proper
    name in `text_low` — not as a substring of a longer name.

    [LOCAL-564 r2] The Boston miss was a substring match: venue `Toro` matched
    inside `Del Toro has closed` and `Toro Mexican Street Food`. A whole-name
    match requires:

      * the token DIRECTLY BEFORE the name is not a capitalised word joined to
        it (`Del Toro`, `El Toro`) — i.e. not `[A-Z]\\w*` abutting the name,
        unless that word is a leading article of the venue itself; and
      * the token DIRECTLY AFTER the name does not continue it
        (`Toro Mexican Street Food`, `Toro Toro`) — i.e. not another capitalised
        word abutting the name.

    `allow_after` holds place tokens (the stop's own city/state/country) that
    are LOCATORS, not name continuations: "Chart House Boston" and "La Marée
    Monaco" are the venue plus its city, so a following word in `allow_after`
    does not disqualify the span.

    Deterministic, no keyword list. `text_orig` carries the original casing so
    the capitalisation test is meaningful; `text_low` is where we search.
    """
    if not venue_low:
        return
    allow_after = {a.lower() for a in allow_after if a}
    # [LOCAL-564 r3] In a Title Case headline every word is capitalised, so a
    # capitalised word AFTER the venue carries no name signal; skip the
    # following-word capitalisation test for the whole span in that register. The
    # preceding-word test stays, so "Del Toro Has Closed" still rejects "Toro".
    title_case = _is_title_case(text_orig)
    vlen = len(venue_low)
    start = 0
    while True:
        at = text_low.find(venue_low, start)
        if at < 0:
            return
        end = at + vlen
        start = at + 1  # advance for the next search regardless of outcome

        # --- preceding token: a capitalised word joined to the name? ---------
        # Walk back over whitespace; if the char immediately before the name is a
        # letter, the name is glued into a longer token (reject). If separated by
        # a space, inspect the preceding word: a capitalised word that is not a
        # leading article of the venue means the real name is "<Word> <venue>".
        i = at - 1
        if i >= 0 and (text_orig[i].isalpha()):
            # Letter directly abutting (no space): part of a longer token.
            continue
        # Skip a single run of spaces to find the preceding word.
        j = i
        while j >= 0 and text_orig[j].isspace():
            j -= 1
        if j >= 0:
            k = j
            while k >= 0 and (text_orig[k].isalpha() or text_orig[k] == "'"):
                k -= 1
            prev_word = text_orig[k + 1:j + 1]
            if prev_word:
                # A capitalised word before the name joins into it — UNLESS the
                # venue name itself begins with that article (handled below).
                venue_first = venue_low.split()[0] if venue_low.split() else ''
                if prev_word[0].isupper() and prev_word.lower() not in _NAME_ARTICLES:
                    # "Del Toro", "El Toro" — the capitalised predecessor is part
                    # of the real name. Reject this span.
                    continue
                # A leading article that is actually the venue's own first token
                # (e.g. venue "La Marée", text "La Marée") is fine and already
                # inside the matched span, so a separate preceding "La" would be a
                # DIFFERENT article in front — treat a capitalised article the same
                # as any capitalised word only when it is NOT the venue's own lead.
                if (prev_word.lower() in _NAME_ARTICLES
                        and prev_word[0].isupper()
                        and prev_word.lower() != venue_first):
                    continue

        # --- following token: a capitalised word continuing the name? --------
        n = end
        if n < len(text_orig) and text_orig[n].isalpha():
            # Letter directly abutting (no space): part of a longer token.
            continue
        m = n
        while m < len(text_orig) and text_orig[m].isspace():
            m += 1
        if m < len(text_orig):
            p = m
            while p < len(text_orig) and (text_orig[p].isalpha() or text_orig[p] == "'"):
                p += 1
            next_word = text_orig[m:p]
            if (next_word and next_word[0].isupper()
                    and next_word.lower() not in allow_after
                    and next_word.lower() not in _CLOSURE_AUX_TOKENS
                    and not (title_case and next_word.lower() in _TITLE_CASE_MINOR)):
                # "Toro Mexican", "Toro Toro" — the capitalised successor continues
                # the name. ("Chart House Boston", "La Marée Monaco" are exempt:
                # the successor is the stop's own city/region, a locator.) Reject.
                #
                # [LOCAL-564 r3] Exemptions that let a Title Case closure headline
                # (Eater/Globe/Patch) bind without reading its capitalisation as a
                # name signal:
                #  * `_CLOSURE_AUX_TOKENS`: a following word that begins/belongs to
                #    the closure phrase never continues a name — "Neptune Oyster
                #    Has Permanently Closed" ("Has" is the verb, not the venue).
                #  * in a `title_case` clause, a following MINOR connective
                #    (in/of/at/…) is likewise not a continuation; the headline
                #    capitalises it only by convention ("Neptune Oyster In Boston
                #    Has Closed"). A real name continuation ("Toro Mexican") is a
                #    non-minor, non-closure word and is still rejected, and the
                #    preceding-word test keeps "Del Toro ..." from matching a bare
                #    "Toro" even in Title Case.
                continue

        yield (at, end)


def _whole_name_at(text_low, text_orig, venue_low, allow_after=()):
    """First whole-name span start, or -1. See `_whole_name_spans`."""
    for s, _e in _whole_name_spans(text_low, text_orig, venue_low, allow_after):
        return s
    return -1


def _title_starts_with_venue(title, venue_low):
    """True when `title` STARTS with the venue as a whole name (leading article
    allowed). Used for the bare-status-fragment Yelp case."""
    if not title or not venue_low:
        return False
    t_low = title.lower()
    head = re.sub(r'^(the|le|la|les|el)\s+', '', t_low.strip())
    v = re.sub(r'^(the|le|la|les|el)\s+', '', venue_low.strip())
    if not head.startswith(v):
        return False
    # The character after the matched venue must not continue the name.
    after_at = len(t_low) - len(head) + len(v)
    if after_at < len(t_low):
        ch = t_low[after_at]
        if ch.isalpha():
            return False
        # A capitalised word immediately following continues the name.
        rest = title[after_at:].lstrip()
        if rest and rest[0].isalpha() and rest[0].isupper():
            # Allow a separator (dash/comma) between venue and city; only reject
            # when the venue is directly glued to another capitalised word with
            # just a space, e.g. "Toro Mexican".
            if title[after_at:after_at + 1] == ' ':
                return False
    return True


def _closure_binds(snippet, title, url, venue, city):
    """Does this snippet report THIS venue, in THIS place, as the thing that closed?

    Pure function over text — no network — so it is unit-testable from the exact
    snippets that shipped the defect. Returns (binds: bool, reason: str). When it
    returns False the reason explains which check rejected it, for the
    `[LOCAL-564] closure REJECTED (<reason>)` log.
    """
    text = f"{title or ''}. {snippet or ''}".strip()
    low = text.lower()
    v_low = (venue or '').lower().strip()
    if not v_low or not low:
        return False, 'empty'

    city_tok, stop_state, stop_country = _parse_stop_place(city)
    city_low = (city_tok or '').lower()
    # Place tokens that may follow the venue as a LOCATOR, not a name
    # continuation: "Chart House Boston", "La Marée Monaco". Split multi-word
    # cities ("Newton Centre") into their words so each is exempt individually.
    place_tokens = set()
    for part in (city_low, (stop_state or '').lower(), (stop_country or '').lower()):
        for w in part.split():
            if w:
                place_tokens.add(w)

    # --- PLACE MATCH -------------------------------------------------------
    # Reject outright if the snippet names a US state or country that is not the
    # stop's. This is the Chart House / Weehawken guard — and the ONLY place
    # gate. [LOCAL-564 r2] The old "closure names no place matching the stop"
    # rejection is gone: it regressed the case that matters most (Neptune Oyster
    # "has permanently closed" named no place, so it was kept live and a listener
    # was sent to a shuttered restaurant). No contradiction plus a subject match
    # now means bound; the subject match is the gate.
    contradicted, why = _place_contradicted(text, city_tok, stop_state, stop_country)
    if contradicted:
        return False, f"wrong place: {why}"

    # --- SUBJECT MATCH -----------------------------------------------------
    # The closure marker must be PREDICATED OF THIS VENUE, not merely co-occur
    # with it. Split into clauses on sentence punctuation AND semicolons — a
    # semicolon joins two independent businesses ("BarLola ... Has Closed;
    # Buttermilk & Bourbon to Replace It") and each side must be judged alone.
    #
    # [LOCAL-564 r2] Split the ORIGINAL-cased text too and carry it alongside each
    # lowercase clause, so the whole-name test (`_whole_name_at`) can read the
    # capitalisation that distinguishes "Del Toro" from a standalone "Toro".
    _splitter = r'(?<=[.!?;])\s+|;'
    clauses = [c for c in re.split(_splitter, low) if c.strip()]
    clauses_orig = [c for c in re.split(_splitter, text) if c.strip()]
    for idx, clause in enumerate(clauses):
        clause_orig = clauses_orig[idx] if idx < len(clauses_orig) else clause
        marker = next((m for m in _CLOSED_MARKERS if m in clause), None)
        if not marker:
            continue
        # [LOCAL-570] A clause that is really a TEMPORARY-closure notice
        # ("temporarily closed", "closed for renovations", "closed on Mondays",
        # "fermé temporairement") must never bind, even though it contains a
        # closure-marker substring. The venue is still in business; skip it.
        if _temporarily_closed(clause):
            continue
        m_at = clause.find(marker)
        # Whole-name position of the venue in THIS clause (not a substring of a
        # longer proper name). -1 when the venue is not present as a whole name.
        v_at = _whole_name_at(clause, clause_orig, v_low, place_tokens)

        # Successor phrasing in the marker clause binds the closure to the OTHER
        # name: "X Has Closed; Y to Replace It" closes X. If our venue is named
        # with successor phrasing, it is the replacement, not the closed thing.
        succ = next((s for s in _SUCCESSOR_MARKERS if s in clause), None)
        if succ and v_at >= 0:
            succ_at = clause.find(succ)
            # Venue sits after the marker as the thing replacing it.
            if v_at > m_at and succ_at >= 0:
                return False, (f"successor phrasing '{succ}': venue is the "
                               f"replacement, not closed")

        if v_at >= 0:
            # Venue named in the marker clause as a whole name. It must be the
            # SUBJECT — before the marker. A name only AFTER the marker (a list
            # item, a successor) is not what closed.
            if v_at > m_at:
                return False, "venue named after the closure marker, not its subject"
            return True, 'bound'

        # Venue NOT a whole name in the marker clause. Two possibilities remain:
        #  (a) the marker clause is a bare STATUS fragment and the subject is in
        #      the immediately preceding clause ("<Venue>. Permanently closed.");
        #  (b) the marker clause is a bare STATUS fragment and the subject is in
        #      the TITLE/URL ("Permanently closed." + title "Neptune Oyster -
        #      Boston - Yelp", slug naming Boston).
        before_marker = clause[:m_at].strip()
        before_marker = re.sub(r'^(the|a|an)\s+', '', before_marker)
        if before_marker:
            # The marker clause names its own subject — not our venue.
            return False, "closure predicated of another business, not the venue"

        # (a) look back one clause for the venue as its head.
        prev = clauses[idx - 1] if idx > 0 else ''
        prev_orig = clauses_orig[idx - 1] if idx > 0 and (idx - 1) < len(clauses_orig) else ''
        if prev and _whole_name_at(prev, prev_orig, v_low, place_tokens) >= 0:
            # Require the venue to START the preceding clause (allowing a leading
            # article), so "La Marée Monaco" heads it but a list does not.
            head = re.sub(r'^(the|le|la|les|el)\s+', '', prev.strip())
            if head.startswith(re.sub(r'^(the|le|la|les|el)\s+', '', v_low)):
                # And the preceding clause must not itself be successor phrasing.
                if any(s in prev for s in _SUCCESSOR_MARKERS):
                    return False, "preceding clause is successor phrasing, not a closure"
                return True, 'bound'
            return False, "venue is not the subject of the closure notice"

        # (b) bare status fragment, snippet names no subject: accept when the
        #     TITLE starts with the venue (whole-name) AND the title or URL slug
        #     names the stop's city, and nothing contradicts the place (already
        #     checked above). This is the Yelp listing case.
        snip_low = (snippet or '').lower()
        snippet_names_subject = _whole_name_at(snip_low, snippet or '', v_low, place_tokens) >= 0
        if not snippet_names_subject and _title_starts_with_venue(title, v_low):
            city_in_title = bool(city_low and city_low in (title or '').lower())
            city_in_url = bool(city_low and url and city_low in url.lower())
            if city_in_title or city_in_url:
                return True, 'bound (title subject + city in title/url)'

    return False, 'no closure marker predicated of the venue'


def closure_scan(name, city):
    """A dedicated closure probe, run across spelling variants.

    Deterministic string matching over search snippets — not an LLM judgement.
    The LLM half already proved it will believe whichever page it is shown; this
    asks one narrow question of the raw text instead.

    [LOCAL-564] A match now requires BOTH a place that is not contradicted and
    the venue being the SUBJECT that closed. See `_closure_binds`.

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
                binds, reason = _closure_binds(
                    item.get('snippet', ''), item.get('title', ''),
                    item.get('url', ''), v, city)
                if binds:
                    return True, f"{item['snippet'][:160]} [{item.get('url','')}]"
                # [LOCAL-564] Say WHY a co-occurring closure was not applied, so a
                # kept-live venue is auditable instead of silent. Only log when a
                # closure marker was actually present but rejected.
                if reason and reason not in ('empty', 'no closure marker predicated of the venue'):
                    _snip = (item.get('snippet', '') or '')[:120]
                    print(f"  [LOCAL-564] closure REJECTED ({reason}) for '{v[:40]}' "
                          f"— kept live: {_snip}")
    return False, ''


def _fields(d):
    return {k: str((d or {}).get(k, '') or '').strip()
            for k in ('status', 'hours', 'closed_days', 'reservation',
                      'price_band', 'michelin', 'cuisine', 'evidence')}


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
           'price_band': '', 'michelin': '', 'cuisine': '', 'evidence': '', 'sources': [],
           'provider': '', 'usable': False, 'deliverable': True, 'reason': ''}
    if not name:
        out['reason'] = 'no name'
        return out

    evidence = _search_evidence(name, city)
    out['sources'] = [e['url'] for e in evidence if e.get('url')][:6]
    parsed = _extract(name, city, evidence, api_key, timeout=timeout)
    provider = f"serp({len(evidence)})+openai" if parsed else ''

    fields = _fields(parsed)
    # [D546] Escalate to Gemini when ANY key field is missing, not only when
    # everything is. Michael, 2026-08-29: "If we add this to each restaurant that
    # has that information easily available in SERPER and/or Gemini".
    #
    # Measured: SERP+OpenAI gave Cafe de Paris its hours and cuisine but no price
    # and no booking policy, so the old all-or-nothing `_thin` test never
    # escalated — while his own Gemini query returned starters EUR 15-35, mains
    # EUR 35-80, and EUR 70-130 per head. The data was one call away.
    #
    # Gemini fills ONLY the empty fields. It never overwrites something the
    # grounded SERP path already established.
    _KEY = ('hours', 'closed_days', 'reservation', 'price_band', 'cuisine')
    _missing = [k for k in _KEY if not fields.get(k)]
    if _missing:
        g = _gemini(name, city, timeout=timeout)
        if g:
            gf = _fields(g)
            _filled = [k for k in _missing if gf.get(k)]
            for k in _filled:
                fields[k] = gf[k]
            if _filled:
                provider = (provider + '+gemini') if provider else 'gemini'
                if g.get('_sources') and not out['sources']:
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
                       ('Cuisine / type of food', 'cuisine'), ('Rating', 'michelin')):
        if p.get(key):
            lines.append(f"  - {label}: {p[key]}")
    if not lines:
        return ""
    return (
        "\nPRACTICAL FACTS FOR THIS RESTAURANT — VERIFIED FROM PUBLISHED SOURCES.\n"
        + "\n".join(lines) + "\n"
        "TELL THE LISTENER EVERY ONE OF THESE THAT APPEARS ABOVE, in the narrator's own voice, "
        "before the stop ends: WHEN IT IS OPEN (days and hours), WHETHER A BOOKING IS NEEDED, "
        "ROUGHLY WHAT IT COSTS, and WHAT KIND OF FOOD IT SERVES.\n"
        "They are standing outside deciding whether to go in. A story about the chef that never "
        "says the place shuts on Mondays, or what a meal costs, or whether it is seafood or a "
        "brasserie, has failed them. Weave them into the prose - do not read a list.\n"
        "State these as fact; they are sourced. **If one of them is NOT listed above, say nothing "
        "about it** - do not guess an opening time, a price or a cuisine. An invented opening hour "
        "sends someone to a locked door.\n"
    )

# ---------------------------------------------------------------------------
# [D547] RESTORED. D546's prompt-block edit sliced from an index TO THE END OF
# THE FILE and replaced it, silently deleting this entire section. The next run
# printed 'cannot import name propose_replacements' and shipped Le Vistamar and
# La Maree - both known-closed - because the whole D538 block was skipped.
# Recovered verbatim from edb45d1.
# ---------------------------------------------------------------------------
# [D545] REPLENISHMENT — Michael, 2026-08-28:
#   "why would you recommend shipping while the wrong number of stops at the
#    place where the stops can be plentiful is a terrible bug! The system can not
#    find 3 restaurants in Monaco, really???"
#
# He is right and the previous judgement was wrong. Dropping a dead restaurant is
# correct; delivering 2 of 3 because of it is not, and announcing the shortfall
# does not discharge it. Monaco has hundreds of restaurants.
#
# Bounded and ADDITIVE by construction: this can only propose extra candidates,
# never remove one. Every proposal is vetted by the same corpus + closure checks
# that dropped the original, so replenishment cannot smuggle a dead venue back in.
# ---------------------------------------------------------------------------

_REPLACE_SYSTEM = (
    "You name real {kind} for an audio walking tour. Return ONLY places that CURRENTLY EXIST and "
    "that a visitor could reach this month.\n"
    "\n"
    "Rules:\n"
    "- Real, specific, named places. No categories, no invented names.\n"
    "- Do NOT return any name on the exclusion list, or a renamed version of one.\n"
    "- They must be INSIDE the area named below. A famous place in the next town is the single "
    "most common mistake here and it gets the stop deleted later.\n"
    "- Prefer places with a STORY: a founding, a siege, a famous resident, a scandal, a disaster, "
    "a first. A tour needs something to say.\n"
    "- If you are not confident a place still exists under that name, leave it out.\n"
    "\n"
    'Return ONLY JSON: {{"places": [{{"name": "", "why": "<the story in one clause>"}}]}}'
)


def propose_replacements(city, exclude, n, api_key, model=None, timeout=45,
                         kind='restaurants'):
    """Name `n` more real, currently-existing places in `city`, excluding `exclude`.

    [D556] Michael, 2026-08-30: "fix all tour type as a replenishment is a general
    process for any tour." A walking tour of Cimiez asked for 6 stops and got 4 —
    the scope check correctly removed Villa Leopolda (Villefranche-sur-Mer) and the
    Matisse Chapel (Vence), and nothing replaced them, because this was written
    restaurant-only.

    `kind` is the noun the model is asked for: "restaurants", "places to visit",
    "landmarks". Everything else is identical.

    Returns a list of {'name','why'}. Never raises; an empty list means the tour
    stays short and the D536 shortfall notice reports it honestly.
    """
    if not city or n <= 0 or not api_key:
        return []
    import requests
    _ex = ', '.join(sorted({e for e in (exclude or []) if e})) or '(none)'
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            data=json.dumps({
                "model": model or os.environ.get("TOUR_PRACTICALS_MODEL", "gpt-4o"),
                "messages": [
                    {"role": "system", "content": _REPLACE_SYSTEM.format(kind=kind)},
                    {"role": "user", "content":
                        f"Area: {city}\nExclude: {_ex}\n\nName {n + 2} {kind} INSIDE that area."},
                ],
                "temperature": 0.3, "seed": 7, "max_tokens": 600,
                "response_format": {"type": "json_object"},
            }),
            timeout=timeout,
        )
        if resp.status_code != 200:
            return []
        _d = json.loads(resp.json()["choices"][0]["message"]["content"])
        out = []
        for r in (_d.get('places') or _d.get('restaurants') or []):
            nm = (r.get('name') or '').strip() if isinstance(r, dict) else str(r).strip()
            if nm:
                out.append({'name': nm,
                            'why': (r.get('why', '') if isinstance(r, dict) else '')})
        return out
    except Exception:
        return []
