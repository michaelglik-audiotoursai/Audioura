#!/usr/bin/env python3
"""test_d515_replay.py — Michael's rule replayed over every story we already have.

He asked to *"test this rule on a number of stories and see if such rule makes
sense."* Forty-one are already on disk with their index, kind, counts and full
adjudication — 37 from the D510 lab run and 4 from today's production replay — so
the rule can be scored before another dollar is spent.

This does NOT re-run retrieval. It re-applies the acceptance decision to stories
whose verdicts were computed under the old gate, which is exactly the comparison
wanted: same material, two rules.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ.setdefault('STORY_GATE_D515', '1')

from story_adjudicate import surviving_errors        # noqa: E402
from story_publish_gate import evaluate, best_of, D515_ACCEPT_INDEX  # noqa: E402


def load_lab(path='ADJUDICATED_STORIES.md'):
    """The 37 lab stories, grouped by work."""
    s = open(os.path.join(HERE, path), encoding='utf-8').read()
    works, cur = {}, None
    for block in re.split(r'\n(?=# |## credit_line )', s):
        if block.startswith('# ') and not block.startswith('## '):
            cur = block.split('\n')[0][2:].strip()
            if cur.lower().startswith(('37 adjudicated', 'moses', 'le l', 'au soleil')):
                works.setdefault(cur, [])
            continue
        if not block.startswith('## credit_line ') or cur is None:
            continue
        head = block.split('\n')[0]
        cl = head.replace('## credit_line ', '').split(' —')[0].strip()
        meta = re.search(r'kind \*\*(\w+)\*\* · index \*\*(\d+)\*\*.*?'
                         r'`C(\d+)` `Corr(\d+)` `D(\d+)` `X(\d+)`', block)
        story = re.search(r'### THE STORY\n\n(.+?)\n\n<details>', block, re.S)
        adj = re.search(r'```\n(.*?)\n```', block, re.S)
        if not (meta and story):
            continue
        kind, idx, c, corr, d, x = meta.groups()
        works.setdefault(cur, []).append({
            'id': cl, 'kind': kind, 'index': int(idx),
            'counts': {'CONFIRMED': int(c), 'CORRECTED': int(corr),
                       'DISPUTED': int(d), 'UNATTESTED': int(x)},
            'story': story.group(1).strip(),
            'adjudication': adj.group(1) if adj else '',
            'source': 'lab'})
    return {k: v for k, v in works.items() if v}


def load_today():
    """Today's production candidates, if the JSONL is present."""
    out = {}
    for fn in sorted(os.listdir(HERE)):
        if not (fn.startswith('MOSES_CANDIDATES_') and fn.endswith('.jsonl')):
            continue
        for line in open(os.path.join(HERE, fn), encoding='utf-8'):
            d = json.loads(line)
            out.setdefault(d['work'] + ' (production, today)', []).append({
                'id': d['credit_line'][:34], 'kind': d['kind'],
                'index': d['index'] or 0, 'counts': d['counts'],
                'story': d['story'], 'adjudication': '',
                'ungrounded': d.get('ungrounded') or [], 'source': 'prod'})
    return out


def decide(cands):
    """Walk the candidates in order under BOTH rules. Returns the two outcomes."""
    old = new = None
    for c in cands:
        c['factual_errors'] = surviving_errors(c['story'], c['adjudication'])
        c['gate'] = evaluate({'story_kind': c['kind'], 'index': c['index'],
                              'counts': c['counts'],
                              'tells_disagreement': bool(re.search(
                                  r'some sources|others say|disagree|dispute',
                                  c['story'], re.I)),
                              'factual_errors': c['factual_errors'],
                              'ungrounded': c.get('ungrounded') or []})
        if old is None and c['gate'].get('legacy_passes'):
            old = c
        if new is None and c['gate']['passes']:
            new = c
    fallback = None
    if new is None:
        fallback = best_of(cands)
    return old, new, fallback


def main():
    works = {}
    works.update(load_lab())
    works.update(load_today())

    n_pub_old = n_pub_new = n_fallback = 0
    rows = []
    for work, cands in works.items():
        old, new, fb = decide(cands)
        chosen = new or fb
        n_pub_old += bool(old)
        n_pub_new += bool(chosen)
        n_fallback += bool(fb)
        print('=' * 78)
        print(f"{work}   ({len(cands)} candidates)")
        print('=' * 78)
        print(f"{'cand':<36}{'kind':<10}{'idx':>4}  {'old gate':<28}{'D515'}")
        for c in cands:
            g = c['gate']
            veto = ('WRONG:' + g['factual_errors'][0]['wrong'][:22]) if g['factual_errors'] \
                else ('INVENTED:' + ','.join(g['ungrounded']) if g['ungrounded'] else '')
            print(f"  {c['id'][:34]:<34}{c['kind']:<10}{c['index']:>4}  "
                  f"{('PASS' if g['legacy_passes'] else 'fail:' + ','.join(g['legacy_failed']))[:26]:<28}"
                  f"{'ACCEPT' if g['passes'] else 'reject:' + ','.join(g['failed'])}"
                  f"{'  ' + veto if veto else ''}")
        print()
        print(f"  OLD  -> {'publishes ' + old['id'] if old else 'PUBLISHES NOTHING'}")
        if new:
            print(f"  D515 -> accepts {new['id']} at index {new['index']} "
                  f"(examined {cands.index(new) + 1} of {len(cands)})")
        elif fb:
            print(f"  D515 -> FALLBACK to {fb['id']} at index {fb['index']} "
                  f"({fb['kind']}, examined all {len(cands)})")
        else:
            print(f"  D515 -> publishes nothing "
                  f"(no candidate above {D515_ACCEPT_INDEX} without a veto)")
        rows.append({'work': work, 'old': old['id'] if old else None,
                     'new': (new or fb)['id'] if (new or fb) else None,
                     'by': 'accept' if new else ('fallback' if fb else 'none'),
                     'index': (new or fb)['index'] if (new or fb) else None,
                     'kind': (new or fb)['kind'] if (new or fb) else None,
                     'examined_old': len(cands),
                     'examined_new': (cands.index(new) + 1) if new else len(cands)})
        print()

    print('=' * 78)
    print(f"{len(works)} works · old gate published {n_pub_old} · "
          f"D515 publishes {n_pub_new} ({n_fallback} by fallback)")
    saved = sum(r['examined_old'] - r['examined_new'] for r in rows)
    print(f"candidates NOT bought under D515 (early stop): {saved}")
    print('=' * 78)
    json.dump(rows, open(os.path.join(HERE, 'D515_REPLAY.json'), 'w'),
              indent=2, ensure_ascii=False)


if __name__ == '__main__':
    main()
