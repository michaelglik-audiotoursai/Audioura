#!/usr/bin/env python3
"""score_local692b_tours.py — LOCAL-692B host-side editor scoring.

The generator container ships a LEGACY openai SDK, so tour_editor_score.judge()
returned None inside the eval container (D659 3d wants the PRODUCTION editor,
gpt-4.1, 3 runs). This host has the modern SDK (openai 2.x), so we score the
STORED tours here with gpt-4.1 x3 — the exact production editor — reading each
tour's content via `docker exec psql` (the DB port is not published to the host).

Usage: python3 score_local692b_tours.py 696:HCMC_BEFORE 697:HCMC_AFTER ...
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Load .env (OPENAI_API_KEY) for the modern SDK.
_env = os.path.join(HERE, '.env')
if os.path.exists(_env):
    for _l in open(_env):
        _l = _l.strip()
        if _l and not _l.startswith('#') and '=' in _l:
            k, v = _l.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

os.environ['EDITOR_SCORE_MODEL'] = 'gpt-4.1'
os.environ['EDITOR_SCORE_RUNS'] = '3'

import tour_editor_score as tes  # noqa: E402


def _fetch(tour_id):
    out = subprocess.run(
        ['docker', 'exec', 'development-postgres-2-1', 'psql', '-U', 'admin',
         '-d', 'audiotours', '-t', '-A', '-c',
         f'SELECT tour_content FROM audio_tours WHERE id={int(tour_id)};'],
        capture_output=True, text=True)
    return out.stdout


def main():
    specs = sys.argv[1:]
    if not specs:
        print('usage: score_local692b_tours.py <id:label> ...')
        return 2
    print(f"editor model={tes.MODEL} runs={tes.RUBRIC_RUNS}")
    for spec in specs:
        tid, _, label = spec.partition(':')
        text = _fetch(tid)
        if not text or len(text) < 200:
            print(f"{label} (id={tid}): NO TEXT")
            continue
        stops = text.count('\nStop ') or text.count('Stop ')
        try:
            score, detail = tes.score_text(label, text, stops)
            runs = detail.get('runs', [])
            print(f"{label} (id={tid}): score={score}  "
                  f"rubric_avg={detail.get('rubric_avg')}  "
                  f"story={detail.get('story')} place={detail.get('place')} "
                  f"accuracy={detail.get('accuracy')}  runs={len(runs)}")
        except Exception as e:
            print(f"{label} (id={tid}): SCORE FAILED {type(e).__name__}: {e}")


if __name__ == '__main__':
    sys.exit(main())
