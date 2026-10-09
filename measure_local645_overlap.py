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
    out = os.path.join(HERE, 'LOCAL645_overlap_measurement.json')
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump({'grounded_call_map': {
            '3_stop_cut': grounded_calls_per_tour(3),
            '5_stop_cut': grounded_calls_per_tour(5),
            '3_stop_precap': grounded_calls_per_tour(3, pre_cap=True, leads_grounded=True),
            '5_stop_precap': grounded_calls_per_tour(5, pre_cap=True, leads_grounded=True),
        }, 'overlap': a}, fh, indent=2, ensure_ascii=False)
    print(f"\n    wrote {os.path.basename(out)}")
    print("=" * 78)


if __name__ == '__main__':
    main()
