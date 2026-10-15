#!/usr/bin/env python3
"""make_hcmc_after_mp3.py — LOCAL-692.

Produce MP3s for the HCMC after-version so Michael can listen. Reads the stored
is_test tour from the DB by id, splits it into stops, and synthesises each stop
with AWS Polly (Joanna, neural) via boto3 directly — using the AWS creds already
in .env — writing MP3s to tours/local692_mp3/. Self-contained: does NOT touch any
audioura-* service container. [LOCAL-692B] Pronunciation of the Vietnamese names
is done at the TTS layer via Polly SSML <sub>/<phoneme> (TextType='ssml'); the
narration text is clean (no "(say: …)"), so the listener hears the correct names
without any respelling being read aloud.

Usage: python3 make_hcmc_after_mp3.py <tour_id>
"""
import os
import re
import subprocess
import sys

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'tours', 'local692_mp3')
VOICE = 'Joanna'  # English neural, the production default


def _load_env():
    env_path = os.path.realpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), '.env'))
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())
    except Exception as e:
        print(f"[env] could not read {env_path}: {e}")


def _fetch_tour(tour_id):
    # Prefer a mounted text file (container-friendly); fall back to docker exec
    # on a host that has the docker CLI.
    tf = os.environ.get('TOUR_TEXT_FILE')
    if tf and os.path.exists(tf):
        with open(tf, encoding='utf-8') as f:
            return f.read()
    out = subprocess.run(
        ['docker', 'exec', 'development-postgres-2-1', 'psql', '-U', 'admin',
         '-d', 'audiotours', '-t', '-A', '-c',
         f'SELECT tour_content FROM audio_tours WHERE id={int(tour_id)};'],
        capture_output=True, text=True).stdout
    return out


def _split_stops(text):
    """Return [(index, title, spoken_body)]. Spoken body excludes the metadata
    lines (Coordinates/Address/Museum Information/Directions) so the MP3 is the
    narration a listener hears."""
    parts = re.split(r"(?mi)^Stop\s+(\d+):\s*(.+)$", text)
    # parts: [pre, num, title, body, num, title, body, ...]
    stops = []
    for i in range(1, len(parts), 3):
        num = parts[i]
        title = parts[i + 1].strip()
        body = parts[i + 2]
        # Keep Orientation + narration; drop field/metadata and the Directions tail.
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


def _polly_mp3(text, path):
    import boto3
    region = os.environ.get('AWS_REGION') or os.environ.get(
        'AWS_DEFAULT_REGION') or 'us-east-1'
    client = boto3.client('polly', region_name=region)
    # [LOCAL-692B] Pronounce known Vietnamese names via SSML <sub>/<phoneme> at
    # the TTS layer (the narration text is clean — no "(say:)"). Build SSML per
    # chunk so each chunk is an independent <speak> document.
    try:
        import vietnamese_name_aid as _vn
    except Exception:
        _vn = None

    def _ssml_or_text(chunk):
        if _vn is None:
            return chunk, 'text'
        try:
            if any(a.full in chunk for a in _vn.LEXICON.values()):
                ssml, _ = _vn.to_ssml(chunk)
                return ssml, 'ssml'
        except Exception:
            pass
        return chunk, 'text'

    # Polly caps a single request at 3000 displayed chars; split on sentences if
    # needed. SSML tags add a little length, so split the PLAIN text at 2600.
    chunks = []
    if len(text) <= 2600:
        chunks = [text]
    else:
        cur = ''
        for sent in re.split(r'(?<=[.!?])\s+', text):
            if len(cur) + len(sent) + 1 > 2600 and cur:
                chunks.append(cur)
                cur = sent
            else:
                cur = (cur + ' ' + sent).strip()
        if cur:
            chunks.append(cur)
    audio = b''
    for ch in chunks:
        payload, ttype = _ssml_or_text(ch)
        resp = client.synthesize_speech(
            Text=payload, TextType=ttype, OutputFormat='mp3',
            VoiceId=VOICE, Engine='neural')
        audio += resp['AudioStream'].read()
    with open(path, 'wb') as f:
        f.write(audio)
    return len(audio)


def main():
    if len(sys.argv) < 2:
        print('usage: make_hcmc_after_mp3.py <tour_id>')
        return 2
    tour_id = sys.argv[1]
    _load_env()
    os.makedirs(OUT_DIR, exist_ok=True)
    text = _fetch_tour(tour_id)
    if not text or len(text) < 200:
        print(f'[error] tour {tour_id} not found or empty')
        return 1
    stops = _split_stops(text)
    print(f'[mp3] tour {tour_id}: {len(stops)} stops -> {OUT_DIR}')
    total = 0
    for num, title, spoken in stops:
        safe = re.sub(r'[^A-Za-z0-9]+', '_', title)[:40].strip('_')
        path = os.path.join(OUT_DIR, f'HCMC_after_stop{num}_{safe}.mp3')
        try:
            n = _polly_mp3(spoken, path)
            total += n
            print(f'  stop {num}: {title[:50]} -> {os.path.basename(path)} '
                  f'({n} bytes, {len(spoken)} chars)')
        except Exception as e:
            print(f'  stop {num}: FAILED {type(e).__name__}: {e}')
    print(f'[mp3] done, {total} audio bytes total')
    return 0


if __name__ == '__main__':
    sys.exit(main())
