#!/usr/bin/env python3
"""michaels_chain.py — Michael's four routines, in his order, with every output shown.

His words, 2026-08-14:

    "It should start with the matrix and end up with the text. The first one makes a
    query out of the matrix -- and I want to see that query. The next one calls AI
    with this query and gets back the resulting story. Then we validate the story. I
    want to see the result of that. Then if valid and has more sentences than 5, we
    ask to summarize in 3 sentences. And that should be the story."

This is NOT `story_pipeline.py`. That one interrogates the internet and makes the
writer work from retrieved passages. This one is Michael's chain as he specified it:
the query goes to the AI, and the AI's own answer is the story.

    python3 michaels_chain.py --tour TOUR_MFA_20260812_2030.txt --stop 2 \\
        --credit-line "The convergence of narrative and imagery in this exhibit"
"""
import argparse
import os
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
for _l in open(os.path.join(HERE, '.env')):
    _l = _l.strip()
    if _l and not _l.startswith('#') and '=' in _l:
        _k, _v = _l.split('=', 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from interrogation_matrix import build_matrix, extract_stops        # noqa: E402
from request_and_structure import request_to_ai, structure_ai_output  # noqa: E402
from validate_story import validate_story                          # noqa: E402
from story_opportunity_scan import split_sentences                 # noqa: E402

W = 78
MODEL = 'gpt-4o'


def head(n, name):
    print(f"\n{'=' * W}\nROUTINE {n} — {name}\n{'=' * W}")


def wrap(t, indent='  '):
    for para in (t or '').split('\n'):
        print(textwrap.fill(para, width=W, initial_indent=indent,
                            subsequent_indent=indent) if para.strip() else '')


def ask_openai(prompt: str) -> str:
    import requests
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        raise SystemExit('OPENAI_API_KEY not set')
    r = requests.post(
        'https://api.openai.com/v1/chat/completions',
        headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
        json={'model': MODEL, 'temperature': 0.4, 'max_tokens': 500,
              'messages': [{'role': 'user', 'content': prompt}]},
        timeout=60)
    r.raise_for_status()
    return r.json()['choices'][0]['message']['content'].strip()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--tour', required=True)
    p.add_argument('--stop', type=int, required=True)
    p.add_argument('--credit-line', default='')
    p.add_argument('--tour-type', default='museum')
    a = p.parse_args()

    full = open(a.tour, encoding='utf-8').read()
    stop = extract_stops(full)[a.stop]

    print('=' * W)
    print(f"MICHAEL'S CHAIN — stop {a.stop}: {stop['title']}")
    print('=' * W)

    # ── 0 ────────────────────────────────────────────────────────────────────
    head(0, 'interrogation_matrix — the starting point')
    m = build_matrix(stop['text'], tour_type=a.tour_type, tour_context=full)
    if a.credit_line:
        m['credit_line'] = {'value': a.credit_line, 'status': 'DERIVED',
                            'source': 'override', 'rung': ''}
        print(f"  credit_line OVERRIDDEN to: {a.credit_line!r}\n")
    for k, c in m.items():
        c = c or {}
        print(f"  {k:18} {(c.get('value') or '')[:50]:52} {c.get('status', '')}")

    # ── 1 ────────────────────────────────────────────────────────────────────
    head(1, 'Request_to_AI — MAKE A QUERY OUT OF THE MATRIX')
    req = request_to_ai(m)
    print("  THE QUERY:\n")
    wrap(req['request'], indent='    ')
    if req.get('unverified_terms'):
        print(f"\n  terms in it that nothing has verified: "
              f"{', '.join(req['unverified_terms'])}")

    # ── 2 ────────────────────────────────────────────────────────────────────
    head(2, 'CALL AI WITH THAT QUERY — the answer is the story')
    answer = ask_openai(req['request'])
    print(f"  {len(split_sentences(answer))} sentences, {len(answer)} chars\n")
    wrap(answer, indent='    ')

    # ── 3 ────────────────────────────────────────────────────────────────────
    head(3, 'Validate_Story — IS IT TRUE TO THE SOURCES')
    # Michael's chain has no retrieved corpus: the AI's own answer IS the story, so
    # the only text it can be checked against is the stop we started from. Stated
    # plainly rather than hidden — this is the weak joint in this chain.
    corpus = stop['text']
    print("  checked against: the stop text itself (this chain retrieves nothing,")
    print("  so there is no independent corpus to check against)\n")
    v = validate_story(answer, corpus)
    print(f"  VERDICT: {v['verdict']}\n")
    for s in v['sentences']:
        print(f"  [{s['status']}]")
        wrap(s['text'], indent='      ')

    # ── 4 ────────────────────────────────────────────────────────────────────
    head(4, 'Structure_AI_output — >5 SENTENCES? SUMMARIZE TO 3')
    n = len(split_sentences(answer))
    print(f"  sentence count: {n}")
    print(f"  rule: >5 -> summarize to 3 · <3 -> substitute credit_line and re-ask "
          f"· 3-5 -> accept\n")
    res = structure_ai_output(answer, m, ask_openai,
                             _stop_text=stop['text'], _tour_context=full)
    print(f"  status          {res['status']}")
    print(f"  sentences       {res['sentences']}")
    print(f"  credit_line     {res.get('credit_line_used')!r}")
    print(f"  substitutions   {res.get('chain')}")
    print(f"  AI calls made   {res.get('asks')}")

    print(f"\n{'=' * W}\nTHE STORY\n{'=' * W}\n")
    wrap(res['text'], indent='  ')
    print()


if __name__ == '__main__':
    main()
