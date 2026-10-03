#!/usr/bin/env python3
"""LOCAL-568 retry-yield parser (OFFLINE, read-only).

Reconstructs per-stop writer-loop trajectories from recorded logs.

Ground truth signals (every line is emitted by generate_tour_text.py):
  COST : "Stop N API call cost: $X (T tokens, model=M)"  -- ONE per attempt.
  RETRY: "[LOCAL-432] Stop N: STORY RETRY - story_count=C < 3 ... (attempt K/5)"
         -- emitted ONLY when the story-retry branch fires; annotates the
            attempt that just finished (K-1) with story_count=C.
         Other gates (LOCAL-393 word floor, LOCAL-391 beats, LOCAL-417 gate,
         LOCAL-98 metadata) also 'continue' the same loop WITHOUT a story_count
         line, so some attempts legitimately have an unknown story_count.
  WC   : "Stop N description word count: W words" -- loop ended; LAST attempt is
         KEPT (code: success return ships current attempt, not best-by-story).

Episode = one stop's full writer loop within one generation pass. Each COST
line opens/extends the current episode for that stop; a WC line closes it; a
new COST line after a WC (or an attempt counter that would exceed 5) opens a
new episode (next pass).

We attribute each COST to a sequential attempt index (1,2,3,...). When a RETRY
line follows a COST for the same stop, we attach its story_count to that
attempt and assert the attempt index matches K-1 (sanity).
"""
import re, json, os

COST_RE = re.compile(r'Stop (\d+) API call cost: \$([0-9.]+) \((\d+) tokens, model=([\w.-]+)\)')
RETRY_RE = re.compile(r'\[LOCAL-432\] Stop (\d+): STORY RETRY . story_count=(\d+) < 3, need (\d+) more, retrying \(attempt (\d+)/(\d+)\)')
WC_RE = re.compile(r'Stop (\d+) description word count: (\d+) words')
THRESHOLD = 3
MAX_ATTEMPTS = 5

def parse_log(path, tour, source):
    open_ep = {}       # stop -> episode
    episodes = []
    last_cost_attempt = {}  # stop -> index of attempt whose COST we just saw (awaiting verdict)

    def new_episode(stop):
        return {'tour': tour, 'source': source, 'stop': stop, 'attempts': []}

    with open(path, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            m = COST_RE.search(line)
            if m:
                stop = int(m.group(1))
                cost = float(m.group(2)); tokens = int(m.group(3)); model = m.group(4)
                ep = open_ep.get(stop)
                # start a new episode if none open, or if the open one already hit MAX
                if ep is None or len(ep['attempts']) >= MAX_ATTEMPTS:
                    if ep is not None:
                        episodes.append(ep)
                    ep = new_episode(stop)
                    open_ep[stop] = ep
                attempt_idx = len(ep['attempts']) + 1
                ep['attempts'].append({'attempt': attempt_idx, 'cost': cost,
                                       'tokens': tokens, 'model': model,
                                       'story_count': None, 'retry_reason': None})
                last_cost_attempt[stop] = attempt_idx
                continue
            m = RETRY_RE.search(line)
            if m:
                stop = int(m.group(1)); sc = int(m.group(2)); nextk = int(m.group(4))
                prevk = nextk - 1
                ep = open_ep.get(stop)
                if ep and ep['attempts']:
                    a = ep['attempts'][-1]
                    a['story_count'] = sc
                    a['retry_reason'] = 'story'
                    a['logged_attempt_num'] = prevk  # for sanity check
                continue
            m = WC_RE.search(line)
            if m:
                stop = int(m.group(1)); wc = int(m.group(2))
                ep = open_ep.get(stop)
                if ep and ep['attempts']:
                    ep['attempts'][-1]['final_word_count'] = wc
                    ep['attempts'][-1]['is_final'] = True
                    episodes.append(ep)
                    del open_ep[stop]
                continue
    for stop, ep in list(open_ep.items()):
        if ep['attempts']:
            episodes.append(ep)
    return episodes

def summarize(ep):
    atts = ep['attempts']
    sc_by_att = {a['attempt']: a['story_count'] for a in atts}
    final = atts[-1]
    terminated_clean = final.get('is_final', False)
    n = len(atts)
    # first attempt with observed story_count >= 3
    first_meet = None
    for a in atts:
        if a['story_count'] is not None and a['story_count'] >= THRESHOLD:
            first_meet = a['attempt']; break
    # Inference: if the loop terminated cleanly (WC line) at attempt < 5 and the
    # last attempt had an UNKNOWN story_count, the only clean exit from the
    # story-retry branch is story_count >= 3. So the final attempt met threshold.
    final_inferred = None
    if first_meet is None and terminated_clean and final['attempt'] < MAX_ATTEMPTS \
       and final['story_count'] is None:
        # But only infer if the PRIOR attempt fired a story retry (i.e. the loop
        # was in story-retry territory). Otherwise the stop may have never been
        # short at all (terminated for another reason).
        prior_story = any(a['retry_reason'] == 'story' for a in atts[:-1])
        if prior_story:
            first_meet = final['attempt']
            final_inferred = THRESHOLD
            sc_by_att[final['attempt']] = THRESHOLD
    reached5_short = terminated_clean and final['attempt'] >= MAX_ATTEMPTS and first_meet is None \
                     and any(a['retry_reason'] == 'story' for a in atts)
    total_cost = sum(a['cost'] for a in atts if a['cost'] is not None)
    story_retry_count = sum(1 for a in atts if a['retry_reason'] == 'story')
    return {
        'tour': ep['tour'], 'source': ep['source'], 'stop': ep['stop'],
        'num_attempts': n,
        'story_count_by_attempt': sc_by_att,
        'final_count_inferred_ge3': final_inferred is not None,
        'first_attempt_meeting_threshold': first_meet if first_meet else 'never',
        'reached_attempt_5_still_short': bool(reached5_short),
        'story_retry_fired_count': story_retry_count,
        'cost_by_attempt': {a['attempt']: round(a['cost'],4) if a['cost'] is not None else None for a in atts},
        'writer_cost_total': round(total_cost, 4),
        'final_word_count': final.get('final_word_count'),
        'terminated_clean': terminated_clean,
    }

if __name__ == '__main__':
    curated = '/tmp/local568_curated'
    labelmap = {
        '560__palais_lascaris.log': ('palais_lascaris', 'local560_recordings'),
        '560__chart_house.log': ('chart_house', 'local560_recordings'),
        '563__lascaris_run1.log': ('palais_lascaris', 'local563_run1'),
        '563__lascaris_run2.log': ('palais_lascaris', 'local563_run2'),
        '563__logan_run1.log': ('logan_airport', 'local563_run1'),
        '563__logan_run2.log': ('logan_airport', 'local563_run2'),
        '566__palais_before.log': ('palais_lascaris', 'local566_before'),
        '566__palais_after.log': ('palais_lascaris', 'local566_after'),
        '566__logan_before.log': ('logan_airport', 'local566_before'),
        '566__logan_after.log': ('logan_airport', 'local566_after'),
    }
    extra = [('/tmp/local568_src/local566/LOCAL518_museum_of_fine_arts_boston_ma.log', 'MFA_boston', 'local566_LOCAL518')]
    jobs = []
    for fn, (tour, src) in labelmap.items():
        p = os.path.join(curated, fn)
        if os.path.exists(p):
            jobs.append((p, tour, src))
    for p, tour, src in extra:
        if os.path.exists(p):
            jobs.append((p, tour, src))

    all_eps = []
    for p, tour, src in jobs:
        all_eps.extend(parse_log(p, tour, src))

    all_summ = [summarize(e) for e in all_eps]
    retried = [s for s in all_summ if s['num_attempts'] >= 2]
    out = {
        'episodes_all': all_summ,
        'episodes_retried': retried,
        'counts': {'total_episodes': len(all_summ), 'retried_episodes': len(retried)}
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
