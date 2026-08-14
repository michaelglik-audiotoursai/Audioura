#!/usr/bin/env python3
"""story_pipeline.py — the whole chain, wired the way it has to be wired.

Michael's routines, in his order, end to end:

    interrogation_matrix   what to ask about
    Request_to_AI          the question
    -> SEARCH              interrogate the INTERNET with that question   <- see below
    -> rank                LOCAL-459 ranker
    story_writer           write from the retrieved corpus and nothing else
    Validate_Story         entity AND relation grounding
    Evaluate_Story         Historic / Detail / Social, independent 0-100

WHY THE SEARCH STEP IS NOT OPTIONAL
-----------------------------------
Run 1 of the chain sent `Request_to_AI`'s question straight to an LLM and validated
the answer against our corpus. It was REJECTED, and it had to be: the answer came
from the model's memory, which has no overlap with our corpus by construction. The
answer also asserted "The Hogarth Press" as fact — the term entered as a CLAIMED
value in the question and came back as a finding. That is the D427 loop closing on
itself: an invention we shipped, fed back in as a query, returned as confirmation.

Michael's words were "interrogate Internet". So the question drives RETRIEVAL. What
comes back is corpus, and the corpus is what the writer may use. The LLM's own
recall is never evidence.

    python3 story_pipeline.py --tour TOUR_MFA_20260812_2030.txt --stops 1 2 3 \\
        --tour-type museum --live
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
for _l in open(os.path.join(HERE, '.env')):
    _l = _l.strip()
    if _l and not _l.startswith('#') and '=' in _l:
        _k, _v = _l.split('=', 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from interrogation_matrix import build_matrix          # noqa: E402
from request_and_structure import request_to_ai        # noqa: E402
from snippet_ranker import rank_and_cap_snippets       # noqa: E402
from story_opportunity_scan import measure, verdict    # noqa: E402
from story_material_check import assess, load_corpus   # noqa: E402
from story_opportunity_scan import _fold               # noqa: E402
from validate_story import validate_story              # noqa: E402
from evaluate_story import evaluate_story              # noqa: E402
import story_writer                                     # noqa: E402


def slot(m, k):
    return ((m.get(k) or {}).get('value') or '').strip()


# Articles and prepositions carry no identity, so they must not make a surface
# look like a title fragment on their own, nor stop one from matching.
_TITLE_STOP = {'the', 'and', 'with', 'from', 'for', 'les', 'des', 'aux',
               'une', 'his', 'her', 'its'}


def _title_toks(s):
    return {t for t in re.findall(r"[a-z0-9']+", _fold(s))
            if len(t) > 2 and t not in _TITLE_STOP}


def title_fragment_test(canonical, english=''):
    """Predicate: is this handle a piece of the stop's OWN title?

    "Le Lézard", "The Lizard", "Golden Feathers", "At Le Lézard" — all pieces of
    the stop's own title. They cannot be story SUBJECTS because they ARE the
    object. They filled 7 of stop 1's top 10 handles and pushed Louis Broder — the
    publisher the whole story is about — down to 10th.

    D439: the substring form of this test compared against `canonical_title`
    ALONE, so the ENGLISH gloss fragments and anything with a leading preposition
    slipped through and burned every credit_line substitution. Token containment
    against BOTH titles catches all four shapes.
    """
    title_set = _title_toks(canonical) | _title_toks(english)

    def _is_fragment(surface):
        toks = _title_toks(surface)
        return bool(title_set) and bool(toks) and toks <= title_set

    return _is_fragment


def search_the_question(matrix, question, drop_unverified=False):
    """Interrogate the internet with the matrix, not with the model's memory.

    MEASURED, 2026-08-13: dropping CLAIMED terms from the search took the MFA
    stops from 2-of-3 sourceable to 0-of-3. `artist = Salvador Dalí` is CLAIMED —
    the delivered text asserts it and nothing checked it — and it is also the most
    productive query term we have. Removing it removed the Dalí-Freud material
    entirely.

    So: an unverified term BELONGS in the search. Searching for it is how you
    verify it. What is forbidden is treating a page retrieved because of it as
    confirmation of it — and that is `validate_story`'s job downstream, not the
    searcher's. `drop_unverified=True` is kept for the comparison, not for use.
    """
    from work_story_searcher import search_stories_for_stop
    unverified = set()
    if drop_unverified:
        for k, cell in matrix.items():
            if (cell or {}).get('status') == 'CLAIMED':
                unverified.add(k)

    rec = {
        'canonical_title': slot(matrix, 'canonical_title'),
        'english_title': slot(matrix, 'english_title'),
        'artist': '' if 'artist' in unverified else slot(matrix, 'artist'),
        'publisher': '' if 'publisher' in unverified else slot(matrix, 'publisher'),
        'printer': slot(matrix, 'printed_by'),
        # NAME COLLISION, and it cost two full pipeline runs. In Michael's matrix
        # `credit_line` is THE STORY KEYWORD ("Sigmund Freud"). In
        # work_story_searcher `credit_line` is the museum credit line ("Gift of
        # Boris Fridman") — it is regex-mined for a donor and a printer. Feeding
        # the story keyword into that slot means the keyword generates no queries
        # at all, and the searcher hunts a donor named Sigmund Freud.
        #
        # The story keyword is a PERSON THE WORK CONNECTS TO, which is exactly
        # what `collaborator` is: it drives "{collaborator} {artist}" and
        # "{collaborator} {artist} relationship why collaborated" — the two
        # queries that found the Dalí-Freud meeting in the first place.
        'collaborator': slot(matrix, 'credit_line'),
        'credit_line': '',
        'medium': slot(matrix, 'medium'),
        'exhibition_name': slot(matrix, 'medium'),
        'venue_name': slot(matrix, 'venue'),
        'venue_city': '', 'venue_lang': 'en',
    }
    res = search_stories_for_stop(rec, tour_type='contained',
                                  generation_tier=os.environ.get('GENERATION_TIER', 'plus'))
    raw = res.get('results', [])
    kept, _ = rank_and_cap_snippets(raw, rec['artist'],
                                    work_title=rec['canonical_title'], stop_record=rec)
    return rec, raw, kept, res.get('estimated_cost', 0) or 0


def run_stop(stop_text, tour_context, tour_type, live=True, credit_line='',
             subject_is_credit_line=False, tag=''):
    """Run one stop end to end.

    `credit_line` overrides the story keyword the matrix derived. Michael's
    proposal, 2026-08-14: a keyword need not be one word or one name. The most
    STOP-SPECIFIC clause of a sentence — "The convergence of narrative and imagery
    in this exhibit" — is a better seed than the most general one ("unexpected ways
    elsewhere"), and better than a bare common noun ("book").

    `subject_is_credit_line` makes the story be ABOUT the keyword. Without it the
    keyword only shapes RETRIEVAL and the writer's subject still comes from the
    handle ladder — which is why the first run of this experiment returned a story
    about Salvador Dalí and did not test the proposal at all.

    `tag` distinguishes the corpus file between runs of the same stop. Without it
    both arms of an A/B write to a path keyed on the stop title alone and the
    second silently overwrites the first one's evidence.
    """
    m = build_matrix(stop_text, tour_type=tour_type, tour_context=tour_context)
    if credit_line:
        m['credit_line'] = {'value': credit_line, 'status': 'DERIVED',
                            'source': 'override/experiment', 'rung': ''}
    req = request_to_ai(m)
    out = {'matrix': m, 'request': req['request'],
           'unverified': req.get('unverified_terms', []), 'cost': 0.0}

    # Strip the scaffolding lines. "Address: 465 Huntington Ave" is not prose, and
    # left in it contributes handles like "Huntington Ave" that crowd out the
    # protagonists.
    body = re.split(r'\n\s*Directions:', stop_text)[0]
    body = re.sub(r'^\s*(?:Stop \d+|Address|Coordinates)\s*:.*$', '', body, flags=re.M)
    meas = measure(body)
    need = verdict(meas)
    out['needs_story'] = need['needs_additional_story']
    out['need_why'] = need['why']

    if not live:
        out['status'] = 'DRY'
        return out

    rec, raw, kept, cost = search_the_question(m, req['request'])
    out['cost'] = cost
    out['retrieved'], out['kept'] = len(raw), len(kept)
    out['domains'] = [s.get('domain', '') for s in kept]

    corpus_path = os.path.join(
        HERE, 'story_lab_state',
        f"pipe_{re.sub(r'[^a-z0-9]+', '_', slot(m, 'canonical_title').lower())[:40]}"
        f"{('_' + re.sub(r'[^a-z0-9]+', '_', tag.lower())[:24]) if tag else ''}.txt")
    out['corpus_path'] = corpus_path
    with open(corpus_path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join((s.get('title', '') + '. ' + (s.get('snippet') or '')) for s in kept))
    corpus = load_corpus([corpus_path], {})
    out['corpus_chars'] = len(corpus)

    # Order by STORY VALUE, not by the measure's ascending sort. The previous
    # `[:8]` took the eight WEAKEST handles — Address, Huntington Ave, books — and
    # cut Salvador Dalí and Sigmund Freud, which sat at 13 and 14. Both were
    # SOURCEABLE with 11 passages each; the pipeline reported SILENCE three runs
    # running because it never asked about them. FLAT first: an established
    # subject carrying no stakes is the best place to attach a story (D433).
    _rank = {'FLAT': 0, 'MENTIONED': 1, 'DANGLING': 2}
    _is_title_fragment = title_fragment_test(slot(m, 'canonical_title'),
                                             slot(m, 'english_title'))

    def _is_person(h):
        return h['kind'] == 'proper noun' and not _is_title_fragment(h['surface'])

    targets = [h['surface'] for h in
               sorted((h for h in meas['handles']
                       if h['state'] != 'DEVELOPED' and not _is_title_fragment(h['surface'])),
                      key=lambda h: (0 if _is_person(h) else 1,
                                     _rank.get(h['state'], 3), -h['sentences']))]
    out['ladder'] = targets[:10]
    mats = [assess(h, corpus) for h in targets[:8]]
    sourceable = [r['handle'] for r in mats if r['state'] == 'SOURCEABLE']
    out['sourceable'] = sourceable

    if not sourceable:
        # SECOND PASS — drop the principal and ask about the SUBJECT ITSELF.
        # Measured on Beacon Hill: `artist` resolves to Charles Bulfinch ("whoever
        # is in charge"), and his biography crowds the square's own story out of
        # the results. Louisburg Square was sourceable in the D433 sweep, which
        # queried the title alone, and SILENCE here until this pass existed.
        # Same shape as Michael's credit_line substitution: when the question
        # returns nothing, ask a different question before giving up.
        rec2 = dict(rec, artist='', publisher='', printer='', collaborator='')
        from work_story_searcher import search_stories_for_stop as _s2
        res2 = _s2(rec2, tour_type='contained',
                   generation_tier=os.environ.get('GENERATION_TIER', 'plus'))
        out['cost'] += res2.get('estimated_cost', 0) or 0
        kept2, _ = rank_and_cap_snippets(res2.get('results', []), '',
                                         work_title=rec2['canonical_title'],
                                         stop_record=rec2)
        extra = '\n'.join((x.get('title', '') + '. ' + (x.get('snippet') or ''))
                           for x in kept2)
        if extra.strip():
            with open(corpus_path, 'a', encoding='utf-8') as fh:
                fh.write('\n' + extra)
            corpus = load_corpus([corpus_path], {})
            out['corpus_chars'] = len(corpus)
            out['second_pass'] = True
            mats = [assess(h, corpus) for h in targets[:8]]
            sourceable = [r['handle'] for r in mats if r['state'] == 'SOURCEABLE']
            out['sourceable'] = sourceable

    if not sourceable:
        # MICHAEL'S RULE (routine 2, 2026-08-13): "If the information is less than 3
        # sentences, go back to matrix building and substitute credit_line with the
        # next word and call Request_to_AI." It was implemented in
        # request_and_structure.structure_ai_output and never wired in here.
        #
        # Measured: stop 1's credit_line was "book" -> SILENCE. Stops 2 and 3 got
        # "Sigmund Freud" and "Pierre Reverdy" -> STORY. The two that worked were
        # handed a PERSON. Walking the ladder is how a generic noun gets replaced
        # by one.
        out['substitutions'] = []
        for nxt in targets[:4]:
            if _fold(nxt) == _fold(slot(m, 'credit_line')):
                continue
            rec3 = dict(rec, collaborator=nxt)
            from work_story_searcher import search_stories_for_stop as _s3
            res3 = _s3(rec3, tour_type='contained',
                       generation_tier=os.environ.get('GENERATION_TIER', 'plus'))
            out['cost'] += res3.get('estimated_cost', 0) or 0
            kept3, _ = rank_and_cap_snippets(res3.get('results', []), rec3['artist'],
                                             work_title=rec3['canonical_title'],
                                             stop_record=rec3)
            add = '\n'.join((x.get('title', '') + '. ' + (x.get('snippet') or ''))
                             for x in kept3)
            out['substitutions'].append({'credit_line': nxt, 'kept': len(kept3)})
            if not add.strip():
                continue
            with open(corpus_path, 'a', encoding='utf-8') as fh:
                fh.write('\n' + add)
            corpus = load_corpus([corpus_path], {})
            out['corpus_chars'] = len(corpus)
            mats = [assess(h, corpus) for h in targets[:8]]
            sourceable = [r['handle'] for r in mats if r['state'] == 'SOURCEABLE']
            if sourceable:
                out['sourceable'] = sourceable
                out['credit_line_used'] = nxt
                break

    if not sourceable:
        out['status'] = 'SILENCE'
        return out

    subject = slot(m, 'credit_line') if subject_is_credit_line else sourceable[0]
    res = story_writer.write_story(rec, corpus, subject, attempts=2)
    out['subject'] = subject
    out['writer_status'] = res['status']
    out['story'] = res.get('story', '')
    if not out['story']:
        out['status'] = 'NO_STORY'
        return out

    v = validate_story(out['story'], corpus)
    out['validate'] = v['verdict']
    out['bad_sentences'] = [s['text'][:90] for s in v['sentences'] if s['status'] != 'GROUNDED']
    e = evaluate_story(out['story'], m, corpus)
    out['scores'] = {k: e[k] for k in ('historic', 'detail', 'social', 'valuation_index')}
    out['status'] = 'STORY' if v['verdict'] == 'TRUE_TO_SOURCES' else 'REJECTED'
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--tour', required=True)
    p.add_argument('--stops', nargs='*', type=int, default=[1, 2, 3])
    p.add_argument('--tour-type', default='museum')
    p.add_argument('--live', action='store_true')
    p.add_argument('--out', default='')
    p.add_argument('--subject-is-credit-line', action='store_true',
                   help='Write the story ABOUT the credit_line, not about the '
                        'top handle from the ladder.')
    p.add_argument('--tag', default='',
                   help='Distinguish this run\'s corpus file from another run of '
                        'the same stop.')
    p.add_argument('--credit-line', default='',
                   help='Override the derived story keyword. A phrase is allowed '
                        'and is the point — see run_stop().')
    a = p.parse_args()

    full = open(a.tour, encoding='utf-8').read()
    parts = re.split(r'\n(?=Stop \d+:)', full)
    rows = []
    for n in a.stops:
        sel = [x for x in parts if x.startswith(f'Stop {n}:')]
        if not sel:
            continue
        print(f"\n{'=' * 78}\nSTOP {n}\n{'=' * 78}")
        r = run_stop(sel[0], full, a.tour_type, a.live,
                     credit_line=a.credit_line,
                     subject_is_credit_line=a.subject_is_credit_line,
                     tag=a.tag)
        r['stop'] = n
        r['title'] = slot(r['matrix'], 'canonical_title')
        rows.append(r)
        print(f"  {r['title'][:60]}")
        print(f"  needs story {r['needs_story']}   retrieved {r.get('retrieved','-')} -> "
              f"kept {r.get('kept','-')}   corpus {r.get('corpus_chars','-')} chars")
        print(f"  sourceable  {', '.join(r.get('sourceable', [])) or 'NONE'}")
        print(f"  STATUS      {r['status']}   {r.get('validate','')}")
        if r.get('story'):
            print(f"  STORY: {r['story'][:300]}")
        if r.get('scores'):
            s = r['scores']
            print(f"  SCORES  H={s['historic']} D={s['detail']} S={s['social']} "
                  f"index={s['valuation_index']}")
        for b in r.get('bad_sentences', [])[:3]:
            print(f"    ungrounded: {b}")

    print(f"\n\n{'=' * 78}\nPIPELINE SUMMARY\n{'=' * 78}")
    print(f"  {'stop':38} {'status':10} {'val':>4}  H/D/S")
    for r in rows:
        s = r.get('scores') or {}
        print(f"  {r['title'][:37]:38} {r['status']:10} "
              f"{s.get('valuation_index', '-'):>4}  "
              f"{s.get('historic','-')}/{s.get('detail','-')}/{s.get('social','-')}")
    print(f"\n  total search cost: ${sum(r.get('cost', 0) for r in rows):.4f}")
    if a.out:
        json.dump(rows, open(a.out, 'w'), default=str, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    main()
