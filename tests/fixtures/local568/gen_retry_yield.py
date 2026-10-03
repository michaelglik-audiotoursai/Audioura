#!/usr/bin/env python3
"""Generate tests/fixtures/local568/retry_yield.json from parsed trajectories."""
import json, statistics as st, os
from collections import Counter

parsed = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'parsed_trajectories.json')))
# Story-retry episodes: LOCAL-432 fired at least once (museum stops that went short).
eps = [e for e in parsed['episodes_all'] if e['story_retry_fired_count'] >= 1]
THRESHOLD = 3

def scget(e, k):
    return e['story_count_by_attempt'].get(str(k))
def cget(e, k):
    return e['cost_by_attempt'].get(str(k))

# ---------- per-stop yield rows ----------
rows = []
for e in eps:
    sc = {k: scget(e, k) for k in range(1, 6)}
    rows.append({
        'tour': e['tour'],
        'source_run': e['source'],
        'stop': e['stop'],
        'num_attempts': e['num_attempts'],
        'story_count_after_attempt': {str(k): sc[k] for k in range(1, 6)},
        'first_attempt_meeting_threshold': e['first_attempt_meeting_threshold'],
        'reached_attempt_5_still_short': e['reached_attempt_5_still_short'],
        'final_count_inferred_ge3': e['final_count_inferred_ge3'],
        'writer_cost_by_attempt_usd': {str(k): cget(e, k) for k in range(1, 6) if cget(e, k) is not None},
        'writer_cost_total_usd': e['writer_cost_total'],
        'final_word_count': e['final_word_count'],
        'kept_attempt': 'last',  # per code: success return ships current (last) attempt
    })

N = len(eps)
meet = Counter(e['first_attempt_meeting_threshold'] for e in eps)

# ---------- marginal value per attempt ----------
marginal = {}
for k in range(2, 6):
    gains, costs, nran = [], [], 0
    for e in eps:
        if e['num_attempts'] >= k:
            nran += 1
            c = cget(e, k)
            if c is not None:
                costs.append(c)
            a, b = scget(e, k), scget(e, k - 1)
            if a is not None and b is not None:
                gains.append(a - b)
    marginal[str(k)] = {
        'p_threshold_first_met_at_k': round(meet.get(k, 0) / N, 4),
        'count_first_met_at_k': meet.get(k, 0),
        'mean_story_count_gain_vs_k_minus_1': round(st.mean(gains), 3) if gains else None,
        'n_gain_pairs_observed': len(gains),
        'mean_writer_cost_attempt_k_usd': round(st.mean(costs), 4) if costs else None,
        'n_episodes_ran_attempt_k': nran,
    }

# ---------- counterfactual caps (keep-best-so-far) ----------
def best_through(e, C):
    vals = [scget(e, k) for k in range(1, C + 1) if scget(e, k) is not None]
    return max(vals) if vals else None
def cost_through(e, C):
    return round(sum(cget(e, k) for k in range(1, C + 1) if cget(e, k) is not None), 4)

counterfactual = {}
for C in range(1, 6):
    bests, costs, meet3, nn = [], [], 0, 0
    for e in eps:
        nn += 1
        b = best_through(e, C)
        costs.append(cost_through(e, C))
        if b is not None:
            bests.append(b)
            if b >= THRESHOLD:
                meet3 += 1
    counterfactual[str(C)] = {
        'policy': 'keep-best-story_count-so-far',
        'mean_final_story_count': round(st.mean(bests), 3) if bests else None,
        'pct_stops_meeting_threshold': round(meet3 / nn, 4),
        'mean_writer_cost_per_stop_usd': round(st.mean(costs), 4),
        'mean_writer_cost_per_4stop_tour_usd': round(st.mean(costs) * 4, 4),
    }

# ---------- keep-last vs keep-best (the shipped-attempt bug) ----------
regress_episodes = 0
shipped_worse = 0
for e in eps:
    seq = [(k, scget(e, k)) for k in range(1, 6) if scget(e, k) is not None]
    # downward step anywhere
    if any(seq[i][1] < seq[i-1][1] for i in range(1, len(seq))):
        regress_episodes += 1
    # shipped (last observed) worse than an earlier peak
    if len(seq) >= 2 and not e['final_count_inferred_ge3']:
        best = max(v for _, v in seq)
        last = seq[-1][1]
        if last < best:
            shipped_worse += 1

summary = {
    'n_story_retry_stop_episodes': N,
    'threshold_min_story_sentences': THRESHOLD,
    'attempt_cap_today': 5,
    'by_tour': {t: sum(1 for e in eps if e['tour'] == t) for t in sorted(set(e['tour'] for e in eps))},
    'by_source_run': {s: sum(1 for e in eps if e['source'] == s) for s in sorted(set(e['source'] for e in eps))},
    'first_attempt_meeting_threshold_distribution': {
        '1': meet.get(1, 0), '2': meet.get(2, 0), '3': meet.get(3, 0),
        '4': meet.get(4, 0), '5': meet.get(5, 0), 'never': meet.get('never', 0),
    },
    'pct_never_meet_threshold_even_at_cap5': round(meet.get('never', 0) / N, 4),
    'regression_episodes_a_retry_scored_lower_than_prior': regress_episodes,
    'episodes_where_shipped_last_attempt_below_observed_peak': shipped_worse,
}

doc = {
    'issue': 'LOCAL-568',
    'title': 'Story-retry yield analysis (LOCAL-432 / LOCAL-417)',
    'generated_offline': True,
    'no_generation_calls': True,
    'method': {
        'description': (
            'Per-stop writer-loop trajectories reconstructed from recorded logs. '
            'Each "Stop N API call cost" line = one attempt; each '
            '"[LOCAL-432] STORY RETRY story_count=C (attempt K/5)" line annotates '
            'attempt K-1 with story_count=C; "description word count" ends the loop. '
            'The code keeps the LAST attempt on success (generate_tour_text.py:14979); '
            'resolve_final_description (line 5739) picks best by WORD COUNT, not '
            'story_count, and only on gate/API-failure fallback paths.'),
        'threshold': 'min_story_sentences = 3 (story_gate.py); retry fires while story_count < 3 and attempt < 5',
        'episode_definition': 'one stop within one generation pass; recorded logs contain ~2 passes per tour, each counted as an independent episode',
        'scope_note': 'LOCAL-432 only fires for tour_category == "museum". Non-museum tours (chart_house, logan_airport) retried for other gates and are EXCLUDED from story-retry yield.',
        'cost_source': 'per-attempt "Stop N API call cost" (priced at gpt-4o per D370); reconciles in magnitude with cost_record.breakdown.llm',
        'sources': [
            'origin/LOCAL-560-checker-model@d92bbb7:tests/fixtures/local560/recordings/palais_lascaris_nice.log',
            'origin/LOCAL-563-gemini-baseline@707e303:tests/fixtures/local563/runs/lascaris_run{1,2}.log',
            'origin/LOCAL-566-writer-cost@255f826:tests/fixtures/local566/measure/palais_{before,after}.log',
            'origin/LOCAL-566-writer-cost@255f826:LOCAL518_museum_of_fine_arts_boston_ma.log',
        ],
    },
    'summary': summary,
    'yield_table_per_stop': rows,
    'marginal_value_per_attempt': marginal,
    'counterfactual_caps_keep_best_so_far': counterfactual,
}

outdir = os.path.join(os.path.dirname(__file__), 'tests', 'fixtures', 'local568')
# When run from repo root this writes into the worktree.
outdir = 'tests/fixtures/local568'
os.makedirs(outdir, exist_ok=True)
outpath = os.path.join(outdir, 'retry_yield.json')
with open(outpath, 'w', encoding='utf-8') as fh:
    json.dump(doc, fh, indent=2, ensure_ascii=False)
    fh.write('\n')
print('wrote', outpath)
print('N =', N, '| never-meet =', summary['pct_never_meet_threshold_even_at_cap5'])
