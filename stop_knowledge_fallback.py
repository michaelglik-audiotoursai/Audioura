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
citations), OpenAI otherwise. `GEMINI_API_KEY` is currently EMPTY in `.env`, so
the OpenAI path is what runs today.
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
    _noun = 'Place' if focus == 'place' else 'Object'
    _ctx = 'Area' if focus == 'place' else 'Museum'
    _ask = ('What actually happened at this place, and to whom?'
            if focus == 'place' else
            'What is actually known about this specific object?')
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
                    {"role": "system", "content": _SYSTEM_PLACE if focus == 'place' else _SYSTEM},
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


def _gemini_facts(work, venue, timeout=45):
    """Grounded variant — returns citations, so its facts carry sources."""
    try:
        from story_leads import gemini_with_sources
    except Exception as e:
        return None, f"gemini unavailable: {e}"
    try:
        res = gemini_with_sources(
            f"{_SYSTEM}\n\nObject: {work}\nMuseum: {venue}\n\n"
            f"What is actually known about this specific object? Return only the JSON.")
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
    if focus == 'place':
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
        parsed, provider = _gemini_facts(work, venue, timeout)
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
