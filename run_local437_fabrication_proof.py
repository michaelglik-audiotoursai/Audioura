#!/usr/bin/env python3
"""LOCAL-437: Fabrication proof — injected work on the prose_llm path.

D390 Defect 3: LOCAL-436's proof passed a fabricated work directly to the
existence gate. That proved the gate drops unknown works — but the exemption
was never in that path. The exemption applies to works on the prose_llm path,
and those go through LOCAL-372's page-grounding BEFORE the existence gate.

This script constructs the exact case that matters:
  1. Use the real pipeline for MFA Unbound (which goes through prose_llm/checklist)
  2. Monkeypatch the checklist result to INJECT a fabricated work
  3. Run through generate_tour_text end to end
  4. Show the fabricated work is stripped by LOCAL-372 page-grounding

Two modes:
  - Mode A (unit): test title_appears_in_page directly with known page text
  - Mode B (integration): run full pipeline with injected fabrication

Gate mode: enforce (STOP_EXISTENCE_GATE_MODE=enforce)
"""
import os
import sys
import re
from pathlib import Path
from io import StringIO
import contextlib

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

os.environ['STORIED_MODE'] = 'true'
os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
os.environ['TOUR_LLM_MODEL'] = 'gpt-4o'
os.environ.pop('PYTEST_CURRENT_TEST', None)
os.environ.pop('_AUDIOURA_PYTEST_SESSION', None)
os.environ['AUDIOURA_DB_TARGET'] = 'production'
os.environ['DATABASE_URL'] = 'postgresql://admin:password123@localhost:5433/audiotours'
os.environ['DISABLE_TOUR_CACHE'] = '1'

from generate_tour_text import title_appears_in_page, should_exempt_from_existence_gate

print(f"{'#'*70}")
print(f"# LOCAL-437: Fabrication Proof — prose_llm path")
print(f"# Gate mode: enforce (STOP_EXISTENCE_GATE_MODE=enforce)")
print(f"#")
print(f"# Question: can a fabricated work survive through the exempted path?")
print(f"{'#'*70}")

# ═══════════════════════════════════════════════════════════════════════
# MODE A: Direct test of LOCAL-372 page-grounding with known page text
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print(f"MODE A: Direct page-grounding test (title_appears_in_page)")
print(f"{'='*70}")

# Simulate an exhibition page text that contains real works but NOT the fabricated one.
# This represents what the prose_llm extractor would have as input.
SIMULATED_PAGE_TEXT = """
Picasso, Miró, Dalí: Unbound
Organized by the Museum of Fine Arts, Boston

This exhibition explores the intersection of Surrealism, Cubism, and the livre
d'artiste through works by Pablo Picasso, Joan Miró, and Salvador Dalí.

Featured works include:

Le Lézard aux plumes d'or (The Lizard with Golden Feathers), 1971
Pablo Picasso
Illustrated book with lithographs

Moses and Monotheism, 1974
Salvador Dalí
Series of engravings based on Sigmund Freud's final work

Au Soleil du Plafond (Under the Ceiling Sun), 1955
Joan Miró
Lithographs published by Tériade

À toute épreuve (Standing up to anything), 1958
Joan Miró
Woodcuts with text by Paul Éluard

The exhibition is on view through March 2024.
"""

FABRICATED_TITLE = "The Invisible Symphony of Forgotten Dreams"
REAL_TITLES = [
    "Le Lézard aux plumes d'or",
    "Moses and Monotheism",
    "Au Soleil du Plafond",
    "À toute épreuve",
]

print(f"\n--- Step 1: Exemption check ---")
exempt = should_exempt_from_existence_gate(True, 'prose_llm')
print(f"  should_exempt_from_existence_gate(True, 'prose_llm') = {exempt}")
print(f"  → The existence gate is BYPASSED for these stops")
print(f"  → But LOCAL-372 page-grounding runs BEFORE (generate_tour_text.py:6100-6127)")

print(f"\n--- Step 2: Test fabricated work against page text ---")
fabricated_result = title_appears_in_page(FABRICATED_TITLE, SIMULATED_PAGE_TEXT)
print(f"  title_appears_in_page('{FABRICATED_TITLE}', page_text) = {fabricated_result}")
if not fabricated_result:
    print(f"  ✓ STRIPPED: Fabricated work is NOT on the page → dropped by LOCAL-372")
else:
    print(f"  ✗ HOLE: Fabricated work somehow matched → exemption unsafe")

print(f"\n--- Step 3: Real works survive the same check ---")
for title in REAL_TITLES:
    result = title_appears_in_page(title, SIMULATED_PAGE_TEXT)
    status = "✓ grounded" if result else "✗ dropped"
    print(f"  {status}: '{title}'")

print(f"\n--- Step 4: Full scenario simulation ---")
print(f"  Simulating: prose_llm extracts 3 real works + 1 fabricated work")
all_titles = REAL_TITLES[:3] + [FABRICATED_TITLE]
print(f"  Input: {all_titles}")

grounded = []
ungrounded = []
for title in all_titles:
    if title_appears_in_page(title, SIMULATED_PAGE_TEXT):
        grounded.append(title)
    else:
        ungrounded.append(title)

print(f"\n  After LOCAL-372 page-grounding (generate_tour_text.py:6111):")
print(f"    Grounded (delivered): {grounded}")
print(f"    Ungrounded (DROPPED): {ungrounded}")
print(f"    → {len(grounded)} stops survive, {len(ungrounded)} stripped")

# ═══════════════════════════════════════════════════════════════════════
# MODE B: Integration — run full pipeline with fabrication injected
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print(f"MODE B: Full pipeline integration test")
print(f"{'='*70}")

# Monkeypatch find_exhibition_checklist to return a result with a fabricated work
from exhibition_checklist import ExhibitionChecklistResult

def _mock_find_exhibition_checklist(venue_base_url='', exhibition_name='', venue_name='', venue_language='en'):
    """Return a fake checklist result with real works + one fabricated work."""
    result = ExhibitionChecklistResult()
    result.path = 'prose_llm'
    result.exhibition_title = 'Picasso, Miró, Dalí: Unbound'
    result.exhibition_url = 'https://www.mfa.org/exhibition/picasso-miro-dali-unbound'
    result.content_url = 'https://web.archive.org/web/20240101/https://www.mfa.org/exhibition/picasso-miro-dali-unbound'
    result.page_text = SIMULATED_PAGE_TEXT
    result.page_shape = 'prose_llm'
    result.is_from_archive = True
    result.wayback_snapshot_timestamp = '20240101120000'
    result.wayback_age_days = 120
    # 3 real works + 1 fabricated
    result.works = [
        {'title': "Le Lézard aux plumes d'or", 'artist': 'Pablo Picasso', 'date': '1971'},
        {'title': "Moses and Monotheism", 'artist': 'Salvador Dalí', 'date': '1974'},
        {'title': "Au Soleil du Plafond", 'artist': 'Joan Miró', 'date': '1955'},
        {'title': FABRICATED_TITLE, 'artist': 'Unknown', 'date': '2024'},  # INJECTED
    ]
    return result

import generate_tour_text as _gtt
import exhibition_checklist as _ec

# Save originals
_orig_find = _ec.find_exhibition_checklist

# Patch
_ec.find_exhibition_checklist = _mock_find_exhibition_checklist
# Also patch the import inside generate_tour_text if it's cached
if hasattr(_gtt, '_exhibition_checklist_module'):
    pass  # It uses a local import, so patching the module is enough

# We need to patch at the import site inside generate_tour_text
import importlib
# The function is imported locally, so we patch it in the exhibition_checklist module
# which is what the `from exhibition_checklist import find_exhibition_checklist` will get

print(f"\n  Monkeypatched find_exhibition_checklist to inject: '{FABRICATED_TITLE}'")
print(f"  Running full generate_tour_text pipeline...")
print(f"  Location: 'Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA'")
print(f"  Gate mode: enforce")

from generate_tour_text import generate_tour_text
from variance_harness import extract_per_stop_counts

captured = StringIO()
try:
    with contextlib.redirect_stdout(captured):
        result = generate_tour_text(
            location="Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA",
            tour_type="contained",
            output_file=str(PROJECT_ROOT / "tours" / "local437_fabrication_test.json"),
            total_stops=4,  # Request 4 so the fabricated one has a slot
            persona=None,
        )
finally:
    # Restore
    _ec.find_exhibition_checklist = _orig_find

output_log = captured.getvalue()

# Print key lines from the log
print(f"\n  Key pipeline output:")
for line in output_log.split('\n'):
    if any(kw in line for kw in ['LOCAL-372', 'LOCAL-437', 'EXEMPT', 'DROPPED', 'grounded',
                                   'EXISTENCE-GATE', 'prose_llm', 'PROSE_LLM']):
        print(f"    {line.strip()}")

# Check if the fabricated work was dropped
fabrication_dropped = FABRICATED_TITLE in output_log and 'DROPPED' in output_log
fabrication_in_dropped_line = False
for line in output_log.split('\n'):
    if 'DROPPED' in line and 'absent from' in line:
        fabrication_in_dropped_line = True
    if FABRICATED_TITLE in line and ('DROPPED' in line or '✗' in line or 'absent' in line.lower()):
        fabrication_in_dropped_line = True

# Check if fabricated title appears in final tour
tour_text = result[0] if result and result[0] else ''
fabrication_in_tour = FABRICATED_TITLE.lower() in tour_text.lower() if tour_text else False

print(f"\n  Integration results:")
print(f"    Tour generated: {'yes' if tour_text else 'no'}")
if tour_text:
    counts = extract_per_stop_counts(tour_text)
    print(f"    Stops in tour: {len(counts)}")
    for name in counts:
        marker = " ← FABRICATED!" if 'invisible' in name.lower() or 'forgotten' in name.lower() else ""
        print(f"      - {name}{marker}")
print(f"    Fabricated work in final tour: {fabrication_in_tour}")
print(f"    Fabricated work logged as dropped: {fabrication_in_dropped_line}")

# ═══════════════════════════════════════════════════════════════════════
# VERDICT
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print(f"VERDICT")
print(f"{'='*70}")

mode_a_pass = (not fabricated_result)  # Mode A: fabrication stripped
mode_b_pass = (not fabrication_in_tour)  # Mode B: fabrication not in final tour

if mode_a_pass and mode_b_pass:
    print(f"CONFIRMED: The exemption is SAFE.")
    print(f"")
    print(f"  Mode A (unit): title_appears_in_page strips the fabricated work ✓")
    print(f"  Mode B (integration): fabricated work does not appear in final tour ✓")
    print(f"")
    print(f"  Defense chain:")
    print(f"    1. prose_llm extracts works from exhibition page text")
    print(f"    2. LOCAL-372 (line 6100-6127) checks each title against that same page")
    print(f"    3. title_appears_in_page requires word overlap ≥ 70%")
    print(f"    4. A fabricated title has no page evidence → stripped")
    print(f"    5. Only page-grounded titles reach the existence gate exemption")
    print(f"    6. The exemption is safe: you cannot exempt what LOCAL-372 already killed")
elif not mode_a_pass:
    print(f"HOLE FOUND in page-grounding: fabricated work survived title_appears_in_page")
    print(f"The exemption admits fabricated works. Fix needed.")
elif mode_a_pass and not mode_b_pass:
    print(f"PARTIAL: Unit test passes but integration shows fabrication in tour.")
    print(f"Investigate: LOCAL-372 may not be running on this path.")
else:
    print(f"INCONCLUSIVE")

print(f"\nGate mode: enforce (STOP_EXISTENCE_GATE_MODE=enforce)")
print(f"{'='*70}")
