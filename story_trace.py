#!/usr/bin/env python3
"""story_trace.py — every routine's input and output for ONE stop, in order.

Michael, 2026-08-14, looking at a four-sentence paragraph that was not a story:
"Please provide output of all 4 routines you wrote so I can better understand what
is happening. It should start with the matrix and end up with what you generated."

So this prints the chain, stage by stage, showing what each routine was HANDED and
what it PRODUCED. Everything is reproduced offline from the saved corpus — no
search is re-run, so the trace costs nothing and describes the exact run that
produced the story on disk.

    python3 story_trace.py --tour TOUR_MFA_20260812_2030.txt --stop 2 \\
        --run-json /path/to/phrase_subject.json
"""
import argparse
import json
import os
import re
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
for _l in open(os.path.join(HERE, '.env')):
    _l = _l.strip()
    if _l and not _l.startswith('#') and '=' in _l:
        _k, _v = _l.split('=', 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from interrogation_matrix import build_matrix, extract_stops   # noqa: E402
from request_and_structure import request_to_ai                # noqa: E402
from story_opportunity_scan import measure, verdict            # noqa: E402
from story_material_check import assess, load_corpus, passages_about  # noqa: E402
from validate_story import validate_story                      # noqa: E402
from evaluate_story import evaluate_story                      # noqa: E402
from work_story_searcher import synthesize_queries             # noqa: E402
import story_writer                                            # noqa: E402

W = 78


def head(n, name):
    print(f"\n{'═' * W}\nROUTINE {n} — {name}\n{'═' * W}")


def sub(t):
    print(f"\n─── {t} " + '─' * max(0, W - len(t) - 5))


def wrap(t, indent='  '):
    for para in (t or '').split('\n'):
        print(textwrap.fill(para, width=W, initial_indent=indent,
                            subsequent_indent=indent) if para.strip() else '')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--tour', required=True)
    p.add_argument('--stop', type=int, required=True)
    p.add_argument('--run-json', required=True,
                   help='The --out JSON from the story_pipeline run being traced.')
    a = p.parse_args()

    run = json.load(open(a.run_json))
    run = run[0] if isinstance(run, list) else run
    full = open(a.tour, encoding='utf-8').read()
    stop = extract_stops(full)[a.stop]

    print('=' * W)
    print(f"TRACE — stop {a.stop}: {stop['title']}")
    print(f"credit_line : {(run['matrix'].get('credit_line') or {}).get('value')!r}")
    print(f"subject     : {run.get('subject')!r}")
    print('=' * W)

    # ── 1 ────────────────────────────────────────────────────────────────────
    head(1, 'interrogation_matrix — WHAT TO ASK ABOUT')
    sub('INPUT: the stop text as delivered to the listener')
    wrap(stop['text'])
    sub('OUTPUT: the matrix')
    m = run['matrix']
    for k, c in m.items():
        c = c or {}
        v = (c.get('value') or '')
        print(f"  {k:18} {v[:52]:54} {c.get('status', '')}")

    # ── 2 ────────────────────────────────────────────────────────────────────
    head(2, 'Request_to_AI — THE QUESTION')
    sub('OUTPUT: the question put to the internet')
    wrap(run['request'])
    if run.get('unverified'):
        sub('terms in that question that NOTHING has verified')
        wrap(', '.join(run['unverified']))

    # ── 3 ────────────────────────────────────────────────────────────────────
    head(3, 'SEARCH + rank — INTERROGATE THE INTERNET')
    rec = {
        'canonical_title': (m.get('canonical_title') or {}).get('value', ''),
        'english_title': (m.get('english_title') or {}).get('value', ''),
        'artist': (m.get('artist') or {}).get('value', ''),
        'publisher': (m.get('publisher') or {}).get('value', ''),
        'printer': (m.get('printed_by') or {}).get('value', ''),
        'collaborator': (m.get('credit_line') or {}).get('value', ''),
        'credit_line': '', 'medium': (m.get('medium') or {}).get('value', ''),
        'exhibition_name': (m.get('medium') or {}).get('value', ''),
        'venue_name': (m.get('venue') or {}).get('value', ''),
        'venue_city': '', 'venue_lang': 'en',
    }
    sub('the queries actually issued (regenerated deterministically)')
    for q in synthesize_queries(rec, tour_type='contained'):
        print(f"  · {q}")
    print(f"\n  retrieved {run.get('retrieved')} results -> ranker kept {run.get('kept')}")
    print(f"  sources kept: {', '.join(run.get('domains', []))}")

    corpus_path = run.get('corpus_path') or ''
    sub('OUTPUT: the corpus — THE ONLY FACTS THE WRITER MAY USE')
    print(f"  ({corpus_path})\n")
    corpus_text = open(corpus_path, encoding='utf-8').read().strip() if \
        (corpus_path and os.path.exists(corpus_path)) else ''
    if not corpus_text:
        print("  *** MISSING — this run's corpus file is gone. ***")
    for line in corpus_text.split('\n'):
        wrap(line, indent='    ')

    # ── 3b ───────────────────────────────────────────────────────────────────
    head('3b', 'story_opportunity_scan + material check — WHO IS THERE TO WRITE ABOUT')
    body = re.split(r'\n\s*Directions:', stop['text'])[0]
    body = re.sub(r'^\s*(?:Stop \d+|Address|Coordinates)\s*:.*$', '', body, flags=re.M)
    meas = measure(body)
    need = verdict(meas)
    print(f"  needs additional story: {need['needs_additional_story']} — {need['why']}")
    sub('the ladder the subject is normally taken from')
    for h in run.get('ladder', []):
        print(f"  · {h}")
    corpus = load_corpus([corpus_path], {}) if corpus_text else ''
    sub('material check against the corpus')
    for h in run.get('ladder', [])[:8]:
        r = assess(h, corpus)
        print(f"  {h[:40]:42} {r['state']}")
    print(f"\n  SOURCEABLE: {run.get('sourceable')}")
    print(f"  subject the writer was given: {run.get('subject')!r}")

    # ── 4 ────────────────────────────────────────────────────────────────────
    head(4, 'story_writer — WRITE FROM THE CORPUS AND NOTHING ELSE')
    subject = run.get('subject') or ''
    focused = passages_about(subject, corpus)
    sub(f'passages_about({subject!r}) — what the writer was actually shown')
    if focused:
        for f in focused:
            wrap(f, indent='    ')
    else:
        print("  NONE MATCHED — so the writer fell back to the WHOLE corpus.")
        print("  The subject narrowed nothing.")
    sub('the exact prompt sent to the model')
    print("  [SYSTEM]")
    wrap(story_writer.SYSTEM, indent='    ')
    print("\n  [USER]")
    wrap(story_writer.build_prompt(rec, '\n'.join(focused) or corpus, subject),
         indent='    ')
    sub('OUTPUT: the story')
    wrap(run.get('story', ''), indent='    ')

    # ── 5 ────────────────────────────────────────────────────────────────────
    head(5, 'Validate_Story — IS EVERY SENTENCE IN THE SOURCES')
    if corpus:
        v = validate_story(run.get('story', ''), corpus)
        print(f"  verdict: {v['verdict']}\n")
        for s in v['sentences']:
            print(f"  [{s['status']}]")
            wrap(s['text'], indent='      ')

    # ── 6 ────────────────────────────────────────────────────────────────────
    head(6, 'Evaluate_Story — WHAT KIND OF STORY IS IT')
    if corpus:
        e = evaluate_story(run.get('story', ''), m, corpus)
        for k in ('historic', 'detail', 'social', 'valuation_index'):
            print(f"  {k:18} {e[k]}")
        ev = e.get('evidence') or {}
        sub('what those numbers were counted from')
        print('  ' + json.dumps(ev, ensure_ascii=False, default=str)[:1600])

    # ── 7 ────────────────────────────────────────────────────────────────────
    head(7, 'shape_check — DID IT MEET THE SHAPE THE SYSTEM PROMPT DEMANDS')
    if corpus:
        shaped, shape = story_writer.shape_check(run.get('story', ''), rec, corpus)
        print(f"  passed: {shaped}")
        print('  ' + json.dumps(shape, ensure_ascii=False, default=str)[:1600])


if __name__ == '__main__':
    main()
