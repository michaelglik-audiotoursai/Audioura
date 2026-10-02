#!/usr/bin/env python3
"""test_local219_paraphrase_symmetry.py — Paraphrase symmetry regression.

LOCAL-219 requirement: a claim's verdict must not change when a
non-load-bearing clause is added or removed. This test asserts that
both members of each paraphrase pair get the same verdict.

Each pair has:
  - A verbose phrasing (with incidental location/context)
  - A terse phrasing (same fact, minimal wording)
  - The corpus passage(s) to check against
  - The expected verdict (both should match)

Run:
    python3 tests/test_local219_paraphrase_symmetry.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import claim_check


# ─── Paraphrase pairs ────────────────────────────────────────────────────────
# Each tuple: (verbose, terse, passages, expected_verdict, description)

PARAPHRASE_PAIRS = [
    # Contradiction cases: wrong date, both phrasings should fire
    (
        'The museum opened in 1890 in Nice, France.',
        'The museum opened in 1890.',
        ['The museum opened on 21 June 1990 in Nice, France.'],
        'CONTRADICTED',
        'Museum opening date: incidental location removed',
    ),
    (
        'MAMAC was inaugurated in 1975 by the mayor.',
        'MAMAC was inaugurated in 1975.',
        ['MAMAC was inaugurated on 21 June 1990 by Jacques Médecin.'],
        'CONTRADICTED',
        'MAMAC inauguration: incidental agent removed',
    ),
    (
        'The Villa Ephrussi de Rothschild was built in 1920 by a wealthy banker.',
        'The Villa Ephrussi de Rothschild was built in 1920.',
        ['The Villa Ephrussi de Rothschild was built between 1905 and 1912.'],
        'CONTRADICTED',
        'Villa construction date: incidental attribution removed',
    ),
    (
        'Henri Matisse lived in Nice from 1920 until his death.',
        'Matisse lived in Nice from 1920.',
        ['Henri Matisse lived and worked in Nice from 1917 until his death in 1954.'],
        'CONTRADICTED',
        'Matisse residency start: incidental clause removed',
    ),
    # Correct facts: should be SUPPORTED in both phrasings
    (
        'The museum opened on 21 June 1990 in Nice, France.',
        'The museum opened in 1990.',
        ['The museum opened on 21 June 1990 in Nice, France.'],
        'SUPPORTED_PARAPHRASE',
        'Correct date: location detail removed',
    ),
    (
        'MAMAC was inaugurated on 21 June 1990 by Jacques Médecin.',
        'MAMAC was inaugurated in 1990.',
        ['MAMAC was inaugurated on 21 June 1990 by Jacques Médecin.'],
        'SUPPORTED_PARAPHRASE',
        'Correct date: agent detail removed',
    ),
    # Different subject: should be UNSUPPORTED regardless of verbosity
    (
        'The chapel was built in 1432 on the hilltop in Nice.',
        'The chapel was built in 1432.',
        ['The museum opened on 21 June 1990 in Nice, France.'],
        'UNSUPPORTED',
        'Different subject (chapel vs museum): location removed',
    ),
]


def run_tests():
    """Run all paraphrase symmetry tests."""
    print("=" * 70)
    print("LOCAL-219 PARAPHRASE SYMMETRY REGRESSION")
    print("=" * 70)
    print()

    passed = 0
    failed = 0
    symmetry_failures = 0

    for verbose, terse, passages, expected, desc in PARAPHRASE_PAIRS:
        r_v = claim_check.check_paragraph(verbose, '', '', passages)
        r_t = claim_check.check_paragraph(terse, '', '', passages)

        v_verdict = r_v['claims'][0]['verdict'] if r_v['claims'] else 'NO_CLAIMS'
        t_verdict = r_t['claims'][0]['verdict'] if r_t['claims'] else 'NO_CLAIMS'

        symmetric = (v_verdict == t_verdict)
        correct = (v_verdict == expected and t_verdict == expected)

        if symmetric and correct:
            status = '✓ PASS'
            passed += 1
        elif not symmetric:
            status = '✗ SYMMETRY FAIL'
            failed += 1
            symmetry_failures += 1
        else:
            status = '✗ WRONG VERDICT'
            failed += 1

        print(f"  {status}: {desc}")
        print(f"    Verbose: {v_verdict}")
        print(f"    Terse:   {t_verdict}")
        if not correct:
            print(f"    Expected: {expected}")
        print()

    print("=" * 70)
    print(f"  Passed: {passed}/{passed + failed}")
    print(f"  Failed: {failed} (symmetry failures: {symmetry_failures})")
    print()

    # Hard assertion: zero symmetry failures
    if symmetry_failures > 0:
        print("  ✗ REGRESSION: Paraphrase symmetry violated!")
        sys.exit(1)
    if failed > 0:
        print("  ✗ REGRESSION: Wrong verdict on paraphrase pair!")
        sys.exit(1)

    print("  ✓ All paraphrase pairs symmetric and correct")
    return 0


if __name__ == '__main__':
    sys.exit(run_tests())
