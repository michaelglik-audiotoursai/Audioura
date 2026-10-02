"""Show exactly which snippets survive ranking for stops 2 and 3."""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from snippet_ranker import rank_and_cap_snippets, score_snippet

# Load the dump
with open('SNIPPET_DUMP_MFA_STOPS_2_3.json') as f:
    dump = json.load(f)

for stop_key in ['stop_2', 'stop_3']:
    data = dump[stop_key]
    print(f"\n{'=' * 72}")
    print(f"  {data['name']} — Ranking Analysis")
    print(f"{'=' * 72}")
    
    snippets = data['snippets']
    # Reconstruct snippet dicts as the ranker expects
    snippet_dicts = [
        {'title': s['title'], 'snippet': s['snippet'], 'url': s.get('url', ''), 'tier': s.get('tier', '')}
        for s in snippets
    ]
    
    artist = data['artist']
    
    # Score each one
    print(f"\n  ALL SCORES (artist='{artist}'):")
    for i, sd in enumerate(snippet_dicts):
        sc = score_snippet(sd, artist)
        text_preview = sd['snippet'][:100]
        marker = ""
        if sc == -999:
            marker = " [REJECTED]"
        print(f"    [{i+1:2d}] score={sc:3d}{marker} | {sd['title'][:50]}")
        print(f"          {text_preview}")
    
    # Now do the actual rank_and_cap
    ranked, report = rank_and_cap_snippets(snippet_dicts, artist=artist, work_title=data['name'])
    print(f"\n  AFTER RANK+CAP (cap=5):")
    print(f"    input={report['input_count']} bio_rejected={report['rejected_biography_only']} output={report['output_count']}")
    print(f"\n  THE 5 SNIPPETS THAT REACH THE PROMPT:")
    for i, r in enumerate(ranked):
        print(f"    [{i+1}] title: {r['title'][:80]}")
        print(f"        text:  {r['snippet'][:200]}")
        print()
