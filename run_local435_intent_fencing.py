#!/usr/bin/env python3
"""LOCAL-435: Measure intent-parse fencing rate over ≥10 attempts.

Calls the GPT-4o intent analysis endpoint directly (same model, same prompt as
production) and records whether the response is fenced, what format it arrives in,
and whether strip_llm_json_fences recovers it.

This does NOT run the full tour pipeline — it isolates the single failure point
LOCAL-434 diagnosed: the JSON wrapping behavior of GPT-4o on the intent prompt.
"""
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

# --- Environment ---
_env_path = Path.home() / "Audioura" / ".env"
if _env_path.exists():
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v

os.environ['TOUR_LLM_MODEL'] = 'gpt-4o'

import requests
from generate_tour_text import strip_llm_json_fences

LOCATION = "Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA"
NUM_ATTEMPTS = 15  # More than the minimum 10 to have a clearer sample

API_KEY = os.environ.get('OPENAI_API_KEY')
if not API_KEY:
    print("ERROR: OPENAI_API_KEY not set")
    sys.exit(1)


def build_intent_prompt(user_request):
    """Reproduce the exact intent prompt from generate_tour_text.py."""
    return f'''Analyze this tour request and extract the key information:

Request: "{user_request}"

Please provide ONLY a JSON response with these fields:
{{
    "poi_type": "specific type of locations requested",
    "location": "geographic area",
    "theme_type": "BOOK/MOVIE/PRODUCT/STANDARD",
    "theme_name": "name of book, movie, or specific product if applicable",
    "requirements": "any specific criteria mentioned",
    "business_hours_relevant": true/false,
    "accessibility_mentioned": true/false,
    "needs_research": true/false,
    "venue_name": "The full official name of the institution ONLY when the ENTIRE tour is bounded by one specific building or campus. Return null if the tour spans a city, district, neighborhood, multiple venues, or any open-ended area.",
    "geographic_scope": "The most specific bounded area the tour must stay within.",
    "scope_precision": "BUILDING | CORRIDOR | DISTRICT | CITY",
    "transport_mode": "on_foot | animal | bike | vehicle | country_scale",
    "country_scope": "country name for country-scale tours, null otherwise"
}}'''


def call_intent_once(attempt_num):
    """Call the intent endpoint once and return diagnostic info."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    data = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": "You are a tour planning assistant. Respond only with valid JSON."},
            {"role": "user", "content": build_intent_prompt(LOCATION)}
        ],
        "temperature": 0,
        "max_tokens": 400
    }

    start = time.time()
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=headers,
        data=json.dumps(data)
    )
    elapsed = time.time() - start

    if response.status_code != 200:
        return {
            'attempt': attempt_num,
            'status': 'HTTP_ERROR',
            'http_code': response.status_code,
            'raw_response': response.text[:500],
            'elapsed': elapsed,
        }

    result = response.json()
    raw_text = result["choices"][0]["message"]["content"]

    # Classify the response format
    stripped = raw_text.strip()
    is_fenced = stripped.startswith('```')
    is_clean_json = stripped.startswith('{') or stripped.startswith('[')
    has_prose = not is_clean_json and not is_fenced

    # Try raw json.loads
    raw_parse_ok = False
    try:
        json.loads(raw_text)
        raw_parse_ok = True
    except json.JSONDecodeError:
        pass

    # Try with fence stripping
    cleaned = strip_llm_json_fences(raw_text)
    stripped_parse_ok = False
    parsed_venue = None
    try:
        parsed = json.loads(cleaned)
        stripped_parse_ok = True
        parsed_venue = parsed.get('venue_name')
    except json.JSONDecodeError:
        pass

    return {
        'attempt': attempt_num,
        'status': 'OK',
        'is_fenced': is_fenced,
        'is_clean_json': is_clean_json,
        'has_prose': has_prose,
        'raw_parse_ok': raw_parse_ok,
        'stripped_parse_ok': stripped_parse_ok,
        'venue_name': parsed_venue,
        'raw_response': raw_text,
        'elapsed': elapsed,
    }


def main():
    print(f"{'#'*70}")
    print(f"# LOCAL-435: Intent Parse Fencing Rate Measurement")
    print(f"# Location: {LOCATION}")
    print(f"# Model: gpt-4o, temperature=0")
    print(f"# Attempts: {NUM_ATTEMPTS}")
    print(f"{'#'*70}\n")

    results = []

    for i in range(NUM_ATTEMPTS):
        print(f"Attempt {i+1}/{NUM_ATTEMPTS}...", end=" ", flush=True)
        r = call_intent_once(i + 1)
        results.append(r)

        if r['status'] == 'HTTP_ERROR':
            print(f"HTTP {r['http_code']}")
        else:
            fmt = "FENCED" if r['is_fenced'] else ("CLEAN" if r['is_clean_json'] else "PROSE")
            raw_ok = "✓" if r['raw_parse_ok'] else "✗"
            strip_ok = "✓" if r['stripped_parse_ok'] else "✗"
            venue = r.get('venue_name', 'None')
            print(f"format={fmt:7s} raw_parse={raw_ok} stripped_parse={strip_ok} "
                  f"venue={venue} ({r['elapsed']:.1f}s)")

        # Small delay to avoid rate limits
        if i < NUM_ATTEMPTS - 1:
            time.sleep(1.0)

    # --- Summary ---
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")

    ok_results = [r for r in results if r['status'] == 'OK']
    fenced = [r for r in ok_results if r['is_fenced']]
    prose = [r for r in ok_results if r['has_prose']]
    clean = [r for r in ok_results if r['is_clean_json']]
    raw_fails = [r for r in ok_results if not r['raw_parse_ok']]
    strip_fails = [r for r in ok_results if not r['stripped_parse_ok']]
    venue_extracted = [r for r in ok_results if r.get('venue_name')]

    print(f"Total attempts: {NUM_ATTEMPTS}")
    print(f"Successful calls: {len(ok_results)}")
    print(f"Format distribution:")
    print(f"  Clean JSON: {len(clean)}/{len(ok_results)}")
    print(f"  Fenced:     {len(fenced)}/{len(ok_results)}")
    print(f"  Prose wrap: {len(prose)}/{len(ok_results)}")
    print(f"Raw json.loads would fail: {len(raw_fails)}/{len(ok_results)}")
    print(f"After strip_llm_json_fences fails: {len(strip_fails)}/{len(ok_results)}")
    print(f"venue_name extracted: {len(venue_extracted)}/{len(ok_results)}")
    print(f"Fencing rate: {len(fenced)/len(ok_results)*100:.1f}%" if ok_results else "N/A")

    # Log raw responses for any that were fenced or failed
    if fenced:
        print(f"\n--- FENCED RESPONSES (raw) ---")
        for r in fenced:
            print(f"Attempt {r['attempt']}:")
            print(r['raw_response'][:300])
            print()
    if strip_fails:
        print(f"\n--- STILL FAILED AFTER STRIPPING ---")
        for r in strip_fails:
            print(f"Attempt {r['attempt']}:")
            print(r['raw_response'][:300])
            print()

    # Save artifact
    artifact = {
        'task': 'LOCAL-435',
        'measurement': 'intent_fencing_rate',
        'location': LOCATION,
        'model': 'gpt-4o',
        'temperature': 0,
        'num_attempts': NUM_ATTEMPTS,
        'num_ok': len(ok_results),
        'num_fenced': len(fenced),
        'num_prose': len(prose),
        'num_clean': len(clean),
        'fencing_rate': len(fenced) / len(ok_results) if ok_results else None,
        'raw_parse_failure_rate': len(raw_fails) / len(ok_results) if ok_results else None,
        'strip_parse_failure_rate': len(strip_fails) / len(ok_results) if ok_results else None,
        'venue_extraction_rate': len(venue_extracted) / len(ok_results) if ok_results else None,
        'results': results,
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    output_path = PROJECT_ROOT / "local435_intent_fencing_rate.json"
    with open(output_path, 'w') as f:
        json.dump(artifact, f, indent=2)
    print(f"\nArtifact saved: {output_path}")


if __name__ == '__main__':
    main()
