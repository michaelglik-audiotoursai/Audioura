#!/usr/bin/env python3
"""story_leads.py — ask a model what happened, then go and check it.

D438/D439. The order we had was: retrieve, then write. That loses, because a
keyword query has to get lucky. We retrieved "Miró decided to destroy the
lithographs" once and a near-identical query minutes later did not return it —
with the answer already in hand.

This inverts it:

    1. LEAD      ask a model for specific, dated, checkable events
    2. VERIFY    search each claim on its own — narrow, repeatable
    3. KEEP      only what a source confirms; everything else is dropped

A model's answer is a HYPOTHESIS. It is evidence for nothing. That is the same
CLAIMED-vs-GROUNDED line D435 drew for matrix slots, applied to prose.

CROSS-MODEL DISAGREEMENT IS A FABRICATION DETECTOR
--------------------------------------------------
Michael put one question to Meta.AI and Google. Meta said the 1971 edition
followed a DESTROYED 1967 printing; Google said it was four years of patient
technical work. They cannot both be right, and the disagreement is what sent LEAD
to the sources — which backed Meta. One model answering fluently proves nothing;
two models independently proposing the same dated event is real signal.

So providers are pluggable and the runner will use every one it has a key for.

    python3 story_leads.py --subject "Joan Miró" \\
        --work "Le Lézard aux plumes d'or" --venue "Museum of Fine Arts, Boston"
"""
import argparse
import json
import os
import re
import sys
from typing import Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
for _l in open(os.path.join(HERE, '.env')):
    _l = _l.strip()
    if _l and not _l.startswith('#') and '=' in _l:
        _k, _v = _l.split('=', 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from story_opportunity_scan import _fold, _STAKES, _AGENCY_VERB   # noqa: E402


LEAD_PROMPT = """\
You are helping a museum audio tour find TRUE, CHECKABLE events.

Subject: {subject}
Work / place: {work}
Venue: {venue}

List up to 6 specific events involving the subject and this work. Each must be a
single concrete happening a researcher could confirm or refute — a decision, a
refusal, a destruction, a death, a meeting, a sale, a delay.

Rules:
- One event per line, no numbering, no commentary.
- Include a year whenever you know it.
- NO interpretation, NO significance, NO "this reflects" or "this symbolises",
  NO psychological states, NO predictions.
- If you are unsure whether something happened, include it anyway — it will be
  checked. Do NOT hedge with "may have" or "possibly"; state it plainly so it can
  be tested and thrown out.

Format each line as:
YEAR | what happened, in one clause
"""


# ── providers ────────────────────────────────────────────────────────────────

def _openai(prompt: str, model: str = 'gpt-4o') -> str:
    import requests
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        return ''
    r = requests.post('https://api.openai.com/v1/chat/completions',
                      headers={'Authorization': f'Bearer {key}',
                               'Content-Type': 'application/json'},
                      json={'model': model, 'temperature': 0.2, 'max_tokens': 600,
                            'messages': [{'role': 'user', 'content': prompt}]},
                      timeout=60)
    r.raise_for_status()
    return r.json()['choices'][0]['message']['content']


def _gemini(prompt: str, model: str = None, grounded: bool = False) -> str:
    """Google Gemini. ~17x cheaper on input than gpt-4o, ~8x on output.

    NOTE: Gemini 2.5 retires 2026-10-16, so the default is `gemini-flash-latest`
    rather than a pinned 2.5. Michael's key (verified 2026-08-14) exposes 38
    models incl. gemini-3-flash-preview.

    `grounded=True` turns on Grounding with Google Search — the toggle that was
    already ON in Michael's AI Studio console, and the likeliest reason his Google
    answer beat ours. The model searches and cites inside the call instead of
    reciting. It does NOT replace `validate_story`: Google's "tragic mood holding
    sway over Miró's psyche" came out of a grounded console session, so grounded
    output is still a hypothesis until our own verifier checks it.
    """
    model = model or os.environ.get('GEMINI_MODEL', 'gemini-flash-latest')
    import requests
    key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
    if not key:
        return ''
    r = requests.post(
        f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
        headers={'Content-Type': 'application/json', 'x-goog-api-key': key},
        json={'contents': [{'parts': [{'text': prompt}]}],
              'generationConfig': {'temperature': 0.2, 'maxOutputTokens': 600},
              **({'tools': [{'google_search': {}}]} if grounded else {})},
        timeout=60)
    r.raise_for_status()
    d = r.json()
    try:
        return d['candidates'][0]['content']['parts'][0]['text']
    except (KeyError, IndexError):
        return ''


def _gemini_grounded(prompt: str) -> str:
    return _gemini(prompt, grounded=True)


PROVIDERS = {'openai': _openai, 'gemini': _gemini,
             'gemini_grounded': _gemini_grounded}


def available_providers() -> List[str]:
    out = []
    if os.environ.get('OPENAI_API_KEY'):
        out.append('openai')
    if os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY'):
        out.append('gemini')
        out.append('gemini_grounded')
    return out


# ── leads ────────────────────────────────────────────────────────────────────

_YEAR = re.compile(r'\b(1[5-9]\d{2}|20[0-2]\d)\b')


def parse_leads(text: str, provider: str) -> List[Dict]:
    leads = []
    for line in (text or '').splitlines():
        line = line.strip().lstrip('-•* ').strip()
        if not line or len(line) < 12:
            continue
        year, claim = '', line
        if '|' in line:
            a, b = line.split('|', 1)
            if _YEAR.search(a):
                year, claim = _YEAR.search(a).group(1), b.strip()
        if not year:
            m = _YEAR.search(line)
            year = m.group(1) if m else ''
        leads.append({'year': year, 'claim': claim.strip(), 'provider': provider})
    return leads


def merge_leads(all_leads: List[Dict]) -> List[Dict]:
    """Group near-identical claims across providers. Agreement is the signal."""
    merged: List[Dict] = []
    for l in all_leads:
        key = set(w for w in _fold(l['claim']).split() if len(w) > 4)
        hit = None
        for m in merged:
            mk = set(w for w in _fold(m['claim']).split() if len(w) > 4)
            if key and mk and len(key & mk) / max(1, min(len(key), len(mk))) >= 0.5 \
                    and (not l['year'] or not m['year'] or l['year'] == m['year']):
                hit = m
                break
        if hit:
            hit['providers'] = sorted(set(hit['providers']) | {l['provider']})
            hit['year'] = hit['year'] or l['year']
        else:
            merged.append({'year': l['year'], 'claim': l['claim'],
                           'providers': [l['provider']]})
    merged.sort(key=lambda m: (-len(m['providers']), not m['year']))
    return merged


# ── verification ─────────────────────────────────────────────────────────────

_ENTITY = re.compile(r"\b[A-ZÀ-Þ][\wà-ÿ'’\-]+(?:\s+[A-ZÀ-Þ][\wà-ÿ'’\-]+)*")


def _principal(claim: str, work: str, subject: str) -> str:
    """The named party a claim is ABOUT, when that is not the subject or the work.

    D440: `verify()` appended the work title to every query, so the TRUE claim
    "Mourlot was founded in 1852 on rue de Chabrol" was searched as
    `Joan Miró "Le Lézard aux plumes d'or" 1852 Mourlot founded…` — a query about a
    book the printing house predates by a century. It came back UNVERIFIED. A claim
    about a COLLABORATOR needs a query built around the collaborator.
    """
    known = _fold(work + ' ' + subject)
    for e in _ENTITY.findall(claim or ''):
        f = _fold(e)
        if len(f) < 4 or f in known:
            continue
        # A name already inside the subject/work is not a separate party.
        if all(tok in known.split() for tok in f.split()):
            continue
        return e
    return ''


def verify(lead: Dict, work: str, subject: str) -> Dict:
    """One narrow search per claim, two at most. This is the repeatable part."""
    from work_story_searcher import _serp_search
    terms = [w for w in re.findall(r"[A-Za-zà-ÿ'’\-]{4,}", lead['claim'])][:8]

    # Query shapes, most likely first. The work-anchored shape is right for claims
    # about the object; it is actively wrong for claims about a collaborator, so
    # when the claim names a third party we ask about THEM first. The second shape
    # is only paid for when the first finds no carrier sentence.
    q_work = f'{subject} "{work}" {lead["year"]} {" ".join(terms)}'.strip()
    principal = _principal(lead['claim'], work, subject)
    queries = [q_work]
    if principal:
        rest = [t for t in terms if _fold(t) not in _fold(principal)]
        queries.insert(0, f'"{principal}" {lead["year"]} {" ".join(rest)}'.strip())
    # The evidence must be ONE sentence carrying the claim — not content words
    # scattered across eight unrelated results. Measured 2026-08-14: the claim
    # "included in a retrospective exhibition at the MFA in 1993" was CONFIRMED
    # against an AUCTION LISTING, because 'Lézard' appeared on one page and '1993'
    # on another. Nothing anywhere mentioned a retrospective. A verifier that
    # accepts a claim no single source makes is the failure it exists to prevent.
    # THE NAMED PARTY MUST BE IN THE CARRIER SENTENCE. Measured 2026-08-14, and it
    # is the same failure as the 1993 one in a new place: Gemini claimed "Leonard
    # Woolf accompanied Dalí to meet Freud in London, 1938", and this function
    # CONFIRMED it against
    #     "Salvador Dalí met Freud in London in 1938, Freud appeared more
    #      receptive to ... Moses and Monotheism."
    # which does not mention Leonard Woolf at all. The year matched, the content
    # words matched, an agency verb was present — and the actual assertion, the
    # only part anyone would repeat to a visitor, went unchecked. Counting words
    # is not reading a sentence.
    def _carries(sn):
        f = _fold(sn or '')
        if not f:
            return False
        if lead['year'] and lead['year'] not in (sn or ''):
            return False
        if principal:
            # Surname is enough — sources write "Woolf" as often as "Leonard Woolf".
            parts = [p for p in _fold(principal).split() if len(p) > 3]
            if parts and not any(p in f for p in parts):
                return False
        need = [t for t in terms if len(t) > 4]
        hit = sum(1 for t in need if _fold(t) in f)
        return hit >= max(2, (len(need) + 1) // 2) and (
            _AGENCY_VERB.search(sn) or _STAKES.search(sn))

    asked, res, carrier, q = [], [], '', queries[0]
    for cand in queries:
        q, res = cand, _serp_search(cand)[0]
        asked.append(cand)
        carrier = next((s.get('snippet') for s in res
                        if _carries(s.get('snippet'))), '')
        if carrier:
            break

    blob = ' '.join((s.get('title', '') + ' ' + (s.get('snippet') or '')) for s in res)
    fb = _fold(blob)
    content = [t for t in terms if len(t) > 4 and _fold(t) in fb]
    year_ok = (not lead['year']) or (lead['year'] in blob)
    # Recorded for diagnosis only: a page that merely repeats the title is not
    # confirmation, so `substantive` never decides the status on its own.
    substantive = any(_AGENCY_VERB.search(s.get('snippet') or '')
                      or _STAKES.search(s.get('snippet') or '') for s in res)

    return {**lead, 'query': q, 'queries_asked': asked, 'principal': principal,
            'results': len(res),
            'matched_terms': content[:6], 'year_confirmed': year_ok,
            'substantive': substantive,
            'status': 'CONFIRMED' if carrier else 'UNVERIFIED',
            'citations': [s.get('domain', '') for s in res
                          if _carries(s.get('snippet'))][:3],
            'evidence': carrier}


def run(subject: str, work: str, venue: str, providers: List[str] = None,
        verify_top: int = 6) -> Dict:
    providers = providers or available_providers()
    prompt = LEAD_PROMPT.format(subject=subject, work=work, venue=venue)
    raw, leads = {}, []
    for p in providers:
        try:
            txt = PROVIDERS[p](prompt)
        except Exception as e:
            raw[p] = f'ERROR {type(e).__name__}: {e}'
            continue
        raw[p] = txt
        leads += parse_leads(txt, p)
    merged = merge_leads(leads)
    checked = [verify(l, work, subject) for l in merged[:verify_top]]
    return {'providers': providers, 'raw': raw, 'leads': merged, 'checked': checked}


def report(r: Dict) -> None:
    print(f"\n{'=' * 78}\nSTORY LEADS — providers: {', '.join(r['providers']) or 'NONE'}\n{'=' * 78}")
    if len(r['providers']) < 2:
        print("\n  Only one provider available. Cross-model agreement — the strongest")
        print("  signal we have — needs a second. Add GEMINI_API_KEY to .env.")
    print(f"\n  {len(r['leads'])} distinct leads proposed\n")
    for c in r['checked']:
        mark = '  OK  ' if c['status'] == 'CONFIRMED' else ' ---- '
        agree = '+'.join(c.get('providers', []))
        print(f"  [{mark}] {c['year'] or '????'}  ({agree})  {c['claim'][:78]}")
        if c['status'] == 'CONFIRMED':
            print(f"           sources: {', '.join(c['citations'])}")
            if c['evidence']:
                print(f"           {c['evidence'][:150]}")
        else:
            print(f"           {c['results']} results · year={c['year_confirmed']} "
                  f"· substantive={c['substantive']} · matched {c['matched_terms']}")
    n = sum(1 for c in r['checked'] if c['status'] == 'CONFIRMED')
    print(f"\n{'=' * 78}\n  {n} of {len(r['checked'])} leads CONFIRMED — only these may reach a story.")
    print('=' * 78)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--subject', required=True)
    p.add_argument('--work', required=True)
    p.add_argument('--venue', default='')
    p.add_argument('--providers', nargs='*')
    p.add_argument('--verify-top', type=int, default=6)
    p.add_argument('--json', dest='as_json', action='store_true')
    p.add_argument('--out', default='')
    a = p.parse_args()
    r = run(a.subject, a.work, a.venue, a.providers, a.verify_top)
    if a.as_json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        report(r)
    if a.out:
        json.dump(r, open(a.out, 'w'), ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
