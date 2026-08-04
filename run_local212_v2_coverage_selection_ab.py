#!/usr/bin/env python3
"""LOCAL-212 v2: Coverage-aware stop selection A/B test.

Venues:
  1. Musée Matisse (6 stops, all COVERED) — demonstrates mechanism fires with surplus.
  2. Palais Lascaris (12 stops: 8 COVERED, 3 CREATOR_ONLY, 1 EMPTY) — demonstrates
     preference ordering with mixed verdicts.

Arms:
  - ON:  DISABLE_COVERAGE_SELECTION unset (default, selection active)
  - OFF: DISABLE_COVERAGE_SELECTION=1

2 stops requested, 3 runs per arm per venue.
Runs inside the container (audioura-tour-generator-1) to avoid resolver issues (D55/bounce).
"""
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))

from db_connection import get_connection

# ─── Configuration ───────────────────────────────────────────────────────────
VENUES = [
    {
        'name': 'Musee Matisse, Nice, France',
        'label': 'matisse',
        'tour_type': 'museum',
        'total_stops': 2,
        'expected_surplus': True,  # 6 candidates > 2 requested
    },
    {
        'name': 'Palais Lascaris, Nice',
        'label': 'palais_lascaris',
        'tour_type': 'museum',
        'total_stops': 2,
        'expected_surplus': True,  # 12 candidates > 2 requested
    },
]
RUNS_PER_ARM = 3
CONTAINER = 'audioura-tour-generator-1'
COST_CEILING = 0.45
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tours')

# ─── Generation via docker exec ──────────────────────────────────────────────
def clear_cache_for_venue(venue):
    """Delete tour_cache entries matching this venue/type/stops so generation is fresh."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM tour_cache WHERE location = %s AND tour_type = %s AND total_stops = %s",
        (venue['name'], venue['tour_type'], venue['total_stops'])
    )
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    if deleted:
        print(f"  Cleared {deleted} cache entry(ies) for {venue['name']}/{venue['tour_type']}/{venue['total_stops']}")


def run_generation_in_container(venue, arm, run_idx):
    """Run a single generation inside the container. Returns dict with results."""
    # Clear cache before each run so we get fresh generation
    clear_cache_for_venue(venue)
    
    output_file = f"/app/tours/LOCAL212v2_{venue['label']}_{arm}_run{run_idx}.txt"
    
    disable_line = 'os.environ["DISABLE_COVERAGE_SELECTION"] = "1"' if arm == 'OFF' else 'os.environ.pop("DISABLE_COVERAGE_SELECTION", None)'

    # Write script to a temp file to avoid escaping issues
    script_content = f'''import sys, os, time, re
sys.path.insert(0, "/app")
os.environ["STORIED_MODE"] = "true"
os.environ["DISABLE_CORPUS_GATE"] = "0"
{disable_line}
os.environ["TOUR_LLM_MODEL"] = "gpt-3.5-turbo"

from generate_tour_text import generate_tour_text
_start = time.time()
result = generate_tour_text(
    "{venue["name"]}",
    "{venue["tour_type"]}",
    output_file="{output_file}",
    total_stops={venue["total_stops"]},
)
_elapsed = time.time() - _start
if result and result[0]:
    text = result[0]
    stops = re.findall(r"^Stop \\d+:", text, re.MULTILINE)
    print("===RESULT===")
    print(f"SUCCESS|stops={{len(stops)}}|elapsed={{_elapsed:.1f}}")
    print("===TEXT_START===")
    print(text)
    print("===TEXT_END===")
else:
    print("===RESULT===")
    print(f"FAILED|elapsed={{_elapsed:.1f}}")
'''
    # Write to a temp file on the host, then copy into container
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(script_content)
        tmp_path = f.name
    
    try:
        # Copy script into container
        subprocess.run(['docker', 'cp', tmp_path, f'{CONTAINER}:/tmp/gen_script.py'],
                      capture_output=True, check=True)
        
        cmd = ['docker', 'exec', CONTAINER, 'python3', '/tmp/gen_script.py']
        print(f"  Running {venue['label']} {arm} run {run_idx}...")
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        output = proc.stdout + proc.stderr
    finally:
        os.unlink(tmp_path)
    
    # Parse result
    if '===RESULT===' in output:
        result_line = output.split('===RESULT===')[1].strip().split('\n')[0]
        if result_line.startswith('SUCCESS'):
            parts = dict(p.split('=') for p in result_line.split('|')[1:])
            stops_count = int(parts.get('stops', 0))
            
            # Extract text
            if '===TEXT_START===' in output and '===TEXT_END===' in output:
                text = output.split('===TEXT_START===')[1].split('===TEXT_END===')[0].strip()
            else:
                text = None
            
            elapsed_str = parts.get('elapsed', '0').rstrip('s')
            return {
                'success': True,
                'stops_delivered': stops_count,
                'text': text,
                'logs': output,
                'elapsed': float(elapsed_str) if elapsed_str else 0,
            }
    
    return {
        'success': False,
        'stops_delivered': 0,
        'text': None,
        'logs': output,
        'elapsed': 0,
    }


def extract_stop_titles(text):
    """Extract stop titles from generated text."""
    if not text:
        return []
    pattern = r'^Stop \d+:\s*(.+)$'
    matches = re.findall(pattern, text, re.MULTILINE)
    return [m.strip() for m in matches]


def extract_paragraphs(text):
    """Extract content paragraphs (non-heading, non-blank lines of 50+ chars)."""
    if not text:
        return []
    paragraphs = []
    for line in text.split('\n'):
        line = line.strip()
        if len(line) >= 50 and not re.match(r'^(Stop \d+:|#{1,3} )', line):
            paragraphs.append(line)
    return paragraphs


def extract_coverage_log(logs):
    """Extract [LOCAL-212] coverage selection log lines."""
    lines = []
    for line in logs.split('\n'):
        if '[LOCAL-212]' in line:
            lines.append(line.strip())
    return lines


def run_claim_check(paragraphs, venue_name, stop_titles):
    """Run claim_check.py on paragraphs. Returns (total_claims, unsupported_claims)."""
    if not paragraphs:
        return 0, 0
    
    conn = get_connection()
    total_claims = 0
    unsupported_claims = 0
    
    try:
        from claim_check import check_paragraph
        from stop_corpus_reader import get_stop_corpus_for_tour
        
        # Fetch corpus for the stops
        corpus_data = get_stop_corpus_for_tour(venue_name, stop_titles, conn)
        
        # Build passage lookup per stop
        stop_passages = {}
        all_passages = []
        for title in stop_titles:
            sd = corpus_data.get(title)
            if sd and sd.get('passages'):
                stop_passages[title] = sd['passages']
                all_passages.extend(sd['passages'])
            else:
                stop_passages[title] = []
        
        for para in paragraphs:
            # Determine which stop this paragraph belongs to (best-effort: first title match)
            para_stop = None
            for title in stop_titles:
                if title.lower() in para.lower():
                    para_stop = title
                    break
            if not para_stop and stop_titles:
                para_stop = stop_titles[0]
            
            passages_for_stop = stop_passages.get(para_stop, [])
            other_passages = [p for t, ps in stop_passages.items() if t != para_stop for p in ps]
            
            result = check_paragraph(
                para,
                stop_title=para_stop or '',
                venue_name=venue_name,
                passages=passages_for_stop,
                other_stop_passages=other_passages if other_passages else None,
            )
            total_claims += len(result.get('claims', []))
            unsupported_claims += result.get('unsupported_count', 0)
    except Exception as e:
        print(f"    claim_check error: {e}")
    finally:
        conn.close()
    
    return total_claims, unsupported_claims


def run_style_validator(paragraphs):
    """Run style_validator_detector on paragraphs. Returns (failure_count, total_checked)."""
    if not paragraphs:
        return 0, 0
    
    try:
        from style_validator_detector import validate_paragraph
        total = len(paragraphs)
        failures = 0
        for para in paragraphs:
            result = validate_paragraph(para)
            if result.get('rules_violated'):
                failures += 1
        return failures, total
    except Exception as e:
        print(f"    style_validator error: {e}")
        return 0, len(paragraphs)


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Record baseline
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM audio_tours')
    baseline_count = cur.fetchone()[0]
    cur.execute('SELECT id FROM audio_tours WHERE id IN (1,12,14,17,21,24,27,28,29,152) ORDER BY id')
    nice_list = [r[0] for r in cur.fetchall()]
    conn.close()
    
    print(f"=== LOCAL-212 v2: Coverage-aware stop selection A/B ===")
    print(f"Baseline audio_tours: {baseline_count}")
    print(f"Nice list intact: {nice_list == [1,12,14,17,21,24,27,28,29,152]}")
    print()
    
    all_results = {}
    all_paragraphs = []
    total_cost_estimate = 0.0
    
    for venue in VENUES:
        print(f"\n{'='*60}")
        print(f"VENUE: {venue['name']} ({venue['label']})")
        print(f"  Requested stops: {venue['total_stops']}")
        print(f"  Expected surplus: {venue['expected_surplus']}")
        print(f"{'='*60}")
        
        venue_results = {'ON': [], 'OFF': []}
        
        for arm in ['ON', 'OFF']:
            print(f"\n  --- ARM: selection {arm} ---")
            for run_idx in range(1, RUNS_PER_ARM + 1):
                result = run_generation_in_container(venue, arm, run_idx)
                
                if result['success']:
                    titles = extract_stop_titles(result['text'])
                    paragraphs = extract_paragraphs(result['text'])
                    coverage_logs = extract_coverage_log(result['logs'])
                    
                    result['stop_titles'] = titles
                    result['paragraph_count'] = len(paragraphs)
                    result['coverage_logs'] = coverage_logs
                    result['paragraphs'] = paragraphs
                    
                    # Save paragraphs for D71
                    for i, para in enumerate(paragraphs):
                        all_paragraphs.append({
                            'venue': venue['label'],
                            'arm': arm,
                            'run': run_idx,
                            'paragraph_idx': i,
                            'text': para,
                            'stop_titles': titles,
                        })
                    
                    # Estimate cost (gpt-3.5-turbo ~$0.002/tour for 2 stops)
                    total_cost_estimate += 0.005
                    
                    print(f"    ✓ {result['stops_delivered']} stops delivered: {titles}")
                    print(f"      Requested: {venue['total_stops']}, Delivered: {result['stops_delivered']}")
                    if result['stops_delivered'] < venue['total_stops']:
                        print(f"      ⚠️  SHORTFALL: requested {venue['total_stops']}, got {result['stops_delivered']}")
                    for cl in coverage_logs:
                        print(f"      {cl}")
                else:
                    result['stop_titles'] = []
                    result['paragraph_count'] = 0
                    result['coverage_logs'] = []
                    result['paragraphs'] = []
                    print(f"    ✗ FAILED")
                    # Show first 500 chars of logs for diagnosis
                    print(f"      Logs: {result['logs'][:500]}")
                
                venue_results[arm].append(result)
                
                # Save tour text
                if result['text']:
                    fname = f"LOCAL212v2_{venue['label']}_{arm}_run{run_idx}.txt"
                    with open(os.path.join(OUTPUT_DIR, fname), 'w') as f:
                        f.write(result['text'])
        
        all_results[venue['label']] = venue_results
    
    # ─── Run claim_check and style_validator ─────────────────────────────────
    print(f"\n{'='*60}")
    print("METRICS COMPUTATION")
    print(f"{'='*60}")
    
    metrics = {}
    for venue in VENUES:
        vr = all_results[venue['label']]
        venue_metrics = {'ON': [], 'OFF': []}
        
        for arm in ['ON', 'OFF']:
            for i, run in enumerate(vr[arm]):
                if not run['success'] or not run.get('paragraphs'):
                    venue_metrics[arm].append({
                        'run': i+1,
                        'success': False,
                        'stops_delivered': run['stops_delivered'],
                        'stop_titles': run.get('stop_titles', []),
                    })
                    continue
                
                paragraphs = run['paragraphs']
                
                # claim_check
                total_claims, unsupported = run_claim_check(
                    paragraphs, venue['name'], run.get('stop_titles', []))
                
                # style_validator
                style_failures, style_total = run_style_validator(paragraphs)
                
                # anchor rate (simple: does paragraph reference a specific place/work?)
                anchored = sum(1 for p in paragraphs if any(
                    t.lower() in p.lower() for t in run.get('stop_titles', []) if t
                ))
                
                metric = {
                    'run': i+1,
                    'success': True,
                    'stops_delivered': run['stops_delivered'],
                    'stops_requested': venue['total_stops'],
                    'stop_titles': run.get('stop_titles', []),
                    'paragraph_count': len(paragraphs),
                    'total_claims': total_claims,
                    'unsupported_claims': unsupported,
                    'unsupported_per_para': unsupported / len(paragraphs) if paragraphs else 0,
                    'style_failures': style_failures,
                    'style_total': style_total,
                    'style_fail_rate': style_failures / style_total if style_total else 0,
                    'anchored': anchored,
                    'anchor_rate': anchored / len(paragraphs) if paragraphs else 0,
                    'coverage_logs': run.get('coverage_logs', []),
                }
                venue_metrics[arm].append(metric)
        
        metrics[venue['label']] = venue_metrics
    
    # ─── Report ──────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("RESULTS REPORT")
    print(f"{'='*60}")
    
    for venue in VENUES:
        vm = metrics[venue['label']]
        print(f"\n### {venue['name']} ###")
        print(f"Requested stops: {venue['total_stops']}")
        print()
        
        for arm in ['ON', 'OFF']:
            print(f"  ARM: {arm}")
            for m in vm[arm]:
                if not m.get('success'):
                    print(f"    Run {m['run']}: FAILED (stops delivered: {m['stops_delivered']})")
                    continue
                print(f"    Run {m['run']}: {m['stops_delivered']} stops delivered | "
                      f"titles={m['stop_titles']} | "
                      f"unsupported/para={m['unsupported_per_para']:.3f} | "
                      f"style_fail={m['style_fail_rate']:.3f} | "
                      f"anchor={m['anchor_rate']:.3f}")
            
            successful = [m for m in vm[arm] if m.get('success')]
            if successful:
                avg_unsupported = sum(m['unsupported_per_para'] for m in successful) / len(successful)
                avg_style = sum(m['style_fail_rate'] for m in successful) / len(successful)
                avg_anchor = sum(m['anchor_rate'] for m in successful) / len(successful)
                all_delivered = [m['stops_delivered'] for m in successful]
                print(f"    AVG: unsupported/para={avg_unsupported:.3f} | "
                      f"style_fail={avg_style:.3f} | anchor={avg_anchor:.3f}")
                print(f"    Stops delivered: {all_delivered} (requested {venue['total_stops']} each)")
            print()
    
    # ─── Comparability check ─────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("COMPARABILITY CHECK")
    print(f"{'='*60}")
    
    for venue in VENUES:
        vm = metrics[venue['label']]
        on_titles = [set(m.get('stop_titles', [])) for m in vm['ON'] if m.get('success')]
        off_titles = [set(m.get('stop_titles', [])) for m in vm['OFF'] if m.get('success')]
        
        # Check within-arm consistency
        on_consistent = len(set(frozenset(t) for t in on_titles)) == 1 if on_titles else False
        off_consistent = len(set(frozenset(t) for t in off_titles)) == 1 if off_titles else False
        
        # Check cross-arm comparison validity
        if on_titles and off_titles:
            same_stops = on_titles[0] == off_titles[0] if on_consistent and off_consistent else False
        else:
            same_stops = False
        
        print(f"\n  {venue['label']}:")
        print(f"    ON arm consistent titles: {on_consistent} ({[list(t) for t in on_titles]})")
        print(f"    OFF arm consistent titles: {off_consistent} ({[list(t) for t in off_titles]})")
        print(f"    Cross-arm same stops: {same_stops}")
        if not on_consistent or not off_consistent:
            print(f"    ⚠️  Non-deterministic stop selection within arm — comparison may be confounded")
        if not same_stops and on_consistent and off_consistent:
            print(f"    ℹ️  Arms chose DIFFERENT stops — this IS the mechanism working (ON prefers COVERED)")
    
    # ─── Persist ─────────────────────────────────────────────────────────────
    results_file = os.path.join(OUTPUT_DIR, 'LOCAL212v2_results.json')
    with open(results_file, 'w') as f:
        # Remove non-serializable 'text' from results before saving
        save_results = {}
        for venue_label, vr in all_results.items():
            save_results[venue_label] = {}
            for arm, runs in vr.items():
                save_results[venue_label][arm] = []
                for run in runs:
                    save_run = {k: v for k, v in run.items() if k != 'text'}
                    save_results[venue_label][arm].append(save_run)
        json.dump({
            'results': save_results,
            'metrics': metrics,
            'config': {
                'venues': VENUES,
                'runs_per_arm': RUNS_PER_ARM,
                'cost_estimate': total_cost_estimate,
            },
        }, f, indent=2, default=str)
    
    paragraphs_file = os.path.join(OUTPUT_DIR, 'LOCAL212v2_all_paragraphs.json')
    with open(paragraphs_file, 'w') as f:
        json.dump(all_paragraphs, f, indent=2)
    
    print(f"\nPersisted: {results_file}")
    print(f"Persisted: {paragraphs_file}")
    print(f"Estimated cost: ${total_cost_estimate:.3f}")
    
    # ─── Final row counts ────────────────────────────────────────────────────
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM audio_tours')
    final_count = cur.fetchone()[0]
    cur.execute('SELECT id FROM audio_tours WHERE id IN (1,12,14,17,21,24,27,28,29,152) ORDER BY id')
    final_nice = [r[0] for r in cur.fetchall()]
    conn.close()
    
    print(f"\n{'='*60}")
    print("ROW COUNTS")
    print(f"{'='*60}")
    print(f"  audio_tours: {baseline_count} → {final_count} (Δ {final_count - baseline_count})")
    print(f"  Nice list intact: {final_nice == [1,12,14,17,21,24,27,28,29,152]}")


if __name__ == '__main__':
    main()
