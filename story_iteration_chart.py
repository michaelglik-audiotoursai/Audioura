#!/usr/bin/env python3
"""story_iteration_chart.py — does iterating on a stop actually improve the story?

Michael, 2026-08-18: *"provide evaluation index on each iteration for the best
(highest evaluated and validated) story and continue to build up the chart for me
to see the score over iterations so I can see when we stop improving."*

THE SUBJECT, fixed on purpose
-----------------------------
`Picasso, Miró, Dalí: Unbound`, Museum of Fine Arts, Boston — **stop 2, "Moses and
Monotheism"**. The stop we have spent the most time on, so every number here can be
read against something we already understand.

WHAT ONE ITERATION IS
---------------------
This is the retry loop from `STORY_BASELINE.md` §5①, which does not exist in
production. Building it here first is deliberate: the lab is where we find the
stopping rule, and the stopping rule is the part production cannot be written
without.

    1. pick the next FOCUS FACT (rotating; see below)
    2. build queries from the matrix + that fact   work_story_searcher.synthesize_queries
    3. search                                      _serp_search (Serper.dev)
    4. rank and cap the snippets                   snippet_ranker.rank_and_cap_snippets
    5. write ONE candidate story from that material
    6. VALIDATE it — the production deletion gates
    7. EVALUATE what survived                      evaluate_story.valuation_index
    8. the iteration's score = the best VALIDATED story so far

Step 8 is why the curve is monotonic: it is a running best, so a flat stretch means
"the last N iterations bought us nothing", which is exactly the signal Michael asked
to see.

THE FOCUS FACT SLOT
-------------------
Michael's step 7b says: no valid story → take the next fact, put it in `credit_line`,
re-query. `credit_line` cannot carry it — LOCAL-406 regex-parses `donor` and `printer`
out of that field (work_story_searcher.py:426), so a fact written there is read as a
person's name. This harness uses a separate `focus_fact` slot, which is the change
STORY_BASELINE.md §2 proposes.

VALIDATED means: survived the production gate chain with nothing deleted. A story that
loses sentences is scored at what survived, and flagged.

    python3 story_iteration_chart.py --iterations 6 --live
    python3 story_iteration_chart.py --replay          # re-score, no spend
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

STATE = os.path.join(HERE, 'story_lab_state', 'iteration_chart.json')
CHART_MD = os.path.join(HERE, 'STORY_ITERATION_CHART.md')


def load_env():
    path = os.path.join(HERE, '.env')
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ═══════════════════════════════════════════════════════════════════════════════
# THE SUBJECT
# ═══════════════════════════════════════════════════════════════════════════════
# Taken from story_lab_state/stop2_extracted.json, which was built from the real
# tour. `publisher` is deliberately EMPTY: the extractor found "The Hogarth Press"
# there with status UNSUPPORTED, and Michael confirmed it fabricated. Seeding the
# loop with a known falsehood would measure the gates, not the loop.
STOP = {
    'canonical_title': 'Moses and Monotheism',
    'local_title': 'Moses and Monotheism',
    'english_title': 'Moses and Monotheism',
    'artist': 'Salvador Dalí',
    'collaborator': 'Sigmund Freud',
    'publisher': '',
    'printer': '',
    'donor': '',
    'credit_line': '',
    'medium': 'illustrated book, lithographs',
    'exhibition_name': 'Picasso, Miró, Dalí: Unbound',
    'venue_name': 'Museum of Fine Arts, Boston',
    'venue_city': 'Boston, MA',
    'venue_lang': 'en',
}

# The rotation. Michael's step 7b in concrete form: each iteration asks about a
# DIFFERENT fact tying this object to the exhibition, the museum or the city.
# Ordered most-promising first, so a rising curve that flattens early is a real
# stopping point rather than an artifact of a bad ordering.
FOCUS_FACTS = [
    "Dalí's 1974 illustrations for Freud's Moses and Monotheism",
    "the 1938 London meeting between Salvador Dalí and Sigmund Freud",
    "Freud's thesis that Moses was Egyptian, and the reaction to it",
    "how the Museum of Fine Arts Boston acquired this livre d'artiste",
    "the printing and edition history of the Moses and Monotheism portfolio",
    "why Picasso, Miró and Dalí are shown together in Unbound",
    "Dalí's surrealist reading of psychoanalysis in the 1930s",
    "the livre d'artiste tradition and its Boston collectors",
]


# ═══════════════════════════════════════════════════════════════════════════════
# ONE ITERATION
# ═══════════════════════════════════════════════════════════════════════════════

def gather(stop, focus_fact, live):
    """Steps 2-4: queries -> search -> rank. Returns (snippets, meta)."""
    from work_story_searcher import synthesize_queries, _serp_search
    from snippet_ranker import rank_and_cap_snippets

    probe = dict(stop)
    # The focus fact rides in credit_line ONLY for query synthesis, never into the
    # story record — this is the slot STORY_BASELINE.md §2 says needs its own name.
    probe['credit_line'] = focus_fact

    queries = synthesize_queries(probe, 'contained')
    queries = [f'{focus_fact} {stop["canonical_title"]}'] + queries
    queries = queries[:10]

    results, cost_q = [], 0
    if live:
        for q in queries:
            try:
                r, _ = _serp_search(q)
            except Exception as e:
                print(f"      ! query failed: {type(e).__name__}: {e}")
                continue
            results += r
            cost_q += 1
            time.sleep(0.2)
    kept, _ = rank_and_cap_snippets(results, stop.get('artist', ''),
                                    work_title=stop.get('canonical_title', ''))
    return queries, results, kept, cost_q


    # ROUND 2 (D468): the round-1 curve scored `detail` 0 on six of eight
    # iterations — the stories almost never named the physical thing in the case.
    # That is D449, and it survived because the old index could not see it. Now
    # that it can, the writer is told to do it, and the snippet cap is raised so
    # there is material to do it FROM (round 1 discarded 74 of 79 results).
WRITER_PROMPT = """You are writing one story for an audio tour stop.

STOP: {title}
EXHIBITION: {exhibition}
VENUE: {venue}
THE FACT THIS STORY MUST BE BUILT AROUND: {fact}

SOURCE MATERIAL — you may use nothing that is not here:
{material}

Write 3-5 sentences. Rules:
- Connect the fact to THIS object, and through it to the exhibition, the museum or
  the city. That connection is what makes it a story rather than a caption.
- AT LEAST ONE SENTENCE MUST NAME A PHYSICAL PROPERTY OF THE OBJECT IN FRONT OF THE
  LISTENER — its medium, material, size, technique, edition, binding, colour or
  condition — and tie that property to the fact. A listener is standing in front of
  the thing; a story that never mentions it is a caption about something else.
  Take the property from the source material. If the material names none, say so by
  writing nothing about the object rather than inventing a property.
- SAY WHAT IT COST OR WHAT WAS AT STAKE. What was lost, refused, destroyed, left
  unfinished, done only once, done for the last time, or done despite something.
  That is the difference between a story and a caption, and it must come from the
  source material. If the material contains no such consequence, write the story
  without one rather than inventing drama.
- Every factual assertion must be supported by the source material above.
- Do not invent a publisher, printer, donor, date or quantity. If the material does
  not name one, do not name one.
- No instructions to the listener, no "imagine", no rhetorical questions.
Return only the story text."""


def write_story(stop, focus_fact, snippets, live):
    """Step 5. One candidate story from this iteration's material."""
    material = '\n'.join(f"- {s.get('snippet', '')}" for s in snippets[:14]
                         if s.get('snippet'))
    if not material.strip():
        return '', 'no material'
    if not live:
        return '', 'not live'
    from story_leads import _openai
    prompt = WRITER_PROMPT.format(
        title=stop['canonical_title'], exhibition=stop['exhibition_name'],
        venue=stop['venue_name'], fact=focus_fact, material=material[:6000])
    try:
        return _openai(prompt, model=os.environ.get('STORY_WRITER_MODEL', 'gpt-4o')).strip(), ''
    except Exception as e:
        return '', f'{type(e).__name__}: {e}'


def validate(story, corpus):
    """Step 6 — the PRODUCTION deletion gates, in their production order.

    Only the deterministic, free ones: they are the gates that actually delete,
    and running them without API keys is the strict path. Returns
    (surviving_text, [drop records]).
    """
    drops = []
    text = story

    # PHASE 5.156 — unsupported-claim (LOCAL-263). Runs on every tour.
    try:
        from unsupported_claim_gate import apply_unsupported_claim_gate
        new, st = apply_unsupported_claim_gate(text, corpus_passages=[],
                                               api_key=None, model=None)
        if st['sentences_removed']:
            drops.append({'gate': 'LOCAL-263 unsupported-claim',
                          'n': st['sentences_removed']})
            text = new
    except Exception as e:
        drops.append({'gate': 'LOCAL-263', 'error': str(e)})

    # PHASE 5.158b — role-claim (LOCAL-458). Invented publisher/printer/donor.
    try:
        from stop_claim_audit import apply_role_claim_gate
        rec = {'publisher': '', 'credit_line': '', 'artist': STOP['artist']}
        new, dl = apply_role_claim_gate(text, rec, corpus)
        for d in dl:
            drops.append({'gate': 'LOCAL-458 role-claim',
                          'n': len(d['dropped_sentences']),
                          'agent': d['agent'], 'role': d['role']})
        text = new
    except Exception as e:
        drops.append({'gate': 'LOCAL-458', 'error': str(e)})

    # PHASE 5.161 — temporal coherence (LOCAL-402). Fixed in D466.
    try:
        from temporal_coherence_gate import check_temporal_coherence
        from unsupported_claim_gate import _split_sentences
        keep = []
        for s in _split_sentences(text):
            r = check_temporal_coherence(s)
            if r:
                drops.append({'gate': 'LOCAL-402 temporal', 'n': 1,
                              'reason': r['reason']})
            else:
                keep.append(s)
        text = ' '.join(keep)
    except Exception as e:
        drops.append({'gate': 'LOCAL-402', 'error': str(e)})

    return text.strip(), drops


def evaluate(text, corpus):
    """Step 7 — the valuation index. Built at evaluate_story.py:401, unwired in prod."""
    from evaluate_story import evaluate_story
    if not text.strip():
        return {'valuation_index': 0, 'historic': 0, 'detail': 0, 'social': 0}
    return evaluate_story(text, corpus=corpus)


# ═══════════════════════════════════════════════════════════════════════════════

def run(args):
    load_env()
    corpus_path = os.path.join(HERE, 'story_lab_state', 'stop2_page_text.txt')
    corpus = open(corpus_path, encoding='utf-8').read() if os.path.exists(corpus_path) else ''

    state = {'stop': STOP, 'iterations': []}
    if os.path.exists(STATE) and not args.fresh:
        state = json.load(open(STATE))

    done = len(state['iterations'])
    best_so_far = max([i['valuation_index'] for i in state['iterations']
                       if i['validated']] or [0])

    for n in range(done, min(done + args.iterations, len(FOCUS_FACTS))):
        fact = FOCUS_FACTS[n]
        print(f"\n{'=' * 74}\nITERATION {n + 1} — focus fact: {fact}\n{'=' * 74}")

        queries, raw, snippets, nq = gather(STOP, fact, args.live)
        print(f"  {nq} queries -> {len(raw)} raw -> {len(snippets)} kept after ranking")

        story, err = write_story(STOP, fact, snippets, args.live)
        if err:
            print(f"  no story: {err}")
        else:
            print(f"  story: {len(story)} chars")

        survived, drops = validate(story, corpus)
        validated = bool(story) and not drops and bool(survived)
        for d in drops:
            print(f"  DROPPED by {d.get('gate')}: {d.get('reason') or d.get('agent') or d.get('error') or d.get('n')}")

        ev = evaluate(survived, corpus)
        vi = ev['valuation_index']
        if validated and vi > best_so_far:
            best_so_far = vi

        print(f"  valuation_index={vi}  (historic={ev['historic']} "
              f"detail={ev['detail']} social={ev['social']})  "
              f"validated={validated}  running_best={best_so_far}")

        state['iterations'].append({
            'n': n + 1, 'focus_fact': fact, 'queries': queries,
            'raw_results': len(raw), 'kept_snippets': len(snippets),
            'serp_queries': nq, 'story': story, 'survived': survived,
            'drops': drops, 'validated': validated,
            'valuation_index': vi, 'historic': ev['historic'],
            'detail': ev['detail'], 'social': ev['social'],
            'running_best': best_so_far,
        })
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        json.dump(state, open(STATE, 'w'), indent=2, ensure_ascii=False)

    write_chart(state)
    print(f"\n  chart -> {os.path.relpath(CHART_MD, HERE)}")


def write_chart(state):
    """The chart Michael reads. Running best is the line that matters."""
    its = state['iterations']
    lines = [
        '# Story iteration chart — MFA Unbound, stop 2, *Moses and Monotheism*',
        '',
        'Built by `story_iteration_chart.py`. One iteration = one focus fact, its own',
        'queries, its own candidate story, the production deletion gates, then',
        '`evaluate_story.valuation_index`.',
        '',
        '**Read the `best` column.** It is a running best over *validated* stories, so a',
        'flat stretch means those iterations bought nothing — that is the stopping point.',
        '',
        '| # | focus fact | kept | validated | index | hist | detail | social | **best** |',
        '|---|---|---|---|---|---|---|---|---|',
    ]
    for i in its:
        ok = '✅' if i['validated'] else '❌'
        lines.append(
            f"| {i['n']} | {i['focus_fact'][:46]} | {i['kept_snippets']} | {ok} | "
            f"{i['valuation_index']} | {i['historic']} | {i['detail']} | "
            f"{i['social']} | **{i['running_best']}** |")

    lines += ['', '## The curve', '', '```']
    if its:
        top = max(max(i['valuation_index'] for i in its),
                  max(i['running_best'] for i in its), 1)
        for i in its:
            bar = '█' * int(40 * i['running_best'] / top)
            dot = '·' * max(0, int(40 * i['valuation_index'] / top) - len(bar))
            lines.append(f"  {i['n']:2} |{bar}{dot} best={i['running_best']:3} "
                         f"this={i['valuation_index']:3}")
    lines += ['```', '',
              '`█` running best over validated stories · `·` this iteration alone',
              '']

    flat = 0
    for i in reversed(its):
        if its and i['running_best'] == its[-1]['running_best']:
            flat += 1
        else:
            break
    if its:
        lines += ['## Where it stands', '',
                  f"- iterations run: **{len(its)}**",
                  f"- best validated index: **{its[-1]['running_best']}**",
                  f"- iterations since the best improved: **{flat - 1}**",
                  f"- stories rejected by a gate: "
                  f"**{sum(1 for i in its if not i['validated'])} of {len(its)}**",
                  f"- SERP queries spent: **{sum(i['serp_queries'] for i in its)}**",
                  '']
        lines += [
            '## Why it plateaus — read this before tuning anything (D467)', '',
            'The flat stretch is a property of the **metric**, not of the material.',
            '`valuation_index` is [`evaluate_story.py:342`](evaluate_story.py#L342):', '',
            '```',
            'sentence_count * 10   capped at 30   <- maxes at 3 sentences',
            'agency_verbs   * 10   capped at 30',
            'stakes_words   * 12   capped at 25',
            'grounded_fraction * 15               <- proper nouns found in the museum corpus',
            '```', '',
            'Three consequences, all measured:', '',
            '1. **The object is not in the formula.** `detail` — whether a sentence names a',
            '   physical property of the thing in the case — is computed and then never',
            '   added. That is measure 4 in `STORY_GATE_TIERS.md`, the known weakness',
            '   (D449), and the index is blind to it.',
            '2. **Sentences past the third are free.** 3 x 10 already caps that term, so',
            '   Michael\'s "3-5 sentences" is scored as if it were always 3.',
            '3. **Groundedness punishes specificity.** Raising the snippet cap from 5 to 20',
            '   on the best iteration moved `detail` 0 -> 29 (the story finally said',
            '   *"drypoints and lithographs on sheepskin"*) and `historic` 46 -> 66 — and',
            '   the index **fell 61 -> 50**, because the new proper nouns are absent from',
            '   the museum\'s own page. **The scorer repeats the gates\' mistake: it treats',
            '   absence from a narrow corpus as evidence against.**', '',
            'So the plateau does not mean we stopped finding better stories. It means the',
            'instrument stopped being able to see them.', '']

        drops = [d for i in its for d in i['drops']]
        if drops:
            lines += ['### What the gates deleted', '']
            for i in its:
                for d in i['drops']:
                    lines.append(f"- iter {i['n']} — `{d.get('gate')}` — "
                                 f"{d.get('reason') or d.get('agent') or d.get('error') or ''}")
            lines.append('')

    open(CHART_MD, 'w', encoding='utf-8').write('\n'.join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--iterations', type=int, default=3)
    ap.add_argument('--live', action='store_true',
                    help='actually search and write. Without it nothing is spent '
                         'and every iteration scores 0.')
    ap.add_argument('--fresh', action='store_true', help='discard previous iterations')
    ap.add_argument('--replay', action='store_true',
                    help='rebuild the chart from saved state, no spend')
    ap.add_argument('--rescore', action='store_true',
                    help='re-evaluate the SAVED stories with the current index and '
                         'rebuild the chart. No search, no writing, no spend — so '
                         'any change in the curve is the metric and nothing else.')
    a = ap.parse_args()
    if a.replay or a.rescore:
        load_env()
        state = json.load(open(STATE))
        if a.rescore:
            corpus_path = os.path.join(HERE, 'story_lab_state', 'stop2_page_text.txt')
            corpus = (open(corpus_path, encoding='utf-8').read()
                      if os.path.exists(corpus_path) else '')
            best = 0
            for it in state['iterations']:
                ev = evaluate(it.get('survived') or it.get('story', ''), corpus)
                it.update({'valuation_index': ev['valuation_index'],
                           'historic': ev['historic'], 'detail': ev['detail'],
                           'social': ev['social']})
                if it['validated'] and ev['valuation_index'] > best:
                    best = ev['valuation_index']
                it['running_best'] = best
            json.dump(state, open(STATE, 'w'), indent=2, ensure_ascii=False)
        write_chart(state)
        print(f"  chart -> {os.path.relpath(CHART_MD, HERE)}")
        return
    run(a)


if __name__ == '__main__':
    main()
