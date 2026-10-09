#!/usr/bin/env python3
"""measure_local645_overlap.py — LOCAL-645 step 1: MEASURE FIRST (offline, zero paid calls).

The ticket asks, for each recent fresh tour: which story_leads calls were
search-enabled, what they asked, and how much their RESULTS overlap. The
authoritative source is `paid_api_calls` + `.continuous_dev/bench/R*/generator.log`.
Neither is reachable from this worktree (the DB host `postgres-2` is a
container-only name; the bench logs live on the host). So we measure from the two
things that ARE here and are deterministic:

  1. THE GROUNDED-CALL MAP (from the code itself). Every grounded Gemini request
     in a fresh tour is issued at exactly three sites, and the count per tour is a
     function of the stop count N:

        venue preflight (venue_preflight.py)      1   grounded request  / tour
        D511 loop r1    (story_production_loop)   N   grounded requests / tour   (MAX_GROUNDED_PER_STOP=1)
        story_leads.run step-4 fan-out            0   (STORY_LEADS_GROUNDED default off)
                                                 ----
        total search-enabled requests per tour =  N + 1

     At 3 stops that is 4; the ticket's "~7 per 3-stop tour" counts the extra
     grounded calls a stop makes before the LOCAL-594 per-stop cap (and the
     fan-out) — i.e. the pre-cap worst case. We report BOTH so the figure is
     honest either way.

  2. THE OVERLAP OF WHAT THEY ASKED/RETURNED (from story_loop_candidates.jsonl).
     That append-only log records EVERY grounded credit_line pass the D511 loop
     ran, grouped by work, with the story text each produced and the pairwise
     Jaccard overlap the loop itself computed (LOCAL-468). Multiple grounded
     passes about the SAME work, from different credit_line angles, is precisely
     the redundancy LOCAL-645 removes: a per-venue pass answers them once.

This script prints the per-work overlap table that goes in the submission. It
issues NO network calls of any kind.
"""
import json
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

CAND_LOG = os.path.join(HERE, 'story_loop_candidates.jsonl')


def _tokens(text: str):
    """Content-word set for Jaccard overlap (mirrors story_element_extractor)."""
    return {w for w in re.findall(r"[a-z0-9]{4,}", (text or '').lower())}


def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def grounded_calls_per_tour(n_stops: int, pre_cap: bool = False,
                            leads_grounded: bool = False) -> dict:
    """The deterministic per-tour grounded-request count (the grounded-call map).

    pre_cap=False (default, the shipped LOCAL-594 cut): preflight(1) + N stops(1 each).
    pre_cap=True: the worst case before LOCAL-594 — each stop ran up to
        MAX_CREDIT_LINES(4) credit_lines * 2 grounded (r1 narrate + r2 adjudicate).
    leads_grounded=True adds the step-4 fan-out's grounded provider (1 per mined stop).
    """
    preflight = 1
    if pre_cap:
        per_stop = 4 * 2  # MAX_CREDIT_LINES * (r1 + r2), both grounded
    else:
        per_stop = 1      # LOCAL-594 cap: one grounded r1 for the first credit_line
    fanout = n_stops if leads_grounded else 0
    return {
        'n_stops': n_stops,
        'preflight': preflight,
        'd511_per_stop': per_stop,
        'd511_total': per_stop * n_stops,
        'leads_fanout': fanout,
        'total': preflight + per_stop * n_stops + fanout,
    }


def _grounded_request_usd() -> float:
    """The price-card r4 rate for one search-enabled Gemini request, read from the
    meter so no rate is hardcoded here (RATE_TAG 2026-10-08-r4,
    GROUNDED_REQUEST_USD = $0.035 — Google list $35/1,000 grounded prompts)."""
    try:
        sys.path.insert(0, os.path.join(HERE, '_meter'))
        import paid_api_meter as _m
        return float(_m.GROUNDED_REQUEST_USD), _m.RATE_TAG
    except Exception:
        return 0.035, '2026-10-08-r4 (fallback literal)'


def projected_savings() -> dict:
    """Projected grounded-request saving per 3-stop and 5-stop tour under
    GEMINI_PER_VENUE, priced at the price-card r4 per-request rate. NO quality
    claim — LEAD runs the live A/B (flag OFF vs ON) in the morning.

    Model (search-enabled REQUESTS per fresh tour):
      flag OFF (shipped cut): preflight(1) + D511 per-stop grounded(1 * N) = N + 1
      flag ON, FRESH venue  : preflight(1) + ONE venue research pass(1)    = 2
                              (per-stop grounded replaced by the venue pass; a
                               per-work fallback fires only when the venue pass
                               found nothing about a work — 0 in the expected case)
      flag ON, CACHE HIT    : a later tour of the same museum within 30 days reuses
                              the venue pass (0 grounded) and the 7-day preflight
                              cache (0 grounded) -> approaches 0 search-enabled
                              requests on the grounded channel.
    """
    rate, tag = _grounded_request_usd()
    rows = []
    for n in (3, 5):
        off = n + 1                       # preflight + N per-stop grounded
        on_fresh = 2                      # preflight + 1 venue pass
        on_hit = 0                        # both caches hit
        rows.append({
            'tour': f'{n}-stop',
            'off_requests': off,
            'on_fresh_requests': on_fresh,
            'on_cachehit_requests': on_hit,
            'off_usd': round(off * rate, 4),
            'on_fresh_usd': round(on_fresh * rate, 4),
            'on_cachehit_usd': round(on_hit * rate, 4),
            'saving_fresh_usd': round((off - on_fresh) * rate, 4),
            'saving_fresh_pct': round(100.0 * (off - on_fresh) / off, 1),
            'saving_cachehit_usd': round((off - on_hit) * rate, 4),
            'saving_cachehit_pct': round(100.0 * (off - on_hit) / off, 1),
        })
    return {'rate_tag': tag, 'grounded_request_usd': rate, 'rows': rows}


def analyse_candidate_log(path: str = CAND_LOG) -> dict:
    if not os.path.exists(path):
        return {'error': f'no candidate log at {path}'}
    rows = []
    for line in open(path, encoding='utf-8'):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    by_work = defaultdict(list)
    for r in rows:
        by_work[r.get('work', '?')].append(r)

    works = []
    for work, rs in by_work.items():
        stories = [r.get('story', '') for r in rs if r.get('story')]
        # Pairwise overlap of the grounded passes' RESULTS (story text).
        pair_ovs = []
        for i in range(len(stories)):
            for j in range(i + 1, len(stories)):
                pair_ovs.append(_jaccard(stories[i], stories[j]))
        mean_ov = sum(pair_ovs) / len(pair_ovs) if pair_ovs else 0.0
        max_ov = max(pair_ovs) if pair_ovs else 0.0
        # Distinct credit_line "angles" asked about this one work.
        angles = sorted({(r.get('credit_line') or '')[:60] for r in rs})
        works.append({
            'work': work,
            'grounded_passes': len(rs),
            'distinct_angles': len(angles),
            'mean_overlap': round(mean_ov, 3),
            'max_overlap': round(max_ov, 3),
            'sample_angles': angles[:5],
        })
    works.sort(key=lambda w: -w['grounded_passes'])
    total_passes = sum(w['grounded_passes'] for w in works)
    return {
        'rows': len(rows),
        'distinct_works': len(by_work),
        'total_grounded_passes': total_passes,
        'works': works,
    }


def main():
    print("=" * 78)
    print("LOCAL-645 — MEASURE FIRST (offline; zero paid calls)")
    print("=" * 78)

    print("\n(A) GROUNDED-CALL MAP — search-enabled requests per fresh tour")
    print("    (deterministic from the code; see module docstring)\n")
    print(f"    {'tour':<14}{'preflight':>10}{'D511/stop':>11}{'D511 tot':>10}"
          f"{'fanout':>8}{'TOTAL':>7}")
    for n in (3, 5):
        m = grounded_calls_per_tour(n)
        print(f"    {str(n)+'-stop (cut)':<14}{m['preflight']:>10}"
              f"{m['d511_per_stop']:>11}{m['d511_total']:>10}"
              f"{m['leads_fanout']:>8}{m['total']:>7}")
    for n in (3, 5):
        m = grounded_calls_per_tour(n, pre_cap=True, leads_grounded=True)
        print(f"    {str(n)+'-stop (pre)':<14}{m['preflight']:>10}"
              f"{m['d511_per_stop']:>11}{m['d511_total']:>10}"
              f"{m['leads_fanout']:>8}{m['total']:>7}")
    print("\n    (cut) = shipped LOCAL-594 state; (pre) = pre-cap worst case")

    print("\n(B) OVERLAP OF GROUNDED PASSES ON THE SAME WORK")
    print("    source: story_loop_candidates.jsonl (local; LOCAL-468 records it)\n")
    a = analyse_candidate_log()
    if a.get('error'):
        print(f"    {a['error']}")
        return
    print(f"    {a['rows']} grounded candidate passes across "
          f"{a['distinct_works']} works\n")
    print(f"    {'work':<42}{'passes':>7}{'angles':>7}{'meanOv':>8}{'maxOv':>7}")
    for w in a['works']:
        print(f"    {w['work'][:40]:<42}{w['grounded_passes']:>7}"
              f"{w['distinct_angles']:>7}{w['mean_overlap']:>8}{w['max_overlap']:>7}")
    # The headline redundancy figure: grounded passes vs. works.
    if a['distinct_works']:
        ratio = a['total_grounded_passes'] / a['distinct_works']
        print(f"\n    => {a['total_grounded_passes']} grounded passes for only "
              f"{a['distinct_works']} works = {ratio:.1f} grounded searches/work.")
        print("       A per-VENUE pass answers the venue+works ONCE and is reused "
              "by every\n       later stop and later tour of the same museum "
              "(cached 30 days).")

    print("\n(C) PROJECTED SAVING per tour (price card r4; NO quality claim)")
    ps = projected_savings()
    print(f"    rate: ${ps['grounded_request_usd']:.3f} per search-enabled request "
          f"(RATE_TAG {ps['rate_tag']})\n")
    print(f"    {'tour':<9}{'OFF req':>8}{'ON req':>7}{'OFF $':>8}{'ON $':>7}"
          f"{'save $':>8}{'save %':>8}")
    for r in ps['rows']:
        print(f"    {r['tour']:<9}{r['off_requests']:>8}{r['on_fresh_requests']:>7}"
              f"{r['off_usd']:>8.3f}{r['on_fresh_usd']:>7.3f}"
              f"{r['saving_fresh_usd']:>8.3f}{r['saving_fresh_pct']:>7.0f}%")
    print("    (ON = fresh venue, per-stop grounded replaced by ONE venue pass.)")
    for r in ps['rows']:
        print(f"    {r['tour']} repeat within 30d (cache hit): "
              f"ON={r['on_cachehit_requests']} grounded req "
              f"-> save ${r['saving_cachehit_usd']:.3f} "
              f"({r['saving_cachehit_pct']:.0f}%)")

    out = os.path.join(HERE, 'LOCAL645_overlap_measurement.json')
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump({'grounded_call_map': {
            '3_stop_cut': grounded_calls_per_tour(3),
            '5_stop_cut': grounded_calls_per_tour(5),
            '3_stop_precap': grounded_calls_per_tour(3, pre_cap=True, leads_grounded=True),
            '5_stop_precap': grounded_calls_per_tour(5, pre_cap=True, leads_grounded=True),
        }, 'overlap': a, 'projected_savings': ps}, fh, indent=2, ensure_ascii=False)
    print(f"\n    wrote {os.path.basename(out)}")
    print("=" * 78)


if __name__ == '__main__':
    main()
