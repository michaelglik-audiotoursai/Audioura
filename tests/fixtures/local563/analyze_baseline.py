#!/usr/bin/env python3
"""LOCAL-563B — Gemini baseline analysis (analysis only; no generation, no API).

Reads the recordings in tests/fixtures/local563/runs/ and emits:

  item 1  baseline_summary.json            per tour, run1 vs run2
  item 2  noise_floor  (inside baseline_summary.json, key "noise_floor")
  item 3  gemini_questions.jsonl           one line per grounded Gemini call
          gemini_questions_dedup.json      de-duplicated count per call site
  item 4  gemini_facts.json                atomic facts per answer, domain+tier tagged
  item 5  answer_key_check.json            must / must_not / unverified per keyed tour

All numbers come from the saved files. The tour_quality scorer is re-run on the
saved tour text (offline, no provenance/geocoder) exactly as the brief asks
("tour_quality scorer, applied to the saved tour text").

Run from the repo root:  python3 tests/fixtures/local563/analyze_baseline.py
"""
import json
import os
import re
import sys
import glob
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, 'runs')
REPO_ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
sys.path.insert(0, REPO_ROOT)

from tour_quality import score_tour          # noqa: E402
from sentence_split import split_sentences   # noqa: E402

TOURS = ['sail_loft', 'buttermilk', 'chart_house', 'sycamore', 'la_maree',
         'logan', 'our_lady', 'lascaris', 'riviera_bike', 'faneuil']
RUNS_LABELS = ['run1', 'run2']

# ---- caller -> purpose taxonomy (brief: story leads / restaurant practicals /
#      D545 story facts / stop facts / other) ------------------------------------
PURPOSE_BY_CALLER = {
    'story_production_loop.py:run_for_stop:263': 'D545 story facts',
    'story_production_loop.py:run_for_stop:302': 'D545 story facts',
    'generate_tour_text.py:_generate_tour_text_impl:12106': 'story leads',
    'restaurant_practicals.py:_gemini:153': 'restaurant practicals',
    'restaurant_practicals.py:venue_still_operating:328': 'restaurant practicals',
    'stop_knowledge_fallback.py:_gemini_facts:233': 'stop facts',
    'stop_knowledge_fallback.py:_gemini_facts:251': 'stop facts',
    'venue_parts.py:default_ask:360': 'stop facts',
    'venue_parts.py:default_ask_grounded:371': 'stop facts',
}


def purpose_for(caller):
    return PURPOSE_BY_CALLER.get(caller, 'other')


def load_json(path):
    with open(path) as fh:
        return json.load(fh)


def read_text(path):
    with open(path) as fh:
        return fh.read()


# -------------------------------------------------------------------------------
# Gemini jsonl parsing. The recorder stored every field as a string; grounding is
# a repr of a dict. Parse robustly.
# -------------------------------------------------------------------------------
def _as_bool(v):
    return v is True or v == 'True'


def _parse_grounding(raw):
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        pass
    try:
        import ast
        return ast.literal_eval(raw)
    except Exception:
        return {}


def iter_gemini(slug, run):
    path = os.path.join(RUNS, f'{slug}_{run}.gemini.jsonl')
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        d['_grounding'] = _parse_grounding(d.get('grounding'))
        yield d


# -------------------------------------------------------------------------------
# Log parsing: gate removal lines, D538 restaurant practicals.
# -------------------------------------------------------------------------------
RE_235 = re.compile(r'\[LOCAL-235\].*?(\d+)\s+sentences?\s+deleted')
RE_229 = re.compile(r'\[LOCAL-229\].*?(\d+)\s+group\(s\)\s+blocked')
RE_472 = re.compile(r'\[LOCAL-472\].*?(\d+)\s+removal')


def gate_counts_from_log(slug, run):
    """Count gate-deleted sentences from the .log, independent of the .json.

    235 = R10 unfulfilled-promise sentences deleted
    229 = contradicted claim groups blocked
    472 = stop-specificity ungrounded entity removals (count the per-entity lines)
    """
    path = os.path.join(RUNS, f'{slug}_{run}.log')
    c235 = c229 = c472 = 0
    if not os.path.exists(path):
        return {'local235': 0, 'local229': 0, 'local472': 0, 'total': 0}
    for ln in open(path):
        m = RE_235.search(ln)
        if m:
            c235 = int(m.group(1))
        m = RE_229.search(ln)
        if m:
            c229 = int(m.group(1))
        # 472 summary line gives the total; count the individual UNGROUNDED lines
        if '[LOCAL-472] UNGROUNDED entity' in ln:
            c472 += 1
    return {'local235': c235, 'local229': c229, 'local472': c472,
            'total': c235 + c229 + c472}


RE_D538_FACTS = re.compile(r"\[D538\]\s+'([^']+)'\s+via\s+(\S+):\s+(.*)")
RE_D538_DROP = re.compile(r"\[D538\]\s+.*DROPPED\s+'([^']+)'\s+—\s+reported permanently closed:\s*(.*)")


def restaurant_practicals_from_log(slug, run):
    """Pull the [D538] restaurant practical lines straight from the log."""
    path = os.path.join(RUNS, f'{slug}_{run}.log')
    stops = []
    closed = []
    if not os.path.exists(path):
        return {'stops': [], 'closed_dropped': []}
    for ln in open(path):
        m = RE_D538_FACTS.search(ln)
        if m:
            name, provider, raw = m.group(1), m.group(2), m.group(3).strip()
            fields = {}
            for part in raw.split(', '):
                if '=' in part:
                    k, v = part.split('=', 1)
                    fields[k.strip()] = v.strip()
            stops.append({
                'name': name, 'provider': provider,
                'hours': 'hours' in fields and bool(fields.get('hours')),
                'closed_days': bool(fields.get('closed_days')),
                'reservation': 'reservation' in fields and bool(fields.get('reservation')),
                'price_band': 'price_band' in fields and bool(fields.get('price_band')),
                'raw': raw,
            })
        m = RE_D538_DROP.search(ln)
        if m:
            closed.append({'name': m.group(1), 'reason': m.group(2).strip()[:200]})
    return {'stops': stops, 'closed_dropped': closed}


# -------------------------------------------------------------------------------
# ITEM 1 — per-run summary
# -------------------------------------------------------------------------------
def summarize_run(slug, run):
    jpath = os.path.join(RUNS, f'{slug}_{run}.json')
    tpath = os.path.join(RUNS, f'{slug}_{run}.txt')
    meta = load_json(jpath)

    # Re-run the scorer on the saved tour text (offline), as the brief asks.
    text = read_text(tpath) if os.path.exists(tpath) else ''
    req = meta.get('stops_requested')
    is_bldg = meta.get('is_building_tour', False)
    scored = score_tour(text, requested_stops=req, is_building_tour=is_bldg)
    defects = sorted(scored['defects'].keys())
    metrics = scored['metrics']

    # Gate deletions from the log (counted independently of the json).
    gates_log = gate_counts_from_log(slug, run)
    gates_json = meta.get('measures', {}).get('gate_removals', {})

    # Restaurant practicals from the log D538 lines.
    rp_log = restaurant_practicals_from_log(slug, run)
    rp_json = meta.get('measures', {}).get('restaurant_practicals', {})

    # closed verdict: a stop appears in the D538 DROPPED (permanently closed) list
    closed_names = [c['name'] for c in rp_log['closed_dropped']]

    # Grounded request count + cost from the cost record (authoritative).
    cost = meta.get('cost_record', {})
    breakdown = cost.get('breakdown', {})
    grounded = meta.get('gemini_calls', {}).get('grounded_this_run',
                                                cost.get('grounding_requests', 0))

    return {
        'slug': slug,
        'run': run,
        'request': meta.get('request'),
        'tour_type': meta.get('tour_type'),
        'status': meta.get('status'),
        # story score / defects — from re-scoring the saved text
        'story_score_clean': scored['clean'],
        'defects': defects,
        'defect_count': len(defects),
        # people / stops
        'named_people': metrics.get('named_people'),
        'stops_delivered': metrics.get('stops_delivered'),
        'stops_requested': req,
        'dates': metrics.get('dates'),
        'chars': metrics.get('chars'),
        # gate deletions (log-counted) with json cross-check
        'gate_deleted_sentences': gates_log,
        'gate_removals_json': {
            'local235': gates_json.get('local235_r10_sentences_deleted'),
            'local229': gates_json.get('local229_contradicted_groups_blocked'),
            'local472': gates_json.get('local472_specificity_removals'),
            'total': gates_json.get('total'),
        },
        # restaurant practicals from D538
        'restaurant_practicals': {
            'stops': rp_log['stops'],
            'hours_count': sum(1 for s in rp_log['stops'] if s['hours']),
            'reservation_count': sum(1 for s in rp_log['stops'] if s['reservation']),
            'price_band_count': sum(1 for s in rp_log['stops'] if s['price_band']),
            'closed_verdict': closed_names,
            'closed_dropped': rp_log['closed_dropped'],
        },
        # grounded requests + cost + wall time
        'grounded_requests': grounded,
        'cost_llm': round(breakdown.get('llm', 0.0), 6),
        'cost_grounding': round(breakdown.get('grounding', 0.0), 6),
        'cost_tour_total': round(cost.get('tour_total_cost', 0.0), 6),
        'wall_s': meta.get('wall_s'),
    }


# -------------------------------------------------------------------------------
# ITEM 2 — noise floor per numeric measure
# -------------------------------------------------------------------------------
NOISE_MEASURES = [
    ('story_defect_count', lambda r: r['defect_count']),
    ('named_people', lambda r: r['named_people']),
    ('stops_delivered', lambda r: r['stops_delivered']),
    ('gate_deleted_total', lambda r: r['gate_deleted_sentences']['total']),
    ('gate_235', lambda r: r['gate_deleted_sentences']['local235']),
    ('gate_229', lambda r: r['gate_deleted_sentences']['local229']),
    ('gate_472', lambda r: r['gate_deleted_sentences']['local472']),
    ('rp_hours_count', lambda r: r['restaurant_practicals']['hours_count']),
    ('rp_reservation_count', lambda r: r['restaurant_practicals']['reservation_count']),
    ('rp_price_band_count', lambda r: r['restaurant_practicals']['price_band_count']),
    ('rp_closed_verdict', lambda r: len(r['restaurant_practicals']['closed_verdict'])),
    ('grounded_requests', lambda r: r['grounded_requests']),
    ('cost_llm', lambda r: r['cost_llm']),
    ('cost_grounding', lambda r: r['cost_grounding']),
    ('wall_s', lambda r: r['wall_s']),
    ('chars', lambda r: r['chars']),
    ('dates', lambda r: r['dates']),
]


def noise_floor(summary_by_tour):
    out = {}
    for name, fn in NOISE_MEASURES:
        deltas = {}
        for slug in TOURS:
            r1 = summary_by_tour[slug]['run1']
            r2 = summary_by_tour[slug]['run2']
            try:
                d = abs((fn(r1) or 0) - (fn(r2) or 0))
            except TypeError:
                d = None
            deltas[slug] = d
        vals = [v for v in deltas.values() if v is not None]
        out[name] = {
            'per_tour_abs_delta': deltas,
            'mean': round(sum(vals) / len(vals), 4) if vals else None,
            'max': max(vals) if vals else None,
            'max_tour': max(deltas, key=lambda k: (deltas[k] is not None, deltas[k] or 0)) if vals else None,
        }
    return out


# -------------------------------------------------------------------------------
# ITEM 3 — gemini question list
# -------------------------------------------------------------------------------
def grounding_sources(g):
    """Return [{domain, uri}] from a grounding dict, de-duplicated, order-stable."""
    out = []
    seen = set()
    for s in (g.get('sources') or []):
        dom = s.get('domain', '')
        uri = s.get('url') or s.get('uri', '')
        key = (dom, uri)
        if key not in seen:
            seen.add(key)
            out.append({'domain': dom, 'uri': uri})
    return out


def build_questions():
    rows = []
    dedup = collections.defaultdict(lambda: {'total': 0, 'distinct_prompts': set()})
    for slug in TOURS:
        for run in RUNS_LABELS:
            for d in iter_gemini(slug, run):
                if not _as_bool(d.get('grounded')):
                    continue
                caller = d.get('caller', '')
                g = d['_grounding']
                row = {
                    'tour': slug,
                    'run': run,
                    'call_site': caller,
                    'purpose': purpose_for(caller),
                    'grounded': True,
                    'charged': _as_bool(d.get('charged')),
                    'model': d.get('model'),
                    'prompt': d.get('prompt', ''),
                    'response': d.get('response', ''),
                    'grounding_sources': grounding_sources(g),
                    'grounding_queries': g.get('queries') or [],
                    'ts': d.get('ts'),
                    'wall_s': d.get('wall_s'),
                }
                rows.append(row)
                dd = dedup[caller]
                dd['total'] += 1
                dd['distinct_prompts'].add(d.get('prompt', ''))
    dedup_out = {}
    for caller, dd in dedup.items():
        dedup_out[caller] = {
            'purpose': purpose_for(caller),
            'total_calls': dd['total'],
            'distinct_prompts': len(dd['distinct_prompts']),
        }
    return rows, dedup_out


# -------------------------------------------------------------------------------
# ITEM 4 — atomic facts per answer, domain + reliability tier
# -------------------------------------------------------------------------------
def load_answer_key():
    return load_json(os.path.join(HERE, 'SERPER_AB_ANSWER_KEY.json'))


# reliability tier classifier from _reliability_tiers in the answer key.
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
        return 'high'            # wikipedia/wikidata are 'high' per the key
    if d in HIGH_NEWS:
        return 'high'
    if d.endswith('.gov') or '.gov.' in d or d.endswith('.edu') or '.edu.' in d:
        return 'high'
    if d in MEDIUM:
        return 'medium'
    if any(h in d for h in NEVER_ALONE_HINTS):
        return 'discovery'
    # official site of a place is 'high' but we cannot know that generically;
    # everything else unclassified defaults to discovery (blogs/forums/review/niche).
    return 'discovery'


def is_wikipedia(domain):
    return (domain or '').lower() in WIKI_DOMAINS


def build_facts():
    """Split each grounded response into atomic facts, tag domains + tier."""
    key = load_answer_key()  # not used for tiering per-domain beyond the tier spec
    per_tour = {}
    all_rows = []
    for slug in TOURS:
        tour_domains = set()
        tour_facts = 0
        wiki_only_facts = 0
        discovery_facts = 0
        facts_with_support = 0
        for run in RUNS_LABELS:
            for d in iter_gemini(slug, run):
                if not _as_bool(d.get('grounded')):
                    continue
                g = d['_grounding']
                resp = d.get('response', '') or ''
                # strip code fences so sentence split sees prose/JSON lines cleanly
                clean = re.sub(r'```[a-zA-Z]*', '', resp).replace('```', '')
                sents = split_sentences(clean)
                supports = g.get('supports') or []
                answer_domains = {s['domain'] for s in grounding_sources(g)}
                tour_domains |= answer_domains
                for sent in sents:
                    sent_s = sent.strip()
                    if len(sent_s) < 12:
                        continue
                    # domains cited for THIS fact: match supports whose text
                    # overlaps the sentence; fall back to all answer domains.
                    cited = set()
                    for sup in supports:
                        stext = (sup.get('text') or '').strip()
                        if stext and (stext[:40] in sent_s or sent_s[:40] in stext):
                            for src in (sup.get('sources') or []):
                                cited.add(src.get('domain', ''))
                    if not cited:
                        cited = set(answer_domains)
                    cited = {c for c in cited if c}
                    if supports and any(
                            (sup.get('text') or '')[:40] in sent_s
                            or sent_s[:40] in (sup.get('text') or '')
                            for sup in supports):
                        facts_with_support += 1
                    tiers = sorted({tier_for_domain(c) for c in cited}) if cited else ['unknown']
                    wiki_only = bool(cited) and all(is_wikipedia(c) for c in cited)
                    disc = bool(cited) and all(tier_for_domain(c) == 'discovery' for c in cited)
                    tour_facts += 1
                    if wiki_only:
                        wiki_only_facts += 1
                    if disc:
                        discovery_facts += 1
                    all_rows.append({
                        'tour': slug, 'run': run,
                        'call_site': d.get('caller'),
                        'fact': sent_s,
                        'cited_domains': sorted(cited),
                        'tiers': tiers,
                        'wikipedia_only': wiki_only,
                        'discovery_tier': disc,
                    })
        per_tour[slug] = {
            'total_facts': tour_facts,
            'distinct_domains': sorted(tour_domains),
            'distinct_domain_count': len(tour_domains),
            'facts_backed_by_a_support_span': facts_with_support,
            'wikipedia_only_facts': wiki_only_facts,
            'wikipedia_only_share': round(wiki_only_facts / tour_facts, 4) if tour_facts else 0.0,
            'discovery_tier_facts': discovery_facts,
            'discovery_tier_share': round(discovery_facts / tour_facts, 4) if tour_facts else 0.0,
        }
    return per_tour, all_rows


# -------------------------------------------------------------------------------
# ITEM 5 — answer-key check
# -------------------------------------------------------------------------------
def _norm(s):
    return re.sub(r'[^a-z0-9 ]', ' ', (s or '').lower())


def _haystacks(slug):
    """All text where a fact could be stated: both tour texts + both answers."""
    parts = []
    for run in RUNS_LABELS:
        tpath = os.path.join(RUNS, f'{slug}_{run}.txt')
        if os.path.exists(tpath):
            parts.append(('tour_text', run, read_text(tpath)))
        for d in iter_gemini(slug, run):
            if _as_bool(d.get('grounded')):
                parts.append(('gemini_answer', run, d.get('response', '') or ''))
    return parts


# key value -> list of acceptable substrings (normalised) to look for
def _fact_probes(value):
    """Derive a few robust probes from an answer-key value string."""
    v = value
    probes = []
    # years
    probes += re.findall(r'\b(1[6-9]\d\d|20\d\d)\b', v)
    # quoted phrases / proper names: words of length>=4, keep multiword runs
    # pull capitalised runs and distinctive tokens
    caps = re.findall(r'[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*', v)
    probes += [c for c in caps if len(c) >= 4]
    # key single words
    for w in re.findall(r'[A-Za-z]{5,}', v):
        probes.append(w)
    # dedupe, normalise
    seen = []
    for p in probes:
        n = _norm(p).strip()
        if n and n not in seen:
            seen.append(n)
    return seen


# generic words that are too common to identify a specific unverified claim
_GENERIC = {'governor', 'mayor', 'general', 'major', 'street', 'avenue', 'road',
            'boston', 'city', 'open', 'closed', 'status', 'hotel', 'airport',
            'restaurant', 'chef', 'owner', 'president', 'senator'}


def _distinctive_probe(probes):
    """Pick the rarest / most specific probe token (longest non-generic word)."""
    cands = [p for p in probes if p and p not in _GENERIC and len(p) >= 5]
    if not cands:
        cands = [p for p in probes if p]
    singles = [c for c in cands if ' ' not in c]
    pool = singles or cands
    return max(pool, key=len) if pool else None


def answer_key_check():
    key = load_answer_key()
    out = {}
    for slug, spec in key.items():
        if slug.startswith('_') or slug == 'not_keyed':
            continue
        if not isinstance(spec, dict):
            continue
        hay = _haystacks(slug)
        hay_norm = [(src, run, _norm(txt)) for (src, run, txt) in hay]
        tour_only = ' '.join(_norm(txt) for (src, _, txt) in hay if src == 'tour_text')
        gem_only = ' '.join(_norm(txt) for (src, _, txt) in hay if src == 'gemini_answer')
        full = tour_only + ' ' + gem_only

        rec = {'must': {}, 'must_not': {}, 'unverified': {}, 'sources': spec.get('sources', [])}

        # D538 "permanently closed" verdicts in either run, and whether any names
        # the keyed venue itself (the Sycamore D544 auto-FAIL case).
        closed_names = []
        for run in RUNS_LABELS:
            rp = restaurant_practicals_from_log(slug, run)
            for c in rp['closed_dropped']:
                closed_names.append({'run': run, 'name': c['name']})
        venue_token = _norm(slug.replace('_', ' ')).split()[0]
        venue_closed = [c for c in closed_names
                        if venue_token and venue_token in _norm(c['name'])]
        rec['d538_closed_verdicts'] = closed_names
        rec['keyed_venue_got_closed_verdict'] = bool(venue_closed)

        for fname, fval in (spec.get('must') or {}).items():
            probes = _fact_probes(fval)
            hits = [p for p in probes if p and p in full]
            in_tour = any(p in tour_only for p in hits)
            in_gem = any(p in gem_only for p in hits)
            rec['must'][fname] = {
                'value': fval,
                'probes': probes,
                'matched_probes': hits,
                'stated': bool(hits),
                'in_tour_text': in_tour,
                'in_gemini_answer': in_gem,
            }

        for fname, fval in (spec.get('must_not') or {}).items():
            probes = _fact_probes(fval)
            hits = [p for p in probes if p and p in full]
            rec['must_not'][fname] = {
                'value': fval,
                'probes': probes,
                'matched_probes': hits,
                'appeared': bool(hits),
            }

        for fname, fval in (spec.get('unverified') or {}).items():
            # Use the most DISTINCTIVE token of the claim name (the rarest proper
            # noun), not generic words like "governor", so the match is specific.
            name_probes = _fact_probes(fname)
            distinctive = _distinctive_probe(name_probes)
            probes = [distinctive] if distinctive else name_probes
            hits = [p for p in probes if p and p in full]
            # if it appeared, with what source? scan grounding domains ONLY of the
            # answers that actually contain the distinctive token.
            srcs = set()
            fallback_srcs = set()
            backed_by_support = False
            appeared_in_answers = []
            if hits:
                for run in RUNS_LABELS:
                    for d in iter_gemini(slug, run):
                        if not _as_bool(d.get('grounded')):
                            continue
                        resp = _norm(d.get('response', ''))
                        if any(p in resp for p in hits):
                            appeared_in_answers.append(f'{run}:{d.get("caller")}')
                            g = d['_grounding']
                            for sup in (g.get('supports') or []):
                                if any(p in _norm(sup.get('text', '')) for p in hits):
                                    backed_by_support = True
                                    for s in (sup.get('sources') or []):
                                        srcs.add(s.get('domain', ''))
                            for s in grounding_sources(g):
                                fallback_srcs.add(s['domain'])
            rec['unverified'][fname] = {
                'note': fval,
                'distinctive_probe': distinctive,
                'appeared_in_answers': appeared_in_answers,
                'appeared': bool(hits),
                'appeared_in_tour_text': any(p in tour_only for p in hits),
                'backed_by_grounding_support_span': backed_by_support,
                'support_span_sources': sorted(s for s in srcs if s),
                'answer_domains_when_appeared': sorted(s for s in fallback_srcs if s),
            }
        out[slug] = rec
    return out


# -------------------------------------------------------------------------------
# main
# -------------------------------------------------------------------------------
def main():
    # ---- item 1 ----
    summary_by_tour = {}
    for slug in TOURS:
        summary_by_tour[slug] = {
            'run1': summarize_run(slug, 'run1'),
            'run2': summarize_run(slug, 'run2'),
        }

    # ---- item 2 ----
    nf = noise_floor(summary_by_tour)

    # ---- totals ----
    tot_grounded = sum(summary_by_tour[s][r]['grounded_requests'] or 0
                       for s in TOURS for r in RUNS_LABELS)
    tot_llm = round(sum(summary_by_tour[s][r]['cost_llm'] or 0
                        for s in TOURS for r in RUNS_LABELS), 4)
    tot_grounding = round(sum(summary_by_tour[s][r]['cost_grounding'] or 0
                             for s in TOURS for r in RUNS_LABELS), 4)

    baseline = {
        '_about': 'LOCAL-563B Gemini baseline. Per-tour run1 vs run2 across the 10 '
                  'recorded tours (commit 3af65a5). Story score/defects re-computed '
                  'by tour_quality.score_tour on the saved tour text (offline). '
                  'Gate deletions counted from the .log [LOCAL-235/229/472] lines. '
                  'Restaurant practicals and closed verdict from the [D538] lines. '
                  'Grounded request count and cost from each run json cost_record.',
        'tours': summary_by_tour,
        'totals': {
            'grounded_requests': tot_grounded,
            'cost_llm_usd': tot_llm,
            'cost_grounding_usd': tot_grounding,
            'cost_total_usd': round(tot_llm + tot_grounding, 4),
        },
        'noise_floor': nf,
    }
    with open(os.path.join(HERE, 'baseline_summary.json'), 'w') as fh:
        json.dump(baseline, fh, indent=1, ensure_ascii=False)
    print('wrote baseline_summary.json  (grounded=%d  llm=$%.2f  grounding=$%.2f)'
          % (tot_grounded, tot_llm, tot_grounding))

    # ---- item 3 ----
    rows, dedup = build_questions()
    with open(os.path.join(HERE, 'gemini_questions.jsonl'), 'w') as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    with open(os.path.join(HERE, 'gemini_questions_dedup.json'), 'w') as fh:
        json.dump({'de_duplicated_count_per_call_site': dedup,
                   'total_grounded_calls': len(rows)}, fh, indent=1, ensure_ascii=False)
    print('wrote gemini_questions.jsonl  (%d grounded calls)' % len(rows))

    # ---- item 4 ----
    per_tour_facts, fact_rows = build_facts()
    with open(os.path.join(HERE, 'gemini_facts.json'), 'w') as fh:
        json.dump({'_about': 'Item 4: atomic facts per grounded Gemini answer, split '
                             'with sentence_split.split_sentences, each tagged with the '
                             'domains its groundingSupports cite and a reliability tier '
                             '(_reliability_tiers in SERPER_AB_ANSWER_KEY.json).',
                   'per_tour': per_tour_facts,
                   'facts': fact_rows}, fh, indent=1, ensure_ascii=False)
    print('wrote gemini_facts.json  (%d atomic facts)' % len(fact_rows))

    # ---- item 5 ----
    akc = answer_key_check()
    with open(os.path.join(HERE, 'answer_key_check.json'), 'w') as fh:
        json.dump(akc, fh, indent=1, ensure_ascii=False)
    print('wrote answer_key_check.json  (%d keyed tours)' % len(akc))

    return baseline, rows, dedup, per_tour_facts, fact_rows, akc


if __name__ == '__main__':
    main()
