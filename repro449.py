import os, sys, time
os.environ.pop('L447_RETRIEVAL_CHAIN', None)   # flag OFF = default
sys.path.insert(0, os.getcwd())
import requests, rag_retriever, dead_host_breaker

calls = []
def fake_get(url, **kw):
    calls.append((url, kw.get('timeout')))
    time.sleep(kw.get('timeout', 5))          # a host that is down, not refusing
    raise requests.Timeout('simulated dead host')
requests.get = fake_get
rag_retriever.requests.get = fake_get

dead_host_breaker.reset_cold_hosts()
t0 = time.time(); rag_retriever.fetch_wikipedia_summary('Some Stop Title')
print(f"A (not yet cold): {time.time()-t0:.1f}s, {len(calls)} calls")
calls.clear()
t0 = time.time(); rag_retriever.fetch_wikipedia_summary('Another Stop Title')
print(f"B (ALREADY COLD): {time.time()-t0:.1f}s, {len(calls)} calls")
