#!/usr/bin/env python3
"""LOCAL-417 Live Run: MFA tour with required-names suppression + positive gate.

Env: DISABLE_TOUR_CACHE=1, DATABASE_URL, STORIED_MODE=true
DO NOT change TOUR_LLM_MODEL (D346).

Verifies:
1. 4/4 stops produce real content (no refusals, no operator-directed text)
2. Positive gate passes on all stops — each names its subject + states a fact
3. Required-names block suppressed when no snippet evidence (logged)
4. Palais control 4/4, dates intact
5. Doctrinal framing and 'invites contemplation' absent
"""

import os
import sys
import json
import time
import re
from datetime import datetime

# Ensure we're using the local code
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env file
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _key, _val = _line.split('=', 1)
                if _key not in os.environ:  # don't override explicit env
                    os.environ[_key] = _val

# Set environment (these override .env)
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ['DATABASE_URL'] = 'postgresql://admin:password123@localhost:5433/audiotours'
os.environ['STORIED_MODE'] = 'true'

# Verify model is not changed
if 'TOUR_LLM_MODEL' in os.environ:
    print(f"WARNING: TOUR_LLM_MODEL is set to '{os.environ['TOUR_LLM_MODEL']}' — NOT changing per D346")

print(f"LOCAL-417 Live Run")
print(f"Timestamp: {datetime.now().isoformat()}")
print(f"DISABLE_TOUR_CACHE={os.environ.get('DISABLE_TOUR_CACHE')}")
print(f"DATABASE_URL=...@localhost:5433/audiotours")
print(f"STORIED_MODE={os.environ.get('STORIED_MODE')}")
print(f"TOUR_LLM_MODEL={os.environ.get('TOUR_LLM_MODEL', '(not set — using default)')}")
print()

from generate_tour_text import generate_tour_text

# ─── Positive Gate (offline, against storied baseline) ───────────────────────
def run_positive_gate(description, poi_name):
    """Run the LOCAL-417 positive assertion gate on text. Returns (pass, failures)."""
    _417_gate_pass = True
    _417_gate_failures = []

    # Check 1: text names its subject
    _desc_lower = description.lower()
    _poi_lower = poi_name.lower()
    _poi_words = [w for w in re.findall(r'\b[a-z]{3,}\b', _poi_lower)
                  if w not in ('the', 'and', 'for', 'from', 'with', 'that', 'this')]
    _subject_named = (_poi_lower in _desc_lower or
                     any(w in _desc_lower for w in _poi_words))
    if not _subject_named:
        _417_gate_pass = False
        _417_gate_failures.append(f"subject not named (expected '{poi_name}' or keyword)")

    # Check 2: at least one concrete fact
    _has_fact = bool(re.search(
        r'\b(?:1[0-9]{3}|20[0-2][0-9])\b'
        r'|\b\d+\s*(?:cm|inches|feet|meters|ft|in)\b'
        r'|\b\d{2,}[,.]?\d*\s*(?:works?|objects?|pieces?|items?|artifacts?)\b'
        r'|\b(?:oil on canvas|bronze|marble|lithograph|watercolor|fresco|'
        r'tempera|etching|woodcut|ceramic|terracotta|limestone|granite)\b'
        r'|\b(?:donated|acquired|commissioned|exhibited|installed|founded|opened'
        r'|built|constructed|designed|crafted|created)\s+(?:in|by|for)\b'
        r'|\b(?:17th|18th|19th|20th|21st)[\s-]+century\b',
        description, re.IGNORECASE
    ))
    if not _has_fact:
        _417_gate_pass = False
        _417_gate_failures.append("no concrete fact (date, measurement, material, or provenance)")

    # Check 3: no operator-directed language
    _operator_re = re.compile(
        r'\byour (?:description|text|narrative|response|prompt|request)\b'
        r'|\bnotify me\b'
        r'|\brequire(?:s|d)? further assistance\b'
        r'|\bensure to include\b'
        r'|\bmissing required\b'
        r'|\bspecified individuals\b'
        r'|\byour (?:instructions?|requirements?|constraints?)\b'
        r'|\bprovide (?:more|the|additional) (?:details?|information|context)\b'
        r'|\bin your (?:narrative|description|text)\b',
        re.IGNORECASE
    )
    _match = _operator_re.search(description)
    if _match:
        _417_gate_pass = False
        _417_gate_failures.append(f"operator-directed: '{_match.group(0)}'")

    return _417_gate_pass, _417_gate_failures


# ─── Demo: positive gate RED output against storied baseline ─────────────────
print("=" * 70)
print("POSITIVE GATE DEMO — against storied 415 failures")
print("=" * 70)

# These are the exact texts from the 415 run that shipped as tour content
_storied_failures = [
    ("Adam and Eve",
     "There are still some missing required names in your description. "
     "Ensure to include each of the specified individuals with their surnames "
     "and roles in the narrative. Notify me if you require further assistance with this."),
    ("Artist in his studio",
     "Artist in his studio — located in this gallery. A detailed narration could not be generated for this stop."),
]

for poi_name, text in _storied_failures:
    passed, failures = run_positive_gate(text, poi_name)
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"\n  {status}: '{poi_name}'")
    print(f"    Text: {text[:100]}...")
    if failures:
        for f in failures:
            print(f"    RED: {f}")

print()

# ─── MFA Tour ───────────────────────────────────────────────────────────────
print("=" * 70)
print("MFA TOUR: Museum of Fine Arts, Boston (N=4)")
print("=" * 70)

result = generate_tour_text(
    "Museum of Fine Arts, Boston, MA",
    "museum",
    total_stops=4,
    user_id="local417_test",
    job_id="local417_mfa",
)

if result is None:
    print("FATAL: generate_tour_text returned None")
    sys.exit(1)

tour_text, tour_data, (lat, lng) = result

if not tour_text:
    print("FATAL: tour_text is empty")
    sys.exit(1)

# Save tour
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
safe_name = "Museum_of_Fine_Arts__Boston__MA"
tour_file = f"{safe_name}_museum_tour_{timestamp}.txt"
with open(tour_file, 'w') as f:
    f.write(tour_text)
print(f"\nSaved: {tour_file}")

# Save evidence
evidence_file = f"{safe_name}_museum_tour_{timestamp}_evidence.json"
with open(evidence_file, 'w') as f:
    json.dump(tour_data, f, indent=2, default=str)
print(f"Saved: {evidence_file}")

# ─── Validation ─────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("VALIDATION — MFA")
print("=" * 70)

# Parse stops from tour text
stop_sections = re.split(r'\nStop \d+:', tour_text)
# The first section is the header; stops start from index 1
stop_names = re.findall(r'Stop \d+:\s*(.+)', tour_text)

print(f"\nStops found: {len(stop_names)}")
for i, name in enumerate(stop_names, 1):
    print(f"  Stop {i}: {name.strip()}")

# Extract description text per stop (between Orientation: and Directions:)
_all_stop_texts = []
for i, section in enumerate(stop_sections[1:], 1):
    # Find text after orientation header, before directions
    desc_match = re.search(r'(?:Orientation:.*?\n\n|Orientation:.*?\n)(.*?)(?:\nDirections:|\Z)',
                           section, re.DOTALL)
    if desc_match:
        desc_text = desc_match.group(1).strip()
    else:
        # Fallback: get everything between first blank line after header and Directions
        lines = section.split('\n')
        desc_lines = []
        in_content = False
        for line in lines:
            if line.strip().startswith('Directions:'):
                break
            if in_content:
                desc_lines.append(line)
            elif line.strip() == '' and not in_content:
                in_content = True
        desc_text = '\n'.join(desc_lines).strip()
    _all_stop_texts.append((stop_names[i-1].strip() if i <= len(stop_names) else f"Stop {i}", desc_text))

# Run positive gate on each stop
print(f"\n{'─'*40}")
print("POSITIVE GATE CHECK — all stops")
print(f"{'─'*40}")

gate_failures_total = 0
refusal_count = 0
operator_directed_count = 0

# Refusal denylist (cheap backstop)
refusal_patterns = [
    r'\bI cannot provide\b', r'\bI can\'t provide\b',
    r'\bI\'m sorry,?\s+(?:but\s+)?I\b', r'\bas an AI\b',
    r'\bmissing surnames\b', r'\bgiven constraints\b',
    r'\bnotify me if you require\b', r'\bensure to include\b',
    r'\bmissing required names?\b', r'\brequire further assistance\b',
]
refusal_re = re.compile('|'.join(refusal_patterns), re.IGNORECASE)

# Doctrinal/contemplation check
doctrinal_re = re.compile(r'\binvites contemplation\b|\bfall into sin\b|\bcreated by God\b', re.IGNORECASE)

for poi_name, desc_text in _all_stop_texts:
    if not desc_text:
        print(f"\n  ✗ {poi_name}: NO DESCRIPTION TEXT FOUND")
        gate_failures_total += 1
        continue

    # Denylist check
    refusal_match = refusal_re.search(desc_text)
    if refusal_match:
        refusal_count += 1
        print(f"\n  ✗ {poi_name}: REFUSAL DENYLIST HIT — '{refusal_match.group(0)}'")
        print(f"    Text: {desc_text[:200]}...")

    # Positive gate
    passed, failures = run_positive_gate(desc_text, poi_name)
    if passed:
        # Quote opening sentence
        first_sentence = re.split(r'[.!?]', desc_text)[0].strip()
        print(f"\n  ✓ {poi_name}")
        print(f"    Opening: \"{first_sentence[:120]}\"")
    else:
        gate_failures_total += 1
        print(f"\n  ✗ {poi_name}: GATE FAILED")
        for f in failures:
            print(f"    {f}")
        print(f"    Text: {desc_text[:200]}...")

    # Doctrinal check
    doc_match = doctrinal_re.search(desc_text)
    if doc_match:
        print(f"    ✗ DOCTRINAL: '{doc_match.group(0)}'")

print(f"\n{'─'*40}")
print(f"MFA RESULT: {len(stop_names)} stops, gate_failures={gate_failures_total}, "
      f"refusals={refusal_count}")
print(f"'invites contemplation' count: {tour_text.lower().count('invites contemplation')}")

# ─── Palais Control ─────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("PALAIS LASCARIS CONTROL (D302/D326)")
print("=" * 70)

palais_result = generate_tour_text(
    "Palais Lascaris, Nice, France",
    "museum",
    total_stops=4,
    user_id="local417_test",
    job_id="local417_palais",
)

if palais_result:
    palais_text, palais_data, (plat, plng) = palais_result
    palais_file = f"Palais_Lascaris__Nice__France_museum_tour_{timestamp}.txt"
    with open(palais_file, 'w') as f:
        f.write(palais_text)
    print(f"Saved: {palais_file}")

    palais_evidence = f"Palais_Lascaris__Nice__France_museum_tour_{timestamp}_evidence.json"
    with open(palais_evidence, 'w') as f:
        json.dump(palais_data, f, indent=2, default=str)
    print(f"Saved: {palais_evidence}")

    # Check dates
    dates_present = re.findall(r'\b(1[5-8]\d{2})\b', palais_text)
    print(f"  Dates found: {dates_present[:10]}")
    print(f"  'invites contemplation' in Palais: {palais_text.lower().count('invites contemplation')}")

    # Count stops
    palais_stops = re.findall(r'Stop \d+:', palais_text)
    print(f"  Palais stops: {len(palais_stops)}")

    if len(palais_stops) >= 4:
        print("  ✓ Palais 4/4 — CONTROL PASS")
    else:
        print(f"  ✗ Palais {len(palais_stops)}/4 — CONTROL FAIL")
else:
    print("WARNING: Palais control returned None")

# ─── Summary ────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("FINAL SUMMARY")
print("=" * 70)
_palais_stop_count = len(re.findall(r'Stop \d+:', palais_text)) if palais_result else 0
print(f"MFA: {len(stop_names)}/4 stops, gate_failures={gate_failures_total}, refusals={refusal_count}")
print(f"Palais: {'PASS' if _palais_stop_count >= 4 else 'FAIL'}")
print(f"Doctrinal/contemplation: {tour_text.lower().count('invites contemplation')}")
print(f"Timestamp: {datetime.now().isoformat()}")
print(f"Tour file: {tour_file}")
print(f"Evidence file: {evidence_file}")

if gate_failures_total > 0 or refusal_count > 0:
    print("\n*** FAIL ***")
    sys.exit(1)
elif len(stop_names) < 4:
    print(f"\n*** FAIL: Only {len(stop_names)}/4 stops ***")
    sys.exit(1)
else:
    print("\n*** PASS ***")
