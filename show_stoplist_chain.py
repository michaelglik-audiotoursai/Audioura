#!/usr/bin/env python3
"""show_stoplist_chain.py — the stop list chain, end to end, ONE OpenAI call.

Michael, 2026-08-25: show the full chain once, then decide what to investigate.

    user-requested string  ->  prompt sent to OpenAI  ->  raw return from OpenAI

Fidelity rule: the prompt is NOT reconstructed here. `requests.post` is wrapped
inside `exhibition_checklist` so what is printed is the exact payload production
puts on the wire, and the exact bytes that come back. Everything upstream of the
call — page fetch, nav filter, truncation — runs as production runs it.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
for line in open(os.path.join(HERE, '.env')):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import exhibition_checklist as ec

# ── LINK 1: the user-requested string ────────────────────────────────────────
# This is what run_loop_tour.py passes to generate_tour_text() as `location`.
USER_STRING = 'Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA'

# The exhibition page production resolves this to, verbatim from every tour log:
#   [LOCAL-364] Matched exhibition: 'Picasso, Miró, Dalí: Unbound' (score: 1.00)
EXHIBITION_URL = 'http://www.mfa.org/exhibition/picasso-miro-dali-unbound'
EXHIBITION_NAME = 'Picasso, Miró, Dalí: Unbound'

captured = {}
_real_post = ec.requests.post


def _capture_post(url, **kwargs):
    resp = _real_post(url, **kwargs)
    if 'openai.com' in url and 'payload' not in captured:
        captured['url'] = url
        captured['payload'] = kwargs.get('json')
        captured['status'] = resp.status_code
        try:
            captured['body'] = resp.json()
        except Exception:
            captured['body'] = {'_raw_text': resp.text}
    return resp


ec.requests.post = _capture_post

page_text, _links = ec._fetch_page(EXHIBITION_URL)
works = ec.prose_llm_extract_works(page_text, EXHIBITION_NAME)

if 'payload' not in captured:
    print('NO OpenAI CALL WAS MADE — nothing to show.')
    raise SystemExit(1)

payload = captured['payload']
msgs = {m['role']: m['content'] for m in payload['messages']}
body = captured['body']
content = ''
if isinstance(body, dict) and body.get('choices'):
    content = body['choices'][0]['message']['content']

out = []
w = out.append
w('# The stop list chain — one call, captured on the wire')
w('')
w(f"Generated {__import__('time').strftime('%Y-%m-%d %H:%M')} · "
  f"model `{payload.get('model')}` · temperature `{payload.get('temperature')}` · "
  f"HTTP {captured['status']}")
w('')
w('This is the call whose result becomes the tour\'s stop list. Nothing here is')
w('reconstructed — `requests.post` was wrapped inside `exhibition_checklist`.')
w('')
w('---')
w('')
w('## LINK 1 — the user-requested string')
w('')
w('```')
w(USER_STRING)
w('```')
w('')
w(f'Resolved by production to `{EXHIBITION_URL}`')
w(f'(page fetched: {len(page_text)} chars raw)')
w('')
w('---')
w('')
w('## LINK 2 — the prompt sent to OpenAI')
w('')
w(f"Request parameters actually on the wire: `model={payload.get('model')}`, "
  f"`temperature={payload.get('temperature')}`, `max_tokens={payload.get('max_tokens')}`, "
  f"`seed={payload.get('seed', '**ABSENT**')}`")
w('')
w(f"### system message ({len(msgs.get('system',''))} chars)")
w('')
w('```')
w(msgs.get('system', '(none)'))
w('```')
w('')
w(f"### user message ({len(msgs.get('user',''))} chars)")
w('')
w('```')
w(msgs.get('user', '(none)'))
w('```')
w('')
w('---')
w('')
w('## LINK 3 — the raw return from OpenAI')
w('')
if isinstance(body, dict) and body.get('usage'):
    u = body['usage']
    w(f"tokens: prompt={u.get('prompt_tokens')}, completion={u.get('completion_tokens')} · "
      f"finish_reason=`{body['choices'][0].get('finish_reason')}` · "
      f"system_fingerprint=`{body.get('system_fingerprint', 'ABSENT')}`")
    w('')
w('### message content, verbatim')
w('')
w('```')
w(content or '(empty)')
w('```')
w('')
w('---')
w('')
w('## What the pipeline then made of it')
w('')
w(f'`prose_llm_extract_works` returned **{len(works)} work(s)** after its own validation:')
w('')
for i, x in enumerate(works, 1):
    w(f"{i}. `{x.get('title')}` — artist={x.get('artist')!r} date={x.get('date')!r}")
w('')
w('Each surviving entry becomes one stop in the tour.')
w('')

doc = '\n'.join(out)
path = os.path.join(HERE, 'STOPLIST_CHAIN.md')
open(path, 'w').write(doc)
print(doc)
print(f'\n\n[written to {os.path.basename(path)}]')
