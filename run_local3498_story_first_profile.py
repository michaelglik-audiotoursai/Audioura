"""run_local3498_story_first_profile.py — LOCAL-3498 story_first profiling batch.

Runs the church + airport tours (4 stops) with STORY_FIRST_PROFILE=1 so the
sub-phase instrumentation in story_first_profile.py emits its [STORY_FIRST]
lines. D261 env is mandatory (DISABLE_TOUR_CACHE, DATABASE_URL, STORIED_MODE).

Each run's full stdout is captured to its own log so the breakdown can be read
after the fact. Nothing here optimises anything — it only measures.
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Load .env (keys for OpenAI/Gemini/Serper) without overriding the shell.
_envp = os.path.join(HERE, '.env')
if os.path.exists(_envp):
    for line in open(_envp):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# D261 mandatory env.
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ['STORIED_MODE'] = 'true'
os.environ.setdefault('DATABASE_URL',
                      'postgresql://admin:password123@localhost:5433/audiotours')
# Turn the sub-phase profiler ON for this batch.
os.environ['STORY_FIRST_PROFILE'] = '1'

STOPS = 4
STAMP = time.strftime('%Y%m%d_%H%M')

# Three runs across the two required locations. Airport is repeated because the
# task names it as a case and a second sample bounds run-to-run variance.
RUNS = [
    ('church',  'Our Lady Help of Christians Catholic Church, Newton MA'),
    ('airport', 'Boston Logan International Airport, Boston MA'),
    ('church2', 'Our Lady Help of Christians Catholic Church, Newton MA'),
]

from generate_tour_text import generate_tour_text  # noqa: E402

for tag, location in RUNS:
    out_txt = os.path.join(HERE, f'L3498_{tag}_{STAMP}.txt')
    print('=' * 78)
    print(f"RUN {tag}: {location}  ({STOPS} stops)")
    print('=' * 78, flush=True)
    t0 = time.time()
    try:
        text, out_file, _coords = generate_tour_text(location, '', out_txt, STOPS)
    except Exception as e:
        import traceback
        print(f"RUN {tag} FAILED: {e}")
        traceback.print_exc()
        continue
    elapsed = time.time() - t0
    if text:
        open(out_txt, 'w', encoding='utf-8').write(text)
        print(f"\nRUN {tag} OK: {len(text)} chars in {elapsed:.1f}s -> {os.path.basename(out_txt)}",
              flush=True)
    else:
        print(f"\nRUN {tag}: no text returned ({elapsed:.1f}s)", flush=True)
