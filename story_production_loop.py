#!/usr/bin/env python3
"""story_production_loop.py — D511: the whole loop, as one call.

Michael, 2026-08-23: *"We have developed the loop of credit_line values, query
generation with calling Gemini and asserting sources with Serper, and evaluated
and developed stories. I want all of this into production before I generate a new
tour. Comparing one tour old vs new gives me nothing as old can be random and so
is new."*

He is right about the measurement — a single old-vs-new pair is noise at sd 4.9
(D484), which is why D480 requires three runs. So the loop goes in first.

**This module exists so `generate_tour_text` gets ONE call rather than four
scattered edits.** That function is 16,000 lines and every previous insertion
into it has cost a defect; the eight modules built this week are composed here
and the generator imports one name.

The chain, per stop, in the order the evidence justified:

    1. object_record.enrich_matrix   the museum's own record — publisher,
                                     printer, credit line, provenance   [D501]
    2. story_seeds + MATRIX AGENTS   the credit_line list. Agents are added
                                     because A213 measured that seeds taken only
                                     from our own prose can ask only about what
                                     our prose already said — which is why Moses
                                     never reached the Freud/Dalí meeting
    3. per credit_line, in order:
         story_query.compile_*       one question, two encodings          [D507]
         gemini_with_sources         narrate, with grounding metadata     [D508]
         claims_of                   what is checkable
         challenge + page fetch      evidence, from the PAGE not the snippet
                                                                          [D510]
         adjudicate                  CONFIRMED / CORRECTED / DISPUTED /
                                     UNATTESTED, against retrieval        [D509]
         ungrounded_names            a person in no source was invented   [D510]
         story_publish_gate          eventful + index + confirmed         [D510]
    4. STOP AT THE FIRST PASS        iterate-to-threshold, not
                                     permute-and-select. Au Soleil passes on its
                                     first credit_line: 1 call, not 12

**Off by default is deliberate.** `STORY_LOOP_ENABLED=1` turns it on. A loop that
adds ~$0.05 and ~60s per stop must be a decision, not a surprise, and the flag is
what makes the A/B possible at all.

**It never fails a tour.** Every stage is wrapped; any exception returns
`{'story': ''}` and the stop keeps whatever it already had.
"""
import os
import re
import time
from typing import Dict, List, Optional

__all__ = ['run_for_stop', 'is_enabled', 'LOOP_ENABLED_ENV']

LOOP_ENABLED_ENV = 'STORY_LOOP_ENABLED'
MAX_CREDIT_LINES = int(os.environ.get('STORY_LOOP_MAX_CREDIT_LINES', '4'))

# [D523] Examine several credit_lines and keep the BEST, instead of shipping the
# first one over the floor.
#
# Michael, 2026-08-24: *"I see way less stories and less quality stories from
# iteration to iteration and I wonder why."*
#
# Measured from `story_loop_candidates.jsonl`, 13 stop-attempts since D515: **12
# examined exactly one credit_line.** His rule says "if a story passes with index
# 50+, then this is the story and we do not need to verify more", and at a floor
# of 50 the first candidate essentially always qualifies — so the loop stopped
# exploring. What the same three works score across runs:
#
#     Au Soleil   64 · 50 · 71 · 73 · 78 · 60 · 72
#     Le Lézard   61 · 79 · 56 · 65 · 73 · 74 · 69
#     Moses       58 · 37 · 59 · 63 · 72 · 70 · 52
#
# A 20-35 point spread inside one work. Taking the first is one draw from that;
# taking the best of three lands near the top. Both halves of what he noticed
# follow: quality became a lottery, and because `allowed_sentences()` maps index
# to length, a low draw is trimmed to THREE sentences where a high draw earns
# five — fewer words, not only weaker ones.
#
# **This changes one clause of D515 and nothing else.** The floor is still 50,
# `eventful` and `confirmed>=3` still do not gate, and a proven error is still
# the only hard veto. What changes is that "we do not need to verify more"
# becomes "we do not need to verify more ONCE WE HAVE SOMETHING VERY GOOD" —
# `STORY_LOOP_STOP_AT`. `STORY_LOOP_BEST_OF=0` restores accept-first exactly.
BEST_OF = os.environ.get('STORY_LOOP_BEST_OF', '1').strip() != '0'
STOP_AT = int(os.environ.get('STORY_LOOP_STOP_AT', '78'))
CLAIMS_PER_ANSWER = int(os.environ.get('STORY_LOOP_CLAIMS', '4'))
PAGES_PER_QUERY = int(os.environ.get('STORY_LOOP_PAGES', '3'))


def is_enabled() -> bool:
    # [D517] ON by default. It was off because it cost ~$0.05 and ~60s per stop
    # and Michael's rule was that a spend like that must be a decision rather
    # than a surprise. D515/D516 changed the facts underneath that rule: the loop
    # now stops at the first candidate above 50, so it costs **$0.015 and ~35s
    # per stop** — a third of the price — and publishes a story on 9 stops of 9
    # instead of 4. Michael, 2026-08-24: *"Is everything in production? if not,
    # put it there."* `STORY_LOOP_ENABLED=0` turns it off.
    return os.environ.get(LOOP_ENABLED_ENV, '1').strip() != '0'


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text or '')
            if len(s.strip()) > 20]


def _agent_seeds(matrix: Dict) -> List[Dict]:
    """[A213] Credit_lines built from the MATRIX, not from our prose.

    The measured failure: all nine Moses credit_lines were evaluative modifiers
    lifted from its own baseline text, which never mentions that Dalí met Freud
    in London in 1938. The material was retrievable the whole time under the
    query `Sigmund Freud Salvador Dalí`; no seed ever asked for it.

    A matrix agent is a person the museum's own record names. Asking about them
    is how the loop can discover what our prose never said.
    """
    from text_fold import is_placeholder
    out = []
    for role, field in (('artist', 'artist'), ('publisher', 'publisher'),
                        ('printer', 'printed_by'), ('printer', 'printer'),
                        ('collaborator', 'collaborator')):
        v = (matrix.get(field) or '').strip()
        if not v or is_placeholder(v):
            continue
        if any(v.lower() in o['seed'].lower() for o in out):
            continue
        out.append({'id': f'agent:{field}', 'class': 'anchored',
                    'kind': 'matrix_agent', 'seed': v,
                    'ask': f'What did {v} actually do, and what came of it?'})
    credit = (matrix.get('credit_line') or '').strip()
    if credit and not is_placeholder(credit):
        donor = re.sub(r'^(gift|bequest|loan|promised gift)\s+of\s+', '', credit,
                       flags=re.I).split('.')[0].split(',')[0].strip()
        if len(donor) > 4 and not any(donor.lower() in o['seed'].lower() for o in out):
            out.append({'id': 'agent:donor', 'class': 'anchored',
                        'kind': 'matrix_agent', 'seed': donor,
                        'ask': f'Why did {donor} acquire this, and why give it away?'})
    return out


def run_for_stop(matrix: Dict, stop_text: str, exhibition: str = '',
                 venue_url: str = '', extra_entities: Optional[List[str]] = None,
                 verbose: bool = True) -> Dict:
    """The whole loop for one stop. Returns the first story that passes the gate.

    Returns {'story', 'credit_line', 'gate', 'counts', 'index', 'sources',
             'examined', 'candidates', 'cost_usd', 'elapsed_s', 'matrix'}.
    `story` is '' when nothing passes — which is a publishable outcome, not an
    error (Michael: "correct gate behavior is to publish nothing").
    """
    t0 = time.time()
    out = {'story': '', 'credit_line': '', 'gate': None, 'counts': {},
           'index': None, 'sources': [], 'examined': 0, 'candidates': [],
           'cost_usd': 0.0, 'elapsed_s': 0.0, 'matrix': dict(matrix),
           'enabled': True, 'accepted_by': ''}
    gate_best_of = None
    try:
        from object_record import enrich_matrix
        from story_seeds import seeds_for_stop
        from story_query import compile_for_serper, compile_for_gemini
        from story_leads import gemini_with_sources
        from story_adjudicate import (claims_of, challenge_queries_for,
                                      ADJUDICATION_PROMPT, count_statuses,
                                      ungrounded_names, surviving_errors)
        from story_relevance import relevance_of, RELEVANT, WEAK
        from snippet_ranker import fetch_pages_for_top_snippets
        from material_kind import classify_material
        from story_index_pass import apply_story_index
        from story_publish_gate import evaluate as gate_evaluate
        try:
            from story_publish_gate import best_of as gate_best_of
        except ImportError:
            gate_best_of = None
        from work_story_searcher import (_serp_search, normalize_domain,
                                         _classify_domain_quick)
        from cost_rates import search_cost
    except Exception as e:
        if verbose:
            print(f"    [D511] loop unavailable, stop unchanged: {e}")
        out['enabled'] = False
        return out

    n_serp = n_gem = 0

    # ── 1. the museum's own object record ────────────────────────────────
    try:
        if venue_url:
            matrix, _rep = enrich_matrix(dict(matrix), venue_url, verbose=verbose)
            out['matrix'] = dict(matrix)
    except Exception as e:
        if verbose:
            print(f"    [D511] object record skipped: {e}")

    extra = list(extra_entities or [])
    for f in ('artist', 'publisher', 'printed_by', 'collaborator'):
        v = (matrix.get(f) or '').strip()
        if v:
            extra.append(v)

    # ── 2. credit_lines: matrix agents first, then our own prose ─────────
    try:
        prose_seeds = seeds_for_stop(stop_text, set(extra))
    except Exception:
        prose_seeds = []
    seeds = _agent_seeds(matrix) + prose_seeds
    seeds = seeds[:MAX_CREDIT_LINES]
    if verbose:
        print(f"    [D511] {len(seeds)} credit_line(s) to try "
              f"({sum(1 for s in seeds if s['kind'] == 'matrix_agent')} from the "
              f"matrix, {len(seeds) - sum(1 for s in seeds if s['kind'] == 'matrix_agent')} from the text)")

    work = matrix.get('canonical_title', '')
    agents = [a for a in (matrix.get('collaborator'), matrix.get('printed_by'),
                          matrix.get('publisher')) if a]

    for seed in seeds:
        out['examined'] += 1
        cl = seed['seed']
        try:
            gq = compile_for_gemini(matrix, cl, exhibition)
            mat = '\n'.join(f'  {k}: {v}' for k, v in matrix.items() if v)
            r1 = gemini_with_sources(
                f"{gq}\n\nWhat is already known about the work:\n{mat}\n\n"
                "Search, then answer with FACTS ONLY — each one sentence, with its "
                "source in brackets. Prefer what a visitor standing in front of it "
                "cannot see: why it was made, who decided, what went wrong, what it "
                "cost someone. If you find nothing reliable, say exactly "
                '"NO RELIABLE INFORMATION". Do not praise the work. Do not describe '
                "how it looks. Maximum 6 sentences.")
            n_gem += 1
            if not (r1.get('text') or '').strip():
                continue

            judged1 = []
            for s in _sentences(r1['text']):
                v = relevance_of(s, matrix, r1['text'], extra)
                v['sentence'] = s
                judged1.append(v)
            claims = claims_of(judged1, limit=CLAIMS_PER_ANSWER)

            # ── 3. challenge: query the CLAIM, fetch the PAGE ─────────────
            evidence = []
            for c in claims:
                for q in challenge_queries_for(c['claim'], work, agents, limit=1):
                    raw, _ = _serp_search(q)
                    n_serp += 1
                    for r_ in raw:
                        r_.setdefault('url', '')
                    fetch_pages_for_top_snippets(raw, max_fetches=PAGES_PER_QUERY)
                    for res in raw:
                        dom = normalize_domain(res.get('url', ''))
                        body = res.get('fetched_passage') or res.get('snippet') or ''
                        for s in _sentences(body):
                            v = relevance_of(s, matrix, body, extra)
                            if v['verdict'] in (RELEVANT, WEAK):
                                evidence.append(f"[{dom}] {s}")

            seen, ev_lines = set(), []
            for e in evidence:
                if e[:70] in seen:
                    continue
                seen.add(e[:70])
                ev_lines.append(e)
            ev_block = '\n'.join(ev_lines[:60]) or '(no independent evidence retrieved)'

            # ── 4. adjudicate against the evidence, then write ───────────
            r2 = gemini_with_sources(ADJUDICATION_PROMPT.format(
                work=work, exhibition=exhibition, answer=r1['text'],
                evidence=ev_block))
            n_gem += 1
            text2 = r2.get('text') or ''
            m = re.search(r'PART\s*2.*?$', text2, re.S | re.I)
            story = (re.sub(r'^PART\s*2[^\n]*\n', '', m.group(0)).strip()
                     if m else '')
            counts = count_statuses(text2[:m.start()] if m else text2)
            if not story:
                continue

            ungrounded = ungrounded_names(story, ev_block, matrix, extra)
            kept = [j['sentence'] for j in
                    [dict(relevance_of(s, matrix, story, extra), sentence=s)
                     for s in _sentences(story)]
                    if j['verdict'] in (RELEVANT, WEAK)]
            kind = classify_material(kept) if kept else {}

            probe = [{'name': work, 'description': story}]
            try:
                apply_story_index(probe, corpus=ev_block[:40000])
                idx = probe[0].get('_story_index')
            except Exception:
                idx = None

            tells = bool(re.search(
                r'some sources|others say|disagree|dispute|while other',
                story, re.I))
            # [D515] The only hard fail: a correction the story ignored. Read off
            # PART 1 against the PART 2 we would publish — no extra model call.
            errors = surviving_errors(story, text2)

            verdict = gate_evaluate({'story_kind': kind.get('kind', 'none'),
                                     'index': idx, 'counts': counts,
                                     'tells_disagreement': tells,
                                     'factual_errors': errors,
                                     'ungrounded': ungrounded})
            cand = {'credit_line': cl, 'seed_kind': seed['kind'],
                    'story': story, 'counts': counts, 'index': idx,
                    'kind': kind.get('kind', 'none'), 'gate': verdict,
                    'ungrounded': ungrounded, 'factual_errors': errors}
            out['candidates'].append(cand)

            if verbose:
                legacy = verdict.get('legacy_failed', verdict['failed'])
                print(f"    [D511] {seed['id']:<22} kind={cand['kind']:<8} "
                      f"idx={idx or 0:<3} C{counts.get('CONFIRMED',0)} "
                      f"X{counts.get('UNATTESTED',0)} "
                      f"{'PASS' if verdict['passes'] else 'fail:' + ','.join(verdict['failed'])}"
                      f"{'  [old gate: ' + ('pass' if not legacy else ','.join(legacy)) + ']' if 'legacy_failed' in verdict else ''}"
                      f"{'  UNGROUNDED:' + ','.join(ungrounded) if ungrounded else ''}"
                      f"{'  WRONG:' + '; '.join(e['wrong'][:40] for e in errors) if errors else ''}")

            # An invented person is never published, whatever the gate says.
            if ungrounded:
                continue
            if verdict['passes']:
                # Trim to what the score earned (3 / 5 / >5).
                sents = _sentences(story)
                cap = verdict['max_sentences'] or len(sents)
                _kept = ' '.join(sents[:cap])
                _better = (out['index'] or -1) < (idx or 0)
                if not out['story'] or _better:
                    out.update(story=_kept, credit_line=cl,
                               gate=verdict, counts=counts, index=idx,
                               sources=r2.get('sources', []),
                               accepted_by='accepted' if not BEST_OF else 'best_of')
                if not BEST_OF:
                    break
                # [D523] Keep looking unless this one is already very good.
                if (idx or 0) >= STOP_AT:
                    if verbose:
                        print(f"    [D523] index {idx} >= {STOP_AT} — good enough, "
                              f"stopping without buying the rest")
                    break
        except Exception as e:
            if verbose:
                print(f"    [D511] credit_line {seed.get('id')} failed "
                      f"(non-fatal): {type(e).__name__}: {e}")
            continue

    # [D515] "If none of the stories on a stop pass, but the index is more than
    # 50 — accept with the highest index." Nothing was accepted above, so take
    # the best eligible candidate rather than publishing silence.
    if not out['story'] and gate_best_of is not None:
        fallback = gate_best_of(out['candidates'])
        if fallback:
            sents = _sentences(fallback['story'])
            cap = (fallback['gate'].get('max_sentences') or len(sents))
            out.update(story=' '.join(sents[:cap]),
                       credit_line=fallback['credit_line'],
                       gate=fallback['gate'], counts=fallback['counts'],
                       index=fallback['index'], accepted_by='d515_fallback')
            if verbose:
                print(f"    [D511] no candidate accepted outright — "
                      f"[D515] FALLBACK to the highest index: "
                      f"{fallback['index']} ({fallback['kind']}), "
                      f"credit_line '{fallback['credit_line'][:40]}'")

    try:
        from cost_rates import search_cost as _sc
        out['cost_usd'] = round(_sc(n_serp) + n_gem * 0.006, 4)
    except Exception:
        pass
    out['elapsed_s'] = round(time.time() - t0, 1)
    if verbose:
        _scores = [c['index'] for c in out['candidates'] if c.get('index') is not None]
        print(f"    [D511] examined {out['examined']} credit_line(s)"
              f"{' (indices ' + ', '.join(str(s) for s in _scores) + ')' if len(_scores) > 1 else ''}, "
              f"{'STORY ACCEPTED at ' + str(out['index']) if out['story'] else 'no story passed'}, "
              f"~${out['cost_usd']:.3f}, {out['elapsed_s']:.0f}s")

    # [D514] Persist every candidate, not just the winner.
    #
    # Michael asked to see the rejected Moses stories and their verdicts, and
    # they were not on disk: the log carries one summary line per candidate and
    # the story text lived only in this dict. A rejection we cannot read is a
    # rejection we cannot check — and the whole reason Moses publishes nothing
    # is a claim about these texts.
    #
    # Append-only JSONL, one line per candidate, so concurrent stops in the same
    # run cannot clobber each other. Wrapped: persistence must never fail a tour.
    try:
        import json as _json
        _path = os.environ.get('STORY_LOOP_CANDIDATE_LOG', 'story_loop_candidates.jsonl')
        with open(_path, 'a', encoding='utf-8') as _fh:
            for _c in out['candidates']:
                _fh.write(_json.dumps({
                    'ts': time.strftime('%Y-%m-%dT%H:%M:%S'),
                    'work': matrix.get('canonical_title', ''),
                    'credit_line': _c['credit_line'],
                    'seed_kind': _c['seed_kind'],
                    'kind': _c['kind'],
                    'index': _c['index'],
                    'counts': _c['counts'],
                    'passes': _c['gate'].get('passes'),
                    'failed': _c['gate'].get('failed'),
                    'ungrounded': _c['ungrounded'],
                    'factual_errors': _c.get('factual_errors') or [],
                    'legacy_passes': _c['gate'].get('legacy_passes'),
                    'legacy_failed': _c['gate'].get('legacy_failed'),
                    'story': _c['story'],
                }, ensure_ascii=False) + '\n')
    except Exception as _e:
        if verbose:
            print(f"    [D511] candidate log not written (non-fatal): {_e}")
    return out
