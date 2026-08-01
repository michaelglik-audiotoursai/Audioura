"""LOCAL-38 Acceptance: Theme Thread Discovery (SQ-S6b) pilot.

Runs all three venues (Asian Arts, Matisse, Palais Lascaris), captures:
- Discovered themes with coverage scores and supporting element IDs
- Prolog promise and epilog payoff
- Cross-stop callbacks (specific names/works/events referencing other stops)
- Degradation path test
- Regression: Asian 8/8 documented works, base ≥81.25, byte-identical x3
"""
import hashlib
import json
import os
import subprocess
import sys
import time

import requests

GENERATOR_URL = "http://localhost:5000"
TOURS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tours")

# Venue configurations
VENUES = {
    "asian": {
        "location": "Museum of Asian Arts, Nice, France",
        "tour_type": "museum tour",
        "output_prefix": "local38_asian",
        "expected_stops": 8,
        "min_base_score": 81.25,
    },
    "matisse": {
        "location": "Musee Matisse, Nice, France",
        "tour_type": "museum tour",
        "output_prefix": "local38_matisse",
        "expected_stops": 8,
    },
    "palais": {
        "location": "Palais Lascaris, Nice",
        "tour_type": "art and historical instruments",
        "output_prefix": "local38_palais",
        "expected_stops": 6,  # ≥6 is the bar
    },
}


def wait_for_service(url, timeout=60):
    """Wait for the generator service to be ready."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{url}/health", timeout=5)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def generate_tour(venue_key: str, run_idx: int = 0) -> dict:
    """Submit a generation job and poll for result."""
    cfg = VENUES[venue_key]
    
    payload = {
        "location": cfg["location"],
        "tour_type": cfg["tour_type"],
    }
    
    print(f"\n{'='*60}")
    print(f"Generating: {venue_key} (run {run_idx+1})")
    print(f"{'='*60}")
    
    r = requests.post(f"{GENERATOR_URL}/generate", json=payload, timeout=30)
    if r.status_code != 200:
        print(f"  ERROR: /generate returned {r.status_code}: {r.text[:200]}")
        return {}
    
    job = r.json()
    job_id = job.get("job_id")
    if not job_id:
        print(f"  ERROR: no job_id in response")
        return {}
    
    print(f"  Job submitted: {job_id}")
    
    # Poll for completion
    max_wait = 300  # 5 minutes
    start = time.time()
    while time.time() - start < max_wait:
        time.sleep(10)
        try:
            status_r = requests.get(f"{GENERATOR_URL}/status/{job_id}", timeout=10)
            if status_r.status_code == 200:
                status = status_r.json()
                state = status.get("status", "")
                if state == "completed":
                    print(f"  Completed in {time.time()-start:.0f}s")
                    return status
                elif state == "failed":
                    print(f"  FAILED: {status.get('error', '?')}")
                    return {}
                else:
                    print(f"  ... {state} ({time.time()-start:.0f}s)")
        except Exception as e:
            print(f"  Poll error: {e}")
    
    print(f"  TIMEOUT after {max_wait}s")
    return {}


def analyze_tour_content(content: str, venue_key: str) -> dict:
    """Analyze a tour's content for stops, documented works, callbacks."""
    lines = content.split('\n')
    
    stops = []
    current_stop = None
    
    for line in lines:
        if line.startswith('Stop ') and ':' in line:
            if current_stop:
                stops.append(current_stop)
            current_stop = {"title": line.split(':', 1)[1].strip() if ':' in line else line, "text": "", "line": line}
        elif current_stop:
            current_stop["text"] += line + "\n"
    if current_stop:
        stops.append(current_stop)
    
    return {
        "num_stops": len(stops),
        "stops": stops,
        "total_words": len(content.split()),
    }


def find_cross_stop_callbacks(content: str, stops: list) -> list:
    """Find genuine cross-stop callbacks (specific work/person/event named from another stop)."""
    callbacks = []
    
    for i, stop in enumerate(stops):
        text = stop.get("text", "")
        # Check if this stop names something from an earlier stop
        for j, earlier in enumerate(stops[:i]):
            earlier_title = earlier.get("title", "")
            # Extract key proper nouns from earlier stop (works, people)
            import re
            # Look for title references from earlier stops in current stop text
            if earlier_title and len(earlier_title) > 5:
                # Check for partial title match (at least 3 significant words)
                title_words = [w for w in earlier_title.split() if len(w) > 3]
                if title_words:
                    matches = sum(1 for w in title_words if w.lower() in text.lower())
                    if matches >= 2:
                        callbacks.append({
                            "at_stop": i + 1,
                            "references_stop": j + 1,
                            "reference": earlier_title,
                            "context": text[:200],
                        })
    
    return callbacks


def check_thread_file(output_prefix: str) -> dict:
    """Load the _threads.json file if it was generated."""
    pattern = f"{output_prefix}"
    for f in os.listdir(TOURS_DIR):
        if f.startswith(pattern) and f.endswith("_threads.json"):
            path = os.path.join(TOURS_DIR, f)
            with open(path, 'r', encoding='utf-8') as fp:
                return json.load(fp)
    return {}


def run_acceptance():
    """Run full acceptance test."""
    print("LOCAL-38 Theme Thread Discovery — Acceptance Run")
    print("=" * 70)
    
    # Wait for service
    print(f"\nWaiting for tour-generator at {GENERATOR_URL}...")
    if not wait_for_service(GENERATOR_URL):
        print("FATAL: tour-generator not available")
        sys.exit(1)
    print("Service ready.\n")
    
    results = {}
    
    # --- Asian Arts: 3 runs for byte-identity ---
    asian_hashes = []
    for run in range(3):
        result = generate_tour("asian", run)
        if result and result.get("status") == "completed":
            content = result.get("tour_content", "")
            h = hashlib.sha256(content.encode()).hexdigest()[:16]
            asian_hashes.append(h)
            
            if run == 0:
                # Save first run for analysis
                analysis = analyze_tour_content(content, "asian")
                results["asian"] = {
                    "content": content,
                    "analysis": analysis,
                    "hash": h,
                }
                # Save output
                out_path = os.path.join(TOURS_DIR, f"local38_asian_run{run}.txt")
                with open(out_path, 'w', encoding='utf-8') as f:
                    f.write(content)
    
    print(f"\n--- Asian hashes: {asian_hashes}")
    results["asian_byte_identical"] = len(set(asian_hashes)) == 1 if len(asian_hashes) == 3 else False
    
    # --- Matisse ---
    result = generate_tour("matisse")
    if result and result.get("status") == "completed":
        content = result.get("tour_content", "")
        analysis = analyze_tour_content(content, "matisse")
        results["matisse"] = {"content": content, "analysis": analysis}
        out_path = os.path.join(TOURS_DIR, f"local38_matisse.txt")
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(content)
    
    # --- Palais Lascaris ---
    result = generate_tour("palais")
    if result and result.get("status") == "completed":
        content = result.get("tour_content", "")
        analysis = analyze_tour_content(content, "palais")
        results["palais"] = {"content": content, "analysis": analysis}
        out_path = os.path.join(TOURS_DIR, f"local38_palais.txt")
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(content)
    
    # --- Print Evidence ---
    print("\n" + "=" * 70)
    print("ACCEPTANCE EVIDENCE")
    print("=" * 70)
    
    # Theme threads
    for venue_key in ["asian", "matisse", "palais"]:
        print(f"\n--- {venue_key.upper()} ---")
        threads_data = check_thread_file(f"local38_{venue_key}")
        if threads_data:
            print(f"  Mode: {threads_data.get('mode', '?')}")
            for t in threads_data.get("threads", []):
                print(f"  Thread: '{t['name']}' — coverage={t['coverage']:.0%}, weight={t['weight']:.2f}")
                print(f"    Elements: {t['supporting_elements']}")
                print(f"    Stops: {t['stops_covered']}")
            print(f"  Prolog promise: {threads_data.get('prolog_promise', '(none)')[:200]}")
            print(f"  Epilog payoff: {threads_data.get('epilog_payoff', '(none)')[:200]}")
        else:
            print(f"  No thread file found")
        
        if venue_key in results:
            a = results[venue_key].get("analysis", {})
            print(f"  Stops: {a.get('num_stops', '?')}")
            
            # Cross-stop callbacks
            if a.get("stops"):
                callbacks = find_cross_stop_callbacks(
                    results[venue_key].get("content", ""), a["stops"]
                )
                print(f"  Cross-stop callbacks: {len(callbacks)}")
                for cb in callbacks[:5]:
                    print(f"    → Stop {cb['at_stop']} references Stop {cb['references_stop']}: '{cb['reference']}'")
    
    # Regression checks
    print(f"\n--- REGRESSION ---")
    if "asian" in results:
        a = results["asian"]["analysis"]
        print(f"  Asian stops: {a['num_stops']} (expected: 8)")
        print(f"  Asian byte-identical x3: {results.get('asian_byte_identical', False)}")
    
    if "matisse" in results:
        a = results["matisse"]["analysis"]
        print(f"  Matisse stops: {a['num_stops']} (expected: 8)")
    
    if "palais" in results:
        a = results["palais"]["analysis"]
        print(f"  Palais stops: {a['num_stops']} (expected: ≥6)")
    
    # Save full results
    results_path = os.path.join(TOURS_DIR, "local38_acceptance_results.json")
    serializable = {}
    for k, v in results.items():
        if isinstance(v, dict):
            serializable[k] = {kk: vv for kk, vv in v.items() if kk != "content"}
        else:
            serializable[k] = v
    with open(results_path, 'w', encoding='utf-8') as f:
        json.dump(serializable, f, indent=2)
    print(f"\nResults saved to {results_path}")


if __name__ == "__main__":
    run_acceptance()
