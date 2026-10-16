#!/usr/bin/env python3
"""run_local706_eval.py — LOCAL-706 (D667) real-path evaluation.

Renders the HCMC Museum of Fine Arts tour (id 697) through the REAL TTS path —
polly-tts service (TTS_ENGINE=kokoro) in MY OWN disposable container → Kokoro
host service on :5181 — BEFORE and AFTER the name-aid change, and writes the
after-version MP3s plus a report of how each of the three Vietnamese artist
names is rendered.

"Before" = the service WITHOUT the Kokoro markup (bare diacritic names reach
misaki). "After" = the service WITH LOCAL-706 (names wrapped in [name](/IPA/)).
Both go through the identical container→host path; the ONLY difference is the
markup, which is exactly what the ticket asks to measure. No Polly calls are
needed (English voice → Kokoro); the container still has boto3 only as a
fallback that is never hit while the host is healthy.

The container is started by run_local706_live.sh, which also phonemises each
name via the host's misaki G2P for the human-readable before/after rendering
table. This script talks to the already-running container on $POLLY_URL.

Usage: POLLY_URL=http://localhost:5718/synthesize python3 run_local706_eval.py 697
"""
import os
import re
import sys

import requests

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'tours', 'local706_mp3')
VOICE = 'Joanna'                       # English neural → Kokoro af_heart
POLLY_URL = os.environ.get('POLLY_URL', 'http://localhost:5718/synthesize')
NAMES = ['Nguyễn Gia Trí', 'Nguyễn Sáng', 'Tô Ngọc Vân']


def _tour_text():
    tf = os.environ.get('TOUR_TEXT_FILE', '/tmp/tour697.txt')
    with open(tf, encoding='utf-8') as f:
        return f.read()


def _split_stops(text):
    parts = re.split(r"(?mi)^Stop\s+(\d+):\s*(.+)$", text)
    stops = []
    for i in range(1, len(parts), 3):
        num = parts[i]
        title = parts[i + 1].strip()
        body = parts[i + 2]
        lines = []
        for ln in body.splitlines():
            s = ln.strip()
            if re.match(r'(?i)^(Coordinates|Address|Museum Information|'
                        r'The museum is open|Directions|Continue|Proceed|Next)\b', s):
                continue
            lines.append(ln)
        spoken = re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()
        spoken = f'{title}. {spoken}'
        stops.append((num, title, spoken))
    return stops


def _render(text, path):
    resp = requests.post(
        POLLY_URL,
        json={'text': text, 'voice_id': VOICE, 'output_format': 'mp3'},
        timeout=300,
    )
    resp.raise_for_status()
    data = resp.content
    with open(path, 'wb') as f:
        f.write(data)
    return len(data)


def main():
    tour_id = sys.argv[1] if len(sys.argv) > 1 else '697'
    os.makedirs(OUT_DIR, exist_ok=True)
    text = _tour_text()
    stops = _split_stops(text)
    print(f'[eval] tour {tour_id}: {len(stops)} stops via {POLLY_URL} -> {OUT_DIR}')
    total = 0
    for num, title, spoken in stops:
        safe = re.sub(r'[^A-Za-z0-9]+', '_', title)[:40].strip('_')
        path = os.path.join(OUT_DIR, f'HCMC697_after_stop{num}_{safe}.mp3')
        try:
            n = _render(spoken, path)
            total += n
            has = [nm for nm in NAMES if nm in spoken]
            print(f'  stop {num}: {title[:48]:48s} -> {os.path.basename(path)} '
                  f'({n} B, {len(spoken)} ch) names={has}')
        except Exception as e:
            print(f'  stop {num}: FAILED {type(e).__name__}: {e}')
    print(f'[eval] done, {total} audio bytes total')
    return 0


if __name__ == '__main__':
    sys.exit(main())
