#!/usr/bin/env python3
"""repro449.py — LOCAL-449 + LOCAL-450 measurement script.

LOCAL-449 floors:
  A) First timeout: 5.0s, 1 network call.
  B) Already cold: 0.0s, 0 network calls.

LOCAL-450 additions:
  C) Cold host + DB match: 0.0s, 0 network calls, content served.
  D) 429: 1 network call (REST attempt).
"""
import os, sys, time, json
os.environ.setdefault('L447_RETRIEVAL_CHAIN', 'true')
sys.path.insert(0, os.getcwd())
import requests, rag_retriever, dead_host_breaker
from unittest.mock import patch, MagicMock

# ─── Setup ────────────────────────────────────────────────────────────────────

calls = []
def fake_get(url, **kw):
    calls.append((url, kw.get('timeout')))
    time.sleep(kw.get('timeout', 5))  # a host that is down, not refusing
    raise requests.Timeout('simulated dead host')

def fake_get_429(url, **kw):
    calls.append((url, kw.get('timeout')))
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.text = 'Too Many Requests'
    return mock_resp

def mock_db_for_title(title, text):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchall.return_value = [
        (title,
         json.dumps([{'text': text}]),
         json.dumps([{'type': 'wikipedia', 'url': f'https://en.wikipedia.org/wiki/{title}'}])),
    ]
    return mock_conn

# ─── Case A: First timeout (LOCAL-449 floor) ─────────────────────────────────

dead_host_breaker.reset_cold_hosts()
calls.clear()
rag_retriever.requests.get = fake_get
with patch('rag_retriever._fetch_from_stop_corpus', return_value=None):
    t0 = time.time()
    rag_retriever.fetch_wikipedia_summary('Some Stop Title')
elapsed_a = time.time() - t0
calls_a = len(calls)
print(f"A (first timeout):    {elapsed_a:.1f}s, {calls_a} call(s)  [floor: ≤5.0s, 1 call]")

# ─── Case B: Already cold (LOCAL-449 floor) ──────────────────────────────────

calls.clear()
with patch('rag_retriever._fetch_from_stop_corpus', return_value=None):
    t0 = time.time()
    rag_retriever.fetch_wikipedia_summary('Another Stop Title')
elapsed_b = time.time() - t0
calls_b = len(calls)
print(f"B (already cold):     {elapsed_b:.3f}s, {calls_b} call(s)  [floor: ~0s, 0 calls]")

# ─── Case C: Cold + DB match (LOCAL-450 new) ─────────────────────────────────

dead_host_breaker.reset_cold_hosts()
dead_host_breaker.mark_host_cold('en.wikipedia.org', 'test')
calls.clear()
db_content = 'The island of Sainte-Marguerite is the largest of the Lérins Islands. ' * 5
mock_conn = mock_db_for_title('Île Sainte-Marguerite', db_content)

with patch('rag_retriever._get_db_connection', return_value=mock_conn):
    rag_retriever.requests.get = fake_get  # should NOT be called
    t0 = time.time()
    result = rag_retriever.fetch_wikipedia_summary_with_provenance('Île Sainte-Marguerite')
elapsed_c = time.time() - t0
calls_c = len(calls)
source_c = result.get('source', 'NONE')
chars_c = len(result.get('text', ''))
print(f"C (cold + DB match):  {elapsed_c:.3f}s, {calls_c} call(s), source={source_c}, {chars_c} chars  [floor: ~0s, 0 calls, stop_corpus]")

# ─── Case D: 429 (LOCAL-450 new) ─────────────────────────────────────────────

dead_host_breaker.reset_cold_hosts()
calls.clear()
rag_retriever.requests.get = fake_get_429
with patch('rag_retriever._fetch_from_stop_corpus', return_value=None):
    t0 = time.time()
    result = rag_retriever.fetch_wikipedia_summary_with_provenance('Rate Limited Title')
elapsed_d = time.time() - t0
calls_d = len(calls)
print(f"D (429):              {elapsed_d:.3f}s, {calls_d} call(s)  [floor: 1 call]")

# ─── Validation ───────────────────────────────────────────────────────────────

print("\n─── Validation ───")
errors = []
if calls_a != 1:
    errors.append(f"A: expected 1 call, got {calls_a}")
if elapsed_a > 6.0:
    errors.append(f"A: expected ≤5.0s, got {elapsed_a:.1f}s")
if calls_b != 0:
    errors.append(f"B: expected 0 calls, got {calls_b}")
if elapsed_b > 0.1:
    errors.append(f"B: expected <0.1s, got {elapsed_b:.3f}s")
if calls_c != 0:
    errors.append(f"C: expected 0 calls, got {calls_c}")
if source_c != 'stop_corpus':
    errors.append(f"C: expected source=stop_corpus, got {source_c}")
if chars_c < 100:
    errors.append(f"C: expected >100 chars, got {chars_c}")
if calls_d != 1:
    errors.append(f"D: expected 1 call, got {calls_d}")

if errors:
    print("FAIL:")
    for e in errors:
        print(f"  ✗ {e}")
    sys.exit(1)
else:
    print("ALL FLOORS HOLD")
    print(f"  ✓ Cold host: 0 network calls")
    print(f"  ✓ First timeout: {elapsed_a:.1f}s, 1 network call")
    print(f"  ✓ 429: 1 network call")
    print(f"  ✓ Cold + DB: 0 network calls, {chars_c} chars served from stop_corpus")
