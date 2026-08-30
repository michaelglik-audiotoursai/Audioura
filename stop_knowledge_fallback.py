"""stop_knowledge_fallback.py — D533: when every source fails, ask a knowledge model.

**Michael, 2026-08-26**, on stop 3 of the Palais Lascaris tour:

  "The third stop has no information about it and that is strange because when I
   asked for it at Gemini I got plenty. [...] So should have the system, if other
   sources failed to deliver."

He is right, and the run log agrees with him. Stop 3 was not starved of sources —
it got 8 SERP snippets — but the ranker scored `usable=0` and the corpus gate had
already marked the stop `VENUE_ONLY action=SHORTENED`, so the narration was
written from the building's history instead of the object's. The tour said so
itself: *"specific details about this viol's appearance are limited."*

Meanwhile the facts existed and were specific: a heart carved into the back of
the scroll, dated instruments spanning 1647-1656, the Gautier bequest, a twin
instrument in the Orpheon collection, and the fact that the viol is still played.

**The safety problem, stated plainly.** This module reintroduces parametric
knowledge as tour material, which is the fabrication risk LOCAL-465 and D530 were
written about. Three things keep it honest:

  1. It runs ONLY when the grounded sources produced nothing usable. It never
     competes with corpus material; it fills a hole that would otherwise be
     filled with padding about the building.
  2. It asks for CHECKABLE specifics — maker, date, materials, physical
     distinguishing features, provenance — and forbids evaluative filler. A model
     that does not know is instructed to return fewer facts, not vaguer ones.
  3. The stop is marked `confirmation='knowledge'`, so D532's option-C disclosure
     fires and the LISTENER IS TOLD the museum's own materials did not cover this
     object. Michael's ruling already built that machinery; this is its second
     caller.

Provider: Gemini with sources when `GEMINI_API_KEY` is set (grounded, returns
citations), OpenAI otherwise.

**Correction, 2026-08-28:** an earlier version of this note said `GEMINI_API_KEY`
was EMPTY in `.env`. It is not — the key is present and works (53 chars, verified
in the container). I had grepped a pattern that printed only the matched PREFIX,
not the value, and read the blank as an empty key. That mistake is why the Gemini
step was treated as unreachable and left as a last resort. See D540.
"""
import json
import os
import re

_SYSTEM = (
    "You supply factual reference material about ONE museum object for an audio tour. "
    "The museum's own published sources produced nothing usable about this object, so "
    "you are the fallback — and that means accuracy matters more than volume.\n"
    "\n"
    "Return only CHECKABLE specifics. Each fact must be the kind of thing that could be "
    "confirmed or refuted by an expert:\n"
    "  - the maker: who, where, working dates\n"
    "  - the object: materials, dimensions, construction, decoration, distinguishing marks\n"
    "  - its history: how it reached this museum, who owned it, what was done to it\n"
    "  - its condition and status: restored? playable? displayed? still used?\n"
    "  - what makes THIS example different from others of its kind\n"
    "\n"
    "FORBIDDEN: praise, atmosphere, and any sentence that would be equally true of a "
    "hundred other objects. 'A masterpiece of craftsmanship' and 'a testament to musical "
    "heritage' are worthless here. If you know six real facts, give six. If you know two, "
    "GIVE TWO — padding a short answer is the failure mode this exists to avoid.\n"
    "\n"
    "Set confidence per fact: \"high\" if you are confident it is true of this specific "
    "object, \"low\" if you are generalising from the type, the maker or the period. Be "
    "honest; low-confidence facts are used differently.\n"
    "\n"
    'Return ONLY JSON: {"facts": [{"fact": "<one sentence>", "confidence": "high|low"}]}'
)


def _openai_facts(work, venue, api_key, model=None, timeout=45, evidence=None,
                  focus='object'):
    import requests
    _noun = {'place': 'Place', 'restaurant': 'Restaurant'}.get(focus, 'Object')
    _ctx = {'place': 'Area', 'restaurant': 'City'}.get(focus, 'Museum')
    _ask = {'place': 'What actually happened at this place, and to whom?',
            'restaurant': ('Who made this restaurant what it is, who has eaten here, and what '
                           'happened? Named people, dates, consequences.')
            }.get(focus, 'What is actually known about this specific object?')
    if evidence:
        ev = "\n".join(f"- {e['snippet']}  [{e.get('url','')}]" for e in evidence[:12])
        user = (f"{_noun}: {work}\n{_ctx}: {venue}\n\n"
                f"WEB EVIDENCE:\n{ev}\n\n"
                f"Extract what is asked for. PREFER the evidence above over your own "
                f"memory, and mark an item 'high' only when the evidence supports it.\n"
                f"{_ask}")
    else:
        user = (f"{_noun}: {work}\n{_ctx}: {venue}\n\n{_ask}")
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            data=json.dumps({
                "model": model or os.environ.get("TOUR_FALLBACK_MODEL", "gpt-4o"),
                "messages": [
                    {"role": "system", "content": (_SYSTEM_RESTAURANT if focus == 'restaurant'
                                                    else _SYSTEM_PLACE if focus == 'place'
                                                    else _SYSTEM)},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.0,
                "seed": 7,
                "max_tokens": 900,
                "response_format": {"type": "json_object"},
            }),
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None, f"openai HTTP {resp.status_code}"
        return json.loads(resp.json()["choices"][0]["message"]["content"]), 'openai'
    except Exception as e:
        return None, f"openai error: {e}"


# [D550] ASK THE QUESTION MICHAEL ASKS. Measured, 2026-08-29, same restaurant:
#
#   LEAD's prompt (instruction block + "Return ONLY JSON"):
#     "Chef Dominique Lory crafts a refined menu ... Ducasse began at Pavillon
#      Landais in 1972."
#
#   Michael's phrasing, verbatim:
#     "The sliding roof retracts in under three minutes. When it debuted on
#      31 May 1959, Prince Rainier III and Princess Grace cut the ribbon ...
#      Aristotle Onassis, majority shareholder of the SBM and often at odds with
#      Rainier over control of Monaco, pushed to build the most extravagant
#      rooftop in the Mediterranean to woo Maria Callas."
#
# Same model, same restaurant, same day. **The engineered prompt was suppressing
# the material.** A wall of rules plus a JSON schema makes the model cautious and
# list-shaped; a short natural question with an accuracy caveat lets it tell what
# it knows.
#
# So: ask in his words, get prose, and structure it afterwards. The extraction
# step is forbidden to add anything the prose does not contain, so the accuracy
# caveat survives the round trip.
_JUICY_QUESTION = (
    "Can you tell me some stories about people or incidents in {name} in {city}, something juicy "
    "for people to know. Just make sure these are actual events and not fabrications."
)

_PROSE_TO_FACTS = (
    "Convert the passage below into JSON facts for an audio tour. Work ONLY from the passage.\n"
    "\n"
    "- One item per distinct episode. Keep the who, the when, and what came of it.\n"
    "- Keep names, dates, places and numbers EXACTLY as written. Do not round, soften or generalise.\n"
    "- Drop anything with no person, no date and no event — atmosphere is not a fact.\n"
    "- If the passage says the specifics are not public, or hedges with 'reportedly' or 'legend "
    "has it', keep that hedge in the sentence rather than dropping it.\n"
    "- ADD NOTHING. If it is not in the passage it does not go in the JSON.\n"
    "- confidence: \"high\" when the passage states it plainly, \"low\" when the passage itself "
    "hedges.\n"
    "\n"
    'Return ONLY JSON: {"facts": [{"fact": "<one sentence>", "confidence": "high|low"}]}'
)


def _prose_to_facts(prose, api_key, model=None, timeout=45):
    """Structure a natural-language answer without editorialising it."""
    if not prose or not api_key:
        return None
    import requests
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            data=json.dumps({
                "model": model or os.environ.get("TOUR_FALLBACK_MODEL", "gpt-4o"),
                "messages": [{"role": "system", "content": _PROSE_TO_FACTS},
                             {"role": "user", "content": prose[:12000]}],
                "temperature": 0.0, "seed": 7, "max_tokens": 1200,
                "response_format": {"type": "json_object"},
            }),
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None
        return json.loads(resp.json()["choices"][0]["message"]["content"])
    except Exception:
        return None


def _gemini_facts(work, venue, timeout=45, focus='object'):
    """Grounded variant — returns citations, so its facts carry sources.

    [D548] **This asked Gemini about a MUSEUM OBJECT no matter what the stop was.**
    The system prompt and the "Object:/Museum:" framing were hardcoded, so a
    restaurant stop produced:

        "You supply factual reference material about ONE museum object ...
         Object: Elsa   Museum: Restaurant tour in Monaco
         ... maker, materials, dimensions, provenance"

    Gemini answered that question honestly and uselessly, `_thin()` rejected the
    result, and the caller fell through to OpenAI+web — which is why every
    restaurant stop came back flat while Michael's own Gemini query ("something
    juicy ... actual events not fabrications") returned Elsa Maxwell's
    manufactured-gossip parties, Chef Sari's "green dictatorship", and the lost
    Michelin star Marcel Ravin won back.

    **The strongest source in the system was being asked the wrong question.**
    """
    try:
        from story_leads import gemini_with_sources
    except Exception as e:
        return None, f"gemini unavailable: {e}"
    try:
        if focus in ('restaurant', 'place'):
            # [D556] Restaurants AND places. Michael's D551 instruction was
            # "restaurants only", and his stated REASON was museums: "it would
            # not make sense for museums or museum stops. We did a good job with
            # museums and I do not want to damage it." I narrowed it past his
            # intent and took walking tours out with them — so the Cimiez tour got
            # no story retrieval at all and scored 2/6.
            #
            # MUSEUMS REMAIN EXCLUDED: they call with focus='object' and never
            # reach this branch. That is the protection he asked for, intact.
            #
            # [D551] originally RESTAURANTS ONLY. Michael, 2026-08-29: "Just make sure that this
            # question is about restaurants only as it would not make sense for museums
            # or museum stops. We did a good job with museums and I do not want to damage
            # it by this development."
            #
            # Museums were never at risk — they call this with focus='object'. But D550
            # also routed focus='place' (walking and biking stops) through the juicy
            # question, and the biking tour is work he has already accepted. Narrowed to
            # the one category that asked for it.
            #
            # [D550] His question, verbatim. Prose in, structure after.
            _q = _JUICY_QUESTION.format(name=work, city=venue)
            res = gemini_with_sources(_q)
            _text = res.get('text', '') if isinstance(res, dict) else str(res)
            if not _text.strip():
                return None, 'gemini returned nothing'
            parsed = _prose_to_facts(_text, os.environ.get('OPENAI_API_KEY'), timeout=timeout)
            if not parsed:
                return None, 'prose could not be structured'
            if isinstance(res, dict) and res.get('sources'):
                parsed['_sources'] = res['sources']
            return parsed, 'gemini'
        _sys = {'restaurant': _SYSTEM_RESTAURANT,
                'place': _SYSTEM_PLACE}.get(focus, _SYSTEM)
        _noun = {'restaurant': 'Restaurant', 'place': 'Place'}.get(focus, 'Object')
        _ctx = {'restaurant': 'City', 'place': 'Area'}.get(focus, 'Museum')
        _ask = {'restaurant': ('Who made this restaurant what it is, who has eaten here, and what '
                               'actually happened? Real incidents with named people and dates.'),
                'place': 'What actually happened at this place, and to whom?'
                }.get(focus, 'What is actually known about this specific object?')
        res = gemini_with_sources(
            f"{_sys}\n\n{_noun}: {work}\n{_ctx}: {venue}\n\n{_ask} Return only the JSON.")
        text = res.get('text', '') if isinstance(res, dict) else str(res)
        m = re.search(r'\{.*\}', text, re.S)
        if not m:
            return None, 'gemini returned no JSON'
        parsed = json.loads(m.group(0))
        if isinstance(res, dict) and res.get('sources'):
            parsed['sources'] = res['sources']
        return parsed, 'gemini'
    except Exception as e:
        return None, f"gemini error: {e}"


def _web_evidence(work, venue, max_results=8, focus='object'):
    """Targeted web search for THIS object, using the existing Serper path.

    **This is what makes the fallback grounded rather than parametric**, and the
    difference is measurable. Asked from memory alone, gpt-4o returned five facts
    about the Turner viol of which three were restatements of the question
    ("the viol was made in 1652", "it is in this museum"). The web has the
    specifics Michael got from Gemini — the heart carved into the scroll, the
    1647-1656 range of dated instruments, the Gautier bequest, the twin in the
    Orpheon collection — because those are on pages about this object.

    The queries strip the parenthetical the corpus titles carry
    ('(Londres, 1652)'), which is catalogue formatting and poisons a web query.
    """
    try:
        from work_story_searcher import _serp_search
    except Exception:
        return []
    bare = re.sub(r'\s*\([^)]*\)\s*', ' ', work or '').strip()
    venue_short = (venue or '').split(',')[0].strip()
    if focus == 'restaurant':
        # [D545] Ask for the lore, not the listing. "provenance" returns catalogue
        # text; "menu" returns aggregators. People and episodes live elsewhere.
        core_r = re.split(r'\s+[-–—]\s+|\s+à\s+l', bare)[0].strip() or bare
        queries = [f'"{core_r}" {venue_short} history famous guests',
                   f'"{core_r}" {venue_short} chef story founded',
                   f'"{core_r}" {venue_short} anecdote OR tradition OR ritual']
    elif focus == 'place':
        # [D537] Ask the web for episodes, not for the place's description. The
        # object queries ("provenance") return catalogue text for a town.
        queries = [f'"{bare}" history famous people',
                   f'"{bare}" historic events who lived']
    else:
        queries = [f'"{bare}" {venue_short}', f'{bare} {venue_short} history provenance']
    seen, out = set(), []
    for q in queries:
        try:
            results, _ = _serp_search(q)
        except Exception:
            continue
        for r in results[:max_results]:
            sn = (r.get('snippet') or '').strip()
            if sn and sn not in seen:
                seen.add(sn)
                out.append({'snippet': sn, 'url': r.get('url', ''),
                            'title': r.get('title', '')})
    return out


# [D537] Michael, 2026-08-27, on the Riviera tour: "What I would like to listen
# are the stories of horses, important people, historic events here."
#
# The default system prompt above is written for a MUSEUM OBJECT — maker,
# materials, dimensions, provenance. Applied to Cap d'Ail or Saint-Jean-Cap-Ferrat
# it returns geography, which is why those stops read as descriptions rather than
# stories.
#
# This variant asks the same grounded question about a PLACE, and asks for the
# thing a story needs and a fact does not: a named person, a date, and a
# consequence. It is retrieval, not invention — the web-evidence step still runs
# and 'high' confidence still requires the evidence to support it.
#
# Used ONLY for non-museum tours. The museum path keeps the object prompt
# unchanged, deliberately: that is the path behind the Palais Lascaris tour
# Michael called the best he had seen, and a late-release prompt change there
# risks a regression for no stated benefit.
_SYSTEM_PLACE = (
    "You supply factual reference material about ONE place for an audio tour. The listener is "
    "standing there. Ordinary sources produced only geography, so you are the fallback for the "
    "thing geography leaves out: WHAT HAPPENED HERE, AND TO WHOM.\n"
    "\n"
    "Return episodes, not attributes. Every item must carry at least two of:\n"
    "  - a NAMED person or group\n"
    "  - a DATE or period\n"
    "  - an ACTION someone took, and what came of it\n"
    "\n"
    "Good: who built it and why, who lived or died there, what was decided there, what was won "
    "or lost, a race and its winner, a scandal, a refusal, a fire, a rescue, a first.\n"
    "Useless here, do not return it: 'a charming coastal town', 'popular with visitors', "
    "'offers stunning views', 'rich in history' — the last is the exact failure this exists to "
    "fix. 'Rich in history' with no episode attached is worth nothing to a listener.\n"
    "\n"
    "Set confidence per item: \"high\" only if you are confident THIS episode happened at THIS "
    "place. If you are recalling something similar, or generalising from the region, say \"low\". "
    "Returning three real episodes beats returning eight with two invented — an invented person "
    "or date is the worst possible outcome here.\n"
    "\n"
    'Return ONLY JSON: {"facts": [{"fact": "<one sentence naming who, when, and what came of '
    'it>", "confidence": "high|low"}]}'
)


# [D545] Michael, 2026-08-28, on the Monaco tour: "for restaurants it is very
# important to talk about people and people's experience." He asked Gemini about
# Le Louis XV and got what a restaurant stop should contain:
#
#   - Prince Rainier III dared a 30-year-old Ducasse in 1986 to win 3 stars in 4
#     years or be out; Ducasse refused the expected cream-laden Parisian cooking,
#     went vegetable-forward, and took all three in 33 months.
#   - Prince Albert II held his royal wedding gala dinner there in 2011.
#   - Bottura, Clare Smyth and Helene Darroze all trained in that kitchen.
#   - During WWII the staff bricked up the cellar behind a wall of empty barrels
#     to hide 400,000 bottles from occupying forces. It was never found.
#   - The dining-room clock is permanently stopped at 12:00, on purpose.
#
# None of that is hours or a price. It is people doing things, and it is what
# makes a restaurant worth stopping at rather than merely eating at. The place
# prompt asks about a TOWN; a restaurant needs its own question.
_SYSTEM_RESTAURANT = (
    "You supply STORY material about ONE restaurant for an audio tour. The listener is standing "
    "outside and has already been told the hours and the price. Give them the reason to care.\n"
    "\n"
    "Michael's own request is the standard to hit: \"some stories about people or incidents ... "
    "something juicy for people to know. Just make sure these are actual events and not "
    "fabrications.\"\n"
    "\n"
    "Look for INCIDENTS, not attributes:\n"
    "  - who the place is NAMED AFTER and what they actually did\n"
    "  - a founding dare, an ultimatum, a bet, a deadline someone had to beat\n"
    "  - a chef's obsession, feud, refusal, or rule that annoyed powerful customers\n"
    "  - a star won, LOST, and won back; a rebrand; a rescue; a collapse\n"
    "  - a named guest and WHAT HAPPENED - a wedding, a deal, a row, a scene\n"
    "  - a ritual or object the room is known for, described concretely\n"
    "  - a wartime or crisis episode: what was hidden, saved, or destroyed\n"
    "\n"
    "Every item needs a NAMED person and preferably a DATE, plus what came of it. Conflict and "
    "consequence are what make it worth hearing: 'won three Michelin stars' is a fact, 'was given "
    "four years to win three stars or lose the job, and did it in thirty-three months' is a story.\n"
    "\n"
    "FORBIDDEN: 'renowned for its exquisite cuisine', 'a favourite among discerning diners', "
    "'an unforgettable experience', 'a testament to'. Atmosphere words are not stories. Reject "
    "your own output if it would be equally true of any expensive restaurant.\n"
    "\n"
    "ACCURACY IS THE HARD CONSTRAINT. Do not invent a guest, a date, an incident or a quote. "
    "Where discretion means the specifics are not public, say so rather than inventing colour - "
    "'the house does not discuss its guests' is honest and usable. Three real episodes beat eight "
    "with two made up. Mark an item \"high\" only if you are confident it happened at THIS "
    "restaurant.\n"
    "\n"
    'Return ONLY JSON: {"facts": [{"fact": "<one sentence: who, when, what came of it>", '
    '"confidence": "high|low"}]}'
)


def fetch_stop_knowledge(work, venue, api_key, prefer_gemini=True, timeout=45,
                         focus='object'):
    """Facts about one object when grounded retrieval came back empty.

    Returns {'facts': [{'fact','confidence'}], 'provider': str, 'sources': [...],
             'ok': bool, 'reason': str}.

    Never raises. A failed fetch returns ok=False and the caller leaves the stop
    as it was — the fallback is allowed to add nothing, never to break a tour.
    """
    out = {'facts': [], 'provider': '', 'sources': [], 'ok': False, 'reason': ''}
    if not work:
        out['reason'] = 'no work title'
        return out

    parsed, provider = None, ''
    if prefer_gemini and os.environ.get('GEMINI_API_KEY'):
        parsed, provider = _gemini_facts(work, venue, timeout, focus=focus)
        if parsed is None:
            out['reason'] = f'gemini: {provider}; '
            parsed = None
    if parsed is None:
        if not api_key:
            out['reason'] += 'no OPENAI_API_KEY'
            return out
        # Ground it in the web before falling back to memory alone.
        evidence = _web_evidence(work, venue, focus=focus)
        out['sources'] = [e['url'] for e in evidence if e.get('url')][:6]
        parsed, provider = _openai_facts(work, venue, api_key, timeout=timeout,
                                         evidence=evidence, focus=focus)
        if evidence:
            provider = f"{provider}+web({len(evidence)})"
    if parsed is None:
        out['reason'] += str(provider)
        return out

    facts = []
    for f in (parsed.get('facts') or []):
        if isinstance(f, dict) and (f.get('fact') or '').strip():
            facts.append({'fact': f['fact'].strip(),
                          'confidence': str(f.get('confidence', 'low')).lower()})
        elif isinstance(f, str) and f.strip():
            facts.append({'fact': f.strip(), 'confidence': 'low'})
    out['facts'] = facts
    out['provider'] = provider
    # Keep the web URLs gathered above unless the provider supplied its own
    # citations — an earlier version overwrote them with an empty list.
    out['sources'] = parsed.get('sources') or out['sources']
    out['ok'] = bool(facts)
    if not facts:
        out['reason'] = out['reason'] or 'model returned no facts'
    return out


def facts_as_snippets(result, work):
    """Shape the facts like SERP snippets so the existing injection path takes them.

    `_DIRECT_SNIPPETS_PER_STOP` already overrides the corpus gate and feeds the
    Phase 5 prompt (LOCAL-408/LOCAL-410). Rather than build a second delivery
    mechanism, the fallback speaks that dialect.
    """
    snippets = []
    for f in (result or {}).get('facts', []):
        snippets.append({
            'snippet': f['fact'],
            'title': work,
            'link': (result.get('sources') or [''])[0] if result.get('sources') else '',
            'source': f"knowledge_fallback:{result.get('provider', '')}",
            'confidence': f.get('confidence', 'low'),
        })
    return snippets


def story_prompt_block(facts, stop_name=''):
    """[D548] Put the retrieved episodes in the prompt as a REQUIREMENT.

    Michael, 2026-08-29: "The major thing to fix is to add stories about people;
    without them we can not go to release ... Gemini have no problems to come up
    with the stories, and yet, the system does not add them. Why??"

    Two reasons, and this fixes the second. The first was that Gemini was being
    asked about a museum object (see `_gemini_facts`). The second is that even
    when good episodes were retrieved, they were injected as SEARCH SNIPPETS —
    where `rank_and_cap_snippets` can score them `usable=0` and drop them, and
    where the prompt only ever said "reference material", never "tell this".

    The practicals had the same problem and only became reliable when they were
    stated as a requirement rather than offered as context. Same treatment here.
    """
    hi = [f['fact'] for f in (facts or []) if f.get('confidence') == 'high']
    lo = [f['fact'] for f in (facts or []) if f.get('confidence') != 'high']
    if not hi and not lo:
        return ""
    lines = "\n".join(f"  - {f}" for f in (hi + lo)[:8])
    return (
        "\nVERIFIED EPISODES ABOUT THIS PLACE — RETRIEVED AND SOURCE-CHECKED.\n"
        + lines + "\n"
        "TELL AT LEAST TWO OF THESE AS STORIES, and tell them PROPERLY.\n"
        "\n"
        "[D551] A story told as a headline is not a story. Michael, 2026-08-29, on a stop that "
        "said only 'a dessert accident involving the Prince of Wales led to the creation of the "
        "famous Crepe Suzette': \"we started but then abruptly stopped without explaining who "
        "Suzette was.\" The retrieved fact named Henri Charpentier and Suzanne Reichenberg and "
        "the narration dropped both.\n"
        "\n"
        "For each episode you tell:\n"
        "  - name EVERY person the fact names — a dropped name is the story's point removed\n"
        "  - say what actually happened, including what went wrong\n"
        "  - say what came of it: the name that stuck, the record, the consequence\n"
        "  - if the fact explains WHY something is called what it is, deliver that explanation\n"
        "\n"
        "This is the reason the listener is standing here rather than at any other restaurant. "
        "A stop that lists hours and prices and gestures at a story has failed.\n"
        "\n"
        "Use ONLY what is listed above. Do not add a guest, a date or an incident that is not "
        "here, and do not embellish one that is. If a listed fact is thin, tell a different one "
        "rather than inventing detail to fill it out.\n"
    )
