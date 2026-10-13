#!/usr/bin/env python3
"""measure_local674_pervenue.py — LOCAL-674 the GEMINI_PER_VENUE alternative arm.

LOCAL-645's lever for walking kept as an ALTERNATIVE arm (ticket deliverable 2):
instead of ONE grounded Gemini request PER STOP, issue ONE grounded request per
TOUR that asks about the whole area and all its stops together, then split the
answer per stop. For a 5-stop walking tour that is 1 grounded request (~$0.053)
instead of 5 (~$0.27).

For each walking request we call story_leads.venue_research(area, city, works=
[the 5 stops]) ONCE (use_cache=False, fresh), split its prose per stop, and score
each stop's material with the SAME walking-evidence scorer the per-stop harness
uses, so the arm is directly comparable to gemini / serper / serper_plus.

CAP via LOCAL674_MAX_USD (default $0.40 — one grounded request per request, 3
requests). Spend read from the meter jsonl.

    python3 measure_local674_pervenue.py
writes LOCAL674_pervenue_measurement.json
"""

# [LOCAL-678] Install the network paid-API meter for this HOST-run process. In a
# container sitecustomize (PYTHONPATH=/opt/meter) does this; on the host nothing
# does, so without this line every OpenAI/Gemini/Serper call this harness makes
# would be invisible to paid_api_calls. Must be the first thing we do, before any
# paid-call module is imported. Never breaks a run (install_meter fails open).
import os as _os678  # noqa: E402
import sys as _sys678  # noqa: E402
_sys678.path.insert(0, _os678.path.join(
    _os678.path.dirname(_os678.path.abspath(__file__)), "_meter"))
try:
    import meter_bootstrap as _meter_bootstrap  # noqa: F401,E402  (installs the meter)
except Exception as _meter_err:  # metering must never break a run
    print("[LOCAL-678] network meter unavailable (%s): "
          "paid calls from this host run will not be metered" % (_meter_err,))
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import story_leads  # noqa: E402
from measure_local674_walking import (REQUESTS, score_evidence, _log_offset,
                                       _read_meter_since, _spend_of, _rate_tag)


def main():
    max_usd = float(os.environ.get('LOCAL674_MAX_USD', '0.40'))
    print('=' * 78)
    print('LOCAL-674 — GEMINI_PER_VENUE alternative arm (1 grounded request / tour)')
    print(f'cap: ${max_usd:.2f}')
    print('=' * 78)

    start_off = _log_offset()
    results = []
    for req in REQUESTS:
        recs, _ = _read_meter_since(start_off)
        if _spend_of(recs) >= max_usd:
            print(f"[cap] stopping before {req['request']}")
            break
        area = req['request'].replace('Walking tour of', '').strip(' ,')
        print('\n' + '#' * 78)
        print(f"REQUEST: {req['request']}  — one grounded venue pass for {len(req['stops'])} stops")
        off = _log_offset()
        t0 = time.time()
        pv = story_leads.venue_research(area, req['city'], works=req['stops'],
                                        use_cache=False)
        secs = time.time() - t0
        arecs, _ = _read_meter_since(off)
        usd = _spend_of(arecs, kinds={'gemini'})
        works = (pv or {}).get('works', {}) or {}
        print(f"  one grounded request: {secs:.1f}s  ${usd:.5f}  "
              f"sources={len((pv or {}).get('sources', []))}  "
              f"err={pv.get('error') or 'none'}")
        row = {'request': req['request'], 'city': req['city'],
               'area': area, 'tour_usd': round(usd, 5),
               'tour_seconds': round(secs, 1),
               'sources': (pv or {}).get('sources', []), 'stops': {}}
        for place in req['stops']:
            material = works.get(place, '') or ''
            score = score_evidence(place, req['city'], material)
            row['stops'][place] = {'material': material,
                                   'has_material': bool(material.strip()),
                                   'score': score}
            print(f"    {place:28s} evidence={score['evidence_score']:2d} "
                  f"(dated_named={score['dated_named_facts']}, "
                  f"consequence={'Y' if score['has_consequence'] else 'n'}, "
                  f"material={'Y' if material.strip() else 'NONE'})")
        results.append(row)

    # summary — amortise the single tour request over its stops.
    all_recs, _ = _read_meter_since(start_off)
    n_stops = sum(len(r['stops']) for r in results) or 1
    tot_usd = sum(r['tour_usd'] for r in results)
    ev = sum(s['score']['evidence_score'] for r in results for s in r['stops'].values())
    dn = sum(s['score']['dated_named_facts'] for r in results for s in r['stops'].values())
    cq = sum(1 for r in results for s in r['stops'].values() if s['score']['has_consequence'])
    fl = sum(1 for r in results for s in r['stops'].values() if s['score']['filler'])
    nomat = sum(1 for r in results for s in r['stops'].values() if not s['has_material'])
    summary = {
        'rate_tag': _rate_tag(), 'n_requests': len(results), 'n_stops': n_stops,
        'arm': 'gemini_per_venue',
        'mean_evidence_score': round(ev / n_stops, 2),
        'mean_dated_named_facts': round(dn / n_stops, 2),
        'stops_with_consequence': cq, 'stops_filler': fl,
        'stops_no_material': nomat,
        'grounded_requests': len(results),
        'total_usd': round(tot_usd, 5),
        'usd_per_stop_amortised': round(tot_usd / n_stops, 5),
        'total_run_usd': round(_spend_of(all_recs), 5),
    }
    print('\n' + '=' * 78)
    print('SUMMARY (gemini_per_venue)')
    print('=' * 78)
    print(json.dumps(summary, indent=2))
    out = os.environ.get('LOCAL674_PV_OUT_JSON') or os.path.join(
        HERE, 'LOCAL674_pervenue_measurement.json')
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump({'summary': summary, 'results': results}, fh,
                  indent=2, ensure_ascii=False)
    print(f"\nwrote {out}")


if __name__ == '__main__':
    main()
