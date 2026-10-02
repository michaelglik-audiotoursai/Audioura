#!/usr/bin/env python3
"""story_lab.py — run the story pipeline one subroutine at a time.

Michael's ask, 2026-08-12: isolate the subroutines that build a story so we can
run and improve each one separately, rather than only ever seeing the finished
tour. The stages below are his, in his order:

    S1  fact -> stop -> exhibition   assemble the stop record
    S2  making the query             what we ask the internet
    S3  result + evaluation          what came back, and which parts are the story
    S4  the right size               is there enough? if not, learn more
    S5  writing                      the material handed to the story pass
    S6  validation                   the gates that delete bad sentences

Every stage reads and writes ONE json state file, so you can run a stage, look
at the state, edit it by hand, and run the next stage on your edit. Nothing is
hidden between stages.

    python3 story_lab.py stages
    python3 story_lab.py s1 --tour tours/MFA_TOUR_20260812_2030.txt --stop 1
    python3 story_lab.py s2
    python3 story_lab.py s3 --live
    python3 story_lab.py s4
    python3 story_lab.py s5
    python3 story_lab.py s6 --text-from-tour

State lives in story_lab_state/current.json unless --state says otherwise.
S3 is the only stage that spends money, and it refuses to unless given --live.
"""
import argparse
import json
import os
import re
import sys
import textwrap
import warnings

warnings.filterwarnings('ignore')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
STATE_DIR = os.path.join(HERE, 'story_lab_state')
DEFAULT_STATE = os.path.join(STATE_DIR, 'current.json')


# ── plumbing ────────────────────────────────────────────────────────────────

def load_env():
    """Read .env the way the container does, without overwriting a real env."""
    path = os.path.join(HERE, '.env')
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def state_load(path):
    if not os.path.exists(path):
        die(f"no state at {path} — run s1 first")
    return json.load(open(path))


def state_save(path, state):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(state, open(path, 'w'), indent=2, ensure_ascii=False)
    print(f"\n  state -> {os.path.relpath(path, HERE)}")


def die(msg):
    print(f"\nstory_lab: {msg}", file=sys.stderr)
    sys.exit(1)


def head(n, title):
    print(f"\n{'=' * 74}\nSTAGE {n} — {title}\n{'=' * 74}")


def wrap(text, indent='    ', width=96):
    return textwrap.fill(str(text), width=width,
                         initial_indent=indent, subsequent_indent=indent)


# ── tour parsing ────────────────────────────────────────────────────────────

def parse_tour(path):
    """Split a generated tour file into stops. Returns list of dicts."""
    if not os.path.exists(path):
        die(f"tour file not found: {path}")
    raw = open(path, encoding='utf-8').read()
    parts = re.split(r'\n(?=Stop \d+:)', raw)
    stops = []
    for part in parts:
        m = re.match(r'Stop (\d+):\s*(.+)', part)
        if not m:
            continue
        body = part
        def field(name):
            f = re.search(rf'^{name}:\s*(.+)$', body, re.M)
            return f.group(1).strip() if f else ''
        # everything after the Orientation paragraph is the story prose
        orient = field('Orientation')
        after = body.split(orient, 1)[-1] if orient else body
        prose = re.split(r'\n\s*Directions:', after)[0].strip()
        stops.append({
            'index': int(m.group(1)),
            'title': m.group(2).strip(),
            'address': field('Address'),
            'coordinates': field('Coordinates'),
            'orientation': orient,
            'prose': prose,
        })
    return stops


# ── S1 ──────────────────────────────────────────────────────────────────────

def stage1(args):
    head(1, "fact -> stop -> exhibition   (assemble the stop record)")
    print("""
  Everything downstream keys off ONE dict. If a field is empty here, no query
  in S2 can ask about it and no story in S5 can mention it. This is where a
  thin tour is usually decided — not in the writing.
""")
    stops = parse_tour(args.tour)
    if not stops:
        die(f"no stops parsed from {args.tour}")
    chosen = next((s for s in stops if s['index'] == args.stop), None)
    if not chosen:
        die(f"stop {args.stop} not in tour (found {[s['index'] for s in stops]})")

    stop = {
        'canonical_title': chosen['title'],
        'local_title': chosen['title'],
        'artist': args.artist or '',
        'venue_name': args.venue,
        'venue_city': args.city,
        'venue_lang': 'en',
        'exhibition_name': args.exhibition,
        'publisher': args.publisher or '',
        'collaborator': args.collaborator or '',
        'credit_line': args.credit_line or '',
    }

    print("  THE STOP RECORD")
    for k, v in stop.items():
        mark = ' ' if v else '!'
        print(f"   {mark} {k:18} {v!r}")
    empty = [k for k, v in stop.items() if not v]
    if empty:
        print(f"\n  {len(empty)} empty field(s): {', '.join(empty)}")
        print("  Each empty field is a query S2 cannot make. Fill them in the state")
        print("  file by hand and re-run s2 to see exactly what each one buys you.")

    print("\n  WHAT THE TOUR ACTUALLY SAID AT THIS STOP")
    print(wrap(chosen['prose'][:600] + ('…' if len(chosen['prose']) > 600 else '')))

    state = {
        'tour_file': os.path.relpath(args.tour, HERE),
        'stop_index': chosen['index'],
        'stop': stop,
        'tour_prose': chosen['prose'],
        'tour_orientation': chosen['orientation'],
    }
    state_save(args.state, state)


# ── S2 ──────────────────────────────────────────────────────────────────────

def stage2(args):
    head(2, "making the query   (work_story_searcher.synthesize_queries)")
    print("""
  Deterministic and free — no API call. Same stop in, same queries out, so this
  is the cheapest stage to iterate on. D335-D336: queries are built around the
  WORK and the people who made it happen, not the artist's biography.
""")
    state = state_load(args.state)
    stop = state['stop']
    from work_story_searcher import synthesize_queries, synthesize_class_targeted_queries

    queries = synthesize_queries(stop, args.tour_type)
    print(f"  {len(queries)} QUERIES from this stop record:\n")
    for i, q in enumerate(queries, 1):
        print(f"   {i:2}. {q}")

    if not queries:
        print("   (none — the stop record is too empty to ask anything)")

    try:
        cls = synthesize_class_targeted_queries(stop, args.tour_type)
        if cls:
            print(f"\n  {len(cls)} CLASS-TARGETED queries (historic/social/detail):\n")
            for i, q in enumerate(cls, 1):
                print(f"   {i:2}. {q}")
    except Exception as e:
        print(f"\n  class-targeted queries unavailable: {type(e).__name__}: {e}")

    print("""
  TO EXPERIMENT: edit any field in the state file's "stop" and re-run s2.
  Adding a publisher or a credit_line visibly changes the query set — that is
  the fact -> stop link Michael wants to see, made explicit.
""")
    state['queries'] = queries
    state_save(args.state, state)


# ── S3 ──────────────────────────────────────────────────────────────────────

def stage3(args):
    head(3, "result + evaluation   (search_stories_for_stop, then snippet_ranker)")
    state = state_load(args.state)
    stop = state['stop']

    if not args.live:
        print("""
  This stage spends money (SERP + Wikidata lookups). Re-run with --live to
  actually search. Showing the scoring rules against any snippets already in
  the state file instead.
""")
        results = state.get('search_results', [])
        if not results:
            die("no cached search_results in state — re-run with --live")
    else:
        from work_story_searcher import search_stories_for_stop
        print(f"\n  searching, tier={os.environ.get('GENERATION_TIER', 'plus')} …")
        out = search_stories_for_stop(stop, args.tour_type)
        results = out.get('results', [])
        print(f"  status={out.get('story_mining_status')} "
              f"queries={out.get('total_queries')} "
              f"cost=${out.get('estimated_cost', 0):.4f} "
              f"results={len(results)}")
        for q in out.get('query_log', [])[:12]:
            print(f"    · {q.get('result_count', 0):3} hits  "
                  f"{q.get('latency_ms', 0):5}ms  {q.get('query', '')[:70]}")
        state['search_results'] = results
        state['search_meta'] = {k: v for k, v in out.items() if k != 'results'}

    from snippet_ranker import score_snippet, rank_and_cap_snippets
    print(f"\n  SCORING {len(results)} SNIPPETS — this is 'which parts are the story'\n")
    scored = sorted(((score_snippet(s, stop.get('artist', '')), s) for s in results),
                    key=lambda t: -t[0])
    for sc, s in scored[:args.show]:
        print(f"   score {sc:4}  [{s.get('tier', '?')}]  {s.get('domain', '')}")
        print(wrap((s.get('snippet') or '')[:260], indent='            '))
    kept, meta = rank_and_cap_snippets(results, stop.get('artist', ''),
                                       work_title=stop.get('canonical_title', ''))
    print(f"\n  KEPT {len(kept)} of {len(results)} after ranking + cap")
    if isinstance(meta, dict):
        for k, v in list(meta.items())[:10]:
            print(f"    {k}: {v}")
    print("""
  READ THIS AS: everything dropped here can never reach the story. If the tour
  is thin, check whether the material was missing (S3 found nothing) or thrown
  away (S3 found it and the ranker cut it). Those are different bugs.
""")
    state['ranked_snippets'] = kept
    state_save(args.state, state)


# ── S4 ──────────────────────────────────────────────────────────────────────

def stage4(args):
    head(4, "the right size   (corpus_coverage, then targeted refinement)")
    print("""
  Michael's step 4: if what we have is too small, go learn more. This stage
  measures the material and, when it is thin, shows the follow-up queries the
  system would ask to fill the gap.
""")
    state = state_load(args.state)
    stop = state['stop']
    snippets = state.get('ranked_snippets') or state.get('search_results') or []
    passages = [s.get('snippet', '') for s in snippets if s.get('snippet')]

    from corpus_coverage import assess_stop_coverage
    cov = assess_stop_coverage(stop.get('canonical_title', ''),
                               stop.get('venue_name', ''), passages)
    print(f"  COVERAGE for {stop.get('canonical_title')!r}")
    for k, v in cov.items():
        print(f"    {k:24} {v if not isinstance(v, list) else v[:6]}")

    total = sum(len(p) for p in passages)
    print(f"\n    passages                 {len(passages)}")
    print(f"    total chars              {total}")
    print(f"    verdict                  {'THIN — needs replenishment' if total < 1500 else 'enough to write from'}")

    from work_story_searcher import synthesize_fact_targeted_queries
    elements = state.get('reported_elements', [])
    try:
        fq = synthesize_fact_targeted_queries(stop, elements)
        print(f"\n  {len(fq)} FACT-TARGETED FOLLOW-UP QUERIES (the 'learn more' step):\n")
        for i, q in enumerate(fq, 1):
            print(f"   {i:2}. {q}")
        if not fq:
            print("   (none — no reported_elements in state to target)")
        state['refinement_queries'] = fq
    except Exception as e:
        print(f"\n  follow-up queries unavailable: {type(e).__name__}: {e}")

    state['coverage'] = cov
    state_save(args.state, state)


# ── S5 ──────────────────────────────────────────────────────────────────────

def stage5(args):
    head(5, "writing   (the material handed to the story pass)")
    print("""
  NOTE, and it is the important finding of this harness: the story-writing
  prompt itself is NOT a subroutine. It is inline in generate_tour_text() —
  a 10,443-line function — so it cannot be called on its own. What CAN be
  called are the blocks that feed it, shown below. Extracting the prompt is
  the next piece of work, and it is what would let us iterate on the writing
  the way we can already iterate on S2.
""")
    state = state_load(args.state)
    stop = state['stop']
    snippets = state.get('ranked_snippets') or state.get('search_results') or []

    from story_beat_injector import extract_story_beats
    text = '\n'.join(s.get('snippet', '') for s in snippets)
    beats = extract_story_beats(text) if text else []
    print(f"  STORY BEATS mined from the material: {len(beats)}\n")
    for b in beats[:args.show]:
        print(f"   [{b.get('role', '?'):12}] {b.get('person', '?')}")
        print(wrap(b.get('text', b.get('action', ''))[:220], indent='            '))
    if not beats and not snippets:
        print("   (no snippets in the state file — run `s3 --live` first, or this stage")
        print("    is only showing you the empty scaffold)")
    elif not beats:
        print("   (none — no people doing things were found in the material)")
        print("   A stop with material but zero beats is the 'describes what I can see")
        print("   myself' failure: nothing happened, so the prose has nothing to say.")

    try:
        from generate_tour_text import build_snippet_block
        block = build_snippet_block(snippets, stop.get('artist', ''), '')
        print(f"\n  SNIPPET BLOCK as the prompt receives it ({len(block)} chars):\n")
        print(wrap(block[:1200], indent='    '))
    except Exception as e:
        print(f"\n  build_snippet_block unavailable: {type(e).__name__}: {e}")

    state['story_beats'] = beats
    state_save(args.state, state)


# ── S6 ──────────────────────────────────────────────────────────────────────

GATES = [
    ('prose entity grounding', 'prose_entity_grounding_gate', 'apply_prose_entity_grounding_gate'),
    ('form claim',             'prose_entity_grounding_gate', 'apply_form_claim_gate'),
    ('numeric claim',          'prose_entity_grounding_gate', 'apply_numeric_claim_gate'),
    ('dangling demonstrative', 'dangling_demonstrative_gate', 'apply_dangling_demonstrative_gate'),
]


def stage6(args):
    head(6, "validation   (the gates that delete bad sentences)")
    print("""
  These run AFTER the story is written and delete sentences that fail. A stop
  that reads thin is often a stop that was written fine and then cut. Run this
  on the tour's own prose to see which gate would touch it.
""")
    state = state_load(args.state)
    text = state.get('tour_prose', '') if args.text_from_tour else args.text
    if not text:
        die("nothing to validate — pass --text-from-tour or --text")
    print(f"  INPUT ({len(text)} chars)\n")
    print(wrap(text[:700]))

    print("\n  GATES AVAILABLE\n")
    for label, mod, fn in GATES:
        try:
            m = __import__(mod)
            f = getattr(m, fn, None)
            import inspect
            sig = str(inspect.signature(f)) if f else '<missing>'
            print(f"   {label:26} {mod}.{fn}")
            print(f"   {'':26} {sig}")
        except Exception as e:
            print(f"   {label:26} UNAVAILABLE — {type(e).__name__}: {e}")
    print("""
  Each gate takes the prose plus its evidence and returns the surviving text.
  Call one directly to see what it removes and why — that is the fastest way
  to tell 'the writer had nothing' from 'the gate ate it'.
""")


# ── stages listing ──────────────────────────────────────────────────────────

def stages(args):
    print(__doc__)
    print("""
WHERE EACH STAGE LIVES IN THE CODE

  S1  the stop record        generate_tour_text.py, PHASE 3A/3B + exhibition_checklist.py
  S2  making the query       work_story_searcher.py:395   synthesize_queries
  S3  search + evaluate      work_story_searcher.py:773   search_stories_for_stop
                             snippet_ranker.py:140        score_snippet
                             snippet_ranker.py:352        rank_and_cap_snippets
  S4  the right size         corpus_coverage.py:75        assess_stop_coverage
                             work_story_searcher.py:662   synthesize_fact_targeted_queries
                             work_story_searcher.py:940   execute_fact_refinement
  S5  writing                story_beat_injector.py       extract_story_beats
                             exhibition_thesis.py         build_exhibition_thesis_stop_block
                             generate_tour_text.py:2131   build_snippet_block
                             generate_tour_text.py:8765   PHASE 5  <- NOT a callable subroutine
  S6  validation             prose_entity_grounding_gate.py, dangling_demonstrative_gate.py,
                             plus ~15 more gates inline at generate_tour_text.py:11761-12679
""")


# ── main ────────────────────────────────────────────────────────────────────

def main():
    load_env()
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--state', default=DEFAULT_STATE)
    sub = p.add_subparsers(dest='cmd', required=True)

    sub.add_parser('stages').set_defaults(func=stages)

    s1 = sub.add_parser('s1', help='assemble the stop record')
    s1.add_argument('--tour', required=True)
    s1.add_argument('--stop', type=int, default=1)
    s1.add_argument('--venue', default='Museum of Fine Arts, Boston')
    s1.add_argument('--city', default='Boston')
    s1.add_argument('--exhibition', default='Picasso, Miro, Dali: Unbound')
    s1.add_argument('--artist', default='')
    s1.add_argument('--publisher', default='')
    s1.add_argument('--collaborator', default='')
    s1.add_argument('--credit-line', dest='credit_line', default='')
    s1.set_defaults(func=stage1)

    s2 = sub.add_parser('s2', help='synthesize queries')
    s2.add_argument('--tour-type', default='contained')
    s2.set_defaults(func=stage2)

    s3 = sub.add_parser('s3', help='search and evaluate')
    s3.add_argument('--live', action='store_true', help='actually spend money')
    s3.add_argument('--tour-type', default='contained')
    s3.add_argument('--show', type=int, default=8)
    s3.set_defaults(func=stage3)

    s4 = sub.add_parser('s4', help='coverage and replenishment')
    s4.set_defaults(func=stage4)

    s5 = sub.add_parser('s5', help='material handed to the story pass')
    s5.add_argument('--show', type=int, default=8)
    s5.set_defaults(func=stage5)

    s6 = sub.add_parser('s6', help='the validation gates')
    s6.add_argument('--text-from-tour', action='store_true')
    s6.add_argument('--text', default='')
    s6.set_defaults(func=stage6)

    args = p.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
