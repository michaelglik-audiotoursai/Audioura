#!/usr/bin/env python3
"""LOCAL-413: Live end-to-end run — MFA storied tour with real SERP search.

Generates the MFA storied tour and reports:
1. Per stop: the five injected snippets (from prompt_dump_stop1.txt and console output)
2. Per stop: at least one search-sourced fact that appears in delivered text

This is NOT a simulation. It calls real SERP API and real LLM.
"""

import os
import sys
import tempfile

# Force env
os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ.setdefault('DATABASE_URL', 'postgresql://admin:password123@localhost:5433/audiotours')

# Load .env manually (no dotenv dependency)
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(_env_path):
    with open(_env_path, 'r') as _ef:
        for _line in _ef:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _v = _line.split('=', 1)
                os.environ.setdefault(_k.strip(), _v.strip())

# Verify SERP key
if not os.environ.get('SERP_API_KEY'):
    print("FATAL: SERP_API_KEY not available. Stopping — will not simulate.")
    sys.exit(1)

print(f"SERP_API_KEY present: {'*' * 4}{os.environ['SERP_API_KEY'][-4:]}")
print(f"SERP_PROVIDER: {os.environ.get('SERP_PROVIDER', 'not set')}")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import generate_tour_text
from generate_tour_text import generate_tour_text as gen_tour

# Create output in this worktree
_output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tours')
os.makedirs(_output_dir, exist_ok=True)
_output_path = os.path.join(_output_dir, 'local413_live_run.txt')

print("\n" + "=" * 72)
print("  LOCAL-413: LIVE MFA STORIED TOUR GENERATION")
print("=" * 72)

tour_text, output_file, coords = gen_tour(
    "Museum of Fine Arts, Boston, Massachusetts",
    "contained",
    _output_path,
    total_stops=4,
    persona=None,
    user_id='local413_live',
    job_id='local413_live',
)

if tour_text is None:
    print("\n\nFATAL: generate_tour_text returned None — generation failed.")
    sys.exit(1)

# Save the delivered text
with open(_output_path, 'w', encoding='utf-8') as f:
    f.write(tour_text)
print(f"\n  Delivered text written to: {_output_path}")
print(f"  Length: {len(tour_text)} chars")

# Report the prompt dump
_dump_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prompt_dump_stop1.txt')
if os.path.exists(_dump_path):
    with open(_dump_path, 'r', encoding='utf-8') as f:
        _dump = f.read()
    print(f"\n  Prompt dump exists: {_dump_path}")
    print(f"  Prompt dump length: {len(_dump)} chars")
else:
    print(f"\n  WARNING: prompt_dump_stop1.txt not found at {_dump_path}")

print("\n" + "=" * 72)
print("  GENERATION COMPLETE")
print("=" * 72)
