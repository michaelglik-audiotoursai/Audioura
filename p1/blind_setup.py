#!/usr/bin/env python3
"""blind_setup.py — build the blind scoring set for the P1 A/B.

For each of the 16 requests it reads out/A_<id>.json and out/B_<id>.json,
randomly assigns the two arms to labels X and Y (independent coin flip per
pair), and writes:

    blind/<id>_X.txt   the text of whichever arm got X
    blind/<id>_Y.txt   the text of whichever arm got Y
    blind/KEY.json     {<id>: {"X": "A"|"B", "Y": "A"|"B"}}  (+ cost/time)

The text files carry NO arm label in their content — only the id and the
X/Y tag — so the scorer cannot tell gpt-4.1 from mini.  KEY.json is not read
until every score is written (SCORES.json).

No paid API calls.  Pure local file I/O.
"""
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
BLIND = os.path.join(HERE, 'blind')
REQUESTS = os.path.join(HERE, 'requests.json')

# Deterministic seed so the blinding is reproducible / auditable after the fact.
random.seed(20261028)


def load(arm, rid):
    with open(os.path.join(OUT, f'{arm}_{rid}.json'), encoding='utf-8') as fh:
        return json.load(fh)


def main():
    os.makedirs(BLIND, exist_ok=True)
    requests = json.load(open(REQUESTS, encoding='utf-8'))

    key = {}
    for req in requests:
        rid = req['id']
        a = load('A', rid)
        b = load('B', rid)

        # Safety: never blind a pair that is still processing.
        for arm_name, d in (('A', a), ('B', b)):
            if d.get('status') != 'completed':
                raise SystemExit(f'{arm_name}_{rid} status={d.get("status")} — not completed, abort')

        # Random X/Y assignment, independent per pair.
        if random.random() < 0.5:
            x_arm, y_arm = 'A', 'B'
        else:
            x_arm, y_arm = 'B', 'A'
        arms = {'A': a, 'B': b}

        x_text = arms[x_arm]['text']
        y_text = arms[y_arm]['text']

        with open(os.path.join(BLIND, f'{rid}_X.txt'), 'w', encoding='utf-8') as fh:
            fh.write(f'# {rid}_X  (cat={req["cat"]}, location={req["location"]}, stops={req["stops"]})\n\n')
            fh.write(x_text)
        with open(os.path.join(BLIND, f'{rid}_Y.txt'), 'w', encoding='utf-8') as fh:
            fh.write(f'# {rid}_Y  (cat={req["cat"]}, location={req["location"]}, stops={req["stops"]})\n\n')
            fh.write(y_text)

        key[rid] = {
            'cat': req['cat'],
            'location': req['location'],
            'stops': req['stops'],
            'X': x_arm,
            'Y': y_arm,
            'A_usd': a.get('usd'), 'A_seconds': a.get('seconds'),
            'B_usd': b.get('usd'), 'B_seconds': b.get('seconds'),
        }

    with open(os.path.join(BLIND, 'KEY.json'), 'w', encoding='utf-8') as fh:
        json.dump(key, fh, indent=2, ensure_ascii=False)

    n_x_is_a = sum(1 for v in key.values() if v['X'] == 'A')
    print(f'Wrote {len(key)} pairs ({len(key)*2} text files) + KEY.json to blind/')
    print(f'X=A in {n_x_is_a}/{len(key)} pairs, X=B in {len(key)-n_x_is_a}/{len(key)} pairs')


if __name__ == '__main__':
    main()
