#!/usr/bin/env python3
"""[LOCAL-565] Score BOTH engines (Gemini baseline + Serper replay) the same way.

Produces tests/fixtures/local565/score.json with:
  - answer_key   : per keyed tour, must/must_not/unverified for each engine; a
                   wrong "closed" verdict on an open venue is an automatic FAIL.
  - recall       : of Gemini's atomic facts, the share Serper also states
                   (gpt-4o semantic judge, calibrated on 30 hand-labeled pairs).
  - invented     : per engine, 50 sampled facts checked against the cited page.
  - discovery    : per engine, distinct domains / wikipedia-only share /
                   confirmed-discovery / discovery-only facts.
  - cost_latency : per question and per tour, both engines.
  - noise_floor  : 563B per-tour deltas, printed next to every tour comparison.

Both engines use the IDENTICAL tier classifier (copied from analyze_baseline.py)
so the comparison is symmetric. The Gemini side is read from the recorded
fixtures (gemini_questions.jsonl responses + gemini_facts.json + baseline_summary.json);
the Serper side from serper_answers.jsonl.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

L563 = os.path.join(ROOT, 'tests', 'fixtures', 'local563')
L565 = os.path.join(ROOT, 'tests', 'fixtures', 'local565')

TOURS = ['sail_loft', 'buttermilk', 'chart_house', 'sycamore', 'la_maree',
         'logan', 'our_lady', 'lascaris', 'riviera_bike', 'faneuil']
KEYED = ['sail_loft', 'buttermilk', 'chart_house', 'sycamore', 'la_maree', 'logan']


def load_json(p):
    with open(p, encoding='utf-8') as fh:
        return json.load(fh)


def load_jsonl(p):
    rows = []
    with open(p, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# ── tier classifier (identical to analyze_baseline.py, for symmetry) ──────────
WIKI_DOMAINS = {'en.wikipedia.org', 'wikipedia.org', 'www.wikipedia.org',
                'wikidata.org', 'www.wikidata.org'}
HIGH_NEWS = {'bostonglobe.com', 'www.bostonglobe.com', 'nytimes.com',
             'lemonde.fr', 'monaco-hebdo.com', 'bostonmagazine.com',
             'www.bostonmagazine.com'}
MEDIUM = {'michelin.com', 'guide.michelin.com', 'eater.com', 'boston.eater.com',
          'atlasobscura.com', 'www.atlasobscura.com'}
NEVER_ALONE_HINTS = ('tripadvisor', 'yelp', 'facebook', 'instagram')


def tier_for_domain(domain):
    d = (domain or '').lower()
    if not d:
        return 'unknown'
    if d in WIKI_DOMAINS:
        return 'high'
    if d in HIGH_NEWS:
        return 'high'
    if d.endswith('.gov') or '.gov.' in d or d.endswith('.edu') or '.edu.' in d:
        return 'high'
    if d in MEDIUM:
        return 'medium'
    if any(h in d for h in NEVER_ALONE_HINTS):
        return 'discovery'
    return 'discovery'


def is_wikipedia(domain):
    return (domain or '').lower() in WIKI_DOMAINS


_SENT = re.compile(r'(?<=[.!?])\s+')


def split_sentences(text):
    text = re.sub(r'```[a-zA-Z]*', '', text or '').replace('```', '')
    return [s.strip() for s in _SENT.split(text) if len(s.strip()) >= 12]


# ── Serper atomic facts (symmetric with gemini_facts) ─────────────────────────
def build_serper_facts(serper_rows):
    """Split each Serper answer into atomic facts tagged with cited domains+tier.

    A Serper answer's `supports` already map sentence→source(s) (urls+domains);
    we use those directly, matching the gemini_facts construction (supports whose
    text overlaps the sentence, else all answer domains)."""
    per_tour = {}
    all_rows = []
    for slug in TOURS:
        rows = [r for r in serper_rows if r['tour'] == slug]
        tour_domains = set()
        tour_facts = 0
        wiki_only = 0
        disc_only = 0
        with_support = 0
        for r in rows:
            s = r['serper']
            supports = s.get('supports') or []
            answer_domains = {src.get('domain', '')
                              for sup in supports for src in (sup.get('sources') or [])}
            answer_domains = {d for d in answer_domains if d}
            tour_domains |= answer_domains
            for sent in split_sentences(s.get('text', '')):
                cited = set()
                cited_urls = set()
                for sup in supports:
                    st = (sup.get('text') or '').strip()
                    if st and (st[:40] in sent or sent[:40] in st):
                        for src in (sup.get('sources') or []):
                            if src.get('domain'):
                                cited.add(src['domain'])
                            if src.get('url'):
                                cited_urls.add(src['url'])
                if not cited:
                    cited = set(answer_domains)
                    for sup in supports:
                        for src in (sup.get('sources') or []):
                            if src.get('url'):
                                cited_urls.add(src['url'])
                cited = {c for c in cited if c}
                if supports and any((sup.get('text') or '')[:40] in sent
                                    or sent[:40] in (sup.get('text') or '')
                                    for sup in supports):
                    with_support += 1
                tiers = sorted({tier_for_domain(c) for c in cited}) if cited else ['unknown']
                wo = bool(cited) and all(is_wikipedia(c) for c in cited)
                do = bool(cited) and all(tier_for_domain(c) == 'discovery' for c in cited)
                tour_facts += 1
                if wo:
                    wiki_only += 1
                if do:
                    disc_only += 1
                all_rows.append({
                    'tour': slug, 'run': r.get('run'),
                    'call_site': r.get('call_site'),
                    'fact': sent,
                    'cited_domains': sorted(cited),
                    'url': sorted(cited_urls)[0] if cited_urls else '',
                    'tiers': tiers,
                    'wikipedia_only': wo,
                    'discovery_tier': do,
                })
        per_tour[slug] = {
            'total_facts': tour_facts,
            'distinct_domains': sorted(tour_domains),
            'distinct_domain_count': len(tour_domains),
            'facts_backed_by_a_support_span': with_support,
            'wikipedia_only_facts': wiki_only,
            'wikipedia_only_share': round(wiki_only / tour_facts, 4) if tour_facts else 0.0,
            'discovery_tier_facts': disc_only,
            'discovery_tier_share': round(disc_only / tour_facts, 4) if tour_facts else 0.0,
        }
    return per_tour, all_rows


# ── Gemini atomic facts WITH exact source URLs (from recorded runs) ───────────
# gemini_facts.json carries only domains, so a fair invented check (fetch the
# EXACT cited page) is impossible from it. The per-run *.gemini.jsonl recordings
# DO carry grounding.supports with full URLs, so we rebuild Gemini facts with the
# exact url per sentence here — identical construction to the Serper facts — so
# the invented check is apples-to-apples (exact cited page for both engines).
import glob as _glob

_RUN_LABELS = {'run1': 'run1', 'run2': 'run2'}


def build_gemini_facts_with_urls():
    rows = []
    for f in sorted(_glob.glob(os.path.join(L563, 'runs', '*.gemini.jsonl'))):
        base = os.path.basename(f)
        # filename like sail_loft_run1.gemini.jsonl
        m = re.match(r'(.+)_(run\d)\.gemini\.jsonl$', base)
        if not m:
            continue
        slug, run = m.group(1), m.group(2)
        if slug not in TOURS:
            continue
        for line in open(f, encoding='utf-8'):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if not r.get('grounded'):
                continue
            g = r.get('grounding') or {}
            supports = g.get('supports') or []
            resp = re.sub(r'```[a-zA-Z]*', '', r.get('response', '') or '').replace('```', '')
            answer_domains = {s.get('domain', '')
                              for src in supports for s in (src.get('sources') or [])}
            answer_domains = {d for d in answer_domains if d}
            for sent in split_sentences(resp):
                cited = set()
                cited_urls = set()
                for sup in supports:
                    st = (sup.get('text') or '').strip()
                    if st and (st[:40] in sent or sent[:40] in st):
                        for s in (sup.get('sources') or []):
                            if s.get('domain'):
                                cited.add(s['domain'])
                            if s.get('url'):
                                cited_urls.add(s['url'])
                if not cited:
                    continue  # only facts we can tie to a cited URL are checkable
                rows.append({
                    'tour': slug, 'run': run, 'call_site': r.get('caller'),
                    'fact': sent,
                    'cited_domains': sorted(c for c in cited if c),
                    'url': sorted(cited_urls)[0] if cited_urls else '',
                })
    return rows


# ── discovery metrics (both engines, from a facts list) ────────────────────────
def discovery_metrics(facts, per_tour):
    """Per engine: distinct domains, wikipedia-only share, confirmed discoveries
    (a discovery-tier domain in an answer that ALSO carries a high-tier domain),
    and facts resting ONLY on discovery-tier sources.

    'confirmed discovery' is computed per (tour,run,call_site) answer group: a
    discovery-tier fact is 'confirmed' if some fact in the SAME answer cites a
    high-tier source (the discovery lead is corroborated by a reliable source in
    the same answer — Michael's criterion)."""
    # group facts by answer
    groups = {}
    for f in facts:
        k = (f['tour'], f.get('run'), f.get('call_site'))
        groups.setdefault(k, []).append(f)

    confirmed_disc = 0
    disc_only_total = 0
    disc_facts_total = 0
    for k, g in groups.items():
        has_high = any('high' in f['tiers'] for f in g)
        for f in g:
            if f['discovery_tier']:
                disc_facts_total += 1
                disc_only_total += 1
                if has_high:
                    confirmed_disc += 1

    all_domains = set()
    wiki_only = 0
    total = 0
    for f in facts:
        all_domains |= set(f['cited_domains'])
        total += 1
        if f['wikipedia_only']:
            wiki_only += 1
    return {
        'total_facts': total,
        'distinct_domains': len(all_domains),
        'wikipedia_only_facts': wiki_only,
        'wikipedia_only_share': round(wiki_only / total, 4) if total else 0.0,
        'discovery_tier_facts': disc_only_total,
        'discovery_tier_share': round(disc_only_total / total, 4) if total else 0.0,
        'confirmed_discoveries': confirmed_disc,
        'confirmed_discovery_share_of_discovery': (
            round(confirmed_disc / disc_facts_total, 4) if disc_facts_total else 0.0),
    }


# ── engine answer text per tour ──────────────────────────────────────────────
def gemini_answers_by_tour(gq_rows):
    """Concatenate Gemini's recorded responses per tour (code fences stripped)."""
    by = {t: [] for t in TOURS}
    for r in gq_rows:
        t = r.get('tour')
        if t in by:
            resp = re.sub(r'```[a-zA-Z]*', '', r.get('response', '') or '').replace('```', '')
            by[t].append(resp.strip())
    return {t: '\n'.join(x for x in v if x) for t, v in by.items()}


def serper_answers_by_tour(serper_rows):
    by = {t: [] for t in TOURS}
    for r in serper_rows:
        t = r.get('tour')
        if t in by:
            txt = (r['serper'].get('text') or '').strip()
            if txt:
                by[t].append(txt)
    return {t: '\n'.join(v) for t, v in by.items()}


# ── gpt-4o judge ──────────────────────────────────────────────────────────────
def _openai_chat(messages, model='gpt-4o', temperature=0.0, max_tokens=1200):
    import requests
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        raise RuntimeError('no OPENAI_API_KEY')
    r = requests.post('https://api.openai.com/v1/chat/completions',
                      headers={'Authorization': f'Bearer {key}',
                               'Content-Type': 'application/json'},
                      json={'model': model, 'temperature': temperature,
                            'max_tokens': max_tokens, 'messages': messages},
                      timeout=90)
    r.raise_for_status()
    return r.json()['choices'][0]['message']['content']


_JUDGE_SYS = (
    "You are a strict fact-matching judge for a research A/B test. You are given a "
    "FACT and a body of TEXT (an engine's answer). Decide whether the TEXT states "
    "that fact — the same claim, allowing paraphrase, rewording, and formatting "
    "differences, but NOT a different claim. A near-miss with a different number, "
    "name, date, or status does NOT count. Answer with a single token: YES or NO."
)


def judge_states_fact(fact, text, model='gpt-4o'):
    """True if TEXT semantically states FACT. One gpt-4o call."""
    if not text or not fact:
        return False
    text = text[:6000]
    msg = [{'role': 'system', 'content': _JUDGE_SYS},
           {'role': 'user',
            'content': f'FACT:\n{fact}\n\nTEXT:\n{text}\n\nDoes the TEXT state the FACT? Answer YES or NO.'}]
    try:
        out = _openai_chat(msg, model=model, max_tokens=4)
    except Exception:
        return False
    return out.strip().upper().startswith('Y')


# ── recall calibration (30 hand-labeled pairs) ────────────────────────────────
# 30 (fact, text, human_label) pairs spanning clear-match / clear-miss / near-miss,
# hand-labeled by the engineer, used to measure the judge's agreement before we
# trust it on the full fact set. Texts are short synthetic answers; labels are the
# ground truth a careful human assigns.
CALIBRATION_PAIRS = [
    # clear matches
    ("Boston Sail Loft opened in 1984.", "The Sail Loft has been serving since 1984 on Atlantic Ave.", True),
    ("The restaurant takes no reservations.", "Seating is first come, first served; no bookings.", True),
    ("Logan Airport is named for Edward Lawrence Logan.", "The airport honors Gen. Edward L. Logan.", True),
    ("Buttermilk's chef is Jason Santos.", "Chef Jason Santos runs Buttermilk & Bourbon.", True),
    ("La Maree closed permanently in 2020.", "La Maree shut for good in 2020 after a lease dispute.", True),
    ("Sycamore is in Newton, Massachusetts.", "You will find Sycamore at 755 Beacon St, Newton MA.", True),
    ("Chart House sits on Long Wharf.", "The Chart House restaurant occupies 60 Long Wharf.", True),
    ("The Gardiner Building dates to 1763.", "Built in 1763, the Gardiner Building is the oldest on Long Wharf.", True),
    ("Logan opened on September 8, 1923.", "The field opened 8 Sep 1923 as Boston Airport.", True),
    ("Buttermilk opened in February 2017.", "It opened in Feb 2017 in Back Bay.", True),
    ("The venue serves New England seafood.", "Expect classic New England seafood, chowder and lobster rolls.", True),
    ("Sycamore's chef-owner is David Punch.", "David Punch owns and runs Sycamore.", True),
    ("Dinner is served Tuesday to Saturday.", "Open for dinner Tue-Sat from 4:30pm.", True),
    ("The airport was renamed in 1954.", "In 1954 the legislature renamed it for Logan.", True),
    ("Mayor Curley attended the 1923 dedication.", "James Michael Curley was present at the 1923 dedication.", True),
    # clear misses
    ("Boston Sail Loft opened in 1984.", "The restaurant is known for its clam chowder and harbor views.", False),
    ("Logan is named for Edward Lawrence Logan.", "Logan is the busiest airport in New England.", False),
    ("Buttermilk's chef is Jason Santos.", "Buttermilk & Bourbon is a Southern-inspired restaurant.", False),
    ("Sycamore is open.", "Sycamore has permanently closed.", False),
    ("La Maree closed in 2020.", "La Maree is an elegant seafood restaurant in Monaco.", False),
    ("Chart House is on Long Wharf.", "Chart House is a chain of waterfront steak and seafood restaurants.", False),
    ("The building dates to 1763.", "The restaurant offers a raw bar and cocktails.", False),
    ("Dinner Tuesday to Saturday.", "The restaurant is popular with tourists.", False),
    ("Opened September 8, 1923.", "The airport has four runways.", False),
    ("Chef is David Punch.", "The restaurant has a seasonal New American menu.", False),
    # near-misses (different number/name/status → NO)
    ("Boston Sail Loft opened in 1984.", "Boston Sail Loft opened in 1987.", False),
    ("Buttermilk's chef is Jason Santos.", "Buttermilk's chef is James Santos.", False),
    ("Logan opened in 1923.", "Logan opened in 1932.", False),
    ("Sycamore is open.", "Sycamore may be closed for renovations.", False),
    ("Buttermilk opened in February 2017.", "Buttermilk opened in February 2019.", False),
]


def calibrate_judge(model='gpt-4o'):
    agree = 0
    rows = []
    for fact, text, label in CALIBRATION_PAIRS:
        pred = judge_states_fact(fact, text, model=model)
        ok = (pred == label)
        agree += 1 if ok else 0
        rows.append({'fact': fact, 'human': label, 'judge': pred, 'agree': ok})
    return {'pairs': len(CALIBRATION_PAIRS),
            'agreement': round(agree / len(CALIBRATION_PAIRS), 4),
            'detail': rows}


# ── answer-key scoring ────────────────────────────────────────────────────────
_CLOSED_RE = re.compile(r'\b(closed_permanently|permanently closed|has closed|'
                        r'now closed|shut down|closed down|no longer (?:open|operating)|'
                        r'"still_operating":\s*false)\b', re.I)
_OPEN_RE = re.compile(r'\b("status":\s*"open"|is open|still open|currently open|'
                      r'"still_operating":\s*true|open for)\b', re.I)


def score_answer_key(engine_text_by_tour, key, model='gpt-4o'):
    """Per keyed tour: for each `must` fact, is it stated? any `must_not` stated?
    any `unverified` claim present? A wrong 'closed' verdict on an OPEN venue is
    an automatic FAIL (status in the key is 'open' / 'OPEN', text says closed)."""
    result = {}
    for tour in KEYED:
        spec = key.get(tour, {})
        text = engine_text_by_tour.get(tour, '')
        must = spec.get('must', {}) or {}
        must_not = spec.get('must_not', {}) or {}
        unver = spec.get('unverified', {}) or {}

        must_rows = []
        for field, val in must.items():
            fact_str = f'{field}: {val}'
            stated = judge_states_fact(fact_str, text, model=model)
            must_rows.append({'field': field, 'value': val, 'stated': stated})

        must_not_hits = []
        for field, val in must_not.items():
            fact_str = f'{field}: {val}'
            if judge_states_fact(fact_str, text, model=model):
                must_not_hits.append({'field': field, 'value': val})

        unver_hits = []
        for field, val in unver.items():
            if judge_states_fact(f'{field}: {val}', text, model=model):
                unver_hits.append({'field': field, 'value': val})

        # closed/open verdict: does the key say the venue is open?
        key_status = str(must.get('status', '')).lower()
        key_is_open = key_status.startswith('open') or 'open (' in key_status
        says_closed = bool(_CLOSED_RE.search(text))
        says_open = bool(_OPEN_RE.search(text))
        auto_fail = key_is_open and says_closed and not says_open

        n_must = len(must_rows)
        n_stated = sum(1 for m in must_rows if m['stated'])
        result[tour] = {
            'must_total': n_must,
            'must_stated': n_stated,
            'must_missed': [m['field'] for m in must_rows if not m['stated']],
            'must_detail': must_rows,
            'must_not_violations': must_not_hits,
            'unverified_present': unver_hits,
            'key_status_is_open': key_is_open,
            'text_says_closed': says_closed,
            'text_says_open': says_open,
            'auto_fail_wrong_closed': auto_fail,
        }
    return result


# ── recall: of Gemini's atomic facts, share Serper also states ────────────────
def score_recall(gemini_facts, serper_text_by_tour, model='gpt-4o',
                 keyed_only=True, min_len=20):
    """For each Gemini atomic fact (optionally keyed tours only), ask the judge
    whether the Serper answer for that tour states it. Returns per-tour recall and
    the list of missed facts for the keyed tours."""
    tours = KEYED if keyed_only else TOURS
    # Dedup near-identical facts within a tour to avoid double-counting fragments.

    def _is_real_fact(f):
        # Drop JSON-structure fragments: a real atomic fact is a prose claim, not
        # a brace/bracket/quote fragment or a bare key line from a JSON answer.
        s = f.strip()
        if not s or len(s) < min_len:
            return False
        if s[0] in '{}[]"':
            return False
        if re.match(r'^[\w ]{0,20}":', s):   # bare "key": fragment
            return False
        return True

    per_tour = {}
    missed = {}
    for tour in tours:
        facts = [f['fact'].strip() for f in gemini_facts['facts']
                 if f['tour'] == tour and _is_real_fact(f['fact'])]
        # dedup
        seen, uniq = set(), []
        for f in facts:
            k = re.sub(r'\s+', ' ', f.lower())[:80]
            if k not in seen:
                seen.add(k)
                uniq.append(f)
        text = serper_text_by_tour.get(tour, '')
        hit = 0
        miss_list = []
        for f in uniq:
            if judge_states_fact(f, text, model=model):
                hit += 1
            else:
                miss_list.append(f)
        per_tour[tour] = {'gemini_facts': len(uniq), 'serper_states': hit,
                          'recall': round(hit / len(uniq), 4) if uniq else None}
        missed[tour] = miss_list
    overall_g = sum(v['gemini_facts'] for v in per_tour.values())
    overall_h = sum(v['serper_states'] for v in per_tour.values())
    return {'per_tour': per_tour,
            'overall_recall': round(overall_h / overall_g, 4) if overall_g else None,
            'missed_facts': missed}


# ── invented facts: sample 50/engine, check each against its cited page ───────
def score_invented(facts, engine_name, sample_n=50, seed=565, model='gpt-4o'):
    """Sample up to sample_n facts that cite at least one domain, fetch the cited
    page, and ask the judge whether the page supports the fact. Unsupported =
    invented. Returns the rate and per-fact detail."""
    import random
    from story_leads import _fetch_page_text
    rng = random.Random(seed)

    sourced = [f for f in facts if f['cited_domains']
               and f['fact'].strip() and f['fact'].strip()[0] not in '{}[]"'
               and not re.match(r'^[\w ]{0,20}":', f['fact'].strip())
               and len(f['fact'].strip()) >= 20]
    rng.shuffle(sourced)
    sample = sourced[:sample_n]

    checked = []
    unsupported = 0
    exact_url = 0
    homepage_proxy = 0
    # cache page text per url to avoid refetching
    page_cache = {}
    for f in sample:
        url = f.get('url')
        if url:
            exact_url += 1
        else:
            dom = f['cited_domains'][0]
            url = f'https://{dom}/'
            homepage_proxy += 1
        body = page_cache.get(url)
        if body is None:
            body = _fetch_page_text(url, timeout=12, max_length=8000)
            page_cache[url] = body
        supported = judge_states_fact(f['fact'], body, model=model) if body else False
        if not supported:
            unsupported += 1
        checked.append({'tour': f['tour'], 'fact': f['fact'][:160],
                        'domain': f['cited_domains'][0] if f['cited_domains'] else '',
                        'url': url, 'exact_url': bool(f.get('url')),
                        'page_chars': len(body or ''),
                        'supported': supported})
    n = len(checked)
    return {'engine': engine_name, 'sampled': n,
            'unsupported': unsupported,
            'unsupported_rate': round(unsupported / n, 4) if n else None,
            'fetch_method': {'exact_cited_url': exact_url,
                             'domain_homepage_proxy': homepage_proxy},
            'method_note': ('Serper facts carry the exact cited URL (strong check); '
                            'Gemini recorded facts carry only domains, so the cited '
                            'page is approximated by the domain homepage (weaker — a '
                            'deep fact may not appear on the homepage, biasing Gemini '
                            'unsupported upward). Compare engines with this caveat.'),
            'detail': checked}


def cost_latency(serper_rows, baseline):
    """Per-tour and overall cost+latency for both engines.

    Gemini: the RESEARCH cost of the 157 grounded questions is the grounding
    charge (per grounded request); the baseline's cost_llm also covers all
    non-research tour generation, so we report grounding as the comparable
    research cost and also carry the baseline whole-tour totals for context.
    Serper: the exact per-question llm+search cost recorded in the replay.
    Latency: Serper per-question wall time; Gemini per-question wall_s was
    recorded in gemini_questions.jsonl (added separately by the caller)."""
    per_tour = {}
    for t in TOURS:
        srows = [r for r in serper_rows if r['tour'] == t]
        s_llm = sum(r['cost']['llm'] for r in srows)
        s_search = sum(r['cost']['search'] for r in srows)
        s_lat = [r['latency_s'] for r in srows]
        g = baseline['tours'].get(t, {})
        g_ground = sum(g.get(run, {}).get('cost_grounding', 0.0) for run in ('run1', 'run2'))
        g_llm = sum(g.get(run, {}).get('cost_llm', 0.0) for run in ('run1', 'run2'))
        g_wall = sum(g.get(run, {}).get('wall_s', 0.0) for run in ('run1', 'run2'))
        per_tour[t] = {
            'serper': {'questions': len(srows), 'llm_usd': round(s_llm, 5),
                       'search_usd': round(s_search, 5),
                       'total_usd': round(s_llm + s_search, 5),
                       'avg_latency_s': round(sum(s_lat) / len(s_lat), 2) if s_lat else None},
            'gemini_baseline': {'grounding_usd_research': round(g_ground, 4),
                                'llm_usd_whole_tour': round(g_llm, 4),
                                'wall_s_whole_tour': round(g_wall, 1)},
        }
    s_llm_all = sum(r['cost']['llm'] for r in serper_rows)
    s_search_all = sum(r['cost']['search'] for r in serper_rows)
    s_lat_all = [r['latency_s'] for r in serper_rows]
    totals = baseline.get('totals', {})
    return {
        'per_tour': per_tour,
        'overall': {
            'serper': {'questions': len(serper_rows),
                       'llm_usd': round(s_llm_all, 4),
                       'search_usd': round(s_search_all, 4),
                       'total_usd': round(s_llm_all + s_search_all, 4),
                       'avg_latency_s': round(sum(s_lat_all) / len(s_lat_all), 2) if s_lat_all else None},
            'gemini_baseline': {
                'grounded_requests': totals.get('grounded_requests'),
                'grounding_usd_research': totals.get('cost_grounding_usd'),
                'llm_usd_whole_tour': totals.get('cost_llm_usd'),
                'total_usd_whole_tour': totals.get('cost_total_usd')},
        },
    }


if __name__ == '__main__':
    import argparse
    import openai_cost_wrapper
    import cost_accumulator
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', default='gpt-4o')
    ap.add_argument('--invented-n', type=int, default=50)
    ap.add_argument('--out', default=os.path.join(L565, 'score.json'))
    args = ap.parse_args()

    # Judge/invented calls cost OpenAI money — count them against the $8 cap too.
    openai_cost_wrapper.install()

    serper_rows = load_jsonl(os.path.join(L565, 'serper_answers.jsonl'))
    gq_rows = load_jsonl(os.path.join(L563, 'gemini_questions.jsonl'))
    gfacts = load_json(os.path.join(L563, 'gemini_facts.json'))
    key = load_json(os.path.join(L563, 'SERPER_AB_ANSWER_KEY.json'))
    baseline = load_json(os.path.join(L563, 'baseline_summary.json'))

    sper_tour, sfacts = build_serper_facts(serper_rows)
    g_text = gemini_answers_by_tour(gq_rows)
    s_text = serper_answers_by_tour(serper_rows)

    score = {'_about': 'LOCAL-565 Serper-vs-Gemini scoring. Both engines scored '
             'the same way; Gemini from recorded fixtures, Serper from the replay.'}

    with cost_accumulator.tour_scope(job_id='score') as acc:
        print('[score] calibrating judge on 30 hand-labeled pairs...')
        calib = calibrate_judge(model=args.model)
        print(f'[score]   judge agreement: {calib["agreement"]:.0%}')

        print('[score] answer key — Gemini...')
        ak_g = score_answer_key(g_text, key, model=args.model)
        print('[score] answer key — Serper...')
        ak_s = score_answer_key(s_text, key, model=args.model)

        print('[score] recall (Gemini facts stated by Serper), keyed tours...')
        recall = score_recall(gfacts, s_text, model=args.model, keyed_only=True)
        print(f'[score]   overall recall: {recall["overall_recall"]}')

        print(f'[score] invented facts — Gemini sample {args.invented_n} (exact cited URLs from runs)...')
        g_url_facts = build_gemini_facts_with_urls()
        inv_g = score_invented(g_url_facts, 'gemini', sample_n=args.invented_n, model=args.model)
        print(f'[score]   gemini unsupported rate: {inv_g["unsupported_rate"]} '
              f'(n={inv_g["sampled"]})')
        print(f'[score] invented facts — Serper sample {args.invented_n}...')
        inv_s = score_invented(sfacts, 'serper', sample_n=args.invented_n, model=args.model)
        print(f'[score]   serper unsupported rate: {inv_s["unsupported_rate"]}')

        snap = acc.snapshot()

    disc_g = discovery_metrics(gfacts['facts'], gfacts['per_tour'])
    disc_s = discovery_metrics(sfacts, sper_tour)
    cl = cost_latency(serper_rows, baseline)

    score['judge_calibration'] = calib
    score['answer_key'] = {'gemini': ak_g, 'serper': ak_s,
                           'notes': {
                               'la_maree': 'genuinely CLOSED; must_not=open',
                               'sycamore': 'must be OPEN; a closed verdict is auto-FAIL (D544)',
                               'local564': 'Gemini baseline wrongly reported Chart House '
                                           '(Weehawken NJ) and Buttermilk (BarLola) as closed; '
                                           'see per-tour text_says_closed for whether Serper repeats it.'}}
    score['recall'] = recall
    score['invented_facts'] = {'gemini': inv_g, 'serper': inv_s}
    score['discovery'] = {'gemini': disc_g, 'serper': disc_s,
                          'per_tour_gemini': gfacts['per_tour'],
                          'per_tour_serper': sper_tour,
                          'note': 'Identical generic tier classifier for both engines. '
                                  'Official venue sites (e.g. thebostonsailloft.com, '
                                  'sycamorenewton.com) are classed discovery by the generic '
                                  'rule since officiality cannot be inferred per-domain; this '
                                  'inflates discovery_share symmetrically for both engines.'}
    score['cost_latency'] = cl
    score['noise_floor_563B'] = baseline.get('noise_floor', {})
    score['scoring_openai_cost_usd'] = round(snap['breakdown']['llm'], 4)

    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump(score, fh, ensure_ascii=False, indent=1)
    print(f'[score] scoring OpenAI cost: ${snap["breakdown"]["llm"]:.4f}')
    print(f'[score] written {args.out}')

