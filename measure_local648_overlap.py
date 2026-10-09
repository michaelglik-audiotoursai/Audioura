#!/usr/bin/env python3
"""measure_local648_overlap.py — LOCAL-648 offline A/B: Gemini grounded search
vs Serper + page fetch + cheap model, per story-lead question.

For each of six stored museums we RECONSTRUCT the exact story-lead question the
pipeline asks (by replaying the real question builder, story_query.compile_for_seed,
on a signature well-documented work of each venue — the same prompt the D511
per-stop grounded narrate sends), then answer it BOTH ways and compare:

  * number of distinct verifiable facts (names, dates, events) in each answer
  * sources each returned
  * facts present in one answer but missing from the other
  * $ per question (read from the network meter, paid_api_calls)
  * seconds per question (wall clock)

Factual overlap is judged by a cheap model (gpt-4.1-mini) with a spot-check dump
of every answer so the judgement can be verified by hand. We report honestly
where Serper is WORSE.

This makes live paid calls (Gemini grounded, Serper, gpt-4.1-mini). It is capped:
set LOCAL648_MAX_USD (default $2.00 for this offline arm, leaving headroom under
the ticket's $2.50 total). Every call is metered through paid_api_calls; spend is
read back from there per arm (by caller file), never estimated.

Run inside the generator image/container (keys + /opt/meter + DB present):
    python3 measure_local648_overlap.py            # all 6 museums
    python3 measure_local648_overlap.py --limit 2  # Courtauld + Walters only
writes LOCAL648_overlap_measurement.json
"""
import argparse
import json
import os
import re
import sys
import time
from typing import Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import story_leads  # noqa: E402
import serper_research  # noqa: E402
from story_query import compile_for_seed, compile_for_serper  # noqa: E402


# ── the six museums, one signature well-documented work each ──────────────────
# Each is a real holding of the named venue with checkable facts (maker, date,
# acquisition). The question the pipeline asks is reconstructed from these by the
# real builder below — we do not hand-write the question.
MUSEUMS: List[Dict] = [
    {'venue': 'The Courtauld Gallery, London',
     'matrix': {'canonical_title': 'A Bar at the Folies-Bergère',
                'artist': 'Édouard Manet', 'venue_name': 'The Courtauld Gallery',
                'credit_line': 'Samuel Courtauld Trust', 'publication_year': '1882'}},
    {'venue': 'The Walters Art Museum, Baltimore',
     'matrix': {'canonical_title': 'The Ideal City', 'artist': 'Fra Carnevale',
                'venue_name': 'The Walters Art Museum',
                'credit_line': 'acquired by Henry Walters', 'publication_year': '1480'}},
    {'venue': 'The Wallace Collection, London',
     'matrix': {'canonical_title': 'The Swing', 'artist': 'Jean-Honoré Fragonard',
                'venue_name': 'The Wallace Collection',
                'credit_line': 'Sir Richard Wallace', 'publication_year': '1767'}},
    {'venue': 'The Frick Collection, New York',
     'matrix': {'canonical_title': 'St. Francis in the Desert',
                'artist': 'Giovanni Bellini', 'venue_name': 'The Frick Collection',
                'credit_line': 'Henry Clay Frick, 1915', 'publication_year': '1480'}},
    {'venue': 'Uffizi Gallery, Florence',
     'matrix': {'canonical_title': 'The Birth of Venus', 'artist': 'Sandro Botticelli',
                'venue_name': 'Uffizi Gallery',
                'credit_line': 'Medici collection', 'publication_year': '1485'}},
    {'venue': 'National Gallery, London',
     'matrix': {'canonical_title': 'The Arnolfini Portrait', 'artist': 'Jan van Eyck',
                'venue_name': 'National Gallery',
                'credit_line': 'purchased 1842', 'publication_year': '1434'}},
]


def reconstruct_question(m: Dict) -> Dict:
    """Replay the REAL question builder for a prose seed on this work. Returns the
    exact per-stop grounded prompt (what research_with_sources/gemini_with_sources
    receives) and the Serper keyword encoding of the same question."""
    mat = m['matrix']
    seed = {'kind': 'prose', 'seed': mat.get('credit_line', ''), 'ask': ''}
    prompt = compile_for_seed(seed, mat, exhibition=m['venue'])
    serp_q = compile_for_serper(mat, credit_line_seed=mat.get('credit_line', ''))
    return {'venue': m['venue'], 'work': mat['canonical_title'],
            'prompt': prompt, 'serper_keyword_form': serp_q}


# ── fact extraction + overlap judging (cheap model) ───────────────────────────
_FACT_EXTRACT = """\
Extract the distinct, checkable FACTS from the text below — each a single claim \
containing a name, a date, or a concrete event. One fact per line, no numbering, \
no commentary. Drop opinions, descriptions of appearance, and anything with no \
name/date/event. If there are no such facts, output nothing.

TEXT:
{text}
"""

_OVERLAP_JUDGE = """\
Here are two lists of facts answering the SAME question about a museum artwork.

LIST A (Gemini grounded search):
{a}

LIST B (Serper + page fetch + cheap model):
{b}

Count, as JSON only:
{{"shared": <facts asserted in BOTH lists, same claim>,
  "only_a": <facts in A but not B>,
  "only_b": <facts in B but not A>,
  "a_total": <distinct facts in A>,
  "b_total": <distinct facts in B>}}
Judge by MEANING, not wording. Output the JSON object and nothing else.
"""


def _cheap(prompt: str, model: str = 'gpt-4.1-mini', max_tokens: int = 700) -> str:
    import requests
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        return ''
    try:
        r = requests.post('https://api.openai.com/v1/chat/completions',
                          headers={'Authorization': f'Bearer {key}',
                                   'Content-Type': 'application/json'},
                          json={'model': model, 'temperature': 0.0,
                                'max_tokens': max_tokens,
                                'messages': [{'role': 'user', 'content': prompt}]},
                          timeout=60)
        r.raise_for_status()
        return r.json()['choices'][0]['message']['content'] or ''
    except Exception as e:
        return f''


def extract_facts(text: str) -> List[str]:
    if not (text or '').strip():
        return []
    out = _cheap(_FACT_EXTRACT.format(text=text[:4000]))
    facts = [ln.strip().lstrip('-•* ').strip()
             for ln in out.splitlines() if ln.strip()]
    return [f for f in facts if len(f) > 8]


def judge_overlap(a_facts: List[str], b_facts: List[str]) -> Dict:
    if not a_facts and not b_facts:
        return {'shared': 0, 'only_a': 0, 'only_b': 0, 'a_total': 0, 'b_total': 0}
    out = _cheap(_OVERLAP_JUDGE.format(a='\n'.join(a_facts) or '(none)',
                                       b='\n'.join(b_facts) or '(none)'))
    m = re.search(r'\{.*\}', out, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except ValueError:
            pass
    return {'shared': None, 'only_a': None, 'only_b': None,
            'a_total': len(a_facts), 'b_total': len(b_facts),
            'judge_raw': out[:200]}


# ── per-arm spend from the network meter ──────────────────────────────────────
def _meter_log_path() -> str:
    return os.environ.get('PAID_API_LOG', '/meterlogs/paid_api_calls.jsonl')


def _read_meter_since(byte_offset: int):
    """Return (records, new_offset) appended to the meter log since byte_offset."""
    path = _meter_log_path()
    recs = []
    try:
        with open(path, 'r') as fh:
            fh.seek(byte_offset)
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    recs.append(json.loads(line))
                except ValueError:
                    continue
            new_off = fh.tell()
        return recs, new_off
    except FileNotFoundError:
        return [], byte_offset


def _spend_of(recs, kinds=None, caller_sub=None) -> float:
    tot = 0.0
    for r in recs:
        if kinds and r.get('kind') not in kinds:
            continue
        if caller_sub and caller_sub not in (r.get('caller') or ''):
            continue
        tot += float(r.get('usd') or 0.0)
    return tot


def _log_offset() -> int:
    path = _meter_log_path()
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=len(MUSEUMS),
                    help='how many museums (default all 6)')
    ap.add_argument('--max-usd', type=float,
                    default=float(os.environ.get('LOCAL648_MAX_USD', '2.00')))
    args = ap.parse_args()

    print('=' * 78)
    print('LOCAL-648 — OFFLINE A/B: Gemini grounded vs Serper research')
    print('=' * 78)
    print(f'cap: ${args.max_usd:.2f} (meter: {_meter_log_path()})\n')

    results = []
    start_off = _log_offset()

    for m in MUSEUMS[:args.limit]:
        q = reconstruct_question(m)
        print('─' * 78)
        print(f"VENUE: {q['venue']}")
        print(f"WORK : {q['work']}")

        # Running-spend cap gate (read everything since this run started).
        recs_so_far, _ = _read_meter_since(start_off)
        spent = _spend_of(recs_so_far)
        if spent >= args.max_usd:
            print(f"[cap] ${spent:.4f} >= ${args.max_usd:.2f} — stopping before "
                  f"{q['venue']}")
            break

        # ── Gemini grounded ──
        g_off = _log_offset()
        t0 = time.time()
        g = story_leads.gemini_with_sources(q['prompt'], grounded=True)
        g_secs = time.time() - t0
        g_recs, _ = _read_meter_since(g_off)
        g_usd = _spend_of(g_recs, kinds={'gemini'})

        # ── Serper research ──
        s_off = _log_offset()
        t0 = time.time()
        s = serper_research.serper_research(q['prompt'])
        s_secs = time.time() - t0
        s_recs, _ = _read_meter_since(s_off)
        s_usd = _spend_of(s_recs, kinds={'serper', 'openai'})

        g_text = g.get('text', '') or ''
        s_text = s.get('text', '') or ''
        g_facts = extract_facts(g_text)
        s_facts = extract_facts(s_text)
        overlap = judge_overlap(g_facts, s_facts)

        row = {
            'venue': q['venue'], 'work': q['work'], 'prompt': q['prompt'],
            'serper_keyword_form': q['serper_keyword_form'],
            'gemini': {
                'text': g_text, 'error': g.get('error', ''),
                'sources': g.get('sources', []), 'queries': g.get('queries', []),
                'n_facts': len(g_facts), 'facts': g_facts,
                'seconds': round(g_secs, 1), 'usd': round(g_usd, 5),
            },
            'serper': {
                'text': s_text, 'error': s.get('error', ''),
                'sources': s.get('sources', []), 'queries': s.get('queries', []),
                'n_facts': len(s_facts), 'facts': s_facts,
                'seconds': round(s_secs, 1), 'usd': round(s_usd, 5),
            },
            'overlap_judgement': overlap,
        }
        results.append(row)

        print(f"  GEMINI: {len(g_facts)} facts, {len(g.get('sources', []))} "
              f"sources, {g_secs:.1f}s, ${g_usd:.5f}"
              f"{'  ERROR:' + g['error'] if g.get('error') else ''}")
        print(f"  SERPER: {len(s_facts)} facts, {len(s.get('sources', []))} "
              f"sources, {s_secs:.1f}s, ${s_usd:.5f}"
              f"{'  ERROR:' + s['error'] if s.get('error') else ''}")
        print(f"  OVERLAP (cheap-model judge): {overlap}")

    # ── totals ──
    all_recs, _ = _read_meter_since(start_off)
    total_gemini = _spend_of(all_recs, kinds={'gemini'})
    total_serper_arm = _spend_of(all_recs, kinds={'serper', 'openai'})
    total = _spend_of(all_recs)

    n = len(results)
    g_facts_tot = sum(r['gemini']['n_facts'] for r in results)
    s_facts_tot = sum(r['serper']['n_facts'] for r in results)
    g_secs_avg = round(sum(r['gemini']['seconds'] for r in results) / n, 1) if n else 0
    s_secs_avg = round(sum(r['serper']['seconds'] for r in results) / n, 1) if n else 0

    summary = {
        'rate_tag': getattr(_meter(), 'RATE_TAG', '?'),
        'n_questions': n,
        'gemini': {'total_usd': round(total_gemini, 5),
                   'usd_per_q': round(total_gemini / n, 5) if n else 0,
                   'facts_total': g_facts_tot,
                   'facts_per_q': round(g_facts_tot / n, 1) if n else 0,
                   'secs_per_q': g_secs_avg},
        'serper': {'total_usd': round(total_serper_arm, 5),
                   'usd_per_q': round(total_serper_arm / n, 5) if n else 0,
                   'facts_total': s_facts_tot,
                   'facts_per_q': round(s_facts_tot / n, 1) if n else 0,
                   'secs_per_q': s_secs_avg},
        'total_run_usd': round(total, 5),
    }

    print('\n' + '=' * 78)
    print('SUMMARY')
    print('=' * 78)
    print(json.dumps(summary, indent=2))

    out = os.environ.get('LOCAL648_OUT_JSON') or os.path.join(
        HERE, 'LOCAL648_overlap_measurement.json')
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump({'summary': summary, 'results': results}, fh,
                  indent=2, ensure_ascii=False)
    print(f"\nwrote {out}")


def _meter():
    try:
        sys.path.insert(0, os.path.join(HERE, '_meter'))
        import paid_api_meter as _m
        return _m
    except Exception:
        class _X:
            RATE_TAG = '2026-10-08-r4 (fallback)'
        return _X()


if __name__ == '__main__':
    main()
