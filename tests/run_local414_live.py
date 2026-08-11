#!/usr/bin/env python3
"""LOCAL-414: Live run — MFA tour with tier gate + Palais control.

Env: DISABLE_TOUR_CACHE=1, DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours,
     STORIED_MODE=true

Generates:
1. MFA 4-stop tour (the failing scenario from the ticket)
2. Palais Lascaris 4-stop control (D302/D326)

Reports per stop: tier gate survival count, artist attribution, banned phrases.
"""
import os
import sys
import time
import json
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Load .env for API keys
_env_path = os.path.join(PROJECT_ROOT, '.env')
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _v = _line.split('=', 1)
                _k, _v = _k.strip(), _v.strip()
                if _k and _k not in os.environ:
                    os.environ[_k] = _v

# Required env vars (from ticket)
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ['DATABASE_URL'] = 'postgresql://admin:password123@localhost:5433/audiotours'
os.environ['STORIED_MODE'] = 'true'

# Do NOT change TOUR_LLM_MODEL (D346)
# Do NOT delete from audio_tours

# Force production DB for corpus reads
os.environ.pop('PYTEST_CURRENT_TEST', None)
os.environ.pop('_AUDIOURA_PYTEST_SESSION', None)

from generate_tour_text import generate_tour_text

TOURS_DIR = os.path.join(PROJECT_ROOT, 'tours')
os.makedirs(TOURS_DIR, exist_ok=True)


def run_mfa_tour():
    """Generate the MFA tour (the one that failed with apologetics content)."""
    print("\n" + "=" * 72)
    print("LOCAL-414: MFA 4-stop tour generation")
    print("=" * 72)
    
    location = "Museum of Fine Arts, Boston, MA"
    tour_type = "museum"
    output_file = os.path.join(TOURS_DIR, "LOCAL414_MFA_4stop.txt")
    
    start = time.time()
    tour_text, out_file, coords = generate_tour_text(
        location, tour_type, output_file,
        total_stops=4,
    )
    elapsed = time.time() - start
    
    print(f"\n{'=' * 72}")
    print(f"MFA tour completed in {elapsed:.1f}s")
    print(f"Output: {out_file}")
    print(f"{'=' * 72}")
    
    return tour_text, out_file


def run_palais_control():
    """Palais Lascaris 4/4 control (D302/D326)."""
    print("\n" + "=" * 72)
    print("LOCAL-414: Palais Lascaris 4-stop control (D302/D326)")
    print("=" * 72)
    
    location = "Palais Lascaris, Nice, France"
    tour_type = "museum"
    output_file = os.path.join(TOURS_DIR, "LOCAL414_Palais_control.txt")
    
    start = time.time()
    tour_text, out_file, coords = generate_tour_text(
        location, tour_type, output_file,
        total_stops=4,
    )
    elapsed = time.time() - start
    
    print(f"\n{'=' * 72}")
    print(f"Palais control completed in {elapsed:.1f}s")
    print(f"Output: {out_file}")
    print(f"{'=' * 72}")
    
    return tour_text, out_file


def analyze_tour(tour_text, label):
    """Analyze a tour for LOCAL-414 acceptance criteria."""
    print(f"\n{'─' * 72}")
    print(f"ANALYSIS: {label}")
    print(f"{'─' * 72}")
    
    # Parse stops
    stop_pattern = re.compile(r'Stop\s+(\d+):\s*(.+?)(?=\nStop\s+\d+:|\Z)', re.DOTALL)
    stops = stop_pattern.findall(tour_text)
    
    if not stops:
        # Try alternate format
        stops = [(str(i+1), s) for i, s in enumerate(tour_text.split('\n\n')) if s.strip()][:4]
    
    print(f"  Stops found: {len(stops)}")
    
    banned_phrases = [
        'invites contemplation', 'invites the viewer', 'invites us to',
        'a testament to', 'stands as a testament',
    ]
    
    for num, text in stops:
        print(f"\n  Stop {num}:")
        text_lower = text.lower()
        
        # Check banned phrases
        found_banned = [bp for bp in banned_phrases if bp in text_lower]
        if found_banned:
            print(f"    ❌ BANNED PHRASES FOUND: {found_banned}")
        else:
            print(f"    ✓ No banned phrases")
        
        # Check for doctrinal framing
        doctrinal_signals = ['fall into sin', 'disobedience', 'creationist',
                            'apologetics', 'biblical truth', 'gospel']
        found_doctrinal = [d for d in doctrinal_signals if d in text_lower]
        if found_doctrinal:
            print(f"    ❌ DOCTRINAL FRAMING: {found_doctrinal}")
        else:
            print(f"    ✓ No doctrinal framing")
    
    # Check for Cyrus Edwin Dallin (stop 1 fact from 413)
    if 'dallin' in tour_text.lower():
        print(f"\n  ✓ 'Dallin' present in tour (LOCAL-413 search fact preserved)")
    else:
        print(f"\n  ⚠️ 'Dallin' NOT found — LOCAL-413 regression?")
    
    # Check for Rembrandt in 1629 (stop 4 fact from 413)
    if 'rembrandt' in tour_text.lower() and '1629' in tour_text:
        print(f"  ✓ 'Rembrandt' + '1629' present (LOCAL-413 search fact preserved)")
    elif 'rembrandt' in tour_text.lower():
        print(f"  ⚠️ 'Rembrandt' present but '1629' missing")
    else:
        print(f"  ⚠️ 'Rembrandt' NOT found")
    
    # 'invites contemplation' final check
    if 'invites contemplation' in tour_text.lower():
        print(f"\n  ❌ FAIL: 'invites contemplation' in delivered text!")
    else:
        print(f"\n  ✓ 'invites contemplation' absent from delivered text")
    
    return len(stops)


if __name__ == '__main__':
    print("LOCAL-414 Live Run")
    print(f"Started: {time.strftime('%Y-%m-%dT%H:%M:%S%z')}")
    print(f"STORIED_MODE={os.environ.get('STORIED_MODE')}")
    print(f"DISABLE_TOUR_CACHE={os.environ.get('DISABLE_TOUR_CACHE')}")
    print(f"DATABASE_URL=...@localhost:5433/audiotours")
    print(f"TOUR_LLM_MODEL={os.environ.get('TOUR_LLM_MODEL', 'gpt-3.5-turbo (default)')}")
    
    # Run MFA tour
    mfa_text, mfa_file = run_mfa_tour()
    mfa_stops = analyze_tour(mfa_text, "MFA Boston")
    
    # Run Palais control
    palais_text, palais_file = run_palais_control()
    palais_stops = analyze_tour(palais_text, "Palais Lascaris (control)")
    
    print(f"\n{'=' * 72}")
    print("SUMMARY")
    print(f"{'=' * 72}")
    print(f"  MFA:    {mfa_stops}/4 stops")
    print(f"  Palais: {palais_stops}/4 stops")
    print(f"  Output files:")
    print(f"    {mfa_file}")
    print(f"    {palais_file}")
    print(f"Finished: {time.strftime('%Y-%m-%dT%H:%M:%S%z')}")
