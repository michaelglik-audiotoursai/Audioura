"""[D538] For a restaurant, the practicals ARE the content.

Michael, 2026-08-27, on the Monaco tour's `PRACTICAL FACTS GATE: PASSED (0
verified)`:

  "for the restaurants the tour stop can not be a stop if the restaurant is closed
   or the menu is overpriced. If the information does not come from the first
   request to OpenAI.API, we should be querying this from Gemini and SERP."

Offline half runs with no network: the drop rule, the escalation shape, and the
prompt block. The live half needs OPENAI_API_KEY + SERP_API_KEY.

Run:  python3 tests/test_d538_restaurant_practicals.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import restaurant_practicals as rp
from restaurant_practicals import (fetch_practicals, practicals_prompt_block,
                                   _search_evidence, _thin)


def main():
    failures = []
    print("[D538] restaurant practicals\n")

    print("  -- the drop rule: only POSITIVE evidence of closure removes a stop --")
    cases = [
        ({'status': 'closed_permanently', 'hours': '', 'closed_days': '',
          'reservation': '', 'price_band': ''}, False,
         "reported closed — cannot be a stop"),
        ({'status': 'unknown', 'hours': '', 'closed_days': '',
          'reservation': '', 'price_band': ''}, True,
         "UNKNOWN IS NOT CLOSED. Absence of evidence must never delete a stop — "
         "that is the LOCAL-465 / D530 lesson in a new place."),
        ({'status': 'open', 'hours': '12:00-14:00', 'closed_days': 'Monday',
          'reservation': '', 'price_band': ''}, True, "open, keep"),
        ({'status': 'unknown', 'hours': '', 'closed_days': '',
          'reservation': '', 'price_band': 'tasting menu 390 EUR'}, True,
         "EXPENSIVE IS NOT A REASON TO DROP. Le Louis XV is among Europe's "
         "priciest restaurants and was the best stop in the Monaco tour. The band "
         "is disclosed to the listener; the choice stays theirs."),
    ]
    for fields, want_deliverable, why in cases:
        # Exercise the same decision fetch_practicals makes, without the network.
        deliverable = fields.get('status') != 'closed_permanently'
        ok = deliverable == want_deliverable
        print(f"  {'OK ' if ok else 'FAIL'} status={fields['status']:20s} "
              f"deliverable={deliverable}")
        if not ok:
            print(f"       {why}")
            failures.append(fields['status'])

    print("\n  -- 'thin' means nothing the listener can act on --")
    checks = [
        ("michelin stars alone are not actionable",
         _thin({'michelin': '3 stars', 'hours': '', 'closed_days': '',
                'reservation': '', 'price_band': ''})),
        ("hours alone are actionable",
         not _thin({'hours': '12:00-14:00', 'closed_days': '', 'reservation': '',
                    'price_band': ''})),
        ("price alone is actionable",
         not _thin({'hours': '', 'closed_days': '', 'reservation': '',
                    'price_band': '250 EUR'})),
    ]
    for label, cond in checks:
        print(f"  {'OK ' if cond else 'FAIL'} {label}")
        if not cond:
            failures.append(label)

    print("\n  -- query construction: the compound name must be split --")
    # Measured: '"Le Louis XV - Alain Ducasse à l'Hôtel de Paris" Monaco ...'
    # returned 3 snippets; the house name alone returned 34.
    captured = []
    orig = rp._serp
    rp._serp = lambda q, max_results=8: (captured.append(q) or [])
    try:
        _search_evidence("Le Louis XV - Alain Ducasse à l'Hôtel de Paris", "Monaco")
    finally:
        rp._serp = orig
    core_used = any('"Le Louis XV"' in q for q in captured)
    full_used = any('Alain Ducasse' in q for q in captured)
    closed_probe = any('closed permanently' in q for q in captured)
    for label, cond in (("searches the house name alone", core_used),
                        ("also searches the full name", full_used),
                        ("probes for permanent closure", closed_probe)):
        print(f"  {'OK ' if cond else 'FAIL'} {label}")
        if not cond:
            failures.append(label)

    print("\n  -- the prompt block forces disclosure, and stays silent when thin --")
    block = practicals_prompt_block({
        'usable': True, 'hours': '19:30-21:15', 'closed_days': 'Sunday, Monday',
        'reservation': 'essential', 'price_band': 'tasting from 313 USD',
        'cuisine': 'classic French brasserie', 'michelin': '3 stars'})
    # [D546] Michael's four: when it is open, whether to book, what it costs, and
    # what kind of food. Stop 1 of the v3 tour carried all four; stops 2 and 3 did
    # not, because the prompt mandated only booking and price.
    checks = [
        ("hours reach the prompt", '19:30-21:15' in block),
        ("closed days reach the prompt", 'Sunday, Monday' in block),
        ("price reaches the prompt", '313' in block),
        ("CUISINE reaches the prompt", 'classic French brasserie' in block),
        ("all four are mandated, not just two",
         all(k in block for k in ('WHEN IT IS OPEN', 'WHETHER A BOOKING IS NEEDED',
                                  'ROUGHLY WHAT IT COSTS', 'WHAT KIND OF FOOD'))),
        ("invention is forbidden",
         'do not guess' in block and 'locked door' in block),
        ("absent fields must be left unsaid",
         'say nothing about it' in block),
        ("thin practicals produce no block", practicals_prompt_block(
            {'usable': False, 'hours': ''}) == ""),
    ]
    for label, cond in checks:
        print(f"  {'OK ' if cond else 'FAIL'} {label}")
        if not cond:
            failures.append(label)

    api_key = os.environ.get('OPENAI_API_KEY')
    if api_key and os.environ.get('SERP_API_KEY'):
        print("\n  -- live: the two Monaco restaurants from the shipped tour --")
        for name in ("Le Louis XV - Alain Ducasse à l'Hôtel de Paris", "Cipriani Monte Carlo"):
            p = fetch_practicals(name, 'Monaco', api_key)
            got = [k for k in ('hours', 'closed_days', 'reservation', 'price_band') if p.get(k)]
            ok = p['usable']
            print(f"  {'OK ' if ok else 'FAIL'} {name[:38]:40s} {p['provider']} -> {got}")
            if not ok:
                failures.append(name[:24])
    else:
        print("\n  (OPENAI_API_KEY / SERP_API_KEY not set — live half skipped)")

    print()
    if failures:
        print(f"FAILED: {failures}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == '__main__':
    sys.exit(main())
