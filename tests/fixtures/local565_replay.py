#!/usr/bin/env python3
"""[LOCAL-565] Replay harness — run the 157 recorded Gemini questions through
serper_with_sources (Serper-only; the Gemini side is already recorded).

For each recorded question we run its ORIGINAL prompt through the Serper engine in
its OWN per-question cost scope (cost_accumulator.tour_scope), so every answer
carries its exact Serper + reader cost. A bounded ThreadPool runs several at once;
openai_cost_wrapper + executor context propagation ensure the reader's gpt tokens
are attributed inside the right per-question scope even from worker threads.

Hard stop: OpenAI (llm bucket) cumulative spend is checked against OPENAI_CAP ($8).
If reached we stop issuing new work and report. Serper spend is tracked too.

Output: tests/fixtures/local565/serper_answers.jsonl — one line per question:
  {tour, run, call_site, purpose, prompt, serper{text,sources,supports,queries,error},
   latency_s, cost{llm,search,total}, idx}

NO tour generation happens here — only the recorded research questions are replayed.
"""
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))  # repo root (tests/fixtures/ -> repo)
sys.path.insert(0, ROOT)

QUESTIONS = os.path.join(ROOT, 'tests', 'fixtures', 'local563', 'gemini_questions.jsonl')
OUT_DIR = os.path.join(ROOT, 'tests', 'fixtures', 'local565')
OUT_PATH = os.path.join(OUT_DIR, 'serper_answers.jsonl')

OPENAI_CAP = float(os.environ.get('OPENAI_CAP', '8.0'))
MAX_WORKERS = int(os.environ.get('REPLAY_WORKERS', '6'))

# Serper is the engine under test for the replay.
os.environ['RESEARCH_PROVIDER'] = 'serper'

import cost_accumulator          # noqa: E402
import openai_cost_wrapper       # noqa: E402
import story_leads               # noqa: E402

openai_cost_wrapper.install()
cost_accumulator.install_executor_context_propagation()

_lock = threading.Lock()
_llm_spend = {'usd': 0.0}        # cumulative OpenAI spend, guarded
_stop = threading.Event()


def _load_questions():
    rows = []
    with open(QUESTIONS, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _run_one(idx, q):
    """Run one recorded question through the Serper engine in its own cost scope."""
    if _stop.is_set():
        return None
    prompt = q.get('prompt', '')
    t0 = time.time()
    with cost_accumulator.tour_scope(job_id=f'q{idx}') as acc:
        try:
            ans = story_leads.serper_with_sources(prompt)
        except Exception as e:
            ans = {'text': '', 'sources': [], 'supports': [], 'queries': [],
                   'error': f'{type(e).__name__}: {e}'}
        snap = acc.snapshot()
    latency = time.time() - t0

    llm = snap['breakdown']['llm']
    search = snap['breakdown']['search']
    with _lock:
        _llm_spend['usd'] += llm
        running = _llm_spend['usd']
        if running >= OPENAI_CAP:
            _stop.set()

    return {
        'idx': idx,
        'tour': q.get('tour', ''),
        'run': q.get('run', ''),
        'call_site': q.get('call_site', ''),
        'purpose': q.get('purpose', ''),
        'prompt': prompt,
        'serper': ans,
        'latency_s': round(latency, 3),
        'cost': {'llm': llm, 'search': search, 'total': llm + search},
        'running_openai_usd': round(running, 5),
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    questions = _load_questions()
    print(f'[replay] {len(questions)} recorded questions; '
          f'workers={MAX_WORKERS}; OpenAI cap=${OPENAI_CAP:.2f}')

    results = []
    done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_run_one, i, q): i for i, q in enumerate(questions)}
        for fut in as_completed(futures):
            r = fut.result()
            if r is None:
                continue
            results.append(r)
            done += 1
            if done % 10 == 0 or _stop.is_set():
                tot_s = sum(x['cost']['search'] for x in results)
                print(f'[replay] {done}/{len(questions)} done · '
                      f'OpenAI=${_llm_spend["usd"]:.4f} · Serper=${tot_s:.4f} · '
                      f'last tour={r["tour"]}/{r["run"]}')
            if _stop.is_set():
                print(f'[replay] *** OpenAI cap ${OPENAI_CAP:.2f} reached — '
                      f'stopping new work ***')

    results.sort(key=lambda x: x['idx'])
    with open(OUT_PATH, 'w', encoding='utf-8') as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False) + '\n')

    tot_llm = sum(x['cost']['llm'] for x in results)
    tot_search = sum(x['cost']['search'] for x in results)
    n_ok = sum(1 for x in results if not x['serper'].get('error'))
    n_err = len(results) - n_ok
    avg_lat = sum(x['latency_s'] for x in results) / max(1, len(results))
    print('\n=== REPLAY SUMMARY ===')
    print(f'questions replayed : {len(results)} / {len(questions)}')
    print(f'answers ok / error : {n_ok} / {n_err}')
    print(f'OpenAI (llm) spend : ${tot_llm:.4f}')
    print(f'Serper (search)    : ${tot_search:.4f}')
    print(f'total cost         : ${tot_llm + tot_search:.4f}')
    print(f'avg latency/q      : {avg_lat:.2f}s')
    print(f'stopped at cap?    : {_stop.is_set()}')
    print(f'written            : {OUT_PATH}')


if __name__ == '__main__':
    main()
