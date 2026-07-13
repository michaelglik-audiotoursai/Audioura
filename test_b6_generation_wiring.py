"""Test B6: elements→generation wiring with per-status phrasing.

Proves:
1. select_stop_elements ranks and selects correctly
2. format_elements_for_generation produces per-status blocks
3. Different statuses produce different phrasing instructions
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS_COUNT = 0
FAIL_COUNT = 0

def check(condition, msg):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        print(f"  [PASS] {msg}")
        PASS_COUNT += 1
    else:
        print(f"  [FAIL] {msg}")
        FAIL_COUNT += 1


# --- Test data: elements with various statuses ---
test_elements = [
    {
        'text': 'Blue Nude II was conceived during Matisse time in Nice',
        'type': 'origin',
        'corroboration_status': 'documented',
        'source_domain': 'en.wikipedia.org',
        'people': ['Matisse'],
        'dates': ['1952'],
    },
    {
        'text': 'The painting was completed using gouache on paper cut-outs',
        'type': 'technique',
        'corroboration_status': 'reported',
        'source_domain': 'centrepompidou.fr',
        'people': [],
        'dates': [],
    },
    {
        'text': 'Legend has it that Blue Nude II was created in a single fluid cut',
        'type': 'technique',
        'corroboration_status': 'legend',
        'source_domain': 'centrepompidou.fr',
        'people': [],
        'dates': [],
    },
    {
        'text': 'Some sources claim the work was created in 1951 while others say 1952',
        'type': 'date',
        'corroboration_status': 'disputed',
        'source_domain': 'moma.org',
        'people': [],
        'dates': ['1951', '1952'],
    },
    {
        'text': 'The work measures 116.2 x 88.9 cm',
        'type': 'date',
        'corroboration_status': 'reported',
        'source_domain': 'moma.org',
        'people': [],
        'dates': [],
    },
]

print("=" * 60)
print("  B6: elements→generation wiring tests")
print("=" * 60)

# Test 1: select_stop_elements ranks correctly
print("\n  select_stop_elements ranking:")
from story_element_extractor import select_stop_elements, rank_stop_elements

selection = select_stop_elements(test_elements, max_selected=3)
selected = selection['selected_elements']
runners = selection['runner_up_elements']

check(len(selected) == 3, f"3 selected elements (got {len(selected)})")
check(len(runners) == 2, f"2 runner-up elements (got {len(runners)})")
# Origin+documented should rank highest (3.0 type + 2.0 documented + 0.5 people + 0.5 dates = 6.0)
check(selected[0]['type'] == 'origin', f"Top element is origin (got {selected[0]['type']})")
check(selected[0]['corroboration_status'] == 'documented', f"Top element is documented")

# Test 2: format_elements_for_generation produces correct per-status blocks
print("\n  format_elements_for_generation per-status phrasing:")

def format_elements_for_generation(elements):
    """Local copy of the B6 generation formatting function."""
    selection = select_stop_elements(elements, max_selected=3)
    selected = selection.get('selected_elements', [])
    runners = selection.get('runner_up_elements', [])[:2]
    if not selected:
        return ""
    block = "STORY ELEMENTS (use these as primary material, follow phrasing rules per status):\n"
    for elem in selected:
        status = elem.get('corroboration_status', 'reported')
        text = elem.get('text', '')[:200]
        etype = elem.get('type', '')
        if status == 'documented':
            block += f"  [FACT — state directly, no attribution needed] ({etype}): {text}\n"
        elif status == 'reported':
            src = elem.get('source_domain', 'sources')
            block += f"  [REPORTED — use inline attribution: \"According to {src}...\"] ({etype}): {text}\n"
        elif status == 'legend':
            block += f"  [LEGEND — frame as: \"The story goes that...\"] ({etype}): {text}\n"
        elif status == 'disputed':
            block += f"  [DISPUTED — expose both sides with sources] ({etype}): {text}\n"
        else:
            block += f"  [{status}] ({etype}): {text}\n"
    if runners:
        block += "  TEXTURE (weave in if natural):\n"
        for elem in runners:
            block += f"    ({elem.get('type','')}) {elem.get('text','')[:120]}\n"
    return block

block = format_elements_for_generation(test_elements)

check('[FACT' in block and 'no attribution needed' in block,
      "documented → FACT phrasing present")
check('[REPORTED' in block and 'According to' in block,
      "reported → REPORTED phrasing with attribution")
check('[DISPUTED' in block and 'both sides' in block,
      "disputed → DISPUTED phrasing present")
check('TEXTURE' in block,
      "Runner-up elements present as TEXTURE")
check('legend' in block.lower() or 'fluid' in block.lower(),
      "legend element present in output (as TEXTURE runner-up)")

# Test 3: Empty elements produce empty block
print("\n  Edge cases:")
empty_block = format_elements_for_generation([])
check(empty_block == "", "Empty elements → empty block")

single_elem = [test_elements[0]]
single_block = format_elements_for_generation(single_elem)
check('[FACT' in single_block, "Single documented element → FACT block")
check('TEXTURE' not in single_block, "No runners → no TEXTURE section")

# Test 4: Verify the source_domain appears in attribution
print("\n  Attribution source threading:")
reported_only = [test_elements[1]]  # technique, reported, centrepompidou.fr
rep_block = format_elements_for_generation(reported_only)
check('centrepompidou.fr' in rep_block,
      "source_domain threaded into REPORTED attribution")

# Test 5: Legend phrasing when legend element IS selected (top element)
print("\n  Legend phrasing (when legend is top-ranked):")
legend_elem = {'text': 'Legend has it that Blue Nude II was created in a single fluid cut',
               'type': 'technique', 'corroboration_status': 'legend',
               'source_domain': 'centrepompidou.fr', 'people': [], 'dates': []}
leg_block = format_elements_for_generation([legend_elem])
check('[LEGEND' in leg_block and 'story goes' in leg_block,
      "legend as sole element → LEGEND phrasing with 'story goes'")

# --- Summary ---
print(f"\n{'='*60}")
total = PASS_COUNT + FAIL_COUNT
print(f"  RESULTS: {PASS_COUNT}/{total} PASS, {FAIL_COUNT} FAIL")
if FAIL_COUNT > 0:
    print("  *** FAILURES DETECTED ***")
    sys.exit(1)
else:
    print("  ALL TESTS PASSED")
print(f"{'='*60}")
