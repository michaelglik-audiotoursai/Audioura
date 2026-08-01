#!/usr/bin/env python3
"""LOCAL-95 Acceptance: SQ-S6b Dominant Story (Theme Threads).

Acceptance criteria from task:
1. Asian Arts Museum, N=8, three runs: distinct facts, callback count per run,
   internal score (if scorer can be run).
2. Callbacks present on at least half the stops in at least one run.
3. Distinct facts must not decrease against baseline (stdev~7 at n=3, report mean+spread).
4. Degradation: a thin-corpus venue must produce a sane tour, not a forced thread.
5. Cost ceiling: each tour under $1.30.

Usage:
    python run_local95_acceptance.py
"""
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime

import requests

GENERATOR_URL = "http://localhost:5000"
TOURS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tours")
os.makedirs(TOURS_DIR, exist_ok=True)

# Database connection for cache busting between runs
DB_URL = "postgresql://admin:password123@localhost:5432/audiotours"

# Venue configurations
VENUES = {
    "asian": {
        "location": "Musée des Arts Asiatiques, Nice",
        "tour_type": "museum tour",
        "total_stops": 8,
        "output_prefix": "local95_asian",
        "label": "Asian Arts Museum (N=8)",
    },
    "thin_corpus": {
        # A venue with thin corpus — should degrade gracefully
        # Using a location string that won't match any cached venue
        "location": "Musée International d'Art Naïf Anatole Jakovsky, Nice",
        "tour_type": "museum tour",
        "total_stops": 6,
        "output_prefix": "local95_thin",
        "label": "Musée Art Naïf Jakovsky (thin corpus degradation test)",
    },
}

NUM_ASIAN_RUNS = 3


def bust_tour_cache(location: str, tour_type: str, total_stops: int):
    """Delete the tour cache entry so the next generation is fresh."""
    import hashlib
    try:
        import psycopg2
        raw = f"{location.strip().lower()}|{tour_type.strip().lower()}|{total_stops}"
        key = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        conn = psycopg2.connect(DB_URL)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tour_cache WHERE cache_key = %s", (key,))
            conn.commit()
        conn.close()
    except Exception as e:
        print(f"  [cache bust] Warning: {e}")


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
        "total_stops": cfg["total_stops"],
    }

    print(f"\n{'='*70}")
    print(f"  Generating: {cfg['label']} (run {run_idx+1})")
    print(f"{'='*70}")

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
    max_wait = 420  # 7 minutes
    start = time.time()
    while time.time() - start < max_wait:
        time.sleep(10)
        try:
            status_r = requests.get(f"{GENERATOR_URL}/status/{job_id}", timeout=10)
            if status_r.status_code == 200:
                status = status_r.json()
                state = status.get("status", "")
                if state == "completed":
                    elapsed = time.time() - start
                    print(f"  Completed in {elapsed:.0f}s")
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


def count_distinct_facts(text: str) -> int:
    """Count distinct checkable facts in stop text.

    A fact = sentence with at least one: year/century, named person, measurement,
    named event, quoted artwork title.
    """
    sentences = re.split(r'(?<=[.!?])\s+', text)

    _year = re.compile(r'\b\d{3,4}\b|\b\d{1,2}(?:st|nd|rd|th)\s+century\b', re.IGNORECASE)
    _person = re.compile(r'\b[A-Z][a-z]+\s+(?:[A-Z][a-z]+|[IVXLCDM]+)\b')
    _number = re.compile(r'\b\d+(?:\.\d+)?\s*(?:m|km|ft|metres?|meters?|miles?|hectares?|acres?|kg|tons?|tonnes?|years?|centuries?)\b', re.IGNORECASE)
    _event = re.compile(r'\b(?:built|founded|opened|established|designed|created|completed|commissioned|inaugurated|renovated|destroyed|constructed)\s+(?:in|by|during|around)\b', re.IGNORECASE)
    _artwork = re.compile(r'\"[^\"]+\"|"[^"]+"|«[^»]+»', re.IGNORECASE)

    facts = set()
    for sent in sentences:
        sent = sent.strip()
        if not sent or len(sent) < 15:
            continue
        has_year = bool(_year.search(sent))
        has_person = bool(_person.search(sent))
        has_number = bool(_number.search(sent))
        has_event = bool(_event.search(sent))
        has_artwork = bool(_artwork.search(sent))

        if has_year or has_person or has_number or has_event or has_artwork:
            facts.add(sent[:100])

    return len(facts)


def parse_stops(content: str) -> list:
    """Parse tour text into stop dicts."""
    lines = content.split('\n')
    stops = []
    current_stop = None

    for line in lines:
        if line.startswith('Stop ') and ':' in line:
            if current_stop:
                stops.append(current_stop)
            title = line.split(':', 1)[1].strip() if ':' in line else line
            current_stop = {"title": title, "text": "", "raw_line": line}
        elif current_stop:
            current_stop["text"] += line + "\n"
    if current_stop:
        stops.append(current_stop)

    return stops


def find_cross_stop_callbacks(stops: list) -> list:
    """Find genuine cross-stop callbacks — a later stop mentioning material from an earlier one.

    This is the mechanism the SQ-S6b bonus rewards: a stop referring to another stop's
    material by name (specific work, person, event, or place from an earlier stop).
    
    Detection methods:
    1. Stop titles: if stop N mentions the title (or distinctive fragment) of an earlier stop
    2. Proper nouns: if stop N mentions a distinctive proper noun unique to an earlier stop
    """
    callbacks = []

    # Method 1: Title references — check if later stops mention earlier stop titles
    for i in range(1, len(stops)):
        text_i = stops[i].get("text", "").lower()
        for j in range(i):
            title_j = stops[j].get("title", "")
            # Check for substantial title fragments (at least 2 significant words)
            title_words = [w for w in title_j.split() if len(w) > 3 and 
                          w.lower() not in {'stop', 'the', 'this', 'musée', 'museum'}]
            if len(title_words) >= 2:
                # Look for 2+ distinctive words from the title in the stop's text
                matches = sum(1 for w in title_words if w.lower() in text_i)
                if matches >= 2:
                    callbacks.append({
                        "at_stop": i + 1,
                        "references_stop": j + 1,
                        "reference": title_j,
                        "method": "title_reference",
                    })
            # Also try the full title as a substring (for quoted references like "La danse cosmique de Ganesh")
            elif title_j and len(title_j) > 10 and title_j.lower() in text_i:
                callbacks.append({
                    "at_stop": i + 1,
                    "references_stop": j + 1,
                    "reference": title_j,
                    "method": "title_substring",
                })

    # Method 2: Thread entity references — a named entity (person, architect, donor)
    # that first appears in an earlier stop and is referenced again in a later stop.
    # This is the primary mechanism of the SQ-S6b cross-stop correlation bonus.
    _proper_noun_re = re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b')
    stop_proper_nouns = []
    for stop in stops:
        # Only use the actual text content (not across paragraph boundaries)
        text = stop.get("text", "")
        # Find proper nouns per sentence/paragraph (not across newlines)
        nouns = set()
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            found = _proper_noun_re.findall(line)
            for n in found:
                # Filter: distinctive names only
                if (len(n) > 8 and 
                    '\n' not in n and
                    n.lower() not in {
                        'the museum', 'nice france', 'musee des', 'promenade des',
                        'asian arts', 'arts asiatiques', 'the statue', 'the buddha',
                        'the work', 'the artist', 'asian art', 'beautiful art',
                        'this museum', 'this piece', 'this work', 'stop tour',
                        'musée des', 'each stop', 'cultural heritage',
                        'spiritual significance', 'cultural significance',
                    }):
                    nouns.add(n)
        stop_proper_nouns.append(nouns)

    # Find entities that appear in multiple stops — these are thread callbacks
    entity_first_seen = {}  # entity → first stop index
    for idx, nouns in enumerate(stop_proper_nouns):
        for noun in nouns:
            if noun not in entity_first_seen:
                entity_first_seen[noun] = idx

    # A callback is when a later stop references an entity first seen in an earlier stop
    for i in range(1, len(stops)):
        for noun in stop_proper_nouns[i]:
            first = entity_first_seen.get(noun)
            if first is not None and first < i:
                callbacks.append({
                    "at_stop": i + 1,
                    "references_stop": first + 1,
                    "reference": noun,
                    "method": "thread_entity",
                })

    # Deduplicate: count unique (at_stop, references_stop) pairs
    seen_pairs = set()
    unique_callbacks = []
    for cb in callbacks:
        pair = (cb["at_stop"], cb["references_stop"])
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            unique_callbacks.append(cb)

    return unique_callbacks


def count_stops_with_callbacks(callbacks: list, total_stops: int) -> int:
    """Count how many stops have at least one callback."""
    stops_with = set(cb["at_stop"] for cb in callbacks)
    return len(stops_with)


def analyze_run(content: str, venue_key: str, run_idx: int) -> dict:
    """Full analysis of a single tour run."""
    stops = parse_stops(content)
    total_words = len(content.split())

    # Per-stop facts
    per_stop_facts = []
    for stop in stops:
        facts = count_distinct_facts(stop["text"])
        per_stop_facts.append(facts)

    total_facts = sum(per_stop_facts)

    # Callbacks
    callbacks = find_cross_stop_callbacks(stops)
    stops_with_callbacks = count_stops_with_callbacks(callbacks, len(stops))

    return {
        "num_stops": len(stops),
        "total_words": total_words,
        "distinct_facts": total_facts,
        "per_stop_facts": per_stop_facts,
        "callbacks": callbacks,
        "callback_count": len(callbacks),
        "stops_with_callbacks": stops_with_callbacks,
        "stops_fraction_with_callbacks": stops_with_callbacks / max(1, len(stops)),
    }


def check_thread_artifacts(prefix: str) -> dict:
    """Load thread discovery artifacts if generated."""
    for f in os.listdir(TOURS_DIR):
        if prefix in f and f.endswith("_threads.json"):
            path = os.path.join(TOURS_DIR, f)
            with open(path, 'r', encoding='utf-8') as fp:
                return json.load(fp)
    return {}


def run_acceptance():
    """Run full LOCAL-95 acceptance test."""
    print("=" * 70)
    print("  LOCAL-95: SQ-S6b Dominant Story — Acceptance Test")
    print(f"  Time: {datetime.now().isoformat()}")
    print("=" * 70)

    # Wait for service
    print(f"\nWaiting for tour-generator at {GENERATOR_URL}...")
    if not wait_for_service(GENERATOR_URL):
        print("FATAL: tour-generator not available")
        sys.exit(1)
    print("Service ready.\n")

    # ================================================================
    # PHASE 1: Asian Arts Museum, N=8, 3 runs
    # ================================================================
    print("\n" + "=" * 70)
    print("  PHASE 1: Asian Arts Museum N=8, 3 runs")
    print("=" * 70)

    asian_runs = []
    asian_texts = []

    for run_idx in range(NUM_ASIAN_RUNS):
        # Bust tour cache to force fresh generation each run
        bust_tour_cache(VENUES["asian"]["location"], VENUES["asian"]["tour_type"],
                        VENUES["asian"]["total_stops"])
        result = generate_tour("asian", run_idx)
        if result and result.get("status") == "completed":
            content = result.get("tour_content", "")
            if not content:
                # Try to find the output file
                output_file = result.get("output_file", "")
                if output_file and os.path.exists(output_file):
                    with open(output_file, 'r', encoding='utf-8') as f:
                        content = f.read()

            if content:
                # Save to file
                out_path = os.path.join(TOURS_DIR, f"local95_asian_run{run_idx+1}.txt")
                with open(out_path, 'w', encoding='utf-8') as f:
                    f.write(content)

                analysis = analyze_run(content, "asian", run_idx)
                asian_runs.append(analysis)
                asian_texts.append(content)
                print(f"\n  Run {run_idx+1} analysis:")
                print(f"    Stops: {analysis['num_stops']}")
                print(f"    Distinct facts: {analysis['distinct_facts']}")
                print(f"    Callbacks: {analysis['callback_count']}")
                print(f"    Stops with callbacks: {analysis['stops_with_callbacks']}/{analysis['num_stops']}")
            else:
                print(f"  Run {run_idx+1}: No content received")
                asian_runs.append(None)
        else:
            print(f"  Run {run_idx+1}: Generation failed")
            asian_runs.append(None)

    # ================================================================
    # PHASE 2: Thin corpus degradation test
    # ================================================================
    print("\n" + "=" * 70)
    print("  PHASE 2: Thin corpus degradation test")
    print("=" * 70)

    bust_tour_cache(VENUES["thin_corpus"]["location"], VENUES["thin_corpus"]["tour_type"],
                    VENUES["thin_corpus"]["total_stops"])
    thin_result = generate_tour("thin_corpus", 0)
    thin_analysis = None
    thin_content = ""
    if thin_result and thin_result.get("status") == "completed":
        thin_content = thin_result.get("tour_content", "")
        if not thin_content:
            output_file = thin_result.get("output_file", "")
            if output_file and os.path.exists(output_file):
                with open(output_file, 'r', encoding='utf-8') as f:
                    thin_content = f.read()

        if thin_content:
            out_path = os.path.join(TOURS_DIR, "local95_thin_corpus.txt")
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(thin_content)
            thin_analysis = analyze_run(thin_content, "thin_corpus", 0)
            print(f"\n  Thin corpus analysis:")
            print(f"    Stops: {thin_analysis['num_stops']}")
            print(f"    Distinct facts: {thin_analysis['distinct_facts']}")
            print(f"    Callbacks: {thin_analysis['callback_count']}")

    # ================================================================
    # RESULTS SUMMARY
    # ================================================================
    print("\n\n" + "=" * 70)
    print("  RESULTS SUMMARY — LOCAL-95 SQ-S6b Dominant Story")
    print("=" * 70)

    # Asian Arts stats
    valid_runs = [r for r in asian_runs if r is not None]
    if valid_runs:
        facts_list = [r['distinct_facts'] for r in valid_runs]
        callbacks_list = [r['callback_count'] for r in valid_runs]
        stops_with_cb_list = [r['stops_with_callbacks'] for r in valid_runs]
        fractions_list = [r['stops_fraction_with_callbacks'] for r in valid_runs]

        mean_facts = sum(facts_list) / len(facts_list)
        spread_facts = max(facts_list) - min(facts_list) if len(facts_list) > 1 else 0

        print(f"\n  ASIAN ARTS MUSEUM (N=8, {len(valid_runs)} runs):")
        print(f"  {'─'*50}")
        for i, r in enumerate(valid_runs):
            print(f"    Run {i+1}: facts={r['distinct_facts']}, callbacks={r['callback_count']}, "
                  f"stops_w_callbacks={r['stops_with_callbacks']}/{r['num_stops']}")
        print(f"  {'─'*50}")
        print(f"    Mean distinct facts: {mean_facts:.1f} (spread: {spread_facts})")
        print(f"    Mean callbacks: {sum(callbacks_list)/len(callbacks_list):.1f}")
        print(f"    Max stops with callbacks: {max(stops_with_cb_list)} "
              f"(fraction: {max(fractions_list):.0%})")

        # Gate: callbacks on ≥ half the stops in at least one run
        gate_half = any(f >= 0.5 for f in fractions_list)
        print(f"\n    GATE (≥50% stops with callbacks in ≥1 run): {'PASS ✓' if gate_half else 'FAIL ✗'}")
        if not gate_half:
            print(f"      Best fraction: {max(fractions_list):.0%}")

        # Show callback details from best run
        best_run_idx = fractions_list.index(max(fractions_list))
        best_run = valid_runs[best_run_idx]
        if best_run["callbacks"]:
            print(f"\n    Callbacks in best run (run {best_run_idx+1}):")
            for cb in best_run["callbacks"][:8]:
                print(f"      Stop {cb['at_stop']} references Stop {cb['references_stop']}: \"{cb['reference']}\"")
    else:
        print("\n  ASIAN ARTS: NO VALID RUNS")

    # Thin corpus
    if thin_analysis:
        print(f"\n  THIN CORPUS DEGRADATION ({VENUES['thin_corpus']['label']}):")
        print(f"  {'─'*50}")
        print(f"    Stops: {thin_analysis['num_stops']}")
        print(f"    Distinct facts: {thin_analysis['distinct_facts']}")
        print(f"    Callbacks: {thin_analysis['callback_count']}")
        sane = thin_analysis['num_stops'] >= 4 and thin_analysis['distinct_facts'] >= 5
        print(f"    Sane tour (≥4 stops, ≥5 facts): {'PASS ✓' if sane else 'FAIL ✗'}")

    # Thread artifacts
    print(f"\n  THREAD ARTIFACTS:")
    for f in sorted(os.listdir(TOURS_DIR)):
        if "local95" in f and f.endswith("_threads.json"):
            path = os.path.join(TOURS_DIR, f)
            with open(path, 'r', encoding='utf-8') as fp:
                td = json.load(fp)
            mode = td.get("mode", "?")
            n_threads = len(td.get("threads", []))
            print(f"    {f}: mode={mode}, threads={n_threads}")
            for t in td.get("threads", []):
                print(f"      → \"{t.get('name', '?')}\": coverage={t.get('coverage', 0):.0%}, "
                      f"weight={t.get('weight', 0):.2f}")

    # Save full results as JSON
    results_path = os.path.join(TOURS_DIR, "local95_results.json")
    results_json = {
        "timestamp": datetime.now().isoformat(),
        "asian_runs": [r if r else {"status": "failed"} for r in asian_runs],
        "thin_corpus": thin_analysis,
        "summary": {
            "mean_distinct_facts": mean_facts if valid_runs else 0,
            "spread_distinct_facts": spread_facts if valid_runs else 0,
            "max_callbacks": max(callbacks_list) if valid_runs else 0,
            "max_stops_with_callbacks_fraction": max(fractions_list) if valid_runs else 0,
            "gate_half_stops_callbacks": gate_half if valid_runs else False,
        }
    }
    with open(results_path, 'w', encoding='utf-8') as f:
        json.dump(results_json, f, indent=2)
    print(f"\n  Results saved to: {results_path}")

    print("\n" + "=" * 70)
    print("  LOCAL-95 acceptance run complete")
    print("=" * 70)


if __name__ == "__main__":
    run_acceptance()
